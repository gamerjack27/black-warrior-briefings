"""
Tests for the template baseline. Run with:  python -m pytest

Main idea: every number the template writes has to come from the features
it was given, and every flag has to turn into a warning the reader can see.
"""

import copy
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from template_briefing import build  # noqa: E402

BASE = {
    "gauge": "TODA1",
    "name": "Black Warrior River at Oliver Lock and Dam (tailwater)",
    "as_of_utc": "2026-11-22T18:00:00Z",
    "flags": [],
    "flood_stages_ft": {"action": 122, "minor": 129, "moderate": 138, "major": 146},
    "latest_obs": {"stage_ft": 95.47, "valid_utc": "2026-11-22T17:30:00Z", "age_hours": 0.5,
                   "record": "TODA1-obs-stage-20261122T1730Z"},
    "change_6h": {"ft": 0.01, "records": ["A", "B"]},
    "change_24h": {"ft": -0.16, "records": ["C", "D"]},
    "trend": "steady",
    "obs_missing_last_24h": 0,
    "category_now": "below_action",
    "next_stage": {"name": "action", "ft_away": 26.53},
    "forecast": {"issued_utc": "2026-11-22T14:29:00Z", "age_hours": 3.5,
                 "horizon_end_utc": "2026-11-27T12:00:00Z", "peak_stage_ft": 95.2,
                 "peak_valid_utc": "2026-11-22T18:00:00Z", "peak_category": "below_action",
                 "peak_record": "TODA1-fcst-stage-20261122T1800Z-iss20261122T1429Z"},
    "pair_check": {"pair_gauge": "USGS-02465005", "diff_ft": 0.0, "latest_time_gap_hours": 0.0,
                   "records": ["E", "F"]},
}

NORTHPORT = {
    "gauge": "USGS-02465000", "name": "Northport", "as_of_utc": "2026-11-22T18:00:00Z",
    "flags": ["no_forecast_for_gauge"], "flood_stages_ft": None,
    "latest_obs": {"stage_ft": 123.5, "valid_utc": "2026-11-22T17:30:00Z", "age_hours": 0.5,
                   "record": "N1"},
    "change_6h": {"ft": 0.35, "records": ["N2", "N1"]}, "change_24h": None, "trend": "rising",
    "obs_missing_last_24h": 0, "category_now": None, "next_stage": None, "forecast": None,
    "pair_check": None,
}


def text_of(feats):
    b = build(feats)
    return " ".join(s["text"] for sec in b["sections"] for s in sec["sentences"])


def numbers(s):
    # pulls out things like 95.47, +0.01, 26.53 (skips times like 11:30)
    return {float(x) for x in re.findall(r"(?<![\d:])[-+]?\d+\.\d+(?![\d:])", s)}


def test_numbers_come_from_features():
    t = text_of([BASE])
    allowed = {95.47, 0.01, -0.16, 26.53, 95.2, 0.5, 3.5}
    assert numbers(t) <= allowed, numbers(t) - allowed


def test_falling_forecast_not_called_a_crest():
    # forecast peak (95.2) is below the current reading (95.47)
    t = text_of([BASE])
    assert "crest" not in t
    assert "does not expect the river to rise" in t


def test_rising_forecast_is_a_crest():
    g = copy.deepcopy(BASE)
    g["forecast"]["peak_stage_ft"] = 124.0
    g["forecast"]["peak_category"] = "action"
    t = text_of([g])
    assert "crest of 124.00 ft" in t and "at action stage" in t


def test_flags_become_warnings():
    g = copy.deepcopy(BASE)
    g["flags"] = ["stale_forecast", "stale_observation", "nws_usgs_conflict"]
    g["forecast"]["age_hours"] = 41.0
    g["pair_check"]["diff_ft"] = -1.2
    t = text_of([g])
    assert "forecast is 41.0 hours old" in t
    assert "latest reading is 0.5 hours old" in t
    assert "disagree by 1.20 ft" in t


def test_northport_never_gets_a_flood_category():
    t = text_of([NORTHPORT])
    assert "no official flood stages" in t
    assert "flood stage" not in t.replace("no official flood stages", "")
    assert "does not issue forecasts" in t


def test_every_number_sentence_has_a_citation():
    b = build([BASE, NORTHPORT])
    for sec in b["sections"]:
        for s in sec["sentences"]:
            if numbers(s["text"]) and "48 hours" not in s["text"]:
                assert s["records"], s["text"]


def test_central_time_display():
    t = text_of([BASE])
    # 17:30Z on Nov 22 is 11:30 AM CST
    assert "11:30 AM CST" in t