/**
 * QA fixture generator — turns OSRM road geometry into a synthetic 1 Hz drive
 * with realistic GNSS degradation, for tests/replay.js and live chrome-devtools
 * sensor-injection sessions.
 *
 * Usage:
 *   node tests/fixtures/gen-drive.js
 *
 * Emits (deterministic, seed 1337):
 *   tests/fixtures/urban-drive.csv  — exportRun two-section shape; replay with:
 *       node tests/replay.js tests/fixtures/urban-drive.csv --report
 *   tests/fixtures/urban-drive.json — truth + raw fixes (live-injection + scoring)
 *
 * Route: hardcoded OSRM full polyline (13th St -> 2nd St, San Francisco, 8.0 km)
 * from the osrm MCP (overpass demo server). Regenerating the route is a manual
 * MCP step; the geometry is pinned here so fixtures are reproducible offline.
 */
const fs = require('fs');
const path = require('path');

const ROUTE_POLYLINE = 'o}oeF~cejV?E?Y?S@]@a@B_@@a@Dc@BW@GBYH_AJiABU@Q@MBWDc@Do@Do@@a@@K@m@@M?_@@WBcA@[SCA\\?TCn@IpBCj@En@El@Gr@AHALAPCTGn@UrCCb@C`@C`@A`@Ah@?D?VAn@?V@b@LnBHPBVBV@VBT?XDhB@XQ@y@DyCLi@Ba@@E?I@U@SBc@@c@B_@@Q@QBWe@q@_AY_@KIIECCKMwAoBqAgBKOUYm@u@LQhA{A@Ar@cARWDU?[COdAUTIl@SRE`AS^IAYyBb@SDUSWSUOOEYYu@u@UYOSOUOSOQIKMSOSGIuAmBMQq@_AOSMQQU_@i@y@gAJQhCkDnAcBNUZb@\\b@QTuAlB_C`DA@A@ILy@gAa@i@QWOSMQY_@GIU[Y_@mBkCY_@MOLQLOHM@Cn@y@~@qAHId@o@@A@CZa@PUJOPWV[Xc@lA_BMSm@y@QUOWKLgClDKLnAdBNRJOPWV[Xc@lA_Br@_APWNSOQSYy@iAsAgBOUgA{AW]o@{@MSIIEG[a@i@w@k@u@a@k@KOKMa@k@_@e@MSMQAWg@m@EIMODGZc@FKDEV_@DERYt@aAPULL@@DDJMTY@BJLLL?@PGFGLQLPPTj@v@xArBrBpCBBHLJL\\d@h@t@xArB@?v@fA`@j@NRp@|@BDNRJOJOV[RYp@_At@cA\\c@LQFGV[s@aAaAEs@?e@A_@CWEIAc@Ia@Oa@Oc@Wa@U_@W]Y]Y[[_@a@c@e@]a@[a@Wa@u@oA]m@Wg@KUaFuLe@wAQg@Ue@c@u@eCaE[g@Ue@GQGOI[G[E]?GAU@YEGCEGILOfAyAjA{ANWr@aANQNSrBoCdB{BLQGIGIGISY}@mAo@{@KOKMg@u@U[SWMPgB`CKLQVABq@|@_@f@MNcAuAOSMSi@u@U[eAsA[e@{AqB_@i@e@o@MQLQDEZc@vC}D`@g@LSLO\\g@LQZa@RW';

function decodePolyline(str, precision) {
    let index = 0, lat = 0, lon = 0, coords = [];
    const factor = Math.pow(10, precision);
    while (index < str.length) {
        let result = 1, shift = 0, b;
        do { b = str.charCodeAt(index++) - 63 - 1; result += b << shift; shift += 5; } while (b >= 0x1f);
        lat += (result & 1) ? ~(result >> 1) : (result >> 1);
        result = 1; shift = 0;
        do { b = str.charCodeAt(index++) - 63 - 1; result += b << shift; shift += 5; } while (b >= 0x1f);
        lon += (result & 1) ? ~(result >> 1) : (result >> 1);
        coords.push([lat / factor, lon / factor]);
    }
    return coords;
}

