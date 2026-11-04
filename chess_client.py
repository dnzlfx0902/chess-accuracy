"""Cliente de la API publica de Chess.com para analisis de accuracy.

Hallazgos empiricos (2026-11-04, cuenta `foxyxdxb`):
- `/pub/player/<u>/games/<YYYY>/<MM>` incluye `"accuracies": {"white": float,
  "black": float}` SOLO en partidas revisadas. Cobertura medida: 19/42 en
  2026-09..11 (45%), 2/27 en 2023-01 (7%). Ausente = partida sin Game Review.
- El PGN no trae header ni comentario de accuracy (0/42 partidas).
- `/callback/analysis/game/live/<game_id>` responde 401
  `{"message":"Access not authorized"}` sin cookies de sesion: es la unica via
  para accuracy de partidas no revisadas publicamente.

Uso:
    python3 chess_client.py --username foxyxdxb --months 3
    python3 chess_client.py --username foxyxdxb --all
"""

from __future__ import annotations

import argparse
import json
import os
import random
import socket
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.chess.com/pub"
CALLBACK = "https://www.chess.com/callback"
UA = "chess-accuracy-tool/1.0 (+analisis local de accuracy)"
MAX_ATTEMPTS = 5


def _cache_root() -> Path:
    if os.environ.get("CHESS_CACHE_DIR"):
        return Path(os.environ["CHESS_CACHE_DIR"])
    base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / "chess_accuracy"


CACHE_DIR = _cache_root()
MIN_INTERVAL = float(os.environ.get("CHESS_MIN_INTERVAL", "1.0"))
CURRENT_MONTH_TTL = 6 * 3600.0


class ChessAPIError(RuntimeError):
    pass


# --- transporte con rate limit y backoff -----------------------------------

_lock = threading.Lock()
_last_request = [0.0]


def _throttle() -> None:
    with _lock:
        wait = MIN_INTERVAL - (time.monotonic() - _last_request[0])
        if wait > 0:
            time.sleep(wait)
        _last_request[0] = time.monotonic()


def _fetch(url: str, cookie: str | None = None) -> bytes:
    """GET con espaciado minimo entre requests y backoff en 429/5xx."""
    headers = {"User-Agent": UA, "Accept": "application/json"}
    if cookie:
        headers["Cookie"] = cookie
    for attempt in range(1, MAX_ATTEMPTS + 1):
        _throttle()
        try:
            with urllib.request.urlopen(
                urllib.request.Request(url, headers=headers), timeout=30
            ) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            retryable = exc.code == 429 or 500 <= exc.code < 600
            if not retryable or attempt == MAX_ATTEMPTS:
                body = exc.read()[:200]
                raise ChessAPIError(f"{url} -> HTTP {exc.code} {body!r}") from exc
            try:
                delay = float(exc.headers.get("Retry-After") or 0)
            except (TypeError, ValueError):
                delay = 0.0
            time.sleep(delay or min(60.0, 2 ** attempt + random.random()))
        except (urllib.error.URLError, socket.timeout) as exc:
            if attempt == MAX_ATTEMPTS:
                raise ChessAPIError(f"{url} -> {exc!r}") from exc
            time.sleep(2 ** attempt)
    raise ChessAPIError(f"{url} -> agotados los reintentos")


# --- cache en disco ---------------------------------------------------------


def cache_path(key: str) -> Path:
    return CACHE_DIR / f"{key}.json"


def _cache_read(key: str, ttl: float | None) -> dict | None:
    path = cache_path(key)
    if not path.exists():
        return None
    if ttl is not None and time.time() - path.stat().st_mtime > ttl:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return None


def _cache_write(key: str, data: dict) -> None:
    path = cache_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp, path)


def get_json(
    url: str, key: str, ttl: float | None = None, refresh: bool = False
) -> dict:
    """GET con cache: `ttl=None` = inmutable (meses cerrados, partidas)."""
    if not refresh:
        hit = _cache_read(key, ttl)
        if hit is not None:
            return hit
    data = json.loads(_fetch(url))
    _cache_write(key, data)
    return data


# --- endpoints --------------------------------------------------------------


def player(username: str = "foxyxdxb", refresh: bool = False) -> dict:
    return get_json(f"{API}/player/{username}", f"player/{username}", 3600, refresh)


def stats(username: str = "foxyxdxb", refresh: bool = False) -> dict:
    return get_json(f"{API}/player/{username}/stats", f"stats/{username}", 3600, refresh)


def archives(username: str = "foxyxdxb", refresh: bool = False) -> list[str]:
    ttl = CURRENT_MONTH_TTL
    data = get_json(
        f"{API}/player/{username}/games/archives",
        f"archives/{username}",
        ttl,
        refresh,
    )
    return data.get("archives", [])


