from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.base import utcnow
from app.domains.application_accounts.models import ApplicationAccount
from app.domains.applications.platform_matrix import (
    credential_policy_for,
    driver_family_for,
    normalize_platform_family,
    normalize_tenant_host,
    platform_definition_for,
    platform_label,
)
from app.domains.applications.retry_policy import TerminalApplyError

if TYPE_CHECKING:
    from app.domains.jobs.models import ApplyTarget


@dataclass(frozen=True, slots=True)
class TargetReadiness:
    platform_family: str
    platform_label: str
    driver_family: str
    credential_policy: str
    tenant_host: str
    status: str
    reason: str | None
    application_account_id: int | None = None


def _fernet() -> Fernet:
    return Fernet(get_settings().application_account_secret_key.encode("utf-8"))


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:  # pragma: no cover - only hit on broken key rotation / bad data
        raise TerminalApplyError("Stored application credentials could not be decrypted.") from exc


def mask_login_identifier(value: str) -> str:
    if "@" in value:
        local_part, domain = value.split("@", 1)
        if len(local_part) <= 2:
            masked_local = local_part[:1] + "*"
        else:
            masked_local = f"{local_part[:1]}{'*' * max(len(local_part) - 2, 1)}{local_part[-1:]}"
        return f"{masked_local}@{domain}"

    if len(value) <= 2:
        return value[:1] + "*"

    return f"{value[:1]}{'*' * max(len(value) - 2, 1)}{value[-1:]}"


def list_application_accounts(session: Session, *, account_id: int) -> list[ApplicationAccount]:
    return session.scalars(
        select(ApplicationAccount)
        .where(ApplicationAccount.account_id == account_id)
        .order_by(
            ApplicationAccount.platform_family.asc(),
            ApplicationAccount.tenant_host.asc(),
            ApplicationAccount.id.asc(),
        )
    ).all()


def create_application_account(
    session: Session,
    *,
    account_id: int,
    platform_family: str,
    tenant_host: str | None,
    login_identifier: str,
    password: str,
) -> ApplicationAccount:
    normalized_family = normalize_platform_family(platform_family)
    policy = platform_definition_for(destination_url=None, metadata={"platform_family": normalized_family}).credential_policy
    if policy == "not_needed":
        raise ValueError(f"{platform_label(normalized_family)} does not use stored application accounts.")

    normalized_login_identifier = login_identifier.strip()
    if not normalized_login_identifier:
        raise ValueError("Login email or username is required.")
    if not password.strip():
        raise ValueError("Password is required.")

    normalized_host = normalize_tenant_host(tenant_host)
    existing = session.scalar(
        select(ApplicationAccount).where(
            ApplicationAccount.account_id == account_id,
            ApplicationAccount.platform_family == normalized_family,
            ApplicationAccount.tenant_host == normalized_host,
        )
    )
    if existing:
        raise ValueError("An application account already exists for that platform and employer host.")

    account = ApplicationAccount(
        account_id=account_id,
        platform_family=normalized_family,
        tenant_host=normalized_host,
        login_identifier=normalized_login_identifier,
        secret_ciphertext=encrypt_secret(password),
        credential_status="ready",
        last_failure_message=None,
    )
    session.add(account)
    session.flush()
    return account


def update_application_account(
    session: Session,
    *,
    record: ApplicationAccount,
    platform_family: str,
    tenant_host: str | None,
    login_identifier: str | None,
    password: str | None,
) -> ApplicationAccount:
    normalized_family = normalize_platform_family(platform_family)
    policy = platform_definition_for(destination_url=None, metadata={"platform_family": normalized_family}).credential_policy
    if policy == "not_needed":
        raise ValueError(f"{platform_label(normalized_family)} does not use stored application accounts.")

    normalized_host = normalize_tenant_host(tenant_host)
    conflicting = session.scalar(
        select(ApplicationAccount).where(
            ApplicationAccount.account_id == record.account_id,
            ApplicationAccount.platform_family == normalized_family,
            ApplicationAccount.tenant_host == normalized_host,
            ApplicationAccount.id != record.id,
        )
    )
    if conflicting:
        raise ValueError("An application account already exists for that platform and employer host.")

    normalized_login_identifier = login_identifier.strip() if login_identifier and login_identifier.strip() else record.login_identifier
    record.platform_family = normalized_family
    record.tenant_host = normalized_host
    record.login_identifier = normalized_login_identifier
    if password is not None and password.strip():
        record.secret_ciphertext = encrypt_secret(password)
        record.credential_status = "ready"
        record.last_failure_at = None
        record.last_failure_message = None
    return record


def delete_application_account(session: Session, *, record: ApplicationAccount) -> None:
    session.delete(record)


def record_login_success(record: ApplicationAccount, *, when: datetime | None = None) -> None:
    record.credential_status = "ready"
    record.last_successful_at = when or utcnow()
    record.last_failure_at = None
    record.last_failure_message = None


def record_login_failure(record: ApplicationAccount, *, message: str, when: datetime | None = None) -> None:
    record.credential_status = "login_failed"
    record.last_failure_at = when or utcnow()
    record.last_failure_message = message


