"""Run only against the explicitly named, disposable localhost audit databases.

Does not create, drop or reset databases. The operator must supply two empty DBs.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url


def verify(url, legacy):
    target = make_url(url)
    if target.host != "127.0.0.1" or target.port != 55432 or not target.database.startswith(("audit_empty", "audit_legacy")):
        raise ValueError("Only isolated localhost:55432 audit_empty/audit_legacy are allowed")
    engine = create_engine(url)
    with engine.connect() as conn:
        if inspect(conn).get_table_names():
            raise ValueError("Audit requires an empty database; existing data will not be reset")
    def upgrade(revision):
        process = subprocess.run([sys.executable, "-m", "alembic", "upgrade", revision],
                                 cwd=Path(__file__).parents[1],
                                 env={**os.environ, "STEEL_COMPASS_DATABASE_URL": url},
                                 capture_output=True, text=True)
        if process.returncode:
            raise RuntimeError(process.stdout + process.stderr)
    if legacy:
        upgrade("20260730_01")
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO users VALUES (1,'legacy','legacy','unused',false,true,false,'2026-01-01')"))
            conn.execute(text("INSERT INTO projects VALUES (1,1,'retained','original','2026-01-01','2026-01-01')"))
            conn.execute(text("""INSERT INTO project_revisions VALUES
                (1,1,1,'1.0',CAST(:snapshot AS JSON),CAST(:result AS JSON),
                 '{}','legacy-engine','LEGACY-1','2026-01-01')"""),
                 {"snapshot": json.dumps({"legacy": True, "loads": [1, 2, 3]}),
                  "result": json.dumps({"verification_status": "unverified"})})
            before = conn.execute(text("SELECT snapshot,result_bundle,engine_version FROM project_revisions WHERE id=1")).one()
    upgrade("head")
    # Re-running migrations must be safe and idempotent.
    upgrade("head")
    with engine.connect() as conn:
        assert "scene_analysis_snapshots" in inspect(conn).get_table_names()
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == "20261101_08"
        if legacy:
            assert conn.execute(text("SELECT name,description FROM projects WHERE id=1")).one() == ("retained", "original")
            assert conn.execute(text("SELECT snapshot,result_bundle,engine_version FROM project_revisions WHERE id=1")).one() == before
        server = conn.execute(text("SHOW server_version")).scalar()
    engine.dispose()
    return {"database": target.database, "server_version": server, "legacy": legacy,
            "migration_head": "20261101_08", "idempotent": True,
            "historical_rows_preserved": legacy, "status": "passed"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = [verify(os.environ["AUDIT_EMPTY_DATABASE_URL"], False),
            verify(os.environ["AUDIT_LEGACY_DATABASE_URL"], True)]
    args.output.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(rows))
