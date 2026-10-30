"""Pydantic schemas = the contract between the LLM, the app, the UI and the tests.

Design rules (each one is defensible in an interview):
1. extra="forbid": if the LLM adds a field like "estimated_cost", validation FAILS.
   The model cannot sneak in commitments we never asked for.
2. Every requirement is tagged origin = "stated" | "inferred".
   "stated" items MUST quote evidence from the inquiry -> we can verify them in code.
3. Phases have NO duration field and the blueprint has NO cost field (no unsupported commitments).
4. The LLM returns `LLMAnalysis`. The APP wraps it in `AnalysisReport` and owns the
   review status. The model never decides whether its own output is "approved".
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ServiceCategory(str, Enum):
    """Mirrors the four domains listed on cynbit.in, plus OTHER for anything outside them."""

    SOFTWARE_DEVELOPMENT = "software_development"
    AI_AUTOMATION = "ai_automation"
    CLOUD_INFRASTRUCTURE = "cloud_infrastructure"
    DIGITAL_MARKETING_SEO = "digital_marketing_seo"
    OTHER = "other"


class Requirement(StrictModel):
    text: str = Field(min_length=3, max_length=300)
    origin: Literal["stated", "inferred"]
    evidence: str | None = Field(default=None, max_length=300)  # verbatim quote if stated

    @model_validator(mode="after")
    def stated_requires_evidence(self, info: ValidationInfo) -> "Requirement":
        if self.origin == "stated" and not self.evidence:
            raise ValueError("A 'stated' requirement must include a verbatim evidence quote.")
        if self.origin == "inferred" and self.evidence is not None:
            raise ValueError("An 'inferred' requirement must not include stated evidence.")
        if self.origin == "inferred" and not self.text.casefold().startswith("potential:"):
            raise ValueError("An inferred requirement must be phrased as a potential need.")
        if self.origin == "stated" and self.text != self.evidence:
            raise ValueError("A stated requirement's text must match its evidence exactly.")
        inquiry = (info.context or {}).get("inquiry_text")
        if self.origin == "stated" and inquiry is not None and self.evidence not in inquiry:
            raise ValueError("Evidence for a 'stated' requirement must appear verbatim in the inquiry.")
        return self


class ClientConstraints(StrictModel):
    """Only fill a field if the client actually said it. Otherwise leave None."""

    user_scale: str | None = None
    timeline: str | None = None
    budget: str | None = None
    other: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def stated_values_appear_in_inquiry(self, info: ValidationInfo) -> "ClientConstraints":
        inquiry = (info.context or {}).get("inquiry_text")
        if inquiry is not None:
            values = [self.user_scale, self.timeline, self.budget, *self.other]
            for value in values:
                if value is not None and value not in inquiry:
                    raise ValueError("Client constraint values must appear verbatim in the inquiry.")
        return self


class MissingInfo(StrictModel):
    topic: str = Field(min_length=2, max_length=120)
    why_it_matters: str = Field(min_length=3, max_length=300)

    @field_validator("why_it_matters")
    @classmethod
    def rationale_is_potential(cls, value: str) -> str:
        if not value.casefold().startswith("potential:"):
            raise ValueError("Missing-information rationales must be labeled potential.")
        return value


class DiscoveryQuestion(StrictModel):
    question: str = Field(min_length=5, max_length=300)
    missing_information_topic: str = Field(min_length=2, max_length=120)


class Conflict(StrictModel):
    statement_a: str = Field(min_length=3, max_length=300)
    statement_b: str = Field(min_length=3, max_length=300)
    explanation: str = Field(min_length=5, max_length=300)

    @model_validator(mode="after")
    def statements_are_quoted(self, info: ValidationInfo) -> "Conflict":
        inquiry = (info.context or {}).get("inquiry_text")
        if inquiry is not None:
            if self.statement_a not in inquiry or self.statement_b not in inquiry:
                raise ValueError("Both conflict statements must be verbatim quotes from the inquiry.")
            if self.statement_a == self.statement_b:
                raise ValueError("A conflict requires two distinct statements.")
        if not self.explanation.casefold().startswith("potential:"):
            raise ValueError("Conflict explanations must be labeled potential.")
        return self


class Extraction(StrictModel):
    business_domain: str | None = Field(default=None, max_length=120)
    objectives: list[str] = Field(default_factory=list, max_length=10)
    functional_requirements: list[Requirement] = Field(default_factory=list, max_length=25)
    non_functional_requirements: list[Requirement] = Field(default_factory=list, max_length=15)
    constraints: ClientConstraints = Field(default_factory=ClientConstraints)
    service_categories: list[ServiceCategory] = Field(min_length=1)
    missing_information: list[MissingInfo] = Field(default_factory=list, max_length=15)
    discovery_questions: list[DiscoveryQuestion] = Field(min_length=1, max_length=12)
    conflicts: list[Conflict] = Field(default_factory=list, max_length=8)
    # Names must come from the Cynbit catalog (checked in the pipeline, Stage 3)
    overlapping_offerings: list[str] = Field(default_factory=list, max_length=5)

    @field_validator("objectives")
    @classmethod
    def objectives_are_quoted(cls, values: list[str], info: ValidationInfo) -> list[str]:
        inquiry = (info.context or {}).get("inquiry_text")
        if inquiry is not None and any(value not in inquiry for value in values):
            raise ValueError("Objectives must be verbatim quotes from the inquiry.")
        return values

    @field_validator("business_domain")
    @classmethod
    def business_domain_is_qualified(cls, value: str | None) -> str | None:
        if value is not None and not value.casefold().startswith("potential:"):
            raise ValueError("An inferred business domain must be labeled potential.")
        return value

    @field_validator("overlapping_offerings")
    @classmethod
    def offerings_are_in_catalog(
        cls, values: list[str], info: ValidationInfo
    ) -> list[str]:
        available = (info.context or {}).get("catalog_names")
        if available is not None:
            unknown = set(values) - set(available)
            if unknown:
                raise ValueError(
                    f"Offerings must match the public catalog; unknown names: {sorted(unknown)}."
                )
        return values

    @model_validator(mode="after")
    def questions_reference_missing_information(self) -> "Extraction":
        topics = {item.topic for item in self.missing_information}
        for item in self.discovery_questions:
            if item.missing_information_topic not in topics:
                raise ValueError(
                    "Each discovery question must reference a topic in missing_information."
                )
        return self

    @model_validator(mode="after")
    def constraints_are_not_requirements(self) -> "Extraction":
        constraint_values = [
            value for value in (
                self.constraints.user_scale,
                self.constraints.timeline,
                self.constraints.budget,
            )
            if value
        ]
        requirements = (
            self.functional_requirements + self.non_functional_requirements
        )
        for requirement in requirements:
            if requirement.origin != "stated" or requirement.evidence is None:
                continue
            evidence = requirement.evidence.casefold()
            if any(value.casefold() in evidence for value in constraint_values):
                raise ValueError(
                    "A user-scale, timeline, or budget constraint must not be classified "
                    "as a requirement."
                )
        return self


class TechOption(StrictModel):
    component: str = Field(min_length=2, max_length=80)
    suggestion: str = Field(min_length=2, max_length=120)
    rationale: str = Field(min_length=3, max_length=300)

    @model_validator(mode="after")
    def suggestion_is_provisional(self) -> "TechOption":
        if not self.suggestion.casefold().startswith("provisional:"):
            raise ValueError("Technology suggestions must be labeled provisional.")
        if not self.rationale.casefold().startswith("potential:"):
            raise ValueError("Technology rationales must be labeled potential.")
        return self


class Phase(StrictModel):
    # Deliberately NO duration/cost fields.
    name: str = Field(min_length=2, max_length=80)
    description: str = Field(min_length=3, max_length=400)

    @field_validator("description")
    @classmethod
    def descriptions_are_provisional(cls, value: str) -> str:
        if not value.casefold().startswith("provisional:"):
            raise ValueError("Phase descriptions must be labeled provisional.")
        return value


class BlueprintDraft(StrictModel):
    executive_summary: str = Field(min_length=20, max_length=1200)
    business_problem: str = Field(min_length=10, max_length=600)
    architecture_outline: list[str] = Field(min_length=1, max_length=10)
    technology_options: list[TechOption] = Field(default_factory=list, max_length=10)
    phases: list[Phase] = Field(min_length=1, max_length=8)
    risks: list[str] = Field(default_factory=list, max_length=10)
    assumptions_to_confirm: list[str] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def narrative_is_grounded_and_qualified(self, info: ValidationInfo) -> "BlueprintDraft":
        inquiry = (info.context or {}).get("inquiry_text")
        if inquiry is not None and self.business_problem not in inquiry:
            raise ValueError(
                "business_problem must be a verbatim quote from the inquiry, not an inferred workflow."
            )
        if any(not item.casefold().startswith("provisional:") for item in self.architecture_outline):
            raise ValueError("Every architecture item must be labeled provisional.")
        if any(not item.casefold().startswith("confirm ") for item in self.assumptions_to_confirm):
            raise ValueError("Each assumption must be framed as a human confirmation.")
        if any(not item.casefold().startswith("potential:") for item in self.risks):
            raise ValueError("Each risk must be labeled potential.")
        return self


class LLMAnalysis(StrictModel):
    """Exactly what we ask the LLM to return."""

    is_relevant: bool
    relevance_note: str = Field(min_length=3, max_length=300)
    extraction: Extraction | None = None
    blueprint: BlueprintDraft | None = None

    @model_validator(mode="after")
    def relevance_consistency(self) -> "LLMAnalysis":
        if self.is_relevant and self.extraction is None:
            raise ValueError("Relevant inquiries must include an extraction.")
        if self.is_relevant and self.blueprint is None:
            raise ValueError("Relevant inquiries must include a blueprint draft.")
        if not self.is_relevant and (self.extraction is not None or self.blueprint is not None):
            raise ValueError("Irrelevant inquiries must not include extraction or blueprint.")
        return self


class ReviewStatus(str, Enum):
    DRAFT = "draft_unreviewed"
    APPROVED = "approved_by_human"
    REJECTED = "rejected_by_human"


DISCLAIMER = (
    "AI-generated draft for internal discovery only. Not a proposal, quote or commitment on "
    "cost, timeline or feasibility. A human must review before sharing with a client."
)


class AnalysisReport(StrictModel):
    """What the app stores/shows: LLM output + metadata owned by the application."""

    inquiry_text: str
    analysis: LLMAnalysis
    review_status: ReviewStatus = ReviewStatus.DRAFT
    reviewer_notes: str = ""
    normalization_notes: list[str] = Field(default_factory=list)
    model_name: str = ""
    prompt_version: str = ""
    attempts: int = Field(default=1, ge=1)
    latency_seconds: float | None = Field(default=None, ge=0)
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    disclaimer: str = DISCLAIMER
