# Copyright (c) 2026 Ivan Soprun. All rights reserved.
"""Offscreen tests for the user-only export (*.pudb) and its runtime import.

Uses temp databases only; never touches the production database or network.
"""
from __future__ import annotations

import importlib.util
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path


requires_qt = unittest.skipUnless(importlib.util.find_spec("PySide6") is not None, "PySide6 not installed")


def _ensure_app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _make_vendor_db(path: Path, *, model_id: str = "APC:10X5") -> Path:
    """Minimal working database: 1 vendor model + point, 1 motor/battery/frame/build."""
    from propcalc.database import initialize_database
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        initialize_database(connection)
        cursor = connection.execute(
            "INSERT INTO sources(code,name,source_group,source_kind,archive_name,"
            "archive_sha256,archive_bytes) VALUES(?,?,?,?,?,?,?)",
            ("TEST_SRC", "Test source", "test", "test", "test.zip", "00" * 32, 1))
        source_id = int(cursor.lastrowid)
        cursor = connection.execute(
            "INSERT INTO source_files(source_id,relative_path,sha256,file_bytes,status)"
            " VALUES(?,?,?,?,?)",
            (source_id, "test/file.dat", "11" * 32, 1, "parsed"))
        file_id = int(cursor.lastrowid)
        connection.execute(
            "INSERT INTO models(model_id,original_name,diameter_m) VALUES(?,?,?)",
            (model_id, "Test 10x5", 0.254))
        connection.execute(
            "INSERT INTO performance_points(point_key,model_id,original_name,medium,"
            "is_static,source_type,evidence_class,source_file_id,content_hash)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            ("TEST-PT-1", model_id, "Test 10x5", "air", 1, "test", "experiment", file_id, "22" * 32))
        cursor = connection.execute(
            "INSERT INTO motors(name,manufacturer,kv_rpm_per_v) VALUES(?,?,?)",
            ("Test Motor", "TestCo", 500.0))
        motor_id = int(cursor.lastrowid)
        cursor = connection.execute(
            "INSERT INTO batteries(name,chemistry,cells_s,capacity_ah) VALUES(?,?,?,?)",
            ("Test Pack", "LiPo", 4, 5.0))
        battery_id = int(cursor.lastrowid)
        cursor = connection.execute(
            "INSERT INTO frames(name,geometry,diagonal_m) VALUES(?,?,?)",
            ("Test Frame", "X", 0.45))
        frame_id = int(cursor.lastrowid)
        cursor = connection.execute(
            "INSERT INTO saved_builds(name,propeller_model_id,motor_id,battery_id,frame_id,"
            "motor_kv,battery_s) VALUES(?,?,?,?,?,?,?)",
            ("Test Build", model_id, motor_id, battery_id, frame_id, 500.0, 4))
        build_id = int(cursor.lastrowid)
        connection.execute(
            "INSERT INTO saved_build_components(build_id,component_type,component_ref,quantity)"
            " VALUES(?,?,?,?)",
            (build_id, "gps", "Test GPS", 1))
        connection.commit()
    finally:
        connection.close()
    return path


def _tables(path: Path) -> set[str]:
    connection = sqlite3.connect(path)
    try:
        return {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        connection.close()


def _count(path: Path, table: str) -> int:
    connection = sqlite3.connect(path)
    try:
        return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    finally:
        connection.close()


class UserExportTests(unittest.TestCase):
    def test_user_export_has_zero_vendor_rows(self) -> None:
        from propcalc.appdata import USER_EXPORT_FORMAT, export_user_data
        from propcalc.config import APP_VERSION
        from propcalc.database import connect_database
        with tempfile.TemporaryDirectory() as tmp:
            source = _make_vendor_db(Path(tmp) / "work.db")
            connection = connect_database(source)
            try:
                target = Path(tmp) / "userdata.pudb"
                manifest = export_user_data(connection, target, source_sha256="AB" * 32)
            finally:
                connection.close()
            tables = _tables(target)
            self.assertNotIn("models", tables)
            self.assertNotIn("performance_points", tables)
            self.assertNotIn("sources", tables)
            for table in ("motors", "batteries", "frames", "saved_builds",
                          "saved_build_components", "export_manifest"):
                self.assertIn(table, tables)
                self.assertGreater(_count(target, table), 0)
            self.assertEqual(manifest["format"], USER_EXPORT_FORMAT)
            self.assertEqual(manifest["app_version"], APP_VERSION)
            self.assertEqual(manifest["source_db_sha256"], "AB" * 32)
            self.assertEqual(manifest["rows_saved_builds"], "1")
            self.assertTrue(target.stat().st_size < source.stat().st_size)

    def test_full_safety_backup_still_full(self) -> None:
        from propcalc.database import connect_database
        with tempfile.TemporaryDirectory() as tmp:
            source = _make_vendor_db(Path(tmp) / "work.db")
            connection = connect_database(source)
            try:
                backup = Path(tmp) / "safety.db"
                destination = sqlite3.connect(backup)
                try:
                    connection.backup(destination)
                finally:
                    destination.close()
            finally:
                connection.close()
            self.assertEqual(_count(backup, "models"), 1)
            self.assertEqual(_count(backup, "performance_points"), 1)
            self.assertEqual(_count(backup, "saved_builds"), 1)


class UserImportTests(unittest.TestCase):
    def _service(self, tmp: str, *, with_model: bool):
        from propcalc.database import connect_database, initialize_database
        from propcalc.runtime_import import RuntimeImportService
        target = Path(tmp) / "target.db"
        connection = connect_database(target)
        initialize_database(connection)
        if with_model:
            connection.execute(
                "INSERT INTO models(model_id,original_name,diameter_m) VALUES(?,?,?)",
                ("APC:10X5", "Test 10x5", 0.254))
            connection.commit()
        service = RuntimeImportService(connection, target, Path(tmp) / "backups")
        return service, connection

    def _export(self, tmp: str) -> Path:
        from propcalc.appdata import export_user_data
        from propcalc.database import connect_database
        source = _make_vendor_db(Path(tmp) / "work.db")
        connection = connect_database(source)
        try:
            target = Path(tmp) / "userdata.pudb"
            export_user_data(connection, target)
        finally:
            connection.close()
        return target

    def test_import_merges_builds_and_motors(self) -> None:
        service, connection = self._service(tempfile.mkdtemp(), with_model=True)
        with tempfile.TemporaryDirectory() as tmp:
            pudb = self._export(tmp)
            report = service.import_path(pudb)
        try:
            self.assertEqual(report["source_code"], "user_data")
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM saved_builds").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM motors").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM batteries").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM frames").fetchone()[0], 1)
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM saved_build_components").fetchone()[0], 1)
            # Vendor corpus untouched: still exactly the pre-existing model, no points added.
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM models").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM performance_points").fetchone()[0], 0)
            build = connection.execute("SELECT * FROM saved_builds").fetchone()
            self.assertEqual(build["propeller_model_id"], "APC:10X5")
            self.assertEqual(report.get("model_warnings"), [])
        finally:
            connection.close()

    def test_import_warns_on_dangling_model_ref(self) -> None:
        service, connection = self._service(tempfile.mkdtemp(), with_model=False)
        with tempfile.TemporaryDirectory() as tmp:
            pudb = self._export(tmp)
            report = service.import_path(pudb)
        try:
            self.assertIn("APC:10X5", report.get("model_warnings", []))
            self.assertTrue(report.get("warnings"))
            build = connection.execute("SELECT * FROM saved_builds").fetchone()
            self.assertIsNotNone(build)
            self.assertIsNone(build["propeller_model_id"])
        finally:
            connection.close()

    def test_vendor_tables_never_merged_from_user_file(self) -> None:
        service, connection = self._service(tempfile.mkdtemp(), with_model=True)
        with tempfile.TemporaryDirectory() as tmp:
            pudb = self._export(tmp)
            planted = sqlite3.connect(pudb)
            try:
                planted.execute(
                    "CREATE TABLE models(model_id TEXT PRIMARY KEY,original_name TEXT NOT NULL)")
                planted.execute(
                    "INSERT INTO models(model_id,original_name) VALUES(?,?)",
                    ("EVIL:1X1", "Planted vendor row"))
                planted.commit()
            finally:
                planted.close()
            service.import_path(pudb)
        try:
            row = connection.execute(
                "SELECT * FROM models WHERE model_id='EVIL:1X1'").fetchone()
            self.assertIsNone(row)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM models").fetchone()[0], 1)
        finally:
            connection.close()

    def test_corrupt_user_file_rejected(self) -> None:
        service, connection = self._service(tempfile.mkdtemp(), with_model=True)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                bad = Path(tmp) / "corrupt.pudb"
                bad.write_bytes(os.urandom(4096))
                with self.assertRaises(Exception):
                    service.import_path(bad)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM saved_builds").fetchone()[0], 0)
        finally:
            connection.close()

    def test_full_db_still_uses_vendor_merge_path(self) -> None:
        from propcalc.database import connect_database
        service, connection = self._service(tempfile.mkdtemp(), with_model=False)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                full = _make_vendor_db(Path(tmp) / "full.db")
                report = service.import_path(full)
            self.assertEqual(report["source_code"], "compatible_database")
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM models").fetchone()[0], 1)
        finally:
            connection.close()


@requires_qt
class AboutCopyrightTests(unittest.TestCase):
    def test_about_contains_copyright(self) -> None:
        app = _ensure_app()
        from PySide6.QtWidgets import QLabel
        from propcalc.qt_app import PropellerMainWindow
        with tempfile.TemporaryDirectory() as tmp:
            _make_vendor_db(Path(tmp) / "work.db")
            window = PropellerMainWindow(database_path=str(Path(tmp) / "work.db"))
            try:
                app.processEvents()
                texts = [label.text() for label in window.findChildren(QLabel)]
                self.assertTrue(
                    any("© 2026 Ivan Soprun" in text for text in texts),
                    "About tab must contain the © 2026 Ivan Soprun line")
            finally:
                window.close()
                app.processEvents()


if __name__ == "__main__":
    unittest.main(verbosity=2)
