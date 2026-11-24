"""
Gauge settings used by features.py.

Flood stages come from the NWPS gauge info
(https://api.water.noaa.gov/nwps/v1/gauges/TODA1, pulled 2026-11-21).
They only apply to the gauge they belong to. Northport sits in the pool above
Oliver Dam and reads ~28 ft higher than the tailwater, so comparing it to
TODA1's stages would show a fake flood.
"""

GAUGES = {
    "TODA1": {
        "name": "Black Warrior River at Oliver Lock and Dam (tailwater)",
        "obs_gauge": "TODA1",          # where its observations live in records.csv
        "forecast_gauge": "TODA1",
        "pair": "USGS-02465005",       # same physical gauge, published by USGS
        "stages": {"action": 122, "minor": 129, "moderate": 138, "major": 146},
    },
    "USGS-02465000": {
        "name": "Black Warrior River at Northport (Oliver pool, above the dam)",
        "obs_gauge": "USGS-02465000",
        "forecast_gauge": None,        # NWS doesn't forecast this one
        "pair": None,
        "stages": None,                # no official flood stages
    },
}

# thresholds, tweak here instead of in the code
STALE_FORECAST_HOURS = 30   # NWS issues ~1/day at low water, so 24 would flag normal ones
STALE_OBS_HOURS = 2
CONFLICT_FT = 0.5           # NWS vs USGS difference on the same gauge
STEADY_FT = 0.1             # 6h change smaller than this counts as steady