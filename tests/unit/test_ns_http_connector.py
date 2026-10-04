import io
import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from connectors.ns.base import NSCallError, NSHTTPConnector


def _make_connector(agents: dict, auth_token: str = "") -> NSHTTPConnector:
    return NSHTTPConnector(
        base_url="http://localhost:8000",
        registry=agents,
        auth_token=auth_token,
    )


def _mock_response(body: dict, status: int = 200):
    """Return a mock that behaves like urllib.request.urlopen context manager."""
    raw = json.dumps(body).encode("utf-8")
    resp = MagicMock()
    resp.read.return_value = raw
    resp.status = status
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


class TestNSHTTPConnectorBasics(unittest.TestCase):
    def test_agents_returns_registry_keys(self):
        c = _make_connector({"agent_a": {"method": "POST", "endpoint": "/a"}, "agent_b": {"method": "GET", "endpoint": "/b"}})
        self.assertEqual(sorted(c.agents()), ["agent_a", "agent_b"])

    def test_unknown_agent_raises_key_error(self):
        c = _make_connector({})
        with self.assertRaises(KeyError):
            c.call("does_not_exist", {})


class TestNSHTTPConnectorPOST(unittest.TestCase):
    _REGISTRY = {
        "comprehension_agent": {"method": "POST", "endpoint": "/agents/comprehension_agent", "timeout": 10},
    }

    @patch("urllib.request.urlopen")
    def test_post_sends_json_body(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response({"status": "success", "result": "ok"})
        c = _make_connector(self._REGISTRY)

        result = c.call("comprehension_agent", {"project_name": "demo"})

        self.assertEqual(result["status"], "success")
        req = mock_urlopen.call_args[0][0]
        self.assertEqual(req.full_url, "http://localhost:8000/agents/comprehension_agent")
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(json.loads(req.data), {"project_name": "demo"})
        self.assertEqual(req.get_header("Content-type"), "application/json")

    @patch("urllib.request.urlopen")
    def test_post_returns_parsed_json(self, mock_urlopen):
        payload = {"module": "comprehension_agent", "status": "success", "scenarios": 3}
        mock_urlopen.return_value = _mock_response(payload)
        c = _make_connector(self._REGISTRY)

        result = c.call("comprehension_agent", {})

        self.assertEqual(result["scenarios"], 3)

    @patch("urllib.request.urlopen")
    def test_post_wraps_non_json_response(self, mock_urlopen):
        resp = MagicMock()
        resp.read.return_value = b"OK plain text"
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = resp
        c = _make_connector(self._REGISTRY)

        result = c.call("comprehension_agent", {})

        self.assertEqual(result["status"], "success")
        self.assertIn("OK plain text", result["response"])


class TestNSHTTPConnectorGET(unittest.TestCase):
    _REGISTRY = {
        "agentic_sdlc_dev_service": {"method": "GET", "endpoint": "/agents/", "timeout": 10},
    }

    @patch("urllib.request.urlopen")
    def test_get_appends_payload_as_query_string(self, mock_urlopen):
        """GET /agents/?name=agentic_sdlc_dev_service — payload becomes query string."""
        mock_urlopen.return_value = _mock_response({"status": "success", "tools": []})
        c = _make_connector(self._REGISTRY)

        result = c.call("agentic_sdlc_dev_service", {"name": "agentic_sdlc_dev_service"})

        req = mock_urlopen.call_args[0][0]
        self.assertEqual(req.get_method(), "GET")
        self.assertIn("name=agentic_sdlc_dev_service", req.full_url)
        self.assertTrue(req.full_url.startswith("http://localhost:8000/agents/"))
        self.assertIsNone(req.data)   # GET must have no body

    @patch("urllib.request.urlopen")
    def test_get_with_empty_payload_no_query_string(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response({"status": "success"})
        c = _make_connector(self._REGISTRY)

        c.call("agentic_sdlc_dev_service", {})

        req = mock_urlopen.call_args[0][0]
        self.assertEqual(req.full_url, "http://localhost:8000/agents/")

    @patch("urllib.request.urlopen")
    def test_get_no_content_type_header(self, mock_urlopen):
        """GET requests must NOT send Content-Type header."""
        mock_urlopen.return_value = _mock_response({"status": "success"})
        c = _make_connector(self._REGISTRY)

        c.call("agentic_sdlc_dev_service", {"name": "agentic_sdlc_dev_service"})

        req = mock_urlopen.call_args[0][0]
        self.assertIsNone(req.get_header("Content-type"))

    @patch("urllib.request.urlopen")
    def test_get_multiple_query_params(self, mock_urlopen):
        registry = {"search": {"method": "GET", "endpoint": "/agents/", "timeout": 10}}
        mock_urlopen.return_value = _mock_response({"results": []})
        c = _make_connector(registry)

        c.call("search", {"name": "foo", "category": "bar"})

        req = mock_urlopen.call_args[0][0]
        self.assertIn("name=foo", req.full_url)
        self.assertIn("category=bar", req.full_url)


class TestNSHTTPConnectorAuth(unittest.TestCase):
    _REGISTRY = {
        "secure_agent": {"method": "POST", "endpoint": "/secure", "timeout": 10},
    }

    @patch("urllib.request.urlopen")
    def test_auth_token_adds_bearer_header(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response({"status": "success"})
        c = _make_connector(self._REGISTRY, auth_token="my-secret-token")

        c.call("secure_agent", {})

        req = mock_urlopen.call_args[0][0]
        self.assertEqual(req.get_header("Authorization"), "Bearer my-secret-token")

    @patch("urllib.request.urlopen")
    def test_no_auth_token_no_auth_header(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response({"status": "success"})
        c = _make_connector(self._REGISTRY)

        c.call("secure_agent", {})

        req = mock_urlopen.call_args[0][0]
        self.assertIsNone(req.get_header("Authorization"))


class TestNSHTTPConnectorErrors(unittest.TestCase):
    _REGISTRY = {
        "flaky_agent": {"method": "POST", "endpoint": "/flaky", "timeout": 5},
    }

    @patch("urllib.request.urlopen")
    def test_http_error_raises_ns_call_error(self, mock_urlopen):
        import urllib.error
        err = urllib.error.HTTPError(url="", code=500, msg="Server Error", hdrs=None, fp=io.BytesIO(b"boom"))
        mock_urlopen.side_effect = err
        c = _make_connector(self._REGISTRY)

        with self.assertRaises(NSCallError) as ctx:
            c.call("flaky_agent", {})

        self.assertEqual(ctx.exception.status_code, 500)
        self.assertIn("flaky_agent", str(ctx.exception))

    @patch("urllib.request.urlopen")
    def test_http_404_raises_ns_call_error(self, mock_urlopen):
        import urllib.error
        err = urllib.error.HTTPError(url="", code=404, msg="Not Found", hdrs=None, fp=io.BytesIO(b"not found"))
        mock_urlopen.side_effect = err
        c = _make_connector(self._REGISTRY)

        with self.assertRaises(NSCallError) as ctx:
            c.call("flaky_agent", {})

        self.assertEqual(ctx.exception.status_code, 404)

    @patch("urllib.request.urlopen")
    def test_url_error_raises_ns_call_error(self, mock_urlopen):
        import urllib.error
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
        c = _make_connector(self._REGISTRY)

        with self.assertRaises(NSCallError):
            c.call("flaky_agent", {})

    @patch("urllib.request.urlopen")
    def test_timeout_raises_timeout_error(self, mock_urlopen):
        import urllib.error
        mock_urlopen.side_effect = urllib.error.URLError("timed out")
        c = _make_connector(self._REGISTRY)

        with self.assertRaises(TimeoutError) as ctx:
            c.call("flaky_agent", {})

        self.assertIn("flaky_agent", str(ctx.exception))


class TestNSHTTPConnectorDefaultMethod(unittest.TestCase):
    @patch("urllib.request.urlopen")
    def test_missing_method_defaults_to_post(self, mock_urlopen):
        """Registry entries without 'method' key default to POST."""
        registry = {"no_method_agent": {"endpoint": "/agents/no_method"}}
        mock_urlopen.return_value = _mock_response({"status": "success"})
        c = _make_connector(registry)

        c.call("no_method_agent", {"x": 1})

        req = mock_urlopen.call_args[0][0]
        self.assertEqual(req.get_method(), "POST")


if __name__ == "__main__":
    unittest.main()
