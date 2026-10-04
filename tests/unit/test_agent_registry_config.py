import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from tools.config.agent_registry_config import fallback_enabled, python_stub_fallback_enabled


class PythonStubFallbackEnabledTests(unittest.TestCase):
    def _settings(self, path):
        return {"execution": {"ns": {"agent_registry": path}}}

    def _write_registry(self, tmp_path, contents):
        path = os.path.join(tmp_path, "agent_registry.yaml")
        with open(path, "w", encoding="utf-8") as f:
            f.write(contents)
        return path

    def test_missing_file_resolves_false(self):
        settings = self._settings(os.path.join("does", "not", "exist.yaml"))
        self.assertFalse(python_stub_fallback_enabled("script_generation", settings))

    def test_agent_missing_from_registry_resolves_false(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_registry(tmp, "agents:\n  other_agent:\n    connector_type: internal\n")
            settings = self._settings(path)
            self.assertFalse(python_stub_fallback_enabled("script_generation", settings))

    def test_empty_fallbacks_list_resolves_false(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_registry(
                tmp,
                "agents:\n  script_generation:\n    connector_type: internal\n    fallbacks: []\n",
            )
            settings = self._settings(path)
            self.assertFalse(python_stub_fallback_enabled("script_generation", settings))

    def test_declared_python_stub_fallback_without_enabled_flag_resolves_false(self):
        """enabled: true is required now — a bare connector_type match is not enough
        (every fallback tier ships disabled by default)."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_registry(
                tmp,
                "agents:\n"
                "  script_generation:\n"
                "    connector_type: internal\n"
                "    fallbacks:\n"
                "      - connector_type: python_stub\n"
                "        fallback_module: agents.common.fallback_core\n",
            )
            settings = self._settings(path)
            self.assertFalse(python_stub_fallback_enabled("script_generation", settings))

    def test_declared_python_stub_fallback_with_enabled_true_resolves_true(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_registry(
                tmp,
                "agents:\n"
                "  script_generation:\n"
                "    connector_type: internal\n"
                "    fallbacks:\n"
                "      - connector_type: python_stub\n"
                "        fallback_module: agents.common.fallback_core\n"
                "        enabled: true\n",
            )
            settings = self._settings(path)
            self.assertTrue(python_stub_fallback_enabled("script_generation", settings))

    def test_declared_python_stub_fallback_with_enabled_false_resolves_false(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_registry(
                tmp,
                "agents:\n"
                "  script_generation:\n"
                "    connector_type: internal\n"
                "    fallbacks:\n"
                "      - connector_type: python_stub\n"
                "        enabled: false\n",
            )
            settings = self._settings(path)
            self.assertFalse(python_stub_fallback_enabled("script_generation", settings))

    def test_non_stub_fallback_only_resolves_false(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_registry(
                tmp,
                "agents:\n"
                "  script_generation:\n"
                "    connector_type: internal\n"
                "    fallbacks:\n"
                "      - connector_type: ns_http\n"
                "        agent_name: script_generation\n"
                "        enabled: true\n",
            )
            settings = self._settings(path)
            self.assertFalse(python_stub_fallback_enabled("script_generation", settings))


class FallbackEnabledTests(unittest.TestCase):
    """Generalized fallback_enabled() — the single point of control every
    fallback tier (ns_http/alt_model/python_stub/dom_synthesized/...) for every
    agent is gated through."""

    def _settings(self, path):
        return {"execution": {"ns": {"agent_registry": path}}}

    def _write_registry(self, tmp_path, contents):
        path = os.path.join(tmp_path, "agent_registry.yaml")
        with open(path, "w", encoding="utf-8") as f:
            f.write(contents)
        return path

    def test_missing_agent_key_resolves_false(self):
        settings = self._settings(os.path.join("does", "not", "exist.yaml"))
        self.assertFalse(fallback_enabled("discovery", "ns_http", settings))

    def test_matching_connector_type_enabled_false_resolves_false(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_registry(
                tmp,
                "agents:\n"
                "  discovery:\n"
                "    fallbacks:\n"
                "      - connector_type: dom_synthesized\n"
                "        enabled: false\n",
            )
            settings = self._settings(path)
            self.assertFalse(fallback_enabled("discovery", "dom_synthesized", settings))

    def test_matching_connector_type_enabled_true_resolves_true(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_registry(
                tmp,
                "agents:\n"
                "  discovery:\n"
                "    fallbacks:\n"
                "      - connector_type: dom_synthesized\n"
                "        enabled: true\n",
            )
            settings = self._settings(path)
            self.assertTrue(fallback_enabled("discovery", "dom_synthesized", settings))

    def test_unknown_connector_type_resolves_false(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_registry(
                tmp,
                "agents:\n"
                "  semantic_map:\n"
                "    fallbacks:\n"
                "      - connector_type: ns_http\n"
                "        enabled: true\n",
            )
            settings = self._settings(path)
            self.assertFalse(fallback_enabled("semantic_map", "alt_model", settings))


if __name__ == "__main__":
    unittest.main()
