"""
Clean and standardise NHS England monthly A&E attendance files.

NHS England has changed the column headers in these files more times than
you'd expect over the years (spacing, capitalisation, wording, and even the
odd rename of the metric itself). Rather than special-case every file, this
script maps every column name it's seen to a canonical name via
COLUMN_ALIASES, and flags anything it doesn't recognise instead of silently
dropping it.

The raw files don't publish "total attendances" or "in 4 hours" directly -
they report six attendance sub-categories (Type 1 / Type 2 / Other, each
split into walk-in and pre-booked) and six matching "over 4 hours"
sub-categories. Totals and the four-hour percentage are derived from those.
The "waited 4-12h / 12h+ from decision-to-admit" columns are a distinct
metric (post-admission-decision trolley wait) and are kept separate rather
than folded into the four-hour attendance standard.

Every file also carries a "TOTAL" row at the bottom (England-wide sum across
all orgs for that month) - this is filtered out, since left in it would be
processed as a fake trust and badly distort every aggregation.

Some source files (mostly the older .xls ones) also carry a title/notes row
above the real header row, so we sniff for the header instead of assuming
it's row 0.

Usage:
    python src/clean.py
    python src/clean.py --raw-dir data/raw --out data/processed/ae_attendances_tidy.csv
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

import pandas as pd

RAW_DIR_DEFAULT = Path("data/raw")
OUT_PATH_DEFAULT = Path("data/processed/ae_attendances_tidy.csv")

# Canonical column -> every raw spelling we've seen for it.
# Add new spellings here as new files turn up new variants; clean.py will
# print anything it can't map so you know what to add.
COLUMN_ALIASES: dict[str, list[str]] = {
    "period": [
        "period",
    ],
    "org_code": [
        "org code",
    ],
    "org_name": [
        "org name",
    ],
    "region": [
        "parent org",
    ],
    "attendances_type1": [
        "a&e attendances type 1",
    ],
    "attendances_type2": [
        "a&e attendances type 2",
    ],
    "attendances_type3": [
        "a&e attendances other a&e department",
    ],
    "attendances_type1_booked": [
        "a&e attendances booked appointments type 1",
    ],
    "attendances_type2_booked": [
        "a&e attendances booked appointments type 2",
    ],
    "attendances_type3_booked": [
        "a&e attendances booked appointments other department",
    ],
    "over_4hrs_type1": [
        "attendances over 4hrs type 1",
    ],
    "over_4hrs_type2": [
        "attendances over 4hrs type 2",
    ],
    "over_4hrs_type3": [
        "attendances over 4hrs other department",
    ],
    "over_4hrs_type1_booked": [
        "attendances over 4hrs booked appointments type 1",
    ],
    "over_4hrs_type2_booked": [
        "attendances over 4hrs booked appointments type 2",
    ],
    "over_4hrs_type3_booked": [
        "attendances over 4hrs booked appointments other department",
    ],
    "wait_4_12h_dta": [
        "patients who have waited 4-12 hs from dta to admission",
    ],
    "wait_12h_plus_dta": [
        "patients who have waited 12+ hrs from dta to admission",
    ],
    "emergency_admissions_type1": [
        "emergency admissions via a&e - type 1",
    ],
    "emergency_admissions_type2": [
        "emergency admissions via a&e - type 2",
    ],
    "emergency_admissions_type3": [
        "emergency admissions via a&e - other a&e department",
    ],
    "emergency_admissions_other": [
        "other emergency admissions",
    ],
}

# Reverse lookup: normalised raw name -> canonical name.
_ALIAS_LOOKUP = {
    alias.strip().lower(): canonical
    for canonical, aliases in COLUMN_ALIASES.items()
    for alias in aliases
}

REQUIRED_COLUMNS = ["period", "org_code", "org_name"]

# The six attendance sub-categories that sum to total attendances, and the
# six matching "over 4 hours" sub-categories. Both walk-in and pre-booked
# appointments count towards the published four-hour standard.
_ATTENDANCE_COLUMNS = [
    "attendances_type1",
    "attendances_type2",
    "attendances_type3",
    "attendances_type1_booked",
    "attendances_type2_booked",
    "attendances_type3_booked",
]
_OVER_4HRS_COLUMNS = [
    "over_4hrs_type1",
    "over_4hrs_type2",
    "over_4hrs_type3",
    "over_4hrs_type1_booked",
    "over_4hrs_type2_booked",
    "over_4hrs_type3_booked",
]
_EMERGENCY_ADMISSION_COLUMNS = [
    "emergency_admissions_type1",
    "emergency_admissions_type2",
    "emergency_admissions_type3",
    "emergency_admissions_other",
]

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}
_PERIOD_RE = re.compile(r"([a-z]+)-(\d{4})")


def _normalise(col: str) -> str:
    return " ".join(str(col).strip().lower().split())


def _parse_period(raw_period: str) -> str | None:
    """
    Raw period values look like 'MSitAE-SEPTEMBER-2024'. Returns the first
    of that month as an ISO date string, or None if it doesn't parse.
    """
    match = _PERIOD_RE.search(str(raw_period).lower())
    if not match:
        return None
    month_name, year = match.groups()
    month = _MONTHS.get(month_name)
    if month is None:
        return None
    return f"{year}-{month:02d}-01"


def _find_header_row(raw_path: Path, max_scan: int = 10) -> int:
    """
    Some raw files have a title/notes row (or several blank rows) before the
    real header, and that row is often ragged (fewer fields than the data
    rows below it), which trips up pandas' C parser if we try to preview
    with pd.read_csv directly. Read raw lines with csv.reader instead, which
    tolerates uneven row lengths, and pick the first row that contains at
    least two column names we recognise.
    """
    with raw_path.open(newline="") as f:
        reader = csv.reader(f)
        for row_idx, row in enumerate(reader):
            if row_idx >= max_scan:
                break
            row_values = [_normalise(v) for v in row if v]
            hits = sum(1 for v in row_values if v in _ALIAS_LOOKUP)
            if hits >= 2:
                return row_idx
    return 0


def _map_columns(columns: list[str], source_file: str, unmapped: set[str]) -> dict[str, str]:
    mapping = {}
    for col in columns:
        canonical = _ALIAS_LOOKUP.get(_normalise(col))
        if canonical:
            mapping[col] = canonical
        else:
            unmapped.add(f"{source_file}: {col!r}")
    return mapping


def clean_file(raw_path: Path, unmapped: set[str]) -> pd.DataFrame | None:
    header_row = _find_header_row(raw_path)
    df = pd.read_csv(raw_path, header=header_row, dtype=str)
    df = df.dropna(axis=1, how="all")

    mapping = _map_columns(list(df.columns), raw_path.name, unmapped)
    if not mapping:
        return None

    df = df.rename(columns=mapping)
    df = df[[c for c in df.columns if c in COLUMN_ALIASES]]
    df = df.loc[:, ~df.columns.duplicated()]

    missing_required = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_required:
        return None

    # Drop the England-wide "TOTAL" row NHS England appends to every file -
    # otherwise it's processed as a fake trust and wrecks every aggregation.
    df = df[df["org_code"].astype(str).str.strip().str.upper() != "TOTAL"]

    df["period"] = df["period"].apply(_parse_period)
    df = df.dropna(subset=["period"])

    df["org_code"] = df["org_code"].astype(str).str.strip()
    df["org_name"] = df["org_name"].astype(str).str.strip()
    if "region" in df.columns:
        df["region"] = df["region"].astype(str).str.strip()

    # Reindex to the full canonical schema so every output file has the same
    # columns regardless of which metrics that particular month's file
    # reported - missing ones become null rather than absent.
    df = df.reindex(columns=list(COLUMN_ALIASES.keys()))

    numeric_cols = [c for c in df.columns if c not in ("period", "org_code", "org_name", "region")]
    for col in numeric_cols:
        df[col] = pd.to_numeric(
            df[col].astype(str).str.replace(",", "", regex=False).str.strip(),
            errors="coerce",
        )

    df["total_attendances"] = df[_ATTENDANCE_COLUMNS].sum(axis=1, min_count=1)
    df["total_over_4_hours"] = df[_OVER_4HRS_COLUMNS].sum(axis=1, min_count=1)
    df["in_4_hours"] = df["total_attendances"] - df["total_over_4_hours"]
    df["pct_in_4_hours"] = 100.0 * df["in_4_hours"] / df["total_attendances"]
    df["total_emergency_admissions"] = df[_EMERGENCY_ADMISSION_COLUMNS].sum(axis=1, min_count=1)

    df = df.dropna(subset=["org_code", "total_attendances"])
    df["source_file"] = raw_path.name
    return df


def clean_directory(raw_dir: Path) -> tuple[pd.DataFrame, list[Path], set[str]]:
    raw_files = sorted(raw_dir.glob("*.csv"))
    frames = []
    skipped = []
    unmapped: set[str] = set()

    for raw_path in raw_files:
        cleaned = clean_file(raw_path, unmapped)
        if cleaned is None or cleaned.empty:
            skipped.append(raw_path)
            continue
        frames.append(cleaned)

    if not frames:
        return pd.DataFrame(), skipped, unmapped

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values(["period", "org_code"]).reset_index(drop=True)
    return combined, skipped, unmapped


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR_DEFAULT)
    parser.add_argument("--out", type=Path, default=OUT_PATH_DEFAULT)
    args = parser.parse_args()

    if not args.raw_dir.exists():
        print(f"Raw data directory not found: {args.raw_dir}", file=sys.stderr)
        sys.exit(1)

    combined, skipped, unmapped = clean_directory(args.raw_dir)

    if combined.empty:
        print("No files could be cleaned - nothing to write.", file=sys.stderr)
    else:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        combined.to_csv(args.out, index=False)
        n_months = combined["period"].nunique()
        n_orgs = combined["org_code"].nunique()
        print(
            f"Wrote {len(combined):,} rows ({n_months} months x up to {n_orgs} orgs) "
            f"from {combined['source_file'].nunique()} files to {args.out}"
        )

    if skipped:
        print(f"\nSkipped {len(skipped)} file(s) (missing required columns after mapping):")
        for path in skipped:
            print(f"  - {path.name}")

    if unmapped:
        print(f"\n{len(unmapped)} column(s) could not be mapped to a canonical name:")
        for entry in sorted(unmapped):
            print(f"  - {entry}")
        print("\nAdd these to COLUMN_ALIASES in src/clean.py if they should map to an existing field.")


if __name__ == "__main__":
    main()
