"""Dump the reporting views into one Excel workbook.

    python -m reports.build_excel_report
"""
from pathlib import Path

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from pipeline.config import REPORT_DIR

SHEETS = {
    "Account Balances": "SELECT * FROM reporting.vw_AccountBalance ORDER BY AccountNo",
    "Funder Summary": "SELECT * FROM reporting.vw_FunderSummary ORDER BY TotalCharged DESC",
    "Ward Occupancy": "SELECT * FROM reporting.vw_WardOccupancy ORDER BY WardCode, CalendarYear, MonthNumber",
    "Revenue by Category": "SELECT * FROM reporting.vw_RevenueByCategory ORDER BY CalendarYear, MonthNumber, Category",
    "Doctor Activity": "SELECT * FROM reporting.vw_DoctorActivity ORDER BY Admissions DESC",
}
MONEY_WORDS = ("Charged", "Liable", "Paid", "Outstanding", "Amount")
HEADER_FILL = PatternFill("solid", fgColor="2F5597")


def write_report(frames: dict[str, pd.DataFrame], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for sheet, frame in frames.items():
            frame.to_excel(writer, sheet_name=sheet, index=False)
            ws = writer.sheets[sheet]
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions
            for idx, column in enumerate(frame.columns, start=1):
                head = ws.cell(row=1, column=idx)
                head.font = Font(bold=True, color="FFFFFF")
                head.fill = HEADER_FILL
                head.alignment = Alignment(horizontal="center")
                longest = max([len(str(column))] + [len(str(v)) for v in frame[column].head(200)])
                ws.column_dimensions[get_column_letter(idx)].width = min(longest + 4, 45)
                if any(word in column for word in MONEY_WORDS):
                    fmt = '"R" #,##0.00'
                elif column.endswith("Pct"):
                    fmt = '0.0"%"'
                else:
                    continue
                for row in ws.iter_rows(min_row=2, min_col=idx, max_col=idx):
                    row[0].number_format = fmt
    return path


def main() -> None:
    from pipeline.load import get_engine
    with get_engine().connect() as conn:
        frames = {sheet: pd.read_sql(query, conn) for sheet, query in SHEETS.items()}
    print("Report written to", write_report(frames, REPORT_DIR / "hospital_accounts_report.xlsx"))


if __name__ == "__main__":
    main()
