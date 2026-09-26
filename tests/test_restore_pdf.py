# Copyright (c) 2026 Ivan Soprun. All rights reserved.
"""Offscreen tests for database restore and PDF report export.

Uses tempfile copies of work/build/propellers.seed.db and stubs all file
dialogs / message boxes. Never touches the production database.
"""
from __future__ import annotations

import importlib.util
import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TINY_SEED_DB = ROOT / "work" / "build" / "propellers.seed.db"

requires_qt = unittest.skipUnless(importlib.util.find_spec("PySide6") is not None, "PySide6 not installed")
requires_tiny_db = unittest.skipUnless(TINY_SEED_DB.exists(), "local tiny seed database absent")


def _ensure_app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _make_minimal_valid_db(path: Path) -> Path:
    """Build a small but genuinely valid restore candidate (schema + 1 model)."""
    from propcalc.database import initialize_database
    connection = sqlite3.connect(path)
    try:
        initialize_database(connection)
        cursor = connection.execute(
            "INSERT INTO sources(code,name,source_group,source_kind,archive_name,"
            "archive_sha256,archive_bytes) VALUES(?,?,?,?,?,?,?)",
            ("TEST_SRC", "Test source", "test", "test", "test.zip", "00" * 32, 1))
        source_id = int(cursor.lastrowid)
        connection.execute(
            "INSERT INTO source_files(source_id,relative_path,sha256,file_bytes,status)"
            " VALUES(?,?,?,?,?)",
            (source_id, "test/file.dat", "11" * 32, 1, "parsed"))
        connection.execute(
            "INSERT INTO models(model_id,original_name,diameter_m) VALUES(?,?,?)",
            ("TEST:10X5", "Test 10x5", 0.254))
        connection.commit()
    finally:
        connection.close()
    return path


@requires_qt
@requires_tiny_db
class RestoreValidationTests(unittest.TestCase):
    def test_rejects_missing_file(self) -> None:
        from propcalc.qt_app import validate_restore_candidate
        with tempfile.TemporaryDirectory() as tmp:
            ok, message = validate_restore_candidate(Path(tmp) / "nope.db")
            self.assertFalse(ok)
            self.assertTrue(message)

    def test_rejects_corrupt_bytes(self) -> None:
        from propcalc.qt_app import validate_restore_candidate
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "corrupt.db"
            bad.write_bytes(os.urandom(2048))
            ok, _ = validate_restore_candidate(bad)
            self.assertFalse(ok)

    def test_rejects_valid_sqlite_wrong_tables(self) -> None:
        from propcalc.qt_app import validate_restore_candidate
        with tempfile.TemporaryDirectory() as tmp:
            wrong = Path(tmp) / "wrong.db"
            connection = sqlite3.connect(wrong)
            connection.execute("CREATE TABLE unrelated(id INTEGER PRIMARY KEY)")
            connection.commit()
            connection.close()
            ok, message = validate_restore_candidate(wrong)
            self.assertFalse(ok)
            self.assertIn("Required tables missing", message)

    def test_rejects_empty_models(self) -> None:
        from propcalc.qt_app import validate_restore_candidate
        from propcalc.database import initialize_database
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "empty.db"
            connection = sqlite3.connect(empty)
            initialize_database(connection)
            connection.close()
            ok, message = validate_restore_candidate(empty)
            self.assertFalse(ok)
            self.assertIn("no propeller models", message.lower())

    def test_accepts_minimal_valid_db(self) -> None:
        from propcalc.qt_app import validate_restore_candidate
        with tempfile.TemporaryDirectory() as tmp:
            good = _make_minimal_valid_db(Path(tmp) / "good.db")
            ok, message = validate_restore_candidate(good)
            self.assertTrue(ok, message)

    def test_rejects_empty_schema_db(self) -> None:
        from propcalc.qt_app import validate_restore_candidate
        with tempfile.TemporaryDirectory() as tmp:
            # Schema-only file (like the empty tiny seed): tables exist but no models.
            ok, _ = validate_restore_candidate(TINY_SEED_DB)
            self.assertFalse(ok)


