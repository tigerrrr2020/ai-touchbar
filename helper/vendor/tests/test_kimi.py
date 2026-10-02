import json
import os
import stat
import sys
import tempfile
import unittest
from contextlib import contextmanager
from unittest import mock

from usage import kimi


FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "kimi_usage.json")


class TestKimiCredentials(unittest.TestCase):
    def test_official_oauth_configuration(self):
        self.assertEqual(
            kimi.CLIENT_ID,
            "17e5f671-d194-4dfb-9706-5516cb48c098",
        )
        self.assertEqual(
            kimi.OAUTH_URL,
            "https://auth.kimi.com/api/oauth/token",
        )

    def test_credentials_path_honors_kimi_code_home(self):
        with mock.patch.dict(os.environ, {"KIMI_CODE_HOME": "/tmp/kimi-code"}):
            self.assertEqual(
                kimi.credentials_path(),
                os.path.join("/tmp/kimi-code", "credentials", "kimi-code.json"),
            )

    def test_credentials_path_defaults_to_home_kimi_code(self):
        with mock.patch.dict(os.environ, {}, clear=True), \
             mock.patch.object(kimi.os.path, "expanduser",
                               side_effect=lambda path: path.replace("~", "/home/me")):
            self.assertEqual(
                kimi.credentials_path(),
                os.path.join("/home/me/.kimi-code", "credentials", "kimi-code.json"),
            )

    def test_credential_paths_include_legacy_kimi_cli_location(self):
        with mock.patch.dict(os.environ, {"KIMI_SHARE_DIR": "/tmp/legacy"}, clear=True), \
             mock.patch.object(kimi.os.path, "expanduser",
                               side_effect=lambda path: path.replace("~", "/home/me")):
            self.assertEqual(
                kimi.credential_paths(),
                [
                    os.path.join("/home/me/.kimi-code", "credentials", "kimi-code.json"),
                    os.path.join("/tmp/legacy", "credentials", "kimi-code.json"),
                ],
            )

    def test_read_credentials_falls_back_to_legacy_location(self):
        valid = mock.mock_open(read_data='{"access_token":"legacy","expires_at":2000}')
        with mock.patch.object(
            kimi,
            "credential_paths",
            return_value=["/new/kimi-code.json", "/old/kimi-code.json"],
        ), mock.patch("builtins.open", valid) as opened:
            opened.side_effect = [FileNotFoundError, valid.return_value]
            result = kimi.read_credentials()

        self.assertEqual(result["access_token"], "legacy")

    def test_read_credentials_returns_mapping(self):
        with mock.patch("builtins.open", mock.mock_open(
            read_data='{"access_token":"abc","expires_at":2000}'
        )):
            self.assertEqual(kimi.read_credentials("/tmp/creds.json")["access_token"], "abc")

    def test_read_credentials_returns_none_for_invalid_file(self):
        with mock.patch("builtins.open", mock.mock_open(read_data="not-json")):
            self.assertIsNone(kimi.read_credentials("/tmp/creds.json"))

    def test_expired_token_detected(self):
        self.assertTrue(kimi.is_expired({"expires_at": 1000}, now=1000))
        self.assertFalse(kimi.is_expired({"expires_at": 1001}, now=1000))

    def test_zero_expiry_matches_official_unknown_expiry_semantics(self):
        self.assertFalse(kimi.is_expired({"expires_at": 0}, now=1000))


class TestKimiParse(unittest.TestCase):
    def setUp(self):
        with open(FIXTURE) as f:
            self.fixture = json.load(f)

    def test_parse_usage_maps_five_hour_and_weekly(self):
        result = kimi.parse_kimi_usage(self.fixture)

        self.assertEqual(result["five_h"]["pct"], 34)
        self.assertEqual(result["five_h"]["resets_at"], 1781190000)
        self.assertEqual(result["weekly"]["pct"], 8)
        self.assertEqual(result["weekly"]["resets_at"], 1781600000)

    def test_parse_selects_300_minute_window(self):
        result = kimi.parse_kimi_usage(self.fixture)
        self.assertNotEqual(result["five_h"]["pct"], 10)

    def test_parse_accepts_remaining_and_clamps_percentages(self):
        payload = {
            "usage": {"limit": 100, "remaining": -20, "reset_at": 10},
            "limits": [{
                "window": {"duration": 300, "timeUnit": "MINUTE"},
                "detail": {"limit": 100, "remaining": 150, "reset_at": 20},
            }],
        }

        result = kimi.parse_kimi_usage(payload)

        self.assertEqual(result["weekly"]["pct"], 100)
        self.assertEqual(result["five_h"]["pct"], 0)

    def test_parse_accepts_iso_reset_timestamp(self):
        payload = {
            "usage": {
                "limit": 100,
                "used": 1,
                "resetAt": "2026-06-11T13:00:00Z",
            },
            "limits": [{
                "window": {"duration": 300, "timeUnit": "MINUTE"},
                "detail": {"limit": 100, "used": 1, "reset_at": 20},
            }],
        }

        result = kimi.parse_kimi_usage(payload)

        self.assertEqual(result["weekly"]["resets_at"], 1781182800)

    def test_parse_rejects_missing_five_hour_window(self):
        payload = {
            "usage": {"limit": 100, "used": 1, "reset_at": 10},
            "limits": [],
        }
        with self.assertRaises(ValueError):
            kimi.parse_kimi_usage(payload)


