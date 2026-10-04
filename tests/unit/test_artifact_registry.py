import os
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from tools.state.artifact_registry import ArtifactRegistry, content_signature


class ContentSignatureTests(unittest.TestCase):
    def test_same_text_same_signature(self):
        self.assertEqual(
            content_signature("Login with valid credentials", "step 1"),
            content_signature("Login with valid credentials", "step 1"),
        )

    def test_whitespace_and_case_insensitive(self):
        self.assertEqual(
            content_signature("Login   With Valid Credentials"),
            content_signature("login with valid   credentials"),
        )

    def test_different_text_different_signature(self):
        self.assertNotEqual(
            content_signature("Login with valid credentials"),
            content_signature("Logout of the application"),
        )


class ArtifactRegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def test_new_content_gets_module_prefixed_sequential_id(self):
        registry = ArtifactRegistry(self.tmp_dir)
        artifact_id, is_new, _ = registry.get_or_create_id("M03", "BS", "Dashboard loads widgets")
        self.assertEqual(artifact_id, "M03_BS_001")
        self.assertTrue(is_new)

        artifact_id_2, is_new_2, _ = registry.get_or_create_id("M03", "BS", "Dashboard filters results")
        self.assertEqual(artifact_id_2, "M03_BS_002")
        self.assertTrue(is_new_2)

    def test_same_content_reuses_existing_id_without_advancing_counter(self):
        registry = ArtifactRegistry(self.tmp_dir)
        first_id, _, _ = registry.get_or_create_id("M03", "BS", "Dashboard loads widgets")
        second_id, is_new, _ = registry.get_or_create_id("M03", "BS", "Dashboard loads widgets")

        self.assertEqual(first_id, second_id)
        self.assertFalse(is_new)

        next_id, _, _ = registry.get_or_create_id("M03", "BS", "A genuinely new scenario")
        self.assertEqual(next_id, "M03_BS_002")

    def test_different_modules_do_not_collide(self):
        registry = ArtifactRegistry(self.tmp_dir)
        m01_id, _, _ = registry.get_or_create_id("M01", "BS", "Login with valid credentials")
        m02_id, _, _ = registry.get_or_create_id("M02", "BS", "Login with valid credentials")

        # Same content in different modules gets distinct, module-prefixed IDs —
        # this is the exact collision the registry was built to prevent.
        self.assertEqual(m01_id, "M01_BS_001")
        self.assertEqual(m02_id, "M02_BS_001")
        self.assertNotEqual(m01_id, m02_id)

    def test_new_module_starts_at_one_even_when_other_modules_are_populated(self):
        registry = ArtifactRegistry(self.tmp_dir)
        for i in range(7):
            registry.get_or_create_id("M01", "BS", f"M01 scenario {i}")
        for i in range(3):
            registry.get_or_create_id("M02", "BS", f"M02 scenario {i}")

        new_module_id, is_new, _ = registry.get_or_create_id("M03", "BS", "Brand new dashboard scenario")
        self.assertEqual(new_module_id, "M03_BS_001")
        self.assertTrue(is_new)

    def test_persists_across_registry_instances(self):
        registry = ArtifactRegistry(self.tmp_dir)
        artifact_id, _, _ = registry.get_or_create_id("M03", "BS", "Dashboard loads widgets")
        registry.save()

        reloaded = ArtifactRegistry(self.tmp_dir)
        same_id, is_new, _ = reloaded.get_or_create_id("M03", "BS", "Dashboard loads widgets")
        self.assertEqual(same_id, artifact_id)
        self.assertFalse(is_new)

        next_id, _, _ = reloaded.get_or_create_id("M03", "BS", "Yet another new scenario")
        self.assertEqual(next_id, "M03_BS_002")

    def test_different_artifact_types_have_independent_counters(self):
        registry = ArtifactRegistry(self.tmp_dir)
        bs_id, _, _ = registry.get_or_create_id("M03", "BS", "Dashboard loads widgets")
        int_id, _, _ = registry.get_or_create_id("M03", "INT", "click submit button")

        self.assertEqual(bs_id, "M03_BS_001")
        self.assertEqual(int_id, "M03_INT_001")

    def test_missing_module_id_falls_back_to_gen_bucket(self):
        registry = ArtifactRegistry(self.tmp_dir)
        artifact_id, _, _ = registry.get_or_create_id(None, "BS", "Flat mode scenario")
        self.assertEqual(artifact_id, "GEN_BS_001")


if __name__ == "__main__":
    unittest.main()
