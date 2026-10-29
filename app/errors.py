"""LLM-related exceptions. Every message is written to be safe to show to an end user
(no API keys, no raw inquiry text, no stack traces)."""


class LLMError(Exception):
    """Base class for all LLM failures."""


class LLMConfigError(LLMError):
    """Missing/invalid configuration (e.g. no API key)."""


class LLMAuthError(LLMError):
    """Provider rejected our credentials."""


class LLMUnavailableError(LLMError):
    """Network problem, timeout, rate limit or provider-side 5xx. Usually worth retrying later."""


class LLMRequestError(LLMError):
    """Provider rejected the request itself (bad parameter, unknown model, ...). A bug or config issue."""


class LLMOutputError(LLMError):
    """The model answered, but the output was unusable (invalid JSON / failed validation)."""


class LLMTruncatedError(LLMOutputError):
    """Output hit the token limit. Retrying with the same settings will not help."""
