from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from propcalc.repository import Repository


database = Path(sys.argv[1])
repository = Repository(database)
build_id = repository.save_build({
    "name": "EXE 3.2 persistence QA",
    "description": "Must survive a second one-file EXE launch",
    "propeller_model_id": "APC:10X5",
    "motor_kv": 500,
    "battery_s": 4,
    "battery_capacity_ah": 5,
    "esc_current_a": 40,
    "motor_count": 4,
    "mass_kg": 1.5,
    "payload_kg": 0.2,
    "note": "Ivan Soprun",
    "advanced": {"motor_name": "QA motor", "battery_name": "QA battery", "battery_type": "Li-ion",
                 "esc_name": "QA ESC", "frame_name": "QA frame"},
})
components = repository.connection.execute(
    "SELECT COUNT(*) FROM saved_build_components WHERE build_id=?", (build_id,)
).fetchone()[0]
repository.close()
print(json.dumps({"build_id": build_id, "components": components}))
