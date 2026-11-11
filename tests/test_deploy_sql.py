"""Tests for the part of the deploy script that cuts a SQL file into batches."""
from pipeline.deploy_sql import SCRIPTS, SQL_DIR, split_batches


def test_splits_on_go_lines():
    script = "USE LakesideHospital;\nGO\n\nCREATE TABLE t (id int);\ngo\nSELECT 1;\n  GO  \n"
    assert split_batches(script) == ["USE LakesideHospital;", "CREATE TABLE t (id int);", "SELECT 1;"]


def test_go_inside_a_word_is_not_a_split():
    # GOVERNMENT and CATEGORY both have "GO" in them
    script = "SELECT Category FROM t WHERE Name = 'GOVERNMENT';\nGO"
    assert split_batches(script) == ["SELECT Category FROM t WHERE Name = 'GOVERNMENT';"]


def test_every_deploy_script_exists_and_has_something_in_it():
    for name in SCRIPTS:
        assert split_batches((SQL_DIR / name).read_text(encoding="utf-8")), name
