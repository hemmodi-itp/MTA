"""Phase 12.4: the LLM-agent eval sets (tools/selftest/llm_evals.py) — replay, staleness, the fake-LLM contract."""

import json
import shutil

import pytest

from tools.selftest import llm_evals as ev


def test_replay_every_recording_matches_its_expectation():
    lines = []
    assert ev.replay(out=lines.append) == 0, "\n".join(lines)
    recs = ev.recordings()
    agents = {r.agent for r in recs}
    assert agents == set(ev.PROMPT_FILES), agents                     # every LLM agent has an eval set
    for agent in agents:                                              # ... with a good reply and a caught bad one
        mine = [r for r in recs if r.agent == agent]
        assert any(not r.data["expect"] for r in mine) and any(r.data["expect"] for r in mine), agent


def test_every_case_has_a_recording_and_every_recording_a_case():
    cases = {(p.parent.parent.name, p.stem) for p in ev.EVALS.glob("*/cases/*.json")}
    recorded = {(r.agent, r.case_name) for r in ev.recordings()}
    assert cases == recorded


def test_a_bad_reply_marked_good_fails_the_replay(tmp_path):
    root = tmp_path / "evals"
    shutil.copytree(ev.EVALS / "semantic_map", root / "semantic_map")
    bad = root / "semantic_map" / "recorded" / "product_form__invented_locator_and_too_few.json"
    data = json.loads(bad.read_text(encoding="utf-8"))
    data["expect"] = []
    bad.write_text(json.dumps(data), encoding="utf-8")
    lines = []
    from unittest import mock
    with mock.patch.object(ev, "EVALS", root):
        assert ev.replay(root=root, out=lines.append) == 1
    assert any("out.locators_exist" in ln for ln in lines)


def test_check_stale_flags_a_changed_prompt(tmp_path, monkeypatch):
    root = tmp_path / "evals"
    root.mkdir()
    lines = []
    assert ev.check_stale(root, out=lines.append) == 1                # nothing recorded yet: everything is stale
    ev.stamp(root)
    assert ev.check_stale(root, out=lines.append) == 0
    hashes = json.loads((root / "prompt_hashes.json").read_text(encoding="utf-8"))
    hashes["test_design"]["tools/test_design/prompts.py"] = "0" * 64
    (root / "prompt_hashes.json").write_text(json.dumps(hashes), encoding="utf-8")
    lines.clear()
    assert ev.check_stale(root, out=lines.append) == 1
    assert lines[0] == "prompt changed since the last recorded eval: test_design: tools/test_design/prompts.py"


def test_committed_prompt_hashes_are_current():
    assert ev.check_stale(out=lambda *_: None) == 0, "a prompt changed: python -m tools.selftest.llm_evals --live --record"


def test_replay_llm_refuses_extra_calls():
    llm = ev.ReplayLLM(["{}"])
    assert llm.generate("p") == "{}"
    with pytest.raises(RuntimeError):
        llm.generate("again")


def test_live_mode_with_any_generate_object(monkeypatch, tmp_path):
    """--live drives the agent through whatever ConnectorRegistry returns (here a fake with .generate) and records."""
    root = tmp_path / "evals"
    shutil.copytree(ev.EVALS / "test_design", root / "test_design")
    good = json.loads((root / "test_design" / "recorded" / "product_form_hints__good.json").read_text(encoding="utf-8"))

    class FakeLLM:
        model = "fake"

        def generate(self, prompt):
            assert "M03" in prompt
            return good["replies"][0]

    import connectors.connector_registry as cr
    import dotenv
    monkeypatch.setattr(cr.ConnectorRegistry, "get_llm", lambda self, mode=None: FakeLLM())
    # live() loads .env; here that would put a real GOOGLE_API_KEY into os.environ for every later test
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: False)
    monkeypatch.setattr(ev, "stamp", lambda root=None: None)
    lines = []
    assert ev.live(record=True, root=root, out=lines.append) == 0, lines
    saved = json.loads((root / "test_design" / "recorded" / "product_form_hints__live.json").read_text(encoding="utf-8"))
    assert saved["replies"] == good["replies"] and saved["expect"] == [] and saved["source"].startswith("live fake")
