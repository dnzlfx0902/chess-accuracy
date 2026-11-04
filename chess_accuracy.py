#!/usr/bin/env python3
"""Precision historica (accuracy) de una cuenta de Chess.com.

Fuente principal: campo `accuracies` de los archivos mensuales publicos, que
solo aparece en partidas con Game Review publico (parcial, no imputable).
Fuentes opcionales, nunca obligatorias: Game Review autenticado con cookies
Netscape y CSV manual `game_url,accuracy`.

    python3 chess_accuracy.py --username foxyxdxb
    python3 chess_accuracy.py --time-class rapid --json
    python3 chess_accuracy.py --csv-file manual.csv --json

Las cookies nunca se imprimen, loguean ni se escriben en la cache.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
import time
from pathlib import Path

import chess_client as cc

TIME_CLASSES = ("bullet", "blitz", "rapid", "daily")
ACC_MIN, ACC_MAX = 0.0, 100.0


# --- estadistica ------------------------------------------------------------


def _stats(values: list[float], games: int) -> dict:
    n = len(values)
    return {
        "games": games,
        "with_accuracy": n,
        "coverage_pct": round(100.0 * n / games, 1) if games else 0.0,
        "mean": round(statistics.fmean(values), 2) if n else None,
        "median": round(statistics.median(values), 2) if n else None,
        "min": round(min(values), 2) if n else None,
        "max": round(max(values), 2) if n else None,
    }


def summarize(games: list[dict]) -> dict:
    """Metricas global, por color y por ritmo sobre el conjunto recibido."""

    def block(subset: list[dict]) -> dict:
        values = [g["accuracy"] for g in subset if g["accuracy"] is not None]
        return _stats(values, len(subset))

    return {
        "all": block(games),
        "by_color": {c: block([g for g in games if g["color"] == c]) for c in ("white", "black")},
        "by_time_class": {t: block([g for g in games if g["time_class"] == t]) for t in TIME_CLASSES},
    }


# --- CSV manual -------------------------------------------------------------


def load_accuracy_csv(path: str | Path) -> dict[str, float]:
    """`game_url,accuracy` -> {game_id: accuracy}. Cabecera e invalidos fuera."""
    acc: dict[str, float] = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.reader(fh):
            if len(row) < 2 or not row[0].strip() or row[0].lstrip().startswith("#"):
                continue
            url, raw = row[0].strip(), row[1].strip()
            if url.lower() in ("game_url", "url"):
                continue
            try:
                value = float(raw)
            except ValueError:
                continue
            if not ACC_MIN <= value <= ACC_MAX:
                continue
            game_id = url.rstrip("/").rsplit("/", 1)[-1]
            if game_id:
                acc[game_id] = value
    return acc


def apply_csv(games: list[dict], path: str | Path) -> dict:
    acc = load_accuracy_csv(path)
    applied = set()
    for game in games:
        if game["id"] in acc:
            game["accuracy"] = acc[game["id"]]
            game["accuracy_source"] = "csv"
            applied.add(game["id"])
    return {
        "rows": len(acc),
        "applied": len(applied),
        "unmatched": sorted(set(acc) - applied),
    }


# --- cookies / Game Review --------------------------------------------------


def _warn_perms(path: Path) -> None:
    try:
        mode = path.stat().st_mode
    except OSError:
        return
    if mode & 0o077:
        print(
            f"aviso: {path} es legible por otros usuarios; usa chmod 600",
            file=sys.stderr,
        )


def resolve_cookie(path_arg: str | None) -> str:
    """Header `Cookie` desde --cookies-file, CHESS_COOKIES o CHESS_COOKIE.

    Devuelve "" si no hay nada. Nunca expone el valor: los mensajes solo
    nombran la fuente.
    """
    raw = os.environ.get("CHESS_COOKIE", "").strip()
    candidate = path_arg or os.environ.get("CHESS_COOKIES") or os.environ.get("CHESS_COOKIE_FILE")
    if candidate:
        path = Path(candidate)
        if path.is_file():
            _warn_perms(path)
            return cc.load_netscape_cookies(path)
        if not raw and ("=" in candidate or ";" in candidate):
            return candidate.strip()  # CHESS_COOKIES con el header en crudo
    return raw


def review_accuracy(payload: dict, color: str) -> float | None:
    """Accuracy del color dado en un payload de Game Review.

    Formatos conocidos: `{"accuracies": {"white": x, "black": y}}` y objetos
    con `accuracy` + `color`/`side`. Cualquier otra forma -> None (no se
    adivina el lado).
    """

    def walk(node, depth: int = 0):
        if depth > 6:
            return None
        if isinstance(node, dict):
            acc = node.get("accuracies")
            if isinstance(acc, dict):
                value = acc.get(color)
                if isinstance(value, (int, float)):
                    return float(value)
            value = node.get("accuracy")
            side = str(node.get("color") or node.get("side") or "").lower()
            if isinstance(value, (int, float)) and side == color:
                return float(value)
            for child in node.values():
                found = walk(child, depth + 1)
                if found is not None:
                    return found
        elif isinstance(node, list):
            for child in node:
                found = walk(child, depth + 1)
                if found is not None:
                    return found
        return None

    return walk(payload)


def fill_from_review(games: list[dict], cookie: str, limit: int) -> dict:
    attempted = filled = errors = 0
    for game in games:
        if game["accuracy"] is not None or not game["id"]:
            continue
        if attempted >= limit:
            break
        attempted += 1
        try:
            value = review_accuracy(cc.game_review(game["id"], cookie), game["color"])
        except cc.ChessAPIError:
            errors += 1
            continue
        if value is not None:
            game["accuracy"] = round(value, 2)
            game["accuracy_source"] = "game-review"
            filled += 1
    return {"attempted": attempted, "filled": filled, "errors": errors}


# --- salida -----------------------------------------------------------------


def _cell(value, digits: int = 2) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def _table(rows: list[tuple[str, dict]]) -> list[str]:
    head = f"{'Grupo':<12}{'Partidas':>10}{'Con acc':>10}{'Cobertura':>11}{'Media':>9}{'Mediana':>9}{'Min':>8}{'Max':>8}"
    lines = [head, "-" * len(head)]
    for label, s in rows:
        lines.append(
            f"{label:<12}{s['games']:>10}{s['with_accuracy']:>10}"
            f"{s['coverage_pct']:>10.1f}%{_cell(s['mean']):>9}{_cell(s['median']):>9}"
            f"{_cell(s['min']):>8}{_cell(s['max']):>8}"
        )
    return lines


def render(report: dict) -> str:
    total = report["totals"]
    window = report["window"]
    lines = [
        f"Chess.com accuracy - {report['username']}",
        f"Ventana: {window['first']} .. {window['last']} ({window['months']} meses)",
        f"Filtro de ritmo: {report['time_class_filter']}",
        f"Partidas analizadas: {total['games']} - con accuracy: {total['with_accuracy']} "
        f"({total['coverage_pct']:.1f}%)",
        "",
        "Por color",
    ]
    colors = [(("Blancas" if c == "white" else "Negras"), s) for c, s in report["by_color"].items()]
    lines += _table(colors)
    lines += ["", "Por ritmo de juego"]
    rhythms = [(t, s) for t, s in report["by_time_class"].items() if s["games"]]
    lines += _table(rhythms or [("(sin partidas)", total)])
    lines += [
        "",
        "Global",
    ]
    lines += _table([("Global", total)])
    lines += [
        "",
        "Accuracy solo existe en partidas con Game Review publico: las demas",
        "quedan fuera y no se imputan. La cobertura mide ese hueco.",
    ]
    return "\n".join(lines)


# --- main -------------------------------------------------------------------


def build_report(args: argparse.Namespace) -> dict:
    months = cc.iter_months(args.username, args.months)
    games = [
        cc.extract_game(g, args.username)
        for g in cc.iter_games(args.username, args.months, args.refresh)
    ]
    sources = {"public_api": sum(1 for g in games if g["accuracy_source"] == "public-api")}

    csv_info = None
    if args.csv_file:
        csv_info = apply_csv(games, args.csv_file)
        sources["csv"] = csv_info["applied"]

    review_info = None
    if args.game_review:
        cookie = resolve_cookie(args.cookies_file)
        if not cookie:
            raise SystemExit(
                "error: --game-review requiere cookies de sesion; usa --cookies-file "
                "o CHESS_COOKIES (formato Netscape)"
            )
        review_info = fill_from_review(games, cookie, args.review_limit)
        sources["game_review"] = review_info["filled"]

    filtered = [g for g in games if args.time_class == "all" or g["time_class"] == args.time_class]
    summary = summarize(filtered)
    return {
        "username": args.username,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "time_class_filter": args.time_class,
        "window": {
            "months": len(months),
            "first": f"{months[0][0]}-{months[0][1]:02d}" if months else None,
            "last": f"{months[-1][0]}-{months[-1][1]:02d}" if months else None,
        },
        "totals": summary["all"],
        "by_color": summary["by_color"],
        "by_time_class": summary["by_time_class"],
        "coverage": {
            "games": summary["all"]["games"],
            "with_accuracy": summary["all"]["with_accuracy"],
            "coverage_pct": summary["all"]["coverage_pct"],
        },
        "sources": sources,
        "csv": csv_info,
        "game_review": review_info,
        "notes": [
            "accuracy proviene del campo publico `accuracies` del archivo mensual",
            "las partidas sin Game Review publico no aportan dato y no se imputan",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Accuracy historica de una cuenta de Chess.com")
    ap.add_argument("--username", default="foxyxdxb")
    ap.add_argument("--time-class", choices=("all",) + TIME_CLASSES, default="all")
    ap.add_argument("--months", type=int, default=None, help="N meses mas recientes (defecto: todos)")
    ap.add_argument("--csv-file", help="CSV manual game_url,accuracy")
    ap.add_argument("--game-review", action="store_true", help="rellenar huecos via Game Review")
    ap.add_argument("--review-limit", type=int, default=100, help="maximo de Game Reviews por corrida")
    ap.add_argument("--cookies-file", help="cookies Netscape (o CHESS_COOKIES)")
    ap.add_argument("--json", action="store_true", help="volcado JSON estructurado")
    ap.add_argument("--refresh", action="store_true", help="ignorar cache en disco")
    args = ap.parse_args(argv)

    report = build_report(args)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(render(report))
        if report["csv"] and report["csv"]["unmatched"]:
            print(
                f"\nCSV: {report['csv']['rows']} filas, {report['csv']['applied']} aplicadas, "
                f"{len(report['csv']['unmatched'])} sin partida en el historial"
            )
        if report["game_review"]:
            gr = report["game_review"]
            print(f"Game Review: {gr['attempted']} intentos, {gr['filled']} rellenados, {gr['errors']} errores")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
