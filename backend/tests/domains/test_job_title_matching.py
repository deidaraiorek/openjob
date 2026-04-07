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


def test_title_matching_accepts_safe_software_modifiers_for_new_grad_roles() -> None:
    result = match_title_against_catalog(
        "Software Engineer - New Grad - AI Platform",
        ["New Grad Software Engineer"],
    )

    assert result.matched is True
    assert result.normalized_core_title == "ai engineer platform software"
    assert result.matched_level_tokens == ["new grad"]
    assert result.ignored_modifier_tokens == ["ai", "platform"]


def test_title_matching_accepts_software_developer_as_software_engineer_family() -> None:
    result = match_title_against_catalog(
        "Software Developer - Early Career",
        ["Software Engineer I", "New Grad Software Engineer"],
    )

    assert result.matched is True
    assert result.normalized_core_title == "engineer software"
    assert result.matched_level_tokens == ["early career"]


def test_title_matching_accepts_new_grad_year_and_specialization_tokens() -> None:
    result = match_title_against_catalog(
        "New Grads 2026 - Software Engineer - Algorithm",
        ["New Grad Software Engineer"],
    )

    assert result.matched is True
    assert result.ignored_modifier_tokens == ["2026", "algorithm"]


def test_title_matching_allows_ambiguous_seniority_when_core_role_matches() -> None:
    result = match_title_against_catalog(
        "Software Engineer",
        ["Software Engineer I"],
    )

    assert result.matched is True
    assert result.reject_reason is None


def test_title_matching_rejects_out_of_catalog_families() -> None:
    result = match_title_against_catalog(
        "Data Engineer - Early Career",
        ["New Grad Software Engineer", "Software Engineer I"],
    )

    assert result.matched is False
    assert result.reject_reason == "family_mismatch"
    assert result.summary == "Title does not match the saved title catalog's role family."


def test_title_matching_rejects_senior_mismatch_when_catalog_has_no_senior_tokens() -> None:
    result = match_title_against_catalog(
        "Staff Machine Learning Engineer",
        ["New Grad Software Engineer", "Software Engineer I"],
    )

    assert result.matched is False
    assert result.reject_reason == "seniority_mismatch"


def test_title_matching_rejects_level_two_against_new_grad_catalog() -> None:
    result = match_title_against_catalog(
        "Software Engineer II",
        ["Software Engineer I", "New Grad Software Engineer"],
    )

    assert result.matched is False
    assert result.reject_reason == "seniority_mismatch"


def test_title_matching_rejects_senior_title_even_with_new_grad_program_tokens() -> None:
    result = match_title_against_catalog(
        "Senior Software Engineer - New Grad Programs",
        ["New Grad Software Engineer"],
    )

    assert result.matched is False
    assert result.reject_reason == "seniority_mismatch"


def test_title_matching_rejects_hardware_even_with_university_grad_marker() -> None:
    result = match_title_against_catalog(
        "Hardware Engineer - University Grad",
        ["New Grad Software Engineer"],
    )

    assert result.matched is False
    assert result.reject_reason == "family_mismatch"
