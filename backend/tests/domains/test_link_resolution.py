from app.domains.jobs.deduplication import DiscoveryCandidate
from app.domains.sources.link_classification import classify_resolved_target
from app.domains.sources.link_resolution import ResolvedLink, resolve_github_candidate, summarize_candidate_targets


def test_classify_resolved_target_upgrades_greenhouse_links_into_direct_targets() -> None:
    target = classify_resolved_target(
        source_url="https://simplify.jobs/jobs/acme-1",
        resolved_url="https://boards.greenhouse.io/acme/jobs/123",
        link_kind="listing",
        link_label="Software Engineer I",
    )

    assert target.target_type == "greenhouse_apply"
    assert target.destination_url == "https://boards.greenhouse.io/acme/jobs/123"
    assert target.compatibility_state == "api_compatible"
    assert target.metadata["board_token"] == "acme"
    assert target.metadata["job_post_id"] == "123"


def test_classify_resolved_target_routes_unknown_custom_domain_to_generic_browser_driver() -> None:
    target = classify_resolved_target(
        source_url="https://simplify.jobs/jobs/aurora-1",
        resolved_url="https://aurora.tech/careers/8402011002?gh_jid=8402011002",
        link_kind="apply",
    )

    assert target.target_type == "generic_career_page"
    assert target.compatibility_state == "browser_compatible"
    assert target.destination_url == "https://aurora.tech/careers/8402011002?gh_jid=8402011002"
    assert target.metadata.get("board_token") is None
    assert target.metadata.get("job_post_id") is None


def test_classify_resolved_target_sniffs_greenhouse_board_token_from_page_body() -> None:
    page_body = (
        '<script src="https://boards.greenhouse.io/embed/job_board/js?for=aurora"></script>'
    )
    target = classify_resolved_target(
        source_url="https://simplify.jobs/jobs/aurora-1",
        resolved_url="https://aurora.tech/careers/8402011002?gh_jid=8402011002",
        link_kind="apply",
        page_body=page_body,
    )

    assert target.target_type == "greenhouse_apply"
    assert target.compatibility_state == "api_compatible"
    assert target.metadata["board_token"] == "aurora"
    assert target.metadata["job_post_id"] == "8402011002"


def test_classify_resolved_target_sniffs_lever_company_slug_from_page_body() -> None:
    page_body = (
        '<script src="https://api.lever.co/v0/postings/weride?mode=iframe"></script>'
    )
    target = classify_resolved_target(
        source_url="https://simplify.jobs/jobs/weride-1",
        resolved_url="https://weride.ai/careers/abc12345-1234-1234-1234-123456789012",
        link_kind="apply",
        page_body=page_body,
    )

    assert target.target_type == "lever_apply"
    assert target.compatibility_state == "api_compatible"
    assert target.metadata["company_slug"] == "weride"
    assert target.metadata["posting_id"] == "abc12345-1234-1234-1234-123456789012"


def test_classify_resolved_target_sniffs_ashby_from_page_body() -> None:
    page_body = (
        '<script src="https://jobs.ashbyhq.com/acme/embed"></script>'
    )
    target = classify_resolved_target(
        source_url="https://simplify.jobs/jobs/acme-1",
        resolved_url="https://acme.com/careers/software-engineer",
        link_kind="apply",
        page_body=page_body,
    )

    assert target.target_type == "generic_career_page"
    assert target.compatibility_state == "browser_compatible"
    assert target.metadata["org_name"] == "acme"


def test_resolve_github_candidate_merges_duplicate_direct_targets_and_summarizes_compatibility(monkeypatch) -> None:
    candidate = DiscoveryCandidate(
        source_type="github_curated",
        company_name="Acme",
        title="Software Engineer I",
        location="Remote",
        listing_url="https://simplify.jobs/jobs/acme-1",
        apply_url="https://boards.greenhouse.io/acme/jobs/123",
        apply_target_type="external_link",
        raw_payload={
            "outbound_links": [
                {"kind": "listing", "label": "Software Engineer I", "url": "https://simplify.jobs/jobs/acme-1"},
                {"kind": "apply", "label": "Apply", "url": "https://boards.greenhouse.io/acme/jobs/123"},
            ]
        },
        metadata={"origin": "github_curated"},
    )

    def fake_resolve_link(source_url: str, *, timeout_seconds: float, max_redirects: int) -> ResolvedLink:
        if "simplify.jobs" in source_url:
            return ResolvedLink(
                source_url=source_url,
                resolved_url="https://boards.greenhouse.io/acme/jobs/123",
                redirect_chain=[source_url],
            )
        return ResolvedLink(
            source_url=source_url,
            resolved_url=source_url,
            redirect_chain=[],
        )

    monkeypatch.setattr("app.domains.sources.link_resolution.resolve_link", fake_resolve_link)

    resolved = resolve_github_candidate(candidate)
    summary = summarize_candidate_targets([resolved])

    assert resolved.apply_target_type == "greenhouse_apply"
    assert resolved.apply_url == "https://boards.greenhouse.io/acme/jobs/123"
    assert len(resolved.apply_targets) == 1
    assert resolved.apply_targets[0].metadata["source_urls"] == [
        "https://simplify.jobs/jobs/acme-1",
        "https://boards.greenhouse.io/acme/jobs/123",
    ]
    assert summary == {
        "api_compatible_targets": 1,
        "browser_compatible_targets": 0,
        "manual_only_targets": 0,
        "resolution_failed_targets": 0,
    }


def test_resolve_github_candidate_marks_failures_without_aborting_candidate(monkeypatch) -> None:
    candidate = DiscoveryCandidate(
        source_type="github_curated",
        company_name="Acme",
        title="Software Engineer I",
        location="Remote",
        listing_url="https://example.com/jobs/123",
        apply_url="https://example.com/jobs/123",
        apply_target_type="external_link",
        raw_payload={
            "outbound_links": [
                {"kind": "apply", "label": "Apply", "url": "https://example.com/jobs/123"},
            ]
        },
        metadata={"origin": "github_curated"},
    )

    monkeypatch.setattr(
        "app.domains.sources.link_resolution.resolve_link",
        lambda source_url, **_: ResolvedLink(
            source_url=source_url,
            resolved_url=source_url,
            redirect_chain=[],
            failure_reason="Timed out while resolving the outbound link.",
        ),
    )

    resolved = resolve_github_candidate(candidate)

    assert resolved.apply_targets[0].target_type == "external_link"
    assert resolved.apply_targets[0].metadata["compatibility_state"] == "resolution_failed"
    assert resolved.metadata["compatibility_reason"] == "Timed out while resolving the outbound link."
