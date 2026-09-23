from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from propcalc.audit import export_audit, export_manual_verification
from propcalc.database import connect_database


connection = connect_database(ROOT / "work" / "build" / "propellers.db")
export_audit(connection, ROOT / "work" / "reports")
export_manual_verification(connection, ROOT / "work" / "reports" / "manual_verification.json")
connection.close()
