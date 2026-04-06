from app.domains.jobs.title_matching import match_title_against_catalog


def test_title_matching_accepts_reordered_new_grad_titles() -> None:
    result = match_title_against_catalog(
        "Software Engineer, New Grad",
        ["New Grad Software Engineer", "Backend Engineer"],
    )

    assert result.matched is True
    assert result.matched_titles == ["New Grad Software Engineer"]


def test_title_matching_accepts_roman_and_numeric_level_variants() -> None:
    result = match_title_against_catalog(
        "Software Engineer 1",
        ["Software Engineer I"],
    )

    assert result.matched is True


def test_title_matching_rejects_out_of_catalog_families() -> None:
    result = match_title_against_catalog(
        "Data Engineer",
        ["New Grad Software Engineer", "Software Engineer I"],
    )

    assert result.matched is False


def test_title_matching_rejects_senior_mismatch_when_catalog_has_no_senior_tokens() -> None:
    result = match_title_against_catalog(
        "Staff Machine Learning Engineer",
        ["New Grad Software Engineer", "Software Engineer I"],
    )

    assert result.matched is False
