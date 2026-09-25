"""Repair 8 corrupted UIUC diameter/pitch values + derived per-row fields.

Background (verified read-only against work/extracted UIUC HTML spec pages):
  volume-2/propDB-volume-2.html: "140 mm X 45 mm" (vp_140x45),
    "100 mm X 80 mm" (pl_100x80), "96 mm X 70 mm" (kpf_96x70),
    "130 mm X 70 mm" (ef_130x70), "57 mm X 20mm" (pl_57x20).
  volume-3/propDB-volume-3.html: "12.5 x 6" / "12.5 x 7.5" / "12.5 x 9"
    inches (ancf_125x6 / ancf_125x75 / ancf_125x9).
Corruption: mm values stored as inches (x25.4 too large), or dropped
decimal for the 12.5in Aeronauts (125 inches -> 3.175 m). Raw Ct/Cp/RPM
are innocent; stored thrust/power/torque were derived with the bad D.

True dimensions (m):
  VAPOR 140X45 0.140/0.045; PLANTRACO 100X80 0.100/0.080;
  KP 96X70 0.096/0.070; E-FLITE 130X70 0.130/0.070;
  PLANTRACO 57X20 0.057/0.020; AERONAUT 125X75 0.3175/0.1905;
  125X9 0.3175/0.2286; 125X6 0.3175/0.1524.

Usage:
  python repair_diameters_v1.py --db PATH [--dry-run] [--apply]
Default is --dry-run (no writes). --apply performs writes after
creating a timestamped backup next to the DB.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import math
import shutil
import sqlite3
import sys
from pathlib import Path

RHO_DEFAULT = 1.225
# Tolerance for "row matches old-diameter computation" gate (relative).
TOL_REL = 1e-6
# Tight equality for "already correct" abort check.
TOL_EXACT = 1e-12

# (model_id, true_diameter_m, true_pitch_m). model_ids re-derived via
# read-only query at runtime; script aborts if any is missing.
TARGETS: list[tuple[str, float, float]] = [
    ("UIUC:VAPOR:140X45", 0.140, 0.045),
    ("UIUC:PLANTRACO:100X80", 0.100, 0.080),
    ("UIUC:KP:96X70", 0.096, 0.070),
    ("UIUC:E-FLITE:130X70", 0.130, 0.070),
    ("UIUC:PLANTRACO:57X20", 0.057, 0.020),
    ("UIUC:AERONAUT:125X75", 0.3175, 0.1905),
    ("UIUC:AERONAUT:125X9", 0.3175, 0.2286),
    ("UIUC:AERONAUT:125X6", 0.3175, 0.1524),
]


def _close(a: float | None, b: float | None, tol: float) -> bool:
    if a is None or b is None:
        return a is b
    if b == 0.0:
        return abs(a - b) <= tol
    return abs(a - b) / max(abs(b), 1e-30) <= tol


def main() -> int:
    ap = argparse.ArgumentParser(description="Repair 8 corrupted diameters (dry-run by default).")
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
    olds: dict[str, tuple[float | None, float | None]] = {}
    for mid, td, tp in TARGETS:
        row = ro.execute(
            "SELECT model_id, diameter_m, pitch_m FROM models WHERE model_id = ?", (mid,)
        ).fetchone()
        if row is None:
            problems.append(f"missing model_id {mid}")
            continue
        olds[mid] = (row["diameter_m"], row["pitch_m"])
        if _close(row["diameter_m"], td, TOL_EXACT) and _close(row["pitch_m"], tp, TOL_EXACT):
            problems.append(f"already correct {mid} (aborting to avoid double-apply)")
    if problems:
        for p in problems:
            print(f"ABORT: {p}", file=sys.stderr)
        ro.close()
        return 1
    # Row counts for the report (read-only).
    counts: dict[str, int] = {}
    for mid, _, _ in TARGETS:
        counts[mid] = ro.execute(
            "SELECT COUNT(*) FROM performance_points WHERE model_id = ?", (mid,)
        ).fetchone()[0]
    ro.close()
    total = sum(counts.values())
    print(f"Verified 8 model_ids present, none already correct. Total rows: {total}")
    for mid, td, tp in TARGETS:
        od, op = olds[mid]
        print(f"  {mid}: models D {od} -> {td}, P {op} -> {tp} | rows={counts[mid]}")

    if not do_apply:
        # Dry-run: compute what WOULD change on first row of each model.
        ro2 = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
        ro2.row_factory = sqlite3.Row
        print("DRY-RUN: no writes made.")
        for mid, td, tp in TARGETS:
            od, _op = olds[mid]
            r = ro2.execute(
                "SELECT rpm, ct, cp, thrust_n, power_w FROM performance_points"
                " WHERE model_id = ? ORDER BY performance_id LIMIT 1", (mid,)
            ).fetchone()
            if r is None or r["ct"] is None or r["rpm"] is None:
                print(f"  {mid}: no computable rows (would set D={td} P={tp})")
                continue
            n = r["rpm"] / 60.0
            # Formulas: T = Ct*rho*n^2*D^4, P = Cp*rho*n^3*D^5, Q = P/(2*pi*n), rho=1.225
            t_new = r["ct"] * RHO_DEFAULT * n * n * td**4
            p_new = r["cp"] * RHO_DEFAULT * n**3 * td**5
            print(f"  {mid}: sample rpm={r['rpm']} T {r['thrust_n']:.3f} -> {t_new:.6f},"
                  f" P {r['power_w']:.3f} -> {p_new:.6f} (D {od} -> {td}, P -> {tp})")
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
        for mid, td, tp in TARGETS:
            od, op = olds[mid]
            cur = con.execute(
                "SELECT performance_id, rpm, ct, cp, thrust_n, power_w, torque_nm,"
                " density_kg_m3, diameter_m FROM performance_points WHERE model_id = ?",
                (mid,),
            )
            rows = cur.fetchall()
            n_ok = 0
            n_skip = 0
            for r in rows:
                pid = r["performance_id"]
                rpm, ct, cp = r["rpm"], r["ct"], r["cp"]
                if rpm is None or ct is None or cp is None or rpm == 0:
                    n_skip += 1
                    continue
                rho = r["density_kg_m3"] if r["density_kg_m3"] else RHO_DEFAULT
                dold = r["diameter_m"] if r["diameter_m"] else od
                n = rpm / 60.0
                # Expected values under OLD (corrupted) diameter.
                t_old_exp = ct * rho * n * n * dold**4
                p_old_exp = cp * rho * n**3 * dold**5
                q_old_exp = p_old_exp / (2.0 * math.pi * n)
                # Gate: recompute ONLY rows matching old-diameter computation
                # within tolerance; otherwise leave the row untouched (counted
                # as skipped) so unrelated/manual rows are never clobbered.
                # Near-zero values use absolute comparison via _close(b==0 branch).
                if not (_close(r["thrust_n"], t_old_exp, TOL_REL)
                        and _close(r["power_w"], p_old_exp, TOL_REL)
                        and _close(r["torque_nm"], q_old_exp, TOL_REL)):
                    n_skip += 1
                    continue
                # Recompute with TRUE diameter.
                # T = Ct*rho*n^2*D^4, P = Cp*rho*n^3*D^5, Q = P/(2*pi*n), rho=1.225 (per-row density)
                t_new = ct * rho * n * n * td**4
                p_new = cp * rho * n**3 * td**5
                q_new = p_new / (2.0 * math.pi * n)
                con.execute(
                    "UPDATE performance_points SET diameter_m = ?, pitch_m = ?,"
                    " thrust_n = ?, power_w = ?, torque_nm = ? WHERE performance_id = ?",
                    (td, tp, t_new, p_new, q_new, pid),
                )
                n_ok += 1
            con.execute(
                "UPDATE models SET diameter_m = ?, pitch_m = ? WHERE model_id = ?",
                (td, tp, mid),
            )
            after = con.execute(
                "SELECT diameter_m, pitch_m FROM models WHERE model_id = ?", (mid,)
            ).fetchone()
            mx = con.execute(
                "SELECT MAX(thrust_n) FROM performance_points WHERE model_id = ?", (mid,)
            ).fetchone()[0]
            print(f"{mid}: D {od} -> {after['diameter_m']}, P {op} -> {after['pitch_m']} |"
                  f" rows={len(rows)} recomputed={n_ok} skipped={n_skip} max_thrust_now={mx:.6f}")
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
