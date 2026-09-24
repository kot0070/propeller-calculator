"""Offscreen Qt smoke: main window builds with 8 tabs even on an empty seed DB.

Skipped when PySide6 is unavailable or the local seed database is absent
(e.g. fresh clone without the private release database).
"""
from __future__ import annotations

import importlib.util
import os
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SEED_DB = ROOT / "work" / "build" / "propellers.db"

requires_qt = unittest.skipUnless(importlib.util.find_spec("PySide6") is not None, "PySide6 not installed")
requires_db = unittest.skipUnless(SEED_DB.exists(), "local seed database absent")


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
