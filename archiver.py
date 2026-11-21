"""
Forecast archiver for the Black Warrior River gauges.

NWPS only serves the *current* forecast for a gauge, so if we don't save
them as they come out they're gone. This grabs the stageflow response for
each gauge and saves it raw (gzipped) whenever there's a new forecast.

Run it by hand:   python archiver.py
GitHub Actions also runs it every hour (see .github/workflows/archive.yml).
"""

import csv
import gzip
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

GAUGES = ["TODA1", "TCLA1"]  # Oliver L&D, Holt L&D
URL = "https://api.water.noaa.gov/nwps/v1/gauges/{lid}/stageflow"

RAW_DIR = Path("data/raw")
LOG_FILE = RAW_DIR / "fetch_log.csv"

HEADERS = {"User-Agent": "black-warrior-briefings (UA CS451 class project)"}


def save_name(issued_time):
    # windows doesn't allow ':' in filenames
    return issued_time.replace(":", "-") + ".json.gz"


def log_save(lid, fetched_at, issued_time, path):
    new_file = not LOG_FILE.exists()
    with open(LOG_FILE, "a", newline="") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["gauge", "fetched_at_utc", "forecast_issued_utc", "file"])
        w.writerow([lid, fetched_at, issued_time, path.as_posix()])


def archive_gauge(lid):
    """Returns True if the fetch worked (whether or not anything new was saved)."""
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        resp = requests.get(URL.format(lid=lid), headers=HEADERS, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as e:
        print(f"[{lid}] fetch failed: {e}")
        return False

    # some gauges come back with no forecast at all. NWPS doesn't just leave it
    # out though, it sends issuedTime = 0001-01-01T00:00:00Z (a "zero" date)
    # and an empty data list, so check for both
    forecast = data.get("forecast") or {}
    issued = forecast.get("issuedTime") or ""
    if issued.startswith("0001-") or not issued or not forecast.get("data"):
        print(f"[{lid}] no current forecast, skipping")
        return True

    out_dir = RAW_DIR / lid
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / save_name(issued)

    if out_path.exists():
        print(f"[{lid}] forecast {issued} already saved")
        return True

    # save the exact text we got back, not the parsed dict
    with gzip.open(out_path, "wt", encoding="utf-8") as f:
        f.write(resp.text)
    log_save(lid, fetched_at, issued, out_path)
    print(f"[{lid}] saved new forecast {issued} -> {out_path}")
    return True


def main():
    results = [archive_gauge(lid) for lid in GAUGES]
    # only fail the run if nothing worked, one bad gauge shouldn't block the rest
    if not any(results):
        sys.exit(1)


if __name__ == "__main__":
    main()