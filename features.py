"""
Builds the facts a briefing is written from, for each gauge, as of a given time.
Both the template baseline and the LLM read this output, and every fact carries
the record_id(s) it came from so the checker can trace it back.

    python features.py                                  # as of right now
    python features.py --as-of 2026-11-24T18:00:00Z     # replay a past moment

"As of" means we only use data that existed at that moment: observations up to
that time and forecasts issued before it. That's what lets us replay old floods.
"""

import argparse
import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from gauges import (GAUGES, STALE_FORECAST_HOURS, STALE_OBS_HOURS, CONFLICT_FT,
                    STEADY_FT)

RECORDS = Path("data/clean/records.csv")
OUT_DIR = Path("data/features")


def parse(ts):
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def fmt(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ") if dt else None


def hours(td):
    return round(td.total_seconds() / 3600, 1)


def load_records():
    rows = []
    with open(RECORDS, newline="") as f:
        for r in csv.DictReader(f):
            if r["value"] == "" or r["parameter"] != "stage":
                continue  # only stage for now, flow is too spotty across gauges
            r["value"] = float(r["value"])
            r["valid"] = parse(r["valid_time_utc"])
            r["issued"] = parse(r["issued_time_utc"]) if r["issued_time_utc"] else None
            rows.append(r)
    return rows


def known_at(r):
    """When a reading actually became public. NWS readings show up ~1h after
    they're measured, so use their publish time. USGS last_modified can be years
    later for old data (it changes when they approve it), so only trust it if
    it's within a few hours of the reading, otherwise fall back to valid time."""
    if r["issued"] and r["issued"] - r["valid"] <= timedelta(hours=6):
        return r["issued"]
    return r["valid"]


def obs_series(rows, gauge, as_of):
    s = [r for r in rows if r["gauge_id"] == gauge and r["kind"] == "observed"
         and known_at(r) <= as_of]
    return sorted(s, key=lambda r: r["valid"])


def value_near(series, target, tol=timedelta(minutes=30)):
    """Closest reading to target within tol, or None."""
    best = None
    for r in series:
        d = abs(r["valid"] - target)
        if d <= tol and (best is None or d < abs(best["valid"] - target)):
            best = r
    return best


def category(value, stages):
    if stages is None or value is None:
        return None
    cat = "below_action"
    for name in ("action", "minor", "moderate", "major"):
        if value >= stages[name]:
            cat = name
    return cat


def next_stage(value, stages):
    if stages is None or value is None:
        return None, None
    for name in ("action", "minor", "moderate", "major"):
        if value < stages[name]:
            return name, round(stages[name] - value, 2)
    return None, None  # already past major


def change(series, latest, hrs):
    old = value_near(series, latest["valid"] - timedelta(hours=hrs))
    if old is None:
        return None
    return {"ft": round(latest["value"] - old["value"], 2),
            "records": [old["record_id"], latest["record_id"]]}


def gauge_features(rows, key, cfg, as_of):
    f = {"gauge": key, "name": cfg["name"], "as_of_utc": fmt(as_of), "flags": []}
    stages = cfg["stages"]
    f["flood_stages_ft"] = stages

    # --- latest observation
    obs = obs_series(rows, cfg["obs_gauge"], as_of)
    if not obs:
        f["latest_obs"] = None
        f["flags"].append("no_observations")
    else:
        last = obs[-1]
        age = hours(as_of - last["valid"])
        f["latest_obs"] = {"stage_ft": last["value"], "valid_utc": last["valid_time_utc"],
                           "age_hours": age, "record": last["record_id"]}
        if age > STALE_OBS_HOURS:
            f["flags"].append("stale_observation")

        f["change_6h"] = change(obs, last, 6)
        f["change_24h"] = change(obs, last, 24)
        c6 = f["change_6h"]
        if c6 is None:
            f["trend"] = None
            f["flags"].append("cant_compute_trend")
        else:
            f["trend"] = ("steady" if abs(c6["ft"]) < STEADY_FT
                          else "rising" if c6["ft"] > 0 else "falling")

        # gaps: 15-min readings expected, count how many are missing in last 24h
        # (counted back from the last reading, not as_of, so normal publish lag
        # doesn't show up as a missing reading)
        window = [r for r in obs if r["valid"] > last["valid"] - timedelta(hours=24)]
        expected = 96
        f["obs_missing_last_24h"] = max(0, expected - len(window))
        if f["obs_missing_last_24h"] > 8:  # more than 2 hours worth
            f["flags"].append("observation_gaps")

        f["category_now"] = category(last["value"], stages)
        nxt, dist = next_stage(last["value"], stages)
        f["next_stage"] = {"name": nxt, "ft_away": dist} if nxt else None

    # --- forecast (latest one issued before as_of)
    f["forecast"] = None
    if cfg["forecast_gauge"] is None:
        f["flags"].append("no_forecast_for_gauge")
    else:
        fc = [r for r in rows if r["gauge_id"] == cfg["forecast_gauge"]
              and r["kind"] == "forecast" and r["issued"] <= as_of]
        if not fc:
            f["flags"].append("no_forecast_available")
        else:
            issued = max(r["issued"] for r in fc)
            pts = sorted((r for r in fc if r["issued"] == issued), key=lambda r: r["valid"])
            future = [r for r in pts if r["valid"] >= as_of] or pts
            peak = max(future, key=lambda r: r["value"])
            age = hours(as_of - issued)
            f["forecast"] = {
                "issued_utc": fmt(issued),
                "age_hours": age,
                "horizon_end_utc": pts[-1]["valid_time_utc"],
                "peak_stage_ft": peak["value"],
                "peak_valid_utc": peak["valid_time_utc"],
                "peak_category": category(peak["value"], stages),
                "peak_record": peak["record_id"],
            }
            if age > STALE_FORECAST_HOURS:
                f["flags"].append("stale_forecast")
            # the forecast's first point can be before the latest obs (they overlap)
            # so note that, the briefing should lead with the observation

    # --- NWS vs USGS on the same physical gauge
    f["pair_check"] = None
    if cfg["pair"] and f.get("latest_obs"):
        pair = obs_series(rows, cfg["pair"], as_of)
        if not pair:
            f["flags"].append("pair_missing")
        else:
            plast = pair[-1]
            match = value_near(pair, obs[-1]["valid"], tol=timedelta(minutes=0))
            diff = round(obs[-1]["value"] - match["value"], 2) if match else None
            time_gap = hours(obs[-1]["valid"] - plast["valid"])
            f["pair_check"] = {"pair_gauge": cfg["pair"], "diff_ft": diff,
                               "latest_time_gap_hours": time_gap,
                               "records": [obs[-1]["record_id"]] + ([match["record_id"]] if match else [])}
            if diff is None:
                f["flags"].append("pair_no_matching_time")
            elif abs(diff) > CONFLICT_FT:
                f["flags"].append("nws_usgs_conflict")
            if abs(time_gap) > STALE_OBS_HOURS:
                f["flags"].append("nws_usgs_time_mismatch")

    return f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", help="UTC time like 2026-11-24T18:00:00Z (default: now)")
    args = ap.parse_args()
    as_of = parse(args.as_of) if args.as_of else datetime.now(timezone.utc).replace(microsecond=0)

    rows = load_records()
    out = [gauge_features(rows, k, cfg, as_of) for k, cfg in GAUGES.items()]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"features_{fmt(as_of).replace(':', '-')}.json"
    path.write_text(json.dumps(out, indent=2))

    for g in out:
        obs = g.get("latest_obs") or {}
        print(f"{g['gauge']}: stage {obs.get('stage_ft')} ft, trend {g.get('trend')}, "
              f"category {g.get('category_now')}, flags {g['flags'] or 'none'}")
    print(f"saved {path}")


if __name__ == "__main__":
    main()