class TestKimiHttp(unittest.TestCase):
    def test_access_token_is_not_exposed_in_process_arguments(self):
        completed = mock.Mock(
            stdout='{"usage":{},"limits":[]}\n__HTTP__200',
        )
        with mock.patch.object(kimi, "_proxy", return_value=None), \
             mock.patch.object(kimi.subprocess, "run", return_value=completed) as run:
            kimi._http_get_usage("secret-token")

        args = run.call_args.args[0]
        self.assertNotIn("secret-token", " ".join(args))
        self.assertIn("Authorization: Bearer secret-token", run.call_args.kwargs["input"])

    def test_http_rejects_newlines_in_token(self):
        with self.assertRaises(ValueError):
            kimi._http_get_usage("bad\ntoken")

    def test_refresh_token_is_sent_in_stdin_not_process_arguments(self):
        completed = mock.Mock(
            stdout=(
                '{"access_token":"new","refresh_token":"new-refresh",'
                '"expires_in":3600}\n__HTTP__200'
            ),
        )
        with mock.patch.object(kimi, "_proxy", return_value=None), \
             mock.patch.object(kimi.subprocess, "run", return_value=completed) as run:
            result = kimi._http_refresh("secret-refresh")

        args = run.call_args.args[0]
        self.assertNotIn("secret-refresh", " ".join(args))
        self.assertIn("refresh_token=secret-refresh", run.call_args.kwargs["input"])
        self.assertEqual(result["access_token"], "new")


class TestKimiStorage(unittest.TestCase):
    def test_lock_path_matches_official_kimi_code_namespace(self):
        path = "/tmp/home/credentials/kimi-code.json"
        self.assertEqual(
            kimi._refresh_lock_target(path),
            os.path.join("/tmp/home", "oauth", "kimi-code"),
        )

    def test_atomic_write_preserves_unknown_fields_and_tightens_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "credentials", "kimi-code.json")
            os.makedirs(os.path.dirname(path))
            with open(path, "w") as f:
                json.dump({"access_token": "old", "custom": "keep"}, f)

            kimi._write_credentials_atomic(
                path,
                {"access_token": "new", "custom": "keep"},
            )

            with open(path) as f:
                stored = json.load(f)
            self.assertEqual(stored["custom"], "keep")
            self.assertEqual(stored["access_token"], "new")
            if sys.platform != "win32":
                self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)


