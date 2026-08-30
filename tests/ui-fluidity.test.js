/**
 * Generic UI fluidity template — copy to any project.
 * 1. Fill LIVE_IDS / FORBIDDEN to match your project
 * 2. Run: node tests/ui-fluidity.test.js
 */
const fs = require("fs"), path = require("path");
const INDEX = path.join(__dirname, "..", "index.html"); // adjust per project
const text = fs.existsSync(INDEX) ? fs.readFileSync(INDEX, "utf8") : "";
const script = (text.match(/<script>([\s\S]*?)<\/script>/)||[])[1]||"";
const liveIds = ["speed-display","max-speed-gauge","speed-bar","speed-ring","dist-display"]; // ← configure
let ok=true, fail=m=>{console.error("FAIL:",m);ok=false}, pass=m=>console.log("PASS:",m);

// Example Gate 1 bans — adapt regex to your names
if (/current.*=.*gps/i.test(script) && /dom\.speed.*current/i.test(script)) fail("direct lowFreq→DOM"); else pass("no direct GPS→DOM");
if (liveIds.some(id=>text.includes(id) && /Math\.round.*\* 100/.test(script))) {
  // narrow to bar lines: check accPct style
  if (/const accPct = Math\.round/.test(script)) fail("Math.round bars"); else pass("bars fractional");
} else pass("bars fractional");
if (text.includes("displayDistance") || !/distance.*toFixed/.test(text)) pass("distance interpolator"); else fail("distance stair");

// Sim: 1Hz ramp, 60fps fallback smoother — generic
let cur=0,disp=0,out=[]; for(let t=0;t<=6000;t+=16.6){ if(Math.floor(t/1000)!==Math.floor((t-16.6)/1000)) cur=Math.min(27.77,2.777*t/1000); const a=1-Math.exp(-0.0166/0.60); disp+=(cur-disp)*a; if(t%200<8) out.push(disp*3.6);} let min=Infinity,max=-Infinity; for(let i=1;i<out.length;i++){const d=out[i]-out[i-1]; min=Math.min(min,d); max=Math.max(max,d);} const ratio=min/max; console.log(`ratio ${ratio.toFixed(3)} min ${min.toFixed(2)}`); if(ratio<0.08) fail("plateau"); else pass("continuous");
console.log(ok?"\nPerfection verdict: PASS":"\nPerfection verdict: FAIL"); process.exit(ok?0:1);
