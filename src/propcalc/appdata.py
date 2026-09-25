# Copyright (c) 2026 Ivan Soprun. All rights reserved.
from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from .config import APP_FOLDER, APP_VERSION, AUTHOR, PUBLISHER_FOLDER
from .database import connect_database, initialize_database


def resource_path(relative: str) -> Path:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return root / relative


def local_paths() -> dict[str, Path]:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / PUBLISHER_FOLDER / APP_FOLDER
    return {"base": base, "database": base / "propellers.db", "backups": base / "backups",
            "exports": base / "exports", "logs": base / "logs"}


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def embedded_database_path() -> Path:
    candidates = [resource_path("assets/propellers.db"), resource_path("work/build/propellers.db")]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("Embedded propellers.db is missing")


def prepare_working_database() -> tuple[Path, dict[str, Path]]:
    paths = local_paths()
    for key in ("base", "backups", "exports", "logs"):
        paths[key].mkdir(parents=True, exist_ok=True)
    embedded = embedded_database_path()
    database = paths["database"]
    if not database.exists():
        # Publish the initial 296 MB database atomically.  A power loss or forced
        # termination during the copy may leave only this staging file; the next
        # launch safely overwrites it while an existing working database is never
        # replaced by an EXE update.
        staging = database.with_suffix(".db.installing")
        shutil.copy2(embedded, staging)
        os.replace(staging, database)
    connection = connect_database(database)
    initialize_database(connection)
    embedded_hash = file_sha(embedded)
    connection.execute("INSERT INTO app_settings(key,value) VALUES('author',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (AUTHOR,))
    connection.execute("INSERT INTO app_settings(key,value) VALUES('embedded_db_sha256',?) ON CONFLICT(key) DO NOTHING", (embedded_hash,))
    connection.commit()
    connection.close()
    return database, paths


def export_database(connection: sqlite3.Connection, target: Path) -> None:
    """Full-fidelity safety copy (connection.backup).

    Retained ONLY for internal backups/ safety copies. Never used for the
    Database-tab user export (see export_user_data): this dumps the entire
    ~296 MB vendor corpus alongside user rows.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    destination = sqlite3.connect(target)
    connection.backup(destination)
    destination.close()


# ---------------------------------------------------------------------------
# User-only export format ("Propeller user data", *.pudb).
#
# A *.pudb file is a plain SQLite database (openable by any SQLite client)
# containing ONLY user-owned tables:
#   motors, batteries, frames, saved_builds, saved_build_components
# plus one manifest table:
#   export_manifest(key TEXT PRIMARY KEY, value TEXT NOT NULL)
#
# Manifest keys: format ("propcalc-user-data/1"), exported_at (UTC ISO-8601),
# app_version, source_db_sha256 (hex, may be "" when unavailable), and one
# "rows_<table>" count per user table. Vendor tables (models,
# performance_points, geometries, sources, ...) are NEVER created here, so a
# user export contains zero vendor rows by construction. Full-corpus copies
# remain available only via export_database() for internal safety backups.
# ---------------------------------------------------------------------------

USER_EXPORT_FORMAT = "propcalc-user-data/1"

USER_EXPORT_TABLES = (
    "motors",
    "batteries",
    "frames",
    "saved_builds",
    "saved_build_components",
)

_USER_EXPORT_SCHEMA_SQL = r"""
CREATE TABLE motors (
    motor_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    manufacturer TEXT,
    kv_rpm_per_v REAL,
    resistance_ohm REAL,
    no_load_current_a REAL,
    max_current_a REAL,
    max_power_w REAL,
    max_voltage_v REAL,
    mass_kg REAL,
    notes TEXT,
    is_user INTEGER NOT NULL DEFAULT 1,
    UNIQUE(name, manufacturer)
);

CREATE TABLE batteries (
    battery_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    chemistry TEXT NOT NULL DEFAULT 'LiPo',
    cells_s INTEGER,
    capacity_ah REAL,
    c_rating REAL,
    internal_resistance_ohm REAL,
    mass_kg REAL,
    notes TEXT,
    is_user INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE frames (
    frame_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    geometry TEXT,
    diagonal_m REAL,
    motor_count INTEGER,
    arm_width_m REAL,
    arm_thickness_m REAL,
    material TEXT,
    mass_kg REAL,
    payload_kg REAL,
    holes_factor REAL,
    custom_json TEXT,
    is_user INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE saved_builds (
    build_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    propeller_model_id TEXT,
    motor_id INTEGER REFERENCES motors(motor_id),
    battery_id INTEGER REFERENCES batteries(battery_id),
    frame_id INTEGER REFERENCES frames(frame_id),
    motor_kv REAL,
    battery_s INTEGER,
    battery_capacity_ah REAL,
    esc_current_a REAL,
    motor_count INTEGER NOT NULL DEFAULT 1,
    mass_kg REAL,
    payload_kg REAL,
    advanced_json TEXT NOT NULL DEFAULT '{}',
    note TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE saved_build_components (
    component_id INTEGER PRIMARY KEY AUTOINCREMENT,
    build_id INTEGER NOT NULL REFERENCES saved_builds(build_id) ON DELETE CASCADE,
    component_type TEXT NOT NULL,
    component_ref TEXT,
    quantity INTEGER NOT NULL DEFAULT 1,
    properties_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE export_manifest (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def export_user_data(
    connection: sqlite3.Connection,
    target: Path,
    *,
    source_sha256: str = "",
) -> dict[str, str]:
    """Write a user-only export (see format notes above) and return its manifest."""
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    manifest: dict[str, str] = {
        "format": USER_EXPORT_FORMAT,
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "app_version": APP_VERSION,
        "source_db_sha256": source_sha256 or "",
    }
    destination = sqlite3.connect(target)
    try:
        destination.execute("PRAGMA foreign_keys=OFF")
        destination.executescript(_USER_EXPORT_SCHEMA_SQL)
        for table in USER_EXPORT_TABLES:
            rows = connection.execute(f"SELECT * FROM {table}").fetchall()
            if rows:
                columns = list(rows[0].keys())
                destination.executemany(
                    f"INSERT INTO {table}({','.join(columns)})"
                    f" VALUES({','.join('?' for _ in columns)})",
                    [tuple(row[column] for column in columns) for row in rows],
                )
            manifest[f"rows_{table}"] = str(len(rows))
        destination.executemany(
            "INSERT INTO export_manifest(key,value) VALUES(?,?)",
            list(manifest.items()),
        )
        destination.commit()
    finally:
        destination.close()
    return manifest
