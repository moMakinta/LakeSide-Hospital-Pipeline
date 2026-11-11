"""Reads the data quality checks from the database and fails if any of them failed.

    python -m pipeline.check_quality

"Fails" means the program ends with exit code 1. That is how a CI pipeline knows
a step went wrong: exit code 0 = fine, anything else = stop and mark the run red.
"""
import sys

import pandas as pd

from pipeline.load import get_engine


def main() -> int:
    with get_engine().connect() as conn:
        checks = pd.read_sql("SELECT CheckName, FailedRows, Result FROM reporting.vw_DataQualityChecks", conn)

    print(checks.to_string(index=False))
    failed = checks[checks["Result"] != "PASS"]
    if len(failed):
        print(f"\n{len(failed)} check(s) failed.")
        return 1
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
