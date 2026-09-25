from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import sqlite3
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable

from .database import initialize_database
from .normalization import (
    INCH_M,
    NormalizedModel,
    compact_apc_alias,
    normalize_apc,
    normalize_enola,
    normalize_uiuc,
)


AIR_DENSITY = 1.225
LBF_N = 4.4482216152605
HP_W = 745.6998715822702
IN_LBF_NM = 0.1129848290276167


SOURCE_SPECS = {
    "APC_CATALOG_202602": {
        "name": "APC Product Data File 2026-02",
        "organization": "APC Propellers / Landing Products",
        "source_group": "APC Propellers",
        "source_kind": "catalog",
        "version": "2026-02",
        "source_date": "2026-02",
        "path": Path(r"C:\Users\kot00\Downloads\PROP-DATA-FILE_202602.xlsx"),
        "note": "Manufacturer catalog: dimensions, SKU, category, status and mass; not performance test data.",
    },
    "ENOLA_2026": {
        "name": "ENOLA Propeller Database 2026 (attached Propeller_Database archive)",
        "organization": "ENOLA / archive authors",
        "source_group": "ENOLA Propeller Database 2026",
        "source_kind": "mixed experiment/CFD/geometry",
        "version": "attached 2026 archive",
        "source_date": "2026",
        "path": Path(r"C:\Users\kot00\Downloads\Propeller_Database.zip"),
        "note": "Internal BBDD structure separates experiments, CFD/numerical results, acoustics and geometry.",
    },
    "OTHER_CFD_DATASET": {
        "name": "Attached CFD aircraft configuration dataset",
        "organization": "Unknown (attached Dataset.zip)",
        "source_group": "Other attached sources",
        "source_kind": "CFD airframe/rotor-system",
        "version": "attached 2026",
        "source_date": "2026",
        "path": Path(r"C:\Users\kot00\Downloads\Dataset.zip"),
        "note": "Contains coupled vehicle/rotor CFD rows but no propeller identity or diameter; audited separately.",
    },
    "UIUC_2022": {
        "name": "UIUC Propeller Database Volumes 1-4",
        "organization": "University of Illinois Urbana-Champaign",
        "source_group": "UIUC Propeller Database",
        "source_kind": "physical experiment/geometry",
        "version": "Volumes 1-4 archive",
        "source_date": "2022-06-27",
        "path": Path(r"C:\Users\kot00\Downloads\UIUC-propDB.zip"),
        "note": "UIUC archive README date 2022-06-27; static and wind-tunnel measurements are physical experiments.",
    },
    "APC_RPM_REV5": {
        "name": "APC Propeller RPM Limits Rev 5",
        "organization": "APC Propellers / Landing Products",
        "source_group": "APC Propellers",
        "source_kind": "structural RPM limits",
        "version": "Rev 5",
        "source_date": "2022-03-23",
        "path": Path(r"C:\Users\kot00\Downloads\APC-Propeller-RPM-Limits-rev5.pdf"),
        "note": "Manufacturer structural speed specification; rules are coefficient divided by propeller diameter in inches.",
    },
    "APC_PERFILES_202602": {
        "name": "APC PERFILES performance predictions 2026-02",
        "organization": "APC Propellers / Landing Products",
        "source_group": "APC Propellers",
        "source_kind": "manufacturer numerical prediction",
        "version": "v2025-1001 / simulation 2026-02-24",
        "source_date": "2026-02-24",
        "path": Path(r"C:\Users\kot00\Downloads\PERFILES_WEB-202602.zipx"),
        "note": "Manufacturer performance predictions; explicitly not classified as physical experiments.",
    },
    "APC_PE0_202602": {
        "name": "APC PE0 geometry files 2026-02",
        "organization": "APC Propellers / Landing Products",
        "source_group": "APC Propellers",
        "source_kind": "manufacturer geometry",
        "version": "v2025-1001 / 2026-02-24",
        "source_date": "2026-02-24",
        "path": Path(r"C:\Users\kot00\Downloads\PE0-FILES_WEB-202602.zipx"),
        "note": "Manufacturer blade geometry and section summaries; not performance measurements.",
    },
}


