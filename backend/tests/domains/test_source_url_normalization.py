from app.domains.sources.models import JobSource
from app.domains.sources.url_normalization import (
    derive_greenhouse_board_token,
    derive_lever_company_slug,
    normalize_github_curated_url,
)


def _source(source_type: str, base_url: str | None, settings: dict | None = None) -> JobSource:
    return JobSource(
        account_id=1,
        source_key="test",
        source_type=source_type,
        name="Test",
        base_url=base_url,
        settings_json=settings or {},
        active=True,
    )


def test_greenhouse_embed_url_derives_board_token() -> None:
    source = _source(
        "greenhouse_board",
        "https://job-boards.greenhouse.io/embed/job_board?for=Stripe",
    )

    assert derive_greenhouse_board_token(source) == "stripe"


def test_greenhouse_board_url_derives_board_token() -> None:
    source = _source(
        "greenhouse_board",
        "https://job-boards.greenhouse.io/stripe",
    )

    assert derive_greenhouse_board_token(source) == "stripe"


def test_greenhouse_job_url_derives_board_token() -> None:
    source = _source(
        "greenhouse_board",
        "https://job-boards.greenhouse.io/stripe/jobs/1234567",
    )

    assert derive_greenhouse_board_token(source) == "stripe"


def test_lever_board_url_derives_company_slug() -> None:
    source = _source(
        "lever_postings",
        "https://jobs.lever.co/figma",
    )

    assert derive_lever_company_slug(source) == "figma"


def test_invalid_greenhouse_url_raises_clean_error() -> None:
    source = _source("greenhouse_board", "https://job-boards.greenhouse.io/embed/job_board")

    try:
        derive_greenhouse_board_token(source)
    except ValueError as exc:
        assert str(exc) == "Greenhouse sources need a valid board URL or settings.board_token."
    else:
        raise AssertionError("Expected ValueError for invalid Greenhouse URL")


def test_github_blob_url_normalizes_to_raw_readme_url() -> None:
    assert normalize_github_curated_url(
        "https://github.com/SimplifyJobs/New-Grad-Positions/blob/dev/README.md"
    ) == "https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/README.md"


def test_github_repo_url_defaults_to_head_readme() -> None:
    assert normalize_github_curated_url("https://github.com/SimplifyJobs/New-Grad-Positions") == (
        "https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/HEAD/README.md"
    )


def test_invalid_github_curated_url_raises_clean_error() -> None:
    try:
        normalize_github_curated_url("https://example.com/jobs")
    except ValueError as exc:
        assert str(exc) == "GitHub curated sources need a GitHub README URL."
    else:
        raise AssertionError("Expected ValueError for invalid GitHub curated URL")
