from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA_VERSION = 3


SCHEMA_SQL = r"""
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

CREATE TABLE IF NOT EXISTS schema_info (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sources (
    source_id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    organization TEXT,
    source_group TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    version TEXT,
    source_date TEXT,
    archive_name TEXT NOT NULL,
    archive_sha256 TEXT NOT NULL,
    archive_bytes INTEGER NOT NULL,
    provenance_note TEXT,
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS source_files (
    source_file_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL REFERENCES sources(source_id),
    relative_path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    file_bytes INTEGER NOT NULL,
    extension TEXT,
    raw_line_count INTEGER,
    raw_data_rows INTEGER NOT NULL DEFAULT 0,
    parsed_records INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    category TEXT,
    skip_reason TEXT,
    parser_name TEXT,
    parse_error TEXT,
    UNIQUE(source_id, relative_path)
);

CREATE TABLE IF NOT EXISTS models (
    model_id TEXT PRIMARY KEY,
    original_name TEXT NOT NULL,
    manufacturer TEXT,
    series TEXT,
    diameter_m REAL,
    pitch_m REAL,
    blade_count INTEGER,
    rotation TEXT CHECK(rotation IN ('CW','CCW','REVERSIBLE','UNKNOWN') OR rotation IS NULL),
    medium TEXT NOT NULL DEFAULT 'air' CHECK(medium IN ('air','water','unknown')),
    sku TEXT,
    catalog_status TEXT,
    catalog_description TEXT,
    weight_kg REAL,
    has_experiment INTEGER NOT NULL DEFAULT 0,
    has_prediction INTEGER NOT NULL DEFAULT 0,
    has_cfd INTEGER NOT NULL DEFAULT 0,
    has_geometry INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS model_raw_mappings (
    mapping_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL REFERENCES sources(source_id),
    raw_name TEXT NOT NULL,
    model_id TEXT NOT NULL REFERENCES models(model_id),
    normalization_rule TEXT NOT NULL,
    UNIQUE(source_id, raw_name)
);

CREATE TABLE IF NOT EXISTS performance_points (
    performance_id INTEGER PRIMARY KEY AUTOINCREMENT,
    point_key TEXT NOT NULL UNIQUE,
    model_id TEXT NOT NULL REFERENCES models(model_id),
    original_name TEXT NOT NULL,
    manufacturer TEXT,
    series TEXT,
    diameter_m REAL,
    pitch_m REAL,
    blade_count INTEGER,
    rotation TEXT,
    medium TEXT NOT NULL,
    rpm REAL,
    advance_ratio_j REAL,
    speed_m_s REAL,
    ct REAL,
    cp REAL,
    efficiency REAL,
    thrust_n REAL,
    power_w REAL,
    torque_nm REAL,
    density_kg_m3 REAL,
    is_static INTEGER NOT NULL,
    source_type TEXT NOT NULL,
    evidence_class TEXT NOT NULL CHECK(evidence_class IN ('experiment','prediction','cfd','numerical','catalog')),
    source_file_id INTEGER NOT NULL REFERENCES source_files(source_file_id),
    source_version TEXT,
    source_row INTEGER,
    raw_row TEXT,
    content_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS geometries (
    geometry_id INTEGER PRIMARY KEY AUTOINCREMENT,
    geometry_key TEXT NOT NULL UNIQUE,
    model_id TEXT NOT NULL REFERENCES models(model_id),
    original_name TEXT NOT NULL,
    geometry_kind TEXT NOT NULL,
    station_index INTEGER,
    radius_ratio REAL,
    radius_m REAL,
    chord_ratio REAL,
    chord_m REAL,
    twist_deg REAL,
    sweep_deg REAL,
    thickness_ratio REAL,
    source_file_id INTEGER NOT NULL REFERENCES source_files(source_file_id),
    source_row INTEGER,
    raw_json TEXT,
    content_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS rpm_limits (
    rpm_limit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    limit_key TEXT NOT NULL UNIQUE,
    model_id TEXT REFERENCES models(model_id),
    rule_code TEXT NOT NULL,
    category_en TEXT NOT NULL,
    category_uk TEXT NOT NULL,
    coefficient_rpm_in REAL NOT NULL,
    diameter_in REAL,
    max_rpm REAL,
    application_note TEXT,
    source_file_id INTEGER NOT NULL REFERENCES source_files(source_file_id),
    revision TEXT NOT NULL,
    content_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS import_history (
    import_id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT,
    source_path TEXT,
    source_sha256 TEXT,
    source_code TEXT,
    status TEXT NOT NULL,
    added INTEGER NOT NULL DEFAULT 0,
    updated INTEGER NOT NULL DEFAULT 0,
    skipped INTEGER NOT NULL DEFAULT 0,
    conflicts INTEGER NOT NULL DEFAULT 0,
    errors INTEGER NOT NULL DEFAULT 0,
    backup_path TEXT,
    report_json TEXT
);

CREATE TABLE IF NOT EXISTS import_errors (
    error_id INTEGER PRIMARY KEY AUTOINCREMENT,
    import_id INTEGER REFERENCES import_history(import_id),
    source_file_id INTEGER REFERENCES source_files(source_file_id),
    relative_path TEXT,
    row_number INTEGER,
    error_code TEXT NOT NULL,
    message TEXT NOT NULL,
    raw_value TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS motors (
    motor_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    manufacturer TEXT,
    kv_rpm_per_v REAL,
    resistance_ohm REAL,
    no_load_current_a REAL,
    max_current_a REAL,
    max_power_w REAL,
    max_voltage_v REAL,
    mass_kg REAL,
    notes TEXT,
    is_user INTEGER NOT NULL DEFAULT 1,
    UNIQUE(name, manufacturer)
);

CREATE TABLE IF NOT EXISTS batteries (
    battery_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    chemistry TEXT NOT NULL DEFAULT 'LiPo',
    cells_s INTEGER,
    capacity_ah REAL,
    c_rating REAL,
    internal_resistance_ohm REAL,
    mass_kg REAL,
    notes TEXT,
    is_user INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS frames (
    frame_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    geometry TEXT,
    diagonal_m REAL,
    motor_count INTEGER,
    arm_width_m REAL,
    arm_thickness_m REAL,
    material TEXT,
    mass_kg REAL,
    payload_kg REAL,
    holes_factor REAL,
    custom_json TEXT,
    is_user INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS saved_builds (
    build_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    propeller_model_id TEXT REFERENCES models(model_id),
    motor_id INTEGER REFERENCES motors(motor_id),
    battery_id INTEGER REFERENCES batteries(battery_id),
    frame_id INTEGER REFERENCES frames(frame_id),
    motor_kv REAL,
    battery_s INTEGER,
    battery_capacity_ah REAL,
    esc_current_a REAL,
    motor_count INTEGER NOT NULL DEFAULT 1,
    mass_kg REAL,
    payload_kg REAL,
    advanced_json TEXT NOT NULL DEFAULT '{}',
    note TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS saved_build_components (
    component_id INTEGER PRIMARY KEY AUTOINCREMENT,
    build_id INTEGER NOT NULL REFERENCES saved_builds(build_id) ON DELETE CASCADE,
    component_type TEXT NOT NULL,
    component_ref TEXT,
    quantity INTEGER NOT NULL DEFAULT 1,
    properties_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_models_manufacturer ON models(manufacturer);
CREATE INDEX IF NOT EXISTS idx_models_size ON models(diameter_m, pitch_m);
CREATE INDEX IF NOT EXISTS idx_models_evidence ON models(has_experiment, has_prediction, has_cfd);
CREATE INDEX IF NOT EXISTS idx_perf_model_rpm_j ON performance_points(model_id, rpm, advance_ratio_j);
CREATE INDEX IF NOT EXISTS idx_perf_source ON performance_points(source_file_id, evidence_class);
CREATE INDEX IF NOT EXISTS idx_perf_static ON performance_points(is_static, model_id);
CREATE INDEX IF NOT EXISTS idx_geom_model ON geometries(model_id, radius_ratio);
CREATE INDEX IF NOT EXISTS idx_source_files_status ON source_files(source_id, status, category);
CREATE INDEX IF NOT EXISTS idx_rpm_limits_model ON rpm_limits(model_id);
CREATE INDEX IF NOT EXISTS idx_saved_builds_name ON saved_builds(name);

CREATE VIEW IF NOT EXISTS database_summary AS
SELECT
    (SELECT COUNT(*) FROM models) AS models,
    (SELECT COUNT(*) FROM performance_points) AS characteristics,
    (SELECT COUNT(*) FROM sources) AS sources,
    (SELECT COUNT(*) FROM models WHERE has_experiment=1) AS models_with_experiments,
    (SELECT COUNT(*) FROM models WHERE has_prediction=1 AND has_experiment=0 AND has_cfd=0) AS prediction_only_models;
"""


