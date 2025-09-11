// JavaScript to drive the dashboard UI. It uses the Fetch API to
// communicate with the FastAPI backend and manipulates the DOM to
// present tickers, buckets and signals. This script relies on
// elements defined in ``templates/index.html``.

document.addEventListener("DOMContentLoaded", () => {
  loadBuckets();
  loadSignals();
  loadBreadth();

  // Hook up the add ticker form
  const addTickerForm = document.getElementById("addTickerForm");
  addTickerForm.addEventListener("submit", async (evt) => {
    evt.preventDefault();
    const tickerInput = document.getElementById("tickerInput");
    const bucketSelect = document.getElementById("bucketSelect");
    const symbol = tickerInput.value.trim();
    const bucket = bucketSelect.value || undefined;
    if (!symbol) {
      setStatus("addTickerStatus", "Please enter a ticker symbol.");
      return;
    }
    try {
      const resp = await fetch("/tickers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol, bucket }),
      });
      if (!resp.ok) {
        const err = await resp.json();
        setStatus("addTickerStatus", `Error: ${err.detail || resp.status}`);
      } else {
        tickerInput.value = "";
        bucketSelect.selectedIndex = 0;
        setStatus("addTickerStatus", `Added ${symbol.toUpperCase()}`);
        await loadBuckets();
        await loadSignals();
        await loadBreadth();
      }
    } catch (ex) {
      setStatus("addTickerStatus", `Error: ${ex.message}`);
    }
  });

  // Refresh signals button
  document.getElementById("refreshSignals").addEventListener("click", async () => {
    await loadSignals(true);
    await loadBreadth();
  });

  // Save layout button
  const saveBtn = document.getElementById("saveLayoutBtn");
  if (saveBtn) {
    saveBtn.addEventListener("click", async () => {
      try {
        const resp = await fetch("/save", { method: "POST" });
        if (resp.ok) {
          alert("Saved.");
        } else {
          alert("Save failed.");
        }
      } catch (ex) {
        alert("Save failed.");
      }
    });
  }

  // Bucket management buttons
  const createBucketBtn = document.getElementById("createBucketBtn");
  const renameBucketBtn = document.getElementById("renameBucketBtn");
  const deleteBucketBtn = document.getElementById("deleteBucketBtn");

  if (createBucketBtn) {
    createBucketBtn.addEventListener("click", async () => {
      const name = document.getElementById("newBucketName").value.trim();
      if (!name) return;
      try {
        await fetch("/buckets", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name }),
        });
        document.getElementById("newBucketName").value = "";
        await loadBuckets();
        await loadSignals();
        await loadBreadth();
      } catch (err) {
        console.error(err);
      }
    });
  }

  if (renameBucketBtn) {
    renameBucketBtn.addEventListener("click", async () => {
      const oldName = document.getElementById("oldBucketName").value.trim();
      const newName = document.getElementById("newBucketName2").value.trim();
      if (!oldName || !newName) return;
      try {
        await fetch("/buckets/rename", {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ old: oldName, new: newName }),
        });
        document.getElementById("oldBucketName").value = "";
        document.getElementById("newBucketName2").value = "";
        await loadBuckets();
        await loadSignals();
        await loadBreadth();
      } catch (err) {
        console.error(err);
      }
    });
  }

  if (deleteBucketBtn) {
    deleteBucketBtn.addEventListener("click", async () => {
      const name = document.getElementById("delBucketName").value.trim();
      if (!name) return;
      try {
        await fetch(`/buckets/${encodeURIComponent(name)}`, { method: "DELETE" });
        document.getElementById("delBucketName").value = "";
        await loadBuckets();
        await loadSignals();
        await loadBreadth();
      } catch (err) {
        console.error(err);
      }
    });
  }
});

function setStatus(id, message) {
  const p = document.getElementById(id);
  p.textContent = message;
  setTimeout(() => {
    p.textContent = "";
  }, 5000);
}

