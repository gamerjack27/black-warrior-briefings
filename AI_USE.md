# AI use log

Our proposal said we'd keep track of what AI generated, how we checked it, and what got fixed. This is that list. Tool for everything so far: Claude.

"AI's own tests" means tests Claude ran on sample data before handing code over. "Our check" means what we ran or looked at ourselves on real data.

## archiver.py + .github/workflows/archive.yml (Nov 21)

- **What it made:** script that saves each new NWS forecast for TODA1 and TCLA1, and an hourly GitHub Actions workflow that runs it.
- **AI's own tests:** fake API returning our saved TODA1 response. Checked new forecast saved, repeat skipped, one gauge failing doesn't stop the other, saved file is byte-identical to the response.
- **Our check:** ran it locally twice, then ran the workflow by hand on GitHub (passed). By Nov 24 it had saved forecasts for Nov 22, 23 and 24 on its own.
- **Corrections:** first version saved a TCLA1 file named `0001-01-01T00-00-00Z`. NWS sends that year-1 date when a gauge has no forecast, and the code treated it as a real issue time. Fixed to skip it. We found this on our first local run.

## fetch_usgs.py + normalize.py (Nov 24)

- **What it made:** USGS fetcher (last N days or a date range) and the script that turns all raw NWS/USGS files into one table, `data/clean/records.csv`.
- **AI's own tests:** our real TODA1 file plus an edited second snapshot and a made-up USGS sample (the USGS API wasn't reachable from Claude's sandbox). Checked IDs are unique, kcfs converts to cfs, -9999 becomes empty, repeated observations are kept once.
- **Our check:** ran on real data (15,100 records). Compared stage at one time across sources: TODA1 (NWS) and USGS-02465005 both read 95.72 ft, which confirms they're the same gauge.
- **Corrections:** the AI's tests caught empty placeholder rows keeping the raw `kcfs` / `ft^3/s` unit instead of `cfs`. Fixed before we got it.

## features.py + gauges.py (Nov 24)

- **What it made:** builds the facts for a briefing at any "as of" time (latest reading, trend, flood category, forecast, NWS/USGS cross-check, flags). Flood stages and thresholds live in gauges.py.
- **AI's own tests:** replayed five times from our TODA1 data, including an injected 1.2 ft NWS/USGS disagreement. Each case raised the expected flags.
- **Our check:** replayed Nov 22 18:00Z and confirmed it used the forecast issued that morning (14:29Z), not a later one.
- **Corrections:**
  - AI's tests caught normal ~1 hr publishing delay being counted as missing readings.
  - Looking at our Nov 22 replay, the latest reading was 18:00Z with age 0, but NWS didn't publish it until ~18:54Z, so the replay was using data nobody had yet. Fixed to only use readings once published. This changed that replay's trend from "rising" to "steady". After the fix, a Nov 21 19:45Z replay picked 95.62 ft at 18:30Z, which matches what the live NWS gauge page showed us at that time.

## template_briefing.py + tests/test_template.py (Nov 24)

- **What it made:** the template baseline (fixed sentences filled from a features file) and 7 unit tests.
- **AI's own tests:** the 7 tests (numbers only come from the features, falling forecast isn't called a "crest", flags show as warnings, Northport never gets a flood category, numeric sentences have record IDs, Central time is right).
- **Our check:** `py -m pytest` (7 passed) and read through the Nov 22 briefing against its features file.
- **Corrections:** reworded two clumsy sentences ("That is below action stage, no flooding, 26.38 ft below action stage") and removed a wrong reason given for why Northport can't be compared to other gauges.