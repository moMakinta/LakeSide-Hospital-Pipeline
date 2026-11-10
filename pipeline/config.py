"""Folder paths and the SQL Server connection string."""
from configparser import ConfigParser
from pathlib import Path
from urllib.parse import quote_plus

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
CLEAN_DIR = ROOT / "data" / "clean"
REJECT_DIR = ROOT / "data" / "rejects"
REPORT_DIR = ROOT / "reports" / "output"
CONFIG_FILE = ROOT / "config.ini"


def connection_url() -> str:
    if not CONFIG_FILE.exists():
        raise FileNotFoundError("config.ini not found - copy config.example.ini to config.ini first")
    parser = ConfigParser()
    parser.read(CONFIG_FILE)
    cfg = parser["sqlserver"]
    parts = [
        f"DRIVER={{{cfg.get('driver', 'ODBC Driver 17 for SQL Server')}}}",
        f"SERVER={cfg.get('server', 'localhost')}",
        f"DATABASE={cfg.get('database', 'LakesideHospital')}",
        "TrustServerCertificate=yes",
    ]
    if cfg.getboolean("trusted_connection", fallback=True):
        parts.append("Trusted_Connection=yes")
    else:
        parts += [f"UID={cfg.get('username')}", f"PWD={cfg.get('password')}"]
    return "mssql+pyodbc:///?odbc_connect=" + quote_plus(";".join(parts))
