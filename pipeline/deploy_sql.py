"""Runs the SQL scripts in the sql folder against the server in config.ini.

    python -m pipeline.deploy_sql

This does the same thing as opening each file in SSMS and pressing F5, one
after the other. It exists so the database can be built without a person
clicking, which is what the CI pipeline needs.

WARNING: script 03 drops and recreates the core tables, so this is for
setting up a fresh database. Don't run it against one that has data you
want to keep.
"""
import re
import sys
import time

from pipeline.config import ROOT, connection_string

SQL_DIR = ROOT / "sql"

# in this order. 08 is not here because it is analysis queries, not part of the database
SCRIPTS = [
    "01_create_database.sql",
    "02_create_landing_tables.sql",
    "03_create_core_tables.sql",
    "04_populate_dim_date.sql",
    "05_create_load_procedures.sql",
    "06_create_reporting_views.sql",
    "07_create_data_quality_view.sql",
]

# GO is not SQL. It is how SSMS knows where one batch ends and the next starts,
# so SQL Server itself gives an error if it sees one. The file has to be cut
# up on the GO lines and each piece sent on its own.
GO_LINE = re.compile(r"^\s*GO\s*;?\s*$", re.IGNORECASE | re.MULTILINE)


def split_batches(sql_text: str) -> list[str]:
    """Cut a script into batches on the lines that only say GO."""
    return [batch.strip() for batch in GO_LINE.split(sql_text) if batch.strip()]


def connect(attempts: int = 30, wait_seconds: int = 3):
    """Connect to the master database. Keeps trying for a while, because in CI
    the SQL Server container needs some time to start up."""
    import pyodbc      # imported here so the tests can use split_batches without the ODBC driver

    for attempt in range(1, attempts + 1):
        try:
            # autocommit: CREATE DATABASE is not allowed inside a transaction
            return pyodbc.connect(connection_string(database="master"), autocommit=True, timeout=5)
        except pyodbc.Error as error:
            if attempt == attempts:
                raise
            print(f"  server not ready yet (attempt {attempt}/{attempts}): {str(error)[:80]}")
            time.sleep(wait_seconds)


def main() -> int:
    connection = connect()
    cursor = connection.cursor()

    for name in SCRIPTS:
        batches = split_batches((SQL_DIR / name).read_text(encoding="utf-8"))
        print(f"{name}  ({len(batches)} batches)")
        for number, batch in enumerate(batches, start=1):
            try:
                cursor.execute(batch)
                # a batch can have several statements. stepping through the results
                # makes sure an error in a later statement is not missed
                while cursor.nextset():
                    pass
            except Exception as error:
                print(f"  FAILED in batch {number}:\n{batch[:300]}\n\n{error}")
                return 1

    connection.close()
    print("All scripts ran.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
