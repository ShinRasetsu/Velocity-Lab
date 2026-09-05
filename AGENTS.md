# Velocity-Lab — Agent Instructions

## Project
Single-file HUD: `index.html` (telemetry), `sw.js`, `manifest.json`. No build step. GPS + IMU fusion, 60fps `renderLoop`.

## Perfection Bar
Every live value at 60Hz, never GPS-rate stairs. See `.opencode/skills/perfection-audit/SKILL.md` 9 gates (project-matched, Gate 8 live Playwright, Gate 9 optimization advisory).

## Before every commit / push
1. `node tests/fluidity.test.js` must PASS (Gate 1) + `node tests/telemetry.test.js` must PASS (Gate 4) — `python tests/tests.py` is equivalent fallback.
2. `/audit` must show `Perfection verdict: PASS` (all 9 gates, Gate 8 SKIP allowed if no playwright, Gate 9 is SUGGEST). `/audit-fluidity` for quick Gate 1.
3. If you touched `index.html`/`sw.js`/`manifest.json`, run perfection-auditor subagent.

## Hard Rules
- Never assign `Geolocation.watchPosition` value directly to DOM. Use `display*` interpolator per frame (`index.html:2043`).
- Speed: `Math.round(displaySpeedKmph)` integer 3-digit (0-999, no decimal) — `index.html:2043`; Bars: `.toFixed(1)` not `Math.round` (`index.html:2121`), `speed-bar` `transition:none` (`index.html:647`).
- Distance/MAX must interpolate (`displayDistanceM:2039`, `displayMaxKmph:1967`), not raw.
- Timers must use `crossFraction`/`lerp` sub-sample (`index.html:1505`), gated `conf>=GPS_QUALITY_MIN` (`index.html:1696`).
- Speed estimator: Doppler trusted else `lsVelocity` 3 s/12 window (1/acc²) + 1D Kalman (adaptive `Q`, accuracy-weighted `R`); NIS gate + slew-limit ±3.5G·dt (always advances), outlier-time (≥4 s) single-delta re-acquire, window eviction — no median buffer.
- Weak fixes (`!trustSpeed && conf<MIN`) refresh anchor only — never speed/distance/fusion/heading; status tiers `FIX/WEAK/COAST/STALE`, IMU coasts <20 s with zero GPS correction; `lastUsableGpsTime` gates coast, held target bleeds after 10 s weak-only (never pins); gap quarantine holds speed one fix (Doppler bypasses).
- `prev` diff guard on every DOM write, `dtClamped 32` (`index.html:1921`), `will-change/contain` (`index.html:647`).
- `prefers-reduced-motion` disables boot only, not telemetry (`index.html:897`).

## Restart
After editing `opencode.json` or `.opencode/**`, restart opencode.
