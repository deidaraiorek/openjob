from app.domains.jobs.deduplication import DiscoveryCandidate, normalize_url


def test_normalize_url_preserves_identifying_greenhouse_query_params() -> None:
    first = normalize_url("https://stripe.com/jobs/search?gh_jid=7532733")
    second = normalize_url("https://stripe.com/jobs/search?gh_jid=7306915")

    assert first == "stripe.com/jobs/search?gh_jid=7532733"
    assert second == "stripe.com/jobs/search?gh_jid=7306915"
    assert first != second


def test_normalize_url_ignores_non_identifying_query_params() -> None:
    value = normalize_url("https://stripe.com/jobs/search?gh_jid=7532733&utm_source=test")

    assert value == "stripe.com/jobs/search?gh_jid=7532733"


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
