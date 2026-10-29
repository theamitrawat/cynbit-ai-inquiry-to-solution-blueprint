"""One real call to Groq. Run this FIRST to confirm your key, model and schema work.

    python -m scripts.smoke_test
    python -m scripts.smoke_test "We need a mobile app for ..."

The default inquiry below is SYNTHETIC (made up for testing).
"""
import sys

from app.config import get_settings
from app.errors import LLMError
from app.llm_client import GroqClient
from app.logging_config import setup_logging
from app.pipeline import analyze_inquiry
from app.validation import InvalidInquiryError

SYNTHETIC_INQUIRY = (
    "We run three dental clinics in Jaipur. We want a web app where patients can book "
    "appointments online and get SMS reminders, and our receptionists can see a daily schedule. "
    "We have about 2,000 patients. We would like to launch before March."
)


def main() -> int:
    settings = get_settings()
    setup_logging(settings.log_level)
    text = sys.argv[1] if len(sys.argv) > 1 else SYNTHETIC_INQUIRY

    try:
        client = GroqClient(settings)
        report = analyze_inquiry(text, client, settings)
    except InvalidInquiryError as exc:
        print(f"Invalid input: {exc}")
        return 2
    except LLMError as exc:
        print(f"LLM error ({type(exc).__name__}): {exc}")
        return 1

    a = report.analysis
    print(f"\nmodel={report.model_name}  attempts={report.attempts}  latency={report.latency_seconds}s  "
          f"tokens(in/out)={report.prompt_tokens}/{report.completion_tokens}")
    print(f"relevant={a.is_relevant}  note={a.relevance_note}")
    if a.extraction:
        e = a.extraction
        print(f"categories={[c.value for c in e.service_categories]}  overlap={e.overlapping_offerings}")
        print(f"functional reqs={len(e.functional_requirements)}  missing={len(e.missing_information)}  "
              f"questions={len(e.discovery_questions)}  conflicts={len(e.conflicts)}")
    print("\n--- full JSON ---")
    print(report.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
