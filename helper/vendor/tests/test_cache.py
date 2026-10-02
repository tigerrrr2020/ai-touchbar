import os
import tempfile
import unittest
from usage import cache


class TestCache(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "c.json")

    def test_read_returns_none_when_missing(self):
        self.assertIsNone(cache.read(self.path, ttl=300, now=1000))

    def test_write_then_read_within_ttl(self):
        cache.write(self.path, {"x": 1}, now=1000)
        self.assertEqual(cache.read(self.path, ttl=300, now=1200), {"x": 1})

    def test_read_entry_includes_cache_timestamp(self):
        cache.write(self.path, {"x": 1}, now=1000)
        self.assertEqual(
            cache.read_entry(self.path, ttl=300, now=1200),
            {"ts": 1000, "data": {"x": 1}},
        )

    def test_read_returns_none_when_expired(self):
        cache.write(self.path, {"x": 1}, now=1000)
        self.assertIsNone(cache.read(self.path, ttl=300, now=1400))

    def test_read_stale_ignores_ttl(self):
        cache.write(self.path, {"x": 1}, now=1000)
        self.assertEqual(cache.read_stale(self.path), {"x": 1})

    def test_read_stale_entry_includes_cache_timestamp(self):
        cache.write(self.path, {"x": 1}, now=1000)
        self.assertEqual(
            cache.read_stale_entry(self.path),
            {"ts": 1000, "data": {"x": 1}},
        )
