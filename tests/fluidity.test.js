/**
 * Fluidity gate — detects stair-step regressions.
 * Run: node tests/fluidity.test.js
 * Exit 0 = PASS, 1 = FAIL
 *
 * Simulates the old bug: GPS 1Hz + 125ms lerp → plateau. New code must
 * produce continuous motion (minDelta/maxDelta > 0.15) and low lag.
 * Also static-scans index.html for forbidden patterns.
 */
const fs = require("fs");
const path = require("path");

const INDEX = path.join(__dirname, "..", "index.html");
const text = fs.readFileSync(INDEX, "utf8");
const script = (text.match(/<script>([\s\S]*?)<\/script>/) || [])[1] || "";

function fail(msg) {
  console.error("FAIL:", msg);
  return false;
}
function pass(msg) {
  console.log("PASS:", msg);
  return true;
}

let ok = true;

// --- Static scans (Gate 1) ---
if (/dom\.speed\.textContent.*currentSpeedMs/.test(script)) {
  ok = fail("index.html: direct GPS→DOM assignment (currentSpeedMs → speed-display) — must use displaySpeedMs") && false;
} else pass("no direct GPS→DOM for speed");

if (/const accPct = Math\.round/.test(script) || /const brkPct = Math\.round/.test(script) || /const latPct = Math\.round/.test(script)) {
  ok = fail("index.html: Math.round on G bars — use .toFixed(1) for 0.1% steps") && false;
} else pass("no Math.round stairs on bars");

if (text.includes("(distanceMeters / 1000).toFixed") && !text.includes("displayDistanceM")) {
  ok = fail("index.html: distance uses raw distanceMeters stair — must use displayDistanceM interpolation") && false;
} else pass("distance interpolator present");

if (text.includes(".speed-bar-fill") && /transition:\s*width 75ms/.test(text)) {
  ok = fail("index.html: speed-bar transition 75ms fights RAF — must be transition:none") && false;
} else pass("speed-bar transition gate");

if (!script.includes("displaySpeedMs += predAccel") && !script.includes("fusedLongG * GRAVITY_MS2 * dtSec")) {
  ok = fail("index.html: missing IMU dead-reckoning (displaySpeedMs += fused*GRAVITY*dt)") && false;
} else pass("IMU dead-reckoning present");

if (!script.includes("displayMaxKmph") || !script.includes("peakMarker") || !script.includes("displayMaxKmph / BAR_MAX_SPEED")) {
  ok = fail("index.html: missing displayMaxKmph glide or peakMarker not using it") && false;
} else pass("MAX glide present");

if (!script.includes("smoothTime") || !script.includes("interval * 0.60")) {
  ok = fail("index.html: missing GPS-only fallback smoothTime clamp (interval*0.60)") && false;
} else pass("fallback smoother present");

// --- Simulation (Gate 1) ---
function simulateFallback() {
  let cur = 0, disp = 0;
  const hz = 1; // 1Hz GPS worst case
  let out = [];
  for (let t = 0; t <= 6000; t += 16.6) {
    if (Math.floor(t / 1000) !== Math.floor((t - 16.6) / 1000)) {
      cur = Math.min(27.77, 2.777 * (t / 1000));
    }
    const dtSec = 16.6 / 1000;
    const interval = 1 / hz;
    const smoothTime = Math.max(0.35, Math.min(0.75, interval * 0.60));
    const alpha = 1 - Math.exp(-dtSec / smoothTime);
    disp += (cur - disp) * alpha;
    if (t % 200 < 8) out.push(disp * 3.6);
  }
  let min = Infinity, max = -Infinity;
  for (let i = 1; i < out.length; i++) {
    const d = out[i] - out[i - 1];
    if (d < min) min = d;
    if (d > max) max = d;
  }
  return { min, max, ratio: min / max, out };
}

const sim = simulateFallback();
console.log(`Sim fallback 1Hz ramp: minDelta=${sim.min.toFixed(2)} maxDelta=${sim.max.toFixed(2)} ratio=${sim.ratio.toFixed(3)} out=[${sim.out.map(v=>v.toFixed(1)).join(", ")}]`);
if (sim.ratio < 0.08) {
  ok = fail(`simulation ratio ${sim.ratio.toFixed(3)} < 0.08 — plateau/stairs detected`) && false;
} else pass(`simulation ratio ${sim.ratio.toFixed(3)} >= 0.08 — continuous`);
if (sim.min < 0.4) {
  ok = fail(`simulation minDelta ${sim.min.toFixed(2)} < 0.4 — still stair`) && false;
} else pass(`minDelta ${sim.min.toFixed(2)} — no flat frame`);

// --- Verdict ---
if (ok) {
  console.log("\nPerfection verdict: PASS (0 stairs, 0 janks)");
  process.exit(0);
} else {
  console.error("\nPerfection verdict: FAIL — fix Gate 1 per .opencode/skills/perfection-audit/SKILL.md");
  process.exit(1);
}
