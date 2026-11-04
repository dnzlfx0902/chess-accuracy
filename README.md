# chess_accuracy

Precisión (accuracy) histórica de una cuenta de Chess.com calculada desde datos
reales de la API pública, con desglose por color y ritmo y cobertura explícita.

## Uso

```bash
python3 chess_accuracy.py                          # foxyxdxb, todo el historial
python3 chess_accuracy.py --username foxyxdxb
python3 chess_accuracy.py --time-class rapid       # all|bullet|blitz|rapid|daily
python3 chess_accuracy.py --months 12              # últimos 12 meses
python3 chess_accuracy.py --json                   # volcado estructurado
python3 chess_accuracy.py --csv-file manual.csv    # completar con datos propios
python3 chess_accuracy.py --game-review --cookies-file cookies.txt
python3 chess_accuracy.py --refresh                # ignora la caché en disco
```

Sin dependencias externas: solo stdlib de Python 3.10+.

## Qué mide

- **Media aritmética y mediana** de accuracy: global, por color (blancas/negras)
  y por ritmo de juego (bullet, blitz, rapid, daily).
- **Cobertura**: partidas con dato de accuracy vs partidas analizadas, en número
  y porcentaje, por grupo y global.
- El valor de accuracy es el del color con el que jugó la cuenta consultada; el
  JSON de Chess.com trae ambos lados (`accuracies.white` y `accuracies.black`).

## Qué queda fuera

Chess.com publica `accuracies` **solo** en partidas con Game Review público. En
`foxyxdxb` son 156 de 757 (20,6 %): 730 rapid, 13 bullet, 7 daily, 7 blitz. Las
partidas sin Game Review no aportan dato y **no se imputan**: la media se calcula
únicamente sobre las que tienen valor, y la cobertura muestra el hueco.

Consecuencia práctica: las métricas describen el subconjunto revisado, no todo el
historial. Un 20,6 % de cobertura no es una media de las 757 partidas.

El PGN descargable tampoco trae accuracy (0/42 comprobadas) y el export CSV de
Chess.com no la incluye. Detalle medido en `FINDINGS.md`.

## Completar la cobertura

### 1. Game Review con cookies de sesión

`GET https://www.chess.com/callback/analysis/game/live/<id>` responde
`401 Access not authorized` sin sesión. Para usarlo:

1. Exporta las cookies de `chess.com` en formato **Netscape** (`cookies.txt`),
   p. ej. con la extensión "Get cookies.txt LOCALLY" estando logueado.
2. `chmod 600 cookies.txt` (el CLI avisa si es legible por otros usuarios).
3. Ejecuta:

```bash
export CHESS_COOKIES=/ruta/cookies.txt       # o --cookies-file /ruta/cookies.txt
python3 chess_accuracy.py --game-review --review-limit 50
```

`--review-limit` acota cuántas partidas se piden por corrida (por defecto 100);
el cliente espacia 1 s entre peticiones. El formato del payload de Game Review no
está verificado empíricamente (requiere sesión), por lo que el extractor solo
acepta formas explícitas y descarta el resto antes que adivinar el color.

Las cookies **nunca** se imprimen, loguean, escriben en caché ni aparecen en
`--json`; solo se usan como header HTTP. Los mensajes de error nombran la fuente,
no el valor.

### 2. CSV manual

Formato `game_url,accuracy`, con cabecera opcional:

```csv
game_url,accuracy
https://www.chess.com/game/live/173859834546,55.55
https://www.chess.com/game/live/173859834547,61.2
```

```bash
python3 chess_accuracy.py --csv-file manual.csv
```

Las filas se cruzan por id de partida y **sobrescriben** el valor de la API; las
filas cuyo id no existe en el historial se cuentan al final como "sin partida en
el historial" y no alteran las métricas. Valores fuera de `0..100` y filas
inválidas se descartan.

## Salida `--json`

```json
{
  "username": "foxyxdxb",
  "time_class_filter": "all",
  "window": {"months": 32, "first": "2023-01", "last": "2026-11"},
  "totals": {"games": 757, "with_accuracy": 156, "coverage_pct": 20.6,
             "mean": 65.0, "median": 65.68, "min": 11.4, "max": 99.44},
  "by_color": {"white": {...}, "black": {...}},
  "by_time_class": {"bullet": {...}, "blitz": {...}, "rapid": {...}, "daily": {...}},
  "coverage": {"games": 757, "with_accuracy": 156, "coverage_pct": 20.6},
  "sources": {"public_api": 156},
  "csv": null,
  "game_review": null
}
```

## Caché

`~/.cache/chess_accuracy` (override con `CHESS_CACHE_DIR`). Los meses cerrados
son inmutables, el mes en curso caduca a las 6 h y `player`/`stats` a la hora.
Una corrida en frío son ~32 peticiones (~33 s a 1 s/petición); en caliente,
~0,1 s sin red.

## Tests

```bash
python3 -m unittest test_chess_accuracy test_chess_client
```

26 tests offline (estadística, CSV, cookies, payloads y CLI con datos sintéticos).
