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

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    def stated_requires_evidence(self) -> "Requirement":
        if self.origin == "stated" and not self.evidence:
            raise ValueError("A 'stated' requirement must include a verbatim evidence quote.")
        return self


class ClientConstraints(StrictModel):
    """Only fill a field if the client actually said it. Otherwise leave None."""

    user_scale: str | None = None
    timeline: str | None = None
    budget: str | None = None
    other: list[str] = Field(default_factory=list)


class MissingInfo(StrictModel):
    topic: str = Field(min_length=2, max_length=120)
    why_it_matters: str = Field(min_length=3, max_length=300)


class Extraction(StrictModel):
    business_domain: str | None = Field(default=None, max_length=120)
    objectives: list[str] = Field(default_factory=list, max_length=10)
    functional_requirements: list[Requirement] = Field(default_factory=list, max_length=25)
    non_functional_requirements: list[Requirement] = Field(default_factory=list, max_length=15)
    constraints: ClientConstraints = Field(default_factory=ClientConstraints)
    service_categories: list[ServiceCategory] = Field(min_length=1)
    missing_information: list[MissingInfo] = Field(default_factory=list, max_length=15)
    discovery_questions: list[str] = Field(min_length=1, max_length=12)
    conflicts: list[str] = Field(default_factory=list, max_length=8)
    # Names must come from the Cynbit catalog (checked in the pipeline, Stage 3)
    overlapping_offerings: list[str] = Field(default_factory=list, max_length=5)


class TechOption(StrictModel):
    component: str = Field(min_length=2, max_length=80)
    suggestion: str = Field(min_length=2, max_length=120)
    rationale: str = Field(min_length=3, max_length=300)


class Phase(StrictModel):
    # Deliberately NO duration/cost fields.
    name: str = Field(min_length=2, max_length=80)
    description: str = Field(min_length=3, max_length=400)


class BlueprintDraft(StrictModel):
    executive_summary: str = Field(min_length=20, max_length=1200)
    business_problem: str = Field(min_length=10, max_length=600)
    architecture_outline: list[str] = Field(min_length=1, max_length=10)
    technology_options: list[TechOption] = Field(default_factory=list, max_length=10)
    phases: list[Phase] = Field(min_length=1, max_length=8)
    risks: list[str] = Field(default_factory=list, max_length=10)
    assumptions_to_confirm: list[str] = Field(min_length=1, max_length=12)


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
    model_name: str = ""
    prompt_version: str = ""
    attempts: int = Field(default=1, ge=1)
    latency_seconds: float | None = Field(default=None, ge=0)
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    disclaimer: str = DISCLAIMER
