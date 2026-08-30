---
description: Run perfusion audit and auto-fix stair/jank and telemetry issues
agent: perfection-auditor
model: opencode/muse-spark-1.2-contributor-free
---

Run full 7-gate audit per `.opencode/skills/perfection-audit/SKILL.md`, then if FAIL, fix in place:

- G1: direct GPS→DOM → `displaySpeedMs`/`displayMaxKmph`/`displayDistanceM` interpolators, `Math.round`→`.toFixed(1)`, `75ms`→`none`
- G2: `barPct/ringDeg/peakDeg` from `display*`, `displayMaxKmph` glide `3.2/s`
- G3: `will-change/contain/translateZ`, `prev` guards, `dtClamped`
- G4: `crossFraction/lerp` timers, `conf>=GPS_QUALITY_MIN`, `IMU_ALPHA`/`FUSION_*`/`PHYSICAL_G_CLAMP`
- G5: PWA `manifest`/`sw.js`/`wakeLock`/`iOS gate`/`STORAGE_KEY`
- G6: `--scale`/`safe-area`/`panel`/`scanlines`/`BAR_MAX`/`hazard`
- G7: `aria-live`/`prefers-reduced-motion`

Verify with `node tests/fluidity.test.js` && `python tests/tests.py` until PASS. End with `Perfection verdict` and list files changed.

$ARGUMENTS
