from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UnitSpec:
    si: str
    imperial: str
    to_imperial: float
    imperial_offset: float = 0.0


SPECS = {
    "length_m": UnitSpec("m", "ft", 3.280839895013123),
    "length_mm": UnitSpec("mm", "in", 0.03937007874015748),
    "mass_kg": UnitSpec("kg", "lb", 2.2046226218487757),
    "mass_g": UnitSpec("g", "oz", 0.035273961949580414),
    "temperature": UnitSpec("°C", "°F", 1.8, 32.0),
    "speed": UnitSpec("m/s", "mph", 2.2369362920544025),
    "force": UnitSpec("N", "lbf", 0.22480894387096263),
    "torque": UnitSpec("N·m", "oz·in", 141.61193227806098),
    "power": UnitSpec("W", "hp", 0.0013410220895950279),
    "pressure": UnitSpec("kPa", "psi", 0.14503773773020923),
    "volume": UnitSpec("L", "US gal", 0.2641720523581484),
}


def from_si(value: float | None, quantity: str, system: str) -> float | None:
    if value is None or system == "SI":
        return value
    spec = SPECS[quantity]
    return value * spec.to_imperial + spec.imperial_offset


def to_si(value: float | None, quantity: str, system: str) -> float | None:
    if value is None or system == "SI":
        return value
    spec = SPECS[quantity]
    return (value - spec.imperial_offset) / spec.to_imperial


def unit_label(quantity: str, system: str) -> str:
    spec = SPECS[quantity]
    return spec.si if system == "SI" else spec.imperial
