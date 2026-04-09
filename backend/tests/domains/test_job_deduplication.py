from app.domains.jobs.deduplication import DiscoveryCandidate, normalize_url


def test_normalize_url_preserves_identifying_greenhouse_query_params() -> None:
    first = normalize_url("https://stripe.com/jobs/search?gh_jid=7532733")
    second = normalize_url("https://stripe.com/jobs/search?gh_jid=7306915")

    assert first == "https://stripe.com/jobs/search?gh_jid=7532733"
    assert second == "https://stripe.com/jobs/search?gh_jid=7306915"
    assert first != second


def test_normalize_url_ignores_non_identifying_query_params() -> None:
    value = normalize_url("https://stripe.com/jobs/search?gh_jid=7532733&utm_source=test")

    assert value == "https://stripe.com/jobs/search?gh_jid=7532733"


def test_normalize_url_extracts_workday_job_key() -> None:
    value = normalize_url(
        "https://generalmotors.wd5.myworkdayjobs.com/en-US/Careers_GM/job/Markham-Ontario-Canada/Software-Developer---Early-Career_JR-202518896?utm_source=Simplify&ref=Simplify"
    )

    assert (
        value
        == "https://generalmotors.wd5.myworkdayjobs.com/Software-Developer---Early-Career_JR-202518896"
    )


def test_normalize_url_extracts_lever_job_key() -> None:
    value = normalize_url(
        "https://jobs.lever.co/weride/1dc0209a-f90b-4f1c-a614-75f5b7883e6d/apply?utm_source=Simplify&ref=Simplify"
    )

    assert value == "https://jobs.lever.co/weride/1dc0209a-f90b-4f1c-a614-75f5b7883e6d/"


def test_normalize_url_extracts_icims_job_key() -> None:
    value = normalize_url(
        "https://careers-gdms.icims.com/jobs/69999/job?mobile=true&needsRedirect=false&utm_source=Simplify&ref=Simplify"
    )

    assert value == "https://careers-gdms.icims.com/69999"


def test_normalize_url_extracts_ashby_job_key() -> None:
    value = normalize_url(
        "https://jobs.ashbyhq.com/glide/5ece3064-6884-43c2-923c-066d6187b25d/application?utm_source=Simplify&ref=Simplify"
    )

    assert value == "https://jobs.ashbyhq.com/glide/5ece3064-6884-43c2-923c-066d6187b25d"


def test_build_canonical_key_is_not_the_only_identity_for_greenhouse_urls() -> None:
    first = DiscoveryCandidate(
        source_type="greenhouse_board",
        company_name="Stripe",
        title="Software Engineer",
        location="Remote",
        listing_url="https://stripe.com/jobs/search?gh_jid=1",
    )
    second = DiscoveryCandidate(
        source_type="greenhouse_board",
        company_name="Stripe",
        title="Software Engineer",
        location="Remote",
        listing_url="https://stripe.com/jobs/search?gh_jid=2",
    )

    assert normalize_url(first.listing_url) != normalize_url(second.listing_url)
