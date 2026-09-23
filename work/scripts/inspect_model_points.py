from __future__ import annotations

import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
database = ROOT / "work" / "build" / "propellers.db"
connection = sqlite3.connect(database)
connection.row_factory = sqlite3.Row

model_id = "APC:8X9"
rows = connection.execute(
    """SELECT p.performance_id,p.rpm,p.advance_ratio_j,p.speed_m_s,p.ct,p.cp,p.efficiency,
              p.thrust_n,p.power_w,p.is_static,p.evidence_class,p.source_type,
              sf.relative_path,p.source_row
       FROM performance_points p
       JOIN source_files sf ON sf.source_file_id=p.source_file_id
       WHERE p.model_id=? AND p.rpm IS NOT NULL AND p.ct IS NOT NULL AND p.cp IS NOT NULL
       ORDER BY CASE p.evidence_class
                    WHEN 'experiment' THEN 0 WHEN 'prediction' THEN 1
                    WHEN 'cfd' THEN 2 WHEN 'numerical' THEN 3 ELSE 4 END,
                p.is_static DESC,p.rpm DESC,COALESCE(p.advance_ratio_j,0)
       LIMIT 30""",
    (model_id,),
).fetchall()

print(f"{model_id}: {len(rows)} displayed rows")
for row in rows:
    print(dict(row))

connection.close()
