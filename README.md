# NHS A&E Performance: Who's Missing the Four-Hour Target, and Why

**[Live dashboard →](https://nhs-ae-analysis-aakash.streamlit.app/)**

A data analysis project examining Accident & Emergency (A&E) performance across NHS trusts in England, using publicly available NHS England data. The goal is to move from raw, inconsistent monthly files to a clear set of findings a decision-maker could act on.

## The question

NHS England sets a standard that 95% of A&E patients should be admitted, transferred, or discharged within four hours. Most trusts have not met this for years. This project asks:

- Which trusts consistently miss the four-hour target, and is their performance trending down?
- Is there a clear seasonal pattern, and how bad is winter pressure?
- Do high-volume trusts always perform worse, or are some handling large volumes well?
- Are there regional disparities worth flagging to commissioners?

## Headline findings

Across April 2024 to June 2026, national four-hour performance never got close to the 95% standard. It moved in a fairly narrow band, from 71.1% in December 2024 up to 77.1% in March 2026, and never broke 78%. So this isn't a story about a system in freefall. It's a story about a system that's settled into a new, much lower normal and stayed there.

Winter is worse, but not dramatically so. November through January are consistently the weakest calendar months (72-73% on a volume-weighted basis), while July and August are the strongest (76%). That's roughly a 3-4 point gap, real but smaller than the "winter crisis" framing in most headlines would suggest. December 2024 specifically stands out as the single worst month in the whole dataset.

Bigger trusts do tend to perform worse. Attendance volume and four-hour performance are moderately negatively correlated (r ≈ -0.51 across trusts in the latest month), and four of the five worst-performing trusts have well below the median attendance count. But volume isn't destiny: Northumbria Healthcare NHS Foundation Trust handled over 25,000 attendances in the latest month at 91.2% in 4 hours, easily the best major trust in the dataset, while East Cheshire NHS Trust and The Shrewsbury and Telford Hospital NHS Trust both sat at 51.6% with far lower volumes. Whatever's driving the worst performers, it isn't simply "too many patients."

Regionally, London and the South East consistently outperform (76-77% averaged across the full period), while the North West, South West and Midlands lag (72-73%). That's a persistent 4-5 point gap, not a one-off, which is the kind of pattern worth flagging to commissioners rather than writing off as noise.

## What this project demonstrates

- **Real data wrangling.** The raw monthly files are inconsistent: column names drift, header rows move, trust codes change. The cleaning step handles this rather than relying on a pre-cleaned dataset.
- **SQL, not just pandas.** Cleaned data is loaded into DuckDB and the core aggregations are written as SQL, kept in `/sql`.
- **Analysis as narrative.** The EDA notebook is structured around the four questions above, each answered with a chart and a written takeaway.
- **A shareable output.** A Streamlit dashboard (`dashboard/app.py`, [live here](https://nhs-ae-analysis-aakash.streamlit.app/)) with region and date filters, a trust-level drill-down, and a leaderboard table. Regional comparison is a ranked bar chart and small-multiples trend grid rather than a geographic map - the ONS boundary files needed for a real choropleth weren't reachable from the environment this was built in.
- **Honest framing.** A methodology note covers what the data can and can't tell you.

## Data source

NHS England — A&E Attendances and Emergency Admissions (monthly).
https://www.england.nhs.uk/statistics/statistical-work-areas/ae-waiting-times-and-activity/

Download the monthly CSV files into `data/raw/`. The files are public and free - go to the year page for each financial year (e.g. "Monthly A&E Attendances and Emergency Admissions 2025-26") and grab the "Monthly A&E [Month] [Year] (CSV, ...)" link for each month, not the XLS or the aggregate national time series. Filenames don't matter; `clean.py` sorts by the `period` value inside each file, not the filename. See `data/raw/README.md` for more detail.

This analysis uses 27 months, April 2024 through June 2026 (January-March 2024 aren't included).

## Project structure

```
nhs-ae-analysis/
├── data/
│   ├── raw/          # downloaded monthly files (gitignored, not committed)
│   └── processed/    # cleaned, combined dataset
├── notebooks/
│   └── 01_exploratory_analysis.ipynb
├── src/
│   ├── clean.py      # reads raw files, standardises, outputs one tidy CSV
│   └── load_db.py    # loads processed data into DuckDB
├── sql/
│   └── analysis.sql  # the core aggregation queries
├── dashboard/
│   └── app.py        # Streamlit dashboard
├── outputs/          # exported charts and figures
├── requirements.txt      # what the dashboard needs (Streamlit Cloud reads this)
└── requirements-dev.txt  # + Jupyter/Excel/test deps for local dev
```

## How to run

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

# 1. Clean and combine the raw monthly files
python src/clean.py

# 2. Load the tidy dataset into DuckDB
python src/load_db.py

# 3. Open the analysis notebook
jupyter notebook notebooks/01_exploratory_analysis.ipynb

# 4. Or launch the dashboard
streamlit run dashboard/app.py
```

`requirements.txt` alone is enough to just run the dashboard (and is what Streamlit Community Cloud installs from) - `requirements-dev.txt` adds Jupyter, Excel support, and test dependencies for local data-wrangling work.

## Methodology and limitations

**Total attendances and the four-hour percentage are derived, not published directly.** The raw NHS England files report six attendance sub-categories (Type 1, Type 2, and Other/UTC, each split into walk-in and pre-booked) and six matching "over 4 hours" sub-categories, but no single "total" column. `src/clean.py` sums these to get `total_attendances` and `in_4_hours`. This is all-types performance (Type 1 major A&E blended with Type 2 and Type 3/UTC), which reads more favourably than Type-1-only performance would, since smaller urgent treatment centres tend to hit close to 100%. If you want the Type-1-only story, `attendances_type1` and `over_4hrs_type1` are both in the tidy dataset separately.

**"Waited 4-12h / 12h+" is a different metric and isn't part of the percentage above.** That column measures the wait from decision-to-admit to actual admission (trolley/corridor waits), not the four-hour A&E clock. Conflating the two would double-count and misrepresent both.

**Every raw file carries an England-wide "TOTAL" row.** `clean.py` filters it out by matching `org_code == "TOTAL"` (case-insensitive, since the capitalisation isn't consistent across files). Miss this and you'd be aggregating a phantom mega-trust alongside the real ones.

**Regional grouping comes from the `Parent Org` column already in the raw data**, not a separate lookup - it's NHS England's own seven-region breakdown (London, Midlands, North East and Yorkshire, North West, South East, South West, East of England).

**A missed four-hour target isn't the same as poor clinical care.** The standard measures time-to-decision (admit, transfer, or discharge), not outcome. A trust under sustained pressure can miss the target while still delivering good care; this dataset can't distinguish that from a trust with genuine operational problems.

**Trust mergers and code changes aren't reconciled.** If a trust's `org_code` changed over the period (mergers, reconfigurations), its time series in this dataset would appear discontinuous rather than joined up. I haven't cross-checked `org_code` continuity against NHS's organisational change records, so treat any trust-level series with a sudden gap or jump with that in mind.

**January-March 2024 aren't in this dataset**, purely because that's where the downloaded range starts. The 27 months covered (April 2024-June 2026) still span two full winters, which is enough for the seasonality comparison to hold up.

## Known issues

**pandas and pyarrow are pinned in `requirements.txt`** (`pandas<3.0`, `pyarrow>=22,<25`). Unpinned, the dashboard resolves the newest pandas 3.0.x / pyarrow 25.x, which segfault (a native crash, not a Python exception - no traceback, the whole process just dies) inside Streamlit's rerun machinery as soon as a widget triggers a second script run, e.g. moving the date-range slider. Bisected with `streamlit.testing.v1.AppTest` down to `df["period"].between(...)` on a `@st.cache_data`-cached DataFrame plus `st.dataframe()` on the leaderboard table.

The pyarrow floor matters as much as the ceiling: Streamlit Community Cloud currently runs **Python 3.14**, and pyarrow only started shipping Python 3.14 wheels from **22.0.0** onward - anything older forces a from-source build (CMake + Arrow C++) that fails outright in Streamlit Cloud's build environment (a completely different failure mode from the runtime segfault, surfacing as "installer returned a non-zero exit code" during dependency processing rather than a crash after launch). So the safe, buildable, non-crashing range is specifically `pyarrow>=22,<25` - verified via `AppTest` across many widget combinations and a real browser session. If you ever change either pin, re-run that kind of check before trusting the deploy.

**`requirements.txt` is deliberately lean (just what the dashboard imports).** It used to also list Jupyter, matplotlib, seaborn, openpyxl and xlrd, none of which `dashboard/app.py` needs - Jupyter in particular pulls in a large, unrelated dependency tree (IPython's console deps: `rich`, `pygments`, `markdown-it-py`, etc.) that caused a dependency-resolution failure on a Streamlit Cloud rebuild. Those packages now live in `requirements-dev.txt` for local notebook/data-wrangling work instead.

## Tech stack

Python (pandas), DuckDB / SQL, Jupyter, and Power BI / Streamlit for the dashboard.
