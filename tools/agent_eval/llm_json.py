"""
llm_json.py — ask an LLMConnector for JSON and get a parsed object back.

Uses the connector's native JSON mode when it has one (GeminiConnector.generate_json,
optionally schema-enforced), otherwise plain generate(). On a PARSE failure it retries once with
an explicit "JSON only" reminder before giving up. Connector errors — timeouts, truncation at the
output-token limit (LLMTruncatedError), safety blocks (LLMBlockedError), API errors — are not
retried here: the connector already retried what is retryable, and re-sending the identical
prompt can't fix the rest.

FencedTemplate — a string.Template for prompts that carry untrusted text: the placeholders it is
told about are wrapped in <untrusted_content> fences (tools/agent_eval/untrusted.py) at
substitution time, so a caller passing raw app output / BRD text can't break the prompt.
"""

import inspect
import re
from string import Template
from typing import Any, Dict, List, Mapping, Optional

from connectors.llm.base import LLMConnector
from tools.agent_eval.untrusted import fence_untrusted
from tools.shared.llm_response_validator import validate_llm_json

_RETRY_SUFFIX = (
    "\n\nIMPORTANT: your previous answer was not valid JSON. "
    "Respond with ONE valid JSON value only — no prose, no markdown fences."
)


def generate_json(
    llm: LLMConnector,
    prompt: str,
    required_keys: Optional[List[str]] = None,
    expected_type: type = dict,
    retries: int = 1,
    schema: Optional[Dict[str, Any]] = None,
    temperature: Optional[float] = None,
) -> Any:
    """schema / temperature are forwarded to connectors whose generate_json accepts them (Gemini).

    retries applies to parse/shape failures only and is capped at 1.
    """
    native = getattr(llm, "generate_json", None)
    params = inspect.signature(native).parameters if native else {}
    extra = {k: v for k, v in (("schema", schema), ("temperature", temperature)) if v is not None and k in params}
    if native:
        call = lambda p: native(p, **extra)  # noqa: E731
    else:
        call = llm.generate
    attempts = 1 + max(0, min(int(retries), 1))
    last_exc: Optional[Exception] = None
    for attempt in range(attempts):
        raw = call(prompt if attempt == 0 else prompt + _RETRY_SUFFIX)  # connector errors propagate unchanged
        try:
            return validate_llm_json(raw or "", required_keys=required_keys, expected_type=expected_type)
        except ValueError as exc:
            last_exc = exc
    raise ValueError(f"LLM did not return valid JSON after {attempts} attempt(s): {last_exc}")


# ── prompts with untrusted placeholders ──────────────────────────────────────

_FENCE_TAG = re.compile(r"<\s*/?\s*untrusted_content\b[^>]*>", re.I)


def _already_fenced(value: str) -> bool:
    """A single, intact fence produced by fence_untrusted (exactly one opening and one closing tag)."""
    v = value.strip()
    return (v.startswith('<untrusted_content source="') and v.endswith("</untrusted_content>")
            and len(_FENCE_TAG.findall(v)) == 2)


class FencedTemplate(Template):
    """string.Template that fences selected placeholders as untrusted and fills optional ones.

        T = FencedTemplate("... $tests ...", fenced={"tests": "app_output"}, defaults={"extra": "(none)"})
        T.substitute(tests=raw_text)      # raw_text arrives inside <untrusted_content source="app_output">

    Values that are already a single intact fence (the caller fenced them) are kept as they are.
    """

    def __init__(self, template: str, fenced: Optional[Mapping[str, str]] = None,
                 defaults: Optional[Mapping[str, str]] = None) -> None:
        super().__init__(template)
        self.fenced = dict(fenced or {})
        self.defaults = dict(defaults or {})

    def _values(self, mapping: Optional[Mapping[str, Any]], kws: Dict[str, Any]) -> Dict[str, Any]:
        values: Dict[str, Any] = dict(self.defaults)
        values.update(mapping or {})
        values.update(kws)
        for name, source in self.fenced.items():
            if name in values:
                text = "" if values[name] is None else str(values[name])
                values[name] = text.strip() if _already_fenced(text) else fence_untrusted(source, text)
        return values

    def substitute(self, mapping=None, /, **kws):  # type: ignore[override]
        return super().substitute(self._values(mapping, kws))

    def safe_substitute(self, mapping=None, /, **kws):  # type: ignore[override]
        return super().safe_substitute(self._values(mapping, kws))
