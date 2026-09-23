from __future__ import annotations

import csv
import hashlib
import json
import shutil
import sqlite3
import tempfile
import time
import uuid
import zipfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .ingest import IngestSession, SOURCE_SPECS, sha256_file
from .normalization import compact_apc_alias, normalize_apc


class ImportErrorWithReport(RuntimeError):
    pass


def safe_extract(archive_path: Path, output: Path) -> list[tuple[str, Path, str, int]]:
    records: list[tuple[str, Path, str, int]] = []
    with zipfile.ZipFile(archive_path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            relative = Path(*Path(info.filename.replace("\\", "/")).parts)
            if relative.is_absolute() or ".." in relative.parts:
                raise ImportErrorWithReport(f"Unsafe archive member: {info.filename}")
            target = (output / relative).resolve()
            if output.resolve() not in target.parents:
                raise ImportErrorWithReport(f"Archive path escapes temporary directory: {info.filename}")
            target.parent.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256()
            with archive.open(info) as source, target.open("wb") as destination:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    destination.write(chunk)
                    digest.update(chunk)
            records.append((relative.as_posix(), target, digest.hexdigest().upper(), info.file_size))
    return records


def detect_archive(records: list[tuple[str, Path, str, int]]) -> str:
    names = [relative.upper() for relative, *_ in records]
    if any(Path(name).name.startswith("PER3_") and name.endswith(".DAT") for name in names):
        return "APC_PERFILES_202602"
    if any(name.endswith("-PERF.PE0") for name in names):
        return "APC_PE0_202602"
    if any("UIUC-PROPDB" in name or ("VOLUME-" in name and "/DATA/" in name) for name in names):
        return "UIUC_2022"
    if any(name.startswith("BBDD/") or "/BBDD/" in name for name in names):
        return "ENOLA_2026"
    raise ImportErrorWithReport("Archive is valid, but its layout is not recognized as UIUC, APC PERFILES/PE0, or ENOLA")


class RuntimeImportService:
    def __init__(self, connection: sqlite3.Connection, database_path: Path, backup_dir: Path):
        self.connection = connection
        self.database_path = database_path
        self.backup_dir = backup_dir

    def backup(self) -> Path:
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        target = self.backup_dir / (
            f"propellers-before-import-{time.strftime('%Y%m%d-%H%M%S')}-"
            f"{time.time_ns() % 1_000_000_000:09d}-{uuid.uuid4().hex[:8]}.db")
        backup_connection = sqlite3.connect(target)
        self.connection.backup(backup_connection)
        backup_connection.close()
        return target

    def import_path(self, source_path: str | Path) -> dict[str, Any]:
        path = Path(source_path)
        if not path.exists():
            raise FileNotFoundError(path)
        source_hash = sha256_file(path)
        backup = self.backup()
        before = {
            "models": self.connection.execute("SELECT COUNT(*) FROM models").fetchone()[0],
            "points": self.connection.execute("SELECT COUNT(*) FROM performance_points").fetchone()[0],
            "geometry": self.connection.execute("SELECT COUNT(*) FROM geometries").fetchone()[0],
        }
        cursor = self.connection.execute(
            "INSERT INTO import_history(source_path,source_sha256,status,backup_path) VALUES(?,?,'running',?)",
            (str(path), source_hash, str(backup)),
        )
        import_id = int(cursor.lastrowid)
        self.connection.commit()
        try:
            if path.suffix.lower() == ".db":
                detail = self._merge_database(path)
            elif path.suffix.lower() in {".zip", ".zipx"}:
                detail = self._import_archive(path)
            elif path.suffix.lower() == ".xlsx":
                detail = self._import_apc_catalog(path)
            elif path.suffix.lower() in {".dat", ".pe0"}:
                detail = self._import_single_apc_file(path)
            elif path.suffix.lower() == ".csv":
                detail = self._import_generic_csv(path)
            else:
                raise ImportErrorWithReport(f"Unsupported import extension: {path.suffix}")
            after = {
                "models": self.connection.execute("SELECT COUNT(*) FROM models").fetchone()[0],
                "points": self.connection.execute("SELECT COUNT(*) FROM performance_points").fetchone()[0],
                "geometry": self.connection.execute("SELECT COUNT(*) FROM geometries").fetchone()[0],
            }
            report = {"source": str(path), "sha256": source_hash, "backup": str(backup), "before": before,
                      "after": after, "added": {key: after[key] - before[key] for key in before}, **detail}
            self.connection.execute(
                """UPDATE import_history SET finished_at=CURRENT_TIMESTAMP,status='success',added=?,updated=?,skipped=?,
                   conflicts=?,errors=0,report_json=? WHERE import_id=?""",
                (sum(max(0, value) for value in report["added"].values()), detail.get("updated", 0),
                 detail.get("skipped", 0), detail.get("conflicts", 0), json.dumps(report, ensure_ascii=False), import_id),
            )
            self.connection.commit()
            return report
        except Exception as exc:
            self.connection.rollback()
            self.connection.execute(
                "UPDATE import_history SET finished_at=CURRENT_TIMESTAMP,status='error',errors=1,report_json=? WHERE import_id=?",
                (json.dumps({"error": f"{type(exc).__name__}: {exc}", "backup": str(backup)}, ensure_ascii=False), import_id),
            )
            self.connection.commit()
            raise

    def _prepare_session(self, code: str, archive_path: Path) -> IngestSession:
        session = IngestSession(self.connection)
        spec = SOURCE_SPECS[code]
        self.connection.execute(
            """INSERT INTO sources(code,name,organization,source_group,source_kind,version,source_date,archive_name,
               archive_sha256,archive_bytes,provenance_note) VALUES(?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(code) DO UPDATE SET archive_name=excluded.archive_name,archive_sha256=excluded.archive_sha256,
               archive_bytes=excluded.archive_bytes,imported_at=CURRENT_TIMESTAMP""",
            (code, spec["name"], spec["organization"], spec["source_group"], spec["source_kind"], spec["version"],
             spec["source_date"], archive_path.name, sha256_file(archive_path), archive_path.stat().st_size,
             spec["note"] + " Runtime merge import."),
        )
        session.source_ids[code] = self.connection.execute("SELECT source_id FROM sources WHERE code=?", (code,)).fetchone()[0]
        rows = self.connection.execute(
            """SELECT mm.raw_name,m.* FROM model_raw_mappings mm JOIN sources s ON s.source_id=mm.source_id
               JOIN models m ON m.model_id=mm.model_id WHERE s.code='APC_CATALOG_202602'"""
        ).fetchall()
        for row in rows:
            session.apc_aliases[compact_apc_alias(row["raw_name"])] = normalize_apc(row["raw_name"])
        return session

    def _import_archive(self, archive_path: Path) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="propcalc-import-") as temp:
            records = safe_extract(archive_path, Path(temp))
            code = detect_archive(records)
            self.connection.execute("BEGIN IMMEDIATE")
            session = self._prepare_session(code, archive_path)
            for relative, path, sha, size in records:
                session.register_file(code, relative, path, sha, size)
            if code == "UIUC_2022":
                session.ingest_uiuc()
            elif code == "APC_PERFILES_202602":
                session.ingest_apc_predictions()
            elif code == "APC_PE0_202602":
                session.ingest_apc_geometry()
            elif code == "ENOLA_2026":
                session.ingest_enola()
            session.classify_remaining_files()
            self.connection.commit()
            return {"source_code": code, "files": len(records), "updated": session.stats.get("performance_updated", 0) + session.stats.get("geometry_updated", 0),
                    "skipped": session.stats.get("performance_skipped", 0) + session.stats.get("geometry_skipped", 0),
                    "conflicts": 0, "parser_stats": dict(session.stats)}

    def _import_apc_catalog(self, path: Path) -> dict[str, Any]:
        code = "APC_CATALOG_202602"
        original = SOURCE_SPECS[code]["path"]
        SOURCE_SPECS[code]["path"] = path
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            session = self._prepare_session(code, path)
            session.register_file(code, path.name, path)
            session.ingest_apc_catalog()
            self.connection.commit()
            return {"source_code": code, "files": 1, "updated": 0, "skipped": 0, "conflicts": 0}
        finally:
            SOURCE_SPECS[code]["path"] = original

    def _import_single_apc_file(self, path: Path) -> dict[str, Any]:
        code = "APC_PE0_202602" if path.suffix.lower() == ".pe0" else "APC_PERFILES_202602"
        self.connection.execute("BEGIN IMMEDIATE")
        session = self._prepare_session(code, path)
        session.register_file(code, path.name, path)
        if code == "APC_PE0_202602":
            session.ingest_apc_geometry()
        else:
            session.ingest_apc_predictions()
        self.connection.commit()
        return {"source_code": code, "files": 1, "updated": session.stats.get("performance_updated", 0) + session.stats.get("geometry_updated", 0),
                "skipped": session.stats.get("performance_skipped", 0) + session.stats.get("geometry_skipped", 0),
                "conflicts": 0, "parser_stats": dict(session.stats)}

    def _import_generic_csv(self, path: Path) -> dict[str, Any]:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        delimiter = ";" if text.splitlines()[0].count(";") > text.splitlines()[0].count(",") else ","
        rows = list(csv.DictReader(text.splitlines(), delimiter=delimiter))
        headers = {key.upper().replace(" ", "") for key in (rows[0] if rows else {})}
        if "RPM" not in headers:
            raise ImportErrorWithReport("CSV is readable but lacks an RPM column; supported generic CSV requires RPM and Ct/Cp or thrust/torque")
        raise ImportErrorWithReport("Generic CSV model identity is ambiguous. Import it inside an ENOLA BBDD archive or use a compatible propellers.db.")

    def _merge_database(self, path: Path) -> dict[str, Any]:
        if path.resolve() == self.database_path.resolve():
            raise ImportErrorWithReport("The selected database is already the active working database")
        source = sqlite3.connect(path)
        source.row_factory = sqlite3.Row
        required = {"models", "performance_points", "sources", "source_files"}
        available = {row[0] for row in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not required.issubset(available):
            source.close()
            raise ImportErrorWithReport("Database is not compatible: required tables are missing")
        added = updated = skipped = conflicts = 0
        self.connection.execute("BEGIN IMMEDIATE")
        source_id_map: dict[int, int] = {}
        for row in source.execute("SELECT * FROM sources"):
            existing = self.connection.execute("SELECT source_id FROM sources WHERE code=?", (row["code"],)).fetchone()
            if existing:
                target_id = existing[0]
            else:
                columns = [key for key in row.keys() if key != "source_id"]
                cursor = self.connection.execute(
                    f"INSERT INTO sources({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",
                    tuple(row[column] for column in columns),
                )
                target_id = int(cursor.lastrowid)
            source_id_map[row["source_id"]] = target_id
        file_id_map: dict[int, int] = {}
        for row in source.execute("SELECT * FROM source_files"):
            target_source = source_id_map[row["source_id"]]
            existing = self.connection.execute(
                "SELECT source_file_id FROM source_files WHERE source_id=? AND relative_path=?", (target_source, row["relative_path"])
            ).fetchone()
            if existing:
                target_file = existing[0]
            else:
                columns = [key for key in row.keys() if key not in {"source_file_id", "source_id"}]
                cursor = self.connection.execute(
                    f"INSERT INTO source_files(source_id,{','.join(columns)}) VALUES(?,{','.join('?' for _ in columns)})",
                    (target_source,) + tuple(row[column] for column in columns),
                )
                target_file = int(cursor.lastrowid)
            file_id_map[row["source_file_id"]] = target_file
        model_columns = [row[1] for row in self.connection.execute("PRAGMA table_info(models)")]
        source_model_columns = [row[1] for row in source.execute("PRAGMA table_info(models)")]
        common = [column for column in model_columns if column in source_model_columns]
        for row in source.execute("SELECT * FROM models"):
            existing = self.connection.execute("SELECT * FROM models WHERE model_id=?", (row["model_id"],)).fetchone()
            changed = bool(existing and any(
                row[column] is not None and row[column] != existing[column]
                for column in common if column not in {"model_id", "created_at", "updated_at"}
            ))
            placeholders = ",".join("?" for _ in common)
            updates = ",".join(f"{column}=COALESCE(excluded.{column},models.{column})" for column in common if column != "model_id")
            self.connection.execute(
                f"INSERT INTO models({','.join(common)}) VALUES({placeholders}) ON CONFLICT(model_id) DO UPDATE SET {updates}",
                tuple(row[column] for column in common),
            )
            added += int(existing is None)
            updated += int(changed)
            skipped += int(existing is not None and not changed)
        for table, key_column in (("performance_points", "point_key"), ("geometries", "geometry_key")):
            if table not in available:
                continue
            target_columns = [row[1] for row in self.connection.execute(f"PRAGMA table_info({table})") if row[1] not in {"performance_id", "geometry_id"}]
            source_columns = [row[1] for row in source.execute(f"PRAGMA table_info({table})")]
            common = [column for column in target_columns if column in source_columns]
            for row in source.execute(f"SELECT * FROM {table}"):
                existing = self.connection.execute(f"SELECT content_hash FROM {table} WHERE {key_column}=?", (row[key_column],)).fetchone()
                values = []
                for column in common:
                    values.append(file_id_map.get(row[column], row[column]) if column == "source_file_id" else row[column])
                updates = ",".join(f"{column}=excluded.{column}" for column in common if column not in {key_column, "model_id", "source_file_id"})
                self.connection.execute(
                    f"INSERT INTO {table}({','.join(common)}) VALUES({','.join('?' for _ in common)}) "
                    f"ON CONFLICT({key_column}) DO UPDATE SET {updates}", values,
                )
                if existing is None:
                    added += 1
                elif existing[0] == row["content_hash"]:
                    skipped += 1
                else:
                    updated += 1
        self.connection.commit()
        source.close()
        return {"source_code": "compatible_database", "files": 1, "updated": updated, "skipped": skipped,
                "conflicts": conflicts, "records_added": added}