async function loadBuckets() {
  try {
    const resp = await fetch("/buckets");
    const data = await resp.json();
    const buckets = data.buckets || {};
    // Update global bucket list early so that selects below can use it
    DATASTORE_BUCKETS = Object.keys(buckets);
    // Populate bucket select
    const bucketSelect = document.getElementById("bucketSelect");
    // Clear existing options except first
    while (bucketSelect.options.length > 1) {
      bucketSelect.remove(1);
    }
    DATASTORE_BUCKETS.forEach((bucket) => {
      const opt = document.createElement("option");
      opt.value = bucket;
      opt.textContent = bucket;
      bucketSelect.appendChild(opt);
    });
    // Render bucket lists
    const container = document.getElementById("bucketsContainer");
    container.innerHTML = "";
    for (const [bucketName, symbols] of Object.entries(buckets)) {
      const section = document.createElement("div");
      section.className = "bucket";
      const label = document.createElement("div");
      label.className = "bucket-label";
      label.textContent = bucketName;
      section.appendChild(label);
      const list = document.createElement("ul");
      list.style.listStyle = "none";
      list.style.paddingLeft = "0";
      symbols.forEach((sym) => {
        const li = document.createElement("li");
        li.style.marginBottom = "4px";
        const symbolSpan = document.createElement("span");
        symbolSpan.textContent = sym;
        symbolSpan.style.marginRight = "0.5rem";
        li.appendChild(symbolSpan);
        // Create select to move bucket
        const moveSel = document.createElement("select");
        moveSel.setAttribute("data-symbol", sym);
        DATASTORE_BUCKETS.forEach((b) => {
          const opt = document.createElement("option");
          opt.value = b;
          opt.textContent = b;
          if (b === bucketName) opt.selected = true;
          moveSel.appendChild(opt);
        });
        moveSel.addEventListener("change", async (evt) => {
          const newBucket = evt.target.value;
          const symbol = evt.target.getAttribute("data-symbol");
          await moveTicker(symbol, newBucket);
        });
        li.appendChild(moveSel);
        // Remove button
        const delButton = document.createElement("button");
        delButton.textContent = "x";
        delButton.style.marginLeft = "0.5rem";
        delButton.addEventListener("click", async () => {
          await removeTicker(sym);
        });
        li.appendChild(delButton);
        list.appendChild(li);
      });
      section.appendChild(list);
      container.appendChild(section);
    }
  } catch (ex) {
    console.error(ex);
  }
}

// Global variable to hold bucket names for the move selects
let DATASTORE_BUCKETS = [];

// Sorting globals for signals table
let SORT_KEY = "symbol";
let SORT_DIR = "asc"; // "asc" | "desc"

function fmt2(x) {
  if (x === null || x === undefined || x === "") return "";
  const n = Number(x);
  if (Number.isNaN(n)) return x;
  return n.toFixed(2);
}

async function loadSignals(forceUpdate = false) {
  try {
    // Call signals endpoint with analyst data
    const resp = await fetch("/signals?include_analyst=true");
    const data = await resp.json();
    let signals = data.signals || [];
    // Sort by current sort key
    signals.sort((a, b) => {
      const ka = a[SORT_KEY];
      const kb = b[SORT_KEY];
      const isNum = (v) => typeof v === "number" || (!isNaN(Number(v)) && v !== null && v !== undefined && v !== "");
      let cmp;
      if (isNum(ka) && isNum(kb)) {
        cmp = Number(ka) - Number(kb);
      } else {
        cmp = String(ka ?? "").localeCompare(String(kb ?? ""));
      }
      return SORT_DIR === "asc" ? cmp : -cmp;
    });
    const tbody = document.getElementById("signalsBody");
    tbody.innerHTML = "";
    signals.forEach((row) => {
      const tr = document.createElement("tr");
      const cells = [
        row.symbol,
        row.bucket,
        fmt2(row.close),
        fmt2(row.sma50),
        fmt2(row.sma200),
        row.above50 ? "Yes" : "No",
        row.above200 ? "Yes" : "No",
        row.entry_ok ? "✅" : "—",
        fmt2(row.avg_target),
        fmt2(row.buy_pct),
        fmt2(row.hold_pct),
        fmt2(row.sell_pct),
        row.analyst_total ?? "",
        fmt2(row.dist_to_target_pct),
        (row.next_earnings || ""),
      ];
      cells.forEach((val) => {
        const td = document.createElement("td");
        td.textContent = val === null || val === undefined ? "" : val;
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    // Make headers clickable for sorting
    const thead = document.querySelector("#signalsTable thead");
    thead.querySelectorAll("th").forEach((th) => {
      th.style.cursor = "pointer";
      th.onclick = () => {
        const k = th.getAttribute("data-key");
        if (!k) return;
        if (SORT_KEY === k) {
          SORT_DIR = SORT_DIR === "asc" ? "desc" : "asc";
        } else {
          SORT_KEY = k;
          SORT_DIR = "asc";
        }
        loadSignals();
      };
    });
  } catch (ex) {
    console.error(ex);
  }
}

async function loadBreadth() {
  try {
    const resp = await fetch("/breadth");
    const data = await resp.json();
    const span = document.getElementById("riskOn");
    if (data.risk_on === true) {
      span.textContent = "Yes";
      span.style.color = "green";
    } else if (data.risk_on === false) {
      span.textContent = "No";
      span.style.color = "red";
    } else {
      span.textContent = "—";
      span.style.color = "";
    }
  } catch (ex) {
    console.error(ex);
  }
}

async function removeTicker(symbol) {
  try {
    const resp = await fetch(`/tickers/${symbol}`, { method: "DELETE" });
    if (resp.ok) {
      await loadBuckets();
      await loadSignals();
      await loadBreadth();
    }
  } catch (ex) {
    console.error(ex);
  }
}

async function moveTicker(symbol, newBucket) {
  try {
    const resp = await fetch("/tickers/move", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol, bucket: newBucket }),
    });
    if (resp.ok) {
      await loadBuckets();
      await loadSignals();
      await loadBreadth();
    } else {
      const err = await resp.json();
      console.error(err);
    }
  } catch (ex) {
    console.error(ex);
  }
}