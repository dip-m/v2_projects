// Vanilla JavaScript for the dashboard UI with expandable sub-rows.
//
// This script replaces the previous React-based implementation which could not
// run in the browser without a build step. It fetches data from the FastAPI
// backend and constructs a table where each ticker has a summary row and an
// expandable details row. The details row contains additional technical
// indicators. The script also handles bucket management and adding/removing
// tickers.

// Utility functions for formatting values
function fmtNum(v, d = 2) {
  if (v === null || v === undefined || v === "") return "—";
  const n = Number(v);
  return isNaN(n) ? String(v) : n.toFixed(d);
}

function fmtPct(v) {
  if (v === null || v === undefined || v === "") return "—";
  const n = Number(v);
  return isNaN(n) ? String(v) : n.toFixed(2) + "%";
}

function fmtBool(b) {
  return b === true ? "Yes" : b === false ? "No" : "—";
}

function fmtDate(d) {
  if (!d) return "—";
  try {
    const date = new Date(d);
    if (!isNaN(date)) return date.toISOString().slice(0, 10);
  } catch (_) {}
  return String(d);
}

// Global to hold bucket names (used for selects)
let DATASTORE_BUCKETS = [];

// Formatting helper for move ticker selects
async function moveTicker(symbol, bucket) {
  if (!symbol || !bucket) return;
  try {
    await fetch(`/tickers/move`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol, bucket }),
    });
    await loadBuckets();
    await loadSignals();
    await loadBreadth();
  } catch (err) {
    console.error(err);
  }
}

async function removeTicker(symbol) {
  if (!symbol) return;
  try {
    await fetch(`/tickers/${encodeURIComponent(symbol)}`, { method: "DELETE" });
    await loadBuckets();
    await loadSignals();
    await loadBreadth();
  } catch (err) {
    console.error(err);
  }
}

function setStatus(id, message) {
  const p = document.getElementById(id);
  if (!p) return;
  p.textContent = message;
  setTimeout(() => {
    p.textContent = "";
  }, 5000);
}

// Fetch and render bucket cards and populate selects
async function loadBuckets() {
  try {
    const resp = await fetch("/buckets");
    const data = await resp.json();
    const buckets = data.buckets || {};
    DATASTORE_BUCKETS = Object.keys(buckets);
    // Populate bucket select in Add Ticker form
    const bucketSelect = document.getElementById("bucketSelect");
    if (bucketSelect) {
      // Remove all options except the first (default)
      while (bucketSelect.options.length > 1) {
        bucketSelect.remove(1);
      }
      DATASTORE_BUCKETS.forEach((bucket) => {
        const opt = document.createElement("option");
        opt.value = bucket;
        opt.textContent = bucket;
        bucketSelect.appendChild(opt);
      });
    }
    // Render bucket cards
    const container = document.getElementById("bucketsContainer");
    if (container) {
      container.innerHTML = "";
      Object.entries(buckets).forEach(([name, list]) => {
        const card = document.createElement("div");
        card.className = "bucket-card";
        const title = document.createElement("div");
        title.className = "bucket-label";
        title.textContent = name;
        card.appendChild(title);
        const chipContainer = document.createElement("div");
        chipContainer.style.display = "flex";
        chipContainer.style.flexWrap = "wrap";
        chipContainer.style.marginTop = "8px";
        (list || []).forEach((sym) => {
          const chip = document.createElement("div");
          chip.className = "ticker-chip";
          chip.textContent = sym;
          chipContainer.appendChild(chip);
        });
        card.appendChild(chipContainer);
        container.appendChild(card);
      });
    }
  } catch (ex) {
    console.error(ex);
  }
}

