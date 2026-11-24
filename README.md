# black-warrior-briefings

CS451 final project (Alternative Case 4). We pull river data for the Black Warrior River around Tuscaloosa from NWS and USGS, and turn it into short written briefings two ways:

1. a fixed template (the baseline), and
2. an LLM that has to cite the data records it used (in progress).

Then we check both for accuracy, how they handle stale/missing/conflicting data, and whether readers understand them.

**This is a class project, not an official flood warning.** For real conditions go to https://www.weather.gov/bmx.

## Gauges

| ID | Where | Data |
|----|-------|------|
| TODA1 | Black Warrior River at Oliver Lock and Dam (tailwater) | NWS observations + forecasts, flood stages |
| USGS-02465005 | Same spot as TODA1, published by USGS | USGS observations (used to cross-check NWS) |
| USGS-02465000 | Northport, in the pool above Oliver Dam | USGS observations only, no flood stages |
| TCLA1 | Holt Lock and Dam | NWS, but no forecast has been issued since we started archiving |

Northport reads about 28 ft higher than TODA1 because it's above the dam. Don't compare it to TODA1's flood stages.

## Setup

Needs Python 3.12 or newer.

```
git clone https://github.com/gamerjack27/black-warrior-briefings.git
cd black-warrior-briefings
pip install -r requirements.txt
```

On Windows use `py` instead of `python` / `pip` (e.g. `py -m pip install -r requirements.txt`).

## Making a briefing

Run these in order from the repo folder:

```
python fetch_usgs.py          # USGS readings for the last 30 days
python normalize.py           # all raw files -> data/clean/records.csv
python features.py --as-of 2026-11-22T18:00:00Z
python template_briefing.py data/features/features_2026-11-22T18-00-00Z.json
```

The last command prints the briefing and saves it to `data/briefings/` as `.md` (readable) and `.json` (each sentence with the record IDs it came from).

Leave off `--as-of` to use the current time. Times go in as UTC (ending in `Z`). Briefings show Central time.

`--as-of` replays a past moment using only data that was public then: readings count once they were published, and the forecast is the latest one issued before that time. NWS doesn't keep old forecasts, so replays only have forecasts from Nov 21, 2026 on (when our archiver started).

## Running the tests

```
python -m pytest
```

## The forecast archiver

NWS only serves the current forecast for a gauge, so we save them as they come out. `.github/workflows/archive.yml` runs `archiver.py` every hour on GitHub and commits any new forecast to `data/raw/<gauge>/`. You don't need to run anything for this. To run it by hand: `python archiver.py`, or Actions tab -> Archive NWS forecasts -> Run workflow.

## Files

| File | What it does |
|------|--------------|
| `archiver.py` | Saves each new NWS forecast (raw, gzipped) |
| `fetch_usgs.py` | Pulls USGS 15-minute readings. `--days N` or `--start YYYY-MM-DD --end YYYY-MM-DD` |
| `normalize.py` | Turns all raw files into one table, one row per value |
| `gauges.py` | Flood stages and thresholds (stale forecast = 30 h, conflict = 0.5 ft, etc.) |
| `features.py` | Facts for a briefing at a given time, with flags for problems |
| `template_briefing.py` | The baseline briefing |
| `tests/` | Unit tests |
| `AI_USE.md` | What AI generated for this project and how we checked it |

## Data notes

- Everything is stored in UTC. Flow is stored in cfs (NWS sends kcfs).
- NWS uses -9999 / -999 for missing values. Those become blank, never a number.
- USGS data is provisional and can be revised.
- At low water NWS issues about one TODA1 forecast a day, which is why a forecast only counts as stale after 30 hours.

## Sources

- NWS National Water Prediction Service API: https://api.water.noaa.gov/nwps/v1/docs/
- USGS Water Data API: https://api.waterdata.usgs.gov/

## Team

Jackson Lammons, Alexander Gray, Nolan Thompson (CS451)