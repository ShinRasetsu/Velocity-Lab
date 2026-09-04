---
name: perfection-audit
description: Use ONLY when auditing Velocity-Lab or any HUD/telemetry UI for stair-step, jank, or obvious UX regressions — triggers fluidity, interpolation, and perfection gates.
---

# Perfection Audit — Velocity-Lab (Project-Matched, 9 Gates)

Prevents "obvious but overlooked" bugs like KM speed / MAX stairs. This version is tuned to `index.html:1` single-file HUD — no build step — GPS+IMU 60fps `renderLoop`. For generic reuse see `ui-fluidity-audit`. Gate 8 is live Playwright, Gate 9 is optimization/feature/accuracy suggestions.

## When to trigger
- Any edit to `index.html` `<script>` or `<style>` touching live telemetry, gauge, or shell
- Any edit to `sw.js`, `manifest.json`, `tests/`, `.opencode/**`
- Before `git commit`, `git push`, `deploy.bat`, `verify-deploy.ps1`
- User says `/audit`, `audit`, `perfection`, `fluidity`, `stairs`, `jank`, `smooth`

## 9-Gate Flow — must pass in order, no skipping (Gate 8 live only if MCPs available, Gate 9 advisory)

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
- GNSS: `GPS_STALE_MS 8000` → hold + `GNSS COAST` if IMU <20 s else `currentSpeedMs=0` + `GNSS STALE` (`index.html:1889`); tiers `FIX/WEAK/COAST/STALE` by `lastGpsConfidence>=MIN`; weak fixes (`!trustSpeed && conf<MIN`) refresh anchor only, never speed/distance/fusion/heading; retry skips if fixes resumed <4 s, `GPS_MAX_DT_SEC 5.0` clamp (`index.html:1621`), `GPS_RETRY_MS` + `restartGPS` (`index.html:1869`), error `ERR: PERMISSION_DENIED/TIMEOUT` (`index.html:1721`), `gnss-alert.active` (`index.html:292,2085`)

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

### Gate 8 — Live Tools (must use MCPs if `opencode.json:6` enabled — finds faults static can't)
- **Playwright** `mcp.playwright` — **must run**: `browser_navigate` `file://.../index.html` + `https://shinrasetsu.github.io/Velocity-Lab/index.html` `index.html:8` must both `title: Velocity-Lab Telemetry` `index.html:6` else FAIL; `browser_snapshot` must show `speed-display` `0` integer + `hasBestMarker` + no `#text-scale-btn` (auto-scale only) else FAIL; `browser_evaluate` must confirm computed `--text-scale` follows viewport (`390px→1.15`, `≥600px→1.3`, `index.html:133`) with no inline override, and `speedBarTransition:none` + `will-change:width` + `sw.controller` true else FAIL; `browser_take_screenshot` `390×844` + `929×861` must show `panel:169` brackets + `hazard:819` + `scanlines:154` else FAIL; offline `page.route` abort → must still render `appShellStrategy:99` else FAIL. If MCP enabled but not called → FAIL Gate 8.
- **Figma** `mcp.figma` `FIGMA_KEY` — **must run** if `FIGMA_FILE_KEY` set: `get_design`/`get_code` → tokens `--green/amber/red/cyan/purple:107-113`, `--panel:114`, `--gauge clamp:540`, `panel brackets:169`, `neon-* :94` must exactly match `index.html` — drift `>2%` → FAIL `file:line` diff; if no `FIGMA_FILE_KEY`, `SKIP` with `set FIGMA_FILE_KEY` hint.
- **Chrome-DevTools** `mcp.chrome-devtools` — **must run**: `performance_start` → reload → `performance_stop` → `hud-boot 0.28s:553` must `<400ms` and `will-change:342,647` layer count `<12` and `CLS <0.05` else FAIL. If MCP not installed, `SKIP` does not fail 0-7, but enabled MCP not used → FAIL.
- **Cross-check `ui-fluidity-audit`**: load `ui-fluidity-audit` skill, run its generic Gate 1 sim with project `liveIds` from `audit.config.json` (or `index.html:958-1051` inventory) — generic ratio must also `≥0.08` else FAIL. This catches faults `perfection-audit` project-specific regex misses.

