"""
Pulls USGS continuous (15-min) readings for our sites and saves the raw
responses, same idea as archiver.py. Unlike NWS, USGS keeps history, so this
doesn't need to run on a schedule. Run it when we need data.

    python fetch_usgs.py                       # last 30 days
    python fetch_usgs.py --days 7
    python fetch_usgs.py --start 2018-12-20 --end 2019-01-05   # past flood
"""

import argparse
import gzip
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

SITES = [
    "USGS-02465000",  # Black Warrior at Northport
    "USGS-02465005",  # below Oliver L&D (same gauge NWS uses for TODA1 obs)
]
PARAMS = {"00065": "stage", "00060": "flow"}

BASE = "https://api.waterdata.usgs.gov/ogcapi/v0/collections/continuous/items"
OUT_DIR = Path("data/raw/USGS")
HEADERS = {"User-Agent": "black-warrior-briefings (UA CS451 class project)"}


def fetch_all_pages(site, pcode, time_arg):
    params = {
        "f": "json",
        "monitoring_location_id": site,
        "parameter_code": pcode,
        "time": time_arg,
        "skipGeometry": "true",
        "limit": 10000,
    }
    pages = []
    url = BASE
    while url:
        r = requests.get(url, params=params, headers=HEADERS, timeout=60)
        r.raise_for_status()
        pages.append(r.text)
        # the "next" link already has every query param baked in
        nxt = [l["href"] for l in r.json().get("links", []) if l.get("rel") == "next"]
        url, params = (nxt[0], None) if nxt else (None, None)
    return pages


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--start", help="YYYY-MM-DD")
    ap.add_argument("--end", help="YYYY-MM-DD")
    args = ap.parse_args()

    if args.start and args.end:
        time_arg = f"{args.start}T00:00:00Z/{args.end}T23:59:59Z"
    else:
        time_arg = f"P{args.days}D"  # ISO duration, means "the last N days"

    fetched = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")

    for site in SITES:
        for pcode, name in PARAMS.items():
            try:
                pages = fetch_all_pages(site, pcode, time_arg)
            except (requests.RequestException, ValueError) as e:
                print(f"[{site} {name}] failed: {e}")
                continue

            n = sum(len(json.loads(p).get("features", [])) for p in pages)
            if n == 0:
                # some sites just don't measure flow, that's fine
                print(f"[{site} {name}] no data")
                continue

            out = OUT_DIR / site
            out.mkdir(parents=True, exist_ok=True)
            for i, text in enumerate(pages):
                path = out / f"{pcode}_{fetched}_p{i}.json.gz"
                with gzip.open(path, "wt", encoding="utf-8") as f:
                    f.write(text)
            print(f"[{site} {name}] saved {n} readings in {len(pages)} page(s)")


if __name__ == "__main__":
    main()