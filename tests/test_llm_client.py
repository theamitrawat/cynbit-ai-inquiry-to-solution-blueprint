import groq
import httpx
import pytest

from app.config import Settings
from app.errors import (
    LLMAuthError, LLMConfigError, LLMOutputError, LLMRequestError,
    LLMTruncatedError, LLMUnavailableError,
)
from app.llm_client import GroqClient
from tests.fakes import StubSDK, sdk_response

REQ = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
SCHEMA = {"type": "object", "properties": {"a": {"type": "string", "minLength": 1}}}
MSGS = [{"role": "user", "content": "hi"}]


def status_error(cls, code, message="boom"):
    return cls(message, response=httpx.Response(code, request=REQ), body=None)


def make(script, **overrides):
    s = Settings(llm_api_key="test-key", **overrides)
    sdk = StubSDK(script)
    return GroqClient(s, sdk_client=sdk), sdk


def test_success_returns_text_latency_and_usage():
    client, sdk = make([sdk_response('{"a": "x"}')])
    r = client.generate_json(MSGS, SCHEMA, "demo")
    assert r.text == '{"a": "x"}' and r.prompt_tokens == 120 and r.completion_tokens == 60
    assert r.latency_seconds >= 0


def test_request_is_built_correctly_for_gpt_oss():
    client, sdk = make([sdk_response("{}")], llm_model="openai/gpt-oss-20b", llm_reasoning_effort="low")
    client.generate_json(MSGS, SCHEMA, "demo")
    req = sdk.requests[0]
    js = req["response_format"]["json_schema"]
    assert req["response_format"]["type"] == "json_schema"
    assert js["strict"] is True and js["name"] == "demo"
    assert js["schema"]["additionalProperties"] is False and "minLength" not in str(js["schema"])
    assert req["reasoning_effort"] == "low"
    assert req["max_completion_tokens"] == 4000


def test_reasoning_effort_not_sent_to_other_models():
    client, sdk = make([sdk_response("{}")], llm_model="some/other-model")
    client.generate_json(MSGS, SCHEMA, "demo")
    assert "reasoning_effort" not in sdk.requests[0]


def test_missing_api_key_is_a_config_error():
    with pytest.raises(LLMConfigError, match="LLM_API_KEY"):
        GroqClient(Settings(llm_api_key=None))


def test_api_key_never_appears_in_settings_repr():
    assert "super-secret" not in repr(Settings(llm_api_key="super-secret"))


@pytest.mark.parametrize("cls,code,expected", [
    (groq.AuthenticationError, 401, LLMAuthError),
    (groq.PermissionDeniedError, 403, LLMAuthError),
    (groq.RateLimitError, 429, LLMUnavailableError),
    (groq.InternalServerError, 500, LLMUnavailableError),
    (groq.NotFoundError, 404, LLMRequestError),
])
def test_http_errors_are_mapped(cls, code, expected):
    client, _ = make([status_error(cls, code)])
    with pytest.raises(expected):
        client.generate_json(MSGS, SCHEMA, "demo")


def test_connection_and_timeout_errors_are_unavailable():
    for exc in (groq.APIConnectionError(request=REQ), groq.APITimeoutError(request=REQ)):
        client, _ = make([exc])
        with pytest.raises(LLMUnavailableError):
            client.generate_json(MSGS, SCHEMA, "demo")


def test_schema_mismatch_400_is_an_output_error():
    err = status_error(groq.BadRequestError, 400, "Generated JSON does not match the expected schema.")
    client, _ = make([err])
    with pytest.raises(LLMOutputError):
        client.generate_json(MSGS, SCHEMA, "demo")


def test_strict_schema_rejection_falls_back_to_best_effort_once(caplog):
    err = status_error(groq.BadRequestError, 400, "This model does not support response format `json_schema`.")
    client, sdk = make([err, sdk_response('{"a": "x"}')])
    r = client.generate_json(MSGS, SCHEMA, "demo")
    assert r.text == '{"a": "x"}'
    assert "schema or response-format compatibility" in caplog.text
    assert [q["response_format"]["json_schema"]["strict"] for q in sdk.requests] == [True, False]
    # and it remembers: next call goes straight to best-effort
    sdk.script.append(sdk_response("{}"))
    client.generate_json(MSGS, SCHEMA, "demo")
    assert sdk.requests[-1]["response_format"]["json_schema"]["strict"] is False


def test_strict_json_validate_failure_falls_back_once(caplog):
    # The provider reports a missing required property even though the excerpt contains it;
    # duplicate constraints keys also make the excerpt unreliable as proof of schema validity.
    failed_generation = (
        '{"blueprint": null, "constraints": {"budget": null, "budget": null}}'
    )
    err = status_error(
        groq.BadRequestError,
        400,
        "code=json_validate_failed Generated JSON does not match the expected schema. "
        f"jsonschema: '' does not validate with /required: missing properties: 'blueprint'. "
        f"failed_generation={failed_generation}",
    )
    client, sdk = make([err, sdk_response('{"a": "x"}')])

    result = client.generate_json(MSGS, SCHEMA, "demo")

    assert result.text == '{"a": "x"}'
    assert "provider output validation" in caplog.text
    assert [r["response_format"]["json_schema"]["strict"] for r in sdk.requests] == [True, False]


def test_best_effort_json_validate_failure_is_an_output_error_without_further_fallback():
    err = status_error(groq.BadRequestError, 400, "code=json_validate_failed")
    client, sdk = make([err], llm_strict_schema=False)

    with pytest.raises(LLMOutputError):
        client.generate_json(MSGS, SCHEMA, "demo")

    assert len(sdk.requests) == 1


def test_unrelated_400_is_a_request_error_not_a_fallback():
    err = status_error(groq.BadRequestError, 400, "invalid value for temperature")
    client, sdk = make([err])
    with pytest.raises(LLMRequestError):
        client.generate_json(MSGS, SCHEMA, "demo")
    assert len(sdk.requests) == 1


def test_truncated_output_is_detected():
    client, _ = make([sdk_response('{"a": ', finish_reason="length")])
    with pytest.raises(LLMTruncatedError):
        client.generate_json(MSGS, SCHEMA, "demo")


def test_empty_output_is_an_output_error():
    client, _ = make([sdk_response("   ")])
    with pytest.raises(LLMOutputError):
        client.generate_json(MSGS, SCHEMA, "demo")
