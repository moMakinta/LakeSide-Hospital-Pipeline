"""Cleaning and validation.

Each clean_* function returns (clean_rows, rejected_rows). Rejects keep the
original values and get a RejectReason column. Working columns that start
with an underscore are temporary and get dropped at the end.
"""
from __future__ import annotations

import pandas as pd

DATE_FORMATS = ("%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M", "%Y-%m-%d", "%d/%m/%Y",
                "%d-%b-%Y", "%Y-%m-%d %H:%M:%S")


def _strip(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in df.columns:
        df[col] = df[col].astype("string").str.strip()
    return df.replace("", pd.NA)


def parse_dates(values: pd.Series) -> pd.Series:
    """Try each known format in turn. Anything that doesn't parse comes back as NaT."""
    out = pd.Series(pd.NaT, index=values.index, dtype="datetime64[ns]")
    for fmt in DATE_FORMATS:
        todo = out.isna() & values.notna()
        if not todo.any():
            break
        out[todo] = pd.to_datetime(values[todo], format=fmt, errors="coerce")
    return out


def parse_money(values: pd.Series) -> pd.Series:
    """'R 1,299.00' -> 1299.0"""
    cleaned = values.astype("string").str.replace(r"[Rr\s,]", "", regex=True)
    return pd.to_numeric(cleaned, errors="coerce").astype("float64")


def _split(df, bad, reason, rejects):
    """Move the rows flagged in `bad` to the reject list, return the rest."""
    bad = bad.reindex(df.index).fillna(True).astype(bool)
    if bad.any():
        rejected = df[bad].copy()
        rejected["RejectReason"] = reason
        rejects.append(rejected)
    return df[~bad].copy()


def _combine(rejects, columns):
    if not rejects:
        return pd.DataFrame(columns=[*columns, "RejectReason"])
    out = pd.concat(rejects, ignore_index=True)
    return out[[c for c in out.columns if not c.startswith("_")]]


def _upper(df, cols):
    for col in cols:
        df[col] = df[col].str.upper()


# ---- reference data

def clean_tariffs(raw):
    df, rejects = _strip(raw), []
    _upper(df, ["TariffCode", "FunderCovered"])
    df["Category"] = df["Category"].str.title()
    df["_rate"] = parse_money(df["Rate"])
    df["_from"] = parse_dates(df["EffectiveFrom"])
    df = _split(df, df["TariffCode"].isna(), "Missing tariff code", rejects)
    df = _split(df, df["_rate"].isna() | (df["_rate"] <= 0), "Invalid rate", rejects)
    df = _split(df, df["_from"].isna(), "Invalid effective date", rejects)
    df = _split(df, df.duplicated(["TariffCode", "_from"], keep="last"), "Duplicate tariff for the same date", rejects)
    out = pd.DataFrame({
        "TariffCode": df["TariffCode"], "Description": df["Description"], "Category": df["Category"],
        "UnitOfMeasure": df["Unit"], "Rate": df["_rate"].round(2),
        "IsFunderCovered": (df["FunderCovered"] != "N").astype(int),   # anything except N counts as covered
        "EffectiveFrom": df["_from"],
    })
    return out.reset_index(drop=True), _combine(rejects, raw.columns)


def clean_wards(raw, tariffs):
    df, rejects = _strip(raw), []
    _upper(df, ["WardCode", "AccommodationTariff"])
    df["_beds"] = pd.to_numeric(df["BedCount"], errors="coerce")
    df = _split(df, df["WardCode"].isna(), "Missing ward code", rejects)
    df = _split(df, df["_beds"].isna() | (df["_beds"] <= 0), "Invalid bed count", rejects)
    df = _split(df, ~df["AccommodationTariff"].isin(tariffs["TariffCode"]), "Accommodation tariff not in tariff list", rejects)
    df = _split(df, df.duplicated("WardCode", keep="last"), "Duplicate ward", rejects)
    out = pd.DataFrame({"WardCode": df["WardCode"], "WardName": df["WardName"], "WardType": df["WardType"],
                        "BedCount": df["_beds"].astype(int), "AccommodationTariffCode": df["AccommodationTariff"]})
    return out.reset_index(drop=True), _combine(rejects, raw.columns)


def clean_doctors(raw):
    df, rejects = _strip(raw), []
    _upper(df, ["DoctorID"])
    df = _split(df, df["DoctorID"].isna(), "Missing doctor id", rejects)
    df = _split(df, df.duplicated("DoctorID", keep="last"), "Duplicate doctor", rejects)
    return df[["DoctorID", "DoctorName", "Speciality"]].reset_index(drop=True), _combine(rejects, raw.columns)


def clean_funders(raw):
    df, rejects = _strip(raw), []
    _upper(df, ["FunderCode"])
    df["_cover"] = pd.to_numeric(df["CoverPct"].str.replace("%", "", regex=False), errors="coerce")
    df = _split(df, df["FunderCode"].isna(), "Missing funder code", rejects)
    df = _split(df, df["_cover"].isna() | (df["_cover"] < 0) | (df["_cover"] > 100), "Cover % must be 0-100", rejects)
    df = _split(df, df.duplicated("FunderCode", keep="last"), "Duplicate funder", rejects)
    out = pd.DataFrame({"FunderCode": df["FunderCode"], "FunderName": df["FunderName"],
                        "FunderType": df["FunderType"], "CoverPct": df["_cover"].round(2)})
    return out.reset_index(drop=True), _combine(rejects, raw.columns)


def clean_patients(raw):
    df, rejects = _strip(raw), []
    _upper(df, ["PatientID"])
    df["FullName"] = df["FullName"].str.title()
    df["Gender"] = df["Gender"].str.upper().str[:1].where(lambda s: s.isin(["M", "F"]), "U")
    df["Gender"] = df["Gender"].fillna("U")
    df = _split(df, df["PatientID"].isna(), "Missing patient id", rejects)
    df = _split(df, df.duplicated("PatientID", keep="last"), "Duplicate patient", rejects)
    df["DateOfBirth"] = parse_dates(df["DateOfBirth"])     # a missing date of birth is allowed
    return df[["PatientID", "FullName", "DateOfBirth", "Gender", "City"]].reset_index(drop=True), _combine(rejects, raw.columns)


# ---- transactions

ADMISSION_TYPES = {"emergency": "Emergency", "elective": "Elective", "day case": "Day case", "daycase": "Day case"}


def clean_admissions(raw, patients, wards, doctors, funders):
    df, rejects, stats = _strip(raw), [], {}
    _upper(df, ["AdmissionID", "PatientID", "WardCode", "DoctorID", "FunderCode"])
    df = _split(df, df["AdmissionID"].isna(), "Missing admission id", rejects)
    df = _split(df, df.duplicated("AdmissionID", keep="first"), "Duplicate admission", rejects)

    df["_admit"] = parse_dates(df["AdmitDateTime"])
    df["_disch"] = parse_dates(df["DischargeDateTime"])
    df = _split(df, df["_admit"].isna(), "Invalid or missing admit date", rejects)
    # no discharge date is fine, the patient is still in hospital
    df = _split(df, df["DischargeDateTime"].notna() & df["_disch"].isna(), "Invalid discharge date", rejects)
    df = _split(df, df["_disch"] < df["_admit"], "Discharge before admission", rejects)

    df = _split(df, ~df["PatientID"].isin(patients["PatientID"]), "Unknown patient", rejects)
    df = _split(df, ~df["WardCode"].isin(wards["WardCode"]), "Unknown ward", rejects)
    df = _split(df, ~df["DoctorID"].isin(doctors["DoctorID"]), "Unknown doctor", rejects)

    # blank funder = the patient is paying themselves
    blank = df["FunderCode"].isna()
    stats["blank_funder_set_to_private"] = int(blank.sum())
    df.loc[blank, "FunderCode"] = "PRIV"
    df = _split(df, ~df["FunderCode"].isin(funders["FunderCode"]), "Unknown funder", rejects)

    kind = df["AdmissionType"].str.lower().str.replace(r"[\s_-]+", " ", regex=True)
    df["AdmissionType"] = kind.map(ADMISSION_TYPES).fillna("Unknown")
    df["AdmitDateTime"], df["DischargeDateTime"] = df["_admit"], df["_disch"]
    stats["still_admitted"] = int(df["DischargeDateTime"].isna().sum())

    cols = ["AdmissionID", "PatientID", "WardCode", "DoctorID", "FunderCode", "AuthorisationNo",
            "AdmitDateTime", "DischargeDateTime", "AdmissionType", "DiagnosisGroup", "SourceFile"]
    return df[cols].reset_index(drop=True), _combine(rejects, raw.columns), stats


def clean_charges(raw, admissions, tariffs):
    """Charge lines only carry a tariff code and a quantity. The amount is worked out in SQL."""
    df, rejects = _strip(raw), []
    _upper(df, ["ChargeID", "AdmissionID", "TariffCode"])
    df = _split(df, df["ChargeID"].isna(), "Missing charge id", rejects)
    df = _split(df, df.duplicated("ChargeID", keep="first"), "Duplicate charge", rejects)

    df["_qty"] = pd.to_numeric(df["Quantity"], errors="coerce").astype("float64")
    df = _split(df, df["_qty"].isna() | (df["_qty"] <= 0), "Quantity must be more than zero", rejects)
    df = _split(df, ~df["TariffCode"].isin(tariffs["TariffCode"]), "Unknown tariff code", rejects)
    df = _split(df, ~df["AdmissionID"].isin(admissions["AdmissionID"]), "Admission not found", rejects)

    df["_date"] = parse_dates(df["ServiceDate"])
    df = _split(df, df["_date"].isna(), "Invalid or missing service date", rejects)

    adm = admissions.drop_duplicates("AdmissionID").set_index("AdmissionID")
    df["_admit"] = df["AdmissionID"].map(adm["AdmitDateTime"]).dt.normalize()
    df["_disch"] = df["AdmissionID"].map(adm["DischargeDateTime"]).dt.normalize()
    outside = (df["_date"] < df["_admit"]) | (df["_date"] > df["_disch"])
    df = _split(df, outside, "Service date outside the admission", rejects)

    first_rate = tariffs.groupby("TariffCode")["EffectiveFrom"].min()
    df = _split(df, df["_date"] < df["TariffCode"].map(first_rate), "No tariff rate for that date", rejects)

    out = pd.DataFrame({"ChargeID": df["ChargeID"], "AdmissionID": df["AdmissionID"], "ServiceDate": df["_date"],
                        "TariffCode": df["TariffCode"], "Quantity": df["_qty"].round(2),
                        "CapturedBy": df["CapturedBy"], "SourceFile": df["SourceFile"]})
    return out.reset_index(drop=True), _combine(rejects, raw.columns)


def clean_payments(raw, admissions):
    df, rejects = _strip(raw), []
    _upper(df, ["PaymentID", "AdmissionID"])
    df["PayerType"] = df["PayerType"].str.title()
    df = _split(df, df["PaymentID"].isna(), "Missing payment id", rejects)
    df = _split(df, df.duplicated("PaymentID", keep="first"), "Duplicate payment", rejects)
    df["_amount"] = parse_money(df["Amount"])
    # TODO: negative amounts could be refunds. rejecting them for now
    df = _split(df, df["_amount"].isna() | (df["_amount"] <= 0), "Amount must be more than zero", rejects)
    df = _split(df, ~df["PayerType"].isin(["Funder", "Patient"]), "Payer type must be Funder or Patient", rejects)
    df = _split(df, ~df["AdmissionID"].isin(admissions["AdmissionID"]), "Admission not found", rejects)
    df["_date"] = parse_dates(df["PaymentDate"])
    df = _split(df, df["_date"].isna(), "Invalid or missing payment date", rejects)
    out = pd.DataFrame({"PaymentID": df["PaymentID"], "AdmissionID": df["AdmissionID"], "PaymentDate": df["_date"],
                        "PayerType": df["PayerType"], "PaymentMethod": df["Method"],
                        "Amount": df["_amount"].round(2), "SourceFile": df["SourceFile"]})
    return out.reset_index(drop=True), _combine(rejects, raw.columns)
