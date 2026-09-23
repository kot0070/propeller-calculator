from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtWidgets import QApplication

from propcalc.qt_app import PropellerMainWindow


def main() -> None:
    output = ROOT / "work" / "visual_qa"
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="propcalc-render-") as folder:
        database = Path(folder) / "visual.db"
        source = sqlite3.connect(ROOT / "work" / "build" / "propellers.db")
        target = sqlite3.connect(database)
        source.backup(target)
        source.close()
        target.close()
        app = QApplication([])
        window = PropellerMainWindow(database)
        window._switch_language("uk")
        window.show()
        app.processEvents()
        window.add_current_to_compare()
        for width, height in ((1366, 768), (1920, 1080)):
            window.resize(width, height)
            app.processEvents()
            for index in range(window.tabs.count()):
                window.tabs.setCurrentIndex(index)
                app.processEvents()
                path = output / f"{width}x{height}_{index + 1}_{window.tabs.tabText(index)}.png"
                window.grab().save(str(path))
            window.tabs.setCurrentIndex(6)
            for help_index in range(window.help_pages.count()):
                window.help_pages.setCurrentIndex(help_index)
                app.processEvents()
                window.grab().save(str(output / f"{width}x{height}_help_{help_index + 1}_uk.png"))
            window._snapshot()
            window._build_ui()
            app.processEvents()
            window.tabs.setCurrentIndex(0)
            for mode, mode_name in ((0, "simple"), (1, "engineering")):
                window.calculator_modes.setCurrentIndex(mode)
                app.processEvents()
                window.grab().save(str(output / f"{width}x{height}_calculator_{mode_name}_uk.png"))
        window._switch_language("en")
        window.resize(1366, 768)
        window.tabs.setCurrentIndex(0)
        for mode, mode_name in ((0, "simple"), (1, "engineering")):
            window.calculator_modes.setCurrentIndex(mode)
            app.processEvents()
            window.grab().save(str(output / f"1366x768_calculator_{mode_name}_en.png"))
        window.tabs.setCurrentIndex(2)
        app.processEvents()
        window.grab().save(str(output / "1366x768_builds_en.png"))
        window.close()


if __name__ == "__main__":
    main()
