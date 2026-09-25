from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from .repository import CoefficientSample, Repository


G = 9.80665


BATTERY_CHEMISTRIES: dict[str, dict[str, float]] = {
    "LiPo": {"nominal_v": 3.7, "full_v": 4.2, "minimum_v": 3.3, "usable_fraction": 0.80,
             "typical_c": 30.0},
    "Li-ion": {"nominal_v": 3.6, "full_v": 4.2, "minimum_v": 3.0, "usable_fraction": 0.85,
               "typical_c": 8.0},
    "LiFePO4": {"nominal_v": 3.2, "full_v": 3.65, "minimum_v": 2.8, "usable_fraction": 0.90,
                "typical_c": 15.0},
}


def battery_spec(chemistry: str) -> dict[str, float]:
    """Return conservative nominal battery data used by the estimate."""
    return BATTERY_CHEMISTRIES.get(chemistry, BATTERY_CHEMISTRIES["LiPo"])


@dataclass
class CalculationInputs:
    model_id: str
    voltage_v: float = 14.8
    throttle: float = 1.0
    motor_kv: float = 900.0
    motor_resistance_ohm: float | None = None
    motor_i0_a: float | None = None
    motor_max_current_a: float | None = None
    motor_max_power_w: float | None = None
    esc_current_a: float = 40.0
    battery_capacity_ah: float = 5.0
    battery_c_rating: float = 30.0
    battery_s: int = 4
    battery_type: str = "LiPo"
    speed_m_s: float = 0.0
    mass_kg: float = 1.5
    motor_count: int = 1
    density_kg_m3: float = 1.225
    medium: str = "air"
    rpm_override: float | None = None
    source_point_id: int | None = None


@dataclass
class OperatingPoint:
    rpm: float = 0.0
    j: float = 0.0
    ct: float = 0.0
    cp: float = 0.0
    thrust_n: float = 0.0
    torque_nm: float = 0.0
    prop_power_w: float = 0.0
    electrical_power_w: float = 0.0
    current_a: float = 0.0
    aero_efficiency: float = 0.0
    system_efficiency: float = 0.0
    motor_efficiency: float = 0.0
    confidence: float = 0.0
    evidence: str = "none"
    source_type: str = ""
    extrapolated: bool = False


@dataclass
class CalculationResult:
    point: OperatingPoint
    total_thrust_n: float
    thrust_to_weight: float
    runtime_min: float
    esc_margin_percent: float
    motor_current_margin_percent: float | None
    motor_power_margin_percent: float | None
    battery_margin_percent: float
    structural_rpm: float | None
    structural_margin_percent: float | None
    optimum: OperatingPoint | None
    recommended_voltage_v: float | None
    recommended_throttle: float | None
    recommended_s: int | None
    missing_parameters: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    trace: list[dict[str, Any]] = field(default_factory=list)