def find_application_account_for_target(
    session: Session,
    *,
    account_id: int,
    target: ApplyTarget,
) -> ApplicationAccount | None:
    tenant_host = normalize_tenant_host(
        target.metadata_json.get("tenant_host")
        if isinstance(target.metadata_json, dict)
        else None
    ) or normalize_tenant_host(target.destination_url)
    platform_family = normalize_platform_family(
        platform_definition_for(
            destination_url=target.destination_url,
            target_type=target.target_type,
            metadata=target.metadata_json,
        ).family
    )

    record = session.scalar(
        select(ApplicationAccount).where(
            ApplicationAccount.account_id == account_id,
            ApplicationAccount.platform_family == platform_family,
            ApplicationAccount.tenant_host == tenant_host,
        )
    )
    if record is not None:
        return record

    if not tenant_host:
        return None

    return session.scalar(
        select(ApplicationAccount).where(
            ApplicationAccount.account_id == account_id,
            ApplicationAccount.platform_family == platform_family,
            ApplicationAccount.tenant_host == "",
        )
    )


def resolve_target_readiness(
    session: Session,
    *,
    account_id: int,
    target: ApplyTarget,
) -> TargetReadiness:
    definition = platform_definition_for(
        destination_url=target.destination_url,
        target_type=target.target_type,
        metadata=target.metadata_json,
    )
    tenant_host = normalize_tenant_host(
        target.metadata_json.get("tenant_host")
        if isinstance(target.metadata_json, dict)
        else None
    ) or normalize_tenant_host(target.destination_url)
    driver_family = driver_family_for(
        destination_url=target.destination_url,
        target_type=target.target_type,
        metadata=target.metadata_json,
    )
    credential_policy = credential_policy_for(
        destination_url=target.destination_url,
        target_type=target.target_type,
        metadata=target.metadata_json,
    )
    compatibility_reason = None
    if isinstance(target.metadata_json, dict):
        raw_compatibility_reason = target.metadata_json.get("compatibility_reason")
        if isinstance(raw_compatibility_reason, str) and raw_compatibility_reason.strip():
            compatibility_reason = raw_compatibility_reason.strip()

    if definition.family == "external":
        return TargetReadiness(
            platform_family=definition.family,
            platform_label=definition.label,
            driver_family=driver_family,
            credential_policy=credential_policy,
            tenant_host=tenant_host,
            status="manual_only",
            reason=compatibility_reason or "No automation driver is available for this link yet.",
        )

    if target.target_type == "external_link":
        if not definition.implemented:
            return TargetReadiness(
                platform_family=definition.family,
                platform_label=definition.label,
                driver_family=driver_family,
                credential_policy=credential_policy,
                tenant_host=tenant_host,
                status="platform_not_supported",
                reason=f"{definition.label} is recognized but not supported yet.",
            )
        return TargetReadiness(
            platform_family=definition.family,
            platform_label=definition.label,
            driver_family=driver_family,
            credential_policy=credential_policy,
            tenant_host=tenant_host,
            status="manual_only",
            reason=compatibility_reason
            or (
                f"{definition.label} link is recognized, but this generic external target "
                "still needs a target upgrade before it can run automatically."
            ),
        )

    if not definition.implemented:
        return TargetReadiness(
            platform_family=definition.family,
            platform_label=definition.label,
            driver_family=driver_family,
            credential_policy=credential_policy,
            tenant_host=tenant_host,
            status="platform_not_supported",
            reason=f"{definition.label} is recognized but not supported yet.",
        )

    if credential_policy in {"tenant_required", "optional"}:
        record = find_application_account_for_target(session, account_id=account_id, target=target)
        if record is not None:
            return TargetReadiness(
                platform_family=definition.family,
                platform_label=definition.label,
                driver_family=driver_family,
                credential_policy=credential_policy,
                tenant_host=tenant_host,
                status=record.credential_status if record.credential_status != "ready" else "ready",
                reason=record.last_failure_message,
                application_account_id=record.id,
            )

    if credential_policy == "tenant_required":
        host_label = tenant_host or "this employer host"
        if record is None:
            return TargetReadiness(
                platform_family=definition.family,
                platform_label=definition.label,
                driver_family=driver_family,
                credential_policy=credential_policy,
                tenant_host=tenant_host,
                status="missing_application_account",
                reason=f"Add an application account for {definition.label} and {host_label} before running this target.",
            )

    return TargetReadiness(
        platform_family=definition.family,
        platform_label=definition.label,
        driver_family=driver_family,
        credential_policy=credential_policy,
        tenant_host=tenant_host,
        status="ready",
        reason=None,
    )


def ensure_target_ready(
    session: Session,
    *,
    account_id: int,
    target: ApplyTarget,
) -> TargetReadiness:
    readiness = resolve_target_readiness(session, account_id=account_id, target=target)
    if readiness.status == "ready":
        return readiness
    raise TerminalApplyError(readiness.reason or "This target is not ready to run.")
