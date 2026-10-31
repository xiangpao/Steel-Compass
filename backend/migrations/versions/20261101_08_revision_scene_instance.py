"""index scene revisions by scene instance

Revision ID: 20261101_08
Revises: 20260813_07
"""

from alembic import op
import sqlalchemy as sa


revision = "20261101_08"
down_revision = "20260813_07"
branch_labels = None
depends_on = None

INDEX = "ix_project_revisions_scene_instance_id"
BATCH_SIZE = 200


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # Databases created by Base.metadata.create_all already have the column.
    if "scene_instance_id" not in {item["name"] for item in inspector.get_columns("project_revisions")}:
        op.add_column("project_revisions", sa.Column("scene_instance_id", sa.Integer(), nullable=True))
    if INDEX not in {item["name"] for item in inspector.get_indexes("project_revisions")}:
        op.create_index(INDEX, "project_revisions", ["scene_instance_id"])

    # Backfill from the snapshot JSON; the snapshot itself is only read.
    revisions = sa.table(
        "project_revisions",
        sa.column("id", sa.Integer()),
        sa.column("snapshot", sa.JSON()),
        sa.column("scene_instance_id", sa.Integer()),
    )
    pending_ids = bind.execute(
        sa.select(revisions.c.id).where(revisions.c.scene_instance_id.is_(None)).order_by(revisions.c.id)
    ).scalars().all()
    # Snapshots can be large; read them a chunk at a time.
    for start in range(0, len(pending_ids), BATCH_SIZE):
        chunk = pending_ids[start:start + BATCH_SIZE]
        updates = []
        for revision_id, snapshot in bind.execute(
            sa.select(revisions.c.id, revisions.c.snapshot).where(revisions.c.id.in_(chunk))
        ):
            scene_context = snapshot.get("scene_context") if isinstance(snapshot, dict) else None
            instance_id = scene_context.get("scene_instance_id") if isinstance(scene_context, dict) else None
            if isinstance(instance_id, int) and not isinstance(instance_id, bool):
                updates.append({"revision_id": revision_id, "instance_id": instance_id})
        if updates:
            bind.execute(
                revisions.update()
                .where(revisions.c.id == sa.bindparam("revision_id"))
                .values(scene_instance_id=sa.bindparam("instance_id")),
                updates,
            )


def downgrade() -> None:
    op.drop_index(INDEX, table_name="project_revisions")
    with op.batch_alter_table("project_revisions") as batch_op:
        batch_op.drop_column("scene_instance_id")
