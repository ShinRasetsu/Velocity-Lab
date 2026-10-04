/**
 * CSP gate — Content-Security-Policy hash freshness.
 * Run: node tests/csp.test.js        (verify)
 * Run: node tests/csp.test.js --fix  (stamp current inline-script hashes into the meta)
 * Exit 0 = PASS, 1 = FAIL
 *
 * index.html is single-file, so the CSP meta carries sha256 hashes of every
 * inline <script> block. Any script edit invalidates the hash — this gate
 * fails until --fix re-stamps it. Also guards the two invariants that keep
 * script-src hash-only: no inline event-handler attributes, no
 * 'unsafe-inline'/'unsafe-eval'.
 *
 * Hash note: browsers hash the script's DOM text content, which the HTML
 * parser newline-normalizes (CRLF/CR -> LF) before it reaches the DOM.
 * We normalize the same way so the stamp is correct on both CRLF and LF
 * working copies.
 */
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const INDEX = path.join(__dirname, "..", "index.html");
const fix = process.argv.includes("--fix");

function fail(msg) {
  console.error("FAIL:", msg);
  return false;
}
function pass(msg) {
  console.log("PASS:", msg);
  return true;
}

let ok = true;
let text = fs.readFileSync(INDEX, "utf8");

// --- Extract every inline <script> and hash its exact content ---
const hashes = [];
const scriptRe = /<script(?![^>]*\ssrc=)[^>]*>([\s\S]*?)<\/script>/g;
let m;
while ((m = scriptRe.exec(text)) !== null) {
  if (m[1].trim().length === 0) continue;
  const content = m[1].replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  hashes.push(crypto.createHash("sha256").update(content, "utf8").digest("base64"));
}

if (hashes.length === 0) {
  ok = fail("index.html: no inline <script> found — nothing to hash?") && false;
} else {
  pass(`found ${hashes.length} inline script block(s), sha256 computed`);
}

// --- Expected policy (single source of truth lives here) ---
const expected = [
  "default-src 'self'",
  "script-src 'self' " + hashes.map(h => `'sha256-${h}'`).join(" "),
  "style-src 'self' 'unsafe-inline'",
  "font-src 'self'",
  "img-src 'self'",
  "connect-src 'self'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "manifest-src 'self'"
].join("; ");

// --- Compare with the meta actually shipped ---
const metaRe = /<meta http-equiv="Content-Security-Policy" content="([^"]*)">/;
const metaMatch = text.match(metaRe);

if (fix) {
  if (metaMatch && metaMatch[1] === expected) {
    pass("CSP meta already current — nothing to fix");
  } else if (metaMatch) {
    text = text.replace(metaRe, `<meta http-equiv="Content-Security-Policy" content="${expected}">`);
    fs.writeFileSync(INDEX, text, "utf8");
    pass("CSP meta re-stamped with current hashes");
  } else {
    const anchor = '    <meta charset="UTF-8">\n';
    text = text.replace(anchor, anchor + `    <meta http-equiv="Content-Security-Policy" content="${expected}">\n`);
    fs.writeFileSync(INDEX, text, "utf8");
    pass("CSP meta inserted after charset");
  }
} else {
  if (!metaMatch) {
    ok = fail("index.html: CSP meta tag missing — run `node tests/csp.test.js --fix`") && false;
  } else if (metaMatch[1] === expected) {
    pass("CSP meta hash-fresh (matches inline scripts)");
  } else if (metaMatch[1] === "CSP_HASH_PENDING") {
    ok = fail("CSP meta still a placeholder — run `node tests/csp.test.js --fix`") && false;
  } else {
    ok = fail("CSP meta STALE — inline script changed after last stamp. Run `node tests/csp.test.js --fix`") && false;
  }

  if (metaMatch) {
    const scriptSrc = (metaMatch[1].match(/script-src[^;]*/) || [""])[0];
    if (/unsafe-inline|unsafe-eval/.test(scriptSrc)) {
      ok = fail("CSP script-src contains unsafe-inline/unsafe-eval — not allowed here") && false;
    } else pass("script-src has no unsafe-* fallback");
  }

  // --- Inline event handlers would silently die under hash-only script-src ---
  const handlerRe = /\son(click|change|input|submit|keydown|keyup|load|error|touchstart|touchend|pointerdown|pointerup)=/;
  if (handlerRe.test(text)) {
    ok = fail("index.html: inline event handler attribute present — bind via addEventListener instead (hash-only CSP blocks it)") && false;
  } else pass("no inline event-handler attributes");

  // --- Remote fetches are forbidden: font-src/connect-src must stay 'self' ---
  if (metaMatch && !/font-src 'self'/.test(metaMatch[1])) {
    ok = fail("CSP font-src is not 'self' — fonts are vendored locally") && false;
  } else if (metaMatch) pass("font-src locked to 'self' (vendored fonts)");
}

// --- Verdict ---
if (ok) {
  console.log("\nCSP verdict: PASS");
  process.exit(0);
} else {
  console.error("\nCSP verdict: FAIL");
  process.exit(1);
}
