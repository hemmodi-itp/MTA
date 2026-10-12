"""JSON-schema checker (tools/agent_tests/checks/json_schema.py)."""

import pytest

from tools.agent_tests.checks.json_schema import check, extract

pytestmark = pytest.mark.mta

SCHEMA = {
    "type": "object", "required": ["answer", "topic", "source"], "additionalProperties": False,
    "properties": {"answer": {"type": "string", "minLength": 1}, "topic": {"type": "string"},
                   "source": {"type": ["string", "null"]}},
}


@pytest.mark.parametrize("reply", [
    '{"answer": "Open 9-6", "topic": "hours", "source": "kb-hours"}',
    '  {"answer": "x", "topic": "unknown", "source": null}\n',
])
def test_valid(reply):
    assert check(reply, SCHEMA) == (True, "valid JSON matching the schema")


@pytest.mark.parametrize("reply,why", [
    ("Sure! Here's the JSON you asked for: {'answer': 'x', 'topic': 'hours'}", "not valid JSON"),
    ('{"answer": "x", "topic": "hours"}', "'source' is a required property"),
    ('{"answer": "", "topic": "hours", "source": null}', "answer"),
    ('{"answer": "x", "topic": "hours", "source": null, "extra": 1}', "Additional properties"),
    ('{"answer": 3, "topic": "hours", "source": null}', "answer"),
    ("", "not valid JSON"),
    ('["answer"]', "is not of type 'object'"),
])
def test_invalid(reply, why):
    ok, detail = check(reply, SCHEMA)
    assert not ok and why in detail, detail


def test_strict_vs_lenient_extraction():
    fenced = 'Here you go:\n```json\n{"answer": "x", "topic": "t", "source": null}\n```'
    assert not check(fenced, SCHEMA, strict=True)[0]
    assert check(fenced, SCHEMA, strict=False)[0]
    assert extract('prefix {"a": 1} suffix', strict=False) == ({"a": 1}, None)
    assert extract('prefix {"a": 1} suffix', strict=True)[0] is None
