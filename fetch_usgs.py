"""
Turns everything in data/raw/ (NWS stageflow snapshots + USGS pages) into one
clean table: data/clean/records.csv, one row per value.

Rules (see the record table in our notes):
  - observed and forecast rows are never mixed, `kind` says which
  - flow is always cfs (NWS sends kcfs), stage is always ft
  - placeholder values like -9999 become empty, never a number
  - all times are UTC "YYYY-MM-DDTHH:MM:SSZ"
  - observations show up in every NWS snapshot, so they're kept once
    (first time we saw them). forecasts are kept per issuance.
"""

import csv
import gzip
import json
from datetime import datetime, timezone
from pathlib import Path

RAW = Path("data/raw")
OUT = Path("data/clean/records.csv")

FIELDS = ["record_id", "gauge_id", "source", "kind", "parameter", "value", "unit",
          "valid_time_utc", "issued_time_utc", "retrieved_time_utc", "status", "raw_file"]

USGS_PARAMS = {"00065": "stage", "00060": "flow"}


def utc(ts):
    """Any ISO timestamp -> UTC string ending in Z. Empty/None stays empty."""
    if not ts:
        return ""
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)  # assume UTC if they didn't say
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def compact(ts):
    # 2026-11-22T00:00:00Z -> 20261122T0000Z, for ids
    return ts.replace("-", "").replace(":", "")[:13] + "Z" if ts else "none"


def clean_value(v, unit):
    """Returns (value, unit) with placeholders dropped and flow in cfs."""
    u = (unit or "").strip()
    scale = 1
    if u == "kcfs":
        u, scale = "cfs", 1000
    elif u == "ft^3/s":
        u = "cfs"
    # unit gets fixed first so even empty rows end up with cfs, not kcfs

    try:
        v = float(v)
    except (TypeError, ValueError):
        return None, u
    if v <= -999:  # NWS uses -9999 and -999 for "no data"
        return None, u
    return round(v * scale, 3), u


def make_row(gauge, source, kind, param, value, unit, valid, issued, retrieved, status, raw):
    rid = f"{gauge}-{'fcst' if kind == 'forecast' else 'obs'}-{param}-{compact(valid)}"
    if kind == "forecast":
        rid += f"-iss{compact(issued)}"
    return {
        "record_id": rid, "gauge_id": gauge, "source": source, "kind": kind,
        "parameter": param, "value": "" if value is None else value, "unit": unit,
        "valid_time_utc": valid, "issued_time_utc": issued,
        "retrieved_time_utc": retrieved, "status": status, "raw_file": raw,
    }


def load_fetch_times():
    """archiver.py logs when each NWS file was fetched, look those up by path."""
    log = RAW / "fetch_log.csv"
    if not log.exists():
        return {}
    with open(log, newline="") as f:
        return {r["file"]: r["fetched_at_utc"] for r in csv.DictReader(f)}


def nws_rows(path, retrieved):
    gauge = path.parent.name
    raw = path.as_posix()
    with gzip.open(path, "rt", encoding="utf-8") as f:
        d = json.load(f)

    for kind in ("observed", "forecast"):
        block = d.get(kind) or {}
        if kind == "forecast" and str(block.get("issuedTime", "")).startswith("0001-"):
            continue  # no-forecast placeholder, same as in archiver.py
        for pt in block.get("data", []):
            valid = utc(pt["validTime"])
            # obs: each point has its own publish time. forecast: the whole
            # forecast shares one issuedTime
            issued = utc(pt.get("generatedTime")) if kind == "observed" else utc(block.get("issuedTime"))
            for param, key, unit_key in (("stage", "primary", "primaryUnits"),
                                         ("flow", "secondary", "secondaryUnits")):
                val, unit = clean_value(pt.get(key), block.get(unit_key))
                yield make_row(gauge, "NWS", kind, param, val, unit, valid, issued,
                               retrieved, "", raw)


def usgs_rows(path):
    site = path.parent.name
    raw = path.as_posix()
    # filename is {pcode}_{fetched}_p{n}.json.gz, fetched time is in there
    fetched = path.name.split("_")[1].replace("Z", "")
    day, clock = fetched.split("T")
    retrieved = f"{day}T{clock.replace('-', ':')}Z"

    with gzip.open(path, "rt", encoding="utf-8") as f:
        d = json.load(f)
    for feat in d.get("features", []):
        p = feat.get("properties", {})
        param = USGS_PARAMS.get(p.get("parameter_code"))
        if not param:
            continue
        val, unit = clean_value(p.get("value"), p.get("unit_of_measure"))
        yield make_row(site, "USGS", "observed", param, val, unit, utc(p.get("time")),
                       utc(p.get("last_modified")), retrieved,
                       p.get("approval_status") or "", raw)


def main():
    fetch_times = load_fetch_times()
    rows = {}
    revised = 0

    # sorted so older files are read first -> "first time we saw it" wins
    nws_files = sorted(p for p in RAW.glob("*/*.json.gz") if p.parent.name != "USGS")
    usgs_files = sorted(RAW.glob("USGS/*/*.json.gz"))

    for path in nws_files:
        for r in nws_rows(path, fetch_times.get(path.as_posix(), "")):
            old = rows.get(r["record_id"])
            if old is None:
                rows[r["record_id"]] = r
            elif old["value"] != r["value"]:
                revised += 1  # agency changed a value after the fact, keep the first one

    for path in usgs_files:
        for r in usgs_rows(path):
            rows.setdefault(r["record_id"], r)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    out_rows = sorted(rows.values(), key=lambda r: (r["gauge_id"], r["kind"], r["parameter"],
                                                    r["valid_time_utc"], r["issued_time_utc"]))
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(out_rows)

    blanks = sum(1 for r in out_rows if r["value"] == "")
    print(f"read {len(nws_files)} NWS files, {len(usgs_files)} USGS files")
    print(f"wrote {len(out_rows)} records to {OUT} ({blanks} with no value)")
    if revised:
        print(f"note: {revised} observations were revised in later snapshots (kept first version)")


if __name__ == "__main__":
    main()