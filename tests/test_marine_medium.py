"""Regression tests for marine (underwater) medium labeling at the ingest boundary.

Source of truth (read-only reference):
  work/extracted/APC_PERFILES_202602/PERFILES_WEB/PERFILES2-MARINE/PER3_10x10M-JK.dat
  header "DEFINITIONS: (Underwater)" -> medium water, rho ~= 1000 kg/m^3.

Bug: IngestSession.ingest_apc_predictions() labeled marine rows medium='water'
but stored density_kg_m3=1.225 (air), and models.medium stayed 'air' because
ensure_model() keeps the first-seen medium (the APC catalog ingest runs first
with medium='air'). These tests pin the corrected behaviour through the REAL
import path (IngestSession.ingest_apc_predictions) on minimal marine-like
fixtures in a throwaway tmp DB -- the production database is never touched.
"""
from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path

from propcalc.ingest import AIR_DENSITY, WATER_DENSITY, IngestSession

CODE = "APC_PERFILES_202602"


def _per3_fixture(*, underwater: bool) -> str:
    definitions = "DEFINITIONS: (Underwater)" if underwater else "DEFINITIONS:"
    return (
        "         12x8M-JK                (12x8M-JK.dat)\n"
        "         v2022-0915\n"
        f"         {definitions}\n"
        "         PROP RPM = 3000\n"
        "         10.0 0.2 0.70 0.1000 0.0500 1.0 2.0 3.0 100.0 5.0 50.0 0.0 0.0 0.0 0.0\n"
        "         0.0 0.0 0.65 0.1100 0.0550 1.1 2.1 3.1 110.0 5.5 55.0 0.0 0.0 0.0 0.0\n"
    )


def _make_session() -> tuple[IngestSession, sqlite3.Connection]:
    connection = sqlite3.connect(":memory:")
    session = IngestSession(connection)
    connection.execute(
        """INSERT INTO sources(code,name,source_group,source_kind,archive_name,archive_sha256,archive_bytes)
           VALUES(?,?,?,?,?,?,?)""",
        (CODE, "test", "test-group", "test-kind", "test.zip", "00" * 32, 1),
    )
    session.source_ids[CODE] = connection.execute(
        "SELECT source_id FROM sources WHERE code=?", (CODE,)
    ).fetchone()[0]
    return session, connection


def _add_file(session: IngestSession, connection: sqlite3.Connection,
              relative: str, path: Path) -> None:
    source_id = session.source_ids[CODE]
    connection.execute(
        """INSERT INTO source_files(source_id,relative_path,sha256,file_bytes,extension,status)
           VALUES(?,?,?, ?, ?, 'pending')""",
        (source_id, relative, "11" * 32, path.stat().st_size, ".dat"),
    )
    file_id = connection.execute(
        "SELECT source_file_id FROM source_files WHERE source_id=? AND relative_path=?",
        (source_id, relative),
    ).fetchone()[0]
    session.source_files[(CODE, relative)] = (file_id, path)


class MarineMediumIngestTest(unittest.TestCase):
    def _run_fixture(self, tmp_dir: Path, *, relative: str, underwater: bool,
                     preseed_air_model: bool) -> tuple[sqlite3.Connection, str]:
        fixture = tmp_dir / Path(relative).name
        fixture.write_text(_per3_fixture(underwater=underwater), encoding="utf-8")
        session, connection = _make_session()
        _add_file(session, connection, relative, fixture)
        if preseed_air_model:
            # Simulate the catalog ingest running first with medium='air'.
            air_model = session.resolve_apc_prediction_model(
                Path(relative).stem.replace("PER3_", ""), "air")
            session.ensure_model(air_model)
        session.ingest_apc_predictions()
        model_id = session.resolve_apc_prediction_model(
            Path(relative).stem.replace("PER3_", ""), "air").model_id
        return connection, model_id

    def test_marine_path_sets_water_medium_and_density(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            connection, model_id = self._run_fixture(
                Path(tmp),
                relative="PERFILES_WEB/PERFILES2-MARINE/PER3_12x8M-JK.dat",
                underwater=False,  # path alone must be enough
                preseed_air_model=True,
            )
            model = connection.execute(
                "SELECT medium FROM models WHERE model_id=?", (model_id,)).fetchone()
            self.assertIsNotNone(model)
            self.assertEqual(model[0], "water")
            rows = connection.execute(
                "SELECT DISTINCT medium, density_kg_m3 FROM performance_points"
                " WHERE model_id=?", (model_id,)).fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][0], "water")
            self.assertAlmostEqual(rows[0][1], 1000.0, places=9)
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM performance_points WHERE model_id=?",
                (model_id,)).fetchone()[0], 2)

    def test_underwater_header_sets_water_without_marine_path(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            connection, model_id = self._run_fixture(
                Path(tmp),
                relative="PERFILES_WEB/PERFILES2/PER3_12x9M-JK.dat",
                underwater=True,  # header alone must be enough
                preseed_air_model=True,
            )
            model = connection.execute(
                "SELECT medium FROM models WHERE model_id=?", (model_id,)).fetchone()
            self.assertIsNotNone(model)
            self.assertEqual(model[0], "water")
            rows = connection.execute(
                "SELECT DISTINCT medium, density_kg_m3 FROM performance_points"
                " WHERE model_id=?", (model_id,)).fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][0], "water")
            self.assertAlmostEqual(rows[0][1], WATER_DENSITY, places=9)

    def test_air_file_stays_air(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            connection, model_id = self._run_fixture(
                Path(tmp),
                relative="PERFILES_WEB/PERFILES2/PER3_12x10.dat",
                underwater=False,
                preseed_air_model=False,
            )
            model = connection.execute(
                "SELECT medium FROM models WHERE model_id=?", (model_id,)).fetchone()
            self.assertIsNotNone(model)
            self.assertEqual(model[0], "air")
            rows = connection.execute(
                "SELECT DISTINCT medium, density_kg_m3 FROM performance_points"
                " WHERE model_id=?", (model_id,)).fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][0], "air")
            self.assertAlmostEqual(rows[0][1], AIR_DENSITY, places=9)


if __name__ == "__main__":
    unittest.main()
