from __future__ import annotations

import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
database = ROOT / "work" / "build" / "propellers.db"
connection = sqlite3.connect(database)
for key, value in (("calculator_mode", "0"),):
    connection.execute(
        "INSERT INTO app_settings(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
connection.commit()
print(connection.execute("SELECT key,value FROM app_settings ORDER BY key").fetchall())
connection.close()