## Reference Library — HUDs, Motion, HIG+APCA (for Gate 6/3/7)
- **HUDs:** `Garmin G3X` (glass avionics `--panel:114` `scanlines:154`), `AIM Solo 2` (track `timer-*:1064` `crossFraction:1505`), `MoTeC C125` (motorsport `--gauge clamp:540` `redline 306deg:383`), `F1 23`/`Gran Turismo 7` (telemetry `g-force-ring:435` `4-quadrant` `g-dot:730` trail)
- **Motion:** `Framer Motion` `spring 500/30, damping 30` → `g-force-boot 0.8s:516` `spring(0.34,1.56)` + `hud-boot 0.28s:553` `spring`, `Lottie` `0-199` `2289` RPM sweep `32ms` `42/step`
- **HIG+APCA:** `Apple HIG` `44pt` min `action-btn:44` `0.38×0.95rem` + `brand-mark:249` `1.15rem`, `WCAG APCA 70` vs `prefers-contrast:930` `--line 0.55` `APCA 62→75` `clr-* :68`

## How to run
```
/audit              → full 9 gates (0-9, 8 live if MCPs available, 9 advisory)
/audit-fluidity     → Gate 1 only (quick)
/audit-fix          → auditor + auto-fix
Verify: node tests/fluidity.test.js && node tests/telemetry.test.js && pwsh verify-deploy.ps1
# python alternative: python tests/tests.py (same as node telemetry)
# live: playwright → browser_navigate file://index.html + https://shinrasetsu.github.io/Velocity-Lab/index.html
#       figma → get_design FIGMA_FILE_KEY + compare tokens 107-113,540,169
#       chrome-devtools → performance_start + check hud-boot <400ms
# refs: compare index.html tokens 107-113,540,169,154,94 vs Garage/F1/MoTeC Figma, motion spring, HIG 44pt, APCA 70
```

## Output format
`PASS/FAIL` per gate with `file:line`, FAIL shows before/after snippet + `verify:` cmd. Then a **Recommendations** list (ranked, every run): `priority P0-P2` + `impact` + `effort Low/Med` + `file:line` + one-line fix. End `Perfection verdict: PASS | FAIL (x stairs, y janks, z telemetry)`.

## Advisory — UI Polish (always output, non-blocking, to catch improvements)
Even if 0-8 PASS, auditor must suggest 2-3 lively/sharp/contrast wins: e.g., `scanlines:154` static → pulse `0.12→0.18` at 3s, `neon-* :94` `text-shadow 10px` → add `pulse 2s` on `peak-marker:390`, `hud-boot 0.28s:553` could use `spring(stiffness 500)` via `chrome-devtools` + `Figma` lively `g-force-ring 0.8s`, `prefers-contrast:more:903` `--line 0.40` could be `0.55` for sharp. List as `SUGGEST` not FAIL.

### Gate 9 — Optimization & Feature & Accuracy (Advisory, must output ranked Recommendations even if PASS)
- **Optimization:** `saveSession` idle cadence (`index.html:2240` — done 1.5s+idle), `sw.js:76` `MAX_RUNTIME` (done 100), `will-change` layers (`index.html:361` — done), font load (`index.html:20` `display=optional` vs self-host `woff2`), `peak-pulse` box-shadow paint (`index.html:419`), dead per-frame `emX/emY` (removed)
- **Accuracy:** `GPS_STALE_MS` (`index.html:1145` — done 8000), `GPS_ACC_TRUST 4-25m` + L5/barometer altitude, `FUSION_GPS_WEIGHT` adapt >5Hz (`index.html:1550` — done), `crossFraction` linear vs quadratic (`index.html:1602`), creep gate (`index.html:1760` — done 0.3 high-conf)
- **Features/UI:** timer ghost best (`index.html:1114` — done `BEST_KEY`), text-scale fully auto via media (`index.html:133` — button removed), landscape grid (done `orientation: landscape`), iOS re-ask expiry (`index.html:2216`), `manifest.json` shortcuts/share_target, HIG 44pt touch (`index.html:44`)
- Rank every item `P0 (bug/risk) / P1 (real win) / P2 (polish)` with `impact` + `effort Low/Med` + `file:line`. Skip items already implemented; never re-suggest done work.

## Self-check — why stairs missed
- Only `tests/tests.py:116` pure functions, no `renderLoop` fluidity sim
- No lint for `Math.round` bars, `distanceMeters` direct, `75ms` transition
- No telemetry/system/design gates — now added as 4/5/6
Do not mark Gate 1 PASS without `node tests/fluidity.test.js` exit 0.
