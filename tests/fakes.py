"""Test doubles. No network, no API key."""
from types import SimpleNamespace

from app.llm_client import LLMResult
from app.schemas import (
    BlueprintDraft, DiscoveryQuestion, Extraction, LLMAnalysis, MissingInfo, Phase,
    Requirement, ServiceCategory,
)


def valid_analysis() -> LLMAnalysis:
    return LLMAnalysis(
        is_relevant=True,
        relevance_note="Genuine software project inquiry.",
        extraction=Extraction(
            business_domain="Potential: healthcare scheduling",
            objectives=["book appointments online"],
            functional_requirements=[
                Requirement(text="book appointments online", origin="stated",
                            evidence="book appointments online"),
                Requirement(text="Potential: role-based access for staff", origin="inferred"),
            ],
            missing_information=[MissingInfo(
                topic="SMS provider",
                why_it_matters="Potential: this determines the integration approach.",
            )],
            service_categories=[ServiceCategory.SOFTWARE_DEVELOPMENT],
            discovery_questions=[DiscoveryQuestion(
                question="Which SMS provider do you use today?",
                missing_information_topic="SMS provider",
            )],
        ),
        blueprint=BlueprintDraft(
            executive_summary="Draft outline of a clinic appointment booking web application.",
            business_problem="book appointments online",
            architecture_outline=[
                "Provisional: Web frontend", "Provisional: API backend", "Provisional: Database"
            ],
            phases=[Phase(
                name="Discovery",
                description="Provisional: confirm requirements with the client.",
            )],
            assumptions_to_confirm=["Confirm whether the inquiry is limited to a web app."],
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
