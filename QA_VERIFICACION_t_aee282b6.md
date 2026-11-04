# QA independiente — `chess_accuracy.py` vs `foxyxdxb` (t_aee282b6)

Fecha: 2026-11-04 · Verificador: tester · Entorno: Linux 6.18.35_1, Python 3.14.7, sin credenciales de Chess.com.

## Veredicto: PASS

Las 5 tareas de verificación se ejecutaron contra la API y la web reales de Chess.com.
Todos los números del CLI (global, por color, por ritmo, filtros y cobertura) coinciden
exactamente con un recálculo propio desde 32 archivos mensuales descargados de nuevo
(caché propia, sin importar `chess_client` ni `chess_accuracy`). 26 tests en verde.
Sin fugas de cookies. Dos observaciones no bloqueantes al final.

Artefactos verificados (hashes SHA256 del momento de la prueba):

| Archivo | Bytes | SHA256 |
|---|---|---|
| `chess_accuracy.py` | 11777 | `7652f555ea2d9979fd6435e1bade64047a6692249768a566243521bcf78d8074` |
| `chess_client.py` | 10260 | `98db11c2cb26b9dbb764eebf469faaa49d1b5137abd05ab9720a10f7ee778704` |
| `README.md` | 4526 | `419ed40baf37d4ac14a3c127bdcdbe1acd7abf2ac0edf0a427df16f0fd4e62d4` |

## 1. Ejecución real del CLI

```
$ cd /mnt/datos/proyectos/chess_accuracy && python3 chess_accuracy.py --username foxyxdxb
Chess.com accuracy - foxyxdxb
Ventana: 2023-01 .. 2026-11 (32 meses)
Filtro de ritmo: all
Partidas analizadas: 757 - con accuracy: 156 (20.6%)

Por color
Grupo         Partidas   Con acc  Cobertura    Media  Mediana     Min     Max
-----------------------------------------------------------------------------
Blancas            387        84      21.7%    66.13    65.27   39.12   99.44
Negras             370        72      19.5%    63.70    65.94   11.40   97.27

Por ritmo de juego
Grupo         Partidas   Con acc  Cobertura    Media  Mediana     Min     Max
-----------------------------------------------------------------------------
bullet              13         3      23.1%    50.35    47.90   37.78   65.37
blitz                7         0       0.0%        -        -       -       -
rapid              730       152      20.8%    65.17    65.81   11.40   99.44
daily                7         1      14.3%    84.33    84.33   84.33   84.33

Global
Grupo         Partidas   Con acc  Cobertura    Media  Mediana     Min     Max
-----------------------------------------------------------------------------
Global             757       156      20.6%    65.00    65.68   11.40   99.44
```

- `rc=0`, stderr vacío, 0,123 s en caliente.
- **Corrida en frío** (`CHESS_CACHE_DIR` vacío, 33 peticiones reales): `rc=0`, 32,7 s,
  0 bytes de stderr, 33 archivos de caché; salida **byte a byte idéntica** a la caliente
  (MD5 `7c287403820b9a424234fd58c209d234` en ambas).
- `--time-class {rapid,bullet,daily,blitz}` y `--months 12` ejecutados: `rc=0` en los 4.

## 2. Cotejo empírico contra la web oficial

Superficie usada: `https://www.chess.com/games/archive/foxyxdxb` (historial público,
muestra la accuracy de ambos lados sin sesión). La pestaña Game Review y
`/callback/analysis/game/live/<id>` **exigen sesión** (verificado: HTTP 401, coincide
con lo declarado por la implementación).

Casos testigo (color y valor del lado de `foxyxdxb`):

| Partida | URL | Color (título web) | Web (blancas/negras) | API | Valor que usa el CLI | Δ |
|---|---|---|---|---|---|---|
| 120309015670 | /game/live/120309015670 | blancas («foxyxdxb vs smart-bruv») | 56 / 61.8 | 56 / 61.84 | **56** | 0 |
| 120339727422 | /game/live/120339727422 | negras («palzdra vs foxyxdxb») | 61.2 / 69 | 61.26 / 69 | **69** | 0 |
| 186549921998 | /game/live/186549921998 | blancas | 64.9 / 51.4 | 64.98 / 51.45 | **64.98** | 0,08 |
| 186498984232 | /game/live/186498984232 | negras | 69.6 / 71.4 | 69.7 / 71.47 | **71.47** | 0,07 |

