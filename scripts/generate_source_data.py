"""Makes the fake hospital source files in data/raw.

All patients, doctors and funders are invented. The files are messy on
purpose so the cleaning step has something to do.

    python scripts/generate_source_data.py
"""
import csv
import random
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
rng = random.Random(7)
START, CUTOFF = date(2025, 1, 1), date(2025, 12, 31)
INCREASE_DATE = date(2025, 7, 1)

# code, name, type, beds, accommodation tariff
WARDS = [
    ("W-GEN", "General Medical", "General", 20, "ACC-GEN"),
    ("W-SUR", "Surgical", "Surgical", 18, "ACC-SUR"),
    ("W-MAT", "Maternity", "Maternity", 10, "ACC-MAT"),
    ("W-PAE", "Paediatric", "Paediatric", 8, "ACC-PAE"),
    ("W-HC", "High Care", "High Care", 5, "ACC-HC"),
    ("W-ICU", "Intensive Care", "ICU", 6, "ACC-ICU"),
    ("W-DAY", "Day Ward", "Day", 8, "ACC-DAY"),
]

# code, description, category, unit, rate, covered by funder (Y/N)
TARIFFS = [
    ("ACC-GEN", "General ward - per day", "Accommodation", "Day", 3450, "Y"),
    ("ACC-SUR", "Surgical ward - per day", "Accommodation", "Day", 3650, "Y"),
    ("ACC-MAT", "Maternity ward - per day", "Accommodation", "Day", 3900, "Y"),
    ("ACC-PAE", "Paediatric ward - per day", "Accommodation", "Day", 3550, "Y"),
    ("ACC-HC", "High care - per day", "Accommodation", "Day", 9800, "Y"),
    ("ACC-ICU", "Intensive care - per day", "Accommodation", "Day", 18500, "Y"),
    ("ACC-DAY", "Day ward - per visit", "Accommodation", "Day", 1950, "Y"),
    ("EXT-PVT", "Private room upgrade - per day", "Accommodation", "Day", 1200, "N"),
    ("THR-MIN", "Major theatre - per minute", "Theatre", "Minute", 185, "Y"),
    ("THR-MNR", "Minor theatre - per minute", "Theatre", "Minute", 120, "Y"),
    ("PRC-APP", "Appendectomy", "Procedure", "Each", 14500, "Y"),
    ("PRC-CSC", "Caesarean section", "Procedure", "Each", 16800, "Y"),
    ("PRC-NVD", "Normal delivery", "Procedure", "Each", 9800, "Y"),
    ("PRC-HIP", "Hip replacement", "Procedure", "Each", 48000, "Y"),
    ("PRC-KNE", "Knee arthroscopy", "Procedure", "Each", 17500, "Y"),
    ("PRC-CHO", "Cholecystectomy", "Procedure", "Each", 19800, "Y"),
    ("PRC-TON", "Tonsillectomy", "Procedure", "Each", 8900, "Y"),
    ("PRC-END", "Endoscopy", "Procedure", "Each", 5200, "Y"),
    ("PRC-CAT", "Cataract surgery", "Procedure", "Each", 12500, "Y"),
    ("PRC-HRN", "Hernia repair", "Procedure", "Each", 13200, "Y"),
    ("PHA-IVF", "IV fluids 1L", "Pharmacy", "Unit", 185, "Y"),
    ("PHA-ABX", "IV antibiotics - dose", "Pharmacy", "Unit", 320, "Y"),
    ("PHA-ANL", "Analgesia - dose", "Pharmacy", "Unit", 95, "Y"),
    ("PHA-TTO", "Take-home medication pack", "Pharmacy", "Unit", 450, "N"),
    ("CON-DRS", "Dressing pack", "Consumables", "Unit", 140, "Y"),
    ("CON-IVS", "IV administration set", "Consumables", "Unit", 210, "Y"),
    ("CON-THP", "Theatre pack", "Consumables", "Unit", 2850, "Y"),
    ("CON-OXY", "Oxygen - per hour", "Consumables", "Hour", 65, "Y"),
    ("CNS-DOC", "Doctor ward visit", "Clinical", "Each", 780, "Y"),
    ("RAD-XR", "X-ray", "Clinical", "Each", 890, "Y"),
    ("RAD-CT", "CT scan", "Clinical", "Each", 6400, "Y"),
    ("LAB-FBC", "Blood panel", "Clinical", "Each", 420, "Y"),
]
INCREASES = {"Accommodation": 1.06, "Theatre": 1.05}   # from 1 July

