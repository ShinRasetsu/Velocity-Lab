# Velocity-Lab — Agent Instructions

## Project
Single-file HUD: `index.html` (telemetry), `sw.js`, `manifest.json`. No build step. GPS + IMU fusion, 60fps `renderLoop`.

## MCP Stack — Source of Truth (all sessions, never remove)

Single source of truth for the MCP tool stack. Config: `opencode.json` `mcp` block, mirrored in `~/.config/opencode/opencode.jsonc` — keep both configs + this table in sync on any change. Never remove, rename, or disable these servers.

| Job | Server key (package) | Why | Needs |
| --- | --- | --- | --- |
| Live library docs | `context7` (`@upstash/context7-mcp`) | MapLibre, Leaflet, vis.gl, geomagnetism — stops hallucinated APIs | `CONTEXT7_API_KEY` env optional |
| Specs | `w3c` (`@shuji-bonji/w3c-mcp`) | Service Worker, Web App Manifest, Sensor / Device Orientation — W3C/WHATWG/IETF specs, WebIDL, `get_pwa_specs` | — |
| Code quality | `eslint` (`@eslint/mcp`) | In-session lint of HUD JS — unsafe/broken patterns caught pre-runtime | — |
| PWA audit | `lighthouse` (`@danielsogl/lighthouse-mcp`) | Installability, HTTPS, SW — not sensors | Chrome; `CHROME_PATH` if nonstandard |
| Device QA | `chrome-devtools` (`chrome-devtools-mcp`) | GPS emulation, sensors, Permissions-Policy | — |
| Tiles / routing | `osrm` (`@pipeworx/mcp-osrm`) + `openstreetmap` (`@cyanheads/openstreetmap-mcp-server`) | OSRM demo routing, Nominatim geocode + Overpass — Backend only. Do not put compass on a server | — |
| Places (optional) | `google-maps` (`google-maps-mcp-server`) + `geoapify` (`@pipeworx/mcp-geoapify`) | Geocode/places. Heading still local | `GOOGLE_MAPS_API_KEY` env; Geoapify key passed per call as `_apiKey` |

- All `type: "local"` stdio via `npx -y`. `playwright` (Gate 8) and `github` in `opencode.json` stay too.
- Heading/compass/fusion is always local (`index.html`) — these MCPs are reference/QA/backend only, never HUD runtime deps.

### MCP usage policy (best-use per server)
- `context7`: resolve docs before ANY unfamiliar web API or lib call (Wake Lock, Sensors, Notification…), not just the 4 geo libs.
- `w3c`: conformance reference set = `geolocation`, `permissions`, `permissions-policy`, `csp`, `screen-wake-lock`, `generic-sensor`, `deviceorientation` + SW/Manifest/PWA. Consult before touching sensor/permission/CSP code.
- `lighthouse` = full scorecard incl. Performance; `chrome-devtools` = raw traces + device emulation (its built-in Lighthouse excludes perf). No overlap waste.
- `eslint`: lint before commits (inline JS via extraction or `eslint-plugin-html`).
- `osrm` + `openstreetmap` + `geoapify` = **QA fixture generators**: `osrm_route` road geometry → noisy 1Hz synthetic trace → `osrm_match` sanity → inject via chrome-devtools GPS emulation → verify FIX/WEAK/COAST/STALE, estimator arbitration, coasting. Never app runtime.
- **Drive-fixture pipeline (proven 2026-10)**: `node tests/fixtures/gen-drive.js` regenerates `urban-drive.csv/.json` from pinned OSRM geometry (seed 1337; weak/canyon/outage phases baked in). Offline gate: `node tests/replay.js tests/fixtures/urban-drive.csv --report` (verdict must be OK). Live QA: chrome-devtools `navigate_page` with `initScript` fake-geolocation replaying the JSON (see gen-drive.js header) — status tiers must transition FIX→STALE→WEAK per fusion spec. `osrm_match` sanity is optional (demo server caps `/match` near zero).

## Perfection Bar
Every live value at 60Hz, never GPS-rate stairs. See `.opencode/skills/perfection-audit/SKILL.md` 9 gates (project-matched, Gate 8 live Playwright, Gate 9 optimization advisory).

## Before every commit / push
1. `node tests/fluidity.test.js` must PASS (Gate 1) + `node tests/telemetry.test.js` must PASS (Gate 4) + `node tests/layout.test.js` must PASS (Gate 6) + `node tests/csp.test.js` must PASS (CSP hash freshness) — `python tests/tests.py` is equivalent fallback.
2. `/audit` must show `Perfection verdict: PASS` (all 9 gates, Gate 8 SKIP allowed if no playwright, Gate 9 is SUGGEST). `/audit-fluidity` for quick Gate 1.
3. If you touched `index.html`/`sw.js`/`manifest.json`, run perfection-auditor subagent.

## Hard Rules
- Never assign `Geolocation.watchPosition` value directly to DOM. Use `display*` interpolator per frame (`index.html:2043`).
- Speed: `Math.round(displaySpeedKmph)` integer 3-digit (0-999, no decimal) — `index.html:2043`; Bars: `.toFixed(1)` not `Math.round` (`index.html:2121`), `speed-bar` `transition:none` (`index.html:647`).
- Distance/MAX must interpolate (`displayDistanceM:2039`, `displayMaxKmph:1967`), not raw.
- Timers must use `crossFraction`/`lerp` sub-sample (`index.html:1505`), gated `conf>=GPS_QUALITY_MIN` (`index.html:1696`).
- Speed estimator: Doppler trusted else `lsVelocity` 3 s/12 window (1/acc²) + 1D Kalman (adaptive `Q` `Q0 0.7 IMU / 2.2 GPS`, accuracy-weighted `R` `R_MAX 60`); NIS gate + slew-limit car-envelope (always advances), outlier-time (≥4 s) filtered-vMeas re-acquire (never raw single-delta), window eviction — no median buffer; IMU data older than 1 s never predicts, coasts, or tares.
- Weak fixes (`!trustSpeed && conf<MIN`) refresh anchor only — never speed/distance/fusion/heading; status tiers `FIX/WEAK/COAST/STALE`, IMU coasts <20 s with zero GPS correction; `lastUsableGpsTime` gates coast, held target bleeds after 10 s weak-only (never pins); gap quarantine holds speed one fix (Doppler bypasses).
- `prev` diff guard on every DOM write, `dtClamped 32` (`index.html:1921`), `will-change/contain` (`index.html:647`).
- `prefers-reduced-motion` disables boot only, not telemetry (`index.html:897`).
- CSP meta in `index.html` carries `'sha256-…'` hashes of inline scripts — after ANY script edit run `node tests/csp.test.js --fix` or the CSP gate fails.
- Zero remote fetches: fonts are vendored in `fonts/` (no CDN). If a new external resource is ever added, CSP meta + `sw.js` CDN branch must be updated with it — default answer is: vendor it.

## Restart
After editing `opencode.json` or `.opencode/**`, restart opencode.
