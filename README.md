# Lakeside Hospital Records Pipeline

An ETL project built around a made-up private hospital. It takes admission, charge and payment files, cleans them with Python, loads them into SQL Server, and works out what each patient account was charged, who owes what, and how full the wards were.

Author: Oregomoditse Makinta

The patients, doctors and medical schemes are invented by `scripts/generate_source_data.py`. No real patient information is used anywhere.

## What it covers

- **Resources** - wards with a fixed number of beds, and the doctors who admit to them
- **Admissions** - who was admitted, to which ward, under which doctor, for how long
- **Accounts** - every admission is an account. It has charges on one side and payments on the other
- **Charging** - how the amount on each account is worked out (this is the main part, see below)

## The source files

In `data/raw`:

| file | what it is |
|---|---|
| `wards.xlsx` | 7 wards, bed count, and which tariff a night in that ward is billed at |
| `doctors.xlsx` | 22 doctors and their speciality |
| `funders.xlsx` | medical aid plans and how much of the bill they cover, plus `PRIV` for self-paying patients |
| `tariffs.xlsx` | the price list. Some codes have two rows because prices went up on 1 July |
| `patients.csv` | patients |
| `admissions_2025_MM.csv` | one file per month |
| `charges_2025_MM.csv` | one file per month. Only a tariff code and a quantity, **no amounts** |
| `payments_2025.csv` | payments from funders and patients |

The files are messy on purpose: mixed date formats, duplicates, discharges dated before the admission, charges for admissions that don't exist, charges dated after the patient went home, amounts like `R 12,500.00`, lower-case codes with spaces, and so on.

## How charging works

The charge files don't have rand amounts in them. The amounts are calculated in `core.usp_LoadCharges` (in `sql/05_create_load_procedures.sql`). The rules:

1. **Amount = quantity x rate.** The rate comes from the price list, and it has to be the rate that was valid on the day of the service. Accommodation went up 6% and theatre 5% on 1 July, so the same code can have two prices in the year.
2. **Different things are charged in different units.** Wards per day, theatre per minute, procedures as a flat fee, pharmacy and consumables per unit, oxygen per hour.
3. **Accommodation is not in any file.** It is worked out from the admission: one charge line per night, at the tariff for that ward. A day case counts as one day. A stay that crosses 1 July gets the old rate for the nights before and the new rate after. Patients still in hospital are charged up to the latest date in the data.
4. **The bill is split between the funder and the patient.** The funder pays its cover % (for example 80%) of each line and the patient pays the rest. Self-paying patients have 0% cover, so everything is theirs.
5. **Some things funders never pay for.** Take-home medication and private room upgrades are marked as not covered in the price list, so they go fully to the patient even on a 100% plan.

Payments are then matched to the account, split by who paid, and `reporting.vw_AccountBalance` shows what the funder and the patient each still owe.

## How it fits together

```
raw files -> Python (pandas) -> landing tables -> stored procs -> core tables -> reporting views -> Excel
                  |
                  +-> rejected rows go to data/rejects with a reason
```

Core tables:

- `core.DimWard`, `core.DimDoctor` - the resources
- `core.DimFunder`, `core.DimPatient`, `core.DimDate`
- `core.DimTariff` - the price list with `EffectiveFrom` / `EffectiveTo` on each row
- `core.FactAdmission` - one row per admission
- `core.FactCharge` - one row per charge line, with amount, funder part and patient part
- `core.FactPayment` - one row per payment

Because each accommodation charge line is one bed for one night, counting them per ward per month also gives bed occupancy (`reporting.vw_WardOccupancy`). I liked that the billing data answered a resource question without needing anything extra.

## Running it

