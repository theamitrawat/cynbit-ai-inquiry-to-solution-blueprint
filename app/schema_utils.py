"""Convert a Pydantic JSON schema into the subset Groq's Structured Outputs accepts.

Groq strict mode (constrained decoding) requires:
  - every property listed in `required`  (optional fields must be nullable instead)
  - `additionalProperties: false` on every object
and it supports only a subset of JSON Schema keywords.

We strip keywords the provider may reject (length/size limits, defaults, titles).
That is SAFE because the full Pydantic model re-validates the response afterwards,
so limits such as max_length are still enforced - just by us, not by the provider.
"""
from typing import Any

_STRIP_KEYWORDS = {
    "default", "title", "pattern", "format",
    "minLength", "maxLength", "minItems", "maxItems",
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
}
_SCHEMA_MAPS = {"properties", "$defs"}  # dicts whose KEYS are names, not schema keywords


def to_strict_json_schema(schema: dict[str, Any]) -> dict[str, Any]:
    return _convert(schema)


def _convert(node: Any) -> Any:
    if isinstance(node, list):
        return [_convert(item) for item in node]
    if not isinstance(node, dict):
        return node

    out: dict[str, Any] = {}
    for key, value in node.items():
        if key in _STRIP_KEYWORDS:
            continue
        if key in _SCHEMA_MAPS:
            out[key] = {name: _convert(sub) for name, sub in value.items()}
        else:
            out[key] = _convert(value)

    if "properties" in out:
        out["required"] = list(out["properties"].keys())
        out["additionalProperties"] = False
    return out
