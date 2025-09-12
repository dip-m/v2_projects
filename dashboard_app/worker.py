import os, json, time, logging
from datetime import datetime, timezone
from pathlib import Path
from .data_store import STORE

DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
CACHE_FILE = DATA_DIR / "signals.json"

REFRESH_SEC = int(os.getenv("REFRESH_SEC", "600"))
SLEEP_BETWEEN = float(os.getenv("SLEEP_BETWEEN", "1.6"))

def refresh_once():
    rows = STORE.signals(include_analyst=True)
    payload = {"as_of": datetime.now(timezone.utc).isoformat(), "signals": rows}
    tmp = CACHE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    tmp.replace(CACHE_FILE)

def main():
    logging.basicConfig(level=logging.INFO)
    while True:
        try:
            refresh_once()
            logging.info("Signals refreshed.")
        except Exception as e:
            logging.exception("Refresh failed: %s", e)
        time.sleep(REFRESH_SEC)

if __name__ == "__main__":
    main()