// Fetch and render signals in a table with expandable sub-rows
async function loadSignals() {
  try {
    const resp = await fetch("/signals?include_analyst=true");
    const data = await resp.json();
    const signals = data.signals || [];
    const tbody = document.getElementById("signalsBody");
    if (!tbody) return;
    tbody.innerHTML = "";

    signals.forEach((row) => {
      // Main row
      const trMain = document.createElement("tr");
      // Expand/collapse cell
      const tdToggle = document.createElement("td");
      const btn = document.createElement("button");
      btn.textContent = "▶";
      btn.style.border = "1px solid #ddd";
      btn.style.borderRadius = "4px";
      btn.style.width = "24px";
      btn.style.height = "24px";
      btn.style.display = "flex";
      btn.style.alignItems = "center";
      btn.style.justifyContent = "center";
      btn.style.cursor = "pointer";
      btn.dataset.expanded = "false";
      tdToggle.appendChild(btn);
      trMain.appendChild(tdToggle);
      // Ticker cell: symbol, name (if available), bucket pill
      const tdTicker = document.createElement("td");
      const symbolSpan = document.createElement("span");
      symbolSpan.style.fontWeight = "600";
      symbolSpan.textContent = row.symbol;
      tdTicker.appendChild(symbolSpan);
      if (row.name) {
        const nameSpan = document.createElement("span");
        nameSpan.style.color = "#64748b"; // slate-500
        nameSpan.style.marginLeft = "4px";
        nameSpan.textContent = `(${row.name})`;
        tdTicker.appendChild(nameSpan);
      }
      if (row.bucket) {
        const pill = document.createElement("span");
        pill.textContent = row.bucket;
        pill.style.backgroundColor = "#e0f2fe"; // sky-100
        pill.style.color = "#0369a1"; // sky-700
        pill.style.fontSize = "0.75rem";
        pill.style.padding = "2px 6px";
        pill.style.borderRadius = "9999px";
        pill.style.marginLeft = "6px";
        tdTicker.appendChild(pill);
      }
      trMain.appendChild(tdTicker);
      // Close price
      const tdClose = document.createElement("td");
      tdClose.textContent = fmtNum(row.close);
      trMain.appendChild(tdClose);
      // Entry
      const tdEntry = document.createElement("td");
      tdEntry.textContent = fmtBool(row.entry_ok);
      trMain.appendChild(tdEntry);
      // RSI zone
      const tdRsiZone = document.createElement("td");
      tdRsiZone.textContent = row.rsi_zone || "—";
      trMain.appendChild(tdRsiZone);
      // Pivot
      const tdPivot = document.createElement("td");
      tdPivot.textContent = row.pivot !== null && row.pivot !== undefined ? String(row.pivot) : "—";
      trMain.appendChild(tdPivot);
      // Avg Target
      const tdAvgTarget = document.createElement("td");
      tdAvgTarget.textContent = fmtNum(row.avg_target);
      trMain.appendChild(tdAvgTarget);
      // Buy %
      const tdBuy = document.createElement("td");
      tdBuy.textContent = fmtPct(row.buy_pct);
      trMain.appendChild(tdBuy);
      // Next earnings
      const tdNextEr = document.createElement("td");
      tdNextEr.textContent = fmtDate(row.next_earnings);
      trMain.appendChild(tdNextEr);
      // Re-entry
      const tdReentry = document.createElement("td");
      tdReentry.textContent = row.reentry === true || row.reentry === "yes" || row.reentry === "ok" ? "Re-entry ✓" : row.reentry === false || row.reentry === "no" ? "No" : "—";
      trMain.appendChild(tdReentry);

      // Details row (initially hidden)
      const trSub = document.createElement("tr");
      trSub.style.display = "none";
      const tdBlank = document.createElement("td");
      trSub.appendChild(tdBlank);
      const tdSub = document.createElement("td");
      tdSub.colSpan = 9;
      // Create a container for indicator blocks
      const container = document.createElement("div");
      container.style.display = "grid";
      container.style.gridTemplateColumns = "repeat(auto-fill, minmax(180px, 1fr))";
      container.style.gap = "0.5rem";
      container.style.backgroundColor = "#f8fafc"; // slate-50
      container.style.padding = "0.75rem";
      container.style.borderRadius = "0.5rem";

      // Moving averages block
      const blockMA = document.createElement("div");
      blockMA.style.border = "1px solid #e2e8f0";
      blockMA.style.borderRadius = "0.5rem";
      blockMA.style.padding = "0.5rem";
      const maTitle = document.createElement("div");
      maTitle.style.fontSize = "0.75rem";
      maTitle.style.fontWeight = "600";
      maTitle.style.color = "#64748b";
      maTitle.textContent = "Moving Averages";
      blockMA.appendChild(maTitle);
      const maLine1 = document.createElement("div");
      const delta50 = row.sma50 !== null && row.sma50 !== undefined && row.close !== null && row.close !== undefined ? ((row.close - row.sma50) / row.sma50) * 100 : null;
      maLine1.textContent = `SMA50: ${fmtNum(row.sma50)} (${fmtPct(delta50)})`;
      blockMA.appendChild(maLine1);
      const maLine2 = document.createElement("div");
      const delta200 = row.sma200 !== null && row.sma200 !== undefined && row.close !== null && row.close !== undefined ? ((row.close - row.sma200) / row.sma200) * 100 : null;
      maLine2.textContent = `SMA200: ${fmtNum(row.sma200)} (${fmtPct(delta200)})`;
      blockMA.appendChild(maLine2);
      const maLine3 = document.createElement("div");
      maLine3.textContent = `Above 50: ${fmtBool(row.above50)} · Above 200: ${fmtBool(row.above200)}`;
      blockMA.appendChild(maLine3);
      container.appendChild(blockMA);

      // MACD block
      const blockMACD = document.createElement("div");
      blockMACD.style.border = "1px solid #e2e8f0";
      blockMACD.style.borderRadius = "0.5rem";
      blockMACD.style.padding = "0.5rem";
      const macdTitle = document.createElement("div");
      macdTitle.style.fontSize = "0.75rem";
      macdTitle.style.fontWeight = "600";
      macdTitle.style.color = "#64748b";
      macdTitle.textContent = "MACD";
      blockMACD.appendChild(macdTitle);
      const macdLine = document.createElement("div");
      macdLine.textContent = `MACD: ${fmtNum(row.macd, 4)} · Signal: ${fmtNum(row.macd_signal, 4)} · Hist: ${fmtNum(row.macd_hist, 4)}`;
      blockMACD.appendChild(macdLine);
      container.appendChild(blockMACD);

      // Volume block
      const blockVol = document.createElement("div");
      blockVol.style.border = "1px solid #e2e8f0";
      blockVol.style.borderRadius = "0.5rem";
      blockVol.style.padding = "0.5rem";
      const volTitle = document.createElement("div");
      volTitle.style.fontSize = "0.75rem";
      volTitle.style.fontWeight = "600";
      volTitle.style.color = "#64748b";
      volTitle.textContent = "Volume";
      blockVol.appendChild(volTitle);
      const volLine1 = document.createElement("div");
      volLine1.textContent = `Vol: ${fmtNum(row.volume)}`;
      blockVol.appendChild(volLine1);
      const volLine2 = document.createElement("div");
      volLine2.textContent = `Avg20: ${fmtNum(row.avg20)}`;
      blockVol.appendChild(volLine2);
      container.appendChild(blockVol);

      // 52-week range block
      const blockRange = document.createElement("div");
      blockRange.style.border = "1px solid #e2e8f0";
      blockRange.style.borderRadius = "0.5rem";
      blockRange.style.padding = "0.5rem";
      const rangeTitle = document.createElement("div");
      rangeTitle.style.fontSize = "0.75rem";
      rangeTitle.style.fontWeight = "600";
      rangeTitle.style.color = "#64748b";
      rangeTitle.textContent = "52-week Range";
      blockRange.appendChild(rangeTitle);
      const rangeLine1 = document.createElement("div");
      rangeLine1.textContent = `High: ${fmtNum(row.w52_high)}`;
      blockRange.appendChild(rangeLine1);
      const rangeLine2 = document.createElement("div");
      rangeLine2.textContent = `Low: ${fmtNum(row.w52_low)}`;
      blockRange.appendChild(rangeLine2);
      container.appendChild(blockRange);

      // Analyst block
      const blockAnalyst = document.createElement("div");
      blockAnalyst.style.border = "1px solid #e2e8f0";
      blockAnalyst.style.borderRadius = "0.5rem";
      blockAnalyst.style.padding = "0.5rem";
      const analystTitle = document.createElement("div");
      analystTitle.style.fontSize = "0.75rem";
      analystTitle.style.fontWeight = "600";
      analystTitle.style.color = "#64748b";
      analystTitle.textContent = "Analysts";
      blockAnalyst.appendChild(analystTitle);
      const analystLine1 = document.createElement("div");
      analystLine1.textContent = `Buy: ${fmtPct(row.buy_pct)} · Hold: ${fmtPct(row.hold_pct)} · Sell: ${fmtPct(row.sell_pct)}`;
      blockAnalyst.appendChild(analystLine1);
      const analystLine2 = document.createElement("div");
      analystLine2.textContent = `Total: ${row.analyst_total !== null && row.analyst_total !== undefined ? row.analyst_total : "—"}`;
      blockAnalyst.appendChild(analystLine2);
      container.appendChild(blockAnalyst);

      // Distance to target block
      const blockTarget = document.createElement("div");
      blockTarget.style.border = "1px solid #e2e8f0";
      blockTarget.style.borderRadius = "0.5rem";
      blockTarget.style.padding = "0.5rem";
      const targetTitle = document.createElement("div");
      targetTitle.style.fontSize = "0.75rem";
      targetTitle.style.fontWeight = "600";
      targetTitle.style.color = "#64748b";
      targetTitle.textContent = "Target Gap";
      blockTarget.appendChild(targetTitle);
      const targetLine1 = document.createElement("div");
      targetLine1.textContent = `Dist to Target: ${fmtPct(row.dist_to_target_pct)}`;
      blockTarget.appendChild(targetLine1);
      container.appendChild(blockTarget);

      // Extras block
      const blockExtras = document.createElement("div");
      blockExtras.style.border = "1px solid #e2e8f0";
      blockExtras.style.borderRadius = "0.5rem";
      blockExtras.style.padding = "0.5rem";
      const extrasTitle = document.createElement("div");
      extrasTitle.style.fontSize = "0.75rem";
      extrasTitle.style.fontWeight = "600";
      extrasTitle.style.color = "#64748b";
      extrasTitle.textContent = "Extras";
      blockExtras.appendChild(extrasTitle);
      const extrasLine1 = document.createElement("div");
      extrasLine1.textContent = `Pivot: ${fmtNum(row.pivot)}`;
      blockExtras.appendChild(extrasLine1);
      const extrasLine2 = document.createElement("div");
      extrasLine2.textContent = `RSI Zone: ${row.rsi_zone || "—"}`;
      blockExtras.appendChild(extrasLine2);
      const extrasLine3 = document.createElement("div");
      extrasLine3.textContent = `Re-entry: ${row.reentry !== null && row.reentry !== undefined ? row.reentry : "—"}`;
      blockExtras.appendChild(extrasLine3);
      container.appendChild(blockExtras);

      tdSub.appendChild(container);
      trSub.appendChild(tdSub);

      // Toggle click handler
      btn.addEventListener("click", () => {
        const expanded = btn.dataset.expanded === "true";
        btn.dataset.expanded = (!expanded).toString();
        trSub.style.display = expanded ? "none" : "table-row";
        btn.style.transform = expanded ? "rotate(0deg)" : "rotate(90deg)";
      });

      tbody.appendChild(trMain);
      tbody.appendChild(trSub);
    });
  } catch (ex) {
    console.error(ex);
  }
}

// Fetch and display risk-on indicator
async function loadBreadth() {
  try {
    const resp = await fetch("/breadth");
    const data = await resp.json();
    const span = document.getElementById("riskOn");
    if (!span) return;
    if (data.risk_on === true) {
      span.textContent = "Yes";
      span.style.color = "green";
    } else if (data.risk_on === false) {
      span.textContent = "No";
      span.style.color = "red";
    } else {
      span.textContent = "—";
      span.style.color = "inherit";
    }
  } catch (ex) {
    console.error(ex);
  }
}

// Entry point: set up event listeners and load data
document.addEventListener("DOMContentLoaded", () => {
  // Add ticker form
  const addTickerForm = document.getElementById("addTickerForm");
  if (addTickerForm) {
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
          let err;
          try {
            err = await resp.json();
          } catch (ex) {
            err = {};
          }
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
  }
  // Refresh signals button(s)
  document.querySelectorAll("#refreshSignals").forEach((btn) => {
    btn.addEventListener("click", async () => {
      await loadSignals();
      await loadBreadth();
    });
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
  // Initial data load
  loadBuckets();
  loadSignals();
  loadBreadth();
});