---
description: Run full 7-gate perfection audit (project-matched for Velocity-Lab HUD)
agent: perfection-auditor
---

Run the full perfection audit per `.opencode/skills/perfection-audit/SKILL.md` 7 gates in order (0 Trace, 1 Fluidity, 2 Visual, 3 Perf, 4 Telemetry, 5 System/PWA, 6 Design, 7 A11y).

Steps:
1. Read `.opencode/skills/perfection-audit/SKILL.md`
2. Launch perfection-auditor subagent to grep `index.html`/`sw.js`/`manifest.json` for forbidden patterns and verify all interpolators/constants.
3. Execute `node tests/fluidity.test.js` and `python tests/tests.py` (if available) and include outputs.
4. Report PASS/FAIL per gate with file:line and fix snippets. End with `Perfection verdict: PASS | FAIL (x stairs, y janks, z telemetry)`.

$ARGUMENTS