# code, name, type, cover %, weight
FUNDERS = [
    ("BAO-CMP", "Baobab Medical Scheme - Comprehensive", "Medical Aid", 100, 22),
    ("BAO-HSP", "Baobab Medical Scheme - Hospital Plan", "Medical Aid", 90, 18),
    ("PRO-CLS", "Protea Health - Classic", "Medical Aid", 100, 16),
    ("PRO-ESS", "Protea Health - Essential", "Medical Aid", 80, 14),
    ("IND-STD", "Indlovu Care - Standard", "Medical Aid", 85, 12),
    ("PRIV", "Private (self-pay)", "Private", 0, 18),
]

SPECIALITIES = {"Physician": ["W-GEN", "W-HC", "W-ICU"], "Surgeon": ["W-SUR", "W-DAY", "W-ICU"],
                "Obstetrician": ["W-MAT"], "Paediatrician": ["W-PAE"],
                "Orthopaedic Surgeon": ["W-SUR", "W-DAY"], "Ophthalmologist": ["W-DAY"]}
DOCTOR_COUNTS = {"Physician": 6, "Surgeon": 5, "Obstetrician": 3, "Paediatrician": 3,
                 "Orthopaedic Surgeon": 3, "Ophthalmologist": 2}

# diagnosis group, ward, admission type, (min, max nights), procedure, theatre minutes, weight
CASES = [
    ("Appendicitis", "W-SUR", "Emergency", (2, 4), "PRC-APP", (45, 90), 5),
    ("Hip replacement", "W-SUR", "Elective", (4, 7), "PRC-HIP", (90, 150), 3),
    ("Gallstones", "W-SUR", "Elective", (1, 3), "PRC-CHO", (60, 110), 4),
    ("Hernia", "W-SUR", "Elective", (1, 2), "PRC-HRN", (40, 80), 4),
    ("Knee injury", "W-DAY", "Day case", (0, 0), "PRC-KNE", (30, 60), 5),
    ("Cataract", "W-DAY", "Day case", (0, 0), "PRC-CAT", (20, 40), 6),
    ("Endoscopy", "W-DAY", "Day case", (0, 0), "PRC-END", (15, 30), 8),
    ("Tonsillitis", "W-PAE", "Elective", (1, 2), "PRC-TON", (25, 45), 4),
    ("Childbirth - caesarean", "W-MAT", "Elective", (3, 4), "PRC-CSC", (40, 70), 6),
    ("Childbirth - normal", "W-MAT", "Emergency", (2, 3), "PRC-NVD", None, 7),
    ("Pneumonia", "W-GEN", "Emergency", (3, 8), None, None, 9),
    ("Gastroenteritis", "W-GEN", "Emergency", (1, 3), None, None, 8),
    ("Diabetes complications", "W-GEN", "Emergency", (2, 6), None, None, 6),
    ("Cardiac chest pain", "W-HC", "Emergency", (2, 5), None, None, 5),
    ("Stroke", "W-ICU", "Emergency", (4, 12), None, None, 2),
    ("Major trauma", "W-ICU", "Emergency", (3, 10), None, None, 2),
    ("Bronchiolitis", "W-PAE", "Emergency", (2, 5), None, None, 5),
]

FIRST_M = ["Thabo", "Sipho", "Johan", "Kagiso", "Pieter", "Bongani", "Dumisani", "Farouk",
           "Hendrik", "Jabu", "Liam", "Mpho", "Oliver", "Riaan", "Sibusiso", "Vusi", "Yusuf"]
