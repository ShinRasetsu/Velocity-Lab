---
description: Run perfusion audit and auto-fix stair/jank issues
agent: perfection-auditor
model: opencode/muse-spark-1.2-contributor-free
---

Run full audit per `.opencode/skills/perfection-audit/SKILL.md`, then if FAIL, fix `index.html` in place:

- Replace direct GPS→DOM with `displaySpeedMs`/`displayMaxKmph`/`displayDistanceM` interpolators (Gate 1)
- Replace `Math.round(...*100)` bars with `.toFixed(1)` (Gate 1)
- Set `.speed-bar-fill { transition:none }` (Gate 2)
- Ensure `prev` diffs + `dtClamped` + throttling (Gate 3)

Verify with `node tests/fluidity.test.js` until PASS. End with `Perfection verdict` and list files changed.

$ARGUMENTS
