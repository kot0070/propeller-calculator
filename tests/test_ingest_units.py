"""Regression tests for UIUC diameter/pitch unit handling at the ingest boundary.

Source of truth (read-only reference):
  work/extracted/UIUC-propDB/UIUC-propDB/volume-2/propDB-volume-2.html
  work/extracted/UIUC-propDB/UIUC-propDB/volume-3/propDB-volume-3.html

Volume-2 micro-prop designations are millimetres (spec labels carry an
explicit "mm" suffix, e.g. "140 mm X 45 mm"); volume-3 Aeronaut filenames
drop the decimal point of half-inch sizes (spec "12.5 x 7.5" is filed as
"125x75"). normalize_uiuc() treats every designation as inches, so these
tests pin the corrected behaviour of resolve_uiuc_model() in
propcalc.ingest, the real function used by IngestSession.ingest_uiuc().
"""
from __future__ import annotations

import unittest
from pathlib import Path

from propcalc.ingest import IngestSession, resolve_uiuc_model

INCH_M = 0.0254

# (raw model name as produced by IngestSession.uiuc_raw_model,
#  expected diameter_m, expected pitch_m)
MM_CASES: tuple[tuple[str, float, float], ...] = (
    ("vp_140x45", 0.140, 0.045),  # spec "140 mm X 45 mm"
    ("pl_100x80", 0.100, 0.080),  # spec "100 mm X 80 mm"
    ("kpf_96x70", 0.096, 0.070),  # spec "96 mm X 70 mm"
    ("ef_130x70", 0.130, 0.070),  # spec "130 mm X 70 mm"
    ("pl_57x20", 0.057, 0.020),  # spec "57 mm X 20mm"
)

DROPPED_DECIMAL_CASES: tuple[tuple[str, float, float], ...] = (
    ("ancf_125x75", 12.5 * INCH_M, 7.5 * INCH_M),  # spec "12.5 x 7.5"
    ("ancf_125x9", 12.5 * INCH_M, 9.0 * INCH_M),  # spec "12.5 x 9"
    ("ancf_125x6", 12.5 * INCH_M, 6.0 * INCH_M),  # spec "12.5 x 6"
)

# (raw model name, expected diameter_m, expected pitch_m); must stay inches.
INCH_REGRESSION_CASES: tuple[tuple[str, float, float], ...] = (
    ("apce_9x6", 9.0 * INCH_M, 6.0 * INCH_M),
    ("ancf_10x6", 10.0 * INCH_M, 6.0 * INCH_M),
    ("ancf_12x8", 12.0 * INCH_M, 8.0 * INCH_M),
)


