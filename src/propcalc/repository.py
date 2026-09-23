from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from .database import connect_database, initialize_database


@dataclass(frozen=True)
class CoefficientSample:
    ct: float
    cp: float
    efficiency: float
    evidence_class: str
    source_type: str
    rpm_requested: float
    j_requested: float
    rpm_low: float
    rpm_high: float
    j_low: float
    j_high: float
    extrapolated: bool


class Repository:
    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)
        self.connection = connect_database(self.database_path)
        initialize_database(self.connection)

    def close(self) -> None:
        self.connection.close()

    def clear_caches(self) -> None:
        self._load_curve.cache_clear()

    def summary(self) -> dict[str, int]:
        row = self.connection.execute("SELECT * FROM database_summary").fetchone()
        return dict(row)

    def search_models(self, term: str = "", *, medium: str | None = None, limit: int = 250) -> list[sqlite3.Row]:
        like = f"%{term.strip()}%"
        sql = """SELECT m.*,(SELECT COUNT(*) FROM performance_points p WHERE p.model_id=m.model_id) AS point_count,
                 (SELECT COUNT(*) FROM geometries g WHERE g.model_id=m.model_id) AS geometry_count
                 FROM models m WHERE (m.model_id LIKE ? OR m.original_name LIKE ? OR m.manufacturer LIKE ? OR
                 COALESCE(m.series,'') LIKE ? OR COALESCE(m.sku,'') LIKE ?)"""
        params: list[Any] = [like] * 5
        if medium:
            sql += " AND m.medium=?"
            params.append(medium)
        sql += " ORDER BY CASE WHEN m.has_experiment=1 THEN 0 WHEN m.has_prediction=1 THEN 1 ELSE 2 END,m.manufacturer,m.diameter_m,m.pitch_m LIMIT ?"
        params.append(limit)
        return self.connection.execute(sql, params).fetchall()

    def get_model(self, model_id: str) -> sqlite3.Row | None:
        return self.connection.execute("SELECT * FROM models WHERE model_id=?", (model_id,)).fetchone()

    def model_points(self, model_id: str, limit: int = 1000) -> list[sqlite3.Row]:
        return self.connection.execute(
            """SELECT p.rpm,p.advance_ratio_j,p.speed_m_s,p.ct,p.cp,p.efficiency,p.thrust_n,p.power_w,p.torque_nm,
               p.is_static,p.evidence_class,p.source_type,sf.relative_path
               FROM performance_points p JOIN source_files sf ON sf.source_file_id=p.source_file_id
               WHERE p.model_id=? ORDER BY p.evidence_class,p.rpm,p.advance_ratio_j LIMIT ?""", (model_id, limit)
        ).fetchall()

    def reference_points(self, model_id: str, limit: int = 250) -> list[sqlite3.Row]:
        """Return source rows for the reproducible database-point calculator mode."""
        return self.connection.execute(
            """SELECT p.performance_id,p.rpm,p.advance_ratio_j,p.speed_m_s,p.ct,p.cp,p.efficiency,
                      p.thrust_n,p.power_w,p.torque_nm,p.is_static,p.evidence_class,p.source_type,
                      sf.relative_path,p.source_row
               FROM performance_points p
               JOIN source_files sf ON sf.source_file_id=p.source_file_id
               WHERE p.model_id=? AND p.rpm IS NOT NULL AND p.ct IS NOT NULL AND p.cp IS NOT NULL
               ORDER BY CASE p.evidence_class
                            WHEN 'experiment' THEN 0 WHEN 'prediction' THEN 1
                            WHEN 'cfd' THEN 2 WHEN 'numerical' THEN 3 ELSE 4 END,
                        p.is_static DESC,p.rpm DESC,COALESCE(p.advance_ratio_j,0)
               LIMIT ?""",
            (model_id, limit),
        ).fetchall()

    def get_performance_point(self, performance_id: int, model_id: str | None = None) -> sqlite3.Row | None:
        sql = """SELECT p.performance_id,p.model_id,p.rpm,p.advance_ratio_j,p.speed_m_s,p.ct,p.cp,p.efficiency,
                        p.thrust_n,p.power_w,p.torque_nm,p.is_static,p.evidence_class,p.source_type,
                        sf.relative_path,p.source_row
                 FROM performance_points p
                 JOIN source_files sf ON sf.source_file_id=p.source_file_id
                 WHERE p.performance_id=?"""
        params: list[Any] = [performance_id]
        if model_id is not None:
            sql += " AND p.model_id=?"
            params.append(model_id)
        return self.connection.execute(sql, params).fetchone()

    def nearest_raw_point(self, model_id: str, rpm: float, j: float, evidence: str | None = None) -> sqlite3.Row | None:
        """Return one untouched source row nearest to an operating point.

        This intentionally does not interpolate or derive missing thrust/power values.  It is
        used by the UI to keep a source-data row visibly separate from calculated results.
        """
        params: list[Any] = [model_id]
        evidence_sql = ""
        if evidence and evidence != "none":
            evidence_sql = " AND p.evidence_class=?"
            params.append(evidence)
        static_sql = " AND p.is_static=1" if abs(j) < 1e-9 else " AND p.is_static=0"
        rows = self.connection.execute(
            f"""SELECT p.performance_id,p.rpm,p.advance_ratio_j,p.speed_m_s,p.ct,p.cp,p.efficiency,p.thrust_n,p.power_w,p.torque_nm,
                       p.is_static,p.evidence_class,p.source_type,sf.relative_path,p.source_row
                FROM performance_points p JOIN source_files sf ON sf.source_file_id=p.source_file_id
                WHERE p.model_id=? AND p.rpm IS NOT NULL AND p.ct IS NOT NULL AND p.cp IS NOT NULL
                {evidence_sql}{static_sql}
                ORDER BY ABS(p.rpm-?) / MAX(ABS(?),1.0) +
                         ABS(COALESCE(p.advance_ratio_j,0)-?) / MAX(ABS(?),0.05)
                LIMIT 1""",
            params + [rpm, rpm, j, j],
        ).fetchone()
        if rows is not None:
            return rows
        # Some sources do not mark static/dynamic consistently; keep a documented fallback.
        return self.connection.execute(
            f"""SELECT p.performance_id,p.rpm,p.advance_ratio_j,p.speed_m_s,p.ct,p.cp,p.efficiency,p.thrust_n,p.power_w,p.torque_nm,
                       p.is_static,p.evidence_class,p.source_type,sf.relative_path,p.source_row
                FROM performance_points p JOIN source_files sf ON sf.source_file_id=p.source_file_id
                WHERE p.model_id=? AND p.rpm IS NOT NULL AND p.ct IS NOT NULL AND p.cp IS NOT NULL
                {evidence_sql}
                ORDER BY ABS(p.rpm-?) / MAX(ABS(?),1.0) +
                         ABS(COALESCE(p.advance_ratio_j,0)-?) / MAX(ABS(?),0.05)
                LIMIT 1""",
            params + [rpm, rpm, j, j],
        ).fetchone()

    @lru_cache(maxsize=32)
    def _load_curve(self, model_id: str) -> tuple[str, list[tuple[float, float, float, float, float, str]]]:
        counts = self.connection.execute(
            """SELECT evidence_class,COUNT(*) n FROM performance_points
               WHERE model_id=? AND rpm IS NOT NULL AND advance_ratio_j IS NOT NULL AND ct IS NOT NULL AND cp IS NOT NULL
               GROUP BY evidence_class""", (model_id,)
        ).fetchall()
        preferred = None
        for evidence in ("experiment", "prediction", "cfd", "numerical"):
            if any(row["evidence_class"] == evidence and row["n"] >= 2 for row in counts):
                preferred = evidence
                break
        if preferred is None:
            return "none", []
        rows = self.connection.execute(
            """SELECT rpm,advance_ratio_j,ct,cp,COALESCE(efficiency,0),source_type
               FROM performance_points WHERE model_id=? AND evidence_class=? AND rpm IS NOT NULL
               AND advance_ratio_j IS NOT NULL AND ct IS NOT NULL AND cp IS NOT NULL
               ORDER BY rpm,advance_ratio_j""", (model_id, preferred)
        ).fetchall()
        data = [(float(row[0]), float(row[1]), float(row[2]), float(row[3]), float(row[4]), str(row[5])) for row in rows]
        return preferred, data

    @staticmethod
    def _interp_j(points: list[tuple[float, float, float, float, float, str]], j: float) -> tuple[float, float, float, float, float, str, bool]:
        points = sorted(points, key=lambda item: item[1])
        low = points[0]
        high = points[-1]
        extrapolated = j < low[1] or j > high[1]
        for left, right in zip(points, points[1:]):
            if left[1] <= j <= right[1]:
                low, high = left, right
                break
        if j <= points[0][1]:
            low = high = points[0]
        elif j >= points[-1][1]:
            low = high = points[-1]
        fraction = 0.0 if high[1] == low[1] else (j - low[1]) / (high[1] - low[1])
        values = [low[index] + fraction * (high[index] - low[index]) for index in (2, 3, 4)]
        return values[0], values[1], values[2], low[1], high[1], low[5], extrapolated

    def coefficients(self, model_id: str, rpm: float, j: float) -> CoefficientSample | None:
        # Static data are individual RPM samples rather than J-curves.  Keeping this
        # path separate prevents a J=0 request from being paired with the first
        # non-zero wind-tunnel point of a neighboring dynamic curve.
        if abs(j) < 1e-9:
            for evidence in ("experiment", "prediction", "cfd", "numerical"):
                rows = self.connection.execute(
                    """SELECT rpm,ct,cp,COALESCE(efficiency,0) AS efficiency,source_type
                       FROM performance_points
                       WHERE model_id=? AND evidence_class=? AND is_static=1
                       AND rpm IS NOT NULL AND ct IS NOT NULL AND cp IS NOT NULL
                       ORDER BY rpm""", (model_id, evidence)
                ).fetchall()
                if len(rows) < 2:
                    continue
                low = rows[0]
                high = rows[-1]
                extrapolated = rpm < float(low["rpm"]) or rpm > float(high["rpm"])
                for left, right in zip(rows, rows[1:]):
                    if float(left["rpm"]) <= rpm <= float(right["rpm"]):
                        low, high = left, right
                        break
                if rpm <= float(rows[0]["rpm"]):
                    low = high = rows[0]
                elif rpm >= float(rows[-1]["rpm"]):
                    low = high = rows[-1]
                span = float(high["rpm"]) - float(low["rpm"])
                fraction = 0.0 if span == 0 else (rpm - float(low["rpm"])) / span
                def interpolate(name: str) -> float:
                    return float(low[name]) + fraction * (float(high[name]) - float(low[name]))
                return CoefficientSample(
                    interpolate("ct"), interpolate("cp"), interpolate("efficiency"), evidence,
                    str(low["source_type"]), rpm, 0.0, float(low["rpm"]), float(high["rpm"]),
                    0.0, 0.0, extrapolated,
                )
        evidence, data = self._load_curve(model_id)
        if not data:
            return None
        grouped: dict[float, list[tuple[float, float, float, float, float, str]]] = {}
        for point in data:
            grouped.setdefault(point[0], []).append(point)
        rpms = sorted(grouped)
        rpm_low = rpms[0]
        rpm_high = rpms[-1]
        rpm_extrapolated = rpm < rpm_low or rpm > rpm_high
        for left, right in zip(rpms, rpms[1:]):
            if left <= rpm <= right:
                rpm_low, rpm_high = left, right
                break
        if rpm <= rpms[0]:
            rpm_low = rpm_high = rpms[0]
        elif rpm >= rpms[-1]:
            rpm_low = rpm_high = rpms[-1]
        low_sample = self._interp_j(grouped[rpm_low], j)
        high_sample = self._interp_j(grouped[rpm_high], j)
        fraction = 0.0 if rpm_high == rpm_low else (rpm - rpm_low) / (rpm_high - rpm_low)
        ct = low_sample[0] + fraction * (high_sample[0] - low_sample[0])
        cp = low_sample[1] + fraction * (high_sample[1] - low_sample[1])
        eta = low_sample[2] + fraction * (high_sample[2] - low_sample[2])
        return CoefficientSample(ct, cp, eta, evidence, low_sample[5], rpm, j, rpm_low, rpm_high,
                                 min(low_sample[3], high_sample[3]), max(low_sample[4], high_sample[4]),
                                 rpm_extrapolated or low_sample[6] or high_sample[6])

    def structural_rpm(self, model_id: str) -> sqlite3.Row | None:
        return self.connection.execute(
            "SELECT * FROM rpm_limits WHERE model_id=? ORDER BY rpm_limit_id DESC LIMIT 1", (model_id,)
        ).fetchone()

    def save_build(self, payload: dict[str, Any], build_id: int | None = None) -> int:
        values = (
            payload.get("name") or "Untitled", payload.get("description"), payload.get("propeller_model_id"),
            payload.get("motor_kv"), payload.get("battery_s"), payload.get("battery_capacity_ah"),
            payload.get("esc_current_a"), payload.get("motor_count", 1), payload.get("mass_kg"), payload.get("payload_kg"),
            json.dumps(payload.get("advanced", {}), ensure_ascii=False), payload.get("note"),
        )
        if build_id is None:
            cursor = self.connection.execute(
                """INSERT INTO saved_builds(name,description,propeller_model_id,motor_kv,battery_s,battery_capacity_ah,
                   esc_current_a,motor_count,mass_kg,payload_kg,advanced_json,note) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", values)
            build_id = int(cursor.lastrowid)
        else:
            self.connection.execute(
                """UPDATE saved_builds SET name=?,description=?,propeller_model_id=?,motor_kv=?,battery_s=?,
                   battery_capacity_ah=?,esc_current_a=?,motor_count=?,mass_kg=?,payload_kg=?,advanced_json=?,note=?,
                   updated_at=CURRENT_TIMESTAMP WHERE build_id=?""", values + (build_id,))
        self.connection.execute("DELETE FROM saved_build_components WHERE build_id=?", (build_id,))
        advanced = payload.get("advanced", {})
        components: list[tuple[str, Any, int, dict[str, Any]]] = [
            ("propeller", payload.get("propeller_model_id"), payload.get("motor_count", 1), {}),
            ("motor", advanced.get("motor_name") or "custom motor", payload.get("motor_count", 1),
             {"kv_rpm_per_v": payload.get("motor_kv")}),
            ("battery", advanced.get("battery_name") or "custom battery", 1,
             {"chemistry": advanced.get("battery_type", "LiPo"), "cells_s": payload.get("battery_s"),
              "capacity_ah": payload.get("battery_capacity_ah")}),
            ("esc", advanced.get("esc_name") or "custom ESC", payload.get("motor_count", 1),
             {"current_a": payload.get("esc_current_a")}),
            ("frame", advanced.get("frame_name") or "custom frame", 1, {}),
        ]
        for accessory in advanced.get("accessories", []):
            if not accessory.get("enabled"):
                continue
            quantity = max(1, int(accessory.get("quantity", 1)))
            mass_each_kg = max(0.0, float(accessory.get("mass_kg", 0)))
            category = str(accessory.get("category") or "other")
            reference = str(accessory.get("model") or category)
            components.append((
                "accessory", reference, quantity,
                {"category": category, "mass_each_kg": mass_each_kg,
                 "mass_total_kg": mass_each_kg * quantity, "enabled": True},
            ))
        for component_type, reference, quantity, properties in components:
            self.connection.execute(
                """INSERT INTO saved_build_components(build_id,component_type,component_ref,quantity,properties_json)
                   VALUES(?,?,?,?,?)""",
                (build_id, component_type, reference, int(quantity or 1), json.dumps(properties, ensure_ascii=False)),
            )
        self.connection.commit()
        return build_id

    def builds(self) -> list[sqlite3.Row]:
        return self.connection.execute("SELECT * FROM saved_builds ORDER BY updated_at DESC,name").fetchall()

    def get_build(self, build_id: int) -> sqlite3.Row | None:
        return self.connection.execute("SELECT * FROM saved_builds WHERE build_id=?", (build_id,)).fetchone()

    def delete_build(self, build_id: int) -> None:
        self.connection.execute("DELETE FROM saved_builds WHERE build_id=?", (build_id,))
        self.connection.commit()

    def duplicate_build(self, build_id: int) -> int:
        row = self.get_build(build_id)
        if row is None:
            raise KeyError(build_id)
        payload = dict(row)
        payload["name"] = f"{payload['name']} (copy)"
        payload["advanced"] = json.loads(payload.pop("advanced_json") or "{}")
        return self.save_build(payload)
