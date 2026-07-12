"""
End-to-end test for src/clean.py against synthetic raw files that mirror
the real NHS England format: six attendance sub-columns and six matching
"over 4 hours" sub-columns (no direct "total" column), a Parent Org region
field, a period like "MSitAE-MAY-2024", and a "TOTAL" footer row that must
be filtered out rather than treated as a real org.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from clean import clean_directory  # noqa: E402

HEADER = (
    "Period,Org Code,Parent Org,Org name,"
    "A&E attendances Type 1,A&E attendances Type 2,A&E attendances Other A&E Department,"
    "A&E attendances Booked Appointments Type 1,A&E attendances Booked Appointments Type 2,"
    "A&E attendances Booked Appointments Other Department,"
    "Attendances over 4hrs Type 1,Attendances over 4hrs Type 2,Attendances over 4hrs Other Department,"
    "Attendances over 4hrs Booked Appointments Type 1,Attendances over 4hrs Booked Appointments Type 2,"
    "Attendances over 4hrs Booked Appointments Other Department,"
    "Patients who have waited 4-12 hs from DTA to admission,Patients who have waited 12+ hrs from DTA to admission,"
    "Emergency admissions via A&E - Type 1,Emergency admissions via A&E - Type 2,"
    "Emergency admissions via A&E - Other A&E department,Other emergency admissions"
)


def _write(path: Path, text: str) -> None:
    path.write_text(text)


def test_clean_directory_derives_totals_and_drops_total_row(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()

    # Trust A: 1000 Type 1 (100 over 4hrs), no other categories.
    # Trust B: 800 Type 1 (50 over 4hrs) + 200 Type 2 (50 over 4hrs).
    # Plus the England-wide TOTAL row every real file carries.
    _write(
        raw_dir / "2024-05.csv",
        HEADER + "\n"
        "MSitAE-MAY-2024,RXK,NHS ENGLAND MIDLANDS ,Sample Trust A,1000,0,0,0,0,0,100,0,0,0,0,0,0,0,10,0,0,0\n"
        "MSitAE-MAY-2024,RXL,NHS ENGLAND LONDON,Sample Trust B,800,200,0,0,0,0,50,50,0,0,0,0,0,0,8,2,0,0\n"
        "TOTAL,TOTAL,Total,Total,1800,200,0,0,0,0,150,50,0,0,0,0,0,0,18,2,0,0\n",
    )

    combined, skipped, unmapped = clean_directory(raw_dir)

    assert skipped == []
    assert unmapped == set()
    assert len(combined) == 2
    assert set(combined["org_code"]) == {"RXK", "RXL"}
    assert (combined["period"] == "2024-05-01").all()

    trust_a = combined[combined["org_code"] == "RXK"].iloc[0]
    assert trust_a["total_attendances"] == 1000
    assert trust_a["total_over_4_hours"] == 100
    assert trust_a["in_4_hours"] == 900
    assert trust_a["pct_in_4_hours"] == 90.0
    assert trust_a["region"] == "NHS ENGLAND MIDLANDS"

    trust_b = combined[combined["org_code"] == "RXL"].iloc[0]
    assert trust_b["total_attendances"] == 1000
    assert trust_b["in_4_hours"] == 900


def test_clean_directory_reports_unmapped_columns(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()

    _write(
        raw_dir / "2024-06.csv",
        HEADER + ",Mystery Column\n"
        "MSitAE-JUNE-2024,RXK,NHS ENGLAND MIDLANDS ,Sample Trust A,1000,0,0,0,0,0,100,0,0,0,0,0,0,0,10,0,0,0,foo\n"
        "TOTAL,TOTAL,Total,Total,1000,0,0,0,0,0,100,0,0,0,0,0,0,0,10,0,0,0,\n",
    )

    combined, skipped, unmapped = clean_directory(raw_dir)

    assert skipped == []
    assert len(combined) == 1
    assert any("Mystery Column" in entry for entry in unmapped)


def test_clean_directory_skips_files_missing_required_columns(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()

    _write(
        raw_dir / "2024-07.csv",
        "Period,Org Code,Org name\nMSitAE-JULY-2024,RXK,Sample Trust A\n",
    )

    combined, skipped, unmapped = clean_directory(raw_dir)

    assert combined.empty
    assert len(skipped) == 1
    assert skipped[0].name == "2024-07.csv"
