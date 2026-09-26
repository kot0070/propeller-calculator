"""Repair marine (underwater) medium labeling: 11 models + their row densities.

Background (verified read-only against production DB and extracted sources):
  work/extracted/APC_PERFILES_202602/PERFILES_WEB/PERFILES2-MARINE holds 11
  PER3 files (14X17M, 14X13M, 10X10M-JK, 10X14M-LH, 10X4M-LH, 10X4P,
  10X5M-LH, 10X8M-LH, 11X6M-LH, 9X4M-LH, 9X5M-JK) whose header reads
  "DEFINITIONS: (Underwater)". Their 12,769 performance rows are correctly
  labeled medium='water' but carry density_kg_m3=1.225 (air), and the 11
  models rows are stuck at medium='air' because ensure_model() keeps the
  first-seen medium (the APC catalog ingest runs first with 'air').

Corruption: models.medium='air' (should be 'water') and per-row
density_kg_m3=1.225 (should be 1000.0) for exactly these 11 models.
Raw Ct/Cp/RPM and the stored thrust/power/torque (computed by APC under
water density) are innocent and are NOT touched by this script.

Usage:
  python repair_marine_medium_v1.py --db PATH [--dry-run] [--apply]
Default is --dry-run (no writes). --apply performs writes after
creating a timestamped backup next to the DB.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import shutil
import sqlite3
import sys
from pathlib import Path

RHO_AIR = 1.225
RHO_WATER = 1000.0
# Tight equality for "already correct" abort check.
TOL_EXACT = 1e-12

# model_ids re-derived via read-only query at runtime; script aborts if any
# is missing.
TARGETS: list[str] = [
    "APC:10X10M-JK",
    "APC:10X14M-LH",
    "APC:10X4M-LH",
    "APC:10X4P",
    "APC:10X5M-LH",
    "APC:10X8M-LH",
    "APC:11X6M-LH",
    "APC:14X13M",
    "APC:14X17M",
    "APC:9X4M-LH",
    "APC:9X5M-JK",
]


def _close(a: float | None, b: float | None, tol: float) -> bool:
    if a is None or b is None:
        return a is b
    if b == 0.0:
        return abs(a - b) <= tol
    return abs(a - b) / max(abs(b), 1e-30) <= tol


def main() -> int:
    ap = argparse.ArgumentParser(description="Repair marine medium labeling (dry-run by default).")
    ap.add_argument("--db", required=True, help="Path to propellers.db")
    ap.add_argument("--dry-run", action="store_true", default=False)
    ap.add_argument("--apply", action="store_true", default=False)
    args = ap.parse_args()
    if args.dry_run and args.apply:
        print("ERROR: --dry-run and --apply are mutually exclusive.", file=sys.stderr)
        return 2
    do_apply = bool(args.apply)  # default dry-run unless --apply explicitly given

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"ERROR: --db not found: {db_path}", file=sys.stderr)
        return 2

    # Read-only verification pass: re-derive exact model_ids, abort if any
    # missing or already correct (prevents double-apply).
    ro = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    ro.row_factory = sqlite3.Row
    problems: list[str] = []
    mediums: dict[str, str | None] = {}
    for mid in TARGETS:
        row = ro.execute(
            "SELECT model_id, medium FROM models WHERE model_id = ?", (mid,)
        ).fetchone()
        if row is None:
            problems.append(f"missing model_id {mid}")
            continue
        mediums[mid] = row["medium"]
    if problems:
        for p in problems:
            print(f"ABORT: {p}", file=sys.stderr)
        ro.close()
        return 1
    # Row counts for the report (read-only).
    counts: dict[str, int] = {}
    air_density_counts: dict[str, int] = {}
    medium_dist: dict[str, list[tuple[str, int]]] = {}
    for mid in TARGETS:
        counts[mid] = ro.execute(
            "SELECT COUNT(*) FROM performance_points WHERE model_id = ?", (mid,)
        ).fetchone()[0]
        air_density_counts[mid] = ro.execute(
            "SELECT COUNT(*) FROM performance_points WHERE model_id = ? AND density_kg_m3 = ?",
            (mid, RHO_AIR),
        ).fetchone()[0]
        medium_dist[mid] = [
            (r["medium"], r["n"]) for r in ro.execute(
                "SELECT medium, COUNT(*) AS n FROM performance_points"
                " WHERE model_id = ? GROUP BY medium", (mid,)).fetchall()
        ]
    already = [mid for mid in TARGETS
               if mediums[mid] == "water" and air_density_counts[mid] == 0 and counts[mid] > 0]
    if already:
        for mid in already:
            print(f"ABORT: already correct {mid} (aborting to avoid double-apply)", file=sys.stderr)
        ro.close()
        return 1
    ro.close()
    total = sum(counts.values())
    total_air = sum(air_density_counts.values())
    print(f"Verified 11 model_ids present, none already correct. Total rows: {total} "
          f"({total_air} with air density {RHO_AIR})")
    for mid in TARGETS:
        print(f"  {mid}: models.medium {mediums[mid]} -> water | rows={counts[mid]} "
              f"density=={RHO_AIR}: {air_density_counts[mid]} mediums={medium_dist[mid]}")

    if not do_apply:
        # Dry-run: show what WOULD change on a sample row of each model.
        ro2 = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
        ro2.row_factory = sqlite3.Row
        print("DRY-RUN: no writes made.")
        for mid in TARGETS:
            r = ro2.execute(
                "SELECT rpm, density_kg_m3, thrust_n FROM performance_points"
                " WHERE model_id = ? ORDER BY performance_id LIMIT 1", (mid,)
            ).fetchone()
            if r is None:
                print(f"  {mid}: no rows (would set models.medium water)")
                continue
            print(f"  {mid}: sample rpm={r['rpm']} thrust_n={r['thrust_n']} kept,"
                  f" density {r['density_kg_m3']} -> {RHO_WATER} (models.medium -> water)")
        ro2.close()
        print("DRY-RUN complete. Re-run with --apply to write (backup created automatically).")
        return 0

    # --apply path.
    print("REMINDER: take/keep a backup before schema/data repair. This script creates a")
    print("timestamped backup itself before writing; keep it until validation passes.")
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = db_path.with_name(f"{db_path.name}.bak.{stamp}")
    shutil.copy2(db_path, backup_path)
    print(f"Backup created: {backup_path}")

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    try:
        for mid in TARGETS:
            cur = con.execute(
                "SELECT performance_id, density_kg_m3 FROM performance_points WHERE model_id = ?",
                (mid,),
            )
            rows = cur.fetchall()
            n_ok = 0
            n_skip = 0
            for r in rows:
                # Gate: rewrite ONLY rows still carrying the air default;
                # otherwise leave the row untouched (counted as skipped) so
                # unrelated/manual rows are never clobbered.
                if not _close(r["density_kg_m3"], RHO_AIR, TOL_EXACT):
                    n_skip += 1
                    continue
                con.execute(
                    "UPDATE performance_points SET density_kg_m3 = ? WHERE performance_id = ?",
                    (RHO_WATER, r["performance_id"]),
                )
                n_ok += 1
            con.execute(
                "UPDATE models SET medium = 'water' WHERE model_id = ?", (mid,))
            after = con.execute(
                "SELECT medium FROM models WHERE model_id = ?", (mid,)).fetchone()
            print(f"{mid}: models.medium -> {after['medium']} |"
                  f" rows={len(rows)} density_fixed={n_ok} skipped={n_skip}")
        con.commit()
        qc = con.execute("PRAGMA quick_check").fetchone()[0]
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
        print(f"integrity: quick_check={qc} fk_errors={len(fk)}")
    finally:
        con.close()
    print(f"APPLY complete. Backup at {backup_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
