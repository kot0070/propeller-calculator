from __future__ import annotations

import sys
from pathlib import Path

from PIL import ImageGrab


target = Path(sys.argv[1]).resolve()
target.parent.mkdir(parents=True, exist_ok=True)
ImageGrab.grab(all_screens=True).save(target)
print(target)
