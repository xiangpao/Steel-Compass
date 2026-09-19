from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import User, Project, SceneInstance
from app.core.site_profile import ProjectSiteProfile
from app.routers.project_routes import update_project_site_profile


def test_site_condition_change_invalidates_every_scene_draft_analysis():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = User(username="fixture",display_name="fixture",password_hash="unused")
        db.add(user)
        db.flush()
        project = Project(owner_id=user.id,name="isolated")
        db.add(project)
        db.flush()
        instance = SceneInstance(project_id=project.id,family_id="pergola-pavilion",variant_id="flat-single",
            title="fixture",template_version="fixture",draft_state={"last_analysis_snapshot_id":42,
            "last_analysis_package":{"old":True},"foundation_candidate_sets":{"old":True},"user_note":"keep"})
        db.add(instance)
        db.commit()
        update_project_site_profile(project.id,ProjectSiteProfile(basic_wind_pressure_kpa=0.9),db,user)
        db.refresh(instance)
        assert instance.draft_state["last_analysis_snapshot_id"] is None
        assert instance.draft_state["last_analysis_package"] is None
        assert instance.draft_state["foundation_candidate_sets"] == {}
        assert instance.draft_state["user_note"] == "keep"
    engine.dispose()


def test_client_draft_cannot_forge_or_restore_server_analysis():
    from app.routers.scene_routes import _client_draft
    result = _client_draft({"last_analysis_snapshot_id":42,"last_analysis_package":{"status":"passed"},
                            "foundation_candidate_sets":{"fake":True},"user_note":"keep"})
    assert result["last_analysis_snapshot_id"] is None
    assert result["last_analysis_package"] is None
    assert result["foundation_candidate_sets"] == {}
    assert result["user_note"] == "keep"