@requires_qt
@requires_tiny_db
class RestoreReplaceTests(unittest.TestCase):
    def _make_window(self, app, tmp: str):
        from propcalc.qt_app import PropellerMainWindow
        db_copy = Path(tmp) / "work.db"
        shutil.copy2(TINY_SEED_DB, db_copy)
        window = PropellerMainWindow(database_path=str(db_copy))
        app.processEvents()
        app.processEvents()
        return window

    @staticmethod
    def _sha(path: Path) -> str:
        import hashlib
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def test_invalid_restore_leaves_original_intact(self) -> None:
        from unittest import mock

        app = _ensure_app()
        import propcalc.qt_app as qt_app

        with tempfile.TemporaryDirectory() as tmp:
            window = self._make_window(app, tmp)
            try:
                before = self._sha(window.database_path)
                corrupt = Path(tmp) / "corrupt.db"
                corrupt.write_bytes(os.urandom(4096))
                with (
                    mock.patch.object(
                        qt_app.QFileDialog, "getOpenFileName",
                        return_value=(str(corrupt), "SQLite (*.db)")),
                    mock.patch.object(qt_app.QMessageBox, "critical") as critical,
                    mock.patch.object(qt_app.QMessageBox, "information") as info,
                ):
                    window.restore_database()
                    app.processEvents()
                self.assertTrue(critical.called, "invalid file must show an error dialog")
                self.assertFalse(info.called, "no success dialog on invalid file")
                self.assertEqual(self._sha(window.database_path), before)
                # Repository still functional on the untouched original.
                summary = window.repository.summary()
                self.assertIn("models", summary)
            finally:
                window.close()
                app.processEvents()

    def test_valid_restore_replaces_and_reopens(self) -> None:
        app = _ensure_app()

        with tempfile.TemporaryDirectory() as tmp:
            window = self._make_window(app, tmp)
            try:
                other = _make_minimal_valid_db(Path(tmp) / "other.db")
                marker = "restore-probe-marker"
                connection = sqlite3.connect(other)
                connection.execute(
                    "INSERT INTO app_settings(key,value) VALUES(?,?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    ("restore_probe", marker))
                connection.commit()
                connection.close()
                backups_before = set(window.paths["backups"].glob("*.db"))
                returned_backup = window.restore_database_from_path(other)
                app.processEvents()
                # Safety backup created in the backups dir.
                self.assertTrue(returned_backup.is_file())
                self.assertGreater(returned_backup.stat().st_size, 0)
                fresh_backups = set(window.paths["backups"].glob("*.db"))
                self.assertGreater(len(fresh_backups), len(backups_before))
                # App reopened on the restored file: marker visible, repo works.
                row = window.repository.connection.execute(
                    "SELECT value FROM app_settings WHERE key='restore_probe'").fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(row[0], marker)
                summary = window.repository.summary()
                self.assertGreater(int(summary.get("models", 0)), 0)
                window.calculate()
                app.processEvents()
            finally:
                window.close()
                app.processEvents()

    def test_same_file_restore_rejected(self) -> None:
        app = _ensure_app()

        with tempfile.TemporaryDirectory() as tmp:
            window = self._make_window(app, tmp)
            try:
                before = self._sha(window.database_path)
                with self.assertRaises(ValueError):
                    window.restore_database_from_path(window.database_path)
                self.assertEqual(self._sha(window.database_path), before)
            finally:
                window.close()
                app.processEvents()


@requires_qt
@requires_tiny_db
class PdfReportTests(unittest.TestCase):
    def _make_window(self, app, tmp: str):
        from propcalc.qt_app import PropellerMainWindow
        db_copy = Path(tmp) / "work.db"
        shutil.copy2(TINY_SEED_DB, db_copy)
        window = PropellerMainWindow(database_path=str(db_copy))
        window.show()
        app.processEvents()
        app.processEvents()
        return window

    @staticmethod
    def _assert_pdf(path: Path) -> None:
        self_size = path.stat().st_size
        assert self_size > 0, "PDF must be non-empty"
        with path.open("rb") as stream:
            header = stream.read(5)
        assert header == b"%PDF-", f"missing PDF header: {header!r}"

    def test_calc_pdf_creates_valid_file(self) -> None:
        from unittest import mock

        app = _ensure_app()
        import propcalc.qt_app as qt_app

        with tempfile.TemporaryDirectory() as tmp:
            window = self._make_window(app, tmp)
            try:
                window.calculate()
                app.processEvents()
                target = Path(tmp) / "calc.pdf"
                with (
                    mock.patch.object(
                        qt_app.QFileDialog, "getSaveFileName",
                        return_value=(str(target), "PDF (*.pdf)")),
                    mock.patch.object(qt_app.QMessageBox, "information"),
                    mock.patch.object(qt_app.QMessageBox, "critical") as critical,
                ):
                    window.export_calc_pdf_report()
                    app.processEvents()
                self.assertFalse(critical.called)
                self.assertTrue(target.is_file())
                self._assert_pdf(target)
            finally:
                window.close()
                app.processEvents()

    def test_compare_pdf_creates_valid_file(self) -> None:
        from unittest import mock

        app = _ensure_app()
        import propcalc.qt_app as qt_app

        with tempfile.TemporaryDirectory() as tmp:
            window = self._make_window(app, tmp)
            try:
                window.calculate()
                app.processEvents()
                window.add_current_to_compare()
                window.add_current_to_compare()
                app.processEvents()
                self.assertGreaterEqual(len(window.compare_items), 1)
                target = Path(tmp) / "compare.pdf"
                with (
                    mock.patch.object(
                        qt_app.QFileDialog, "getSaveFileName",
                        return_value=(str(target), "PDF (*.pdf)")),
                    mock.patch.object(qt_app.QMessageBox, "information"),
                    mock.patch.object(qt_app.QMessageBox, "critical") as critical,
                ):
                    window.export_compare_pdf_report()
                    app.processEvents()
                self.assertFalse(critical.called)
                self.assertTrue(target.is_file())
                self._assert_pdf(target)
            finally:
                window.close()
                app.processEvents()

    def test_invalid_input_state_does_not_crash_export(self) -> None:
        from unittest import mock

        app = _ensure_app()
        import propcalc.qt_app as qt_app

        with tempfile.TemporaryDirectory() as tmp:
            window = self._make_window(app, tmp)
            try:
                window.edits["voltage"].setText("abc")
                app.processEvents()
                window.calculate()  # inline error, no modal
                app.processEvents()
                target = Path(tmp) / "invalid.pdf"
                with (
                    mock.patch.object(
                        qt_app.QFileDialog, "getSaveFileName",
                        return_value=(str(target), "PDF (*.pdf)")),
                    mock.patch.object(qt_app.QMessageBox, "information"),
                    mock.patch.object(qt_app.QMessageBox, "critical"),
                ):
                    try:
                        window.export_calc_pdf_report()
                    except Exception as exc:  # noqa: BLE001
                        self.fail(f"export raised on invalid input: {exc!r}")
                    app.processEvents()
                # Fallback PDF is written even with invalid inputs; never a crash.
                self.assertTrue(target.is_file(), "fallback PDF must be written")
                self._assert_pdf(target)
                leftovers = list(Path(tmp).glob("*.writing"))
                self.assertEqual(leftovers, [], f"no partial files: {leftovers}")
            finally:
                window.close()
                app.processEvents()


@requires_qt
@requires_tiny_db
class UserExportHandlerTests(unittest.TestCase):
    """Database-tab export button writes a user-only *.pudb (never a full backup)."""

    def _make_window(self, app, tmp: str):
        from propcalc.qt_app import PropellerMainWindow
        db_copy = Path(tmp) / "work.db"
        shutil.copy2(TINY_SEED_DB, db_copy)
        connection = sqlite3.connect(db_copy)
        cursor = connection.execute("INSERT INTO motors(name) VALUES(?)", ("Handler Motor",))
        motor_id = int(cursor.lastrowid)
        connection.execute(
            "INSERT INTO saved_builds(name,motor_id,motor_kv) VALUES(?,?,?)",
            ("Handler Build", motor_id, 500.0))
        connection.commit()
        connection.close()
        window = PropellerMainWindow(database_path=str(db_copy))
        app.processEvents()
        app.processEvents()
        return window

    def test_export_db_writes_user_only_pudb(self) -> None:
        from unittest import mock

        app = _ensure_app()
        import propcalc.qt_app as qt_app

        with tempfile.TemporaryDirectory() as tmp:
            window = self._make_window(app, tmp)
            try:
                target = Path(tmp) / "userdata"  # no extension: handler must append .pudb
                with (
                    mock.patch.object(
                        qt_app.QFileDialog, "getSaveFileName",
                        return_value=(str(target), "Propeller user data (*.pudb)")),
                    mock.patch.object(qt_app.QMessageBox, "information"),
                    mock.patch.object(qt_app.QMessageBox, "critical") as critical,
                ):
                    window.export_db()
                    app.processEvents()
                self.assertFalse(critical.called)
                written = Path(str(target) + ".pudb")
                self.assertTrue(written.is_file())
                connection = sqlite3.connect(written)
                try:
                    tables = {row[0] for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'")}
                    self.assertNotIn("models", tables)
                    self.assertNotIn("performance_points", tables)
                    manifest = {row[0]: row[1] for row in connection.execute(
                        "SELECT key,value FROM export_manifest")}
                    self.assertEqual(manifest.get("format"), "propcalc-user-data/1")
                    self.assertEqual(
                        connection.execute("SELECT COUNT(*) FROM saved_builds").fetchone()[0], 1)
                finally:
                    connection.close()
            finally:
                window.close()
                app.processEvents()


if __name__ == "__main__":
    unittest.main(verbosity=2)