class ResolveUiucModelUnitsTest(unittest.TestCase):
    def test_millimetre_designations_parse_as_mm(self) -> None:
        for raw_name, diameter_m, pitch_m in MM_CASES:
            with self.subTest(raw_name=raw_name):
                model = resolve_uiuc_model(raw_name)
                self.assertAlmostEqual(model.diameter_m, diameter_m, places=9)
                self.assertAlmostEqual(model.pitch_m, pitch_m, places=9)

    def test_dropped_decimal_inch_designations_keep_decimal(self) -> None:
        for raw_name, diameter_m, pitch_m in DROPPED_DECIMAL_CASES:
            with self.subTest(raw_name=raw_name):
                model = resolve_uiuc_model(raw_name)
                self.assertAlmostEqual(model.diameter_m, diameter_m, places=9)
                self.assertAlmostEqual(model.pitch_m, pitch_m, places=9)

    def test_ordinary_inch_designations_unchanged(self) -> None:
        for raw_name, diameter_m, pitch_m in INCH_REGRESSION_CASES:
            with self.subTest(raw_name=raw_name):
                model = resolve_uiuc_model(raw_name)
                self.assertAlmostEqual(model.diameter_m, diameter_m, places=9)
                self.assertAlmostEqual(model.pitch_m, pitch_m, places=9)

    def test_real_filenames_resolve_to_true_dimensions(self) -> None:
        cases = (
            ("vp_140x45_static_0590rd.txt", "static_experiment", 0.140, 0.045),
            ("vp_140x45_0591rd_4991.txt", "dynamic_experiment", 0.140, 0.045),
            ("vp_140x45_geom.txt", "geometry", 0.140, 0.045),
            ("ef_130x70_static_0350rd.txt", "static_experiment", 0.130, 0.070),
            ("pl_100x80_geom.txt", "geometry", 0.100, 0.080),
            ("pl_57x20_static_0531rd.txt", "static_experiment", 0.057, 0.020),
            ("kpf_96x70_static_0382rd.txt", "static_experiment", 0.096, 0.070),
            ("ancf_125x75_static_0914od.txt", "static_experiment", 12.5 * INCH_M, 7.5 * INCH_M),
            ("ancf_125x9_0906od_3015.txt", "dynamic_experiment", 12.5 * INCH_M, 9.0 * INCH_M),
            ("ancf_125x6_0925od_3027.txt", "dynamic_experiment", 12.5 * INCH_M, 6.0 * INCH_M),
        )
        for filename, category, diameter_m, pitch_m in cases:
            with self.subTest(filename=filename):
                raw_model = IngestSession.uiuc_raw_model(Path(filename), category)
                model = resolve_uiuc_model(raw_model)
                self.assertAlmostEqual(model.diameter_m, diameter_m, places=9)
                self.assertAlmostEqual(model.pitch_m, pitch_m, places=9)

    def test_designation_without_size_stays_unknown(self) -> None:
        model = resolve_uiuc_model("pl_triturbo")
        self.assertIsNone(model.diameter_m)
        self.assertIsNone(model.pitch_m)

    def test_dropped_decimal_sibling_designations(self) -> None:
        # Spec "12 x 6.5" is filed as "12x65"; spec "13 x 6.5" as "13x65"
        # (volume-3 oracle page). resolve_uiuc_model must restore the decimal.
        cases = (
            ("ancf_12x65", 12.0 * INCH_M, 6.5 * INCH_M),  # 0.3048 / 0.1651
            ("ancf_13x65", 13.0 * INCH_M, 6.5 * INCH_M),  # 0.3302 / 0.1651
        )
        for raw_name, diameter_m, pitch_m in cases:
            with self.subTest(raw_name=raw_name):
                model = resolve_uiuc_model(raw_name)
                self.assertAlmostEqual(model.diameter_m, diameter_m, places=9)
                self.assertAlmostEqual(model.pitch_m, pitch_m, places=9)

    def test_sibling_designations_resolve_from_real_filenames(self) -> None:
        cases = (
            ("ancf_12x65_static_0806od.txt", "static_experiment", 12.0 * INCH_M, 6.5 * INCH_M),
            ("ancf_12x65_0807od_3032.txt", "dynamic_experiment", 12.0 * INCH_M, 6.5 * INCH_M),
            ("ancf_13x65_static_0570od.txt", "static_experiment", 13.0 * INCH_M, 6.5 * INCH_M),
        )
        for filename, category, diameter_m, pitch_m in cases:
            with self.subTest(filename=filename):
                raw_model = IngestSession.uiuc_raw_model(Path(filename), category)
                model = resolve_uiuc_model(raw_model)
                self.assertAlmostEqual(model.diameter_m, diameter_m, places=9)
                self.assertAlmostEqual(model.pitch_m, pitch_m, places=9)

    def test_near_miss_inch_designations_unchanged(self) -> None:
        # "12x6" is spec "12 x 6" (not "12 x 6.5") and "12x9" is spec
        # "12 x 9" (not "12.5 x 9"); both must pass through as plain inches.
        cases = (
            ("ancf_12x6", 12.0 * INCH_M, 6.0 * INCH_M),
            ("ancf_12x9", 12.0 * INCH_M, 9.0 * INCH_M),
        )
        for raw_name, diameter_m, pitch_m in cases:
            with self.subTest(raw_name=raw_name):
                model = resolve_uiuc_model(raw_name)
                self.assertAlmostEqual(model.diameter_m, diameter_m, places=9)
                self.assertAlmostEqual(model.pitch_m, pitch_m, places=9)


if __name__ == "__main__":
    unittest.main()