Valor por partida obtenido con `chess_client.extract_game` sobre el JSON oficial (el CLI
solo agrega), y contrastado con el número que muestra la web.

Lote completo (página 1 del historial, 50 partidas):

- 19 partidas con accuracy visible en la web → **38 valores comparados**, **38/38 dentro
  de ≤0,1** de diferencia absoluta (36 < 0,1; 2 exactamente 0,1), media 0,055. Los valores
  web se muestran truncados a 1 decimal y el archivo mensual llega redondeado a 2:
  p. ej. 69,69 → archivo `69.7`, web `69.6`. Ninguna diferencia indica dato distinto.
- **31 partidas sin accuracy en la web y `null` en la API** → la cobertura no imputa.
- **50/50 partidas con el color de `foxyxdxb` correcto** (orden web = blancas, negras).
- 0 ids del API ausentes en la web y 0 filas web sin partida en el API.

Dato adicional: la web muestra «All Games (750)» y el CLI cuenta 757. No es error: 750 =
13 bullet + 7 blitz + 730 rapid; los 7 daily (pestaña aparte en la web) completan 757.

## 3. Validación matemática

Recálculo propio (media = suma/n, mediana = media de los dos centrales ordenados) desde
32 archivos descargados de nuevo; comparado campo a campo con `--json`:

| Grupo | Partidas | Con acc | Cobertura | Media | Mediana | Min | Max | Match |
|---|---|---|---|---|---|---|---|---|
| Global | 757 | 156 | 20,6 % | 65,00 | 65,68 | 11,40 | 99,44 | OK |
| Blancas | 387 | 84 | 21,7 % | 66,13 | 65,27 | 39,12 | 99,44 | OK |
| Negras | 370 | 72 | 19,5 % | 63,70 | 65,94 | 11,40 | 97,27 | OK |
| bullet | 13 | 3 | 23,1 % | 50,35 | 47,90 | 37,78 | 65,37 | OK |
| blitz | 7 | 0 | 0,0 % | — | — | — | — | OK |
| rapid | 730 | 152 | 20,8 % | 65,17 | 65,81 | 11,40 | 99,44 | OK |
| daily | 7 | 1 | 14,3 % | 84,33 | 84,33 | 84,33 | 84,33 | OK |
| `--time-class rapid` | 730 | 152 | 20,8 % | 65,17 | 65,81 | — | — | OK |
| `--time-class bullet` | 13 | 3 | 23,1 % | 50,35 | 47,90 | — | — | OK |
| `--time-class daily` | 7 | 1 | 14,3 % | 84,33 | 84,33 | — | — | OK |
| `--time-class blitz` | 7 | 0 | 0,0 % | — | — | — | — | OK |
| `--months 12` (2025-08..2026-11) | 389 | 92 | 23,7 % | 65,62 | — | — | — | OK |

Cobertura y conteos honestos:

- 387+370 = 757 partidas y 84+72 = 156 con dato; 13+7+730+7 = 757 y 3+0+152+1 = 156.
- `totals.with_accuracy` = `coverage.with_accuracy` = `sources.public_api` = 156.
- Ninguna partida sin dato entra en media/mediana; 0 partidas con `accuracies` parcial
  (dict presente pero sin el lado de la cuenta), así que `sources.public_api` no infla.
- **Valores enteros incluidos**: el JSON oficial trae 3 accuracies del lado de la cuenta
  como `int` (56, 69, 61; partidas 120309015670, 120339727422, 168297384828). El recálculo
  incluyéndolos reproduce la media 65,00 exacta → no se pierden por filtro float-only.
- 0 valores fuera de 0..100; 0 partidas sin color asignado (757/757 resueltas).

## 4. Seguridad de credenciales y formato

Canario sintético `PHPSESSID=QA_LEAK_CANARY_a7f3e9d1` (nunca una cookie real):

