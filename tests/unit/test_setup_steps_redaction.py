"""Phase 4.3 — credentials never reach the logs: a setup step's literal `value` is redacted."""

import logging

from tools.playwright_scanner import execute_setup_steps, redact_setup_arg


class _Locator:
    def __init__(self, page, sel):
        self.page, self.sel = page, sel

    def fill(self, value):
        self.page.filled[self.sel] = value

    def click(self):
        pass


class _Page:
    url = "http://shop.local/products"

    def __init__(self):
        self.filled = {}

    def goto(self, url, **_):
        pass

    def locator(self, sel):
        return _Locator(self, sel)

    def wait_for_load_state(self, *a, **k):
        pass

    def wait_for_timeout(self, ms):
        pass

    def click(self, sel, **_):
        pass


def test_redact_setup_arg():
    assert redact_setup_arg({"selector": "#password", "value": "s3cret"}) == {"selector": "#password", "value": "***"}
    assert redact_setup_arg({"selector": "#user", "value_env": "APP_USER"}) == {"selector": "#user", "value_env": "APP_USER"}
    assert redact_setup_arg("https://shop.local/login") == "https://shop.local/login"


def test_setup_steps_fill_the_real_value_but_never_log_it(caplog):
    page = _Page()
    steps = [{"goto": "http://shop.local/login"},
             {"fill": {"selector": "#username", "value": "alice"}},
             {"fill": {"selector": "#password", "value": "alice-pass-1"}},
             {"click": "#login-button"}]
    logger = logging.getLogger("test.setup.redaction")
    with caplog.at_level(logging.DEBUG, logger="test.setup.redaction"):
        execute_setup_steps(page, steps, logger)
    assert page.filled == {"#username": "alice", "#password": "alice-pass-1"}   # behaviour unchanged
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "alice-pass-1" not in text
    assert "'#password'" in text and "***" in text
