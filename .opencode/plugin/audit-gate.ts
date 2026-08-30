import type { Plugin } from "@opencode-ai/plugin"

export default (async ({ directory }) => {
  return {
    // Gate 1 enforcement: block git commit/push if stair patterns detected — the exact miss that shipped
    "permission.ask": async (input, output) => {
      const tool = (input as any).tool as string
      const pattern = (input as any).pattern as string | undefined
      // Only gate bash git commit/push
      if (tool !== "bash") return
      const cmd = String(pattern ?? "")
      if (!/git\s+(commit|push)/.test(cmd)) return
      try {
        const fs = await import("node:fs")
        const path = await import("node:path")
        const idx = path.join(directory, "index.html")
        if (!fs.existsSync(idx)) return
        const txt = fs.readFileSync(idx, "utf8")
        const script = (txt.match(/<script>([\s\S]*?)<\/script>/) || [])[1] || ""
        const hasDirect = /dom\.speed\.textContent.*currentSpeedMs/.test(script)
        const hasRoundBars = /const accPct = Math\.round/.test(script)
        const hasDistStair = txt.includes("(distanceMeters / 1000).toFixed") && !txt.includes("displayDistanceM")
        const has75 = txt.includes(".speed-bar-fill") && /transition:\s*width 75ms/.test(txt)
        if (hasDirect || hasRoundBars || hasDistStair || has75) {
          ;(output as any).decision = "deny"
          ;(output as any).reason = `⛔ Perfection Gate 1 FAIL — stair-step regression detected. Run /audit-fluidity or node tests/fluidity.test.js. Found: ${[hasDirect && "direct GPS→DOM", hasRoundBars && "Math.round bars", hasDistStair && "distance stair", has75 && "75ms transition"].filter(Boolean).join(", ")}. Fix per .opencode/skills/perfection-audit/SKILL.md then retry.`
        }
      } catch {}
    },
    "tool.execute.before": async (input, output) => {
      const tool = (input as any).tool as string
      const args = (output as any).args as Record<string, any> | undefined
      if (tool !== "bash") return
      const cmd: string = args?.command ?? ""
      if (/git\s+(commit|push)|deploy\.bat/.test(cmd)) {
        console.warn("⛔ Perfection Gate: /audit-fluidity or node tests/fluidity.test.js required before push. See .opencode/skills/perfection-audit/SKILL.md")
      }
    },
  }
}) satisfies Plugin
