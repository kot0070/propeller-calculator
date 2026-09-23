from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path


path = Path(sys.argv[1])
connection = sqlite3.connect(path)
tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
metadata = dict(connection.execute("SELECT key,value FROM metadata")) if "metadata" in tables else {}
settings = dict(connection.execute("SELECT key,value FROM app_settings"))
report = {
    "path": str(path.resolve()),
    "bytes": path.stat().st_size,
    "quick_check": connection.execute("PRAGMA quick_check").fetchone()[0],
    "foreign_key_errors": len(connection.execute("PRAGMA foreign_key_check").fetchall()),
    "models": connection.execute("SELECT COUNT(*) FROM models").fetchone()[0],
    "performance_points": connection.execute("SELECT COUNT(*) FROM performance_points").fetchone()[0],
    "author": metadata.get("author", "Ivan Soprun"),
    "calculator_mode": settings.get("calculator_mode"),
    "saved_builds": connection.execute("SELECT COUNT(*) FROM saved_builds").fetchone()[0],
    "saved_build_components": connection.execute("SELECT COUNT(*) FROM saved_build_components").fetchone()[0],
}
connection.close()
print(json.dumps(report, ensure_ascii=False, indent=2))
