/**
 * Field-stat histograms over an exportRun/fixture CSV fixlog section.
 *
 * Usage: node tests/fieldstats.js [drive.csv]
 *
 * Answers questions the replay --report can't: raw-observable distributions
 * (accuracy, speedAccuracy presence, headings) and — on device exports where
 * the estimator columns are filled — the R values actually used when
 * speedAccuracy is missing (the "assume 1.0 m/s on iOS" question), residual
 * percentiles, and truth-scored recording stats on generator fixtures.
 * Missing columns degrade gracefully (device exports lack truthV, fixtures
 * lack estimator columns).
 */
const fs = require('fs'), path = require('path');

const file = process.argv[2] || path.join(__dirname, 'fixtures', 'urban-drive.csv');
const lines = fs.readFileSync(file, 'utf8').split(/\r?\n/);
let i = 0;
while (i < lines.length && lines[i].trim() !== '') i++;
while (i < lines.length && lines[i].trim() === '') i++;
if (i >= lines.length || lines[i].indexOf('# fixlog') !== 0) throw new Error('no # fixlog section in ' + file);
i++;

const num = function(s) { return (s === undefined || s === '') ? null : Number(s); };
const rows = [];
for (; i < lines.length; i++) {
  const line = lines[i].trim();
  if (!line || line[0] !== '@') continue;
  const c = line.split(',');
  rows.push({
    acc: num(c[5]), dop: num(c[6]), sacc: num(c[7]), hdg: num(c[8]),
    conf: num(c[9]), vMeas: num(c[10]), kv: num(c[11]), kp: num(c[12]),
    k: num(c[13]), innov: num(c[14]), r: num(c[15]), fl: c[16] || '',
    ig: num(c[17]), dist: num(c[18])
  });
}
if (!rows.length) throw new Error('no @ rows in ' + file);

function pct(vals, q) {
  if (!vals.length) return null;
  const s = vals.slice().sort(function(a, b) { return a - b; });
  return s[Math.min(s.length - 1, Math.floor(q * s.length))];
}
function fmt(x, d) {
  if (x === null || x === undefined || !isFinite(x)) return 'n/a';
  return Number(x).toFixed(d === undefined ? 2 : d);
}
function hist(vals, bins, max) {
  if (!vals.length) return '  (none)';
  const counts = [];
  for (let b = 0; b < bins; b++) counts.push(0);
  for (const v of vals) counts[Math.min(bins - 1, Math.floor(v / max * bins))]++;
  const peak = Math.max.apply(null, counts.concat([1]));
  let out = '';
  for (let b = 0; b < bins; b++) {
    const lo = (b / bins * max).toFixed(1);
    out += '  ' + lo + ' +' + '#'.repeat(Math.round(counts[b] / peak * 40)) + ' ' + counts[b] + '\n';
  }
  return out.replace(/\n$/, '');
}

console.log('== fieldstats (' + file + ') ==  n=' + rows.length);
const dop = rows.filter(function(r) { return r.dop !== null; });
const noSacc = dop.filter(function(r) { return r.sacc === null; });
console.log('doppler present   ' + dop.length + ' (' + fmt(100 * dop.length / rows.length, 1) + '%)');
console.log('sacc missing      ' + noSacc.length + ' of doppler (' + fmt(dop.length ? 100 * noSacc.length / dop.length : 0, 1) + '%)  <- iOS-style unknown-Doppler share');
console.log('heading present   ' + rows.filter(function(r) { return r.hdg !== null; }).length);
const accs = rows.map(function(r) { return r.acc; }).filter(function(x) { return x !== null; });
console.log('acc p50/p90/max   ' + fmt(pct(accs, 0.5), 1) + ' / ' + fmt(pct(accs, 0.9), 1) + ' / ' + fmt(Math.max.apply(null, accs.concat([0])), 0) + ' m');
const saccs = dop.map(function(r) { return r.sacc; }).filter(function(x) { return x !== null; });
console.log('sacc p50/p90/max  ' + fmt(pct(saccs, 0.5), 2) + ' / ' + fmt(pct(saccs, 0.9), 2) + ' / ' + fmt(Math.max.apply(null, saccs.concat([0])), 2) + ' m/s');
console.log('-- acc histogram (0..40 m) --\n' + hist(accs, 10, 40));

// The iOS question: what R did missing-sacc fixes actually run, vs measured?
const rNoSacc = rows.map(function(r) { return (r.dop !== null && r.sacc === null) ? r.r : null; }).filter(function(x) { return x !== null; });
const rSacc = rows.map(function(r) { return (r.dop !== null && r.sacc !== null) ? r.r : null; }).filter(function(x) { return x !== null; });
if (rNoSacc.length || rSacc.length) {
  console.log('R | sacc missing  n=' + rNoSacc.length + ' p50=' + fmt(pct(rNoSacc, 0.5)) + ' p90=' + fmt(pct(rNoSacc, 0.9)));
  console.log('R | sacc present  n=' + rSacc.length + ' p50=' + fmt(pct(rSacc, 0.5)) + ' p90=' + fmt(pct(rSacc, 0.9)));
  console.log('-- R histogram, sacc-missing (0..8) --\n' + hist(rNoSacc, 10, 8));
} else {
  console.log('R columns empty (fixture CSV, not a device export) — run on an exportRun to audit the sacc=1.0 assumption');
}

// Estimator-vs-Doppler residuals with percentiles (needs estimator columns).
const res = rows.map(function(r) { return (r.dop !== null && r.kv !== null) ? r.kv - r.dop : null; }).filter(function(x) { return x !== null; });
if (res.length) {
  const sq = res.reduce(function(a, x) { return a + x * x; }, 0) / res.length;
  console.log('estVsDoppler n=' + res.length + ' rms=' + fmt(Math.sqrt(sq)) + ' p90=' + fmt(pct(res.map(Math.abs), 0.9)) + ' max=' + fmt(Math.max.apply(null, res.map(Math.abs).concat([0]))) + ' m/s');
}
// NOTE: recording-vs-truth odometer scoring intentionally lives outside this
// tool: no single CSV ever carries estimator output (kv) and distance truth
// together. Score odometer endpoints via `node tests/replay.js <csv> --dump`
// (distM column) against the generator JSON truth.