function rng(seed) {
    let a = seed >>> 0;
    return function () {
        a |= 0; a = (a + 0x6D2B79F5) | 0;
        let t = Math.imul(a ^ (a >>> 15), 1 | a);
        t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
        return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
}
function gauss(r) {
    const u = Math.max(1e-12, r()), v = r();
    return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

const track = decodePolyline(ROUTE_POLYLINE, 5);
const seg = [];
let totalM = 0;
const R_M = 111320;
for (let i = 1; i < track.length; i++) {
    const dy = (track[i][0] - track[i - 1][0]) * R_M;
    const dx = (track[i][1] - track[i - 1][1]) * R_M * Math.cos(37.77 * Math.PI / 180);
    const d = Math.hypot(dx, dy);
    if (d > 0) { seg.push({ d: d, brg: Math.atan2(dx, dy) * 180 / Math.PI }); totalM += d; }
}

function at(distM) {
    let acc = 0;
    for (let i = 0; i < seg.length; i++) {
        if (acc + seg[i].d >= distM) {
            const f = (distM - acc) / seg[i].d;
            const la = track[i][0] + (track[i + 1][0] - track[i][0]) * f;
            const lo = track[i][1] + (track[i + 1][1] - track[i][1]) * f;
            return { lat: la, lon: lo, brg: seg[i].brg };
        }
        acc += seg[i].d;
    }
    const last = track[track.length - 1];
    return { lat: last[0], lon: last[1], brg: seg[seg.length - 1].brg };
}

const rand = rng(1337);
const T0 = 1759000000000;
const phases = [
    { v: 0, hold: 4, label: 'start-parked' },
    { v: 14, label: 'pull-away+cruise' },
    { v: 0, hold: 18, label: 'red-light' },
    { v: 16, label: 'cruise' },
    { outage: 12, label: 'urban-canyon-outage' },
    { v: 11, label: 'canyon-crawl', weak: true },
    { v: 17, label: 'recovered-cruise' },
    { v: 0, hold: 6, label: 'end-stop' }
];

const fixes = [], truth = [];
let t = 0, dist = 0, curV = 0, lastV = 0, wanderLat = 0, wanderLon = 0;
for (const ph of phases) {
    if (ph.outage) {
        for (let s = 0; s < ph.outage; s++) { t += 1; dist += lastV; truth.push({ t: t, v: lastV, d: dist }); }
        continue;
    }
    if (ph.hold) {
        for (let s = 0; s < ph.hold; s++) {
            const p = at(dist);
            truth.push({ t: t, v: 0, d: dist, lat: p.lat, lon: p.lon });
            emitFix(0, p, ph);
            t += 1;
        }
        continue;
    }
    const target = ph.v, dur = Math.max(6, Math.round((totalM * 0.85) / phases.length / target));
    for (let s = 0; s < dur; s++) {
        const a = curV < target ? 2.2 : 0;
        curV = Math.min(target, curV + a);
        lastV = curV;
        if (curV > 0.5) dist += curV;
        if (dist >= totalM - 5) break;
        const p = at(dist);
        truth.push({ t: t, v: curV, d: dist, lat: p.lat, lon: p.lon });
        emitFix(curV, p, ph);
        t += 1;
    }
}

function emitFix(v, p, ph) {
    const weak = !!ph.weak;
    wanderLat = wanderLat * 0.92 + gauss(rand) * (weak ? 0.9 : 0.15);
    wanderLon = wanderLon * 0.92 + gauss(rand) * (weak ? 0.9 : 0.15);
    const accM = weak ? 22 + rand() * 18 : 5 + rand() * 6;
    const spike = weak && rand() < 0.08 ? 40 + rand() * 30 : 0;
    const lat = p.lat + wanderLat / R_M + gauss(rand) * (accM / 2) / R_M + spike * gauss(rand) / R_M;
    const lon = p.lon + wanderLon / (R_M * Math.cos(37.77 * Math.PI / 180)) + gauss(rand) * (accM / 2) / (R_M * Math.cos(37.77 * Math.PI / 180)) + spike * gauss(rand) / (R_M * Math.cos(37.77 * Math.PI / 180));
    const doppler = (!weak && v > 0.4) ? v + gauss(rand) * 0.15 : null;
    const sacc = doppler !== null ? 0.3 + rand() * 0.2 : null;
    const hdg = v > 0.5 ? ((p.brg + gauss(rand) * 3 + 360) % 360) : null;
    fixes.push({
        tMs: T0 + t * 1000 + Math.round((rand() - 0.5) * 260),
        tsMs: T0 + t * 1000,
        lat: Number(lat.toFixed(7)), lon: Number(lon.toFixed(7)),
        acc: Math.round(accM), doppler: doppler, sacc: sacc, hdg: hdg,
        weak: weak, truthV: v
    });
}

const csv = [];
csv.push('metric,value');
csv.push('');
csv.push('# fixlog,"tMs,tsMs,lat,lon,acc,doppler,sacc,hdg,conf,vMeas,kalmanV,kalmanP,kGain,innov,R,flags,fusedG,distM,jumpDist,maxPlaus,rawDt"');
for (const f of fixes) {
    csv.push(['@', f.tMs, f.tsMs, f.lat, f.lon, f.acc,
        f.doppler === null ? '' : f.doppler.toFixed(3),
        f.sacc === null ? '' : f.sacc.toFixed(2),
        f.hdg === null ? '' : f.hdg.toFixed(1)].join(','));
}

const outDir = __dirname;
fs.writeFileSync(path.join(outDir, 'urban-drive.csv'), csv.join('\n') + '\n');
fs.writeFileSync(path.join(outDir, 'urban-drive.json'), JSON.stringify({
    route: { lengthM: Math.round(totalM), points: track.length },
    seed: 1337, t0: T0,
    phases: phases.map(p => p.label),
    weakFixes: fixes.filter(f => f.weak).length,
    dopplerFixes: fixes.filter(f => f.doppler !== null).length,
    fixes: fixes, truth: truth
}, null, 1));

console.log('route: ' + Math.round(totalM) + ' m over ' + track.length + ' shape points');
console.log('fixes: ' + fixes.length + ' (weak ' + fixes.filter(f => f.weak).length + ', doppler ' + fixes.filter(f => f.doppler !== null).length + ', outage ' + phases.filter(p => p.outage).map(p => p.outage + 's').join('') + ')');
console.log('wrote tests/fixtures/urban-drive.csv + urban-drive.json');
