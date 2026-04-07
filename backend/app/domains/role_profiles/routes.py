from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.accounts.dependencies import get_current_account
from app.domains.accounts.models import Account
from app.domains.role_profiles.models import RoleProfile
from app.db.session import get_db_session
from app.tasks.job_relevance import rescore_account_jobs_now

router = APIRouter(prefix="/role-profile", tags=["role-profile"])


class RoleProfileUpsertRequest(BaseModel):
    prompt: str
    generated_titles: list[str] = Field(default_factory=list)
    generated_keywords: list[str] = Field(default_factory=list)


class RoleProfileResponse(BaseModel):
    id: int
    prompt: str
    generated_titles: list[str]
    generated_keywords: list[str]


def serialize_role_profile(profile: RoleProfile) -> RoleProfileResponse:
    return RoleProfileResponse(
        id=profile.id,
        prompt=profile.prompt,
        generated_titles=profile.generated_titles,
        generated_keywords=profile.generated_keywords,
    )


@router.get("", response_model=RoleProfileResponse)
def get_role_profile(
    current_account: Account = Depends(get_current_account),
    session: Session = Depends(get_db_session),
) -> RoleProfileResponse:
    profile = session.scalar(
        select(RoleProfile).where(RoleProfile.account_id == current_account.id),
    )
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role profile not found")
    return serialize_role_profile(profile)


@router.put("", response_model=RoleProfileResponse)
def upsert_role_profile(
    payload: RoleProfileUpsertRequest,
    current_account: Account = Depends(get_current_account),
    session: Session = Depends(get_db_session),
) -> RoleProfileResponse:
    profile = session.scalar(
        select(RoleProfile).where(RoleProfile.account_id == current_account.id),
    )
    if not profile:
        profile = RoleProfile(account_id=current_account.id, prompt=payload.prompt)
        session.add(profile)

    profile.prompt = payload.prompt
    profile.generated_titles = payload.generated_titles
    profile.generated_keywords = []

    session.commit()
    rescore_account_jobs_now(session, account_id=current_account.id)
    session.refresh(profile)
    return serialize_role_profile(profile)
