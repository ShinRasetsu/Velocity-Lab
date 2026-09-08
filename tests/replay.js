/**
 * Phase-3 replay bench — tune the estimator against data, not vibes.
 *
 * Usage:
 *   node tests/replay.js [drive.csv] [--baseline base.html] [--strict] [--help]
 *
 * - No args: runs the built-in synthetic suite (truth-known drives) against
 *   the worktree index.html and prints a metrics table.
 * - drive.csv: replays an exportRun CSV (uses its # fixlog section: arrival
 *   times, GPS stamps, raw observables) through the real onPositionSuccess.
 * - --baseline <file>: runs everything against that index.html too and prints
 *   side-by-side deltas. Make one via: git show HEAD:index.html > /tmp/base.html
 * - --strict: exit 1 if any primary metric regresses vs baseline beyond
 *   tolerance (rmse +3%, bumps +0, lag90 +0.25s, maxStep +0.5, drift +10%).
 *   This is the gate a tuning change must pass: better-or-neutral.
 *
 * Hard violations (always exit 1): non-finite estimate, deadlock (truth>5
 * while est<0.5 for 6+ straight fixes), teleport leak (single-fix |dEst|>8
 * while |dTruth|<1 on synthetic drives).
 *
 * Exit codes: 0 pass/bench-ok, 1 regression|violation, 2 runtime error.
 * Node-only bench (no python counterpart needed).
 */
const fs = require('fs'), path = require('path'), vm = require('vm');

const ROOT = path.join(__dirname, '..');
const INDEX = path.join(ROOT, 'index.html');
const TESTS = path.join(__dirname, 'telemetry.test.js');

function extractBody(html) {
  const m = html.match(/<script>([\s\S]*?)<\/script>/);
  if (!m) throw new Error('no <script> block');
  return m[1];
}
// Reuse the telemetry PRELUDE verbatim so the harness can never drift from it.
function extractPrelude() {
  const src = fs.readFileSync(TESTS, 'utf8');
  const m = src.match(/const PRELUDE = `([\s\S]*?)`;/);
  if (!m) throw new Error('PRELUDE not found in telemetry.test.js');
  return m[1];
}

