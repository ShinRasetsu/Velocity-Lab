# Velocity-Lab — Agent Instructions

## Project
Single-file HUD: `index.html` (telemetry), `sw.js`, `manifest.json`. No build step. GPS + IMU fusion, 60fps `renderLoop`.

## Perfection Bar
Every live value at 60Hz, never GPS-rate stairs. See `.opencode/skills/perfection-audit/SKILL.md` 7 gates (project-matched).

## Before every commit / push
1. `node tests/fluidity.test.js` must PASS (Gate 1) + `node tests/telemetry.test.js` must PASS (Gate 4) — `python tests/tests.py` is equivalent fallback.
2. `/audit` must show `Perfection verdict: PASS` (all 7 gates, zero SKIP). `/audit-fluidity` for quick Gate 1.
3. If you touched `index.html`/`sw.js`/`manifest.json`, run perfection-auditor subagent.

## Hard Rules
- Never assign `Geolocation.watchPosition` value directly to DOM. Use `display*` interpolator per frame (`index.html:1975`).
- Bars: `.toFixed(1)` not `Math.round` (`index.html:2053`), `speed-bar` `transition:none` (`index.html:647`).
- Distance/MAX must interpolate (`displayDistanceM:2039`, `displayMaxKmph:1967`), not raw.
- Timers must use `crossFraction`/`lerp` sub-sample (`index.html:1505`), gated `conf>=GPS_QUALITY_MIN` (`index.html:1696`).
- `prev` diff guard on every DOM write, `dtClamped 32` (`index.html:1921`), `will-change/contain` (`index.html:647`).
- `prefers-reduced-motion` disables boot only, not telemetry (`index.html:897`).

## Restart
After editing `opencode.json` or `.opencode/**`, restart opencode.
