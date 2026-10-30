import pytest
from pydantic import ValidationError

from app.schemas import (
    AnalysisReport, BlueprintDraft, DiscoveryQuestion, Extraction, LLMAnalysis, MissingInfo, Phase, Requirement,
    ReviewStatus, ServiceCategory,
)


def make_extraction(**overrides) -> Extraction:
    data = dict(
        service_categories=[ServiceCategory.SOFTWARE_DEVELOPMENT],
        missing_information=[MissingInfo(topic="supported platforms", why_it_matters="This informs design.")],
        discovery_questions=[DiscoveryQuestion(
            question="Which platforms must be supported?",
            missing_information_topic="supported platforms",
        )],
    )
    data.update(overrides)
    return Extraction(**data)


def make_blueprint(**overrides) -> BlueprintDraft:
    data = dict(
        executive_summary="Draft summary of a web app for managing bookings for a small business.",
        business_problem="We want a booking app for our salon.",
        architecture_outline=["Provisional: Web frontend", "Provisional: REST API", "Provisional: Relational database"],
        phases=[Phase(name="Discovery", description="Confirm requirements with the client.")],
        assumptions_to_confirm=["Confirm whether the client wants a web app, a mobile app, or both."],
    )
    data.update(overrides)
    return BlueprintDraft(**data)


def test_stated_requirement_needs_evidence():
    with pytest.raises(ValidationError, match="evidence"):
        Requirement(text="Send rent reminders", origin="stated")


def test_stated_requirement_with_evidence_ok():
    r = Requirement(text="sending rent reminders", origin="stated", evidence="sending rent reminders")
    assert r.origin == "stated"


def test_stated_evidence_must_be_an_exact_quote_from_inquiry():
    with pytest.raises(ValidationError, match="verbatim"):
        Requirement.model_validate(
            {"text": "rent is due", "origin": "stated", "evidence": "rent is due"},
            context={"inquiry_text": "We need a tool for reminders."},
        )


def test_stated_requirement_cannot_add_details_beyond_its_quote():
    with pytest.raises(ValidationError, match="match its evidence exactly"):
        Requirement(
            text="Online booking with patient accounts", origin="stated",
            evidence="Patients can book appointments online",
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
    assert Requirement(text="Potential: role-based access control", origin="inferred").evidence is None


def test_inferred_requirement_must_be_labeled_as_potential():
    with pytest.raises(ValidationError, match="potential need"):
        Requirement(text="Role-based access control", origin="inferred")


def test_discovery_question_must_link_to_an_existing_information_gap():
    with pytest.raises(ValidationError, match="reference a topic"):
        make_extraction(
            discovery_questions=[DiscoveryQuestion(
                question="What is your preferred color scheme?",
                missing_information_topic="unlisted topic",
            )]
        )


def test_conflict_statements_must_be_quoted_from_inquiry():
    with pytest.raises(ValidationError, match="verbatim quotes"):
        Extraction.model_validate(
            {"service_categories": [ServiceCategory.SOFTWARE_DEVELOPMENT],
             "discovery_questions": [DiscoveryQuestion(
                 question="What timeline do you mean?", missing_information_topic="timeline"
             )],
             "missing_information": [{"topic": "timeline", "why_it_matters": "It affects scope."}],
             "conflicts": [{"statement_a": "launch tomorrow", "statement_b": "build everything",
                            "explanation": "The scope and schedule conflict."}]},
            context={"inquiry_text": "We need a website."},
        )


def test_conflict_can_be_returned_with_two_source_quotes():
    text = "We need launch in one week. Do not launch before security review is complete."
    extraction = Extraction.model_validate(
        {"service_categories": [ServiceCategory.SOFTWARE_DEVELOPMENT],
         "discovery_questions": [DiscoveryQuestion(
             question="Can the security review be completed before launch?",
             missing_information_topic="security review schedule",
         )],
         "missing_information": [{
             "topic": "security review schedule", "why_it_matters": "It affects launch readiness."
         }],
         "conflicts": [{
             "statement_a": "We need launch in one week.",
             "statement_b": "Do not launch before security review is complete.",
             "explanation": "The requested launch date may precede review completion.",
         }]},
        context={"inquiry_text": text},
    )
    assert len(extraction.conflicts) == 1


def test_technology_suggestions_must_be_provisional():
    from app.schemas import TechOption

    with pytest.raises(ValidationError, match="labeled provisional"):
        TechOption(component="Database", suggestion="PostgreSQL", rationale="Relational storage.")


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


def test_relevant_requires_blueprint():
    with pytest.raises(ValidationError, match="blueprint"):
        LLMAnalysis(
            is_relevant=True, relevance_note="Looks like a software request.",
            extraction=make_extraction(),
        )


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


def test_business_problem_must_be_quoted_from_inquiry():
    from app.schemas import LLMAnalysis

    analysis = LLMAnalysis(
        is_relevant=True, relevance_note="A software project request.",
        extraction=make_extraction(), blueprint=make_blueprint(),
    )
    with pytest.raises(ValidationError, match="business_problem must be a verbatim quote"):
        analysis.model_validate(
            analysis.model_dump(), context={"inquiry_text": "We need an appointment booking app."}
        )


def test_report_roundtrips_through_json():
    analysis = LLMAnalysis(is_relevant=False, relevance_note="Not a project inquiry.")
    report = AnalysisReport(inquiry_text="What is the weather in Jaipur today?", analysis=analysis)
    assert AnalysisReport.model_validate_json(report.model_dump_json()) == report
