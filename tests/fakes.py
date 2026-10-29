"""Test doubles. No network, no API key."""
from types import SimpleNamespace

from app.llm_client import LLMResult
from app.schemas import (
    BlueprintDraft, Extraction, LLMAnalysis, Phase, Requirement, ServiceCategory,
)


def valid_analysis() -> LLMAnalysis:
    return LLMAnalysis(
        is_relevant=True,
        relevance_note="Genuine software project inquiry.",
        extraction=Extraction(
            business_domain="Healthcare scheduling",
            objectives=["Let patients book online"],
            functional_requirements=[
                Requirement(text="Online appointment booking", origin="stated",
                            evidence="book appointments online"),
                Requirement(text="Role-based access for staff", origin="inferred"),
            ],
            service_categories=[ServiceCategory.SOFTWARE_DEVELOPMENT],
            discovery_questions=["Which SMS provider do you use today?"],
        ),
        blueprint=BlueprintDraft(
            executive_summary="Draft outline of a clinic appointment booking web application.",
            business_problem="Appointments are not bookable online.",
            architecture_outline=["Web frontend", "API backend", "Database"],
            phases=[Phase(name="Discovery", description="Confirm requirements with the client.")],
            assumptions_to_confirm=["Web only, no native mobile app."],
        ),
    )


def valid_json() -> str:
    return valid_analysis().model_dump_json()


def irrelevant_json() -> str:
    return LLMAnalysis(is_relevant=False, relevance_note="Not a project request.").model_dump_json()


class FakeLLMClient:
    """Plays back scripted responses. An Exception instance in the script is raised."""

    model_name = "fake/model"

    def __init__(self, script):
        self.script = list(script)
        self.calls: list[list[dict]] = []

    def generate_json(self, messages, schema, schema_name):
        self.calls.append(messages)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return LLMResult(text=item, model=self.model_name, latency_seconds=0.01,
                         prompt_tokens=100, completion_tokens=50)


class StubSDK:
    """Mimics `groq.Groq().chat.completions.create` for GroqClient tests."""

    def __init__(self, script):
        self.script = list(script)
        self.requests: list[dict] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def sdk_response(content: str, finish_reason: str = "stop", prompt=120, completion=60):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content), finish_reason=finish_reason)],
        usage=SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion),
    )
