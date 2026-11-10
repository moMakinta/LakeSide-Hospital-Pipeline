"""Read the raw files. Everything comes in as text, types get fixed in transform.py."""
from pathlib import Path

import pandas as pd


def _read_monthly(raw_dir: Path, pattern: str) -> pd.DataFrame:
    files = sorted(raw_dir.glob(pattern))
    if not files:
        raise FileNotFoundError(f"no files matching {pattern} in {raw_dir}")
    frames = []
    for path in files:
        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
        frame["SourceFile"] = path.name
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def extract_all(raw_dir: Path) -> dict[str, pd.DataFrame]:
    return {
        "wards": pd.read_excel(raw_dir / "wards.xlsx", dtype=str),
        "doctors": pd.read_excel(raw_dir / "doctors.xlsx", dtype=str),
        "funders": pd.read_excel(raw_dir / "funders.xlsx", dtype=str),
        "tariffs": pd.read_excel(raw_dir / "tariffs.xlsx", dtype=str),
        "patients": pd.read_csv(raw_dir / "patients.csv", dtype=str, keep_default_na=False),
        "admissions": _read_monthly(raw_dir, "admissions_*.csv"),
        "charges": _read_monthly(raw_dir, "charges_*.csv"),
        "payments": _read_monthly(raw_dir, "payments_*.csv"),
    }
