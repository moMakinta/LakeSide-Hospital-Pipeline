"""Runs the whole thing: extract -> transform -> load.

    python -m pipeline.run_pipeline              # full run, needs SQL Server
    python -m pipeline.run_pipeline --skip-load  # just the cleaning step
"""
import argparse
import logging

from pipeline import extract, transform
from pipeline.config import CLEAN_DIR, RAW_DIR, REJECT_DIR

log = logging.getLogger("pipeline")


def _save(frame, folder, name):
    folder.mkdir(parents=True, exist_ok=True)
    frame.to_csv(folder / f"{name}.csv", index=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-load", action="store_true", help="stop after writing the cleaned files")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")

    raw = extract.extract_all(RAW_DIR)

    # reference data first, the transactions get checked against it
    tariffs, rej_tariffs = transform.clean_tariffs(raw["tariffs"])
    wards, rej_wards = transform.clean_wards(raw["wards"], tariffs)
    doctors, rej_doctors = transform.clean_doctors(raw["doctors"])
    funders, rej_funders = transform.clean_funders(raw["funders"])
    patients, rej_patients = transform.clean_patients(raw["patients"])
    admissions, rej_adm, stats = transform.clean_admissions(raw["admissions"], patients, wards, doctors, funders)
    charges, rej_charges = transform.clean_charges(raw["charges"], admissions, tariffs)
    payments, rej_payments = transform.clean_payments(raw["payments"], admissions)

    clean = {"Tariff": tariffs, "Ward": wards, "Doctor": doctors, "Funder": funders, "Patient": patients,
             "Admission": admissions, "Charge": charges, "Payment": payments}
    rejects = {"Tariff": rej_tariffs, "Ward": rej_wards, "Doctor": rej_doctors, "Funder": rej_funders,
               "Patient": rej_patients, "Admission": rej_adm, "Charge": rej_charges, "Payment": rej_payments}

    for name in clean:
        _save(clean[name], CLEAN_DIR, name.lower())
        _save(rejects[name], REJECT_DIR, f"{name.lower()}_rejects")
        log.info("%-10s %6d kept, %5d rejected", name, len(clean[name]), len(rejects[name]))
        if len(rejects[name]):
            for reason, count in rejects[name]["RejectReason"].value_counts().items():
                log.info("    %-40s %5d", reason, count)
    for key, value in stats.items():
        log.info("%s: %d", key, value)

    if args.skip_load:
        log.info("--skip-load given, cleaned files are in %s", CLEAN_DIR)
        return

    from pipeline import load      # imported here so --skip-load works without pyodbc installed
    engine = load.get_engine()
    load.load_landing(engine, clean)
    result = load.run_core_load(engine)
    log.info("Load finished:\n%s", result.to_string(index=False))


if __name__ == "__main__":
    main()