def _is_current_month(year: int, month: int) -> bool:
    now = time.gmtime()
    return (year, month) == (now.tm_year, now.tm_mon)


def month_games(
    username: str, year: int, month: int, refresh: bool = False
) -> list[dict]:
    ttl = CURRENT_MONTH_TTL if _is_current_month(year, month) else None
    data = get_json(
        f"{API}/player/{username}/games/{year}/{month:02d}",
        f"games/{username}/{year}-{month:02d}",
        ttl,
        refresh,
    )
    return data.get("games", [])


def iter_months(username: str, months: int | None = None):
    """Rellena (year, month) desde el archivo mas reciente hacia atras."""
    arch = archives(username)
    parsed = []
    for url in arch:
        parts = url.rstrip("/").split("/")
        parsed.append((int(parts[-2]), int(parts[-1])))
    if months is not None:
        parsed = parsed[-months:]
    return parsed


def iter_games(username: str = "foxyxdxb", months: int | None = None, refresh: bool = False):
    for year, month in iter_months(username, months):
        for game in month_games(username, year, month, refresh):
            yield game


# --- extraccion -------------------------------------------------------------


def _opponent_side(game: dict, side: str) -> str:
    return "black" if side == "white" else "white"


def extract_game(game: dict, username: str = "foxyxdxb") -> dict:
    """Partida normalizada. `accuracy` es None si Chess.com no la publica."""
    me = username.lower()
    sides = {"white": game.get("white") or {}, "black": game.get("black") or {}}
    color = next(
        (s for s in ("white", "black") if sides[s].get("username", "").lower() == me),
        None,
    )
    acc = game.get("accuracies") or {}
    accuracies = {s: acc.get(s) for s in ("white", "black")}
    mine, theirs = (sides[color], sides[_opponent_side(game, color)]) if color else ({}, {})
    return {
        "id": (game.get("url") or "").rstrip("/").rsplit("/", 1)[-1] or None,
        "url": game.get("url"),
        "uuid": game.get("uuid"),
        "time_class": game.get("time_class"),
        "time_control": game.get("time_control"),
        "rated": game.get("rated"),
        "rules": game.get("rules"),
        "color": color,
        "result": mine.get("result"),
        "opponent": theirs.get("username"),
        "player_rating": mine.get("rating"),
        "opponent_rating": theirs.get("rating"),
        "accuracy": accuracies.get(color) if color else None,
        "accuracy_white": accuracies["white"],
        "accuracy_black": accuracies["black"],
        "accuracy_source": "public-api" if acc else None,
        "end_time": game.get("end_time"),
        "eco": game.get("eco"),
    }


# --- Game Review via cookies (unico camino para partidas no revisadas) ------


def load_netscape_cookies(path: str | Path) -> str:
    """Convierte un cookies.txt (formato Netscape) en header `Cookie`."""
    jar = []
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw[len("#HttpOnly_"):] if raw.startswith("#HttpOnly_") else raw
        if not line or line.startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) < 7:
            continue
        domain, _flag, _path, _secure, expiry, name, value = fields[:7]
        if not domain.lstrip(".").lower().endswith("chess.com"):
            continue
        if expiry.isdigit() and int(expiry) and int(expiry) < time.time():
            continue
        jar.append(f"{name}={value}")
    return "; ".join(jar)


def game_review(game_id: str | int, cookie: str | None = None) -> dict:
    """JSON de Game Review. Requiere sesion: 401 sin cookies validas."""
    if not cookie:
        env_file = os.environ.get("CHESS_COOKIE_FILE")
        cookie = os.environ.get("CHESS_COOKIE") or (
            load_netscape_cookies(env_file) if env_file else ""
        )
    if not cookie:
        raise ChessAPIError(
            "game_review requiere cookies de sesion de chess.com "
            "(CHESS_COOKIE o CHESS_COOKIE_FILE en formato Netscape); "
            "sin ellas el callback responde 401"
        )
    raw = _fetch(f"{CALLBACK}/analysis/game/live/{game_id}", cookie=cookie)
    return json.loads(raw)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--username", default="foxyxdxb")
    ap.add_argument("--months", type=int, default=3)
    ap.add_argument("--all", action="store_true", help="todos los meses del archivo")
    ap.add_argument("--refresh", action="store_true", help="ignorar cache")
    args = ap.parse_args(argv)

    months = None if args.all else args.months
    games = [extract_game(g, args.username) for g in iter_games(args.username, months, args.refresh)]
    with_acc = [g for g in games if g["accuracy"] is not None]
    summary = {
        "username": args.username,
        "months": len(iter_months(args.username, months)),
        "games": len(games),
        "with_accuracy": len(with_acc),
        "coverage_pct": round(100 * len(with_acc) / len(games), 1) if games else 0.0,
        "cache_dir": str(CACHE_DIR),
        "sample": with_acc[0] if with_acc else None,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
