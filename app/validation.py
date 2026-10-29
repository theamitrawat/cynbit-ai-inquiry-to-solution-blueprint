"""Input validation. Runs BEFORE any LLM call so bad input costs nothing."""
import re

from app.config import Settings, get_settings


class InvalidInquiryError(ValueError):
    """Raised with a user-friendly message when the inquiry cannot be processed."""


_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_MIN_LETTERS = 10


def clean_inquiry(raw: object, settings: Settings | None = None) -> str:
    """Return a cleaned inquiry string or raise InvalidInquiryError."""
    settings = settings or get_settings()

    if not isinstance(raw, str):
        raise InvalidInquiryError("Inquiry must be text.")

    text = _CONTROL_CHARS.sub("", raw)
    text = re.sub(r"[ \t]+", " ", text)             # collapse repeated spaces/tabs
    text = re.sub(r"\n{3,}", "\n\n", text).strip()  # collapse blank-line runs

    if not text:
        raise InvalidInquiryError("Inquiry is empty. Please describe what you want to build.")
    if len(text) < settings.min_inquiry_chars:
        raise InvalidInquiryError(
            f"Inquiry is too short ({len(text)} characters). "
            f"Please write at least {settings.min_inquiry_chars} characters."
        )
    if len(text) > settings.max_inquiry_chars:
        raise InvalidInquiryError(
            f"Inquiry is too long ({len(text)} characters). "
            f"Maximum is {settings.max_inquiry_chars}."
        )
    if sum(ch.isalpha() for ch in text) < _MIN_LETTERS:
        raise InvalidInquiryError("Inquiry does not look like a text description.")
    return text
