"""The analysis pipeline:  raw text -> clean -> prompt -> LLM -> parse/validate -> (repair) -> report.

Failure policy:
  - Bad input            -> InvalidInquiryError, BEFORE any API call.
  - Provider down/limits -> LLMUnavailableError etc. propagate immediately (retrying now won't help).
  - Unusable model output-> up to `max_attempts` tries. After a validation failure we show the
                            model its own output + the exact errors and ask for a corrected version.
  - Still failing        -> LLMOutputError with a clear message. We never return unvalidated data.
"""
import logging
import time

from pydantic import ValidationError

from app.config import Settings, get_settings
from app.errors import LLMOutputError, LLMTruncatedError
from app.llm_client import LLMClient
from app.prompts import PROMPT_VERSION, build_messages
from app.schemas import AnalysisReport, LLMAnalysis
from app.validation import clean_inquiry

logger = logging.getLogger(__name__)

SCHEMA_NAME = "inquiry_analysis"

_REPAIR_TEMPLATE = (
    "Your previous JSON failed validation with these errors:\n{errors}\n"
    "Return the corrected JSON only. Do not add fields. Follow the rules in the system message."
)


def _summarise_errors(exc: ValidationError, limit: int = 8) -> str:
    lines = []
    for err in exc.errors()[:limit]:
        loc = ".".join(str(p) for p in err["loc"]) or "(root)"
        lines.append(f"- {loc}: {err['msg']}")
    return "\n".join(lines)


def analyze_inquiry(
    raw_text: object,
    client: LLMClient,
    settings: Settings | None = None,
    max_attempts: int = 2,
) -> AnalysisReport:
    settings = settings or get_settings()
    text = clean_inquiry(raw_text, settings)  # raises InvalidInquiryError

    messages = build_messages(text)
    schema = LLMAnalysis.model_json_schema()

    started = time.perf_counter()
    prompt_tokens = 0
    completion_tokens = 0
    saw_usage = False
    last_problem = "unknown"

    for attempt in range(1, max_attempts + 1):
        try:
            result = client.generate_json(messages, schema, SCHEMA_NAME)
        except LLMTruncatedError:
            raise  # same settings -> same result; surface immediately
        except LLMOutputError as exc:
            last_problem = str(exc)
            logger.warning("Attempt %d/%d: unusable model output (%s)", attempt, max_attempts, last_problem)
            continue  # provider-level output failure: retry the same request

        if result.prompt_tokens is not None:
            saw_usage = True
            prompt_tokens += result.prompt_tokens
            completion_tokens += result.completion_tokens or 0

        try:
            analysis = LLMAnalysis.model_validate_json(
                result.text, context={"inquiry_text": text}
            )
        except ValidationError as exc:
            last_problem = _summarise_errors(exc)
            logger.warning("Attempt %d/%d: output failed validation (%d errors)",
                           attempt, max_attempts, exc.error_count())
            messages = messages + [
                {"role": "assistant", "content": result.text},
                {"role": "user", "content": _REPAIR_TEMPLATE.format(errors=last_problem)},
            ]
            continue

        return AnalysisReport(
            inquiry_text=text,
            analysis=analysis,
            model_name=client.model_name,
            prompt_version=PROMPT_VERSION,
            attempts=attempt,
            latency_seconds=round(time.perf_counter() - started, 3),
            prompt_tokens=prompt_tokens if saw_usage else None,
            completion_tokens=completion_tokens if saw_usage else None,
        )

    raise LLMOutputError(
        f"The model did not return a valid analysis after {max_attempts} attempts. "
        f"Last problem: {last_problem}"
    )
