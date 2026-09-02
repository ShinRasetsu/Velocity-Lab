---
name: perfection-audit
description: Use ONLY when auditing Velocity-Lab or any HUD/telemetry UI for stair-step, jank, or obvious UX regressions — triggers fluidity, interpolation, and perfection gates.
---

# Perfection Audit — Velocity-Lab (Project-Matched, 7 Gates)

Prevents "obvious but overlooked" bugs like KM speed / MAX stairs. This version is tuned to `index.html:1` single-file HUD — no build step — GPS+IMU 60fps `renderLoop`. For generic reuse see `ui-fluidity-audit`.

## When to trigger
- Any edit to `index.html` `<script>` or `<style>` touching live telemetry, gauge, or shell
- Any edit to `sw.js`, `manifest.json`, `tests/`, `.opencode/**`
- Before `git commit`, `git push`, `deploy.bat`, `verify-deploy.ps1`
- User says `/audit`, `audit`, `perfection`, `fluidity`, `stairs`, `jank`, `smooth`

## 7-Gate Flow — must pass in order, no skipping

### Gate 0 — Requirement Trace (2 min)
Map every live DOM id to source Hz. GPS-rate (1-10Hz) must not hit DOM directly.
- Inventory: `speed-display:999`, `max-speed-gauge:1001`, `speed-bar:1005`, `speed-ring:990`, `peak-marker:992`, `dist-display:979`, `session-time:983`, `live-lon-g:1015`, `live-lat-g:1031`, `brake-live:1024`, `accel-fill:1019`, `brake-fill:1028`, `lat-fill:1038`, `g-magnitude-arc:995`, `accuracy-display:958`, `fusion-display:959`, `update-rate:963`, `wake-lock-status:964`, `gnss-alert:972`, `timer-*:1064`, `v-score-*:1051`
- Ask per id: source `watchPosition`/`devicemotion`/`performance.now`? → if GPS-rate and no `display*`/`ui*` interpolator → FAIL.

### Gate 1 — 60fps Fluidity (stair detection) — THE miss
- Rule: no `Geolocation` value directly to DOM. Must `displayX += (target-display)*alpha` or IMU `display+=fused*GRAVITY*dt + (target-display)*corrAlpha` (`index.html:1930`).
- Static bans (FAIL if found):
  - `dom.speed.textContent = (currentSpeedMs*3.6)` → use `displaySpeedMs` (`index.html:1975`)
  - `Math.round(...*100)%` on `accPct/brkPct/latPct` or `frontPos/backPos/rightPos/leftPos` (`index.html:2008-2011`) → `.toFixed(1)` (`index.html:2053`)
  - `(distanceMeters/1000).toFixed` → `displayDistanceM` (`index.html:2039-2053`)
  - `transition: width 75ms` on `speed-bar-fill` (`index.html:642`) → `transition:none` + `will-change` (`index.html:647`)
- Sim: `node tests/fluidity.test.js` 10s 0→100km/h ramp at 1Hz, sample 200ms, FAIL if `minDelta/maxDelta <0.08` or `minDelta<0.4`.

### Gate 2 — Visual Continuity
- `Math.round(displaySpeedKmph)` integer 3-digit `index.html:2043` (0-999, no decimal), bar% `.toFixed(2)` `index.html:2047`, `ringDeg .toFixed(1)` `index.html:2051`, G-bars `.toFixed(1)` `index.html:2121`, G text `.toFixed(2)` `index.html:2060`, peak `.toFixed(1)` `index.html:2131`
- `barPct/ringDeg/peakDeg` from `display*` not `currentSpeedMs`/`maxSpeedKmph` raw (`index.html:1979,1984,2063`)
- `displayMaxKmph` glide `3.2/s` monotonic snap `<0.03` (`index.html:1967`), `displayDistanceM` `+displaySpeedMs*dt` + `0.9/s` corr (`index.html:2039`)

### Gate 3 — Performance / Compositor
- `will-change:width` `contain:paint` `translateZ(0)` on `g-bar-fill:342`, `gauge-ticks:367`, `speed-ring:377`, `g-force-ring:435`, `speed-bar-fill:647-649`
- `prev` diff guard on every DOM write (`setDOM` `index.html:1258` + `prev.speedBar:1981`, `prev.ringDeg:1985`, `prev.distKm:2049`, `prev.accelBar:2056` etc.) — no unconditional write in `renderLoop`
- `dtClamped=min(dt,32)` `dtSec` consistent (`index.html:1921`), no `dt>32` leak
- `document.hidden → throttle 400ms:1887`, `gnssStale → 250ms:2096`

### Gate 4 — Telemetry Correctness (what old audit missed beyond stairs)
- **Timers:** `crossFraction`/`lerp`/`interpolatedLaunchMs` (`index.html:1505-1521`) sub-sample interpolation; `lastTimerSpeedKmh/Dist/TimeMs` state cleared on reset (`index.html:1805`); `updateTimers` must be gated `conf>=GPS_QUALITY_MIN` (`index.html:1696`)
- **Fusion:** `IMU_ALPHA 0.15` adapt `0.08-0.35` (`index.html:1435`), `FUSION_CORRECTION_GAIN 0.35`, `FUSION_GPS_WEIGHT 0.12`, `IMU_BIAS_CLAMP 0.5` (`index.html:1453`), `PHYSICAL_G_CLAMP_LONG 3.5` glitch check (`index.html:1663`), `gpsLongGBuffer` median 5 (`index.html:1669`)
- **Distance:** `>0.5 m/s` gate (`index.html:1672`), Haversine fallback (`index.html:1632`), `glitchCount` inc on `>3.5G` (`index.html:1665`)
- **Scoring:** `calculateVehicleScore` caps `20/10/15/25=70` (`index.html:1486`), `Math.round` per category allowed only there; `evaluateAndRenderScore` on `stateDirty` (`index.html:2087`)
- **Verify:** `node tests/telemetry.test.js` must PASS (and `python tests/tests.py` if python available) — covers `gpsConfidence`, scoring, timer interpolation. No SKIP allowed: if `python` missing, `node tests/telemetry.test.js` is mandatory. `tests/telemetry.test.js` is Node port of `tests.py` via `vm` shim.

