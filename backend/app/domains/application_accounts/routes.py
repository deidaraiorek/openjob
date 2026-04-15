from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.domains.accounts.dependencies import get_current_account
from app.domains.accounts.models import Account
from app.domains.application_accounts.models import ApplicationAccount
from app.domains.application_accounts.service import (
    create_application_account,
    delete_application_account,
    list_application_accounts,
    mask_login_identifier,
    update_application_account,
)
from app.domains.applications.platform_matrix import platform_label

router = APIRouter(prefix="/application-accounts", tags=["application-accounts"])


class ApplicationAccountCreateRequest(BaseModel):
    platform_family: str
    tenant_host: str | None = None
    login_identifier: str
    password: str = Field(min_length=1)


class ApplicationAccountUpdateRequest(BaseModel):
    platform_family: str
    tenant_host: str | None = None
    login_identifier: str | None = None
    password: str | None = None


class ApplicationAccountResponse(BaseModel):
    id: int
    platform_family: str
    platform_label: str
    tenant_host: str
    login_identifier_masked: str
    credential_status: str
    last_successful_at: datetime | None
    last_failure_at: datetime | None
    last_failure_message: str | None


def serialize_application_account(record: ApplicationAccount) -> ApplicationAccountResponse:
    return ApplicationAccountResponse(
        id=record.id,
        platform_family=record.platform_family,
        platform_label=platform_label(record.platform_family),
        tenant_host=record.tenant_host,
        login_identifier_masked=mask_login_identifier(record.login_identifier),
        credential_status=record.credential_status,
        last_successful_at=record.last_successful_at,
        last_failure_at=record.last_failure_at,
        last_failure_message=record.last_failure_message,
    )


@router.get("", response_model=list[ApplicationAccountResponse])
def list_application_accounts_route(
    current_account: Account = Depends(get_current_account),
    session: Session = Depends(get_db_session),
) -> list[ApplicationAccountResponse]:
    records = list_application_accounts(session, account_id=current_account.id)
    return [serialize_application_account(record) for record in records]


@router.post("", response_model=ApplicationAccountResponse, status_code=status.HTTP_201_CREATED)
def create_application_account_route(
    payload: ApplicationAccountCreateRequest,
    current_account: Account = Depends(get_current_account),
    session: Session = Depends(get_db_session),
) -> ApplicationAccountResponse:
    try:
        record = create_application_account(
            session,
            account_id=current_account.id,
            platform_family=payload.platform_family,
            tenant_host=payload.tenant_host,
            login_identifier=payload.login_identifier,
            password=payload.password,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    session.commit()
    session.refresh(record)
    return serialize_application_account(record)


@router.put("/{application_account_id}", response_model=ApplicationAccountResponse)
def update_application_account_route(
    application_account_id: int,
    payload: ApplicationAccountUpdateRequest,
    current_account: Account = Depends(get_current_account),
    session: Session = Depends(get_db_session),
) -> ApplicationAccountResponse:
    record = session.scalar(
        select(ApplicationAccount).where(
            ApplicationAccount.id == application_account_id,
            ApplicationAccount.account_id == current_account.id,
        )
    )
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application account not found")

    try:
        update_application_account(
            session,
            record=record,
            platform_family=payload.platform_family,
            tenant_host=payload.tenant_host,
            login_identifier=payload.login_identifier,
            password=payload.password,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    session.commit()
    session.refresh(record)
    return serialize_application_account(record)


@router.delete("/{application_account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_application_account_route(
    application_account_id: int,
    current_account: Account = Depends(get_current_account),
    session: Session = Depends(get_db_session),
) -> None:
    record = session.scalar(
        select(ApplicationAccount).where(
            ApplicationAccount.id == application_account_id,
            ApplicationAccount.account_id == current_account.id,
        )
    )
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application account not found")

    delete_application_account(session, record=record)
    session.commit()