| Prueba | Resultado |
|---|---|
| `--cookies-file` con permisos 0644 + `--game-review` (2 intentos, 401 reales) | `rc=0`; aviso a stderr `es legible por otros usuarios; usa chmod 600`; **0** ocurrencias del canario en stdout/stderr |
| mismo archivo con `chmod 600` | stderr 0 bytes (sin aviso) |
| `CHESS_COOKIES` con el header en crudo | `rc=0`; **0** ocurrencias en stdout/stderr |
| `--json` con el header en crudo en el entorno | `rc=0`; **0** ocurrencias; claves: `by_color, by_time_class, coverage, csv, game_review, generated_at, notes, sources, time_class_filter, totals, username, window` — sin campos de cookie |
| Persistencia: grep del canario en `CHESS_CACHE_DIR`, `~/.cache/chess_accuracy` y el repo | **0 archivos** |
| `--game-review` sin cookies | `rc=1` con `error: --game-review requiere cookies de sesion; usa --cookies-file o CHESS_COOKIES (formato Netscape)` (nombra la fuente, no el valor) |

CSV manual (controles propios): `manual.csv` con 1 fila válida, 1 id inexistente, 1 fila
`abc` y 1 valor `700` → `rows=2, applied=1, unmatched=['999999999999']`,
`sources={'public_api':156,'csv':1}`, media 65,00 → 65,09. Fuera de rango y no numéricos
descartados; sobrescritura del valor de API confirmada (56 → 70).

## 5. README

Contiene uso de todos los flags, qué mide (media/mediana/cobertura), **qué queda fuera**
(Game Review público: 156/757 = 20,6 %, sin imputación, «un 20,6 % de cobertura no es una
media de las 757 partidas»), guía de cookies Netscape + `chmod 600`, formato CSV y su regla
de sobrescritura, esquema `--json`, caché/TTL y comando de tests. Cifras del README
contrastadas contra la corrida real: 156/757, 730 rapid, 13 bullet, 7 daily, 7 blitz → OK.
Límite declarado correctamente: el payload de Game Review no está verificado
empíricamente (sin sesión no se pudo comprobar).

## Observaciones no bloqueantes

1. **Etiqueta de ventana** (`LOW`): `Ventana: 2023-01 .. 2026-11 (32 meses)` — son 32
   archivos mensuales sobre un lapso de **47 meses** con 15 huecos (2023-06, 2023-07,
   2023-10..12, 2024-02, 2024-04, 2024-06..09, 2025-09..11, 2026-01). El número es el
   conteo de archivos, no meses contiguos; no afecta ninguna métrica. `window.months`
   del JSON hereda la misma ambigüedad.
2. **`--months 0`** (`LOW`): `parsed[-0:]` devuelve todos los meses (757 partidas) en vez
   de 0 o error. Sin impacto en el uso documentado (`--months N`, N≥1).

## Cobertura residual / riesgos declarados

- El cotejo con la web usó la **página pública de historial** (50 partidas, 38 valores) y
  4 casos testigo; no se recorrieron las 15 páginas del historial completo.
- La pestaña Game Review y el callback de análisis requieren sesión: **no** se validó el
  shape real del payload de Game Review ni `--game-review` con cookies válidas (no había
  credenciales y no se usaron). Queda como limitación ya declarada por la implementación.
- La tercera partida con accuracy entera (168297384828, `61`) no se localizó en las
  páginas 4, 5, 9 y 10 del historial público; su inclusión en las métricas sí está
  demostrada por el recálculo (que la cuenta) y por el match exacto de la media global.
- Solo se probó la cuenta `foxyxdxb`; no se ejercitó otro usuario ni el caso de cuenta
  inexistente.

## Comandos ejecutados (resumen)

```bash
python3 chess_accuracy.py --username foxyxdxb                       # rc=0, 757/156
CHESS_CACHE_DIR=<vacia> python3 chess_accuracy.py --username foxyxdxb  # frío 32,7 s, rc=0
python3 chess_accuracy.py --time-class rapid|bullet|daily|blitz --json # rc=0
python3 chess_accuracy.py --months 12 --json                        # rc=0 (389/92)
python3 chess_accuracy.py --csv-file manual.csv --json              # rc=0
python3 chess_accuracy.py --game-review --cookies-file <0644>       # rc=0, aviso de permisos
CHESS_COOKIES='PHPSESSID=QA_LEAK_CANARY_...' python3 chess_accuracy.py --json  # 0 fugas
python3 -m unittest test_chess_accuracy test_chess_client           # Ran 26 tests, OK
python3 verify.py   # descarga independiente de 32 archivos mensuales + recálculo propio
```
