"""Regression guards for calculator batch 1 (fixture DB, no production data needed)."""
from __future__ import annotations

import math
import sqlite3
import tempfile
import unittest
from pathlib import Path

from propcalc.calculator import CalculationInputs, PropellerCalculator
from propcalc.database import connect_database, initialize_database
from propcalc.repository import Repository


def make_guard_database(path: Path) -> None:
    connection = connect_database(path)
    initialize_database(connection)
    connection.execute(
        """INSERT INTO sources(code,name,organization,source_group,source_kind,version,source_date,
        archive_name,archive_sha256,archive_bytes,provenance_note)
        VALUES('TEST','Test source','Test','Other','experiment','1','2026-01-01','test.dat','ABC',1,'fixture')""")
    source_id = connection.execute("SELECT source_id FROM sources WHERE code='TEST'").fetchone()[0]
    connection.execute(
        """INSERT INTO source_files(source_id,relative_path,sha256,file_bytes,extension,status,category)
        VALUES(?, 'test.dat','DEF',1,'.dat','recognized','performance')""", (source_id,))
    file_id = connection.execute("SELECT source_file_id FROM source_files").fetchone()[0]
    connection.execute(
        """INSERT INTO models(model_id,original_name,manufacturer,diameter_m,pitch_m,blade_count,medium,has_experiment)
        VALUES('TEST:10X5','10x5','Test',0.254,0.127,2,'air',1)""")
    for key, rpm, ct, cp, ch in (("TEST:P1", 5000, 0.10, 0.05, "A"),
                                 ("TEST:P2", 6000, 0.11, 0.055, "B")):
        connection.execute(
            """INSERT INTO performance_points(point_key,model_id,original_name,manufacturer,diameter_m,pitch_m,
            blade_count,medium,rpm,advance_ratio_j,ct,cp,is_static,source_type,evidence_class,source_file_id,content_hash)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (key, "TEST:10X5", "10x5", "Test", 0.254, 0.127, 2, "air", rpm, 0, ct, cp, 1,
             "physical experiment", "experiment", file_id, ch))
    connection.commit()
    connection.close()


class CalculatorGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.folder = tempfile.TemporaryDirectory()
        cls.db_path = Path(cls.folder.name) / "guards.db"
        make_guard_database(cls.db_path)
        cls.repository = Repository(cls.db_path)
        cls.calculator = PropellerCalculator(cls.repository)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.repository.close()
        cls.folder.cleanup()

    def test_zero_motor_limits_do_not_crash(self) -> None:
        result = self.calculator.calculate(CalculationInputs(
            model_id="TEST:10X5", motor_kv=500, motor_count=1,
            motor_max_current_a=0, motor_max_power_w=0))
        self.assertIsNone(result.motor_current_margin_percent)
        self.assertIsNone(result.motor_power_margin_percent)

    def test_sweep_rejects_total_battery_overload(self) -> None:
        # 4 motors sharing one pack: per-motor current fits the ESC, but the
        # pack total must still block the candidate (old min() logic missed it).
        from propcalc.calculator import G, battery_spec
        inputs = CalculationInputs(
            model_id="TEST:10X5", motor_kv=900, motor_count=4, mass_kg=0.2,
            esc_current_a=60.0, battery_capacity_ah=1.0, battery_c_rating=10.0)
        battery_max = inputs.battery_capacity_ah * inputs.battery_c_rating
        point = self.calculator.operating_point(inputs, 1.0, 14.8)
        assert point is not None
        total = point.current_a * 4
        # Fixture sanity: this operating point really overloads the pack.
        self.assertGreater(total, battery_max)
        self.assertGreater(point.current_a, 0)
        # Sweep must not recommend any point that overloads the pack.
        best, _, _, _ = self.calculator.sweep(inputs)
        motors = max(1, inputs.motor_count)
        if best is not None:
            self.assertLessEqual(best.current_a * motors, battery_max)
        else:
            # Non-vacuous: sweep returned None, so prove EVERY thrust-sufficient
            # candidate it could have considered overloads the pack. Fails if
            # no such candidate exists (neither recommendation nor proof).
            nominal_v = battery_spec(inputs.battery_type)["nominal_v"]
            candidate_s = sorted(set(range(max(2, inputs.battery_s - 2),
                                           min(12, inputs.battery_s + 2) + 1)))
            examined = 0
            for cells in candidate_s:
                voltage = cells * nominal_v
                for step in range(3, 11):
                    throttle = step / 10.0
                    cand = self.calculator.operating_point(inputs, throttle, voltage)
                    if cand is None or cand.thrust_n <= 0 or cand.current_a <= 0:
                        continue
                    if cand.thrust_n * motors < inputs.mass_kg * G * 1.05:
                        continue
                    examined += 1
                    self.assertGreater(
                        cand.current_a * motors, battery_max,
                        f"sweep rejected {cells}S@{throttle:.1f} but it fits the pack; "
                        "None is not proof of battery-overload rejection")
            self.assertGreater(
                examined, 0,
                "sweep returned None but no thrust-sufficient candidate exists; "
                "test is vacuous (neither recommendation nor proof-of-overload)")

    def test_source_point_id_reproduces_exact_row(self) -> None:
        target = self.repository.get_performance_point(2, "TEST:10X5")
        assert target is not None
        inputs = CalculationInputs(
            model_id="TEST:10X5", motor_kv=500, motor_count=1,
            rpm_override=float(target["rpm"]), source_point_id=int(target["performance_id"]))
        result = self.calculator.calculate(inputs)
        self.assertEqual(result.point.rpm, float(target["rpm"]))
        self.assertAlmostEqual(result.point.ct, float(target["ct"]), places=8)
        self.assertAlmostEqual(result.point.cp, float(target["cp"]), places=8)
        self.assertFalse(result.point.extrapolated)

    def test_interpolation_still_works_without_source_point(self) -> None:
        result = self.calculator.calculate(
            CalculationInputs(model_id="TEST:10X5", motor_kv=500, motor_count=1))
        self.assertGreater(result.total_thrust_n, 0)
        self.assertEqual(result.point.evidence, "experiment")
        self.assertFalse(result.point.extrapolated)

    def test_invalid_inputs_warn_without_crash(self) -> None:
        negative_mass = self.calculator.calculate(CalculationInputs(
            model_id="TEST:10X5", motor_kv=500, mass_kg=-5.0))
        self.assertTrue(any("mass_kg" in w for w in negative_mass.warnings))
        negative_density = self.calculator.calculate(CalculationInputs(
            model_id="TEST:10X5", motor_kv=500, density_kg_m3=-1.0))
        self.assertTrue(any("density" in w for w in negative_density.warnings))
        non_finite = self.calculator.calculate(CalculationInputs(
            model_id="TEST:10X5", motor_kv=500, voltage_v=float("nan")))
        self.assertTrue(any("Non-finite" in w for w in non_finite.warnings))
        zero_motors = self.calculator.calculate(CalculationInputs(
            model_id="TEST:10X5", motor_kv=500, motor_count=0))
        self.assertTrue(any("motor_count" in w for w in zero_motors.warnings))

    def test_no_operating_point_runtime_is_nan_with_warning(self) -> None:
        # Unknown model -> operating_point() is None -> zero-substitute point
        # with zero current. Runtime must be a NaN sentinel (never the
        # 240000000.0 min blow-up from dividing by the 1e-6 guard), plus an
        # explicit warning so the UI card can render "—" instead of a number.
        result = self.calculator.calculate(CalculationInputs(
            model_id="NOPE:missing", motor_kv=500, motor_count=1))
        self.assertTrue(math.isnan(result.runtime_min))
        self.assertTrue(any("No valid operating point" in w for w in result.warnings))

    def test_zero_throttle_runtime_is_nan_with_warning(self) -> None:
        result = self.calculator.calculate(CalculationInputs(
            model_id="TEST:10X5", motor_kv=500, motor_count=1, throttle=0.0))
        self.assertTrue(math.isnan(result.runtime_min))
        self.assertTrue(any("No valid operating point" in w for w in result.warnings))

    def test_valid_fixture_runtime_number_unchanged(self) -> None:
        inputs = CalculationInputs(model_id="TEST:10X5", motor_kv=500, motor_count=1)
        result = self.calculator.calculate(inputs)
        self.assertFalse(math.isnan(result.runtime_min))
        self.assertFalse(any("No valid operating point" in w for w in result.warnings))
        self.assertAlmostEqual(result.runtime_min, 36.381749970550864, places=8)


if __name__ == "__main__":
    unittest.main(verbosity=2)
