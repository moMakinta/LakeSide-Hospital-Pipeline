"""Tests for the cleaning rules.  python -m pytest"""
import pandas as pd

from pipeline import transform


def _refs():
    patients = pd.DataFrame({"PatientID": ["P000001"]})
    wards = pd.DataFrame({"WardCode": ["W-GEN"]})
    doctors = pd.DataFrame({"DoctorID": ["DR001"]})
    funders = pd.DataFrame({"FunderCode": ["BAO-CMP", "PRIV"]})
    return patients, wards, doctors, funders


def _admission(**changes):
    row = {"AdmissionID": "ADM1", "PatientID": "P000001", "WardCode": "W-GEN", "DoctorID": "DR001",
           "FunderCode": "BAO-CMP", "AuthorisationNo": "AUTH1", "AdmitDateTime": "2025-03-01 10:00",
           "DischargeDateTime": "2025-03-04 11:00", "AdmissionType": "Emergency",
           "DiagnosisGroup": "Pneumonia", "SourceFile": "t.csv"}
    row.update(changes)
    return row


def _clean_admissions(rows):
    return transform.clean_admissions(pd.DataFrame(rows), *_refs())


def test_dates_in_all_the_source_formats():
    parsed = transform.parse_dates(pd.Series(
        ["2025-01-31 14:30", "31/01/2025 14:30", "2025-01-31", "31-Jan-2025", "unknown"], dtype="string"))
    assert parsed[0] == parsed[1] == pd.Timestamp("2025-01-31 14:30")
    assert parsed[2] == parsed[3] == pd.Timestamp("2025-01-31")
    assert pd.isna(parsed[4])


def test_good_admission_is_kept_and_tidied():
    clean, rejects, _ = _clean_admissions([_admission(WardCode=" w-gen", AdmissionType="DAYCASE",
                                                      DischargeDateTime="04/03/2025 11:00")])
    assert len(clean) == 1 and len(rejects) == 0
    row = clean.iloc[0]
    assert row.WardCode == "W-GEN" and row.AdmissionType == "Day case"
    assert row.DischargeDateTime == pd.Timestamp("2025-03-04 11:00")


def test_bad_admissions_are_rejected_with_a_reason():
    clean, rejects, _ = _clean_admissions([
        _admission(AdmissionID="A", DischargeDateTime="2025-02-27 09:00"),
        _admission(AdmissionID="B", WardCode="W-XXX"),
        _admission(AdmissionID="C", AdmitDateTime="2025-02-30 10:00"),
        _admission(AdmissionID="D"), _admission(AdmissionID="D"),
    ])
    assert list(clean["AdmissionID"]) == ["D"]
    assert sorted(rejects["RejectReason"]) == ["Discharge before admission", "Duplicate admission",
                                               "Invalid or missing admit date", "Unknown ward"]


def test_no_discharge_means_still_admitted_and_blank_funder_means_private():
    clean, rejects, stats = _clean_admissions([_admission(DischargeDateTime="", FunderCode="")])
    assert len(rejects) == 0
    assert pd.isna(clean.iloc[0].DischargeDateTime) and clean.iloc[0].FunderCode == "PRIV"
    assert stats == {"blank_funder_set_to_private": 1, "still_admitted": 1}


def test_charges_are_checked_against_the_admission():
    admissions, _, _ = _clean_admissions([_admission()])
    tariffs = pd.DataFrame({"TariffCode": ["PHA-ANL"], "EffectiveFrom": [pd.Timestamp("2025-01-01")]})

    def charge(cid, **changes):
        row = {"ChargeID": cid, "AdmissionID": "ADM1", "ServiceDate": "2025-03-02", "TariffCode": "PHA-ANL",
               "Quantity": "2", "CapturedBy": "nurse01", "SourceFile": "t.csv"}
        row.update(changes)
        return row

    clean, rejects = transform.clean_charges(pd.DataFrame([
        charge("C1", TariffCode=" pha-anl "),
        charge("C2", ServiceDate="2025-03-20"),
        charge("C3", Quantity="0"),
        charge("C4", AdmissionID="ADM999"),
        charge("C5", TariffCode="XXX-000"),
    ]), admissions, tariffs)
    assert list(clean["ChargeID"]) == ["C1"] and clean.iloc[0].Quantity == 2.0
    assert sorted(rejects["RejectReason"]) == ["Admission not found", "Quantity must be more than zero",
                                               "Service date outside the admission", "Unknown tariff code"]


def test_payments():
    admissions, _, _ = _clean_admissions([_admission()])
    raw = pd.DataFrame({"PaymentID": ["P1", "P2", "P3"], "AdmissionID": ["ADM1"] * 3,
                        "PaymentDate": ["2025-04-01", "01/04/2025", "2025-04-01"],
                        "PayerType": ["FUNDER", "patient", "Patient"], "Method": ["Remittance", "Card", "EFT"],
                        "Amount": ["R 12,500.00", "800", "-50"], "SourceFile": ["t.csv"] * 3})
    clean, rejects = transform.clean_payments(raw, admissions)
    assert list(clean["Amount"]) == [12500.0, 800.0] and list(clean["PayerType"]) == ["Funder", "Patient"]
    assert list(rejects["RejectReason"]) == ["Amount must be more than zero"]