def connect_database(path: str | Path, *, readonly: bool = False) -> sqlite3.Connection:
    path = Path(path)
    if readonly:
        connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=5000")
    return connection


def initialize_database(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA_SQL)
    connection.execute(
        "INSERT INTO schema_info(key,value) VALUES('schema_version',?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (str(SCHEMA_VERSION),),
    )
    connection.commit()


def integrity_report(connection: sqlite3.Connection) -> dict[str, object]:
    quick_check = connection.execute("PRAGMA quick_check").fetchone()[0]
    foreign_keys = [dict(row) for row in connection.execute("PRAGMA foreign_key_check")]
    duplicate_points = connection.execute(
        "SELECT COUNT(*) FROM (SELECT point_key, COUNT(*) c FROM performance_points GROUP BY point_key HAVING c>1)"
    ).fetchone()[0]
    duplicate_mappings = connection.execute(
        "SELECT COUNT(*) FROM (SELECT source_id,raw_name,COUNT(*) c FROM model_raw_mappings GROUP BY source_id,raw_name HAVING c>1)"
    ).fetchone()[0]
    return {
        "quick_check": quick_check,
        "foreign_key_errors": foreign_keys,
        "duplicate_point_keys": duplicate_points,
        "duplicate_raw_mappings": duplicate_mappings,
    }
