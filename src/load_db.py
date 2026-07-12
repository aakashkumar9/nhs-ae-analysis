"""
Load the tidy A&E attendances CSV into a DuckDB database.

Usage:
    python src/load_db.py
    python src/load_db.py --csv data/processed/ae_attendances_tidy.csv --db data/nhs_ae.duckdb
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb

CSV_DEFAULT = Path("data/processed/ae_attendances_tidy.csv")
DB_DEFAULT = Path("data/nhs_ae.duckdb")

CREATE_TABLE_SQL = """
CREATE OR REPLACE TABLE ae_attendances AS
SELECT
    CAST(period AS DATE)               AS period,
    org_code,
    org_name,
    region,
    attendances_type1,
    attendances_type2,
    attendances_type3,
    attendances_type1_booked,
    attendances_type2_booked,
    attendances_type3_booked,
    over_4hrs_type1,
    over_4hrs_type2,
    over_4hrs_type3,
    over_4hrs_type1_booked,
    over_4hrs_type2_booked,
    over_4hrs_type3_booked,
    wait_4_12h_dta,
    wait_12h_plus_dta,
    emergency_admissions_type1,
    emergency_admissions_type2,
    emergency_admissions_type3,
    emergency_admissions_other,
    total_attendances,
    total_over_4_hours,
    in_4_hours,
    pct_in_4_hours,
    total_emergency_admissions,
    source_file
FROM read_csv_auto(?, HEADER=TRUE)
"""


def load(csv_path: Path, db_path: Path) -> int:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    try:
        con.execute(CREATE_TABLE_SQL, [str(csv_path)])
        (row_count,) = con.execute("SELECT COUNT(*) FROM ae_attendances").fetchone()
        return row_count
    finally:
        con.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=CSV_DEFAULT)
    parser.add_argument("--db", type=Path, default=DB_DEFAULT)
    args = parser.parse_args()

    if not args.csv.exists():
        print(f"Tidy CSV not found: {args.csv} (run src/clean.py first)", file=sys.stderr)
        sys.exit(1)

    row_count = load(args.csv, args.db)
    print(f"Loaded {row_count:,} rows into {args.db} (table: ae_attendances)")


if __name__ == "__main__":
    main()