FIRST_F = ["Lerato", "Naledi", "Anika", "Zanele", "Ayesha", "Chloe", "Emma", "Gugu", "Imaan",
           "Karabo", "Nomsa", "Palesa", "Tumi", "Unathi", "Wanda", "Zinhle", "Megan"]
LAST = ["Nkosi", "Dlamini", "Botha", "Naidoo", "Van der Merwe", "Mokoena", "Khumalo", "Pillay",
        "Smith", "Mahlangu", "Jacobs", "Ndlovu", "Pretorius", "Molefe", "Williams", "Zulu",
        "Govender", "Sithole", "Du Plessis", "Mabaso", "Adams", "Tshabalala"]
CITIES = ["Johannesburg", "Pretoria", "Midrand", "Centurion", "Roodepoort", "Soweto", "Benoni", "Krugersdorp"]


def tariff_rows():
    rows = []
    for code, desc, cat, unit, rate, covered in TARIFFS:
        rows.append({"TariffCode": code, "Description": desc, "Category": cat, "Unit": unit,
                     "Rate": float(rate), "FunderCovered": covered, "EffectiveFrom": START})
        if cat in INCREASES:
            rows.append({"TariffCode": code, "Description": desc, "Category": cat, "Unit": unit,
                         "Rate": round(rate * INCREASES[cat], 2), "FunderCovered": covered,
                         "EffectiveFrom": INCREASE_DATE})
    return rows


def messy_date(d, with_time=False):
    r = rng.random()
    if with_time:
        return d.strftime("%Y-%m-%d %H:%M") if r < 0.8 else d.strftime("%d/%m/%Y %H:%M")
    if r < 0.75:
        return d.strftime("%Y-%m-%d")
    return d.strftime("%d/%m/%Y") if r < 0.95 else d.strftime("%d-%b-%Y")


def build_patients(n=3200):
    rows = []
    for i in range(1, n + 1):
        child = rng.random() < 0.18
        female = rng.random() < 0.55
        year = rng.randint(2012, 2024) if child else rng.randint(1940, 2006)
        dob = date(year, rng.randint(1, 12), rng.randint(1, 28))
        rows.append({"PatientID": f"P{i:06d}",
                     "FullName": f"{rng.choice(FIRST_F if female else FIRST_M)} {rng.choice(LAST)}",
                     "DateOfBirth": dob, "Gender": "F" if female else "M", "City": rng.choice(CITIES)})
    return rows