class TestKimiFetch(unittest.TestCase):
    def setUp(self):
        # Neutralize the refresh backoff so these tests are deterministic and
        # never touch the real ~/.cache state.
        patches = [
            mock.patch.object(kimi.refresh_backoff, "due", return_value=True),
            mock.patch.object(kimi.refresh_backoff, "note_failure"),
            mock.patch.object(kimi.refresh_backoff, "clear"),
        ]
        self.backoff_due, self.backoff_note, self.backoff_clear = (
            p.start() for p in patches
        )
        for p in patches:
            self.addCleanup(p.stop)

    def test_fetch_returns_no_data_without_credentials(self):
        with mock.patch.object(kimi, "read_credentials_with_path",
                               return_value=(None, None)):
            self.assertEqual(kimi.fetch_kimi(), {"ok": False, "reason": "no_data"})

    def test_expired_current_credentials_are_refreshed_before_usage(self):
        old = {
            "access_token": "old",
            "refresh_token": "refresh",
            "expires_at": 1000,
        }
        fresh = dict(old, access_token="new", expires_at=2000)
        with mock.patch.object(kimi, "read_credentials_with_path",
                               return_value=(old, "/current.json")), \
             mock.patch.object(kimi, "credentials_path",
                               return_value="/current.json"), \
             mock.patch.object(kimi, "_refresh_credentials",
                               return_value=fresh) as refresh, \
             mock.patch.object(kimi, "_http_get_usage",
                               return_value={"usage": {}, "limits": []}), \
             mock.patch.object(kimi, "parse_kimi_usage",
                               return_value={"ok": True}) as parse, \
             mock.patch.object(kimi.time, "time", return_value=1000):
            self.assertEqual(kimi.fetch_kimi(), {"ok": True})

        refresh.assert_called_once_with("/current.json", old, force=False)
        parse.assert_called_once()

    def test_expired_legacy_credentials_are_also_refreshed(self):
        # The active store may be the legacy ~/.kimi path; it must refresh in
        # place too, not be left read-only to go stale.
        old = {"access_token": "old", "refresh_token": "r", "expires_at": 1000}
        fresh = dict(old, access_token="new", expires_at=2000)
        with mock.patch.object(kimi, "read_credentials_with_path",
                               return_value=(old, "/legacy.json")), \
             mock.patch.object(kimi, "_refresh_credentials",
                               return_value=fresh) as refresh, \
             mock.patch.object(kimi, "_http_get_usage",
                               return_value={"usage": {}, "limits": []}), \
             mock.patch.object(kimi, "parse_kimi_usage", return_value={"ok": True}), \
             mock.patch.object(kimi.time, "time", return_value=1000):
            self.assertEqual(kimi.fetch_kimi(), {"ok": True})
        refresh.assert_called_once_with("/legacy.json", old, force=False)

    def test_fetch_returns_expired_for_rejected_credentials(self):
        creds = {
            "access_token": "abc",
            "refresh_token": "refresh",
            "expires_at": 2000,
        }
        with mock.patch.object(kimi, "read_credentials_with_path",
                               return_value=(creds, "/current.json")), \
             mock.patch.object(kimi, "credentials_path",
                               return_value="/current.json"), \
             mock.patch.object(kimi.time, "time", return_value=1000), \
             mock.patch.object(kimi, "_http_get_usage",
                               side_effect=kimi.KimiAuthError), \
             mock.patch.object(kimi, "_refresh_credentials",
                               side_effect=kimi.KimiRefreshUnauthorized):
            self.assertEqual(kimi.fetch_kimi(), {"ok": False, "reason": "expired"})

    def test_usage_401_refreshes_and_retries_once(self):
        creds = {
            "access_token": "old",
            "refresh_token": "refresh",
            "expires_at": 2000,
        }
        fresh = dict(creds, access_token="new", expires_at=3000)
        usage = {"usage": {}, "limits": []}
        with mock.patch.object(kimi, "read_credentials_with_path",
                               return_value=(creds, "/current.json")), \
             mock.patch.object(kimi, "credentials_path",
                               return_value="/current.json"), \
             mock.patch.object(kimi.time, "time", return_value=1000), \
             mock.patch.object(kimi, "_http_get_usage",
                               side_effect=[kimi.KimiAuthError, usage]) as get, \
             mock.patch.object(kimi, "_refresh_credentials",
                               return_value=fresh) as refresh, \
             mock.patch.object(kimi, "parse_kimi_usage",
                               return_value={"ok": True}):
            self.assertEqual(kimi.fetch_kimi(), {"ok": True})

        refresh.assert_called_once_with("/current.json", creds, force=True)
        self.assertEqual(get.call_count, 2)

    def test_active_backoff_skips_refresh(self):
        creds = {"access_token": "old", "refresh_token": "r", "expires_at": 1000}
        self.backoff_due.return_value = False
        with mock.patch.object(kimi, "read_credentials_with_path",
                               return_value=(creds, "/current.json")), \
             mock.patch.object(kimi, "credentials_path",
                               return_value="/current.json"), \
             mock.patch.object(kimi, "_refresh_credentials") as refresh, \
             mock.patch.object(kimi.time, "time", return_value=1000):
            self.assertEqual(kimi.fetch_kimi(), {"ok": False, "reason": "expired"})
        refresh.assert_not_called()

    def test_rate_limited_refresh_escalates_backoff(self):
        creds = {"access_token": "old", "refresh_token": "r", "expires_at": 1000}
        with mock.patch.object(kimi, "read_credentials_with_path",
                               return_value=(creds, "/current.json")), \
             mock.patch.object(kimi, "credentials_path",
                               return_value="/current.json"), \
             mock.patch.object(kimi, "_refresh_credentials",
                               side_effect=kimi.KimiRefreshRateLimited), \
             mock.patch.object(kimi.time, "time", return_value=1000):
            self.assertEqual(
                kimi.fetch_kimi(), {"ok": False, "reason": "rate_limited"}
            )
        self.assertTrue(self.backoff_note.call_args.kwargs.get("rate_limited"))

    def test_refresh_short_circuits_when_peer_rotated_credentials(self):
        initial = {
            "access_token": "old",
            "refresh_token": "old-refresh",
            "expires_at": 1000,
        }
        peer = {
            "access_token": "peer",
            "refresh_token": "peer-refresh",
            "expires_at": 3000,
        }

        @contextmanager
        def unlocked(_path):
            yield

        with mock.patch.object(kimi, "_refresh_lock", side_effect=unlocked), \
             mock.patch.object(kimi, "_read_credentials_file",
                               return_value=peer), \
             mock.patch.object(kimi, "_http_refresh") as refresh, \
             mock.patch.object(kimi.time, "time", return_value=2000):
            result = kimi._refresh_credentials(
                "/current.json",
                initial,
                force=True,
            )

        self.assertEqual(result, peer)
        refresh.assert_not_called()


if __name__ == "__main__":
    unittest.main()