EXTRACTION_LABEL_TO_SOURCE = {
    "Propeller_Database": "ENOLA_2026",
    "Dataset": "OTHER_CFD_DATASET",
    "UIUC-propDB": "UIUC_2022",
    "APC_PERFILES_202602": "APC_PERFILES_202602",
    "APC_PE0_202602": "APC_PE0_202602",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest().upper()


def read_text(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def count_lines(text: str) -> int:
    if not text:
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)


def float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text or text.lower() in {"na", "n/a", "nan", "-"}:
        return None
    try:
        result = float(text)
    except ValueError:
        return None
    return result if math.isfinite(result) else None


def xml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


# UIUC volume-2 micro-prop designations are millimetres (the spec page prints
# them with an explicit "mm" suffix, e.g. "140 mm X 45 mm"), while some
# UIUC volume-3 Aeronaut filenames drop the decimal point of half-inch sizes
# (spec "12.5 x 7.5" is filed as "125x75"). normalize_uiuc() in
# normalization.py treats every designation as inches, so the affected
# designations are corrected here at the ingest boundary. Reference
# (read-only):
#   work/extracted/UIUC-propDB/UIUC-propDB/volume-2/propDB-volume-2.html
#   work/extracted/UIUC-propDB/UIUC-propDB/volume-3/propDB-volume-3.html
_UIUC_MM_DESIGNATIONS: dict[str, tuple[float, float]] = {
    # filename designation key -> (diameter_mm, pitch_mm)
    "140x45": (140.0, 45.0),  # vp  (Vapor):      spec "140 mm X 45 mm"
    "100x80": (100.0, 80.0),  # pl  (Plantraco):  spec "100 mm X 80 mm"
    "96x70": (96.0, 70.0),  # kpf (KP folding): spec "96 mm X 70 mm"
    "130x70": (130.0, 70.0),  # ef  (E-Flite):    spec "130 mm X 70 mm"
    "57x20": (57.0, 20.0),  # pl  (Plantraco):  spec "57 mm X 20mm"
}

_UIUC_DOTTED_INCH_DESIGNATIONS: dict[str, tuple[float, float]] = {
    # filename designation key -> (diameter_in, pitch_in); the spec page
    # prints these with a decimal point but the data files drop it.
    "125x75": (12.5, 7.5),  # ancf (Aeronaut): spec "12.5 x 7.5"
    "125x9": (12.5, 9.0),  # ancf (Aeronaut): spec "12.5 x 9"
    "125x6": (12.5, 6.0),  # ancf (Aeronaut): spec "12.5 x 6"
    "12x65": (12.0, 6.5),  # ancf (Aeronaut): spec "12 x 6.5"
    "13x65": (13.0, 6.5),  # ancf (Aeronaut): spec "13 x 6.5"
}


def resolve_uiuc_model(raw_name: str) -> NormalizedModel:
    """Resolve a UIUC raw model name to dimensions, correcting the two
    filename conventions normalize_uiuc() misreads as inches."""
    model = normalize_uiuc(raw_name)
    match = re.search(r"(?i)(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)", raw_name)
    if not match:
        return model
    key = f"{match.group(1)}x{match.group(2)}".lower()
    if key in _UIUC_MM_DESIGNATIONS:
        diameter_mm, pitch_mm = _UIUC_MM_DESIGNATIONS[key]
        return NormalizedModel(
            **{**asdict(model), "diameter_m": diameter_mm / 1000.0, "pitch_m": pitch_mm / 1000.0,
               "rule": model.rule + "; UIUC mm designation corrected at ingest (spec labels carry explicit mm)"}
        )
    if key in _UIUC_DOTTED_INCH_DESIGNATIONS:
        diameter_in, pitch_in = _UIUC_DOTTED_INCH_DESIGNATIONS[key]
        return NormalizedModel(
            **{**asdict(model), "diameter_m": diameter_in * INCH_M, "pitch_m": pitch_in * INCH_M,
               "rule": model.rule + "; UIUC dropped-decimal inch designation corrected at ingest (spec prints decimal point)"}
        )
    return model


def column_index(reference: str) -> int:
    letters = re.match(r"[A-Z]+", reference.upper())
    if not letters:
        return 0
    value = 0
    for char in letters.group(0):
        value = value * 26 + ord(char) - 64
    return value - 1


def read_xlsx_rows(path: Path, sheet_name: str) -> list[list[Any]]:
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
          "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
          "p": "http://schemas.openxmlformats.org/package/2006/relationships"}
    with zipfile.ZipFile(path) as archive:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall("m:si", ns):
                shared.append("".join(node.text or "" for node in item.iter() if xml_local_name(node.tag) == "t"))
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        rel_map = {node.attrib["Id"]: node.attrib["Target"] for node in relationships}
        target = None
        for sheet in workbook.findall("m:sheets/m:sheet", ns):
            if sheet.attrib.get("name") == sheet_name:
                target = rel_map[sheet.attrib[f"{{{ns['r']}}}id"]]
                break
        if target is None:
            raise KeyError(f"Worksheet not found: {sheet_name}")
        target = target.lstrip("/")
        if not target.startswith("xl/"):
            target = "xl/" + target
        sheet_root = ET.fromstring(archive.read(target))
        rows: list[list[Any]] = []
        for row in sheet_root.findall(".//m:sheetData/m:row", ns):
            values: list[Any] = []
            for cell in row.findall("m:c", ns):
                index = column_index(cell.attrib.get("r", "A1"))
                while len(values) <= index:
                    values.append(None)
                data_type = cell.attrib.get("t")
                value_node = cell.find("m:v", ns)
                if data_type == "inlineStr":
                    inline = cell.find("m:is", ns)
                    value: Any = "".join(node.text or "" for node in inline.iter() if xml_local_name(node.tag) == "t") if inline is not None else ""
                elif value_node is None:
                    value = None
                elif data_type == "s":
                    value = shared[int(value_node.text or "0")]
                elif data_type in {"str", "b"}:
                    value = value_node.text
                else:
                    value = float_or_none(value_node.text)
                values[index] = value
            rows.append(values)
        return rows


