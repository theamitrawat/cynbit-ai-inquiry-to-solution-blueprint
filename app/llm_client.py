"""Thin wrapper around the Groq SDK.

Responsibilities (and nothing more):
  1. Build the request (JSON-schema structured output, reasoning effort for gpt-oss models).
  2. Measure latency and token usage.
  3. Translate provider exceptions into our own errors with user-safe messages.

Validation of the *content* is NOT done here - that is the pipeline's job.
The rest of the app depends on the small `LLMClient` protocol, so tests can use a fake
client and a different provider could be added without touching the pipeline.
"""
import logging
import time
from dataclasses import dataclass
from typing import Any, Protocol

import groq

from app.config import Settings, get_settings
from app.errors import (
    LLMAuthError, LLMConfigError, LLMOutputError, LLMRequestError,
    LLMTruncatedError, LLMUnavailableError,
)
from app.schema_utils import to_strict_json_schema

logger = logging.getLogger(__name__)

# Groq returns HTTP 400 with these phrases when the model produced output that
# does not fit the schema (best-effort mode). That is an OUTPUT problem -> retryable.
_GENERATION_FAILED_HINTS = (
    "does not match the expected schema",
    "json_validate_failed",
    "failed to generate json",
)
# Phrases suggesting Groq rejected the schema/response_format ITSELF.
_SCHEMA_REJECTED_HINTS = ("response format", "response_format", "json_schema", "strict", "schema")


@dataclass(frozen=True)
class LLMResult:
    text: str
    model: str
    latency_seconds: float
    prompt_tokens: int | None
    completion_tokens: int | None


class LLMClient(Protocol):
    model_name: str

    def generate_json(
        self, messages: list[dict[str, str]], schema: dict[str, Any], schema_name: str
    ) -> LLMResult: ...


class GroqClient:
    def __init__(self, settings: Settings | None = None, sdk_client: Any | None = None) -> None:
        s = settings or get_settings()
        if not s.llm_model:
            raise LLMConfigError("LLM_MODEL is not set. See .env.example.")

        if sdk_client is None:
            key = s.llm_api_key.get_secret_value() if s.llm_api_key else ""
            if not key:
                raise LLMConfigError(
                    "LLM_API_KEY is not set. Copy .env.example to .env and add your Groq API key."
                )
            sdk_client = groq.Groq(
                api_key=key, timeout=s.llm_timeout_seconds, max_retries=s.llm_max_retries
            )

        self._sdk = sdk_client
        self._settings = s
        self._strict = s.llm_strict_schema
        self.model_name = s.llm_model

    # ------------------------------------------------------------------ public
    def generate_json(
        self, messages: list[dict[str, str]], schema: dict[str, Any], schema_name: str
    ) -> LLMResult:
        started = time.perf_counter()
        try:
            try:
                resp = self._create(messages, schema, schema_name, self._strict)
            except groq.BadRequestError as exc:
                if self._strict and (_is_schema_rejection(exc) or _is_strict_output_rejection(exc)):
                    logger.warning(
                        "Groq rejected strict structured output; retrying once in best-effort mode."
                    )
                    self._strict = False
                    resp = self._create(messages, schema, schema_name, False)
                else:
                    raise
        except groq.BadRequestError as exc:
            raise _map_bad_request(exc) from exc
        except (groq.AuthenticationError, groq.PermissionDeniedError) as exc:
            raise LLMAuthError("Groq rejected the API key. Check LLM_API_KEY in your .env.") from exc
        except groq.RateLimitError as exc:
            raise LLMUnavailableError(
                "Groq rate limit reached (free tier limits are per minute and per day). "
                "Wait a minute and try again."
            ) from exc
        except groq.APITimeoutError as exc:  # subclass of APIConnectionError -> must come first
            raise LLMUnavailableError("The request to Groq timed out. Please try again.") from exc
        except groq.APIConnectionError as exc:
            raise LLMUnavailableError("Could not reach Groq. Check your internet connection.") from exc
        except groq.InternalServerError as exc:
            raise LLMUnavailableError("Groq had a server-side problem. Please try again shortly.") from exc
        except groq.APIStatusError as exc:
            if exc.status_code == 404:
                raise LLMRequestError(
                    f"Model '{self.model_name}' was not found. Check LLM_MODEL in your .env."
                ) from exc
            raise LLMRequestError(f"Groq returned HTTP {exc.status_code}.") from exc

        latency = time.perf_counter() - started
        choice = resp.choices[0]
        text = (choice.message.content or "").strip()
        usage = getattr(resp, "usage", None)
        prompt_tokens = getattr(usage, "prompt_tokens", None)
        completion_tokens = getattr(usage, "completion_tokens", None)

        logger.info(
            "LLM call ok: model=%s latency=%.2fs prompt_tokens=%s completion_tokens=%s strict=%s",
            self.model_name, latency, prompt_tokens, completion_tokens, self._strict,
        )

        if choice.finish_reason == "length":
            raise LLMTruncatedError(
                "The model ran out of output tokens. Increase LLM_MAX_OUTPUT_TOKENS "
                "or lower LLM_REASONING_EFFORT."
            )
        if not text:
            raise LLMOutputError("The model returned an empty response.")

        return LLMResult(text, self.model_name, latency, prompt_tokens, completion_tokens)

    # ----------------------------------------------------------------- private
    def _create(self, messages, schema, schema_name, strict: bool):
        s = self._settings
        kwargs: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "temperature": s.llm_temperature,
            "max_completion_tokens": s.llm_max_output_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": strict,
                    "schema": to_strict_json_schema(schema),
                },
            },
        }
        if self.model_name.startswith("openai/gpt-oss") and s.llm_reasoning_effort in (
            "low", "medium", "high",
        ):
            kwargs["reasoning_effort"] = s.llm_reasoning_effort
        return self._sdk.chat.completions.create(**kwargs)


def _is_schema_rejection(exc: groq.BadRequestError) -> bool:
    msg = str(exc).lower()
    if any(h in msg for h in _GENERATION_FAILED_HINTS):
        return False
    return any(h in msg for h in _SCHEMA_REJECTED_HINTS)


def _is_strict_output_rejection(exc: groq.BadRequestError) -> bool:
    """Strict decoding should prevent these, but provider validation can still reject output.

    Retry once in best-effort mode; the pipeline still validates the returned JSON locally.
    This deliberately does not change how best-effort validation failures are classified.
    """
    return "json_validate_failed" in str(exc).lower()


def _map_bad_request(exc: groq.BadRequestError) -> Exception:
    msg = str(exc).lower()

    if any(h in msg for h in _GENERATION_FAILED_HINTS):
        return LLMOutputError(
            "The model produced output that did not fit the required format."
        )

    return LLMRequestError(
        "Groq rejected the request (HTTP 400). Check LLM_MODEL and settings."
    )
