"""Exercise migrations in isolated processes/databases, including retained old rows."""
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
        assert conn.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "20260813_07"
        if legacy:
            assert conn.execute("SELECT name,description FROM projects WHERE id=1").fetchone()==("retained","original")
