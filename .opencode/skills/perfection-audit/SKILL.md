---
name: perfection-audit
description: Use ONLY when auditing Velocity-Lab or any HUD/telemetry UI for stair-step, jank, or obvious UX regressions — triggers fluidity, interpolation, and perfection gates.
---

# Perfection Audit — Velocity-Lab

This skill prevents "obvious but overlooked" UX bugs like the KM speed / MAX stairs.

## When to trigger
- Any edit to `index.html` `<script>` or `<style>` that touches live telemetry (speed, MAX, distance, G, bars, ring)
- Before `git commit`, `git push`, or `deploy.bat`
- When user says /audit, audit, perfection, fluidity, stairs, jank, smooth

## 5-Gate Flow (must pass in order, no skipping)

### Gate 0 — Requirement Trace (2 min)
- Map every live DOM id to source: `speed-display`, `max-speed-gauge`, `speed-bar`, `speed-ring`, `peak-marker`, `dist-display`, `live-lon-g`, `live-lat-g`, `brake-live`, `accel-fill`, `brake-fill`, `lat-fill`, `g-magnitude-arc`
- Ask: "Does this value update at GPS rate (1-10Hz) or at RAF rate (60Hz)?" GPS-rate → FAIL.

### Gate 1 — 60fps Fluidity (stair detection) — THE gate that was missing
- **Rule:** No `Geolocation.watchPosition` value may be assigned directly to DOM. Must go through per-frame interpolator.
- Check pattern `displayX += (target - displayX)*alpha` or IMU dead-reckoning `display += fused*GRAVITY*dt + (target-display)*corrAlpha`
- **Static scan (must fail if found):**
  - `currentSpeedMs = gpsSpeedMs` with direct `dom.speed.textContent = (currentSpeedMs*3.6).toFixed` → FAIL
  - `Math.round(...*100)` on bar widths → FAIL (requires `.toFixed(1)`+)
  - `(distanceMeters/1000).toFixed(2)` on `distDisplay` → FAIL (requires `displayDistanceM` interpolation)
  - `transition: width 75ms` on RAF-driven bars → FAIL (requires `transition:none` + `will-change`)
- **Simulation test:** `node tests/fluidity.test.js` simulates 10s 0→100km/h ramp at 1Hz GPS, samples every 200ms. FAIL if `minDelta/maxDelta < 0.15` (plateau) or `lag > 300ms` at any sample. See `tests/fluidity.test.js:42`.

### Gate 2 — Visual Continuity
- `toFixed(1)` for speed is allowed (0.1km/h), `toFixed(2)` for bar% (0.01%), `toFixed(1)` for `ringDeg` (0.1deg) and G-bars (0.1%), `toFixed(2)` for G text (0.01G)
- `barPct`, `ringDeg`, `peakDeg` must derive from `display*` not `current*` or `maxSpeedKmph` directly
- `displayMaxKmph` must glide `3.2/s` to `maxSpeedKmph`, monotonic, snap `<0.03`

### Gate 3 — Performance / Compositor
- `will-change: width`, `contain: paint`, `transform: translateZ(0)` on `speed-bar-fill`, `g-bar-fill`, `speed-ring`
- `prev` diff guard on every DOM write — no unconditional `textContent` in `renderLoop`
- `dtClamped = min(dt,32)` and `dtSec` used consistently, no `dt` >32 leak
- `if (document.hidden) throttle 400ms` must exist, stale `setTimeout 250ms` must exist

### Gate 4 — Correctness + A11y
- `GPS_STALE_MS`, `GPS_MAX_DT_SEC`, `GPS_ACC_TRUST_*`, `PHYSICAL_G_CLAMP_LONG` unchanged unless justified
- `prefers-reduced-motion` disables boot animations only, not telemetry interpolation
- `aria-live="polite"` on `speed-display`, `live-*-g`, `timer-*`
- `prefers-reduced-transparency` disables `text-shadow`

## How to run
```
/audit                         → full 5 gates
/audit-fluidity                → Gate 1 only (quick)
/audit-fix                     → runs auditor subagent + applies fixes
```

## Output format
Report must be:
- `PASS/FAIL` per gate with file:line
- For FAIL: show before snippet + after fix, and `verify: node tests/fluidity.test.js` result
- End with `Perfection verdict: PASS | FAIL (x stairs, y janks)`

## Self-check — why the stairs were missed
- Old audit only covered `tests/tests.py:116` pure functions, not `renderLoop` fluidity
- No simulation test for GPS→RAF interpolation
- No lint for `Math.round` on bars or direct `distanceMeters` to DOM

This skill closes all three gaps. Do not mark Gate 1 PASS without running `tests/fluidity.test.js`.
