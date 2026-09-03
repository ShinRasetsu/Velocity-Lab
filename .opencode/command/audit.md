---
description: Run full 9-gate perfection audit (project-matched for Velocity-Lab HUD, includes Playwright live + optimization suggestions)
agent: perfection-auditor
---

Run the full perfection audit per `.opencode/skills/perfection-audit/SKILL.md` 9 gates in order (0 Trace, 1 Fluidity, 2 Visual, 3 Perf, 4 Telemetry, 5 System/PWA, 6 Design, 7 A11y, 8 Playwright Live, 9 Optimization advisory).

Steps:
1. Read `.opencode/skills/perfection-audit/SKILL.md` + `.opencode/skills/ui-fluidity-audit/SKILL.md` (cross-check)
2. Launch perfection-auditor subagent to grep `index.html`/`sw.js`/`manifest.json` for forbidden patterns and verify all interpolators/constants; load `ui-fluidity-audit` generic checks with `liveIds` `958-1051`.
3. Execute `node tests/fluidity.test.js` and `node tests/telemetry.test.js` (plus `python tests/tests.py` if python available) and include outputs. No SKIP allowed for telemetry.
4. Must use MCPs if `opencode.json:6` enabled: Playwright `browser_navigate` file + deployed, `browser_snapshot`/`browser_evaluate`/`browser_take_screenshot` + offline; Figma `get_design` FIGMA_FILE_KEY → compare tokens `107-113,540,169`; chrome-devtools `performance_start` → `hud-boot 0.28s:553` — enabled but not called → FAIL Gate 8. Also run `ui-fluidity-audit` generic ratio check.
5. Gate 9: always output 3-5 SUGGEST for optimization (`renderLoop:1983` `saveSession`, `sw.js:84`, `font-display:20`), accuracy (`GPS_ACC_TRUST:1100` L5/barometer, `IMU_ALPHA:1141` EKF), features/UI (`V-SCORE:1097` export, `hazard:819` dismiss, `timer:1064` ghost vs MoTeC/F1) — advisory, not FAIL.
6. Report PASS/FAIL per gate with file:line and fix snippets. End with `Perfection verdict: PASS | FAIL (x stairs, y janks, z telemetry)` plus `SUGGEST` list.

$ARGUMENTS
