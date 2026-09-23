from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from propcalc.audit import export_audit, export_manual_verification
from propcalc.database import connect_database, integrity_report
from propcalc.ingest import IngestSession


def main() -> None:
    database_path = ROOT / "work" / "build" / "propellers.db"
    if database_path.exists():
        database_path.unlink()
    connection = connect_database(database_path)
    session = IngestSession(connection)
    stats = session.run_all(ROOT / "work" / "source_audit" / "extraction_manifest.json")
    audit = export_audit(connection, ROOT / "work" / "reports")
    verification = export_manual_verification(connection, ROOT / "work" / "reports" / "manual_verification.json")
    integrity = integrity_report(connection)
    connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    connection.execute("VACUUM")
    connection.close()
    result = {"ingest_stats": stats, "totals": audit["totals"], "integrity": integrity,
              "manual_checks": [item["result"] for item in verification], "database_bytes": database_path.stat().st_size}
    (ROOT / "work" / "reports" / "build_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