class PropellerCalculator:
    def __init__(self, repository: Repository):
        self.repository = repository

    def _build_point(self, inputs: CalculationInputs, rpm: float, ct: float, cp: float,
                       evidence_class: str, source_type: str, extrapolated: bool,
                       voltage_effective: float) -> OperatingPoint | None:
        model = self.repository.get_model(inputs.model_id)
        if model is None or not model["diameter_m"] or rpm <= 0:
            return None
        diameter = float(model["diameter_m"])
        n = rpm / 60.0
        j = inputs.speed_m_s / (n * diameter) if n > 0 else 0.0
        thrust = ct * inputs.density_kg_m3 * n**2 * diameter**4
        prop_power = cp * inputs.density_kg_m3 * n**3 * diameter**5
        torque = prop_power / (2.0 * math.pi * n) if n > 0 else 0.0
        i0 = inputs.motor_i0_a if inputs.motor_i0_a is not None else 1.0
        if inputs.motor_resistance_ohm and inputs.motor_resistance_ohm > 0:
            back_emf = rpm / inputs.motor_kv
            current = max(i0, (voltage_effective - back_emf) / inputs.motor_resistance_ohm)
        else:
            current = prop_power / max(voltage_effective * 0.82, 0.1) + i0
        electrical = max(0.0, voltage_effective * current)
        motor_eff = min(0.98, max(0.0, prop_power / electrical)) if electrical > 0 else 0.0
        if abs(j) < 1e-9:
            aero = max(0.0, min(1.0, (max(ct, 0.0) ** 1.5) / (math.sqrt(2.0) * cp))) if cp > 0 else 0.0
        else:
            aero = max(0.0, min(1.0, ct * j / cp)) if cp > 0 else 0.0
        system = max(0.0, min(1.0, aero * motor_eff * 0.97))
        base_confidence = {"experiment": 0.94, "prediction": 0.72, "cfd": 0.66, "numerical": 0.60}.get(evidence_class, 0.45)
        confidence = max(0.15, base_confidence - (0.25 if extrapolated else 0.0))
        return OperatingPoint(rpm, j, ct, cp, thrust, torque, prop_power, electrical, current, aero, system,
                              motor_eff, confidence, evidence_class, source_type, extrapolated)

    def _point_from_source_row(self, inputs: CalculationInputs, row: Any,
                               voltage_effective: float) -> OperatingPoint | None:
        """Build an operating point directly from a stored performance row.

        Used when the caller explicitly selects a database point via
        ``source_point_id``. Unlike interpolation, the stored Ct/Cp/RPM are
        reproduced exactly.
        """
        try:
            rpm = float(row["rpm"])
            ct = float(row["ct"])
            cp = float(row["cp"])
        except (TypeError, ValueError, KeyError):
            return None
        evidence_class = str(row["evidence_class"]) if row["evidence_class"] else "none"
        source_type = str(row["source_type"]) if row["source_type"] else ""
        return self._build_point(inputs, rpm, ct, cp, evidence_class, source_type, False, voltage_effective)

    def _point_at_rpm(self, inputs: CalculationInputs, rpm: float, voltage_effective: float) -> OperatingPoint | None:
        model = self.repository.get_model(inputs.model_id)
        if model is None or not model["diameter_m"] or rpm <= 0:
            return None
        diameter = float(model["diameter_m"])
        n = rpm / 60.0
        j = inputs.speed_m_s / (n * diameter) if n > 0 else 0.0
        sample = self.repository.coefficients(inputs.model_id, rpm, j)
        if sample is None:
            return None
        return self._build_point(inputs, rpm, sample.ct, sample.cp, sample.evidence_class,
                                 sample.source_type, sample.extrapolated, voltage_effective)

    def operating_point(self, inputs: CalculationInputs, throttle: float | None = None,
                        voltage: float | None = None) -> OperatingPoint | None:
        direct_source_point = throttle is None and voltage is None and inputs.rpm_override is not None
        throttle = inputs.throttle if throttle is None else throttle
        voltage = inputs.voltage_v if voltage is None else voltage
        effective = max(0.0, voltage * throttle)
        if direct_source_point:
            if inputs.source_point_id is not None:
                row = self.repository.get_performance_point(inputs.source_point_id, inputs.model_id)
                if row is not None:
                    direct = self._point_from_source_row(inputs, row, effective)
                    if direct is not None:
                        return direct
            return self._point_at_rpm(inputs, max(0.0, float(inputs.rpm_override)), effective)
        no_load_rpm = max(0.0, inputs.motor_kv * effective)
        if no_load_rpm <= 0:
            return None
        if not inputs.motor_resistance_ohm or inputs.motor_resistance_ohm <= 0:
            return self._point_at_rpm(inputs, no_load_rpm * 0.80, effective)
        kt = 60.0 / (2.0 * math.pi * inputs.motor_kv)
        i0 = inputs.motor_i0_a or 0.0
        low, high = max(100.0, no_load_rpm * 0.05), no_load_rpm * 0.999
        best: OperatingPoint | None = None
        for _ in range(45):
            rpm = (low + high) / 2.0
            point = self._point_at_rpm(inputs, rpm, effective)
            if point is None:
                return None
            available_current = max(0.0, (effective - rpm / inputs.motor_kv) / inputs.motor_resistance_ohm)
            motor_torque = kt * max(0.0, available_current - i0)
            best = point
            if motor_torque > point.torque_nm:
                low = rpm
            else:
                high = rpm
        return best

    def sweep(self, inputs: CalculationInputs) -> tuple[OperatingPoint | None, float | None, float | None, int | None]:
        best: OperatingPoint | None = None
        best_voltage = None
        best_throttle = None
        best_s = None
        candidate_s = sorted(set(range(max(2, inputs.battery_s - 2), min(12, inputs.battery_s + 2) + 1)))
        for cells in candidate_s:
            voltage = cells * battery_spec(inputs.battery_type)["nominal_v"]
            for step in range(3, 11):
                throttle = step / 10.0
                point = self.operating_point(inputs, throttle, voltage)
                if point is None or point.thrust_n <= 0 or point.current_a <= 0:
                    continue
                if point.thrust_n * max(1, inputs.motor_count) < inputs.mass_kg * G * 1.05:
                    continue
                motors = max(1, inputs.motor_count)
                battery_max_a = inputs.battery_capacity_ah * inputs.battery_c_rating
                if inputs.esc_current_a > 0 and point.current_a > inputs.esc_current_a:
                    continue
                if battery_max_a > 0 and point.current_a * motors > battery_max_a:
                    continue
                rpm_limit = self.repository.structural_rpm(inputs.model_id)
                if rpm_limit and rpm_limit["max_rpm"] and point.rpm > rpm_limit["max_rpm"]:
                    continue
                score = point.system_efficiency
                if best is None or score > best.system_efficiency:
                    best, best_voltage, best_throttle, best_s = point, voltage, throttle, cells
        return best, best_voltage, best_throttle, best_s

    def calculate(self, inputs: CalculationInputs) -> CalculationResult:
        point = self.operating_point(inputs)
        has_operating_point = point is not None
        if point is None:
            point = OperatingPoint()
        total_thrust = point.thrust_n * max(1, inputs.motor_count)
        tw = total_thrust / (max(inputs.mass_kg, 1e-6) * G)
        total_current = point.current_a * max(1, inputs.motor_count)
        chemistry = battery_spec(inputs.battery_type)
        if not has_operating_point or not total_current > 0:
            runtime = float("nan")
        else:
            runtime = inputs.battery_capacity_ah * chemistry["usable_fraction"] / max(total_current, 1e-6) * 60.0
        esc_margin = (inputs.esc_current_a - point.current_a) / max(inputs.esc_current_a, 1e-6) * 100.0
        motor_current_margin = (None if inputs.motor_max_current_a is None or inputs.motor_max_current_a <= 0
                                      else (inputs.motor_max_current_a - point.current_a) / inputs.motor_max_current_a * 100.0)
        motor_power_margin = (None if inputs.motor_max_power_w is None or inputs.motor_max_power_w <= 0
                                    else (inputs.motor_max_power_w - point.prop_power_w) / inputs.motor_max_power_w * 100.0)
        battery_max = inputs.battery_capacity_ah * inputs.battery_c_rating
        battery_margin = (battery_max - total_current) / max(battery_max, 1e-6) * 100.0
        rpm_row = self.repository.structural_rpm(inputs.model_id)
        structural = float(rpm_row["max_rpm"]) if rpm_row and rpm_row["max_rpm"] else None
        structural_margin = (structural - point.rpm) / structural * 100.0 if structural else None
        optimum, recommended_voltage, recommended_throttle, recommended_s = self.sweep(inputs)
        missing = []
        if inputs.motor_resistance_ohm is None:
            missing.append("Rm / motor winding resistance")
        if inputs.motor_i0_a is None:
            missing.append("I0 / no-load current")
        warnings = []
        for _name, _value in (("mass_kg", inputs.mass_kg), ("density_kg_m3", inputs.density_kg_m3),
                              ("voltage_v", inputs.voltage_v), ("throttle", inputs.throttle),
                              ("motor_kv", inputs.motor_kv),
                              ("battery_capacity_ah", inputs.battery_capacity_ah),
                              ("battery_c_rating", inputs.battery_c_rating),
                              ("esc_current_a", inputs.esc_current_a),
                              ("speed_m_s", inputs.speed_m_s)):
            if not math.isfinite(_value):
                warnings.append(f"Non-finite input {_name}; result is not meaningful")
        for _name, _value in (("motor_resistance_ohm", inputs.motor_resistance_ohm),
                              ("motor_max_current_a", inputs.motor_max_current_a),
                              ("motor_max_power_w", inputs.motor_max_power_w)):
            if _value is not None and not math.isfinite(_value):
                warnings.append(f"Non-finite input {_name}; result is not meaningful")
        if inputs.mass_kg <= 0:
            warnings.append("Non-positive mass_kg; T/W uses a guarded minimum and is not meaningful")
        if inputs.density_kg_m3 <= 0:
            warnings.append("Non-positive density_kg_m3; thrust/power scale with density and are not meaningful")
        if inputs.battery_capacity_ah < 0 or inputs.battery_c_rating < 0:
            warnings.append("Negative battery capacity/C-rating; runtime and margins are not meaningful")
        if inputs.motor_resistance_ohm is not None and inputs.motor_resistance_ohm < 0:
            warnings.append("Negative motor_resistance_ohm; result is not meaningful")
        if inputs.motor_max_current_a is not None and inputs.motor_max_current_a < 0:
            warnings.append("Negative motor_max_current_a; margin is not meaningful")
        if inputs.motor_max_power_w is not None and inputs.motor_max_power_w < 0:
            warnings.append("Negative motor_max_power_w; margin is not meaningful")
        if inputs.motor_count <= 0:
            warnings.append("Non-positive motor_count treated as 1")
        if not has_operating_point or not total_current > 0:
            warnings.append("No valid operating point; runtime is not meaningful")
        if missing:
            warnings.append("Simplified-model estimate: missing " + ", ".join(missing))
        if point.extrapolated:
            warnings.append("Operating point is outside a measured/predicted table range; nearest-edge extrapolation used")
        if esc_margin < 0:
            warnings.append("ESC current limit exceeded")
        if battery_margin < 0:
            warnings.append("Battery C-rating current limit exceeded")
        if structural_margin is not None and structural_margin < 0:
            warnings.append("Structural RPM limit exceeded")
        nominal_pack_voltage = inputs.battery_s * chemistry["nominal_v"]
        if nominal_pack_voltage > 0 and abs(inputs.voltage_v - nominal_pack_voltage) / nominal_pack_voltage > 0.12:
            warnings.append(
                f"Battery voltage mismatch: {inputs.voltage_v:.2f} V entered, but {inputs.battery_s}S "
                f"{inputs.battery_type} is about {nominal_pack_voltage:.2f} V nominal")
        model = self.repository.get_model(inputs.model_id)
        if inputs.medium == "water" and model is not None and model["medium"] != "water":
            warnings.append("Water mode uses air-derived dimensionless coefficients; cavitation is not modeled and bench validation is mandatory")
        trace = [
            {"name": "Advance ratio", "formula": "J = V / (n·D)", "value": point.j, "unit": "-"},
            {"name": "Thrust", "formula": "T = Ct·ρ·n²·D⁴", "value": point.thrust_n, "unit": "N/motor"},
            {"name": "Power", "formula": "P = Cp·ρ·n³·D⁵", "value": point.prop_power_w, "unit": "W/motor"},
            {"name": "Torque", "formula": "Q = P/(2πn)", "value": point.torque_nm, "unit": "N·m/motor"},
            {"name": "T/W", "formula": "T_total/(m·g)", "value": tw, "unit": "-"},
            {"name": "Usable battery fraction", "formula": f"chemistry = {inputs.battery_type}",
             "value": chemistry["usable_fraction"], "unit": "-"},
            {"name": "Runtime", "formula": "usable_fraction·Capacity / I_total", "value": runtime, "unit": "min"},
        ]
        return CalculationResult(point, total_thrust, tw, runtime, esc_margin, motor_current_margin,
                                 motor_power_margin, battery_margin, structural, structural_margin, optimum,
                                 recommended_voltage, recommended_throttle, recommended_s, missing, warnings, trace)
