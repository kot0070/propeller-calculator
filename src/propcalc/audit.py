from __future__ import annotations

import csv
import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any

from .config import APP_NAME, APP_VERSION, AUTHOR


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def database_audit(connection: sqlite3.Connection) -> dict[str, Any]:
    source_rows = connection.execute("SELECT * FROM sources ORDER BY source_id").fetchall()
    sources: list[dict[str, Any]] = []
    for source in source_rows:
        source_id = source["source_id"]
        files = connection.execute(
            "SELECT * FROM source_files WHERE source_id=? ORDER BY relative_path", (source_id,)
        ).fetchall()
        format_counts: dict[str, int] = defaultdict(int)
        status_counts: dict[str, int] = defaultdict(int)
        category_counts: dict[str, int] = defaultdict(int)
        reasons: dict[str, int] = defaultdict(int)
        for file in files:
            format_counts[file["extension"] or "[none]"] += 1
            status_counts[file["status"]] += 1
            category_counts[file["category"] or "[none]"] += 1
            if file["skip_reason"]:
                reasons[file["skip_reason"]] += 1
        points = connection.execute(
            """SELECT COUNT(*) AS total,SUM(CASE WHEN p.is_static=1 THEN 1 ELSE 0 END) AS static_points,
               SUM(CASE WHEN p.is_static=0 THEN 1 ELSE 0 END) AS dynamic_points,
               MIN(p.rpm) AS rpm_min,MAX(p.rpm) AS rpm_max,MIN(p.advance_ratio_j) AS j_min,MAX(p.advance_ratio_j) AS j_max,
               SUM(CASE WHEN p.evidence_class='experiment' THEN 1 ELSE 0 END) AS experiment_points,
               SUM(CASE WHEN p.evidence_class='prediction' THEN 1 ELSE 0 END) AS prediction_points,
               SUM(CASE WHEN p.evidence_class IN ('cfd','numerical') THEN 1 ELSE 0 END) AS cfd_numerical_points
               FROM performance_points p JOIN source_files sf ON sf.source_file_id=p.source_file_id WHERE sf.source_id=?""",
            (source_id,),
        ).fetchone()
        raw_models = connection.execute(
            "SELECT COUNT(*) FROM model_raw_mappings WHERE source_id=?", (source_id,)
        ).fetchone()[0]
        normalized_models = connection.execute(
            "SELECT COUNT(DISTINCT model_id) FROM model_raw_mappings WHERE source_id=?", (source_id,)
        ).fetchone()[0]
        sources.append({
            "code": source["code"],
            "name": source["name"],
            "group": source["source_group"],
            "archive": source["archive_name"],
            "sha256": source["archive_sha256"],
            "archive_bytes": source["archive_bytes"],
            "version": source["version"],
            "source_date": source["source_date"],
            "file_count": len(files),
            "formats": dict(sorted(format_counts.items())),
            "status_counts": dict(sorted(status_counts.items())),
            "recognized_files": sum(count for status, count in status_counts.items() if status != "unrecognized"),
            "unrecognized_files": status_counts.get("unrecognized", 0),
            "skip_reasons": [{"reason": reason, "files": count} for reason, count in sorted(reasons.items())],
            "raw_lines": sum(file["raw_line_count"] or 0 for file in files),
            "raw_data_rows": sum(file["raw_data_rows"] or 0 for file in files),
            "parsed_records": sum(file["parsed_records"] or 0 for file in files),
            "raw_unique_models": raw_models,
            "normalized_models": normalized_models,
            "normalized_alias_merges": max(0, raw_models - normalized_models),
            "categories": dict(sorted(category_counts.items())),
            **dict(points),
        })
    group_rows = connection.execute("SELECT DISTINCT source_group FROM sources ORDER BY source_group").fetchall()
    groups: list[dict[str, Any]] = []
    for group_row in group_rows:
        group = group_row[0]
        counts = connection.execute(
            """SELECT COUNT(DISTINCT m.model_id) AS models,
               COUNT(DISTINCT CASE WHEN m.has_experiment=1 THEN m.model_id END) AS models_with_experiment,
               COUNT(DISTINCT CASE WHEN m.has_prediction=1 AND m.has_experiment=0 AND m.has_cfd=0 THEN m.model_id END) AS prediction_only_models
               FROM models m JOIN model_raw_mappings mm ON mm.model_id=m.model_id
               JOIN sources s ON s.source_id=mm.source_id WHERE s.source_group=?""", (group,)
        ).fetchone()
        points = connection.execute(
            """SELECT COUNT(*) AS characteristics,
               SUM(CASE WHEN p.evidence_class='experiment' THEN 1 ELSE 0 END) AS experiment,
               SUM(CASE WHEN p.evidence_class='prediction' THEN 1 ELSE 0 END) AS prediction,
               SUM(CASE WHEN p.evidence_class IN ('cfd','numerical') THEN 1 ELSE 0 END) AS cfd_numerical
               FROM performance_points p JOIN source_files sf ON sf.source_file_id=p.source_file_id
               JOIN sources s ON s.source_id=sf.source_id WHERE s.source_group=?""", (group,)
        ).fetchone()
        groups.append({"group": group, **dict(counts), **dict(points)})
    total = dict(connection.execute("SELECT * FROM database_summary").fetchone())
    total.update({
        "geometries": connection.execute("SELECT COUNT(*) FROM geometries").fetchone()[0],
        "rpm_limit_rows": connection.execute("SELECT COUNT(*) FROM rpm_limits").fetchone()[0],
        "performance_duplicate_keys": connection.execute(
            "SELECT COUNT(*) FROM (SELECT point_key FROM performance_points GROUP BY point_key HAVING COUNT(*)>1)"
        ).fetchone()[0],
        "model_duplicate_ids": connection.execute(
            "SELECT COUNT(*) FROM (SELECT model_id FROM models GROUP BY model_id HAVING COUNT(*)>1)"
        ).fetchone()[0],
    })
    unrecognized = rows_to_dicts(connection.execute(
        """SELECT s.code AS source,sf.relative_path,sf.sha256,sf.file_bytes,sf.extension,sf.skip_reason
           FROM source_files sf JOIN sources s ON s.source_id=sf.source_id
           WHERE sf.status='unrecognized' ORDER BY s.code,sf.relative_path"""
    ).fetchall())
    return {"totals": total, "groups": groups, "sources": sources, "unrecognized_files": unrecognized}


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = list(rows[0]) if rows else []
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def export_audit(connection: sqlite3.Connection, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    audit = {"application": {"name": APP_NAME, "version": APP_VERSION, "author": AUTHOR},
             **database_audit(connection)}
    (output_dir / "audit_report.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    files = rows_to_dicts(connection.execute(
        """SELECT s.code AS source_code,s.source_group,s.archive_name,sf.relative_path,sf.sha256,sf.file_bytes,
           sf.extension,sf.raw_line_count,sf.raw_data_rows,sf.parsed_records,sf.status,sf.category,sf.skip_reason,
           sf.parser_name,sf.parse_error FROM source_files sf JOIN sources s ON s.source_id=sf.source_id
           ORDER BY s.source_id,sf.relative_path"""
    ).fetchall())
    write_csv(output_dir / "source_file_audit.csv", files)
    mappings = rows_to_dicts(connection.execute(
        """SELECT s.code AS source_code,s.source_group,mm.raw_name,mm.model_id,mm.normalization_rule,
           m.manufacturer,m.series,m.diameter_m,m.pitch_m,m.blade_count,m.rotation,m.medium
           FROM model_raw_mappings mm JOIN sources s ON s.source_id=mm.source_id
           JOIN models m ON m.model_id=mm.model_id ORDER BY s.code,mm.raw_name"""
    ).fetchall())
    write_csv(output_dir / "model_id_mapping.csv", mappings)
    write_csv(output_dir / "unrecognized_files.csv", audit["unrecognized_files"])
    summary_lines = [
        "# Propeller Calculator Professional UA v3 - Source Audit",
        "",
        f"**Author / Автор: {AUTHOR}**",
        "",
        "## Database totals",
        "",
    ]
    for key, value in audit["totals"].items():
        summary_lines.append(f"- {key}: {value}")
    summary_lines.extend(["", "## Source groups", "", "| Group | Models | Characteristics | Experiment | Prediction | CFD/numerical |",
                          "|---|---:|---:|---:|---:|---:|"])
    for group in audit["groups"]:
        summary_lines.append(
            f"| {group['group']} | {group['models']} | {group['characteristics'] or 0} | {group['experiment'] or 0} | "
            f"{group['prediction'] or 0} | {group['cfd_numerical'] or 0} |"
        )
    summary_lines.extend(["", "## Sources", ""])
    for source in audit["sources"]:
        summary_lines.extend([
            f"### {source['name']}", "",
            f"- SHA-256: `{source['sha256']}`",
            f"- Files: {source['file_count']} (recognized {source['recognized_files']}; unrecognized {source['unrecognized_files']})",
            f"- Formats: {json.dumps(source['formats'], ensure_ascii=False)}",
            f"- Raw lines / data rows: {source['raw_lines']} / {source['raw_data_rows']}",
            f"- Raw / normalized models: {source['raw_unique_models']} / {source['normalized_models']}",
            f"- Characteristics: {source['total'] or 0} (static {source['static_points'] or 0}; dynamic {source['dynamic_points'] or 0})",
            f"- RPM range: {source['rpm_min']} .. {source['rpm_max']}; J range: {source['j_min']} .. {source['j_max']}", "",
        ])
    summary_lines.extend(["## Unrecognized files", "", f"Count: {len(audit['unrecognized_files'])}. See unrecognized_files.csv.", ""])
    (output_dir / "audit_report.md").write_text("\n".join(summary_lines), encoding="utf-8")
    return audit


