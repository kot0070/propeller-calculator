from __future__ import annotations

import re
from dataclasses import dataclass


INCH_M = 0.0254


UIUC_PREFIXES: dict[str, tuple[str, str]] = {
    "ancf": ("Aeronaut", "Carbon Folding"),
    "ance": ("Aeronaut", "Carbon Electric"),
    "apce": ("APC", "Electric"),
    "apcsp": ("APC", "Sport"),
    "apcsf": ("APC", "Slow Flyer"),
    "apccf": ("APC", "Carbon Folding"),
    "apcff": ("APC", "Free Flight"),
    "apc29ff": ("APC", "29 Free Flight"),
    "gwsdd": ("GWS", "Direct Drive"),
    "gwssf": ("GWS", "Slow Flyer"),
    "grsn": ("Graupner", "Super Nylon"),
    "grcp": ("Graupner", "CAM Prop"),
    "grcsp": ("Graupner", "CAM Speed Prop"),
    "mas": ("Master Airscrew", "Standard"),
    "ma": ("Master Airscrew", "Standard"),
    "magf": ("Master Airscrew", "G/F"),
    "mae": ("Master Airscrew", "Electric"),
    "kyosho": ("Kyosho", "Standard"),
    "kavfk": ("Kavon", "FK"),
    "zin": ("Zingali", "Standard"),
    "rusp": ("Rev Up", "Standard"),
    "da4052": ("UIUC DA4052", "Research propeller"),
    "da4022": ("UIUC DA4022", "Research propeller"),
    "da4002": ("UIUC DA4002", "Research propeller"),
    "nr640": ("UIUC NR640", "Research propeller"),
    "cfnq": ("Crazyflie", "Nano Quadcopter"),
    "kpf": ("KP", "Folding"),
    "pl": ("Plantraco", "Standard"),
    "mi": ("Micro Invent", "Standard"),
    "mit": ("Micro Invent", "Standard"),
    "union": ("Union", "Standard"),
    "ef": ("E-Flite", "Standard"),
    "vp": ("Vapor", "Standard"),
}


@dataclass(frozen=True)
class NormalizedModel:
    model_id: str
    raw_name: str
    manufacturer: str | None
    series: str | None
    diameter_m: float | None
    pitch_m: float | None
    blades: int | None
    rotation: str | None
    medium: str
    rule: str


def clean_token(value: str) -> str:
    value = value.strip().replace("×", "x").replace(" ", "")
    return re.sub(r"[^A-Za-z0-9_.+()\-/x]", "", value)


def format_number(value: float) -> str:
    return f"{value:.4f}".rstrip("0").rstrip(".")


def parse_size(size: str) -> tuple[float | None, float | None]:
    match = re.search(r"(?i)(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)", size)
    if not match:
        return None, None
    return float(match.group(1)), float(match.group(2))


def infer_blades(name: str) -> int | None:
    upper = name.upper().replace(" ", "")
    match = re.search(r"(?:^|-)([23456])(?:B|BLADE)(?:-|$)", upper)
    if match:
        return int(match.group(1))
    match = re.search(r"-([3456])(?:-|$)", upper)
    if match:
        return int(match.group(1))
    return 2 if "X" in upper else None


def infer_rotation(name: str) -> str | None:
    upper = name.upper().replace(" ", "")
    if "REVERSIBLE" in upper or upper.endswith("-R"):
        return "REVERSIBLE"
    if "-LH" in upper or upper.endswith("LH") or upper.endswith("P"):
        return "CW"
    if "-RH" in upper or upper.endswith("RH"):
        return "CCW"
    return None


