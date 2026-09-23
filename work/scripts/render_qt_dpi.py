from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_SCALE_FACTOR"] = "2"

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtWidgets import QApplication
from propcalc.qt_app import PropellerMainWindow


app = QApplication([])
window = PropellerMainWindow(ROOT / "work" / "build" / "propellers.db")
window.resize(683, 384)
window.show()
app.processEvents()
output = ROOT / "work" / "visual_qa" / "1366x768_200percent_calculator.png"
window.grab().save(str(output))
window.close()
