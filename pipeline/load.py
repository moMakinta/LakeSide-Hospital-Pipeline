"""Load the cleaned data into the landing tables and run the stored procedure."""
import logging

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from pipeline.config import connection_url

log = logging.getLogger(__name__)


def get_engine() -> Engine:
    return create_engine(connection_url(), fast_executemany=True)


def load_landing(engine: Engine, tables: dict[str, pd.DataFrame]) -> None:
    """Truncate each landing table and reload it."""
    with engine.begin() as conn:
        for name, frame in tables.items():
            conn.execute(text(f"TRUNCATE TABLE landing.[{name}]"))
            # pandas NA/NaN/NaT -> None, otherwise they don't go in as NULL
            rows = frame.astype(object).where(frame.notna(), None)
            rows.to_sql(name, conn, schema="landing", if_exists="append", index=False, chunksize=1000)
            log.info("Loaded %s rows into landing.%s", len(rows), name)


def run_core_load(engine: Engine) -> pd.DataFrame:
    # autocommit, because the proc has its own transaction. without this the
    # 'Failed' row in audit.LoadLog got rolled back too
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text("EXEC core.usp_RunLoad"))
        return pd.read_sql(text(
            "SELECT StepName, RowsAffected, LoadStatus FROM audit.LoadLog "
            "WHERE StartTime = (SELECT MAX(StartTime) FROM audit.LoadLog) ORDER BY LoadLogID"), conn)
