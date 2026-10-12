"""Phase 4 — Python live locator validation reads the project's execution.test_id_attribute, the same
attribute the TS runtime's getByTestId uses (it used to check Python's default data-testid while the
runtime used data-test)."""

from types import SimpleNamespace

from tools.test_creation.script_generator.locator_resolve import entry_resolves, resolve_entry, by_test_id


class _Loc:
    def __init__(self, how, value, count):
        self.how, self.value, self._count = how, value, count

    def count(self):
        return self._count


class _Base:
    """Counts depend on the selector: `[data-test="x"]` exists once, data-testid "x" not at all."""

    def get_by_test_id(self, v):
        return _Loc("testid", v, 0)

    def locator(self, css):
        return _Loc("css", css, 1 if css == '[data-test="login-button"]' else 0)


def test_default_and_data_testid_use_get_by_test_id():
    assert by_test_id(_Base(), "x").how == "testid"
    assert by_test_id(_Base(), "x", "data-testid").how == "testid"


def test_other_attribute_uses_an_exact_attribute_selector_with_escaping():
    loc = by_test_id(_Base(), 'a"b\\c', "data-qa")
    assert loc.how == "css" and loc.value == '[data-qa="a\\"b\\\\c"]'


def test_entry_resolves_against_the_configured_attribute():
    entry = {"type": "testid", "locator": "login-button"}
    assert entry_resolves(_Base(), entry) is False                 # data-testid: 0 matches
    assert entry_resolves(_Base(), entry, "data-test") is True     # data-test: exactly 1
    assert resolve_entry(_Base(), entry, "data-test").value == '[data-test="login-button"]'


def test_count_rule_unchanged_for_non_testid_entries():
    class B(_Base):
        def locator(self, css):
            return _Loc("css", css, 2)
    assert entry_resolves(B(), {"type": "css", "locator": "#dup"}, "data-test") is False   # 2 matches still rejected


def test_script_generation_and_healing_pass_the_attribute():
    from agents.test_creation.script_generation.agent import ScriptGenerationAgent
    from agents.test_execution.healing.tools import _build_python_locator, _ctx_test_id_attribute, _locator_entry_resolves

    entry = {"type": "testid", "locator": "login-button"}
    assert ScriptGenerationAgent._locator_entry_resolves(_Base(), entry, "data-test") is True
    assert _locator_entry_resolves(_Base(), entry, "data-test") is True
    assert _build_python_locator(_Base(), "getByTestId", "login-button", None, "data-test").how == "css"
    assert _ctx_test_id_attribute(SimpleNamespace()) is None        # test doubles without the method
    assert _ctx_test_id_attribute(SimpleNamespace(test_id_attribute=lambda: "data-test")) == "data-test"