def export_manual_verification(connection: sqlite3.Connection, output_path: Path) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    queries = [
        ("UIUC static", "UIUC_2022", "static_experiment"),
        ("UIUC dynamic", "UIUC_2022", "dynamic_experiment"),
        ("APC prediction static/dynamic", "APC_PERFILES_202602", "performance_prediction"),
        ("ENOLA experiment", "ENOLA_2026", "performance_experiment"),
        ("ENOLA CFD", "ENOLA_2026", "performance_cfd"),
    ]
    for label, source_code, category in queries:
        rows = connection.execute(
            """SELECT p.model_id,p.original_name,p.rpm,p.advance_ratio_j,p.ct,p.cp,p.thrust_n,p.power_w,p.torque_nm,
               p.source_row,p.raw_row,sf.relative_path,sf.sha256,p.evidence_class
               FROM performance_points p JOIN source_files sf ON sf.source_file_id=p.source_file_id
               JOIN sources s ON s.source_id=sf.source_id WHERE s.code=? AND sf.category=?
               ORDER BY p.performance_id LIMIT 3""", (source_code, category)
        ).fetchall()
        samples.append({"check": label, "source": source_code, "samples": rows_to_dicts(rows),
                        "result": "PASS" if rows else "NO SAMPLE - inspect parser category"})
    catalog = connection.execute(
        """SELECT m.model_id,m.original_name,m.sku,m.diameter_m,m.pitch_m,m.weight_kg
           FROM models m JOIN model_raw_mappings mm ON mm.model_id=m.model_id
           JOIN sources s ON s.source_id=mm.source_id WHERE s.code='APC_CATALOG_202602' ORDER BY m.model_id LIMIT 3"""
    ).fetchall()
    samples.append({"check": "APC catalog", "source": "APC_CATALOG_202602", "samples": rows_to_dicts(catalog),
                    "result": "PASS" if catalog else "FAIL"})
    rpm_rules = connection.execute(
        "SELECT rule_code,coefficient_rpm_in,revision FROM rpm_limits WHERE model_id IS NULL ORDER BY rpm_limit_id"
    ).fetchall()
    samples.append({"check": "APC RPM PDF Rev 5", "source": "APC_RPM_REV5", "samples": rows_to_dicts(rpm_rules),
                    "result": "PASS" if len(rpm_rules) == 7 else "FAIL"})
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(samples, ensure_ascii=False, indent=2), encoding="utf-8")
    return samples
