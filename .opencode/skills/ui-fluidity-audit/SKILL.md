---
name: ui-fluidity-audit
description: Use ONLY when auditing any live UI (HUD, telemetry, dashboard, sensor, polling) for stair-step, jank, or 60fps regressions — generic fluidity gates.
---

# UI Fluidity Audit — Generic (reuse in any project)

Drop-in for any project with live values that update slower than render rate. Velocity-Lab is the reference implementation.

## When to trigger
- Any edit to a live value: sensor, GPS, websocket, polling, animation frame
- Before `git commit/push` touching UI
- User says /audit, fluidity, stairs, jank, smooth, 60fps

## Config — define once per project (`audit.config.json` or top of SKILL.md)
```json
{
  "liveIds": ["speed-display", "max-speed", "distance", "g-x", "g-y"],
  "sourceRateHz": 1,
  "renderRateHz": 60,
  "interpolators": ["displaySpeed", "displayMax", "displayDistance"],
  "barIds": ["speed-bar", "g-bar"]
}
```
If no config, Gate 0 inventories: grep `getElementById`, `textContent`, `style.width`, `watchPosition`, `setInterval`, `websocket.onmessage`.

## 5-Gate Flow (generic)

### Gate 0 — Inventory
- List every live DOM write in `requestAnimationFrame`/`renderLoop` vs low-freq callback (`watchPosition`, `fetch`, `setInterval <30Hz`, `onmessage`)
- Question: source Hz vs render Hz? If source < render and no interpolator → FAIL.

### Gate 1 — Fluidity (stair detection) — core gate
- Rule: never `lowFreqValue → DOM` directly. Must `display += (target-display)*alpha` or `display += velocity*dt + (target-display)*corrAlpha` (dead-reckoning).
- Static bans (project must adapt names):
  - `target = lowFreq; dom.x.textContent = target.toFixed` → FAIL
  - `Math.round(*100)%` on continuous bars → FAIL (require `.toFixed(1)`+)
  - `rawDistance.toFixed` without `displayDistance` → FAIL
  - `transition: width 75ms` on RAF-driven bars → FAIL (`transition:none` + `will-change`)
- Simulation: `node tests/ui-fluidity.test.js` — 10s ramp at `sourceRateHz`, sample every 200ms, FAIL if `minDelta/maxDelta < 0.08` (plateau) or `lag > 300ms`.

### Gate 2 — Visual Continuity
- Fractional precision: speed `.toFixed(1)` (0.1), bar `%` `.toFixed(1-2)`, angle `.toFixed(1)`, G `.toFixed(2)` — no integer quant
- Derived values (`bar%`, `ringDeg`, `peak`) from `display*` not `target`/`raw`
- Peaks `displayMax` glide `~3/s`, monotonic, snap `<0.03`

### Gate 3 — Performance
- `will-change`, `contain:paint`, `translateZ(0)` on animated bars/rings
- `prev` diff guard on every DOM write, no unconditional `textContent` in RAF
- `dtClamped=min(dt,32)` + `dtSec` consistently, no `dt>32` leak
- `document.hidden` throttle `300-400ms`, stale `200-300ms`

### Gate 4 — A11y / Correctness
- `prefers-reduced-motion` disables decorative boot only, not telemetry
- `aria-live="polite"` on live regions
- `prefers-reduced-transparency` disables `text-shadow`
- Source constants (`STALE_MS`, `CLAMP`) unchanged unless justified

## How to use in new project
1. Copy this skill folder + `tests/ui-fluidity.test.js` template.
2. Fill `audit.config.json` with your `liveIds`.
3. Add `"plugin": ["./.opencode/plugin/audit-gate.ts"]` (generic gate checks your `audit.config.json`).
4. Run `/audit` or `node tests/ui-fluidity.test.js` — must PASS before push.

## Output
`PASS/FAIL` per gate with `file:line`, fix snippet, `verify: node tests/...`. End `Perfection verdict: PASS | FAIL (x stairs, y janks)`.
