# Hallazgos empíricos — Chess.com API / accuracy (foxyxdxb)

Medido 2026-11-04 contra la API pública en vivo. Reproducible con
`python3 chess_client.py --username foxyxdxb --all`.

## Cuenta
| campo | valor |
|---|---|
| player_id | 234708507 |
| username | foxyxdxb |
| status | premium |
| joined | 1674975419 → 2023-01-29 UTC |
| last_online | 1793827693 (2026-11-04) |
| country | MX |
| league | Champion |

## Volumen (32 archivos mensuales, 2023-01 … 2026-11)
- 757 partidas totales, todas con `foxyxdxb` como jugador.
- time_class: rapid 730, bullet 13, daily 7, blitz 7.
- Mes máximo: 2026-05 con 107 partidas. Media ≈ 24/mes.
- Mes vacío devuelve `{"games": []}` (12 bytes), HTTP 200.

## Campo `accuracies` — SÍ existe, es parcial
- Presente en el JSON de `/pub/player/<u>/games/<YYYY>/<MM>`:
  `"accuracies": {"white": 39.46, "black": 35.94}` (float, 2 decimales).
- Cobertura global: **156/757 = 20.6 %**. Por periodo: 2026-09..11 = 19/42 (45 %),
  2023-01 = 2/27 (7 %). Crece con la antigüedad reciente.
- Cuando aparece, vienen **siempre ambos lados** (19/19 con clave `white` y `black`).
- Sin marcador previo: no hay flag `reviewed` en el JSON; la única señal es la
  presencia de la clave.
- Distribución (n=156): media 65.00, mediana 65.68, min 11.40, max 99.44.
- No correlaciona con `abandoned` (4 con accuracy / 6 sin), ni con `rated`.

## PGN
- 0/42 PGN inspeccionados contienen "accuracy" en headers o comentarios.
  El PGN solo trae `[%clk]` como comentario. No sirve como fuente de accuracy.

## Game Review / callback
- `GET https://www.chess.com/callback/analysis/game/live/<game_id>`
  → **401** `{"message":"Access not authorized"}` sin cookies (también con
  cookies falsas). Endpoint real, protegido por sesión.
- Rutas alternativas probadas → 404 HTML:
  `/callback/analysis/game/<id>/analysis`, `/callback/game-review/live/<id>`,
  `/callback/library/game/<id>`, `/callback/analysis/live/<id>/review`,
  `/callback/analysis/game/live/<id>/review`.
- `GET https://api.chess.com/pub/game/<uuid>` → 404
  `{"code":0,"message":"Data provider not found..."}`. No existe endpoint público
  por uuid.
- Página `https://www.chess.com/game/live/<id>`: HTTP 200, 103 KB, render en JS;
  el HTML SSR no contiene el valor de accuracy (grep de "39.46" y "accurac*" = 0).

### Mecanismo de cookies (implementado en `game_review()`)
Requiere sesión de chess.com. Exportar cookies en formato Netscape (extensión
tipo "Get cookies.txt") y apuntar `CHESS_COOKIE_FILE=/ruta/cookies.txt`
(o pasar el header en `CHESS_COOKIE`). El cliente filtra por dominio
`.chess.com`, respeta expiración y soporta líneas `#HttpOnly_`.
Sin cookies válidas responde 401; no hay vía anónima.

### Fallback CSV
El export CSV de chess.com ("Download games") exige login y **no incluye
accuracy**: solo headers PGN + resultado. No es alternativa; si se necesita
accuracy de partidas no revisadas, la única vía es cookie de sesión o cálculo
propio con engine sobre el PGN.

## Rate limiting observado
- Sin headers `X-RateLimit-*`; sí `cache-control: public, max-age=5` y ETag.
- 32 requests mensuales consecutivas con 1 s de espaciado: 0 × 429.
- El cliente reintenta en 429/5xx respetando `Retry-After` (backoff 2^n, 5 intentos).
