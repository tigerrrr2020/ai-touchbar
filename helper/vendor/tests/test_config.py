import json
import os
import tempfile
import unittest

from usage import config


class TestConfig(unittest.TestCase):
    def test_missing_config_defaults_to_active_refresh_disabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = config.load_config(os.path.join(tmp, "missing.json"))

        self.assertFalse(settings["codex_active_refresh"])
        self.assertEqual(settings["codex_refresh_interval_seconds"], 1800)

    def test_invalid_config_defaults_to_active_refresh_disabled(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            f.write("not-json")
            path = f.name
        self.addCleanup(lambda: os.path.exists(path) and os.unlink(path))

        self.assertFalse(config.load_config(path)["codex_active_refresh"])

    def test_explicit_config_enables_refresh_and_clamps_short_interval(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            json.dump({
                "codex_active_refresh": True,
                "codex_refresh_interval_seconds": 10,
            }, f)
            path = f.name
        self.addCleanup(lambda: os.path.exists(path) and os.unlink(path))

        settings = config.load_config(path)

        self.assertTrue(settings["codex_active_refresh"])
        self.assertEqual(settings["codex_refresh_interval_seconds"], 300)
