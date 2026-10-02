import os
import tempfile
import unittest

from usage import refresh_backoff as rb


class TestRefreshBackoff(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "backoff.json")

    def tearDown(self):
        self.dir.cleanup()

    def test_due_when_no_state(self):
        self.assertTrue(rb.due(self.path, now=1000))

    def test_failure_blocks_then_clears_by_time(self):
        rb.note_failure(self.path, now=1000)  # first failure → BASE_SECONDS
        self.assertFalse(rb.due(self.path, now=1000))
        self.assertFalse(rb.due(self.path, now=1000 + rb.BASE_SECONDS - 1))
        self.assertTrue(rb.due(self.path, now=1000 + rb.BASE_SECONDS))

    def test_different_scope_is_attemptable(self):
        rb.note_failure(self.path, now=1000, scope="old-endpoint")
        self.assertFalse(rb.due(self.path, now=1000, scope="old-endpoint"))
        self.assertTrue(rb.due(self.path, now=1000, scope="new-endpoint"))

    def test_backoff_grows_exponentially(self):
        # Two consecutive failures → ~2x BASE, capped at MAX.
        rb.note_failure(self.path, now=0)
        rb.note_failure(self.path, now=0)
        # second failure delay = BASE * 2^1
        self.assertFalse(rb.due(self.path, now=rb.BASE_SECONDS))   # still blocked
        self.assertTrue(rb.due(self.path, now=rb.BASE_SECONDS * 2))

    def test_delay_capped_at_max(self):
        for _ in range(20):
            rb.note_failure(self.path, now=0)
        self.assertFalse(rb.due(self.path, now=rb.MAX_SECONDS - 1))
        self.assertTrue(rb.due(self.path, now=rb.MAX_SECONDS))

    def test_rate_limited_uses_higher_floor(self):
        rb.note_failure(self.path, now=0, rate_limited=True)
        # First failure's exponential delay (BASE) is below the rate-limit floor.
        self.assertFalse(rb.due(self.path, now=rb.BASE_SECONDS))
        self.assertTrue(rb.due(self.path, now=rb.RATE_LIMIT_MIN_SECONDS))

    def test_clear_resets(self):
        rb.note_failure(self.path, now=1000)
        rb.clear(self.path)
        self.assertTrue(rb.due(self.path, now=1000))

    def test_corrupt_state_is_attemptable(self):
        with open(self.path, "w") as f:
            f.write("not-json")
        self.assertTrue(rb.due(self.path, now=1000))


if __name__ == "__main__":
    unittest.main()
