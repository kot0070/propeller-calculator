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
