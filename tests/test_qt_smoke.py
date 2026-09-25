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
