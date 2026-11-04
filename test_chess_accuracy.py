"""Tests de chess_accuracy.py (offline, datos sinteticos)."""

from __future__ import annotations

import contextlib
import io
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import chess_accuracy as ca
import chess_client as cc

USER = "foxyxdxb"


def raw_game(game_id: int, color: str = "white", time_class: str = "rapid", **extra) -> dict:
    me = {"username": USER, "rating": 1500, "result": "win"}
    foe = {"username": "rival", "rating": 1480, "result": "resigned"}
    game = {
        "url": f"https://www.chess.com/game/live/{game_id}",
        "time_class": time_class,
        "rated": True,
        "white": dict(me if color == "white" else foe),
        "black": dict(me if color == "black" else foe),
    }
    if "accuracies" in extra:
        game["accuracies"] = extra.pop("accuracies")
    game.update(extra)
    return game


def extract(games: list[dict]) -> list[dict]:
    return [cc.extract_game(g, USER) for g in games]


class StatsTest(unittest.TestCase):
    def test_mean_median_coverage_global_and_color(self):
        games = extract(
            [
                raw_game(1, "white", accuracies={"white": 40.0, "black": 30.0}),
                raw_game(2, "white", accuracies={"white": 60.0, "black": 50.0}),
                raw_game(3, "black"),
            ]
        )
        s = ca.summarize(games)
        self.assertEqual(s["all"]["games"], 3)
        self.assertEqual(s["all"]["with_accuracy"], 2)
        self.assertEqual(s["all"]["coverage_pct"], 66.7)
        self.assertEqual(s["all"]["mean"], 50.0)
        self.assertEqual(s["all"]["median"], 50.0)
        self.assertEqual(s["by_color"]["white"]["games"], 2)
        self.assertEqual(s["by_color"]["white"]["coverage_pct"], 100.0)
        self.assertEqual(s["by_color"]["black"]["with_accuracy"], 0)
        self.assertIsNone(s["by_color"]["black"]["mean"])

    def test_median_even_count_and_empty(self):
        self.assertEqual(ca._stats([10.0, 20.0, 30.0, 40.0], 4)["median"], 25.0)
        empty = ca._stats([], 0)
        self.assertEqual(empty["coverage_pct"], 0.0)
        self.assertIsNone(empty["median"])

    def test_accuracy_is_the_players_side(self):
        games = extract([raw_game(1, "black", accuracies={"white": 70.0, "black": 42.5})])
        self.assertEqual(games[0]["accuracy"], 42.5)
        self.assertEqual(games[0]["accuracy_source"], "public-api")


class CsvTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "manual.csv"

    def tearDown(self):
        self.tmp.cleanup()

    def test_load_filters_header_comments_and_invalid(self):
        self.path.write_text(
            "game_url,accuracy\n"
            "# comentario,1\n"
            "https://www.chess.com/game/live/111,55.5\n"
            "https://www.chess.com/game/live/222,abc\n"
            "https://www.chess.com/game/live/333,150\n"
            "https://www.chess.com/game/live/444,0\n",
            encoding="utf-8",
        )
        acc = ca.load_accuracy_csv(self.path)
        self.assertEqual(acc, {"111": 55.5, "444": 0.0})

    def test_apply_overrides_and_reports_unmatched(self):
        games = extract([raw_game(111), raw_game(222, accuracies={"white": 70.0, "black": 60.0})])
        self.path.write_text(
            "https://www.chess.com/game/live/111,55.5\n"
            "https://www.chess.com/game/live/999,60\n",
            encoding="utf-8",
        )
        info = ca.apply_csv(games, self.path)
        self.assertEqual(info["applied"], 1)
        self.assertEqual(info["unmatched"], ["999"])
        self.assertEqual(games[0]["accuracy"], 55.5)
        self.assertEqual(games[0]["accuracy_source"], "csv")
        self.assertEqual(games[1]["accuracy"], 70.0)  # sin fila CSV, intacta


class CookieTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.env = mock.patch.dict(os.environ, {}, clear=False)
        self.env.start()
        for key in ("CHESS_COOKIES", "CHESS_COOKIE", "CHESS_COOKIE_FILE"):
            os.environ.pop(key, None)

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_netscape_file_filters_domain_and_expiry(self):
        path = self.dir / "cookies.txt"
        path.write_text(
            "# Netscape HTTP Cookie File\n"
            "#HttpOnly_.chess.com\tTRUE\t/\tTRUE\t4102444800\tPHPSESSID\tsecret1\n"
            ".evil.com\tTRUE\t/\tTRUE\t4102444800\tPHPSESSID\tnope\n"
            ".chess.com\tTRUE\t/\tTRUE\t1000000000\tOLD\texpired\n",
            encoding="utf-8",
        )
        path.chmod(0o600)
        self.assertEqual(ca.resolve_cookie(str(path)), "PHPSESSID=secret1")

    def test_raw_header_via_env(self):
        os.environ["CHESS_COOKIES"] = "PHPSESSID=abc123; other=1"
        self.assertEqual(ca.resolve_cookie(None), "PHPSESSID=abc123; other=1")

    def test_missing_cookie_is_empty(self):
        self.assertEqual(ca.resolve_cookie(None), "")

    def test_world_readable_file_warns_without_leaking_value(self):
        path = self.dir / "cookies.txt"
        path.write_text(".chess.com\tTRUE\t/\tTRUE\t4102444800\tPHPSESSID\tsecretX\n", encoding="utf-8")
        path.chmod(0o644)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            cookie = ca.resolve_cookie(str(path))
        self.assertEqual(cookie, "PHPSESSID=secretX")
        self.assertIn("chmod 600", err.getvalue())
        self.assertNotIn("secretX", err.getvalue())


class ReviewPayloadTest(unittest.TestCase):
    def test_accuracies_dict(self):
        payload = {"game": {"accuracies": {"white": 88.1, "black": 77.2}}}
        self.assertEqual(ca.review_accuracy(payload, "black"), 77.2)

    def test_accuracy_with_side(self):
        payload = {"players": [{"color": "white", "accuracy": 50.0}, {"color": "black", "accuracy": 60.0}]}
        self.assertEqual(ca.review_accuracy(payload, "black"), 60.0)

    def test_unknown_shape_returns_none(self):
        self.assertIsNone(ca.review_accuracy({"accuracy": 90.0}, "black"))


class EndToEndTest(unittest.TestCase):
    def setUp(self):
        self.games = [
            raw_game(1, "white", "rapid", accuracies={"white": 40.0, "black": 30.0}),
            raw_game(2, "black", "rapid", accuracies={"white": 50.0, "black": 60.0}),
            raw_game(3, "white", "bullet"),
            raw_game(4, "black", "daily"),
        ]
        self.patches = [
            mock.patch.object(cc, "iter_months", lambda u, m=None: [(2026, 11)]),
            mock.patch.object(cc, "iter_games", lambda u, m=None, r=False: iter(self.games)),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def run_cli(self, argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = ca.main(argv)
        return rc, out.getvalue()

    def test_json_report_structure_and_filter(self):
        rc, out = self.run_cli(["--json"])
        self.assertEqual(rc, 0)
        report = json.loads(out)
        self.assertEqual(report["coverage"], {"games": 4, "with_accuracy": 2, "coverage_pct": 50.0})
        self.assertEqual(report["window"], {"months": 1, "first": "2026-11", "last": "2026-11"})
        self.assertEqual(report["totals"]["mean"], 50.0)
        self.assertEqual(report["by_color"]["white"]["with_accuracy"], 1)
        self.assertEqual(report["by_color"]["black"]["with_accuracy"], 1)

        rc, out = self.run_cli(["--json", "--time-class", "bullet"])
        report = json.loads(out)
        self.assertEqual(report["coverage"]["games"], 1)
        self.assertEqual(report["coverage"]["with_accuracy"], 0)

    def test_plain_output_has_tables(self):
        rc, out = self.run_cli([])
        self.assertEqual(rc, 0)
        for token in ("Blancas", "Negras", "rapid", "Global", "50.0%"):
            self.assertIn(token, out)

    def test_cookie_never_in_output(self):
        sentinel = "PHPSESSID=SUPERSECRET123"
        os.environ["CHESS_COOKIES"] = sentinel
        try:
            with mock.patch.object(
                cc,
                "game_review",
                lambda gid, cookie=None: {"accuracies": {"white": 71.0, "black": 72.0}},
            ):
                rc, out = self.run_cli(["--json", "--game-review", "--review-limit", "2"])
                self.assertEqual(rc, 0)
                self.assertNotIn("SUPERSECRET123", out)
                report = json.loads(out)
                self.assertEqual(report["game_review"]["filled"], 2)
        finally:
            os.environ.pop("CHESS_COOKIES", None)

    def test_game_review_without_cookie_exits(self):
        with self.assertRaises(SystemExit):
            ca.main(["--game-review"])


if __name__ == "__main__":
    unittest.main()
