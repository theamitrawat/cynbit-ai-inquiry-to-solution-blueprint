"""The analysis pipeline:  raw text -> clean -> prompt -> LLM -> parse/validate -> (repair) -> report.

Failure policy:
  - Bad input            -> InvalidInquiryError, BEFORE any API call.
  - Provider down/limits -> LLMUnavailableError etc. propagate immediately (retrying now won't help).
  - Unusable model output-> up to `max_attempts` tries. After a validation failure we show the
                            model its own output + the exact errors and ask for a corrected version.
  - Still failing        -> LLMOutputError with a clear message. We never return unvalidated data.
"""
import json
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
    "Return the corrected JSON only. Do not add fields. Follow the rules in the system message. "
    "For any stated requirement, copy evidence as an exact contiguous quote from the original "
    "inquiry, preserving spelling and punctuation; do not paraphrase or reconstruct it. If the "
    "inquiry does not directly support a requirement, do not label it stated. Keep a reasonable "
    "inference only as origin=inferred with evidence=null."
)


def _summarise_errors(exc: ValidationError, limit: int = 8) -> str:
    errors = exc.errors()
    lines = []
    for err in errors[:limit]:
        loc = ".".join(str(p) for p in err["loc"]) or "(root)"
        lines.append(f"- {loc}: {err['msg']}")
    locations = {tuple(err["loc"]) for err in errors}
    if any(loc[:2] == ("extraction", "blueprint") for loc in locations):
        lines.append(
            "- Correction: move `blueprint` to the root object as a sibling of `extraction`; "
            "remove it from inside `extraction`."
        )
    if any(
        "Evidence for a 'stated' requirement" in err["msg"]
        or "stated requirement's text must match its evidence" in err["msg"]
        for err in errors
    ):
        lines.append(
            "- Correction: replace each rejected evidence value with an exact, contiguous "
            "substring copied from the original inquiry. Do not paraphrase. If no exact quote "
            "supports an item, remove it or mark it inferred only when it is a genuine inference."
        )
    return "\n".join(lines)


def _normalise_safe_output(raw: str, inquiry: str) -> str:
    """Apply only lossless structural/grounding corrections before Pydantic validation.

    A stated requirement is reduced to its verbatim evidence, and a misplaced blueprint is
    promoted only when the root object does not already contain one. Ambiguous cases are left
    untouched so normal validation rejects them.
    """
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw
    if not isinstance(data, dict):
        return raw

    changed = False
    extraction = data.get("extraction")
    if isinstance(extraction, dict) and "blueprint" in extraction and "blueprint" not in data:
        data["blueprint"] = extraction.pop("blueprint")
        changed = True

    if isinstance(extraction, dict):
        for field in ("functional_requirements", "non_functional_requirements"):
            items = extraction.get(field)
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict) or item.get("origin") != "stated":
                    continue
                evidence = item.get("evidence")
                if isinstance(evidence, str) and evidence and evidence in inquiry:
                    if item.get("text") != evidence:
                        item["text"] = evidence
                        changed = True

    return json.dumps(data, ensure_ascii=False) if changed else raw


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
                _normalise_safe_output(result.text, text), context={"inquiry_text": text}
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