// --- deterministic PRNG (mulberry32) + gaussian ---
function rng(seed) {
  let a = seed >>> 0;
  return function() {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
function gauss(rand) {
  const u = Math.max(1e-9, rand()), v = rand();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

const MPD = 6371000 * Math.PI / 180;
const LAT0 = 40.0;

// --- synthetic drive generator ---
// profile(t) -> { v (truth m/s), acc, dop (doppler or null), sa, jit (pos sigma m) }
function genDrive(name, durSec, hz, profile, opts) {
  opts = opts || {};
  const rand = rng(opts.seed || 1234);
  const dt = 1 / hz;
  const fixes = [], truth = [];
  let lat = LAT0, t = 0;
  for (let i = 0; i < Math.round(durSec * hz); i++) {
    const p = profile(t);
    truth.push(p.v);
    const step = p.v * dt;
    lat += step / MPD;
    const j = (p.jit > 0) ? gauss(rand) * p.jit / MPD : 0;
    fixes.push({
      dtArr: dt, dtStamp: dt,
      lat: lat + j, lon: 0, acc: p.acc,
      spd: (p.dop === null || p.dop === undefined) ? null : p.v + (p.dopNoise ? gauss(rand) * p.dopNoise : 0),
      sacc: (p.dop === null || p.dop === undefined) ? null : (p.sa !== undefined ? p.sa : 0.5),
      hdg: null, ts: 1
    });
    t += dt;
  }
  return { name: name, hz: hz, fixes: fixes, truth: truth, imu: opts.imu || null };
}
function cruise(v, acc, dop) { return function() { return { v: v, acc: acc, dop: dop === undefined ? 1 : dop, jit: 0 }; }; }

function scenarios() {
  const S = [];
  S.push(genDrive('cruise20', 30, 1, cruise(20, 5)));
  S.push(genDrive('ramp0-30', 12, 1, function(t) {
    const v = t < 6 ? 5 * t : 30;
    return { v: v, acc: 5, dop: 1, jit: 0 };
  }));
  S.push(genDrive('stopgo', 25, 1, function(t) {
    const v = t < 10 ? 20 : (t < 15 ? 0 : 20);
    return { v: v, acc: 6, dop: 1, jit: v === 0 ? 2 : 0 };
  }));
  S.push(genDrive('standstill', 30, 1, function() { return { v: 0, acc: 8, dop: 1, jit: 3 }; }));
  S.push(genDrive('noisy15m', 20, 1, function() { return { v: 20, acc: 15, dop: 1, dopNoise: 1.0, sa: 1.0, jit: 5 }; }, { seed: 77, skip: 3 }));
  // non-Doppler tunnel resume is covered by gap logic; Doppler variant here
  const t12 = genDrive('tunnel12s', 28, 1, cruise(20, 5));
  t12.gapAt = 8; t12.gapSec = 12;
  shiftAfterGap(t12);
  S.push(t12);
  // Soft-band level shift (+16 m => 36 m step-in at cruise), NON-Doppler:
  // an honest teleport model (all later positions shifted, deltas clean)
  const tj = genDrive('teleportSoft', 20, 1, function() { return { v: 20, acc: 5, dop: null, jit: 0 }; });
  for (let k = 10; k < tj.fixes.length; k++) tj.fixes[k].lat += 16 / MPD;
  tj.skip = 5; // lock transient excluded: score the event, not the bootstrap
  S.push(tj);
  // hard teleport: +5 km, Doppler steady
  const th = genDrive('teleport5km', 20, 1, cruise(20, 5));
  th.fixes[10].lat += 5000 / MPD;
  th.hardJumpAt = 10;
  S.push(th);
  // arrival jitter +-0.4 s, exact GPS stamps, non-Doppler (stamp-clock bench)
  const j = genDrive('jitterStamp', 14, 1, function() { return { v: 20, acc: 5, dop: null, jit: 0 }; });
  for (let i = 0; i < j.fixes.length; i++) j.fixes[i].dtArr = (i % 2 === 0) ? 1.4 : 0.6;
  j.skip = 6; // skip cold-start transient: measure steady jitter response
  S.push(j);
  // non-Doppler tunnel: quarantine + seed composition on resume
  const tn = genDrive('tunnelNoDop', 28, 1, function() { return { v: 20, acc: 8, dop: null, jit: 0 }; });
  tn.gapAt = 8; tn.gapSec = 12;
  shiftAfterGap(tn);
  S.push(tn);
// Unobserved motion during an outage jumps the resume position by v*dt:
// without the shift the car implausibly creeps 20 m through a 12 s gap.
function shiftAfterGap(sc) {
  if (sc.gapAt === undefined) return;
  const v = sc.truth[sc.gapAt - 1] || 0;
  for (let k = sc.gapAt; k < sc.fixes.length; k++) sc.fixes[k].lat += (v * sc.gapSec) / MPD;
}
  // IMU-coupled hard launch: 5 m/s^2 ramp with matching inertial events
  const imu = genDrive('imuRamp', 12, 1, function(t) {
    const v = t < 2 ? 0 : (t < 8 ? 5 * (t - 2) : 30);
    return { v: v, acc: 5, dop: 1, jit: 0 };
  }, { seed: 9 });
  imu.imuEvents = [];
  {
    const rand = rng(9), truth = imu.truth, dt = 1;
    for (let i = 0; i < truth.length; i++) {
      const a = i === 0 ? 0 : (truth[i] - truth[i - 1]) / dt;
      for (let k = 0; k < 10; k++) imu.imuEvents.push({ atFix: i, sub: k / 10, ax: 0, az: a + gauss(rand) * 0.2 });
    }
  }
  S.push(imu);
  return S;
}

// --- field-log CSV parser (exportRun two-section shape) ---
function parseLog(csv) {
  const lines = csv.split(/\r?\n/);
  let i = 0;
  while (i < lines.length && lines[i].trim() !== '') i++;
  while (i < lines.length && lines[i].trim() === '') i++;
  if (i >= lines.length || lines[i].indexOf('# fixlog') !== 0) throw new Error('no # fixlog section found');
  i++;
  const fixes = [];
  let prevT = null;
  for (; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line || line[0] !== '@') continue;
    const c = line.split(',');
    const num = function(s) { return (s === undefined || s === '') ? null : Number(s); };
    const t = Number(c[1]), ts = Number(c[2]);
    fixes.push({
      dtArr: (prevT === null || !(t > prevT)) ? 0 : (t - prevT) / 1000,
      dtStamp: 0, // recomputed below once ts-validity is known per pair
      absT: t, absTs: (c[2] === '' ? null : ts),
      lat: Number(c[3]), lon: Number(c[4]), acc: num(c[5]),
      spd: num(c[6]), sacc: num(c[7]), hdg: num(c[8]), ts: 1
    });
    prevT = t;
  }
  // stamp deltas where both ends have stamps, else mirror arrival delta
  for (let k = 0; k < fixes.length; k++) {
    if (k === 0) { fixes[k].dtStamp = fixes[k].dtArr; continue; }
    const a = fixes[k - 1].absTs, b = fixes[k].absTs;
    fixes[k].dtStamp = (a !== null && b !== null && b > a) ? (b - a) / 1000 : fixes[k].dtArr;
  }
  return { name: 'fieldlog', hz: 0, fixes: fixes, truth: null, imu: null };
}

// --- replay engine: fresh vm per scenario+body ---
function runScenario(body, prelude, sc) {
  const ctx = vm.createContext({});
  vm.runInContext(prelude + '\n' + body + '\n' + 'var __t = 0;\nperformance.now = function(){ return __t; };', ctx, { timeout: 5000 });
  const get = function() {
    return JSON.parse(vm.runInContext(
      'JSON.stringify({cs:currentSpeedMs,kv:kalmanV,clean:lastFixClean,g:gpsGlitchCount,d:distanceMeters,mx:maxSpeedKmph,ot:outlierTimeSec})',
      ctx, { timeout: 1000 }));
  };
  const est = [], st = [], times = [];
  let lat = LAT0;
  // stamp clock: exact dtStamp spacing from first arrival (like real GPS),
  // independent of arrival jitter. Field logs carry absolute stamps instead.
  let stampBase = null, cumStamp = 0;
  const feedFix = function(f) {
    vm.runInContext('__t += ' + (f.dtArr * 1000) + ';', ctx, { timeout: 1000 });
    const nowMs = vm.runInContext('__t;', ctx, { timeout: 1000 });
    if (f.absTs !== undefined && f.absTs !== null) {
      stampBase = null;
    } else {
      if (stampBase === null) { stampBase = nowMs; cumStamp = 0; }
      else cumStamp += f.dtStamp * 1000; // ms: stampBase is epoch-ms
    }
    const coords = { latitude: f.lat, longitude: f.lon === undefined ? 0 : f.lon,
      accuracy: (f.acc === null || f.acc === undefined) ? 999 : f.acc,
      altitudeAccuracy: null, speed: (f.spd === null || f.spd === undefined) ? null : f.spd,
      speedAccuracy: (f.sacc === null || f.sacc === undefined) ? null : f.sacc };
    if (f.hdg !== null && f.hdg !== undefined) coords.heading = f.hdg;
    const pos = { coords: coords };
    if (f.ts) {
      pos.timestamp = (f.absTs !== undefined && f.absTs !== null) ? f.absTs : (stampBase + cumStamp);
    }
    vm.runInContext('__lastPos = ' + JSON.stringify(pos) + ';', ctx, { timeout: 1000 });
    vm.runInContext('onPositionSuccess(__lastPos);', ctx, { timeout: 1000 });
  };
  // IMU pre-roll helper: events {atFix, sub, ax, az} at 10x fix rate
  let evIdx = 0;
  const evs = (sc.imu && sc.imu.imuEvents) ? sc.imu.imuEvents.slice().sort(function(a, b) { return (a.atFix - b.atFix) || (a.sub - b.sub); }) : [];
  for (let i = 0; i < sc.fixes.length; i++) {
    if (sc.gapAt !== undefined && i === sc.gapAt) {
      const gapMs = sc.gapSec * 1000;
      vm.runInContext('__t += ' + gapMs + ';', ctx, { timeout: 1000 });
      cumStamp += gapMs; // GPS clock runs through the outage too
      // drop any IMU events inside the gap
      while (evIdx < evs.length && evs[evIdx].atFix < sc.gapAt + sc.gapSec * sc.hz) evIdx++;
      // emulate renderLoop's stale branch past GPS_STALE_MS: the live app
      // zeroes currentSpeedMs AND wipes the estimator, so resume must go
      // through seed/quarantine exactly like on device
      if (gapMs > 8000) {
        vm.runInContext('currentSpeedMs=0.0;kalmanV=0.0;kalmanP=1.0;kalmanInit=false;prevKalmanV=0.0;prevGpsSpeedMs=0.0;outlierTimeSec=0;seedSettle=0;lastFixClean=true;fixWindow=[];lastPosTs=-1;', ctx, { timeout: 1000 });
      }
    }
    while (evIdx < evs.length && evs[evIdx].atFix === i) {
      const e = evs[evIdx++];
      vm.runInContext('__t += ' + ((1 / sc.hz / 10) * 1000) + ';', ctx, { timeout: 1000 });
      vm.runInContext('handleMotion({acceleration:{x:' + e.ax + ',z:' + e.az + '}});', ctx, { timeout: 1000 });
    }
    feedFix(sc.fixes[i]);
    const s = get();
    if (!isFinite(s.cs) || !isFinite(s.kv)) return { error: 'non-finite estimate at fix ' + i };
    est.push(s.cs); st.push(s);
    times.push(vm.runInContext('__t / 1000;', ctx, { timeout: 1000 }));
  }
  let log = null;
  try {
    const raw = vm.runInContext('JSON.stringify(typeof fixLog === "undefined" ? null : fixLog);', ctx, { timeout: 1000 });
    log = JSON.parse(raw);
  } catch (e) { log = null; }
  return { est: est, st: st, times: times, log: log };
}

// --- metrics (truth-anchored where truth exists) ---
function score(sc, res) {
  if (res.error) return { error: res.error };
  let est = res.est, truth = sc.truth, sts = res.st;
  let times = res.times || est.map(function(_, i) { return i / (sc.hz || 1); });
  const nFull = est.length;
  // deadlock is evaluated on the full series; everything else past the skip
  let deadRun = 0, dead = false;
  if (truth) {
    for (let i = 0; i < nFull; i++) {
      if (truth[i] > 5 && est[i] < 0.5) { deadRun++; if (deadRun >= 6) dead = true; } else deadRun = 0;
    }
  }
  if (sc.skip) { est = est.slice(sc.skip); sts = sts.slice(sc.skip); times = times.slice(sc.skip); if (truth) truth = truth.slice(sc.skip); }
  const n = est.length;
  const m = { n: nFull };
  if (truth) {
    let se = 0, over = 0, lag90 = null, tT = -1, drift = 0;
    const vEnd = truth[truth.length - 1];
    for (let i = 0; i < n; i++) {
      const e = (est[i] - truth[i]);
      se += e * e;
      if (truth[i] >= 0.9 * Math.max(vEnd, 0.1) && tT < 0) tT = i;
      if (tT >= 0 && i >= tT) { if (est[i] - truth[i] > over) over = est[i] - truth[i]; }
    }
    m.rmse = Math.sqrt(se / n);
    m.overshoot = over;
    m.deadlock = dead;
    if (tT >= 0 && vEnd > 1) {
      let te = -1;
      for (let i = 0; i < n; i++) if (est[i] >= 0.9 * vEnd) { te = i; break; }
      m.lag90 = (te < 0) ? Infinity : (times[te] - times[tT]);
    } else m.lag90 = 0;
    // standstill creep: distance gained while SETTLED stopped (truth < 0.3
    // two fixes running). Transition lag is honest tracking, not creep —
    // only steady-state accumulation counts.
    let prevD = 0, first = true;
    for (let i = 0; i < n; i++) {
      const d = sts[i].d;
      if (!first && truth[i] < 0.3 && truth[i - 1] < 0.3) drift += Math.max(0, d - prevD);
      prevD = d; first = false;
    }
    m.drift = drift;
  } else {
    m.rmse = null; m.overshoot = null; m.deadlock = false; m.lag90 = null; m.drift = null;
  }
  let bumps = 0, maxStep = 0, coast = 0, leak = 0;
  // (gap index shifted by skip: arrays below are post-slice.)
  const gShift = (sc.gapAt !== undefined) ? sc.gapAt - (sc.skip || 0) : -99;
  for (let i = 1; i < n; i++) {
    const ds = Math.abs(est[i] - est[i - 1]);
    // gap-resume steps are recovery, not response: the estimator was
    // correctly zeroed while stale. rmse still bills them.
    const resumed = (i === gShift || i === gShift + 1);
    if (!resumed && ds > maxStep) maxStep = ds;
    const dt = truth ? Math.abs(truth[i] - truth[i - 1]) : 0;
    if (!resumed) {
      if (ds > 3 && dt < 1) bumps++;
      if (truth && ds > 8 && dt < 1) leak++;
    }
    if (!sts[i].clean) coast++;
  }
  m.bumps = bumps; m.maxStep = maxStep; m.coastFrac = n > 1 ? coast / (n - 1) : 0;
  m.teleportLeak = leak;
  m.glitches = sts.length ? sts[sts.length - 1].g : 0;
  return m;
}

function fmt(x, d) {
  if (x === null || x === undefined) return 'n/a';
  if (x === Infinity) return 'INF';
  return Number(x).toFixed(d === undefined ? 2 : d);
}

function dumpRun(sc, row) {
  if (!row.dump) { console.log('(no series)'); return; }
  const skip = sc.skip || 0;
  console.log('fix | truth | est | flags | vMeas | kGain | innov | jump | maxPl | rawDt');
  for (let i = 0; i < row.dump.est.length; i++) {
    const t = row.dump.truth ? row.dump.truth[i].toFixed(2) : 'n/a';
    const le = (row.dump.log && row.dump.log[i] !== undefined) ? row.dump.log[i] : null;
    const fl = le ? le.fl : '-';
    const extra = le ? (' | ' + le.vm + ' | ' + le.k + ' | ' + le.iv + ' | ' + le.jd + ' | ' + le.mp + ' | ' + le.rd) : '';
    console.log((i < skip ? '*' : ' ') + i + ' | ' + t + ' | ' + row.dump.est[i].toFixed(3) + ' | ' + fl + extra);
  }
}

function printTable(rows, base) {
  const head = ['scenario', 'n', 'rmse', 'lag90s', 'bumps', 'maxStep', 'overshoot', 'coast%', 'driftM', 'notes'];
  console.log(head.join(' | '));
  rows.forEach(function(r) {
    const cols = [r.name, r.m.n, fmt(r.m.rmse), fmt(r.m.lag90), r.m.bumps,
      fmt(r.m.maxStep), fmt(r.m.overshoot), fmt(r.m.coastFrac * 100, 1), fmt(r.m.drift, 1), r.note || ''];
    let line = cols.join(' | ');
    if (base) {
      const b = base[r.name];
      if (b && b.m && !b.m.error && !r.m.error) {
        const d = [];
        if (r.m.rmse !== null && b.m.rmse !== null) d.push('rmse' + (r.m.rmse <= b.m.rmse * 1.03 + 1e-9 ? '=' : ' WORSE'));
        d.push('bumps' + (r.m.bumps <= b.m.bumps ? '=' : ' WORSE'));
        if (r.m.lag90 !== null && b.m.lag90 !== null) d.push('lag' + (r.m.lag90 <= b.m.lag90 + 0.25 ? '=' : ' WORSE'));
        line += '   || base[' + fmt(b.m.rmse) + '/' + b.m.bumps + '/' + fmt(b.m.lag90) + '] ' + d.join(' ');
      }
    }
    console.log(line);
  });
}

function main() {
  const args = process.argv.slice(2);
  if (args.indexOf('--help') !== -1 || args.indexOf('-h') !== -1) {
    console.log('usage: node tests/replay.js [drive.csv] [--baseline base.html] [--strict]');
    return 0;
  }
  const strict = args.indexOf('--strict') !== -1;
  const bi = args.indexOf('--baseline');
  const baseFile = bi !== -1 ? args[bi + 1] : null;
  const di = args.indexOf('--dump');
  const dumpName = di !== -1 ? args[di + 1] : null;
  // first non-flag arg that is not a flag's value
  let logFile = null;
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--baseline' || args[i] === '--dump') { i++; continue; }
    if (args[i][0] !== '-') { logFile = args[i]; break; }
  }

  let body, prelude;
  try {
    body = extractBody(fs.readFileSync(INDEX, 'utf8'));
    prelude = extractPrelude();
  } catch (e) { console.error('load error:', e.message); return 2; }
  let baseBody = null;
  if (baseFile) {
    try { baseBody = extractBody(fs.readFileSync(baseFile, 'utf8')); }
    catch (e) { console.error('baseline load error:', e.message); return 2; }
  }

  let list;
  try {
    const allSc = logFile ? [parseLog(fs.readFileSync(logFile, 'utf8'))] : scenarios();
    list = dumpName ? allSc.filter(function(s) { return s.name === dumpName; }) : allSc;
    if (dumpName && !list.length) { console.error('unknown scenario: ' + dumpName); return 2; }
  } catch (e) { console.error('input error:', e.message); return 2; }
  const rows = [], baseRows = {};
  let failed = 0;
  list.forEach(function(sc) {
    let res, m;
    try { res = runScenario(body, prelude, sc); m = score(sc, res); }
    catch (e) { console.log(sc.name + ' | RUNTIME-ERROR ' + e.message); failed++; return; }
    const row = { name: sc.name, m: m, note: '', dump: res.est ? { est: res.est, truth: sc.truth, log: res.log } : null };
    if (m.error) { row.note = m.error; failed++; }
    if (m.deadlock) { row.note += (row.note ? '; ' : '') + 'DEADLOCK'; failed++; }
    if (m.teleportLeak) { row.note += (row.note ? '; ' : '') + 'TELEPORT-LEAKx' + m.teleportLeak; failed++; }
    if (m.lag90 === Infinity) { row.note += (row.note ? '; ' : '') + 'NEVER-LOCKS'; failed++; }
    rows.push(row);
    if (baseBody) {
      try {
        const bres = runScenario(baseBody, prelude, sc);
        baseRows[sc.name] = { name: sc.name, m: score(sc, bres), dump: bres.est ? { est: bres.est, truth: sc.truth, log: bres.log } : null };
      } catch (e) { console.log(sc.name + ' | BASELINE-ERROR ' + e.message); failed++; }
    }
  });
  if (dumpName) {
    rows.forEach(function(r) {
      console.log('== ' + r.name + ' (new) ==');
      const sc = list.filter(function(s) { return s.name === r.name; })[0];
      dumpRun(sc, r);
      if (baseBody && baseRows[r.name] && baseRows[r.name].dump) {
        console.log('== ' + r.name + ' (base) ==');
        dumpRun(sc, baseRows[r.name]);
      }
    });
    return failed ? 1 : 0;
  }
  printTable(rows, baseBody ? baseRows : null);

  if (strict && baseBody) {
    rows.forEach(function(r) {
      const b = baseRows[r.name];
      if (!b || !b.m || b.m.error || r.m.error) return;
      const bad = [];
      if (r.m.rmse !== null && b.m.rmse !== null) {
        const tol = Math.max(b.m.rmse * 1.03, b.m.rmse + (b.m.rmse < 0.05 ? 0.02 : 0));
        if (r.m.rmse > tol) bad.push('rmse ' + fmt(r.m.rmse) + ' > base ' + fmt(b.m.rmse));
      }
      if (r.m.bumps > b.m.bumps) bad.push('bumps ' + r.m.bumps + ' > base ' + b.m.bumps);
      if (r.m.lag90 !== null && b.m.lag90 !== null && r.m.lag90 > b.m.lag90 + 0.25) bad.push('lag90 ' + fmt(r.m.lag90) + ' > base ' + fmt(b.m.lag90));
      if (r.m.maxStep > b.m.maxStep + 0.5) bad.push('maxStep ' + fmt(r.m.maxStep) + ' > base ' + fmt(b.m.maxStep));
      if (r.m.drift !== null && b.m.drift !== null && r.m.drift > b.m.drift * 1.1 + 0.5) bad.push('drift ' + fmt(r.m.drift) + ' > base ' + fmt(b.m.drift));
      if (bad.length) { console.log('REGRESS [' + r.name + ']: ' + bad.join('; ')); failed++; }
    });
    if (!failed) console.log('STRICT: no regressions vs baseline');
  }
  console.log(failed ? '\nreplay verdict: FAIL (' + failed + ')' : '\nreplay verdict: OK');
  return failed ? 1 : 0;
}

process.exit(main());
