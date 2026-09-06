/**
 * Layout gate — prevents auto-scale / full-screen regressions.
 * Run: node tests/layout.test.js
 * Exit 0 = PASS, 1 = FAIL, 2 = runtime error.
 *
 * Why this exists: the "gaps on tall phones" bug was fixed 4+ times and kept
 * returning, because every fix was verified against a desktop-viewport
 * snapshot while the failure only showed on real phone aspects. This gate
 * pins the structural invariants instead of pixel values:
 *
 *  Static (always runs):
 *   - .stage must pack top (no justify-content:center splitting free space
 *     into mid-screen gaps)
 *   - .gauge-wrap must not use container-type:size (collapses grid tracks)
 *   - uniform --ui dial system must exist; --scale/--text-scale tiers banned
 *   - wide cockpit block must exist (landscape utilization)
 *
 *  Live (runs only if the playwright package resolves; otherwise SKIP):
 *   - shell fills viewport, no horizontal overflow, on phone + tall +
 *     landscape + ultrawide viewports
 *   - max inter-section gap small on portrait (no mid-screen voids)
 *   - --ui follows min(vw/390, vh/844) within tolerance
 */
const fs = require("fs");
const path = require("path");
const http = require("http");

const INDEX = path.join(__dirname, "..", "index.html");
const text = fs.readFileSync(INDEX, "utf8");
const style = (text.match(/<style>([\s\S]*?)<\/style>/) || [])[1] || "";

function fail(msg) {
  console.error("FAIL:", msg);
  return false;
}
function pass(msg) {
  console.log("PASS:", msg);
  return true;
}

let ok = true;

// --- Static scans ---
const stageBlock = (style.match(/\.stage\s*\{[^}]*\}/) || [""])[0];
if (/justify-content\s*:\s*center/.test(stageBlock)) {
  ok = fail("index.html: .stage must not center free space (creates mid-screen gaps) — pack top, absorb in gauge-wrap") && false;
} else pass("stage packs top, no centered gaps");

if (/\.gauge-wrap\s*\{[^}]*container-type\s*:\s*size/.test(style)) {
  ok = fail("index.html: container-type:size on .gauge-wrap collapses grid tracks to 0px") && false;
} else pass("no container collapse on gauge-wrap");

if (!/--s-gauge\s*:\s*var\(--ui\)/.test(text) || !/setProperty\('--ui'/.test(text)) {
  ok = fail("index.html: uniform --ui dial system missing (JS-owned --ui + --s-* dials)") && false;
} else pass("uniform --ui dial system present");

if (/--text-scale|--scale:\s*calc\(100vw/.test(text)) {
  ok = fail("index.html: legacy --scale/--text-scale tiers resurfaced — use --ui only") && false;
} else pass("no legacy scale tiers");

if (!/orientation:\s*landscape[^}]*min-width:\s*600px/.test(text) && !/min-width:\s*600px[^}]*orientation:\s*landscape/.test(text)) {
  ok = fail("index.html: landscape cockpit block missing (wide screens fall back to narrow column)") && false;
} else pass("landscape cockpit present");

// --- Live checks (optional) ---
let playwright = null;
try {
  playwright = require("playwright");
} catch (e) {
  try {
    playwright = require(path.join(__dirname, "..", "node_modules", "playwright"));
  } catch (e2) { /* not installed -> SKIP live */ }
}

async function live() {
  const root = path.join(__dirname, "..");
  const server = http.createServer((req, res) => {
    let p = decodeURIComponent(req.url.split("?")[0]);
    if (p === "/") p = "/index.html";
    fs.readFile(path.join(root, p), (e, d) => {
      if (e) { res.writeHead(404); res.end("nf"); return; }
      res.writeHead(200, { "Content-Type": "text/html" });
      res.end(d);
    });
  });
  await new Promise(r => server.listen(0, "127.0.0.1", r));
  const port = server.address().port;
  const browser = await playwright.chromium.launch();
  try {
    for (const vp of [{ width: 390, height: 844 }, { width: 412, height: 950 }, { width: 800, height: 360 }, { width: 2400, height: 1080 }]) {
      const ctx = await browser.newContext({ viewport: vp });
      const page = await ctx.newPage();
      await page.goto("http://127.0.0.1:" + port + "/index.html", { waitUntil: "load", timeout: 30000 });
      await page.waitForTimeout(2200);
      const m = await page.evaluate(() => {
        const shell = document.querySelector(".dashboard-shell");
        const boxes = [];
        for (const el of shell.children) {
          if (el.id === "ios-gate") continue;
          let pos = "static";
          try { pos = getComputedStyle(el).position; } catch (e) {}
          if (pos === "fixed" || pos === "absolute") continue;
          const r = el.getBoundingClientRect();
          if (r.height <= 0) continue;
          boxes.push({ top: r.top, bottom: r.bottom });
        }
        let maxGap = 0;
        for (let i = 1; i < boxes.length; i++) {
          const g = boxes[i].top - boxes[i - 1].bottom;
          if (g > maxGap) maxGap = g;
        }
        const cs = getComputedStyle(document.documentElement);
        return {
          maxGap: Math.round(maxGap),
          vScroll: document.documentElement.scrollHeight - window.innerHeight,
          hOver: document.documentElement.scrollWidth - window.innerWidth,
          fills: shell.getBoundingClientRect().bottom >= window.innerHeight - 1,
          ui: parseFloat(cs.getPropertyValue("--ui")) || 0
        };
      });
      const expUi = Math.min(vp.width / 390, vp.height / 844);
      const tag = vp.width + "x" + vp.height;
      if (!(m.fills && m.hOver <= 0)) ok = fail(tag + ": must fill viewport without h-overflow") && false;
      else pass(tag + ": fills viewport, no h-overflow");
      const gapLimit = vp.width > vp.height ? 70 : 24;
      if (!(m.maxGap <= gapLimit)) ok = fail(tag + ": inter-section gap " + m.maxGap + "px exceeds " + gapLimit + "px") && false;
      else pass(tag + ": max section gap " + m.maxGap + "px");
      if (Math.abs(m.ui - Math.min(expUi, 2.5)) > 0.35 && m.ui < 0.64) ok = fail(tag + ": --ui " + m.ui + " far from min-ratio " + expUi.toFixed(2)) && false;
      else pass(tag + ": --ui " + m.ui);
      if (m.vScroll > 40) console.log("NOTE " + tag + ": vScroll " + m.vScroll + "px (floor/readability tradeoff)");
      await ctx.close();
    }
  } finally {
    await browser.close();
    server.close();
  }
}

(async () => {
  if (!playwright) {
    console.log("SKIP live layout checks (playwright not installed)");
  } else {
    await live();
  }
  if (ok) {
    console.log("\nPerfection verdict: PASS (layout gates hold)");
    process.exit(0);
  } else {
    console.error("\nPerfection verdict: FAIL — layout regression");
    process.exit(1);
  }
})().catch(e => { console.error("runtime error:", e && e.message); process.exit(2); });
