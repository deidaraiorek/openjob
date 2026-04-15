from app.domains.accounts.service import ensure_account
from app.domains.application_accounts.service import (
    create_application_account,
    decrypt_secret,
    encrypt_secret,
    resolve_target_readiness,
)
from app.domains.jobs.models import ApplyTarget


def test_encrypt_secret_round_trip() -> None:
    ciphertext = encrypt_secret("super-secret-password")

    assert ciphertext != "super-secret-password"
    assert decrypt_secret(ciphertext) == "super-secret-password"


def test_create_application_account_allows_distinct_tenants_and_rejects_duplicate(db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")

    first = create_application_account(
        db_session,
        account_id=account.id,
        platform_family="icims",
        tenant_host="acme.icims.com",
        login_identifier="owner@example.com",
        password="hunter2",
    )
    second = create_application_account(
        db_session,
        account_id=account.id,
        platform_family="icims",
        tenant_host="globex.icims.com",
        login_identifier="owner@example.com",
        password="hunter2",
    )

    assert first.tenant_host == "acme.icims.com"
    assert second.tenant_host == "globex.icims.com"

    try:
        create_application_account(
            db_session,
            account_id=account.id,
            platform_family="icims",
            tenant_host="acme.icims.com",
            login_identifier="owner@example.com",
            password="hunter2",
        )
    except ValueError as exc:
        assert str(exc) == "An application account already exists for that platform and employer host."
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("Expected duplicate platform+tenant creation to fail.")


def test_resolve_target_readiness_requires_platform_account_when_metadata_demands_it(db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")
    target = ApplyTarget(
        target_type="linkedin_easy_apply",
        destination_url="https://www.linkedin.com/jobs/view/123",
        metadata_json={"credential_policy": "tenant_required"},
    )

    readiness = resolve_target_readiness(db_session, account_id=account.id, target=target)

    assert readiness.platform_family == "linkedin"
    assert readiness.status == "missing_application_account"
    assert readiness.reason is not None
    assert "Add an application account" in readiness.reason


def test_resolve_target_readiness_uses_optional_account_status_when_present(db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")
    stored = create_application_account(
        db_session,
        account_id=account.id,
        platform_family="linkedin",
        tenant_host="",
        login_identifier="owner@example.com",
        password="hunter2",
    )
    stored.credential_status = "login_failed"
    stored.last_failure_message = "LinkedIn rejected the stored password."
    db_session.commit()

    target = ApplyTarget(
        target_type="linkedin_easy_apply",
        destination_url="https://www.linkedin.com/jobs/view/123",
        metadata_json={"linkedin_job_id": "123"},
    )

    readiness = resolve_target_readiness(db_session, account_id=account.id, target=target)

    assert readiness.platform_family == "linkedin"
    assert readiness.status == "login_failed"
    assert readiness.reason == "LinkedIn rejected the stored password."
    assert readiness.application_account_id == stored.id


def test_resolve_target_readiness_keeps_recognized_external_links_manual_until_upgraded(db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")
    target = ApplyTarget(
        target_type="external_link",
        destination_url="https://jobs.lever.co/acme/lever-123/apply",
        metadata_json={"origin": "github_curated"},
    )

    readiness = resolve_target_readiness(db_session, account_id=account.id, target=target)

    assert readiness.platform_family == "lever"
    assert readiness.platform_label == "Lever"
    assert readiness.status == "manual_only"
    assert readiness.reason is not None
    assert "target upgrade" in readiness.reason
