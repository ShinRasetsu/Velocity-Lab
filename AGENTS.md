# Velocity-Lab — Agent Instructions

## Project
Single-file HUD: `index.html` (telemetry), `sw.js`, `manifest.json`. No build step. GPS + IMU fusion, 60fps `renderLoop`.

## Perfection Bar
Every live value at 60Hz, never GPS-rate stairs. See `.opencode/skills/perfection-audit/SKILL.md` 5 gates.

## Before every commit / push
1. `node tests/fluidity.test.js` must PASS (Gate 1). No bypass.
2. `/audit` or `/audit-fluidity` must show `Perfection verdict: PASS`.
3. If you touched `index.html` live telemetry, run perfection-auditor subagent.

## Hard Rules
- Never assign `Geolocation.watchPosition` value directly to DOM. Use `display*` interpolator per frame.
- Bars: `.toFixed(1)` not `Math.round`, `speed-bar` `transition:none`.
- Distance/MAX must interpolate (`displayDistanceM`, `displayMaxKmph`), not raw.
- `prev` diff guard on every DOM write in `renderLoop`.
- `prefers-reduced-motion` disables boot only, not telemetry.

## Restart
After editing `opencode.json` or `.opencode/**`, restart opencode.
