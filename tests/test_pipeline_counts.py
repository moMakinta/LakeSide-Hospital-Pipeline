"""Runs the whole cleaning step on the real files in data/raw and checks the row counts.

The other tests check one rule at a time on a few made-up rows. This one is a
safety net: if a change to transform.py makes the pipeline keep or reject a
different number of rows, this fails and I have to look at why. If the change
was on purpose, update the numbers here (and in the README).
"""
from pipeline import extract
from pipeline.config import RAW_DIR
from pipeline.run_pipeline import clean_all

EXPECTED = {            # table: (kept, rejected)
    "Tariff": (42, 0),
    "Ward": (7, 0),
    "Doctor": (22, 0),
    "Funder": (6, 0),
    "Patient": (3200, 40),
    "Admission": (4608, 83),
    "Charge": (68526, 2390),
    "Payment": (6602, 140),
}


def test_row_counts_have_not_changed():
    clean, rejects, stats = clean_all(extract.extract_all(RAW_DIR))
    actual = {name: (len(clean[name]), len(rejects[name])) for name in clean}
    assert actual == EXPECTED
    assert stats["still_admitted"] == 34


def test_no_row_is_lost():
    """Every row that was read must end up either kept or rejected."""
    raw = extract.extract_all(RAW_DIR)
    clean, rejects, _ = clean_all(raw)
    for source, table in [("admissions", "Admission"), ("charges", "Charge"), ("payments", "Payment")]:
        assert len(raw[source]) == len(clean[table]) + len(rejects[table]), table
