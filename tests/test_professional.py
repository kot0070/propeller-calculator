from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from propcalc.calculator import CalculationInputs, PropellerCalculator
from propcalc.database import connect_database, initialize_database
from propcalc.repository import Repository
from propcalc.runtime_import import RuntimeImportService
from propcalc.units import SPECS, from_si, to_si


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_DB = ROOT / "work" / "build" / "propellers.db"


def make_minimal_database(path: Path, ct: float = 0.1, content_hash: str = "A") -> None:
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
    connection.execute(
        """INSERT INTO performance_points(point_key,model_id,original_name,manufacturer,diameter_m,pitch_m,
        blade_count,medium,rpm,advance_ratio_j,ct,cp,is_static,source_type,evidence_class,source_file_id,content_hash)
        VALUES('TEST:P1','TEST:10X5','10x5','Test',0.254,0.127,2,'air',5000,0,?,0.05,1,
        'physical experiment','experiment',?,?)""", (ct, file_id, content_hash))
    connection.commit()
    connection.close()


class DatabaseAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.connection = sqlite3.connect(PRODUCTION_DB)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.connection.close()

    def test_exact_counts_and_integrity(self) -> None:
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM models").fetchone()[0], 1053)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM performance_points").fetchone()[0], 335434)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM sources").fetchone()[0], 7)
        self.assertEqual(self.connection.execute("PRAGMA quick_check").fetchone()[0], "ok")
        self.assertEqual(self.connection.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_no_duplicate_keys(self) -> None:
        duplicate_points = self.connection.execute(
            "SELECT COUNT(*) FROM (SELECT point_key FROM performance_points GROUP BY point_key HAVING COUNT(*)>1)"
        ).fetchone()[0]
        duplicate_models = self.connection.execute(
            "SELECT COUNT(*) FROM (SELECT model_id FROM models GROUP BY model_id HAVING COUNT(*)>1)"
        ).fetchone()[0]
        self.assertEqual(duplicate_points, 0)
        self.assertEqual(duplicate_models, 0)


class CalculationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repository = Repository(PRODUCTION_DB)
        cls.calculator = PropellerCalculator(cls.repository)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.repository.close()

    def test_static_air(self) -> None:
        result = self.calculator.calculate(CalculationInputs(model_id="APC:10X5", motor_kv=500, motor_count=4))
        self.assertGreater(result.total_thrust_n, 0)
        self.assertAlmostEqual(result.point.j, 0.0, places=12)
        self.assertEqual(result.point.evidence, "experiment")
        self.assertFalse(result.point.extrapolated)

    def test_dynamic_air(self) -> None:
        result = self.calculator.calculate(
            CalculationInputs(model_id="APC:10X5", motor_kv=500, motor_count=4, speed_m_s=10.0))
        self.assertGreater(result.point.j, 0)
        self.assertGreater(result.point.rpm, 0)
        self.assertGreaterEqual(result.point.confidence, 0.15)

    def test_raw_source_point_is_kept_separate_from_interpolation(self) -> None:
        inputs = CalculationInputs(model_id="APC:10X5", motor_kv=500, motor_count=4)
        result = self.calculator.calculate(inputs)
        raw = self.repository.nearest_raw_point(inputs.model_id, result.point.rpm, result.point.j,
                                                result.point.evidence)
        self.assertIsNotNone(raw)
        self.assertTrue(raw["relative_path"])
        self.assertNotEqual(float(raw["rpm"]), result.point.rpm)
        self.assertAlmostEqual(float(raw["ct"]), 0.1066, places=4)

    def test_database_point_mode_reproduces_apc_8x9_source_power(self) -> None:
        raw = self.repository.reference_points("APC:8X9")[0]
        self.assertEqual(raw["evidence_class"], "experiment")
        self.assertTrue(raw["is_static"])
        self.assertEqual(float(raw["rpm"]), 6395.0)
        inputs = CalculationInputs(
            model_id="APC:8X9", voltage_v=14.8, motor_kv=540.1,
            speed_m_s=float(raw["speed_m_s"] or 0), rpm_override=float(raw["rpm"]),
            source_point_id=int(raw["performance_id"]),
        )
        result = self.calculator.calculate(inputs)
        self.assertEqual(result.point.rpm, 6395.0)
        self.assertAlmostEqual(result.point.ct, float(raw["ct"]), places=8)
        self.assertAlmostEqual(result.point.cp, float(raw["cp"]), places=8)
        self.assertAlmostEqual(result.point.prop_power_w, float(raw["power_w"]), places=8)

    def test_battery_chemistry_changes_usable_runtime_and_nominal_voltage_warning(self) -> None:
        lipo = self.calculator.calculate(CalculationInputs(
            model_id="APC:10X5", motor_kv=500, battery_type="LiPo", battery_s=4, voltage_v=14.8))
        li_ion = self.calculator.calculate(CalculationInputs(
            model_id="APC:10X5", motor_kv=500, battery_type="Li-ion", battery_s=4, voltage_v=14.8))
        self.assertGreater(li_ion.runtime_min, lipo.runtime_min)
        self.assertAlmostEqual(li_ion.runtime_min / lipo.runtime_min, 0.85 / 0.80, places=8)
        mismatch = self.calculator.calculate(CalculationInputs(
            model_id="APC:10X5", motor_kv=500, battery_type="LiPo", battery_s=6, voltage_v=14.8))
        self.assertTrue(any(item.startswith("Battery voltage mismatch:") for item in mismatch.warnings))

    def test_water_mode_is_explicit_estimate(self) -> None:
        result = self.calculator.calculate(
            CalculationInputs(model_id="APC:10X5", motor_kv=120, voltage_v=7.4, motor_count=1,
                              density_kg_m3=997, medium="water"))
        self.assertGreater(result.total_thrust_n, 0)
        self.assertTrue(any("cavitation" in warning for warning in result.warnings))

    def test_every_unit_round_trip(self) -> None:
        for quantity in SPECS:
            with self.subTest(quantity=quantity):
                original = 23.456789
                converted = from_si(original, quantity, "Imperial")
                restored = to_si(converted, quantity, "Imperial")
                self.assertAlmostEqual(original, restored, places=10)


class PersistenceAndImportTests(unittest.TestCase):
    def test_saved_build_and_components_persist(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "working.db"
            make_minimal_database(database)
            repository = Repository(database)
            payload = {
                "name": "Persistence test", "description": "test", "propeller_model_id": "TEST:10X5",
                "motor_kv": 500, "battery_s": 4, "battery_capacity_ah": 5,
                "esc_current_a": 40, "motor_count": 4, "mass_kg": 1.5, "payload_kg": 0.2,
                "note": "restart", "advanced": {"motor_name": "M1", "battery_name": "B1",
                                                     "esc_name": "E1", "frame_name": "F1"},
            }
            build_id = repository.save_build(payload)
            repository.close()
            reopened = Repository(database)
            row = reopened.get_build(build_id)
            self.assertEqual(row["name"], "Persistence test")
            self.assertEqual(row["payload_kg"], 0.2)
            components = reopened.connection.execute(
                "SELECT component_type,component_ref FROM saved_build_components WHERE build_id=? ORDER BY component_type",
                (build_id,)).fetchall()
            self.assertEqual(len(components), 5)
            reopened.close()

    def test_saved_build_persists_enabled_accessory_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "working.db"
            make_minimal_database(database)
            repository = Repository(database)
            accessories = [
                {"category": "gps", "model": "M10 GNSS", "quantity": 1,
                 "mass_kg": 0.012, "enabled": True},
                {"category": "antenna", "model": "Dual antenna", "quantity": 2,
                 "mass_kg": 0.006, "enabled": True},
                {"category": "camera", "model": "Not installed", "quantity": 1,
                 "mass_kg": 0.025, "enabled": False},
            ]
            build_id = repository.save_build({
                "name": "Accessory test", "propeller_model_id": "TEST:10X5",
                "motor_kv": 500, "battery_s": 4, "battery_capacity_ah": 5,
                "esc_current_a": 40, "motor_count": 4, "mass_kg": 1.5, "payload_kg": 0.2,
                "advanced": {"accessories": accessories},
            })
            saved = repository.get_build(build_id)
            self.assertEqual(json.loads(saved["advanced_json"])["accessories"], accessories)
            rows = repository.connection.execute(
                """SELECT component_ref,quantity,properties_json FROM saved_build_components
                   WHERE build_id=? AND component_type='accessory' ORDER BY component_ref""", (build_id,)).fetchall()
            self.assertEqual(len(rows), 2)
            self.assertEqual(sum(row["quantity"] for row in rows), 3)
            antenna = next(row for row in rows if row["component_ref"] == "Dual antenna")
            self.assertAlmostEqual(json.loads(antenna["properties_json"])["mass_total_kg"], 0.012)
            repository.close()

    def test_merge_is_idempotent_then_updates_and_adds(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source.db"
            target = root / "target.db"
            make_minimal_database(source)
            connection = connect_database(target)
            initialize_database(connection)
            service = RuntimeImportService(connection, target, root / "backups")
            first = service.import_path(source)
            count_1 = connection.execute("SELECT COUNT(*) FROM performance_points").fetchone()[0]
            second = service.import_path(source)
            count_2 = connection.execute("SELECT COUNT(*) FROM performance_points").fetchone()[0]
            self.assertEqual(count_1, 1)
            self.assertEqual(count_2, count_1)
            self.assertGreaterEqual(second["skipped"], 1)
            changed = sqlite3.connect(source)
            changed.execute("UPDATE performance_points SET ct=0.12,content_hash='B' WHERE point_key='TEST:P1'")
            changed.execute(
                """INSERT INTO performance_points(point_key,model_id,original_name,manufacturer,diameter_m,pitch_m,
                blade_count,medium,rpm,advance_ratio_j,ct,cp,is_static,source_type,evidence_class,source_file_id,content_hash)
                SELECT 'TEST:P2',model_id,original_name,manufacturer,diameter_m,pitch_m,blade_count,medium,
                6000,0,0.13,cp,is_static,source_type,evidence_class,source_file_id,'C'
                FROM performance_points WHERE point_key='TEST:P1'""")
            changed.commit()
            changed.close()
            third = service.import_path(source)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM performance_points").fetchone()[0], 2)
            self.assertAlmostEqual(connection.execute(
                "SELECT ct FROM performance_points WHERE point_key='TEST:P1'").fetchone()[0], 0.12)
            self.assertGreaterEqual(third["updated"], 1)
            self.assertEqual(len(list((root / "backups").glob("*.db"))), 3)
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM import_history WHERE status='success'").fetchone()[0], 3)
            connection.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
