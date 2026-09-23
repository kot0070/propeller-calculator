from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import sys
from pathlib import Path

from .config import APP_FOLDER, AUTHOR, PUBLISHER_FOLDER
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
    target.parent.mkdir(parents=True, exist_ok=True)
    destination = sqlite3.connect(target)
    connection.backup(destination)
    destination.close()