def write_csv(name, rows):
    with open(RAW_DIR / name, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    tariffs = tariff_rows()
    info = {t[0]: t for t in TARIFFS}

    def rate_on(code, d):
        return max((t for t in tariffs if t["TariffCode"] == code and t["EffectiveFrom"] <= d),
                   key=lambda t: t["EffectiveFrom"])["Rate"]

    patients = build_patients()
    kids = [p for p in patients if p["DateOfBirth"].year >= 2012]
    adults = [p for p in patients if p["DateOfBirth"].year < 2012]
    mothers = [p for p in adults if p["Gender"] == "F" and 1983 <= p["DateOfBirth"].year <= 2006]

    doctors, n = [], 0
    for spec, count in DOCTOR_COUNTS.items():
        for _ in range(count):
            n += 1
            doctors.append({"DoctorID": f"DR{n:03d}",
                            "DoctorName": f"Dr {rng.choice(FIRST_M + FIRST_F)} {rng.choice(LAST)}",
                            "Speciality": spec})
    ward_doctors = {w[0]: [d["DoctorID"] for d in doctors if w[0] in SPECIALITIES[d["Speciality"]]] for w in WARDS}
    beds = {w[0]: w[3] for w in WARDS}
    ward_tariff = {w[0]: w[4] for w in WARDS}
    cover = {f[0]: f[3] for f in FUNDERS}

    occupancy = defaultdict(int)
    admissions, charges, payments = defaultdict(list), defaultdict(list), []
    adm_no = chg_no = pay_no = 0

    day = START
    while day <= CUTOFF:
        for _ in range(rng.randint(10, 16)):
            diag, ward, adm_type, los_range, proc, minutes, _w = rng.choices(CASES, [c[6] for c in CASES])[0]
            if diag == "Gastroenteritis" and rng.random() < 0.3:
                ward = "W-PAE"
            if diag == "Childbirth - caesarean" and rng.random() < 0.4:
                adm_type = "Emergency"
            los = rng.randint(*los_range)
            discharge_day = day + timedelta(days=los)
            is_open = discharge_day > CUTOFF
            last_day = CUTOFF if is_open else discharge_day
            if is_open:
                nights = [day + timedelta(days=i) for i in range((CUTOFF - day).days + 1)]
            else:
                nights = [day + timedelta(days=i) for i in range(max(los, 1))]
            if any(occupancy[(ward, d)] >= beds[ward] for d in nights):
                continue      # ward is full, patient goes elsewhere
            for d in nights:
                occupancy[(ward, d)] += 1

            adm_no += 1
            adm_id = f"ADM25{adm_no:05d}"
            pool = mothers if ward == "W-MAT" else kids if ward == "W-PAE" else adults
            patient = rng.choice(pool)
            funder = rng.choices(FUNDERS, [f[4] for f in FUNDERS])[0][0]
            if ward == "W-DAY":
                admit_dt = datetime(day.year, day.month, day.day, rng.randint(6, 10), rng.choice([0, 15, 30, 45]))
                discharge_dt = admit_dt + timedelta(hours=rng.randint(4, 8))
            else:
                admit_dt = datetime(day.year, day.month, day.day, rng.randint(0, 23), rng.randint(0, 59))
                discharge_dt = datetime(discharge_day.year, discharge_day.month, discharge_day.day,
                                        rng.randint(9, 16), rng.randint(0, 59))
                if discharge_dt <= admit_dt:
                    discharge_dt = admit_dt + timedelta(hours=3)

            # ---- what was done during the stay
            stay_days = [day + timedelta(days=i) for i in range((last_day - day).days + 1)]
            lines = []
            if ward != "W-DAY" or rng.random() < 0.3:
                lines.append((day, "LAB-FBC", 1))
            if rng.random() < 0.6:
                lines.append((day, "CON-IVS", 1))
            if proc:
                proc_day = stay_days[1] if len(stay_days) > 2 and adm_type == "Elective" and rng.random() < 0.3 else day
                lines.append((proc_day, proc, 1))
                if minutes:
                    lines.append((proc_day, "THR-MNR" if ward == "W-DAY" else "THR-MIN", rng.randint(*minutes)))
                    lines.append((proc_day, "CON-THP", 1))
            for d in stay_days:
                if ward != "W-DAY":
                    lines.append((d, "CNS-DOC", 1))
                if rng.random() < 0.7:
                    lines.append((d, "PHA-ANL", rng.randint(1, 4)))
                if rng.random() < 0.35:
                    lines.append((d, "PHA-IVF", rng.randint(1, 3)))
                if rng.random() < 0.3:
                    lines.append((d, "PHA-ABX", rng.randint(1, 3)))
                if rng.random() < 0.4:
                    lines.append((d, "CON-DRS", 1))
                if ward in ("W-ICU", "W-HC") or (diag in ("Pneumonia", "Bronchiolitis") and rng.random() < 0.6):
                    lines.append((d, "CON-OXY", rng.randint(4, 24)))
            if diag in ("Pneumonia", "Major trauma", "Cardiac chest pain", "Knee injury") or rng.random() < 0.1:
                lines.append((day, "RAD-XR", 1))
            if diag in ("Stroke", "Major trauma"):
                lines.append((day, "RAD-CT", 1))
            if not is_open and rng.random() < 0.6:
                lines.append((discharge_day, "PHA-TTO", 1))
            if ward in ("W-GEN", "W-SUR", "W-MAT") and rng.random() < 0.08:
                lines.append((day, "EXT-PVT", len(nights)))

            # ---- the bill (used to make realistic payments)
            funder_due = patient_due = 0.0
            billable = [(d, code, qty) for d, code, qty in lines] + [(d, ward_tariff[ward], 1) for d in nights]
            for d, code, qty in billable:
                amount = round(qty * rate_on(code, d), 2)
                f_part = round(amount * cover[funder] / 100, 2) if info[code][5] == "Y" else 0.0
                funder_due += f_part
                patient_due += amount - f_part

            # ---- admission row (with some mess)
            row = {"AdmissionID": adm_id, "PatientID": patient["PatientID"], "WardCode": ward,
                   "DoctorID": rng.choice(ward_doctors[ward]),
                   "FunderCode": funder, "AuthorisationNo": "" if funder == "PRIV" else f"AUTH{rng.randint(100000, 999999)}",
                   "AdmitDateTime": messy_date(admit_dt, True),
                   "DischargeDateTime": "" if is_open else messy_date(discharge_dt, True),
                   "AdmissionType": adm_type, "DiagnosisGroup": diag}
            if funder == "PRIV" and rng.random() < 0.3:
                row["FunderCode"] = ""
            r = rng.random()
            if r < 0.04:
                row["AdmissionType"] = rng.choice([adm_type.upper(), adm_type.lower(), f" {adm_type} ", adm_type.replace(" ", "")])
            if rng.random() < 0.02:
                row["WardCode"] = f" {ward.lower()}"
            r = rng.random()
            if r < 0.003 and not is_open:
                row["AdmitDateTime"], row["DischargeDateTime"] = row["DischargeDateTime"], row["AdmitDateTime"]
                if row["AdmitDateTime"][:10] == row["DischargeDateTime"][:10]:
                    row["DischargeDateTime"] = messy_date(admit_dt - timedelta(days=2), True)
            elif r < 0.006:
                row["WardCode"] = "W-XXX"
            elif r < 0.008:
                row["PatientID"] = "P999999"
            elif r < 0.010:
                row["AdmitDateTime"] = rng.choice(["", "unknown", "2025-02-30 10:00"])
            month_file = f"admissions_{day:%Y_%m}.csv"
            admissions[month_file].append(row)
            if rng.random() < 0.005:
                admissions[month_file].append(dict(row))

            # ---- charge rows
            for d, code, qty in lines:
                chg_no += 1
                c = {"ChargeID": f"CH{chg_no:07d}", "AdmissionID": adm_id, "ServiceDate": messy_date(d),
                     "TariffCode": code, "Quantity": qty, "CapturedBy": rng.choice(["nurse01", "nurse02", "nurse03", "theatre", "pharm01", "billing"])}
                r = rng.random()
                if r < 0.004:
                    c["Quantity"] = rng.choice([0, -1])
                elif r < 0.007:
                    c["TariffCode"] = "XXX-000"
                elif r < 0.010:
                    c["AdmissionID"] = "ADM2599999"
                elif r < 0.013 and not is_open:
                    c["ServiceDate"] = messy_date(discharge_day + timedelta(days=rng.randint(5, 15)))
                elif r < 0.015:
                    c["ServiceDate"] = rng.choice(["", "n/a"])
                elif r < 0.035:
                    c["TariffCode"] = f" {code.lower()} "
                month_file = f"charges_{d:%Y_%m}.csv"
                charges[month_file].append(c)
                if rng.random() < 0.008:
                    charges[month_file].append(dict(c))

            # ---- payments
            def pay(when, amount, payer, method):
                nonlocal pay_no
                if amount <= 0 or when > CUTOFF:
                    return
                pay_no += 1
                p = {"PaymentID": f"PAY{pay_no:06d}", "AdmissionID": adm_id, "PaymentDate": messy_date(when),
                     "PayerType": payer, "Method": method, "Amount": f"{amount:.2f}"}
                r = rng.random()
                if r < 0.08:
                    p["Amount"] = f"R {amount:,.2f}"
                elif r < 0.082:
                    p["Amount"] = f"-{amount:.2f}"
                elif r < 0.084:
                    p["AdmissionID"] = "ADM2588888"
                if rng.random() < 0.05:
                    p["PayerType"] = rng.choice([payer.upper(), payer.lower()])
                payments.append(p)
                if rng.random() < 0.005:
                    payments.append(dict(p))

            if funder == "PRIV":
                deposit = min(round(patient_due, 2), float(rng.choice([5000, 10000, 15000, 25000])))
                pay(day, deposit, "Patient", rng.choice(["Card", "EFT", "Cash"]))
                rest = round(patient_due - deposit, 2)
                if not is_open and rest > 0:
                    r = rng.random()
                    if r < 0.65:
                        pay(discharge_day + timedelta(days=rng.randint(3, 40)), rest, "Patient", rng.choice(["Card", "EFT"]))
                    elif r < 0.85:
                        pay(discharge_day + timedelta(days=rng.randint(10, 60)), round(rest * rng.uniform(0.2, 0.7), 2), "Patient", "EFT")
            elif not is_open:
                r = rng.random()
                when = discharge_day + timedelta(days=rng.randint(20, 50))
                if r < 0.85:
                    pay(when, round(funder_due, 2), "Funder", "Remittance")
                elif r < 0.93:
                    pay(when, round(funder_due * rng.uniform(0.85, 0.95), 2), "Funder", "Remittance")
                r = rng.random()
                if r < 0.6:
                    pay(discharge_day + timedelta(days=rng.randint(1, 60)), round(patient_due, 2), "Patient", rng.choice(["Card", "EFT"]))
                elif r < 0.75:
                    pay(discharge_day + timedelta(days=rng.randint(10, 70)), round(patient_due * rng.uniform(0.3, 0.8), 2), "Patient", "EFT")
        day += timedelta(days=1)

    # ---- reference files
    pd.DataFrame([{"WardCode": w[0], "WardName": w[1] + ("  " if rng.random() < 0.3 else ""), "WardType": w[2],
                   "BedCount": w[3], "AccommodationTariff": w[4]} for w in WARDS]
                 ).to_excel(RAW_DIR / "wards.xlsx", index=False, sheet_name="Wards")
    pd.DataFrame(doctors).to_excel(RAW_DIR / "doctors.xlsx", index=False, sheet_name="Doctors")
    pd.DataFrame([{"FunderCode": f[0], "FunderName": f[1], "FunderType": f[2], "CoverPct": f[3]} for f in FUNDERS]
                 ).to_excel(RAW_DIR / "funders.xlsx", index=False, sheet_name="Funders")
    t_rows = []
    for t in tariffs:
        t = dict(t)
        t["EffectiveFrom"] = t["EffectiveFrom"].strftime("%Y-%m-%d")
        r = rng.random()
        if r < 0.15:
            t["Rate"] = f"R {t['Rate']:,.2f}"
        if rng.random() < 0.15:
            t["Category"] = t["Category"].upper()
        t_rows.append(t)
    pd.DataFrame(t_rows).to_excel(RAW_DIR / "tariffs.xlsx", index=False, sheet_name="Tariffs")

    p_rows = []
    for p in patients:
        p = dict(p)
        p["DateOfBirth"] = messy_date(p["DateOfBirth"])
        p["Gender"] = rng.choice({"F": ["F", "F", "F", "Female", "f"], "M": ["M", "M", "M", "Male", "m"]}[p["Gender"]])
        if rng.random() < 0.05:
            p["FullName"] = f" {p['FullName'].upper()} "
        if rng.random() < 0.01:
            p["DateOfBirth"] = ""
        p_rows.append(p)
    p_rows += [dict(r) for r in rng.sample(p_rows, 40)]
    rng.shuffle(p_rows)
    write_csv("patients.csv", p_rows)

    for name, rows in admissions.items():
        write_csv(name, rows)
    for name, rows in charges.items():
        write_csv(name, rows)
    write_csv("payments_2025.csv", payments)
    print(f"{len(p_rows)} patient rows, {sum(map(len, admissions.values()))} admission rows, "
          f"{sum(map(len, charges.values()))} charge rows, {len(payments)} payment rows -> {RAW_DIR}")


if __name__ == "__main__":
    main()
