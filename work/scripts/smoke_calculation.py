from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from propcalc.calculator import CalculationInputs, PropellerCalculator
from propcalc.repository import Repository


repo = Repository(ROOT / "work" / "build" / "propellers.db")
model_id = repo.connection.execute(
    """SELECT model_id FROM models WHERE diameter_m IS NOT NULL AND EXISTS(
       SELECT 1 FROM performance_points p WHERE p.model_id=models.model_id AND p.ct IS NOT NULL AND p.cp IS NOT NULL)
       ORDER BY has_experiment DESC LIMIT 1"""
).fetchone()[0]
result = PropellerCalculator(repo).calculate(CalculationInputs(model_id=model_id))
print({"model_id": model_id, "thrust_n": result.total_thrust_n, "rpm": result.point.rpm,
       "evidence": result.point.evidence, "optimum_rpm": result.optimum.rpm if result.optimum else None})
repo.close()