class IngestSession:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        self.source_ids: dict[str, int] = {}
        self.source_files: dict[tuple[str, str], tuple[int, Path]] = {}
        self.apc_aliases: dict[str, NormalizedModel] = {}
        self.stats = Counter()
        self.initialize()

    def initialize(self) -> None:
        initialize_database(self.connection)

    def register_sources(self) -> None:
        for code, spec in SOURCE_SPECS.items():
            path: Path = spec["path"]
            sha = sha256_file(path)
            self.connection.execute(
                """INSERT INTO sources(code,name,organization,source_group,source_kind,version,source_date,
                   archive_name,archive_sha256,archive_bytes,provenance_note)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(code) DO UPDATE SET name=excluded.name,organization=excluded.organization,
                   source_group=excluded.source_group,source_kind=excluded.source_kind,version=excluded.version,
                   source_date=excluded.source_date,archive_name=excluded.archive_name,
                   archive_sha256=excluded.archive_sha256,archive_bytes=excluded.archive_bytes,
                   provenance_note=excluded.provenance_note""",
                (code, spec["name"], spec["organization"], spec["source_group"], spec["source_kind"],
                 spec["version"], spec["source_date"], path.name, sha, path.stat().st_size, spec["note"]),
            )
            self.source_ids[code] = self.connection.execute("SELECT source_id FROM sources WHERE code=?", (code,)).fetchone()[0]

    def register_file(self, code: str, relative_path: str, path: Path, sha: str | None = None,
                      expected_bytes: int | None = None) -> int:
        source_id = self.source_ids[code]
        sha = sha or sha256_file(path)
        size = expected_bytes if expected_bytes is not None else path.stat().st_size
        extension = path.suffix.lower() or "[no extension]"
        self.connection.execute(
            """INSERT INTO source_files(source_id,relative_path,sha256,file_bytes,extension,status)
               VALUES(?,?,?,?,?,'pending')
               ON CONFLICT(source_id,relative_path) DO UPDATE SET sha256=excluded.sha256,
               file_bytes=excluded.file_bytes,extension=excluded.extension""",
            (source_id, relative_path.replace("\\", "/"), sha, size, extension),
        )
        file_id = self.connection.execute(
            "SELECT source_file_id FROM source_files WHERE source_id=? AND relative_path=?",
            (source_id, relative_path.replace("\\", "/")),
        ).fetchone()[0]
        self.source_files[(code, relative_path.replace("\\", "/"))] = (file_id, path)
        return file_id

    def register_source_files(self, extraction_manifest: Path) -> None:
        records = json.loads(extraction_manifest.read_text(encoding="utf-8"))["records"]
        roots: dict[str, Path] = {}
        for record in records:
            label = record.get("source")
            code = EXTRACTION_LABEL_TO_SOURCE.get(label)
            if not code or record.get("status") != "extracted":
                continue
            path = Path(record["path"])
            if label not in roots:
                roots[label] = next(parent for parent in path.parents if parent.name == label)
            relative = path.relative_to(roots[label]).as_posix()
            self.register_file(code, relative, path, record.get("sha256"), record.get("actual_bytes"))
        for code in ("APC_CATALOG_202602", "APC_RPM_REV5"):
            path = SOURCE_SPECS[code]["path"]
            self.register_file(code, path.name, path)

    def update_file(self, file_id: int, *, status: str, category: str, parser: str,
                    raw_lines: int | None = None, raw_rows: int = 0, parsed: int = 0,
                    reason: str | None = None, error: str | None = None) -> None:
        self.connection.execute(
            """UPDATE source_files SET status=?,category=?,parser_name=?,raw_line_count=?,raw_data_rows=?,
               parsed_records=?,skip_reason=?,parse_error=? WHERE source_file_id=?""",
            (status, category, parser, raw_lines, raw_rows, parsed, reason, error, file_id),
        )

    def ensure_model(self, model: NormalizedModel, **extra: Any) -> None:
        values = {
            "sku": extra.get("sku"),
            "catalog_status": extra.get("catalog_status"),
            "catalog_description": extra.get("catalog_description"),
            "weight_kg": extra.get("weight_kg"),
            "has_experiment": int(bool(extra.get("has_experiment"))),
            "has_prediction": int(bool(extra.get("has_prediction"))),
            "has_cfd": int(bool(extra.get("has_cfd"))),
            "has_geometry": int(bool(extra.get("has_geometry"))),
        }
        self.connection.execute(
            """INSERT INTO models(model_id,original_name,manufacturer,series,diameter_m,pitch_m,blade_count,
               rotation,medium,sku,catalog_status,catalog_description,weight_kg,has_experiment,
               has_prediction,has_cfd,has_geometry)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(model_id) DO UPDATE SET
               manufacturer=COALESCE(models.manufacturer,excluded.manufacturer),
               series=CASE WHEN models.series IS NULL OR models.series='APC' THEN COALESCE(excluded.series,models.series) ELSE models.series END,
               diameter_m=COALESCE(models.diameter_m,excluded.diameter_m),pitch_m=COALESCE(models.pitch_m,excluded.pitch_m),
               blade_count=COALESCE(models.blade_count,excluded.blade_count),rotation=COALESCE(models.rotation,excluded.rotation),
               medium=CASE WHEN models.medium='unknown' THEN excluded.medium ELSE models.medium END,
               sku=COALESCE(excluded.sku,models.sku),catalog_status=COALESCE(excluded.catalog_status,models.catalog_status),
               catalog_description=COALESCE(excluded.catalog_description,models.catalog_description),
               weight_kg=COALESCE(excluded.weight_kg,models.weight_kg),
               has_experiment=MAX(models.has_experiment,excluded.has_experiment),
               has_prediction=MAX(models.has_prediction,excluded.has_prediction),has_cfd=MAX(models.has_cfd,excluded.has_cfd),
               has_geometry=MAX(models.has_geometry,excluded.has_geometry),updated_at=CURRENT_TIMESTAMP""",
            (model.model_id, model.raw_name, model.manufacturer, model.series, model.diameter_m, model.pitch_m,
             model.blades, model.rotation, model.medium, values["sku"], values["catalog_status"],
             values["catalog_description"], values["weight_kg"], values["has_experiment"],
             values["has_prediction"], values["has_cfd"], values["has_geometry"]),
        )

    def map_model(self, source_code: str, model: NormalizedModel) -> None:
        self.ensure_model(model)
        self.connection.execute(
            """INSERT INTO model_raw_mappings(source_id,raw_name,model_id,normalization_rule) VALUES(?,?,?,?)
               ON CONFLICT(source_id,raw_name) DO UPDATE SET model_id=excluded.model_id,
               normalization_rule=excluded.normalization_rule""",
            (self.source_ids[source_code], model.raw_name, model.model_id, model.rule),
        )

    def upsert_performance(self, source_code: str, relative_path: str, model: NormalizedModel,
                           source_row: int, values: dict[str, Any], raw_row: str,
                           evidence: str, source_type: str) -> str:
        file_id = self.source_files[(source_code, relative_path)][0]
        content = {
            "model_id": model.model_id, "row": source_row, "values": values,
            "evidence": evidence, "source_type": source_type,
        }
        content_hash = stable_hash(content)
        point_key = stable_hash([source_code, relative_path, model.model_id, source_row])
        existing = self.connection.execute(
            "SELECT content_hash FROM performance_points WHERE point_key=?", (point_key,)
        ).fetchone()
        status = "added" if existing is None else ("skipped" if existing[0] == content_hash else "updated")
        self.connection.execute(
            """INSERT INTO performance_points(point_key,model_id,original_name,manufacturer,series,diameter_m,
               pitch_m,blade_count,rotation,medium,rpm,advance_ratio_j,speed_m_s,ct,cp,efficiency,thrust_n,
               power_w,torque_nm,density_kg_m3,is_static,source_type,evidence_class,source_file_id,source_version,
               source_row,raw_row,content_hash)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(point_key) DO UPDATE SET rpm=excluded.rpm,advance_ratio_j=excluded.advance_ratio_j,
               speed_m_s=excluded.speed_m_s,ct=excluded.ct,cp=excluded.cp,efficiency=excluded.efficiency,
               thrust_n=excluded.thrust_n,power_w=excluded.power_w,torque_nm=excluded.torque_nm,
               density_kg_m3=excluded.density_kg_m3,is_static=excluded.is_static,source_type=excluded.source_type,
               evidence_class=excluded.evidence_class,raw_row=excluded.raw_row,content_hash=excluded.content_hash,
               updated_at=CURRENT_TIMESTAMP""",
            (point_key, model.model_id, model.raw_name, model.manufacturer, model.series, model.diameter_m,
             model.pitch_m, model.blades, model.rotation, model.medium, values.get("rpm"), values.get("j"),
             values.get("speed_m_s"), values.get("ct"), values.get("cp"), values.get("efficiency"),
             values.get("thrust_n"), values.get("power_w"), values.get("torque_nm"), values.get("density", AIR_DENSITY),
             int(bool(values.get("is_static"))), source_type, evidence, file_id, SOURCE_SPECS[source_code]["version"],
             source_row, raw_row, content_hash),
        )
        self.stats[f"performance_{status}"] += 1
        return status

    def upsert_geometry(self, source_code: str, relative_path: str, model: NormalizedModel,
                        source_row: int | None, station_index: int | None, kind: str,
                        values: dict[str, Any]) -> str:
        file_id = self.source_files[(source_code, relative_path)][0]
        content_hash = stable_hash(values)
        geometry_key = stable_hash([source_code, relative_path, model.model_id, source_row, kind])
        existing = self.connection.execute("SELECT content_hash FROM geometries WHERE geometry_key=?", (geometry_key,)).fetchone()
        status = "added" if existing is None else ("skipped" if existing[0] == content_hash else "updated")
        self.connection.execute(
            """INSERT INTO geometries(geometry_key,model_id,original_name,geometry_kind,station_index,radius_ratio,
               radius_m,chord_ratio,chord_m,twist_deg,sweep_deg,thickness_ratio,source_file_id,source_row,raw_json,content_hash)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(geometry_key) DO UPDATE SET radius_ratio=excluded.radius_ratio,radius_m=excluded.radius_m,
               chord_ratio=excluded.chord_ratio,chord_m=excluded.chord_m,twist_deg=excluded.twist_deg,
               sweep_deg=excluded.sweep_deg,thickness_ratio=excluded.thickness_ratio,raw_json=excluded.raw_json,
               content_hash=excluded.content_hash,updated_at=CURRENT_TIMESTAMP""",
            (geometry_key, model.model_id, model.raw_name, kind, station_index, values.get("radius_ratio"),
             values.get("radius_m"), values.get("chord_ratio"), values.get("chord_m"), values.get("twist_deg"),
             values.get("sweep_deg"), values.get("thickness_ratio"), file_id, source_row,
             json.dumps(values, ensure_ascii=False, sort_keys=True), content_hash),
        )
        self.stats[f"geometry_{status}"] += 1
        return status

    def ingest_apc_catalog(self) -> None:
        code = "APC_CATALOG_202602"
        relative = SOURCE_SPECS[code]["path"].name
        file_id, path = self.source_files[(code, relative)]
        rows = read_xlsx_rows(path, "PRODUCT LIST")
        if not rows:
            self.update_file(file_id, status="error", category="catalog", parser="xlsx-ooxml",
                             error="PRODUCT LIST worksheet is empty")
            return
        header = [str(value).strip() if value is not None else "" for value in rows[0]]
        by_name = {name: index for index, name in enumerate(header)}
        imported = 0
        skipped = 0
        for row_number, row in enumerate(rows[1:], start=2):
            def get(name: str) -> Any:
                index = by_name.get(name)
                return row[index] if index is not None and index < len(row) else None

            raw_name = str(get("Product Name") or "").strip()
            diameter = float_or_none(get("Diameter (INCHES)"))
            pitch = float_or_none(get("Pitch (INCHES)"))
            if not raw_name or diameter is None or pitch is None:
                skipped += 1
                continue
            model = normalize_apc(raw_name)
            if model.diameter_m is None or model.pitch_m is None:
                clean_model = NormalizedModel(
                    **{**asdict(model), "diameter_m": diameter * INCH_M, "pitch_m": pitch * INCH_M}
                )
                model = clean_model
            weight_g = float_or_none(get("Product Weight (NOT for Shipping Calculations) (grams) "))
            description = str(get("Product Description") or "").strip() or None
            categories = str(get("Categories") or "").strip() or None
            series = categories or model.series
            model = NormalizedModel(**{**asdict(model), "series": series})
            self.ensure_model(
                model,
                sku=str(get("Product Code (SKU)") or "").strip() or None,
                catalog_status=str(get("Status") or "").strip() or None,
                catalog_description=description,
                weight_kg=(weight_g / 1000.0 if weight_g is not None else None),
            )
            self.map_model(code, model)
            self.apc_aliases[compact_apc_alias(raw_name)] = model
            imported += 1
        self.update_file(
            file_id, status="imported", category="catalog", parser="xlsx-ooxml:PRODUCT LIST",
            raw_lines=len(rows), raw_rows=max(0, len(rows) - 1), parsed=imported,
            reason=(f"{skipped} rows lacked propeller name/diameter/pitch" if skipped else None),
        )

    @staticmethod
    def uiuc_raw_model(path: Path, category: str) -> str:
        base = path.stem
        if category == "geometry":
            return re.sub(r"_geom$", "", base, flags=re.IGNORECASE)
        if category == "thickness_geometry":
            return re.sub(r"_thick$", "", base, flags=re.IGNORECASE)
        if category == "static_experiment":
            return re.split(r"_static_", base, maxsplit=1, flags=re.IGNORECASE)[0]
        match = re.match(r"^(.*)_[^_]+_(\d{3,6})$", base)
        return match.group(1) if match else base

    @staticmethod
    def uiuc_derived(model: NormalizedModel, rpm: float | None, j: float | None,
                     ct: float | None, cp: float | None) -> dict[str, float | None]:
        values: dict[str, float | None] = {"speed_m_s": None, "thrust_n": None, "power_w": None, "torque_nm": None}
        if model.diameter_m is None or rpm is None:
            return values
        n = rpm / 60.0
        if n <= 0:
            return values
        if j is not None:
            values["speed_m_s"] = j * n * model.diameter_m
        if ct is not None:
            values["thrust_n"] = ct * AIR_DENSITY * n**2 * model.diameter_m**4
        if cp is not None:
            values["power_w"] = cp * AIR_DENSITY * n**3 * model.diameter_m**5
            values["torque_nm"] = values["power_w"] / (2.0 * math.pi * n)
        return values

    def ingest_uiuc(self) -> None:
        code = "UIUC_2022"
        for (source_code, relative), (file_id, path) in sorted(self.source_files.items()):
            if source_code != code or path.suffix.lower() != ".txt":
                continue
            text = read_text(path)
            lines = text.splitlines()
            nonempty = [(index, line.strip()) for index, line in enumerate(lines) if line.strip()]
            header_index, first = nonempty[0] if nonempty else (0, "")
            for candidate_index, candidate in nonempty[:4]:
                lower_candidate = re.sub(r"\s+", " ", candidate.lower())
                if (("ct" in lower_candidate and "cp" in lower_candidate and ("rpm" in lower_candidate or re.search(r"\bj\b", lower_candidate)))
                        or ("r/r" in lower_candidate and ("c/r" in lower_candidate or "t/c" in lower_candidate))):
                    header_index, first = candidate_index, candidate
                    break
            normalized_header = re.sub(r"\s+", " ", first.lower())
            if re.search(r"\brpm\b", normalized_header) and "ct" in normalized_header and "cp" in normalized_header:
                category = "static_experiment"
            elif re.search(r"\bj\b", normalized_header) and "ct" in normalized_header and "cp" in normalized_header:
                category = "dynamic_experiment"
            elif "r/r" in normalized_header and "c/r" in normalized_header and ("beta" in normalized_header or "twist" in normalized_header):
                category = "geometry"
            elif "r/r" in normalized_header and "t/c" in normalized_header:
                category = "thickness_geometry"
            else:
                if path.name.lower() == "readme.txt":
                    self.update_file(file_id, status="recognized_not_imported", category="documentation",
                                     parser="text-classifier", raw_lines=len(lines), reason="UIUC archive README; provenance only")
                else:
                    self.update_file(file_id, status="unrecognized", category="unknown_text", parser="uiuc-text",
                                     raw_lines=len(lines), reason="TXT header does not match UIUC performance or geometry schema")
                continue
            raw_model = self.uiuc_raw_model(path, category)
            model = resolve_uiuc_model(raw_model)
            if category in {"geometry", "thickness_geometry"}:
                self.ensure_model(model, has_geometry=True)
                self.map_model(code, model)
                parsed = 0
                for source_row, line in enumerate(lines[header_index + 1:], start=header_index + 2):
                    tokens = line.split()
                    required = 2 if category == "thickness_geometry" else 3
                    if len(tokens) < required:
                        continue
                    values = [float_or_none(token) for token in tokens[:required]]
                    if any(value is None for value in values):
                        continue
                    radius_ratio = values[0]
                    chord_ratio = values[1] if category == "geometry" else None
                    twist_deg = values[2] if category == "geometry" else None
                    self.upsert_geometry(
                        code, relative, model, source_row, parsed, "blade_thickness" if category == "thickness_geometry" else "blade_definition",
                        {"radius_ratio": radius_ratio, "radius_m": radius_ratio * model.diameter_m / 2 if model.diameter_m else None,
                         "chord_ratio": chord_ratio, "chord_m": chord_ratio * model.diameter_m if chord_ratio is not None and model.diameter_m else None,
                         "twist_deg": twist_deg, "thickness_ratio": values[1] if category == "thickness_geometry" else None,
                         "source": "UIUC measured geometry"},
                    )
                    parsed += 1
                self.update_file(file_id, status="imported" if parsed else "error", category="geometry",
                                 parser="uiuc-geometry-v1", raw_lines=len(lines), raw_rows=max(0, len(lines)-header_index-1),
                                 parsed=parsed, error=None if parsed else "No numeric geometry rows")
                continue
            self.ensure_model(model, has_experiment=True)
            self.map_model(code, model)
            rpm_from_name = None
            if category == "dynamic_experiment":
                match = re.search(r"_(\d{3,6})$", path.stem)
                rpm_from_name = float(match.group(1)) if match else None
                for prefix_line in lines[:header_index]:
                    average_match = re.search(r"RPM\s+average\s*=\s*([0-9.]+)", prefix_line, re.IGNORECASE)
                    if average_match:
                        rpm_from_name = float(average_match.group(1))
                        break
            parsed = 0
            for source_row, line in enumerate(lines[header_index + 1:], start=header_index + 2):
                tokens = line.split()
                if category == "static_experiment":
                    if len(tokens) < 3:
                        continue
                    rpm, ct, cp = (float_or_none(token) for token in tokens[:3])
                    j, efficiency = 0.0, 0.0
                else:
                    if len(tokens) < 4:
                        continue
                    j, ct, cp, efficiency = (float_or_none(token) for token in tokens[:4])
                    rpm = rpm_from_name
                if ct is None or cp is None or (category == "static_experiment" and rpm is None):
                    continue
                derived = self.uiuc_derived(model, rpm, j, ct, cp)
                values = {"rpm": rpm, "j": j, "ct": ct, "cp": cp, "efficiency": efficiency,
                          "density": AIR_DENSITY, "is_static": category == "static_experiment", **derived}
                self.upsert_performance(code, relative, model, source_row, values, line, "experiment",
                                        "UIUC physical wind-tunnel experiment")
                parsed += 1
            self.update_file(file_id, status="imported" if parsed else "error", category=category,
                             parser="uiuc-performance-v1", raw_lines=len(lines), raw_rows=max(0, len(lines)-header_index-1),
                             parsed=parsed, error=None if parsed else "No numeric performance rows")

    def resolve_apc_prediction_model(self, raw_name: str, medium: str) -> NormalizedModel:
        alias = self.apc_aliases.get(compact_apc_alias(raw_name))
        if alias is not None:
            if medium == alias.medium:
                return NormalizedModel(**{**asdict(alias), "raw_name": raw_name,
                                          "rule": "APC prediction filename matched compacted APC catalog designation"})
            return NormalizedModel(**{**asdict(alias), "raw_name": raw_name, "medium": medium,
                                      "rule": "APC prediction filename matched compacted APC catalog designation; marine medium retained"})
        clean = raw_name.replace("_", "")
        match = re.search(r"(?i)(\d+)x(\d+)", clean)
        if match:
            d_token, p_token = match.group(1), match.group(2)
            def decode(token: str, *, diameter: bool) -> str:
                number = int(token)
                if "." in token:
                    return token
                if diameter:
                    if len(token) == 2 and number < 60:
                        return str(number) if number >= 10 else f"{number/10:g}"
                    if len(token) == 3:
                        return f"{number/10:g}" if number >= 100 else f"{number/100:g}"
                else:
                    if number > 30:
                        return f"{number/10:g}"
                return str(number)
            decoded = clean[:match.start()] + decode(d_token, diameter=True) + "x" + decode(p_token, diameter=False) + clean[match.end():]
            model = normalize_apc(decoded, medium=medium)
            return NormalizedModel(**{**asdict(model), "raw_name": raw_name,
                                      "rule": "APC compact prediction filename decoded heuristically; no catalog alias"})
        return normalize_apc(raw_name, medium=medium)

    def ingest_apc_predictions(self) -> None:
        code = "APC_PERFILES_202602"
        for (source_code, relative), (file_id, path) in sorted(self.source_files.items()):
            if source_code != code:
                continue
            text = read_text(path)
            lines = text.splitlines()
            name_match = re.match(r"(?i)PER3_(.+)\.dat$", path.name)
            if not name_match:
                category = "prediction_summary" if path.name.upper().startswith("PER2_") else "unknown_dat"
                reason_map = {
                    "PER2_MAXPE.DAT": "Aggregate maximum-efficiency table derived from per-model PER3 files; retained for audit, not duplicated.",
                    "PER2_N100.DAT": "APC reference/aggregate table; not a per-model performance curve.",
                    "PER2_RPMRANGE.DAT": "APC numerical prediction RPM validity-range metadata; distinct from structural RPM limits.",
                    "PER2_STATIC-1.DAT": "Aggregate static prediction table duplicated by J=0 rows in per-model PER3 files.",
                    "PER2_STATIC-2.DAT": "Aggregate static prediction table duplicated by J=0 rows in per-model PER3 files.",
                    "PER2_TITLEDAT.DAT": "APC prediction title/reference metadata; no per-model curve rows.",
                }
                reason = reason_map.get(path.name.upper(), "DAT filename is not a supported per-model PER3 performance file")
                self.update_file(file_id, status="recognized_not_imported" if category == "prediction_summary" else "unrecognized",
                                 category=category, parser="apc-dat-classifier", raw_lines=len(lines), reason=reason)
                continue
            raw_name = name_match.group(1)
            medium = "water" if "PERFILES2-MARINE" in relative.upper() else "air"
            model = self.resolve_apc_prediction_model(raw_name, medium)
            self.ensure_model(model, has_prediction=True)
            self.map_model(code, model)
            current_rpm: float | None = None
            parsed = 0
            raw_rows = 0
            for source_row, line in enumerate(lines, start=1):
                rpm_match = re.search(r"PROP RPM\s*=\s*([0-9.]+)", line, re.IGNORECASE)
                if rpm_match:
                    current_rpm = float(rpm_match.group(1))
                    continue
                if current_rpm is None:
                    continue
                tokens = line.split()
                if len(tokens) < 15:
                    continue
                nums = [float_or_none(token) for token in tokens[:15]]
                if any(value is None for value in nums):
                    continue
                raw_rows += 1
                speed_mph, j, efficiency, ct, cp, _hp, _torque_imperial, _thrust_imperial, power_w, torque_nm, thrust_n = nums[:11]
                values = {"rpm": current_rpm, "j": j, "speed_m_s": speed_mph * 0.44704, "ct": ct, "cp": cp,
                          "efficiency": efficiency, "thrust_n": thrust_n, "power_w": power_w, "torque_nm": torque_nm,
                          "density": AIR_DENSITY, "is_static": abs(j or 0.0) < 1e-12}
                self.upsert_performance(code, relative, model, source_row, values, line, "prediction",
                                        "APC manufacturer numerical prediction")
                parsed += 1
            self.update_file(file_id, status="imported" if parsed else "error", category="performance_prediction",
                             parser="apc-per3-v1", raw_lines=len(lines), raw_rows=raw_rows, parsed=parsed,
                             error=None if parsed else "No supported PER3 numeric rows")

    def ingest_apc_geometry(self) -> None:
        code = "APC_PE0_202602"
        for (source_code, relative), (file_id, path) in sorted(self.source_files.items()):
            if source_code != code:
                continue
            text = read_text(path)
            lines = text.splitlines()
            match = re.match(r"(?i)(.+)-PERF\.PE0$", path.name)
            if not match:
                self.update_file(file_id, status="unrecognized", category="unknown_pe0", parser="apc-pe0-v1",
                                 raw_lines=len(lines), reason="PE0 filename does not match *-PERF.PE0")
                continue
            raw_name = match.group(1)
            model = self.resolve_apc_prediction_model(raw_name, "air")
            self.ensure_model(model, has_geometry=True)
            self.map_model(code, model)
            in_table = False
            started = False
            parsed = 0
            for source_row, line in enumerate(lines, start=1):
                if "STATION" in line.upper() and "CHORD" in line.upper() and "THICKNESS" in line.upper():
                    in_table = True
                    continue
                if not in_table:
                    continue
                tokens = line.split()
                if len(tokens) < 14:
                    if started and not line.strip():
                        break
                    continue
                nums = [float_or_none(token) for token in tokens[:14]]
                if any(value is None for value in nums):
                    continue
                started = True
                station_in, chord_in = nums[0], nums[1]
                radius_m = station_in * INCH_M
                radius_ratio = radius_m / (model.diameter_m / 2.0) if model.diameter_m else None
                values = {"radius_ratio": radius_ratio, "radius_m": radius_m, "chord_m": chord_in * INCH_M,
                          "chord_ratio": chord_in * INCH_M / model.diameter_m if model.diameter_m else None,
                          "twist_deg": nums[8], "sweep_deg": None, "thickness_ratio": nums[7],
                          "quoted_pitch_in": nums[2], "pitch_le_te_in": nums[3], "pitch_prather_in": nums[4],
                          "sweep_in": nums[5], "rake_in": nums[6], "max_thickness_in": nums[9],
                          "cross_section_in2": nums[10], "zhigh_in": nums[11], "cgy_in": nums[12], "cgz_in": nums[13]}
                self.upsert_geometry(code, relative, model, source_row, parsed, "APC_PE0_blade_section", values)
                parsed += 1
            self.update_file(file_id, status="imported" if parsed else "error", category="manufacturer_geometry",
                             parser="apc-pe0-v1", raw_lines=len(lines), raw_rows=parsed, parsed=parsed,
                             error=None if parsed else "No PE0 station table rows")

    @staticmethod
    def enola_path_model(relative: str) -> tuple[str, str] | None:
        parts = Path(relative).parts
        try:
            index = next(i for i, part in enumerate(parts) if part.upper() == "BBDD")
        except StopIteration:
            return None
        if len(parts) <= index + 2:
            return None
        return parts[index + 1], parts[index + 2]

    @staticmethod
    def normalized_header(value: str) -> str:
        return re.sub(r"[^A-Z0-9]+", "", value.upper())

    def load_enola_metadata(self) -> dict[str, float]:
        code = "ENOLA_2026"
        metadata: dict[str, float] = {}
        for (source_code, relative), (file_id, path) in self.source_files.items():
            if source_code != code or path.name.lower() != "00_generalnfo.xlsx":
                continue
            rows = read_xlsx_rows(path, "Hoja1")
            parsed = 0
            for row in rows:
                if len(row) < 5:
                    continue
                family = str(row[2] or "").strip()
                raw_name = str(row[3] or "").strip()
                diameter_m = float_or_none(row[4])
                if not family or not raw_name or family.lower() == "family":
                    continue
                key = re.sub(r"[^a-z0-9]", "", raw_name.lower())
                if diameter_m is not None:
                    metadata[key] = diameter_m
                model = normalize_enola(family, raw_name, diameter_m)
                self.ensure_model(model)
                self.map_model(code, model)
                parsed += 1
            self.update_file(file_id, status="imported", category="database_metadata", parser="xlsx-ooxml:Hoja1",
                             raw_lines=len(rows), raw_rows=parsed, parsed=parsed)
        return metadata

    @staticmethod
    def enola_evidence(path: Path) -> tuple[str, str]:
        name = path.stem.lower()
        if re.search(r"(?:^|_)(exp|wt|ac)(?:_|$)", name):
            return "experiment", "ENOLA physical experiment"
        if "bemt" in name:
            return "numerical", "ENOLA blade-element momentum numerical result"
        if any(token in name for token in ("rans", "urans", "mrf", "vbm", "rbm", "fluent", "starccm", "_of_", "des")):
            return "cfd", "ENOLA CFD/numerical result"
        return "numerical", "ENOLA numerical result (method inferred from results directory)"

    def ingest_enola(self) -> None:
        code = "ENOLA_2026"
        metadata = self.load_enola_metadata()
        for (source_code, relative), (file_id, path) in sorted(self.source_files.items()):
            if source_code != code or path.name.lower() == "00_generalnfo.xlsx":
                continue
            extension = path.suffix.lower()
            model_parts = self.enola_path_model(relative)
            if extension in {".stl", ".obj", ".x_b"} and model_parts:
                family, raw_name = model_parts
                key = re.sub(r"[^a-z0-9]", "", raw_name.lower())
                model = normalize_enola(family, raw_name, metadata.get(key))
                self.ensure_model(model, has_geometry=True)
                self.map_model(code, model)
                self.upsert_geometry(code, relative, model, None, None, f"CAD_reference_{extension[1:].upper()}",
                                     {"file_sha256": sha256_file(path), "file_bytes": path.stat().st_size,
                                      "note": "External CAD/mesh reference retained in source audit; binary payload not embedded"})
                self.update_file(file_id, status="imported_reference", category="cad_geometry", parser="binary-geometry-reference",
                                 parsed=1, reason="Geometry reference indexed by SHA-256; binary mesh not embedded in SQLite")
                continue
            if extension == ".txt":
                text = read_text(path)
                self.update_file(file_id, status="recognized_not_imported", category="documentation", parser="text-classifier",
                                 raw_lines=count_lines(text), reason="README/provenance text; no tabular performance schema")
                continue
            if extension != ".csv":
                self.update_file(file_id, status="recognized_not_imported", category="metadata", parser="extension-classifier",
                                 reason="Known metadata file type; no supported propeller performance rows")
                continue
            text = read_text(path)
            lines = text.splitlines()
            if not lines:
                self.update_file(file_id, status="error", category="csv", parser="enola-csv-v1", raw_lines=0,
                                 error="Empty CSV")
                continue
            delimiter = ";" if lines and lines[0].count(";") > lines[0].count(",") else ","
            reader = csv.reader(lines, delimiter=delimiter)
            rows = list(reader)
            header = rows[0]
            if len(header) == 10 and "THRUST[N]U_THRUST[N]" in header[3].upper().replace(" ", ""):
                header = header[:3] + ["THRUST[N]", "u_THRUST[N]"] + header[4:]
            normalized = [self.normalized_header(value) for value in header]
            if any(value.startswith("TIME") for value in normalized) and any(value.startswith("PRESSURE") for value in normalized):
                self.update_file(file_id, status="recognized_not_imported", category="acoustics", parser="enola-csv-v1",
                                 raw_lines=len(lines), raw_rows=max(0, len(rows)-1),
                                 reason="Acoustic pressure time series is not a propeller performance point")
                continue
            if "RR" in normalized and any(value.startswith("CHORD") for value in normalized):
                if not model_parts:
                    self.update_file(file_id, status="error", category="geometry", parser="enola-csv-v1",
                                     raw_lines=len(lines), error="Cannot infer ENOLA model from path")
                    continue
                family, raw_name = model_parts
                key = re.sub(r"[^a-z0-9]", "", raw_name.lower())
                model = normalize_enola(family, raw_name, metadata.get(key))
                self.ensure_model(model, has_geometry=True)
                self.map_model(code, model)
                parsed = 0
                for source_row, row in enumerate(rows[1:], start=2):
                    if not row:
                        continue
                    record = {normalized[index]: row[index] if index < len(row) else None for index in range(len(normalized))}
                    radius_ratio = float_or_none(record.get("RR"))
                    if radius_ratio is None:
                        continue
                    chord_mm = float_or_none(next((record[key] for key in record if key.startswith("CHORDMM")), None))
                    chord_ratio = float_or_none(record.get("CR"))
                    twist_deg = float_or_none(next((record[key] for key in record if key.startswith("TWISTDEG")), None))
                    sweep_deg = float_or_none(next((record[key] for key in record if key.startswith("SWEEPDEG")), None))
                    values = {"radius_ratio": radius_ratio,
                              "radius_m": radius_ratio * model.diameter_m / 2 if model.diameter_m else None,
                              "chord_m": chord_mm / 1000 if chord_mm is not None else (chord_ratio * model.diameter_m if chord_ratio is not None and model.diameter_m else None),
                              "chord_ratio": chord_ratio if chord_ratio is not None else (chord_mm / 1000 / model.diameter_m if chord_mm is not None and model.diameter_m else None),
                              "twist_deg": twist_deg, "sweep_deg": sweep_deg, "raw": record}
                    self.upsert_geometry(code, relative, model, source_row, parsed, "blade_definition", values)
                    parsed += 1
                self.update_file(file_id, status="imported" if parsed else "error", category="geometry",
                                 parser="enola-geometry-csv-v1", raw_lines=len(lines), raw_rows=max(0, len(rows)-1),
                                 parsed=parsed, error=None if parsed else "No supported geometry rows")
                continue
            if "RPM" not in normalized or not any(value in normalized for value in ("CT", "CP", "CQ", "THRUSTN", "TORQUENM")):
                category = "airfoil_polar" if any(value in normalized for value in ("ALPHA", "CL", "CD")) else "unsupported_csv"
                self.update_file(file_id, status="recognized_not_imported" if category == "airfoil_polar" else "unrecognized",
                                 category=category, parser="enola-csv-v1", raw_lines=len(lines), raw_rows=max(0, len(rows)-1),
                                 reason="CSV lacks RPM and supported propeller performance fields" if category != "airfoil_polar" else
                                        "Airfoil polar supports geometry/CFD methods but is not a propeller operating point")
                continue
            if not model_parts:
                self.update_file(file_id, status="error", category="performance", parser="enola-csv-v1",
                                 raw_lines=len(lines), error="Cannot infer ENOLA model from path")
                continue
            family, raw_name = model_parts
            key = re.sub(r"[^a-z0-9]", "", raw_name.lower())
            model = normalize_enola(family, raw_name, metadata.get(key))
            evidence, source_type = self.enola_evidence(path)
            self.ensure_model(model, has_experiment=evidence == "experiment", has_cfd=evidence in {"cfd", "numerical"})
            self.map_model(code, model)
            parsed = 0
            for source_row, row in enumerate(rows[1:], start=2):
                if not row:
                    continue
                record = {normalized[index]: row[index] if index < len(row) else None for index in range(len(normalized))}
                rpm = float_or_none(record.get("RPM"))
                if rpm is None:
                    continue
                j = float_or_none(record.get("J"))
                speed = float_or_none(next((record[key] for key in record if key in {"VMS", "VELOCITYMS"}), None))
                ct = float_or_none(record.get("CT"))
                cp = float_or_none(record.get("CP"))
                cq = float_or_none(record.get("CQ"))
                if cp is None and cq is not None:
                    cp = 2.0 * math.pi * cq
                thrust = float_or_none(record.get("THRUSTN"))
                torque = float_or_none(record.get("TORQUENM"))
                power = torque * 2.0 * math.pi * rpm / 60.0 if torque is not None else None
                efficiency = ct * j / cp if ct is not None and j is not None and cp not in (None, 0.0) else None
                values = {"rpm": rpm, "j": j, "speed_m_s": speed, "ct": ct, "cp": cp, "efficiency": efficiency,
                          "thrust_n": thrust, "power_w": power, "torque_nm": torque, "density": AIR_DENSITY,
                          "is_static": (j is not None and abs(j) < 1e-12) or (speed is not None and abs(speed) < 1e-12)}
                self.upsert_performance(code, relative, model, source_row, values, ",".join(row), evidence, source_type)
                parsed += 1
            self.update_file(file_id, status="imported" if parsed else "error", category=f"performance_{evidence}",
                             parser="enola-performance-csv-v1", raw_lines=len(lines), raw_rows=max(0, len(rows)-1),
                             parsed=parsed, error=None if parsed else "No supported performance rows")

    def ingest_other_dataset(self) -> None:
        code = "OTHER_CFD_DATASET"
        for (source_code, relative), (file_id, path) in sorted(self.source_files.items()):
            if source_code != code:
                continue
            text = read_text(path)
            rows = list(csv.reader(text.splitlines()))
            header = rows[0] if rows else []
            has_cfd_schema = "Airspeed_m_s_" in header and "Rotor1AngularRate_rpm_" in header and "Thrust1_N_" in header
            self.update_file(
                file_id,
                status="recognized_not_imported" if has_cfd_schema else "unrecognized",
                category="coupled_airframe_cfd" if has_cfd_schema else "unsupported_csv",
                parser="other-cfd-classifier-v1",
                raw_lines=len(text.splitlines()), raw_rows=max(0, len(rows)-1), parsed=0,
                reason=("Coupled aircraft/rotor CFD rows have no propeller model, diameter or geometry; retained in audit but not mixed with propeller curves"
                        if has_cfd_schema else "CSV schema not recognized"),
            )

    def ingest_rpm_limits(self) -> None:
        code = "APC_RPM_REV5"
        relative = SOURCE_SPECS[code]["path"].name
        file_id, path = self.source_files[(code, relative)]
        rules = [
            ("GENERAL", "Glow/Sport/Pattern and Speed 400 Electric", "ДВЗ Sport/Pattern та Speed 400 Electric", 190000.0),
            ("THIN_DURABLE", "Thin Electric and Durable FPV", "Thin Electric та Durable FPV", 150000.0),
            ("FOLDING", "Folding Electric", "Складані електричні", 120000.0),
            ("MULTIROTOR", "Multi-Rotor and Multi-Rotor Folding", "Мультироторні та складані мультироторні", 105000.0),
            ("SLOW_FLYER", "Slow Flyer", "Slow Flyer", 65000.0),
            ("RACING_GENERAL", "Racing/Carbon and listed 40 Pylon conditions", "Гоночні/Carbon та зазначені умови 40 Pylon", 225000.0),
            ("RACING_ELECTRIC", "Racing/Carbon on electric motors", "Гоночні/Carbon на електромоторах", 270000.0),
        ]
        for code_name, en, uk, coefficient in rules:
            content_hash = stable_hash([code_name, en, uk, coefficient, "Rev 5"])
            self.connection.execute(
                """INSERT INTO rpm_limits(limit_key,model_id,rule_code,category_en,category_uk,coefficient_rpm_in,
                   application_note,source_file_id,revision,content_hash) VALUES(?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(limit_key) DO UPDATE SET category_en=excluded.category_en,category_uk=excluded.category_uk,
                   coefficient_rpm_in=excluded.coefficient_rpm_in,content_hash=excluded.content_hash""",
                (f"rule:{code_name}", None, code_name, en, uk, coefficient,
                 "Maximum RPM = coefficient / propeller diameter (inches); apply only under the rule's stated operating condition.",
                 file_id, "Rev 5, 2022-03-23", content_hash),
            )
        models = self.connection.execute(
            "SELECT * FROM models WHERE manufacturer='APC' AND diameter_m IS NOT NULL"
        ).fetchall()
        for row in models:
            text = " ".join(str(row[key] or "") for key in ("original_name", "series", "catalog_description")).upper()
            if "SLOW" in text or re.search(r"SF(?:-|$)", text):
                rule = rules[4]
            elif "MRF" in text:
                rule = rules[3]
            elif "FOLD" in text or re.search(r"F(?:-|$)", text):
                rule = rules[2]
            elif "MULTI" in text or "MR" in text:
                rule = rules[3]
            elif "THIN" in text or "DURABLE" in text:
                rule = rules[1]
            elif "RACING" in text or "CARBON" in text or "PYLON" in text:
                rule = rules[5]
            else:
                rule = rules[0]
            diameter_in = row["diameter_m"] / INCH_M
            max_rpm = rule[3] / diameter_in
            content_hash = stable_hash([row["model_id"], rule[0], diameter_in, max_rpm])
            self.connection.execute(
                """INSERT INTO rpm_limits(limit_key,model_id,rule_code,category_en,category_uk,coefficient_rpm_in,
                   diameter_in,max_rpm,application_note,source_file_id,revision,content_hash)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(limit_key) DO UPDATE SET rule_code=excluded.rule_code,diameter_in=excluded.diameter_in,
                   max_rpm=excluded.max_rpm,content_hash=excluded.content_hash""",
                (f"model:{row['model_id']}", row["model_id"], rule[0], rule[1], rule[2], rule[3], diameter_in,
                 max_rpm, "Conservative automatic category match. Review special electric-racing conditions before using the higher 270,000/D rule.",
                 file_id, "Rev 5, 2022-03-23", content_hash),
            )
        self.update_file(file_id, status="imported", category="structural_rpm_limits", parser="apc-rpm-rev5-manual-verified",
                         raw_lines=7, raw_rows=7, parsed=len(rules) + len(models),
                         reason="Seven manufacturer formulas manually verified against rendered one-page PDF; model limits use conservative category matching")

    def classify_remaining_files(self) -> None:
        known_docs = {".html", ".css", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".eps", ".fig", ".zip"}
        rows = self.connection.execute(
            """SELECT sf.source_file_id,sf.relative_path,sf.extension,s.code FROM source_files sf
               JOIN sources s ON s.source_id=sf.source_id WHERE sf.status='pending'"""
        ).fetchall()
        for row in rows:
            extension = row["extension"]
            code = row["code"]
            relative = row["relative_path"]
            file_id, path = self.source_files[(code, relative)]
            if extension in known_docs:
                category = "nested_archive" if extension == ".zip" else ("documentation" if extension in {".html", ".pdf"} else "presentation_asset")
                reason = "Nested comparison archive retained; its extracted members duplicate comparison material" if extension == ".zip" else \
                         "Website/paper/presentation asset; no machine-readable propeller operating points"
                raw_lines = count_lines(read_text(path)) if extension in {".html", ".css", ".eps", ".fig"} else None
                self.update_file(file_id, status="recognized_not_imported", category=category,
                                 parser="extension-classifier", raw_lines=raw_lines, reason=reason)
            elif extension == ".jbf" or extension == "[no extension]":
                self.update_file(file_id, status="unrecognized", category="unknown_binary", parser="extension-classifier",
                                 reason="Unknown/unsupported binary metadata format; file retained and SHA-256 logged")
            else:
                raw_lines = count_lines(read_text(path)) if extension in {".txt", ".csv", ".dat", ".pe0"} else None
                self.update_file(file_id, status="unrecognized", category="unsupported", parser="extension-classifier",
                                 raw_lines=raw_lines, reason="No supported parser matched this file; retained and SHA-256 logged")

    def run_all(self, extraction_manifest: Path) -> dict[str, int]:
        self.register_sources()
        self.register_source_files(extraction_manifest)
        self.ingest_apc_catalog()
        self.ingest_uiuc()
        self.ingest_apc_predictions()
        self.ingest_apc_geometry()
        self.ingest_enola()
        self.ingest_other_dataset()
        self.ingest_rpm_limits()
        self.classify_remaining_files()
        self.connection.commit()
        return dict(self.stats)
