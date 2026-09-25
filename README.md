# Propeller Calculator Professional UA — 3.3.0

[Українською](README_UA.md)

Author: **Ivan Soprun**. Offline Windows application for calculating and comparing propellers, with Ukrainian and English interfaces.

The repository contains the original code, tests, data-processing scripts, build materials, the user guide, and reports. The ready EXE, embedded database, and source datasets are stored in the [private release v3.3.0](https://github.com/kot0070/propeller-calculator/releases/tag/v3.3.0).

## MVP status — 3.3.0

Status: **MVP RELEASE CANDIDATE**. All 14 release gates PASS.
Test suites: 41 unit + 14-block UI functional, all green.
Workbook: 127 tests — 58 PASS / 62 N/A (out-of-scope platforms with evidence) / 7 NOT STARTED (all non-gate).
Production DB: 1053 models / 335434 points.
EXE: `Propeller_Calculator_Professional_UA_v3_3.exe`.
Agent report: \work/AGENT_PERFORMANCE_REPORT.md\ (strengths, weaknesses, recommendations).
Known residuals: CI workflow pending token scope; screen-reader live hearing + second-twin translations noted; manual taste rows (T043 CTA etc.) open.
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

After restoring the database:

```powershell
$env:PYTHONPATH = "$PWD\src"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Build the EXE

```powershell
.\.venv\Scripts\python.exe -m pip install "PyInstaller>=6,<7"
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm PropellerCalculator.spec
```

Result: `dist/Propeller_Calculator_Professional_UA_v3_3.exe`. The root spec uses relative paths; the previous original spec is kept in `work/pyinstaller/`.

## Data and integrity checks

- `propellers-database-v3.3.0.zip` — full initial database, required to run from source and to run tests.
- `propeller-source-data-v3.3.0.zip` — all preserved source files; extract into `work/extracted/` for research or to reproduce the import.
- `SHA256SUMS.txt` in the release — checksums of the downloadable files.
- `outputs/` — original audit, user guide, screenshot, and reports from the earlier development. Their results describe the checks at the time the version was created.

Scripts in `work/scripts/` and inventories in `work/source_audit/` are kept from the original; some helper scripts contain paths and dependencies from the original development environment. They are not required for a normal run.
