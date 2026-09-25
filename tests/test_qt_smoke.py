"""Offscreen Qt smoke: main window builds with 8 tabs even on an empty seed DB.

Skipped when PySide6 is unavailable or the local seed database is absent
(e.g. fresh clone without the private release database).
"""
from __future__ import annotations

import importlib.util
import os
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SEED_DB = ROOT / "work" / "build" / "propellers.db"
TINY_SEED_DB = ROOT / "work" / "build" / "propellers.seed.db"

requires_qt = unittest.skipUnless(importlib.util.find_spec("PySide6") is not None, "PySide6 not installed")
requires_db = unittest.skipUnless(SEED_DB.exists(), "local seed database absent")
requires_tiny_db = unittest.skipUnless(TINY_SEED_DB.exists(), "local tiny seed database absent")


@requires_qt
@requires_db
class QtSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        cls._app = QApplication.instance() or QApplication([])
        from propcalc.qt_app import PropellerMainWindow
        cls.window = PropellerMainWindow(database_path=str(SEED_DB))
        cls._app.processEvents()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.window.close()

    def test_main_window_has_8_tabs(self) -> None:
        self.assertEqual(self.window.tabs.count(), 8)

    def test_window_title(self) -> None:
        self.assertIn("Propeller Calculator", self.window.windowTitle())


