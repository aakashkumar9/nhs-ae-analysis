# Raw data

This folder is gitignored — the monthly files aren't committed. Download them
yourself from NHS England and drop them in here as CSV.

## Where to get the files

NHS England — A&E Attendances and Emergency Admissions (monthly statistics):
https://www.england.nhs.uk/statistics/statistical-work-areas/ae-waiting-times-and-activity/

Each month has its own page with a "Trust Level" CSV/XLS export (there's
usually also a "Provider Level" or "CCG Level" file — you want the trust
level one, since that's the org_code / org_name grain the pipeline expects).
Aim for at least 2 years of consecutive months so seasonality actually shows
up in the analysis.

If a month is only published as `.xls`/`.xlsx`, convert it to CSV before
dropping it in here (`src/clean.py` currently reads `*.csv` only) — Excel's
"Save As > CSV UTF-8" is fine, or `pandas.read_excel(...).to_csv(...)`.

## What `clean.py` expects

- One file per month, any filename (the pipeline sorts by the `period`
  column inside the file, not the filename).
- A header row somewhere in the first 10 rows — `clean.py` scans for it, so
  a title row or notes above the header is fine.
- Column names that map to something in `COLUMN_ALIASES` (in `src/clean.py`).
  NHS England has renamed these columns several times over the years. Run
  `python src/clean.py` after adding new files — anything it can't map gets
  printed at the end so you can extend the aliases.

## After downloading

```bash
python src/clean.py
```

Check the output for skipped files or unmapped columns before moving on to
`src/load_db.py`.
