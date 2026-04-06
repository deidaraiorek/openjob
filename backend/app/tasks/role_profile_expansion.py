from __future__ import annotations

from sqlalchemy import select

from app.celery_app import celery_app
from app.db.session import get_session_factory
from app.domains.role_profiles.models import RoleProfile
from app.integrations.openai.role_profile import expand_role_profile_prompt


@celery_app.task(name="app.tasks.role_profile_expansion.expand_role_profile")
def expand_role_profile(profile_id: int) -> dict[str, list[str]]:
    session_factory = get_session_factory()
    with session_factory() as session:
        profile = session.scalar(select(RoleProfile).where(RoleProfile.id == profile_id))
        if not profile:
            return {"generated_titles": [], "generated_keywords": []}

        expanded = expand_role_profile_prompt(profile.prompt)
        profile.generated_titles = expanded["generated_titles"]
        profile.generated_keywords = []
        session.commit()
        return expanded