@requires_qt
@requires_tiny_db
class QtLanguageRebuildTests(unittest.TestCase):
    """Language switches must dispose the previous UI tree.

    Regression test for the hidden-tree leak in PropellerMainWindow._build_ui:
    before the fix, setCentralWidget() replaced the central widget without
    deleting the old one, so each _switch_language/_build_ui left the old tree
    as hidden-but-alive children and the primary-button count found via
    findChildren grew 6 -> 12 -> 18 across two switches (Agent E2 probe).
    After the fix (takeCentralWidget + deleteLater of the old central widget)
    the count must stay stable.

    Uses a tempfile copy of work/build/propellers.seed.db, never the
    production database.
    """

    def test_language_switch_twice_keeps_primary_button_count_stable(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication, QPushButton

        app = QApplication.instance() or QApplication([])
        from propcalc.qt_app import PropellerMainWindow

        with tempfile.TemporaryDirectory() as tmp:
            db_copy = Path(tmp) / "propellers.seed.db"
            shutil.copy2(TINY_SEED_DB, db_copy)
            window = PropellerMainWindow(database_path=str(db_copy))
            try:
                app.processEvents()

                def primary_count() -> int:
                    return sum(
                        1 for b in window.findChildren(QPushButton) if b.objectName() == "primary"
                    )

                initial = primary_count()
                self.assertGreater(initial, 0)
                start_language = window.language
                other = "en" if start_language == "uk" else "uk"
                window._switch_language(other)
                app.processEvents()
                after_first = primary_count()
                window._switch_language(start_language)
                app.processEvents()
                after_second = primary_count()
                self.assertEqual(after_first, initial)
                self.assertEqual(after_second, initial)
                self.assertEqual(window.tabs.count(), 8)
                self.assertEqual(window.language, start_language)
            finally:
                window.close()
                app.processEvents()


if __name__ == "__main__":
    unittest.main(verbosity=2)


@requires_qt
@requires_tiny_db
class QtWarningLocalizationTests(unittest.TestCase):
    """UA mode must localize every engine warning exemplar (no raw English leaks).

    Uses a tempfile copy of work/build/propellers.seed.db, never the
    production database.
    """

    WARNING_EXEMPLARS = [
        # S3 family: parameterized non-finite inputs (all 12 calculator names).
        "Non-finite input mass_kg; result is not meaningful",
        "Non-finite input density_kg_m3; result is not meaningful",
        "Non-finite input voltage_v; result is not meaningful",
        "Non-finite input throttle; result is not meaningful",
        "Non-finite input motor_kv; result is not meaningful",
        "Non-finite input battery_capacity_ah; result is not meaningful",
        "Non-finite input battery_c_rating; result is not meaningful",
        "Non-finite input esc_current_a; result is not meaningful",
        "Non-finite input speed_m_s; result is not meaningful",
        "Non-finite input motor_resistance_ohm; result is not meaningful",
        "Non-finite input motor_max_current_a; result is not meaningful",
        "Non-finite input motor_max_power_w; result is not meaningful",
        # S3 family: fixed guard warnings.
        "Non-positive mass_kg; T/W uses a guarded minimum and is not meaningful",
        "Non-positive density_kg_m3; thrust/power scale with density and are not meaningful",
        "Negative battery capacity/C-rating; runtime and margins are not meaningful",
        "Negative motor_resistance_ohm; result is not meaningful",
        "Negative motor_max_current_a; margin is not meaningful",
        "Negative motor_max_power_w; margin is not meaningful",
        "Non-positive motor_count treated as 1",
        # Remaining calculator warnings.
        "Simplified-model estimate: missing Rm / motor winding resistance, I0 / no-load current",
        "Operating point is outside a measured/predicted table range; nearest-edge extrapolation used",
        "ESC current limit exceeded",
        "Battery C-rating current limit exceeded",
        "Structural RPM limit exceeded",
        "Battery voltage mismatch: 22.20 V entered, but 6S LiPo is about 22.20 V nominal",
        "Water mode uses air-derived dimensionless coefficients; cavitation is not modeled and bench validation is mandatory",
    ]

    def test_ua_warnings_localized_no_english_leak(self) -> None:
        import re

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance() or QApplication([])
        from propcalc.qt_app import PropellerMainWindow

        with tempfile.TemporaryDirectory() as tmp:
            db_copy = Path(tmp) / "propellers.seed.db"
            shutil.copy2(TINY_SEED_DB, db_copy)
            window = PropellerMainWindow(database_path=str(db_copy))
            try:
                app.processEvents()
                if window.language != "uk":
                    window._switch_language("uk")
                    app.processEvents()
                cyrillic = re.compile(r"[\u0400-\u04FF]")
                snake = re.compile(r"[A-Za-z]+_[A-Za-z0-9_]+")
                for exemplar in self.WARNING_EXEMPLARS:
                    localized = window._localize_warning(exemplar)
                    self.assertTrue(
                        cyrillic.search(localized),
                        f"no Cyrillic in localized warning for {exemplar!r}: {localized!r}",
                    )
                    self.assertIsNone(
                        snake.search(localized),
                        f"snake_case English leak for {exemplar!r}: {localized!r}",
                    )
            finally:
                window.close()
                app.processEvents()

    def test_en_warnings_passthrough_intact(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance() or QApplication([])
        from propcalc.qt_app import PropellerMainWindow

        with tempfile.TemporaryDirectory() as tmp:
            db_copy = Path(tmp) / "propellers.seed.db"
            shutil.copy2(TINY_SEED_DB, db_copy)
            window = PropellerMainWindow(database_path=str(db_copy))
            try:
                app.processEvents()
                start_language = window.language
                if start_language != "en":
                    window._switch_language("en")
                    app.processEvents()
                for exemplar in self.WARNING_EXEMPLARS:
                    self.assertEqual(window._localize_warning(exemplar), exemplar)
                if start_language != "en":
                    window._switch_language(start_language)
                    app.processEvents()
            finally:
                window.close()
                app.processEvents()


@requires_qt
@requires_tiny_db
class QtCompareNaNRankingTests(unittest.TestCase):
    """A NaN-runtime entry must never outrank a valid one under maximum time.

    Regression: the compare key was ``item.get(...) or -1e9``; NaN is truthy,
    so a meaningless entry kept a NaN key and ranked #1 under "maximum time"
    (descending) for some insertion orders. The key now normalizes None and
    NaN to -1e9 via PropellerMainWindow._compare_sort_value.

    Uses a tempfile copy of work/build/propellers.seed.db, never the
    production database.
    """

    @staticmethod
    def _item(label: str, runtime: float) -> dict:
        return {"label": label, "thrust": 10.0, "current": 5.0, "power": 70.0,
                "torque": 0.05, "efficiency": 0.5, "aero": 0.6,
                "max_efficiency": 0.55, "recommended_voltage": 14.8,
                "tw": 1.2, "runtime": runtime, "voltage": 14.8,
                "rpm_margin": 10.0, "esc_margin": 20.0, "motor_margin": 15.0,
                "battery_margin": 25.0, "confidence": 0.9,
                "source": "test", "warnings": "", "mass": 1.5}

    def test_nan_runtime_never_first_under_maximum_time(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance() or QApplication([])
        from propcalc.qt_app import PropellerMainWindow

        self.assertEqual(PropellerMainWindow._compare_sort_value(float("nan")), -1e9)
        self.assertEqual(PropellerMainWindow._compare_sort_value(None), -1e9)
        self.assertEqual(PropellerMainWindow._compare_sort_value(36.4), 36.4)
        with tempfile.TemporaryDirectory() as tmp:
            db_copy = Path(tmp) / "propellers.seed.db"
            shutil.copy2(TINY_SEED_DB, db_copy)
            window = PropellerMainWindow(database_path=str(db_copy))
            try:
                app.processEvents()
                combo = window.combos.get("compare_criterion")
                self.assertIsNotNone(combo)
                assert combo is not None
                combo.setCurrentIndex(combo.findData("maximum time"))
                app.processEvents()
                orders = (
                    [self._item("broken", float("nan")), self._item("valid", 36.4)],
                    [self._item("valid", 36.4), self._item("broken", float("nan"))],
                )
                for order in orders:
                    with self.subTest(order=[item["label"] for item in order]):
                        window.compare_items = list(order)
                        window._refresh_compare()
                        app.processEvents()
                        self.assertEqual(window.compare_table.item(0, 1).text(), "valid")
            finally:
                window.close()
                app.processEvents()


@requires_qt
@requires_tiny_db
class QtAccessibilityNamingTests(unittest.TestCase):
    """Frame inputs and tables must carry programmatic names.

    Regression: the 5 Frame-tab QLineEdits had no tip key (empty tooltip /
    accessibleDescription) and all 8 QTables had empty accessibleName /
    objectName, so assistive tools could not identify them.

    Uses a tempfile copy of work/build/propellers.seed.db, never the
    production database.
    """

    FRAME_TIP_KEYS = {
        "frame_motors": "motors",
        "arm_width": "arm_width",
        "arm_thickness": "arm_thickness",
        "frame_mass": "frame_mass",
        "payload": "build_payload",
    }

    def test_frame_inputs_have_tips_and_tables_have_names(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication, QTableWidget

        app = QApplication.instance() or QApplication([])
        from propcalc.qt_app import PropellerMainWindow

        with tempfile.TemporaryDirectory() as tmp:
            db_copy = Path(tmp) / "propellers.seed.db"
            shutil.copy2(TINY_SEED_DB, db_copy)
            window = PropellerMainWindow(database_path=str(db_copy))
            try:
                app.processEvents()
                window.tooltips_enabled = True
                window._apply_tooltips()
                app.processEvents()
                for key, tip in self.FRAME_TIP_KEYS.items():
                    with self.subTest(field=key):
                        widget = window.edits[key]
                        self.assertEqual(window.tip_keys.get(id(widget)), tip)
                        self.assertTrue(widget.toolTip(), f"{key} tooltip empty")
                        self.assertTrue(
                            widget.accessibleDescription(),
                            f"{key} accessibleDescription empty",
                        )
                tables = window.findChildren(QTableWidget)
                self.assertEqual(len(tables), 8)
                for table in tables:
                    with self.subTest(table=table.objectName() or "<unnamed>"):
                        self.assertTrue(table.accessibleName(), "table accessibleName empty")
                        self.assertTrue(table.objectName(), "table objectName empty")
                names = sorted(table.objectName() for table in tables)
                self.assertEqual(len(set(names)), 8, f"objectNames not unique: {names}")
            finally:
                window.close()
                app.processEvents()


@requires_qt
@requires_tiny_db
class QtCalcInputErrorTests(unittest.TestCase):
    """Invalid calculator text must show an inline error, not a modal.

    Regression: plain QLineEdits with float() in _inputs raised into a modal
    critical only (no focus move, no highlight, stale result stays). The fix
    collects per-field parse failures and shows them inline in a persistent
    error label, highlights the first bad field and moves focus to it, with
    no exception escaping calculate() and no invalid result stored.

    Uses a tempfile copy of work/build/propellers.seed.db, never the
    production database.
    """

    def _make_window(self, app, tmp: str):
        from propcalc.qt_app import PropellerMainWindow

        db_copy = Path(tmp) / "propellers.seed.db"
        shutil.copy2(TINY_SEED_DB, db_copy)
        window = PropellerMainWindow(database_path=str(db_copy))
        window.show()
        app.processEvents()
        app.processEvents()
        return window

    def test_invalid_voltage_inline_error_both_modes(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance() or QApplication([])
        from propcalc.qt_app import PropellerMainWindow  # noqa: F401

        with tempfile.TemporaryDirectory() as tmp:
            window = self._make_window(app, tmp)
            try:
                # Sanity: both calculator modes share the single calculate slot.
                self.assertEqual(window.calculator_modes.count(), 2)
                for mode_index in (0, 1):
                    with self.subTest(mode=mode_index):
                        window.calculator_modes.setCurrentIndex(mode_index)
                        app.processEvents()
                        # Valid control first: calculates with no inline error.
                        window.edits["voltage"].setText("14.8")
                        app.processEvents()
                        window.calculate()
                        app.processEvents()
                        self.assertTrue(window.calc_error_label.isHidden())
                        self.assertIsNotNone(window.current_result)
                        prior_result = window.current_result
                        # Invalid: real calculate slot must not raise (no modal).
                        window.edits["voltage"].setText("abc")
                        app.processEvents()
                        try:
                            window.calculate()
                        except Exception as exc:  # noqa: BLE001
                            self.fail(f"calculate() raised on invalid input: {exc!r}")
                        app.processEvents()
                        label = window.calc_error_label
                        self.assertFalse(label.isHidden(), "error label must be shown")
                        self.assertTrue(label.text(), "error label text empty")
                        self.assertIn("voltage", label.text().lower())
                        bad = window.edits["voltage"]
                        self.assertIn("E5484D", bad.styleSheet())
                        self.assertIs(window.focusWidget(), bad)
                        # No invalid result stored; prior valid result retained.
                        self.assertIs(window.current_result, prior_result)
                        # Valid control again: error clears and calculation resumes.
                        window.edits["voltage"].setText("14.8")
                        app.processEvents()
                        window.calculate()
                        app.processEvents()
                        self.assertTrue(window.calc_error_label.isHidden())
                        self.assertEqual(window.edits["voltage"].styleSheet(), "")
            finally:
                window.close()
                app.processEvents()

    def test_invalid_input_update_build_no_raise_user_informed(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from unittest import mock

        from PySide6.QtWidgets import QApplication

        app = QApplication.instance() or QApplication([])
        import propcalc.qt_app as qt_app

        with tempfile.TemporaryDirectory() as tmp:
            window = self._make_window(app, tmp)
            try:
                with (
                    mock.patch.object(qt_app.QMessageBox, "critical") as critical,
                    mock.patch.object(window.repository, "save_build") as save,
                ):
                    # Bypass save (tiny seed DB rejects the FK) and force the
                    # update path: any non-None id reaches _payload().
                    window.current_build_id = 1
                    window.edits["voltage"].setText("abc")
                    app.processEvents()
                    try:
                        window.update_build()
                    except Exception as exc:  # noqa: BLE001
                        self.fail(f"update_build() raised on invalid input: {exc!r}")
                    app.processEvents()
                    save.assert_not_called()
                    informed_inline = (
                        not window.calc_error_label.isHidden()
                        and bool(window.calc_error_label.text())
                    )
                    self.assertTrue(
                        informed_inline or critical.called,
                        "user must be informed via inline label or modal",
                    )
            finally:
                window.close()
                app.processEvents()

    def test_invalid_input_export_build_no_raise_no_file(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from unittest import mock

        from PySide6.QtWidgets import QApplication

        app = QApplication.instance() or QApplication([])
        import propcalc.qt_app as qt_app

        with tempfile.TemporaryDirectory() as tmp:
            window = self._make_window(app, tmp)
            try:
                target = Path(tmp) / "build.json"
                window.edits["voltage"].setText("abc")
                app.processEvents()
                with (
                    mock.patch.object(
                        qt_app.QFileDialog,
                        "getSaveFileName",
                        return_value=(str(target), "JSON (*.json)"),
                    ),
                    mock.patch.object(qt_app.QMessageBox, "critical") as critical,
                ):
                    try:
                        window.export_build()
                    except Exception as exc:  # noqa: BLE001
                        self.fail(f"export_build() raised on invalid input: {exc!r}")
                    app.processEvents()
                    self.assertFalse(target.exists(), "no file must be written")
                    informed_inline = (
                        not window.calc_error_label.isHidden()
                        and bool(window.calc_error_label.text())
                    )
                    self.assertTrue(
                        informed_inline or critical.called,
                        "user must be informed via inline label or modal",
                    )
            finally:
                window.close()
                app.processEvents()


@requires_qt
@requires_tiny_db
class QtBusyConfirmTests(unittest.TestCase):
    """T044/P010: busy cursor around import/export/restore + safe confirm gates.

    All dialogs are stubbed (file dialogs + _confirm/information/critical);
    never touches the production database (tempfile copies of the tiny seed).
    """

    def _make_window(self, app, tmp: str, name: str = "work.db"):
        from propcalc.qt_app import PropellerMainWindow

        db_copy = Path(tmp) / name
        shutil.copy2(TINY_SEED_DB, db_copy)
        window = PropellerMainWindow(database_path=str(db_copy))
        app.processEvents()
        app.processEvents()
        return window

    @staticmethod
    def _make_minimal_valid_db(path: Path) -> Path:
        import sqlite3

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

    @staticmethod
    def _make_user_pudb(path: Path) -> Path:
        """Export a valid .pudb (with one motor + build) for import tests."""
        import sqlite3

        from propcalc.appdata import export_user_data, file_sha

        src = path.parent / "src.db"
        shutil.copy2(TINY_SEED_DB, src)
        connection = sqlite3.connect(src)
        connection.row_factory = sqlite3.Row
        try:
            cursor = connection.execute("INSERT INTO motors(name) VALUES(?)", ("Import Motor",))
            motor_id = int(cursor.lastrowid)
            connection.execute(
                "INSERT INTO saved_builds(name,motor_id,motor_kv) VALUES(?,?,?)",
                ("Import Build", motor_id, 500.0))
            connection.commit()
            source_sha = file_sha(src)
            export_user_data(connection, path, source_sha256=source_sha)
        finally:
            connection.close()
        try:
            src.unlink()  # only the .pudb is needed; drop the staging file early
        except OSError:
            pass
        return path

    def _save_one_build(self, app, window):
        """Create one saved build via the real slot; returns its build_id."""
        from unittest import mock

        import propcalc.qt_app as qt_app

        # The tiny seed is schema-only (no models) and saved_builds has a
        # models FK: insert one model row first, then save via the real slot.
        import sqlite3

        seed = sqlite3.connect(window.database_path)
        try:
            seed.execute(
                "INSERT OR IGNORE INTO models(model_id,original_name,diameter_m)"
                " VALUES(?,?,?)",
                ("TEST:10X5", "Test 10x5", 0.254))
            seed.commit()
        finally:
            seed.close()
        window.repository.clear_caches()
        window.selected_model_id = "TEST:10X5"
        with (
            mock.patch.object(qt_app.QMessageBox, "critical") as critical,
            mock.patch.object(qt_app.QMessageBox, "information"),
        ):
            window.save_build_new()
            app.processEvents()
        self.assertFalse(critical.called)
        self.assertIsNotNone(window.current_build_id)
        assert window.current_build_id is not None
        return window.current_build_id

    def test_confirm_box_defaults_to_safe_no(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication, QMessageBox

        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as tmp:
            window = self._make_window(app, tmp)
            try:
                box = window._confirm_box("probe")
                buttons = box.standardButtons()
                self.assertTrue(buttons & QMessageBox.StandardButton.Yes)
                self.assertTrue(buttons & QMessageBox.StandardButton.No)
                no_button = box.button(QMessageBox.StandardButton.No)
                self.assertIsNotNone(no_button)
                self.assertEqual(box.defaultButton(), no_button)
                self.assertEqual(box.escapeButton(), no_button)
            finally:
                window.close()
                app.processEvents()

    def test_localization_keys_present_both_languages(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as tmp:
            window = self._make_window(app, tmp)
            try:
                for language in ("uk", "en"):
                    with self.subTest(language=language):
                        window.language = language
                        for key in ("busy_working", "confirm_restore", "confirm_restore_info",
                                    "confirm_import", "confirm_import_info",
                                    "confirm_update", "confirm_close"):
                            text = window.tr(key)
                            self.assertNotEqual(text, key, f"missing {key} for {language}")
                            self.assertTrue(text.strip(), f"empty {key} for {language}")
            finally:
                window.close()
                app.processEvents()

    def test_export_busy_cursor_restored(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from unittest import mock

        from PySide6.QtWidgets import QApplication

        app = QApplication.instance() or QApplication([])
        import propcalc.qt_app as qt_app

        with tempfile.TemporaryDirectory() as tmp:
            window = self._make_window(app, tmp)
            try:
                target = Path(tmp) / "userdata"  # no extension: handler appends .pudb
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
                self.assertTrue(Path(str(target) + ".pudb").is_file())
                self.assertIsNone(QApplication.overrideCursor())
                self.assertNotIn(window.tr("busy_working"), window.statusBar().currentMessage())
            finally:
                window.close()
                app.processEvents()

    def test_import_confirm_no_aborts_with_zero_change(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from unittest import mock

        from PySide6.QtWidgets import QApplication

        app = QApplication.instance() or QApplication([])
        import propcalc.qt_app as qt_app

        with tempfile.TemporaryDirectory() as tmp:
            window = self._make_window(app, tmp)
            try:
                import hashlib

                before = hashlib.sha256(window.database_path.read_bytes()).hexdigest()
                builds_before = len(window.repository.builds())
                backups_before = set(window.paths["backups"].glob("*"))
                with (
                    mock.patch.object(
                        qt_app.QFileDialog, "getOpenFileName",
                        return_value=(str(Path(tmp) / "whatever.pudb"),
                                      "Propeller user data (*.pudb)")),
                    mock.patch.object(window, "_confirm", return_value=False) as confirm,
                    mock.patch.object(qt_app.QMessageBox, "information") as info,
                    mock.patch.object(qt_app.QMessageBox, "critical") as critical,
                ):
                    window.import_data()
                    app.processEvents()
                self.assertEqual(confirm.call_count, 1)
                self.assertFalse(info.called)
                self.assertFalse(critical.called)
                self.assertEqual(len(window.repository.builds()), builds_before)
                self.assertEqual(
                    hashlib.sha256(window.database_path.read_bytes()).hexdigest(), before)
                self.assertEqual(set(window.paths["backups"].glob("*")), backups_before)
                self.assertIsNone(QApplication.overrideCursor())
            finally:
                window.close()
                app.processEvents()

    def test_import_confirm_yes_proceeds_busy_restored(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from unittest import mock

        from PySide6.QtWidgets import QApplication

        app = QApplication.instance() or QApplication([])
        import propcalc.qt_app as qt_app

        with tempfile.TemporaryDirectory() as tmp:
            window = self._make_window(app, tmp)
            try:
                pudb = self._make_user_pudb(Path(tmp) / "user.pudb")
                builds_before = len(window.repository.builds())
                with (
                    mock.patch.object(
                        qt_app.QFileDialog, "getOpenFileName",
                        return_value=(str(pudb), "Propeller user data (*.pudb)")),
                    mock.patch.object(window, "_confirm", return_value=True) as confirm,
                    mock.patch.object(qt_app.QMessageBox, "information") as info,
                    mock.patch.object(qt_app.QMessageBox, "critical") as critical,
                ):
                    window.import_data()
                    app.processEvents()
                self.assertEqual(confirm.call_count, 1)
                self.assertFalse(critical.called)
                self.assertTrue(info.called)
                names = [row["name"] for row in window.repository.builds()]
                self.assertIn("Import Build", names)
                self.assertGreater(len(names), builds_before)
                self.assertIsNone(QApplication.overrideCursor())
                self.assertNotIn(window.tr("busy_working"), window.statusBar().currentMessage())
            finally:
                window.close()
                app.processEvents()

    def test_restore_confirm_no_aborts_with_zero_change(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from unittest import mock

        from PySide6.QtWidgets import QApplication

        app = QApplication.instance() or QApplication([])
        import propcalc.qt_app as qt_app

        with tempfile.TemporaryDirectory() as tmp:
            window = self._make_window(app, tmp)
            try:
                import hashlib

                candidate = self._make_minimal_valid_db(Path(tmp) / "candidate.db")
                before = hashlib.sha256(window.database_path.read_bytes()).hexdigest()
                backups_before = set(window.paths["backups"].glob("*.db"))
                with (
                    mock.patch.object(
                        qt_app.QFileDialog, "getOpenFileName",
                        return_value=(str(candidate), "SQLite (*.db)")),
                    mock.patch.object(window, "_confirm", return_value=False) as confirm,
                    mock.patch.object(qt_app.QMessageBox, "information") as info,
                    mock.patch.object(qt_app.QMessageBox, "critical") as critical,
                ):
                    window.restore_database()
                    app.processEvents()
                self.assertEqual(confirm.call_count, 1)
                self.assertFalse(info.called)
                self.assertFalse(critical.called)
                self.assertEqual(
                    hashlib.sha256(window.database_path.read_bytes()).hexdigest(), before)
                self.assertEqual(set(window.paths["backups"].glob("*.db")), backups_before)
                self.assertIsNone(QApplication.overrideCursor())
                # Repository still functional on the untouched original.
                self.assertIn("models", window.repository.summary())
            finally:
                window.close()
                app.processEvents()

    def test_restore_confirm_yes_proceeds_busy_restored(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from unittest import mock

        from PySide6.QtWidgets import QApplication

        app = QApplication.instance() or QApplication([])
        import propcalc.qt_app as qt_app

        with tempfile.TemporaryDirectory() as tmp:
            window = self._make_window(app, tmp)
            try:
                candidate = self._make_minimal_valid_db(Path(tmp) / "candidate.db")
                backups_before = set(window.paths["backups"].glob("*.db"))
                with (
                    mock.patch.object(
                        qt_app.QFileDialog, "getOpenFileName",
                        return_value=(str(candidate), "SQLite (*.db)")),
                    mock.patch.object(window, "_confirm", return_value=True) as confirm,
                    mock.patch.object(qt_app.QMessageBox, "information") as info,
                    mock.patch.object(qt_app.QMessageBox, "critical") as critical,
                ):
                    window.restore_database()
                    app.processEvents()
                self.assertEqual(confirm.call_count, 1)
                self.assertFalse(critical.called)
                self.assertTrue(info.called)
                fresh_backups = set(window.paths["backups"].glob("*.db"))
                self.assertGreater(len(fresh_backups), len(backups_before))
                summary = window.repository.summary()
                self.assertGreater(int(summary.get("models", 0)), 0)
                self.assertIsNone(QApplication.overrideCursor())
                self.assertNotIn(window.tr("busy_working"), window.statusBar().currentMessage())
            finally:
                window.close()
                app.processEvents()

    def test_update_confirm_no_aborts_yes_proceeds(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from unittest import mock

        from PySide6.QtWidgets import QApplication

        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as tmp:
            window = self._make_window(app, tmp)
            try:
                build_id = self._save_one_build(app, window)
                original = str(window.repository.get_build(build_id)["name"])
                # Simulate a user edit of the build card (widget holds the new
                # text and the textEdited slot marks the card dirty).
                window.edits["build_name"].setText("Renamed Build")
                window._sync_edit_value("build_name", "Renamed Build",
                                        window.edits["build_name"])
                app.processEvents()
                self.assertTrue(window._dirty)
                with mock.patch.object(window, "_confirm", return_value=False) as confirm:
                    window.update_build()
                    app.processEvents()
                self.assertEqual(confirm.call_count, 1)
                self.assertEqual(window.repository.get_build(build_id)["name"], original)
                self.assertTrue(window._dirty, "aborted overwrite must stay dirty")
                with mock.patch.object(window, "_confirm", return_value=True) as confirm:
                    window.update_build()
                    app.processEvents()
                self.assertEqual(confirm.call_count, 1)
                self.assertEqual(window.repository.get_build(build_id)["name"], "Renamed Build")
                self.assertFalse(window._dirty, "successful overwrite clears dirty")
            finally:
                window.close()
                app.processEvents()

    def test_delete_confirm_no_aborts_yes_proceeds(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from unittest import mock

        from PySide6.QtWidgets import QApplication

        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as tmp:
            window = self._make_window(app, tmp)
            try:
                build_id = self._save_one_build(app, window)
                count_before = len(window.repository.builds())
                with mock.patch.object(window, "_confirm", return_value=False) as confirm:
                    window.delete_build()
                    app.processEvents()
                self.assertEqual(confirm.call_count, 1)
                self.assertEqual(len(window.repository.builds()), count_before)
                self.assertEqual(window.current_build_id, build_id)
                with mock.patch.object(window, "_confirm", return_value=True) as confirm:
                    window.delete_build()
                    app.processEvents()
                self.assertEqual(confirm.call_count, 1)
                self.assertEqual(len(window.repository.builds()), count_before - 1)
                self.assertIsNone(window.current_build_id)
            finally:
                window.close()
                app.processEvents()

    def test_close_dirty_confirm(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from unittest import mock

        from PySide6.QtGui import QCloseEvent
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as tmp:
            # Clean window: close must not ask and must be accepted.
            window = self._make_window(app, tmp)
            try:
                self.assertFalse(window._dirty)
                with mock.patch.object(window, "_confirm") as confirm:
                    event = QCloseEvent()
                    window.closeEvent(event)
                    app.processEvents()
                confirm.assert_not_called()
                self.assertTrue(event.isAccepted())
            finally:
                # Repository was closed by the accepted closeEvent; sqlite
                # close() is idempotent so a second close is harmless.
                window.close()
                app.processEvents()
            # Dirty window: No keeps it open, Yes closes.
            window = self._make_window(app, tmp, name="work2.db")
            try:
                window._sync_edit_value("build_name", "unsaved",
                                        window.edits["build_name"])
                self.assertTrue(window._dirty)
                with mock.patch.object(window, "_confirm", return_value=False) as confirm:
                    event = QCloseEvent()
                    window.closeEvent(event)
                    app.processEvents()
                self.assertEqual(confirm.call_count, 1)
                self.assertFalse(event.isAccepted())
                with mock.patch.object(window, "_confirm", return_value=True) as confirm:
                    event = QCloseEvent()
                    window.closeEvent(event)
                    app.processEvents()
                self.assertEqual(confirm.call_count, 1)
                self.assertTrue(event.isAccepted())
                # Clear the flag so the finally teardown cannot raise a real dialog.
                window._dirty = False
            finally:
                window.close()
                app.processEvents()
