# Propeller Calculator Professional UA — 3.3.0

## Portfolio snapshot

**Windows desktop engineering application for calculating, comparing, and exploring propeller data.**

- **Stack:** Python 3.11+ · PySide6 · local database · unittest · PyInstaller
- **Dataset scale:** **1,053 propeller models** and **335,434 characteristics**
- **UI:** Ukrainian / English
- **Delivery:** source code, tests, data-processing scripts, reproducible build instructions, and standalone Windows EXE
- **Offline-first:** no Python installation is required for the packaged application

This project demonstrates desktop application development, large local dataset handling, engineering-oriented calculation workflows, packaging, testing, and reproducible release artifacts.

[Українською](README_UA.md)

Author: **Ivan Soprun**. Offline Windows application for calculating and comparing propellers, with Ukrainian and English interfaces.

The repository contains the original code, tests, data-processing scripts, build materials, the user guide, and reports. The ready EXE, embedded database, and source datasets are available from the [public release v3.3.0](https://github.com/kot0070/propeller-calculator/releases/tag/v3.3.0).

## MVP status — 3.3.0

Status: **MVP RELEASE CANDIDATE**. All 14 release gates PASS.
Test suites: 78 unittest methods plus the 14-block UI functional verification. Current CI prepares both the verified production database and the schema-only test fixture, and does not accept unexpected skipped unittests.
Workbook: 127 tests — 60 PASS / 62 N/A (out-of-scope platforms with evidence) / 5 NOT STARTED (all non-gate).
Production DB: 1053 models / 335434 points.
EXE: `Propeller_Calculator_Professional_UA_v3_3.exe`.
Agent report: `work/AGENT_PERFORMANCE_REPORT.md` (strengths, weaknesses, recommendations).
Known residuals: T043 empty-state CTAs and T044 busy indicators shipped (both PASS); remaining open: screen-reader live-hearing leg (T045 residual), env-bound taste rows T046/P008/P010 (NOT STARTED), manual UAT users.
Database tab: one-click restore (`restoreDatabase` → `restore_database`/`restore_database_from_path`) with fail-closed read-only validation (`validate_restore_candidate`: `PRAGMA quick_check`, required tables, model-count check), timestamped safety backup, and atomic replace. Calculator (simple + engineering) and comparison tabs: in-app PDF reports (`exportCalcPdf` → `export_calc_pdf_report`, `exportComparePdf` → `export_compare_pdf_report`) via Qt `QTextDocument`/`QPdfWriter`, covering inputs, results, source-vs-math, warnings, and app version.

## Ready application

Download `Propeller_Calculator_Professional_UA_v3_3.exe` from the release. Python and installation are not required. User guide: [outputs/README_UA.md](outputs/README_UA.md); the full PDF is in `outputs/`.

## Run from source

Requires Python 3.11+ on Windows. PowerShell commands from the repository root:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Download `propellers-database-v3.3.0.zip` from the release into the project root and extract it:

```powershell
New-Item -ItemType Directory -Path work\build -Force
Expand-Archive -LiteralPath .\propellers-database-v3.3.0.zip -DestinationPath .\work\build
.\.venv\Scripts\python.exe .\src\main.py
```

To download with an authenticated GitHub CLI:

```powershell
gh release download v3.3.0 --repo kot0070/propeller-calculator --pattern propellers-database-v3.3.0.zip
```

The database `work/build/propellers.db` contains 1,053 models and 335,434 characteristics. The application creates a separate working copy in `%LOCALAPPDATA%\IvanSoprun\PropellerCalculatorProfessionalUA`.

## Tests

After restoring the production database, also create the schema-only test fixture before running the full suite. GitHub Actions does this automatically.

```powershell
$env:PYTHONPATH = "$PWD\src"
python -c "import sqlite3; from propcalc.database import initialize_database; p=r'work/build/propellers.seed.db'; c=sqlite3.connect(p); initialize_database(c); c.commit(); c.close()"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

`work/build/propellers.db` is used for production-data integrity/calculation checks. `work/build/propellers.seed.db` is intentionally schema-only and is copied into temporary locations by empty-state, restore and PDF tests.

## Build the EXE

```powershell
.\.venv\Scripts\python.exe -m pip install "PyInstaller>=6,<7"
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm PropellerCalculator.spec
```

Result: `dist/Propeller_Calculator_Professional_UA_v3_3.exe`. The root spec uses relative paths; the previous original spec is kept in `work/pyinstaller/`.

## Data and integrity checks

- `propellers-database-v3.3.0.zip` — full initial database, required to run from source and for production-data tests.
- `propeller-source-data-v3.3.0.zip` — preserved source files; extract into `work/extracted/` for research or to reproduce the import, subject to the original third-party source terms.
- `SHA256SUMS.txt` in the release — checksums of the downloadable files.
- `outputs/` — audit, user guide, screenshot, release manifest and test reports from the release process. Their results describe the checks performed for v3.3.0.

Scripts in `work/scripts/` and inventories in `work/source_audit/` are kept from the original development process; some helper scripts contain paths and dependencies from that environment. They are not required for a normal run.