def normalize_apc(raw_name: str, *, medium: str = "air") -> NormalizedModel:
    clean = clean_token(raw_name).upper()
    diameter_in, pitch_in = parse_size(clean)
    if diameter_in is None:
        model_id = f"APC:{clean or 'UNKNOWN'}"
    else:
        size_match = re.search(r"(?i)\d+(?:\.\d+)?x\d+(?:\.\d+)?", clean)
        assert size_match
        prefix = clean[: size_match.start()]
        suffix = clean[size_match.end() :]
        canonical = f"{format_number(diameter_in)}X{format_number(pitch_in)}"
        model_id = f"APC:{prefix}{canonical}{suffix}"
    series = "Marine" if medium == "water" else "APC"
    return NormalizedModel(
        model_id=model_id,
        raw_name=raw_name,
        manufacturer="APC",
        series=series,
        diameter_m=diameter_in * INCH_M if diameter_in is not None else None,
        pitch_m=pitch_in * INCH_M if pitch_in is not None else None,
        blades=infer_blades(clean),
        rotation=infer_rotation(clean),
        medium=medium,
        rule="APC designation normalized: whitespace/case unified; diameter and pitch retained in inches",
    )


def normalize_uiuc(raw_name: str) -> NormalizedModel:
    raw = raw_name.strip()
    parts = raw.split("_", 1)
    prefix = parts[0].lower()
    designation = parts[1] if len(parts) == 2 else raw
    manufacturer, series = UIUC_PREFIXES.get(prefix, (f"UIUC {prefix.upper()}", "Unmapped UIUC series"))
    diameter_in, pitch_in = parse_size(designation)
    if manufacturer == "APC" and diameter_in is not None:
        suffix = {
            "apce": "E",
            "apcsf": "SF",
            "apccf": "CF",
            "apcsp": "",
            "apcff": "FF",
            "apc29ff": "29FF",
        }.get(prefix, prefix.upper())
        canonical = f"{format_number(diameter_in)}X{format_number(pitch_in)}{suffix}"
        model_id = f"APC:{canonical}"
        rule = f"UIUC prefix {prefix} mapped to APC {series}; size normalized"
    else:
        canonical = re.sub(r"[^A-Z0-9.+-]", "-", designation.upper()).strip("-") or prefix.upper()
        maker = re.sub(r"[^A-Z0-9]+", "-", manufacturer.upper()).strip("-")
        model_id = f"UIUC:{maker}:{canonical}"
        rule = f"UIUC prefix {prefix} mapped to {manufacturer}/{series}"
    return NormalizedModel(
        model_id=model_id,
        raw_name=raw_name,
        manufacturer=manufacturer,
        series=series,
        diameter_m=diameter_in * INCH_M if diameter_in is not None else None,
        pitch_m=pitch_in * INCH_M if pitch_in is not None else None,
        blades=infer_blades(designation),
        rotation=infer_rotation(designation),
        medium="air",
        rule=rule,
    )


def normalize_enola(family: str, raw_name: str, diameter_m: float | None = None) -> NormalizedModel:
    family_clean = family.strip() or "Unknown"
    raw_clean = raw_name.strip()
    if family_clean.upper() == "APC":
        size_match = re.search(r"(?i)(\d+(?:\.\d+)?x\d+(?:\.\d+)?)", raw_clean)
        normalized = normalize_apc(size_match.group(1) if size_match else raw_clean)
        return NormalizedModel(
            **{**normalized.__dict__, "raw_name": raw_name, "diameter_m": diameter_m or normalized.diameter_m,
               "rule": "ENOLA APC family mapped to common APC Model_ID"}
        )
    maker = re.sub(r"[^A-Z0-9]+", "-", family_clean.upper()).strip("-")
    designation = re.sub(r"[^A-Z0-9.+-]+", "-", raw_clean.upper()).strip("-")
    diameter_in, pitch_in = parse_size(raw_clean)
    return NormalizedModel(
        model_id=f"ENOLA:{maker}:{designation}",
        raw_name=raw_name,
        manufacturer=family_clean,
        series="ENOLA database",
        diameter_m=diameter_m if diameter_m is not None else (diameter_in * INCH_M if diameter_in else None),
        pitch_m=pitch_in * INCH_M if pitch_in is not None else None,
        blades=infer_blades(raw_clean),
        rotation=infer_rotation(raw_clean),
        medium="air",
        rule="ENOLA family and model normalized without cross-manufacturer merging",
    )


def compact_apc_alias(raw_name: str) -> str:
    value = clean_token(raw_name).upper().replace(".", "")
    return value