You need Python 3.10+, SQL Server 2016 SP1 or newer, SSMS and the ODBC driver for SQL Server.

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
copy config.example.ini config.ini
```

Edit `config.ini` for your server, then run `sql/01` to `sql/07` in SSMS in order.

Or let Python run the scripts instead of SSMS (careful: this rebuilds the core tables, so only on a fresh database):

```
python -m pipeline.deploy_sql
```

```
python -m pipeline.run_pipeline
python -m reports.build_excel_report
```

To see only the cleaning step, without a database:

```
python -m pipeline.run_pipeline --skip-load
```

After a load, check the data quality view. Everything should say PASS:

```
python -m pipeline.check_quality
```

(or `SELECT * FROM reporting.vw_DataQualityChecks` in SSMS). `sql/08_analysis_queries.sql` has the queries I used to look at the results (debtors age analysis, average bill per diagnosis, readmissions within 30 days, theatre hours per month and a few more).

Tests: `python -m pytest`

## CI/CD

This is the part I added last. It uses GitHub Actions, which is built into GitHub and free for public repositories.

**What the words mean**

- **CI (continuous integration)**: every time I push code, a machine at GitHub downloads the repository and checks it automatically. If I broke something, I find out in a minute or two instead of weeks later. The point is that the checks run every time without me having to remember.
- **CD (continuous delivery)**: getting the tested code out in a form that can be used, also automatically. No building or copying by hand.
- **A workflow** is a YAML file in `.github/workflows`. It says when to run (the trigger) and what to do (a list of steps). GitHub reads these files by itself, there is nothing to switch on.
- **A runner** is the temporary machine GitHub starts for each run. It is thrown away afterwards, so every run starts clean.
- **Green / red**: every step is a command. If a command ends with an error the run stops and is marked red. Otherwise it is green.

**The three workflows**

| file | when it runs | what it does |
|---|---|---|
| `ci.yml` | every push to `main`, every pull request | installs Python and the packages, lints the code with ruff, runs the tests, runs the cleaning step on the real files |
| `sql-integration.yml` | only when I start it by hand | starts a real SQL Server in a container, builds the database from the `sql` folder, runs the full pipeline into it twice, and fails if any data quality check says FAIL |
| `release.yml` | when I push a version tag like `v1.0.0` | runs the tests again, zips the project, and publishes it on the repository's Releases page |

So `ci.yml` is the CI, `release.yml` is the CD, and `sql-integration.yml` is a bigger test that sits in between.

**Trying it**

1. Push the project to GitHub. `ci.yml` starts by itself. Look under the **Actions** tab.
2. To run the SQL test: Actions > "SQL integration test" > Run workflow.
3. To make a release:
   ```
   git tag v1.0.0
   git push origin v1.0.0
   ```
   A few minutes later there is a v1.0.0 under **Releases** with the zip attached.

To see CI catch something, change one of the numbers in `tests/test_pipeline_counts.py` and push. The run goes red and shows which test failed.

**Things I had to change to make this possible**

- `pipeline/deploy_sql.py` is new. It runs the SQL scripts from Python, because a CI machine has no SSMS and nobody to press F5. It has to cut each file up on the `GO` lines, because `GO` is an SSMS thing and SQL Server doesn't understand it.
- The data quality checks moved from a query into a view (`reporting.vw_DataQualityChecks`), and `pipeline/check_quality.py` reads it and ends with an error if anything failed. A CI step can only pass or fail on an exit code, it can't look at a result grid.
- `tests/test_pipeline_counts.py` runs the cleaning on the real files and checks the row counts haven't changed.
- `requirements-dev.txt` and `ruff.toml` for the test and lint tools.

**What the CD does not do**

It does not deploy anything to a database server. My SQL Server runs on my own laptop, and a machine at GitHub can't reach that. Real deployment would need a server GitHub can connect to (Azure SQL for example) or a self-hosted runner on my network, with the connection details stored in GitHub Secrets. So "delivery" here stops at a tested, versioned zip.

## Numbers to check against

Cleaning step:

| | read | kept | rejected |
|---|---|---|---|
| patients | 3,240 | 3,200 | 40 |
| admissions | 4,691 | 4,608 | 83 |
| charge lines | 70,916 | 68,526 | 2,390 |
| payments | 6,742 | 6,602 | 140 |

A lot of the charge rejects (988) are "Admission not found". Most of those are charges that belong to an admission that was itself rejected, so one bad admission row takes its charges with it.

After the load, the totals query at the top of `08_analysis_queries.sql` should show:

| | |
|---|---|
| admissions | 4,608 |
| captured charge lines | 68,526 |
| accommodation lines (bed-days) | 13,395 |
| total charged | R 171,545,179.75 |
| funder liable | R 127,014,559.57 |
| patient liable | R 44,530,620.18 |
| total paid | R 138,102,562.73 |

These were worked out separately in pandas from the cleaned files using the same rules, so if the SQL gives something different, one of the two has a mistake.

## Decisions I'm not sure about

- An admission with no funder is treated as self-pay. Could also be a capture error.
- Negative payments are rejected. In real life they could be refunds or reversals.
- A charge dated outside the admission is rejected completely instead of being flagged for someone to look at.
- If an admission is rejected, all its charges and payments are rejected too. That is money that never reaches the report.

## Known issues / not done yet

- Captured charges are priced once, when they are first loaded. If a rate is corrected in the price list later, old charge lines are not re-priced. Accommodation is rebuilt every run so it does pick up changes.
- If the funder on an admission is corrected later, the funder/patient split on charges already loaded is not redone.
- The cover % is one number per funder. Real schemes have limits, co-payments per procedure, and different rates per tariff.
- A patient stays in one ward for the whole admission. No transfers (ICU to general ward for example), which would change the nightly rate.
- Landing tables are fully reloaded each run.
- `DimDate` only covers 2024 to 2026.
- The SQL is only tested by the integration workflow, and that one is started by hand. It should run on every push once I trust it.
- No deployment to a real server (see CI/CD above).
- `deploy_sql.py` rebuilds the core tables every time. There are no migrations, so there is no safe way to change a table that already has data in it.
- `deploy_sql.py` would split in the wrong place if a line inside a comment or a string was just the word GO.
- The password for the test SQL Server is written in the workflow file. That is fine for a throwaway container with fake data, but it's a habit to be careful with.
- The Excel report is formatted tables only, no charts.

## Things I might add

- ward transfers
- scheme tariffs (a different rate per funder for the same code)
- refunds and credit notes
- a Power BI report on the views
