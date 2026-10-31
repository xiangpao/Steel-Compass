"""Exercise migrations in isolated processes/databases, including retained old rows."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from contextlib import closing

import pytest


@pytest.mark.parametrize("legacy", [False, True])
def test_empty_and_legacy_sqlite_upgrade_preserves_rows(tmp_path, legacy):
    db = tmp_path / "migration.db"
    env = {**os.environ,"STEEL_COMPASS_DATABASE_URL":f"sqlite:///{db.as_posix()}"}
    def upgrade(revision):
        result=subprocess.run([sys.executable,"-m","alembic","upgrade",revision],
            cwd=Path(__file__).parents[1],env=env,capture_output=True,text=True)
        assert result.returncode == 0, result.stdout+result.stderr
    if legacy:
        upgrade("20260730_01")
        with closing(sqlite3.connect(db)) as conn:
            conn.execute("INSERT INTO users VALUES (1,'legacy','legacy','unused',0,1,0,'2026-01-01')")
            conn.execute("INSERT INTO projects VALUES (1,1,'retained','original','2026-01-01','2026-01-01')")
            conn.commit()
    upgrade("head")
    with closing(sqlite3.connect(db)) as conn:
        tables={row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "scene_analysis_snapshots" in tables
        assert conn.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "20261101_08"
        if legacy:
            assert conn.execute("SELECT name,description FROM projects WHERE id=1").fetchone()==("retained","original")


def _alembic_upgrade(db: Path, revision: str = "head") -> None:
    env = {**os.environ, "STEEL_COMPASS_DATABASE_URL": f"sqlite:///{db.as_posix()}"}
    result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", revision],
                            cwd=Path(__file__).parents[1], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_revision_scene_instance_backfill_keeps_snapshots_byte_identical(tmp_path):
    db = tmp_path / "backfill.db"
    _alembic_upgrade(db, "20260813_07")
    scene = json.dumps({"scene_context": {"scene_instance_id": 5, "draft_state": {"last_analysis_package": {"x": 1}}}})
    rows = [(1, scene), (2, json.dumps({"calculations": []})), (3, json.dumps({"scene_context": {"scene_instance_id": "bad"}}))]
    with closing(sqlite3.connect(db)) as conn:
        conn.execute("INSERT INTO users VALUES (1,'u','u','unused',0,1,0,'2026-01-01')")
        conn.execute("INSERT INTO projects (id,owner_id,name,description,created_at,updated_at) VALUES (1,1,'p','','2026-01-01','2026-01-01')")
        for revision_id, snapshot in rows:
            conn.execute("INSERT INTO project_revisions (id,project_id,revision_number,snapshot_schema_version,snapshot,"
                         "result_bundle,catalog_versions,engine_version,report_number,created_at) "
                         "VALUES (?,1,?,'3.9',?,'{}','{}','e',?,'2026-01-01')", (revision_id, revision_id, snapshot, f"R{revision_id}"))
        conn.commit()
    _alembic_upgrade(db)
    _alembic_upgrade(db)  # idempotent
    with closing(sqlite3.connect(db)) as conn:
        assert conn.execute("SELECT id,scene_instance_id,snapshot FROM project_revisions ORDER BY id").fetchall() == [
            (revision_id, 5 if revision_id == 1 else None, snapshot) for revision_id, snapshot in rows
        ]
        indexes = {row[1] for row in conn.execute("PRAGMA index_list('project_revisions')")}
        assert "ix_project_revisions_scene_instance_id" in indexes


def test_create_all_database_upgrades_to_head(tmp_path):
    """Databases bootstrapped by Base.metadata.create_all must accept every migration."""
    db = tmp_path / "create_all.db"
    script = ("from sqlalchemy import create_engine; from app.database import Base; import app.models; "
              f"Base.metadata.create_all(create_engine('sqlite:///{db.as_posix()}'))")
    result = subprocess.run([sys.executable, "-c", script], cwd=Path(__file__).parents[1], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    _alembic_upgrade(db)
    with closing(sqlite3.connect(db)) as conn:
        assert conn.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "20261101_08"
