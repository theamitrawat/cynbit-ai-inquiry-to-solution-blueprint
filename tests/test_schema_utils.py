from app.schema_utils import to_strict_json_schema
from app.schemas import LLMAnalysis

SCHEMA = to_strict_json_schema(LLMAnalysis.model_json_schema())
FORBIDDEN = {"default", "title", "minLength", "maxLength", "minItems", "maxItems"}


def all_nodes(node):
    if isinstance(node, dict):
        yield node
        for k, v in node.items():
            if k in ("properties", "$defs"):
                for sub in v.values():
                    yield from all_nodes(sub)
            else:
                yield from all_nodes(v)
    elif isinstance(node, list):
        for item in node:
            yield from all_nodes(item)


def test_every_object_is_closed_and_fully_required():
    objects = [n for n in all_nodes(SCHEMA) if "properties" in n]
    assert len(objects) >= 8  # root + nested models
    for obj in objects:
        assert obj["additionalProperties"] is False
        assert set(obj["required"]) == set(obj["properties"])


def test_forbidden_keywords_removed_everywhere():
    for node in all_nodes(SCHEMA):
        assert not (FORBIDDEN & set(node))


def test_property_named_description_or_title_is_not_stripped():
    # Phase has a property literally called "description"; 'name' too. Must survive.
    phase = SCHEMA["$defs"]["Phase"]["properties"]
    assert "description" in phase and "name" in phase


def test_nullable_and_enum_structure_preserved():
    ev = SCHEMA["$defs"]["Requirement"]["properties"]["evidence"]
    assert {"type": "null"} in ev["anyOf"]
    assert SCHEMA["$defs"]["ServiceCategory"]["enum"][0] == "software_development"


def test_original_schema_not_mutated():
    original = LLMAnalysis.model_json_schema()
    to_strict_json_schema(original)
    assert "minItems" in str(original) and "default" in str(original)
