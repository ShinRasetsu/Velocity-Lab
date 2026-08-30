---
description: Run full 5-gate perfection audit (fluidity, continuity, performance, a11y)
agent: perfection-auditor
---

Run the full perfection audit per `.opencode/skills/perfection-audit/SKILL.md` 5 gates in order.

Steps:
1. Read `.opencode/skills/perfection-audit/SKILL.md`
2. Launch perfection-auditor subagent to grep `index.html` for forbidden stair patterns and verify interpolators.
3. Execute `node tests/fluidity.test.js` and include output.
4. Report PASS/FAIL per gate with file:line and fix snippets. End with `Perfection verdict: PASS | FAIL`.

$ARGUMENTS