### Gate 5 — System & PWA Lifecycle
- PWA: `<link rel="manifest" href="manifest.json":8>`, `theme-color #050505:9`, `apple-touch-icon:17`, `icon-192:16`, `mobile-web-app-capable:12`, `navigator.serviceWorker.register('./sw.js'):2128`
- Install: `beforeinstallprompt` `preventDefault` + `deferredPrompt` + `pwa-install-btn` `display:flex` (`index.html:1390`), `localStorage` for iOS grant `VelocityLab_ios_motion_granted` (`index.html:1052`)
- WakeLock: `navigator.wakeLock.request('screen'):1405`, `visibilitychange` remove/add `devicemotion` (`index.html:1418`), `pagehide` `saveSession` (`index.html:1425`)
- iOS gate: `#ios-gate` dialog `role=dialog` (`index.html:928`), `DeviceMotionEvent.requestPermission` (`index.html:2089`), `USE GPS ONLY` fallback (`index.html:935`), 10s timeout (`index.html:2100`)
- Storage: `STORAGE_KEY VelocityLab_GPS_Telemetry_Data:1096`, `saveSession` on `stateDirty` 2s (`index.html:2087`), `loadSession` 24h expiry (`index.html:1300`), `purgeData`/`resetRun` clear all `display*`/`prev.*` (`index.html:1328,1788`)
- GNSS: `GPS_STALE_MS 30000` → `currentSpeedMs=0` + `GNSS STALE` (`index.html:1889`), `GPS_MAX_DT_SEC 5.0` clamp (`index.html:1621`), `GPS_RETRY_MS` + `restartGPS` (`index.html:1869`), error `ERR: PERMISSION_DENIED/TIMEOUT` (`index.html:1721`), `gnss-alert.active` (`index.html:292,2085`)

### Gate 6 — Design & Layout Perfection
- Gundam system: `--green/amber/red/cyan/purple` (`index.html:107`), `--panel` gradient, `.panel` brackets (`index.html:162`), `.scanlines` `0.12` `pointer-events:none` (`index.html:154`), `.neon-*` shadows (`index.html:94`)
- Viewport: `--scale` `390x844` base, media `(max-width:390)` `calc(100vw/390)` (`index.html:121`), `html font-size calc(16px*var(--scale)):132`, `dashboard-shell` `100svh/100dvh` + `env(safe-area-inset-*)` `0.4rem` (`index.html:189`)
- Gauge: `--gauge clamp(10.5rem,min(70vw,18rem),18rem)` `large 12.5rem` (`index.html:513`), `BAR_MAX_SPEED 200` `zone-60 30%` `zone-100 50%` (`index.html:655`), `redline 306deg` (`index.html:383`), `@property --deg/--front-pos` (`index.html:463`)
- Shell: `stage --gauge` responsive `min-height 620px` clamp `index.html:886`, `tactical 2col` `metric-grid 2col` `hazard-strip` 3px `repeating-linear-gradient` (`index.html:819`), `version-tag` `VER` `index.html:1080`
- No build step: single `index.html` + `sw.js` + `manifest.json` only; `temp.html` not shipped; `verify-deploy.ps1` must PASS if present

### Gate 7 — A11y & Resilience
- `aria-live="polite"` `speed-display:999`, `live-*-g:1015,1024,1031`, `timer-*:1064`, `status-indicator:954` (`index.html:954,999`)
- `aria-label` on `stage:975`, `side-col:976`, `tactical:1043`, `metric-footer:1060`, `ios-gate:928`
- `prefers-reduced-motion: reduce` disables boot `animation`/`transform` only (`index.html:897-919`), never `renderLoop` telemetry (`displaySpeedMs`/`uiG`)
- `prefers-reduced-transparency` disables `text-shadow` (`index.html:892`)
- `focus-visible` outline `var(--green)` (`index.html:54`), `touch-action: pan-y` `overscroll:none` (`index.html:144`), `color-contrast` `clr-*` utilities stable (`index.html:68`)

## How to run
```
/audit              → full 7 gates (0-7)
/audit-fluidity     → Gate 1 only (quick)
/audit-fix          → auditor + auto-fix
Verify: node tests/fluidity.test.js && node tests/telemetry.test.js && pwsh verify-deploy.ps1
# python alternative: python tests/tests.py (same as node telemetry)
```

## Output format
`PASS/FAIL` per gate with `file:line`, FAIL shows before/after snippet + `verify:` cmd. End `Perfection verdict: PASS | FAIL (x stairs, y janks, z telemetry)`.

## Self-check — why stairs missed
- Only `tests/tests.py:116` pure functions, no `renderLoop` fluidity sim
- No lint for `Math.round` bars, `distanceMeters` direct, `75ms` transition
- No telemetry/system/design gates — now added as 4/5/6
Do not mark Gate 1 PASS without `node tests/fluidity.test.js` exit 0.
