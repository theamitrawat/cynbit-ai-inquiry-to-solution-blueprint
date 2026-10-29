import pytest
from pydantic import ValidationError

from app.schemas import (
    AnalysisReport, BlueprintDraft, Extraction, LLMAnalysis, Phase, Requirement,
    ReviewStatus, ServiceCategory,
)


def make_extraction(**overrides) -> Extraction:
    data = dict(
        service_categories=[ServiceCategory.SOFTWARE_DEVELOPMENT],
        discovery_questions=["Which platforms must be supported?"],
    )
    data.update(overrides)
    return Extraction(**data)


def make_blueprint(**overrides) -> BlueprintDraft:
    data = dict(
        executive_summary="Draft summary of a web app for managing bookings for a small business.",
        business_problem="Bookings are handled manually.",
        architecture_outline=["Web frontend", "REST API", "Relational database"],
        phases=[Phase(name="Discovery", description="Confirm requirements with the client.")],
        assumptions_to_confirm=["Client wants a web app, not a mobile app."],
    )
    data.update(overrides)
    return BlueprintDraft(**data)


def test_stated_requirement_needs_evidence():
    with pytest.raises(ValidationError, match="evidence"):
        Requirement(text="Send rent reminders", origin="stated")


def test_stated_requirement_with_evidence_ok():
    r = Requirement(text="Send rent reminders", origin="stated", evidence="sending rent reminders")
    assert r.origin == "stated"


def test_stated_evidence_must_be_an_exact_quote_from_inquiry():
    with pytest.raises(ValidationError, match="verbatim"):
        Requirement.model_validate(
            {"text": "Send rent reminders", "origin": "stated", "evidence": "rent is due"},
            context={"inquiry_text": "We need a tool for reminders."},
        )


def test_client_constraints_must_be_quoted_from_inquiry():
    with pytest.raises(ValidationError, match="verbatim"):
        Extraction.model_validate(
            {"service_categories": [ServiceCategory.SOFTWARE_DEVELOPMENT],
             "discovery_questions": ["How many patients?"],
             "constraints": {"user_scale": "2,000 patients"}},
            context={"inquiry_text": "We run three clinics."},
        )


def test_inferred_requirement_needs_no_evidence():
    assert Requirement(text="Role-based access control", origin="inferred").evidence is None


def test_llm_cannot_add_cost_field_to_blueprint():
    """extra='forbid' blocks unsupported commitments like cost estimates."""
    with pytest.raises(ValidationError, match="extra_forbidden|Extra inputs"):
        make_blueprint(estimated_cost_inr=500000)


def test_phase_has_no_duration_field():
    with pytest.raises(ValidationError):
        Phase(name="Build", description="Implement features.", duration_weeks=8)


def test_extraction_requires_a_category_and_a_question():
    with pytest.raises(ValidationError):
        make_extraction(service_categories=[])
    with pytest.raises(ValidationError):
        make_extraction(discovery_questions=[])


def test_invalid_category_rejected():
    with pytest.raises(ValidationError):
        make_extraction(service_categories=["quantum_computing"])


def test_relevant_requires_extraction():
    with pytest.raises(ValidationError, match="extraction"):
        LLMAnalysis(is_relevant=True, relevance_note="Looks like a software request.")


def test_irrelevant_must_not_have_output():
    with pytest.raises(ValidationError, match="Irrelevant"):
        LLMAnalysis(is_relevant=False, relevance_note="Not a project request.",
                    extraction=make_extraction())


def test_irrelevant_minimal_ok():
    a = LLMAnalysis(is_relevant=False, relevance_note="Not a project inquiry.")
    assert a.extraction is None and a.blueprint is None


def test_report_defaults_to_unreviewed_draft():
    analysis = LLMAnalysis(is_relevant=True, relevance_note="Software project.",
                           extraction=make_extraction(), blueprint=make_blueprint())
    report = AnalysisReport(inquiry_text="We need a booking app for our salon.", analysis=analysis)
    assert report.review_status == ReviewStatus.DRAFT
    assert "not a proposal" in report.disclaimer.lower()


def test_report_roundtrips_through_json():
    analysis = LLMAnalysis(is_relevant=False, relevance_note="Not a project inquiry.")
    report = AnalysisReport(inquiry_text="What is the weather in Jaipur today?", analysis=analysis)
    assert AnalysisReport.model_validate_json(report.model_dump_json()) == report
