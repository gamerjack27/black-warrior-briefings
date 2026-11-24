"""
The baseline: fixed sentences filled in from a features file. No AI.

    python template_briefing.py data/features/features_2026-11-22T18-00-00Z.json

Writes two files to data/briefings/:
  - template_<as_of>.md    the readable briefing
  - template_<as_of>.json  every sentence + the record_ids behind it (for the checker)

Times are shown in Central time; everything underneath stays UTC.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from gauges import STEADY_FT

CENTRAL = ZoneInfo("America/Chicago")
OUT_DIR = Path("data/briefings")

STAGE_ORDER = ["action", "minor", "moderate", "major"]
CATEGORY_TEXT = {
    "below_action": "below action stage, no flooding",
    "action": "at action stage, not yet flooding",
    "minor": "in minor flood",
    "moderate": "in moderate flood",
    "major": "in major flood",
}


def ct(ts):
    """'2026-11-22T17:30:00Z' -> 'Sun 11/22 11:30 AM CST'"""
    dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    local = dt.astimezone(CENTRAL)
    return local.strftime("%a %m/%d %I:%M %p %Z").replace(" 0", " ")


def signed(x):
    return f"+{x:.2f}" if x > 0 else f"{x:.2f}"


def gauge_sentences(g):
    """List of (sentence, [record_ids]) for one gauge."""
    out = []
    obs = g.get("latest_obs")
    stages = g.get("flood_stages_ft")

    if obs is None:
        out.append(("No recent readings are available for this gauge.", []))
    else:
        out.append((f"Latest reading: {obs['stage_ft']:.2f} ft at {ct(obs['valid_utc'])} "
                    f"({obs['age_hours']} hours before this briefing).", [obs["record"]]))

        c6, c24 = g.get("change_6h"), g.get("change_24h")
        if g.get("trend") is None:
            out.append(("There aren't enough recent readings to tell if the river is "
                        "rising or falling.", []))
        else:
            s = f"The river is {g['trend']} ({signed(c6['ft'])} ft over 6 hours"
            recs = list(c6["records"])
            if c24:
                s += f", {signed(c24['ft'])} ft over 24 hours"
                recs += c24["records"]
            out.append((s + ").", recs))

        if stages is None:
            out.append(("This gauge has no official flood stages, so its reading can't be "
                        "compared to flood levels or to readings at other gauges.",
                        [obs["record"]]))
        else:
            cat = g.get("category_now")
            nxt = g.get("next_stage")
            lead = {"below_action": "No flooding", "action": "At action stage, not yet flooding"
                    }.get(cat, f"In {cat} flood")
            s = lead
            if nxt:
                what = "action stage" if nxt["name"] == "action" else f"{nxt['name']} flood stage"
                s += f": {nxt['ft_away']:.2f} ft below {what} ({stages[nxt['name']]} ft)"
            out.append((s + ".", [obs["record"]]))

    # forecast
    fc = g.get("forecast")
    flags = g.get("flags", [])
    if "no_forecast_for_gauge" in flags:
        out.append(("NWS does not issue forecasts for this gauge.", []))
    elif fc is None:
        out.append(("No NWS forecast was available at this time.", []))
    else:
        cur = obs["stage_ft"] if obs else None
        lead = f"The NWS forecast issued {ct(fc['issued_utc'])}"
        # if the "peak" isn't above where the river already is, calling it a
        # crest would be misleading (it can be a forecast that's already behind)
        if cur is not None and fc["peak_stage_ft"] <= cur + STEADY_FT:
            out.append((f"{lead} does not expect the river to rise above its current level "
                        f"through {ct(fc['horizon_end_utc'])}.", [fc["peak_record"]]))
        else:
            cat = CATEGORY_TEXT.get(fc["peak_category"], "") if fc["peak_category"] else ""
            s = (f"{lead} expects a crest of {fc['peak_stage_ft']:.2f} ft around "
                 f"{ct(fc['peak_valid_utc'])}")
            out.append((s + (f" ({cat})." if cat else "."), [fc["peak_record"]]))
        out.append(("NWS forecasts here only account for rain expected about 48 hours "
                    "past the time they're issued.", []))

    # warnings from flags
    if "stale_observation" in flags and obs:
        out.append((f"Warning: the latest reading is {obs['age_hours']} hours old.", [obs["record"]]))
    if "observation_gaps" in flags:
        out.append((f"Warning: {g['obs_missing_last_24h']} readings are missing from the "
                    f"last 24 hours.", []))
    if "stale_forecast" in flags and fc:
        out.append((f"Warning: the forecast is {fc['age_hours']} hours old and may be out "
                    f"of date.", [fc["peak_record"]]))
    pc = g.get("pair_check") or {}
    if "nws_usgs_conflict" in flags:
        out.append((f"Warning: NWS and USGS readings for this gauge disagree by "
                    f"{abs(pc['diff_ft']):.2f} ft. Check both sources.", pc.get("records", [])))
    if "nws_usgs_time_mismatch" in flags:
        out.append((f"Warning: the newest NWS and USGS readings are "
                    f"{abs(pc['latest_time_gap_hours'])} hours apart.", pc.get("records", [])))
    if "pair_missing" in flags or "pair_no_matching_time" in flags:
        out.append(("Note: couldn't cross-check this reading against USGS.", []))

    return out


def build(features):
    as_of = features[0]["as_of_utc"]
    sections = []
    for g in features:
        sections.append({"gauge": g["gauge"], "name": g["name"],
                         "sentences": [{"text": t, "records": r} for t, r in gauge_sentences(g)]})
    return {"as_of_utc": as_of, "method": "template", "sections": sections}


def to_markdown(b):
    lines = [f"# River briefing, as of {ct(b['as_of_utc'])}", ""]
    for s in b["sections"]:
        lines.append(f"## {s['name']}")
        for sent in s["sentences"]:
            cite = f" [{', '.join(sent['records'])}]" if sent["records"] else ""
            lines.append(f"- {sent['text']}{cite}")
        lines.append("")
    lines.append("_Classroom project, not an official warning. "
                 "Official info: https://www.weather.gov/bmx_")
    return "\n".join(lines)


def main():
    if len(sys.argv) != 2:
        print("usage: python template_briefing.py <features json>")
        sys.exit(1)
    features = json.loads(Path(sys.argv[1]).read_text())
    b = build(features)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stem = "template_" + b["as_of_utc"].replace(":", "-")
    (OUT_DIR / f"{stem}.json").write_text(json.dumps(b, indent=2))
    md = to_markdown(b)
    (OUT_DIR / f"{stem}.md").write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()