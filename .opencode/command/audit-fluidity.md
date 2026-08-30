---
description: Quick Gate 1 fluidity check — stair-step detection only
agent: perfection-auditor
---

Run Gate 1 fluidity audit only per `.opencode/skills/perfection-audit/SKILL.md`.

1. Grep forbidden patterns (direct GPS→DOM, Math.round bars, distanceMeters stair, transition 75ms)
2. Run `node tests/fluidity.test.js`
3. Report PASS/FAIL for Gate 1 with file:line.

$ARGUMENTS
