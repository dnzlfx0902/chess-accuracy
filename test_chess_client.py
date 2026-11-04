"""Tests de chess_client con transporte simulado (sin red)."""

import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

import chess_client as cc

GAME_REVIEWED = {
    "url": "https://www.chess.com/game/live/111",
    "uuid": "u-111",
    "time_class": "rapid",
    "time_control": "600",
    "rated": True,
    "rules": "chess",
    "end_time": 1788295903,
    "white": {"username": "foxyxdxb", "result": "win", "rating": 297},
    "black": {"username": "rival", "result": "resigned", "rating": 268},
    "accuracies": {"white": 39.46, "black": 35.94},
}
GAME_PLAIN = {
    "url": "https://www.chess.com/game/live/222",
    "uuid": "u-222",
    "time_class": "rapid",
    "time_control": "600",
    "rated": True,
    "rules": "chess",
    "end_time": 1788295417,
    "white": {"username": "RIVAL", "result": "abandoned", "rating": 260},
    "black": {"username": "foxyxdxb", "result": "win", "rating": 289},
}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for patch in (
            mock.patch.object(cc, "CACHE_DIR", Path(self.tmp.name)),
            mock.patch.object(cc, "MIN_INTERVAL", 0.0),
            mock.patch.object(cc.time, "sleep", lambda s: None),
        ):
            patch.start()
            self.addCleanup(patch.stop)


class TestExtract(Base):
    def test_reviewed_game_has_accuracy_for_color(self):
        row = cc.extract_game(GAME_REVIEWED)
        self.assertEqual(row["color"], "white")
        self.assertEqual(row["accuracy"], 39.46)
        self.assertEqual(row["accuracy_black"], 35.94)
        self.assertEqual(row["accuracy_source"], "public-api")
        self.assertEqual(row["result"], "win")
        self.assertEqual(row["opponent"], "rival")
        self.assertEqual(row["id"], "111")

    def test_plain_game_accuracy_is_none_and_color_case_insensitive(self):
        row = cc.extract_game(GAME_PLAIN)
        self.assertEqual(row["color"], "black")
        self.assertIsNone(row["accuracy"])
        self.assertIsNone(row["accuracy_source"])
        self.assertEqual(row["opponent"], "RIVAL")
        self.assertEqual(row["player_rating"], 289)

    def test_unknown_player_color_is_none(self):
        row = cc.extract_game(GAME_PLAIN, username="otro")
        self.assertIsNone(row["color"])
        self.assertIsNone(row["accuracy"])


class TestCacheAndRateLimit(Base):
    def test_cache_hits_disk_and_avoids_second_fetch(self):
        payload = json.dumps({"games": [GAME_REVIEWED]}).encode()
        with mock.patch.object(cc, "_fetch", return_value=payload) as fetch:
            first = cc.month_games("foxyxdxb", 2026, 9)
            second = cc.month_games("foxyxdxb", 2026, 9)
        self.assertEqual(first, second)
        self.assertEqual(fetch.call_count, 1)
        self.assertTrue(cc.cache_path("games/foxyxdxb/2026-09").exists())

    def test_refresh_bypasses_cache(self):
        payload = json.dumps({"games": []}).encode()
        with mock.patch.object(cc, "_fetch", return_value=payload) as fetch:
            cc.month_games("foxyxdxb", 2026, 9)
            cc.month_games("foxyxdxb", 2026, 9, refresh=True)
        self.assertEqual(fetch.call_count, 2)

    def test_closed_month_never_expires_current_month_does(self):
        with mock.patch.object(cc, "_fetch", return_value=b'{"games": []}'):
            cc.month_games("foxyxdxb", 2020, 1)
        cache = cc.cache_path("games/foxyxdxb/2020-01")
        old = cache.stat().st_mtime - 10 ** 7
        Path(cache).touch()
        import os

        os.utime(cache, (old, old))
        self.assertIsNotNone(cc._cache_read("games/foxyxdxb/2020-01", None))
        self.assertIsNone(cc._cache_read("games/foxyxdxb/2020-01", cc.CURRENT_MONTH_TTL))

    def test_429_retries_then_succeeds(self):
        err = urllib.error.HTTPError("u", 429, "slow down", {"Retry-After": "0"}, io.BytesIO(b""))
        ok = mock.MagicMock()
        ok.__enter__.return_value.read.return_value = b'{"ok": 1}'
        with mock.patch.object(cc.urllib.request, "urlopen", side_effect=[err, ok]) as uo:
            self.assertEqual(cc._fetch("http://x"), b'{"ok": 1}')
        self.assertEqual(uo.call_count, 2)

    def test_non_retryable_error_raises_without_retry(self):
        err = urllib.error.HTTPError("u", 404, "nf", {}, io.BytesIO(b"nope"))
        with mock.patch.object(cc.urllib.request, "urlopen", side_effect=err) as uo:
            with self.assertRaises(cc.ChessAPIError):
                cc._fetch("http://x")
        self.assertEqual(uo.call_count, 1)


class TestCookies(Base):
    def test_netscape_cookie_filtering(self):
        path = Path(self.tmp.name) / "cookies.txt"
        future = "99999999999"
        path.write_text(
            "\n".join(
                [
                    "# Netscape HTTP Cookie File",
                    f"#HttpOnly_.chess.com\tTRUE\t/\tTRUE\t{future}\tPHPSESSID\tabc",
                    f".chess.com\tTRUE\t/\tTRUE\t{future}\tcsrftoken\txyz",
                    f".example.com\tTRUE\t/\tFALSE\t{future}\tother\tnope",
                    f".chess.com\tTRUE\t/\tFALSE\t1000000000\tstale\tgone",
                ]
            )
        )
        header = cc.load_netscape_cookies(path)
        self.assertIn("PHPSESSID=abc", header)
        self.assertIn("csrftoken=xyz", header)
        self.assertNotIn("other", header)
        self.assertNotIn("stale", header)

    def test_game_review_without_cookie_raises(self):
        env = {k: v for k, v in cc.os.environ.items() if not k.startswith("CHESS_COOKIE")}
        with mock.patch.dict(cc.os.environ, env, clear=True):
            with self.assertRaises(cc.ChessAPIError):
                cc.game_review(111)


if __name__ == "__main__":
    unittest.main()
