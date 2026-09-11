"""
Velocity-Lab unit tests.

Run with:  python tests/tests.py

These tests exercise three pure-ish functions inside index.html's inline
<script> block:
  - gpsConfidence(accuracyMeters)        - GPS-quality scaling
  - calculateVehicleScore()              - V-score aggregation
  - updateTimers(speedKmh, distanceM, nowMs) - sprint state machines

They run by extracting the script body, shimming document/navigator/etc.
with a minimal mock so the script's top-level side effects survive, then
calling the three functions through a JS engine (py_mini_racer/V8 preferred,
dukpy/duktape as E5 fallback) and asserting on the resulting JS state.
"""
import json
import re
import sys
import pathlib

# Windows console defaults to cp1252 which can't render some test detail
# strings; force UTF-8 before anything else prints.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

try:
    from py_mini_racer import py_mini_racer as _racer
    _USE_RACER = True
except Exception:
    import dukpy
    _USE_RACER = False

ROOT = pathlib.Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"


def extract_script_body(text: str) -> str:
    m = re.search(r"<script>(.*?)</script>", text, re.S)
    if not m:
        raise RuntimeError("Could not find <script> block in index.html")
    return m.group(1)


# Minimal browser shim. Keep tiny -- only the surface area the inline script
# touches at load time. Element-level methods are no-ops; tests don't rely on
# the DOM, only on the three numeric functions and their state side effects.
PRELUDE = r"""
var __results = [];
function __ok(name, cond, detail) {
    __results.push({ name: String(name), ok: !!cond, detail: detail || '' });
}

// --- DOM stubs ---
function __stubEl() {
    return {
        style: { setProperty: function(){}, getPropertyValue: function(){return '';}, removeProperty: function(){} },
        textContent: '', className: '', innerHTML: '',
        appendChild: function(){return arguments[0];},
        removeChild: function(){return arguments[0];},
        addEventListener: function(){},
        setAttribute: function(){},
        getContext: function(){return null;},
        classList: { add: function(){}, remove: function(){}, toggle: function(c,f){ this._t=this._t||{}; this._t[c]=(f===undefined)?!this._t[c]:!!f; return this._t[c]; }, contains: function(c){ return !!(this._t&&this._t[c]); } }
    };
}
var document = {
    getElementById: function(){ return __stubEl(); },
    createElement: function(){ return __stubEl(); },
    querySelector: function(){ return __stubEl(); },
    querySelectorAll: function(){ return []; },
    addEventListener: function(){},
    visibilityState: 'visible',
    body: __stubEl()
};
var window = { addEventListener: function(){}, DeviceMotionEvent: undefined };
var navigator = {};
var performance = { now: function(){return 0;} };

// --- Storage stubs ---
var __lsStore = {};
var localStorage = {
    getItem: function(k){return Object.prototype.hasOwnProperty.call(__lsStore, k) ? __lsStore[k] : null;},
    setItem: function(k, v){__lsStore[k] = String(v);},
    removeItem: function(k){delete __lsStore[k];}
};
// IndexedDB presence triggers promise creation in the script; lie that it's
// absent so idbOpen rejects quickly and the script keeps running.
var indexedDB = undefined;

// --- Misc stubs ---
var URL = { createObjectURL: function(){return 'blob:x';}, revokeObjectURL: function(){} };
function Blob(){}
function TextEncoder(){}
function TextDecoder(){}
var Intl = (function(){
    function FakeFmt(opts) {
        this.opts = opts || {};
        this.format = function(n){
            var min = this.opts.minimumFractionDigits || 0;
            var max = this.opts.maximumFractionDigits || 3;
            var s = Number(n).toFixed(max);
            var dot = s.indexOf('.');
            if (dot === -1) return s;
            var intPart = s.substring(0, dot);
            var frac = s.substring(dot + 1);
            while (frac.length > min && frac.charAt(frac.length - 1) === '0') frac = frac.substring(0, frac.length - 1);
            return frac.length ? intPart + '.' + frac : intPart;
        };
    }
    return { NumberFormat: FakeFmt };
})();
"""


POSTLUDE = r"""

// Test helpers
function nearly(a, b, eps){eps = eps || 1e-9; return Math.abs(a - b) < eps;}

// === Tests: gpsConfidence ===
__ok('gpsConf: <= trust_min -> 1.0',
    nearly(gpsConfidence(0), 1.0) && nearly(gpsConfidence(GPS_ACC_TRUST_MIN_M), 1.0),
    gpsConfidence(GPS_ACC_TRUST_MIN_M) + " expected 1.0");

__ok('gpsConf: >= trust_max -> 0.0',
    nearly(gpsConfidence(GPS_ACC_TRUST_MAX_M), 0.0) && nearly(gpsConfidence(1000), 0.0),
    gpsConfidence(1000) + " expected 0.0");

__ok('gpsConf: midpoint -> 0.5 (linear interp)',
    nearly(gpsConfidence((GPS_ACC_TRUST_MIN_M + GPS_ACC_TRUST_MAX_M)/2), 0.5),
    "expected 0.5 at midpoint");

__ok('gpsConf: NaN / undefined / string -> 0.0',
    nearly(gpsConfidence(NaN), 0.0) && nearly(gpsConfidence(undefined), 0.0) && nearly(gpsConfidence('x'), 0.0),
    "non-number inputs must clamp to 0");

__ok('gpsConf: monotonic non-increasing in accuracy radius',
    gpsConfidence(2) >= gpsConfidence(5) && gpsConfidence(10) >= gpsConfidence(15) && gpsConfidence(20) >= gpsConfidence(25),
    "confidence must not increase as accuracy radius grows");

// === Tests: calculateVehicleScore ===
function __setPeaks(maxSpd, maxAcc, maxBrk, maxLat) {
    maxSpeedKmph = maxSpd; maxGpsAccelG = maxAcc;
    bestGpsBrakingG = maxBrk; maxGpsLatG = maxLat;
}

__setPeaks(0, 0, 0, 0);
var z = calculateVehicleScore();
__ok('vScore: all-zero -> all-zero',
    z.total === 0 && z.spd === 0 && z.acc === 0 && z.brk === 0 && z.hdl === 0,
    'got total=' + z.total);

__setPeaks(200, 1.0, 1.2, 1.1);
var full = calculateVehicleScore();
__ok('vScore: ceiling caps -> spd20/acc10/brk15/hdl25/total70',
    full.spd === 20 && full.acc === 10 && full.brk === 15 && full.hdl === 25 && full.total === 70,
    'got ' + JSON.stringify(full));

__setPeaks(1000, 50, 50, 50);
var cap = calculateVehicleScore();
__ok('vScore: absurd inputs do not exceed ceilings',
    cap.total === 70 && cap.spd === 20 && cap.acc === 10 && cap.brk === 15 && cap.hdl === 25,
    'got ' + JSON.stringify(cap));

__setPeaks(100, 0.5, 0.6, 0.55);
var half = calculateVehicleScore();
// total rounds the sum-of-floats (10 + 5 + 7.5 + 12.5 = 35), while individual
// components round half-up to {10, 5, 8, 13}. That sum-of-rounded = 36 but
// the formula computes total = round(sum-of-floats) = 35. Verify both.
__ok('vScore: half-peak proportional with native rounding',
    half.spd === 10 && half.acc === 5 && half.brk === 8 && half.hdl === 13 && half.total === 35,
    'got ' + JSON.stringify(half));

// === Tests: updateTimers state machines ===
function __resetTimers() {
    timer0_60.state    = T_IDLE; timer0_60.start    = 0; timer0_60.result    = 0;
    timer0_100.state   = T_IDLE; timer0_100.start   = 0; timer0_100.result   = 0;
    timer100_200.state = T_IDLE; timer100_200.start = 0; timer100_200.result = 0;
    timerQuarter.state = T_IDLE; timerQuarter.start = 0; timerQuarter.result = 0; timerQuarter.startDist = 0;
    timer100_0.state   = T_IDLE; timer100_0.start   = 0; timer100_0.startDist = 0; timer100_0.result   = 0;
    // sub-sample interpolation state: cleared so scenarios are order-independent
    lastTimerSpeedKmh  = NaN; lastTimerDistM = NaN; lastTimerTimeMs = NaN;
    stateDirty = false;
}

// 0-100: stopped -> 5 km/h arm -> 100 km/h complete
__resetTimers();
updateTimers(0, 0, 1000);
__ok('t0_100: stopped keeps IDLE',
    timer0_100.state === T_IDLE && timer0_100.result === 0,
    'state=' + timer0_100.state);

// Launch is back-interpolated: speed crossed the zero-snap threshold (1.5)
// 30% of the way between the stopped fix @1000ms and the 5 km/h fix @2000ms
// => start = 1000 + 0.3*1000 = 1300 ms, not the raw fix timestamp 2000.
updateTimers(5, 2, 2000);
__ok('t0_100: launch arms RUNNING with interpolated start timestamp',
    timer0_100.state === T_RUNNING && nearly(timer0_100.start, 1300, 1e-6),
    'state=' + timer0_100.state + ' start=' + timer0_100.start);

// Finish likewise lands between fixes: 100 km/h crossed 95/99 of the way
// from (5 @ 2000) to (104 @ 14500) => finish ~= 13994.949 ms.
var __expFinish = 2000 + (14500 - 2000) * (100 - 5) / (104 - 5);
updateTimers(104, 100, 14500);
__ok('t0_100: cross threshold -> DONE with interpolated elapsed',
    timer0_100.state === T_DONE && nearly(timer0_100.result, __expFinish - 1300, 1e-6),
    'state=' + timer0_100.state + ' result=' + timer0_100.result + ' expected=' + (__expFinish - 1300));

// 0-100 abort: launch, stop mid-run -> IDLE without overwriting result
__resetTimers();
updateTimers(5, 2, 1000);
updateTimers(0, 5, 5000);
__ok('t0_100: abort on stop returns IDLE without writing result',
    timer0_100.state === T_IDLE && timer0_100.result === 0,
    'state=' + timer0_100.state + ' result=' + timer0_100.result);

// 0-100: once DONE, stopping must NOT clear the result. (Documented behaviour:
// a completed sprint keeps its value until RESET RUN clears it manually.)
__resetTimers();
updateTimers(5, 1, 1000);      // arms from rest (no prior sample) -> start = 1000
updateTimers(105, 80, 7000);   // 100 crossed 95% of (5@1000 -> 105@7000): result ~= 5700
updateTimers(0, 82, 15000);
__ok('t0_100: completed result is preserved across a subsequent stop (DONE retained)',
    timer0_100.state === T_DONE && nearly(timer0_100.result, 5700, 1e-6),
    'state=' + timer0_100.state + ' result=' + timer0_100.result);

// Note: as written, the 0-60/0-100 state machine does NOT auto-re-arm after a
// DONE result; the user must hit RESET RUN to capture a second sprint. This is
// intentional (see the comment in updateTimers), but it's an inconsistency with
// the 100-200 / 100-0 machines, which DO mesh down to T_IDLE on stop.
__ok('t100_200 vs t0_100 re-arm asymmetry documented',
    true,
    '100-200 resets DONE->IDLE on stop; 0-60/0-100 retain DONE until RESET');

// 100-200: must NOT arm before 100, arms at exactly 100, completes at 200
__resetTimers();
updateTimers(99, 5, 1000);
__ok('t100_200: stays IDLE below 100',
    timer100_200.state === T_IDLE,
    'state=' + timer100_200.state);
updateTimers(100, 6, 2000);
updateTimers(150, 60, 3000);
__ok('t100_200: arms at >= 100 -> RUNNING, stays RUNNING at 150',
    timer100_200.state === T_RUNNING && timer100_200.start === 2000,
    'state=' + timer100_200.state);
updateTimers(205, 200, 6000);
// 200 crossed 50/55 of the way from (150 @ 3000) to (205 @ 6000)
__ok('t100_200: cross 200 -> DONE with interpolated elapsed',
    timer100_200.state === T_DONE && nearly(timer100_200.result, 3000 + 3000 * 50 / 55 - 2000, 1e-6),
    'state=' + timer100_200.state + ' result=' + timer100_200.result);

// 1/4 mile: arms on launch, completes only when distance delta >= 402.336 m
__resetTimers();
updateTimers(5, 0, 1000);
__ok('tQuarter: arm from rest sets start AND startDist',
    timerQuarter.state === T_RUNNING && nearly(timerQuarter.start, 1000, 1e-6) && timerQuarter.startDist === 0,
    'state=' + timerQuarter.state + ' start=' + timerQuarter.start + ' startDist=' + timerQuarter.startDist);
updateTimers(50, 300, 4000);
__ok('tQuarter: distance < quarter mile -> still RUNNING',
    timerQuarter.state === T_RUNNING,
    'state=' + timerQuarter.state);
// 402.336 m crossed 102.336/200 of the way from (300 m @ 4000) to (500 m @ 11000)
// finish ~= 7581.76 ms minus the interpolated launch at 1000 ms
var __expQ = (4000 + 7000 * (402.336 - 300) / 200) - 1000;
updateTimers(120, 500, 11000);
__ok('tQuarter: once distance delta >= 402.336 m -> DONE with interpolated elapsed',
    timerQuarter.state === T_DONE && nearly(timerQuarter.result, __expQ, 1e-6),
    'state=' + timerQuarter.state + ' result=' + timerQuarter.result + ' expected=' + __expQ);

// 100-0 braking: only arms at cruise >= 100, records distance traveled to stop
__resetTimers();
updateTimers(80, 0, 1000);
__ok('t100_0: below 100 -> stays IDLE',
    timer100_0.state === T_IDLE,
    'state=' + timer100_0.state);
updateTimers(110, 50, 2000);
__ok('t100_0: cruise >= 100 arms RUNNING with startDist',
    timer100_0.state === T_RUNNING && timer100_0.startDist === 50 && timer100_0.start === 2000,
    'state=' + timer100_0.state + ' startDist=' + timer100_0.startDist);
// Stop point rewinds to the speed-snap crossing (108.5/110 between fixes) and
// walks distance back along the segment: ~414.95 m => braking dist ~= 364.95 m
var __expBrake = (50 + 370 * (110 - SPEED_ZERO_SNAP_KMPH) / 110) - 50;
updateTimers(0, 420, 30000);
__ok('t100_0: stop -> DONE with interpolated positive braking distance',
    timer100_0.state === T_DONE && nearly(timer100_0.result, __expBrake, 1e-6),
    'state=' + timer100_0.state + ' result=' + timer100_0.result + ' expected=' + __expBrake);

// Sub-sample precision sanity check: a launch+finish straddling three fixes
// must land strictly between fix timestamps (old quantised code gave 2000 ms).
__resetTimers();
updateTimers(1, 0, 5000);     // stopped sample
updateTimers(51, 5, 7000);    // launch rewound to t=5020; still running
updateTimers(101, 40, 9000);  // finish rewound to t=8960
__ok('interpolation: threshold crossings land between fixes (3940ms, not 2000ms)',
    timer0_100.state === T_DONE && nearly(timer0_100.result, 3940, 1e-6),
    'result=' + timer0_100.result);

// === Tests: GPS session preservation (frequent SIGNAL LOSS fix) ===
// Mirrored verbatim in tests/telemetry.test.js; ES5-only (dukpy fallback).
var __pendingTimers = [];
setTimeout = function(fn, ms) { __pendingTimers.push({ fn: fn, ms: ms }); return __pendingTimers.length; };
var __geoSpy = { watch: 0, clear: 0 };
navigator.geolocation = {
  watchPosition: function() { __geoSpy.watch++; return 1000 + __geoSpy.watch; },
  clearWatch: function() { __geoSpy.clear++; }
};
function __mkErr(code) { return { code: code, PERMISSION_DENIED: 1, POSITION_UNAVAILABLE: 2, TIMEOUT: 3 }; }
function __resetGeo() { __geoSpy.watch = 0; __geoSpy.clear = 0; __pendingTimers.length = 0; gpsRetryPending = false; gpsFailCount = 0; lastGpsTime = -1; }
__ok('gpsBackoff: 5s,10s,20s,30s cap',
    gpsBackoffDelay(0) === 5000 && gpsBackoffDelay(1) === 10000 && gpsBackoffDelay(2) === 20000 && gpsBackoffDelay(3) === 30000 && gpsBackoffDelay(99) === 30000 && gpsBackoffDelay(-5) === 5000,
    'got ' + gpsBackoffDelay(0) + ',' + gpsBackoffDelay(1) + ',' + gpsBackoffDelay(2) + ',' + gpsBackoffDelay(3));
__resetGeo(); onPositionError(__mkErr(3));
__ok('gpsErr: TIMEOUT never tears down the warm watch',
    __geoSpy.clear === 0 && __geoSpy.watch === 0 && __pendingTimers.length === 0,
    'clear=' + __geoSpy.clear + ' watch=' + __geoSpy.watch + ' pending=' + __pendingTimers.length);
__ok('gpsErr: TIMEOUT still surfaces status',
    String(prev.status).indexOf('TIMEOUT') !== -1,
    'status=' + prev.status);
__resetGeo(); onPositionError(__mkErr(2)); onPositionError(__mkErr(2)); onPositionError(__mkErr(2));
__ok('gpsErr: repeat UNAVAILABLE schedules exactly one recovery',
    __pendingTimers.length === 1 && __geoSpy.clear === 0 && __geoSpy.watch === 0,
    'pending=' + __pendingTimers.length);
__ok('gpsErr: first retry is fast (5s)',
    __pendingTimers[0].ms === 5000,
    'ms=' + (__pendingTimers[0] && __pendingTimers[0].ms));
lastGpsTime = -99999; gpsWatchId = 7; var __recFn = __pendingTimers[0].fn; __recFn();
__ok('gpsErr: recovery replaces watch once and frees the slot',
    __geoSpy.watch === 1 && __geoSpy.clear === 1 && gpsRetryPending === false,
    'watch=' + __geoSpy.watch + ' clear=' + __geoSpy.clear);
__resetGeo(); onPositionError(__mkErr(1));
__ok('gpsErr: PERMISSION_DENIED schedules nothing, kills nothing',
    __pendingTimers.length === 0 && __geoSpy.clear === 0 && __geoSpy.watch === 0,
    'pending=' + __pendingTimers.length);
__resetGeo(); onPositionError({}); onPositionError(null); onPositionError(undefined);
__ok('gpsErr: malformed errors are inert',
    __pendingTimers.length === 0 && __geoSpy.clear === 0,
    'pending=' + __pendingTimers.length);

// === Tests: velocity estimator (lsVelocity + Kalman/NIS/teleport via onPositionSuccess) ===
// ES5-only, mirrored verbatim in tests/telemetry.test.js. Drives the real fix path with a
// controllable clock + synthetic Doppler fixes on a north-bound straight line.
var __t = 10000;
performance.now = function () { return __t; };
var __MPD = 6371000 * Math.PI / 180; // meters per degree of latitude
var __lat = 40.0;

function __resetEst() {
  fixWindow = []; kalmanV = 0; kalmanP = 1; kalmanInit = false; prevKalmanV = 0;
  outlierTimeSec = 0; seedSettle = 0; lastFixClean = true; gpsLongGSm = 0; gpsLatGSm = 0; lastPosTs = -1; fixLog = [];
  driftWindow = []; driftBad = false; driftBadT0 = 0; driftOkT0 = 0; driftDismissed = false;
  lastAcc = null; nisEma = 1.0; zuptStillMs = 0; innovHist = []; stopStillN = 0; stopLatched = false;
  currentSpeedMs = 0; displaySpeedMs = 0; distanceMeters = 0; prevGpsSpeedMs = 0;
  lastGpsTime = -1; lastUsableGpsTime = -1;
  lastGpsLat = undefined; lastGpsLon = undefined; lastGpsHeading = undefined;
  gpsGlitchCount = 0; gpsHzSmooth = 0; lastGpsConfidence = 0;
  imuFusionActive = false; lastImuTime = 0;
  fusedLongG = 0; fusedLatG = 0; imuLongG = 0; imuLatG = 0; imuLongGBias = 0; imuLatGBias = 0;
  lastTimerSpeedKmh = NaN; lastTimerDistM = NaN; lastTimerTimeMs = NaN;
  maxSpeedKmph = 0; maxGpsAccelG = 0; maxGpsLatG = 0; bestGpsBrakingG = 0;
  pendingMaxKmph = 0;
  motionListening = false; motionListenSince = 0; lastMotionKick = 0; lastMotionCheck = 0;
  peakAccArmT = 0; peakBrkArmT = 0; peakLatArmT = 0;
  mountYawMode = 0; mountOffsetY = 0; filteredAccelY = 0; gravSmX = 0; gravSmY = 0; gravSmZ = 0; orientStillN = 0; orientSnapped = false; mountLatSign = 1; latSignAgree = 0; latSignDis = 0;
  __t = 10000; __lat = 40.0;
}

function __coords(speedMs, dtSec, acc, jumpM) {
  __t += dtSec * 1000;
  __lat += (jumpM === undefined ? (speedMs || 0) * dtSec : jumpM) / __MPD;
  return { coords: { latitude: __lat, longitude: 0, accuracy: (acc === undefined ? 5 : acc), altitudeAccuracy: null, speed: speedMs, speedAccuracy: 0.5 } };
}

function __win(times, meters, accs) {
  var out = [], i;
  for (i = 0; i < times.length; i++) out.push({ t: times[i], lat: meters[i] / __MPD, lon: 0, acc: accs[i] });
  return out;
}

// --- lsVelocity: pure weighted least-squares ---
var __vLin = lsVelocity(__win([0, 1, 2, 3], [0, 20, 40, 60], [5, 5, 5, 5]));
__ok('lsVelocity: straight-line 20 m/s -> ~20', __vLin !== null && Math.abs(__vLin - 20) < 0.05, 'got ' + __vLin);

__ok('lsVelocity: span < LS_MIN_SPAN -> null', lsVelocity(__win([0, 0.1], [0, 5], [5, 5])) === null, '');
__ok('lsVelocity: single anchor -> null', lsVelocity(__win([0], [0], [5])) === null, '');
__ok('lsVelocity: empty window -> null', lsVelocity([]) === null, '');

// 1/acc^2 discount: a 100 m outlier anchor must not drag the slope off the clean 30 m/s line.
var __vW = lsVelocity(__win([0, 1, 2, 3], [0, 30, 60, 160], [5, 5, 5, 100]));
var __vU = lsVelocity(__win([0, 1, 2, 3], [0, 30, 60, 160], [5, 5, 5, 5]));
__ok('lsVelocity: 1/acc^2 discount keeps slope on clean line (~30)', __vW !== null && Math.abs(__vW - 30) < 5, 'weighted=' + __vW);
__ok('lsVelocity: unweighted 100m outlier drags slope (proves the weight)', __vU !== null && Math.abs(__vU - 30) > 15, 'uniform=' + __vU);

// --- Kalman: constant-speed convergence + NIS outlier spike rejection ---
__resetEst();
onPositionSuccess(__coords(0, 1));      // seed stationary
onPositionSuccess(__coords(4, 1));
onPositionSuccess(__coords(8, 1));
onPositionSuccess(__coords(12, 1));
onPositionSuccess(__coords(16, 1));
onPositionSuccess(__coords(20, 1));
onPositionSuccess(__coords(20, 1));
onPositionSuccess(__coords(20, 1));     // settle
__ok('kalman: constant 20 m/s Doppler converges near true speed', currentSpeedMs > 15 && currentSpeedMs < 22, 'currentSpeedMs=' + currentSpeedMs);

var __gS = gpsGlitchCount;
onPositionSuccess(__coords(120, 1));    // lone spike
__ok('kalman: single 120 m/s spike is NIS-rejected (coasts, no snap)', Math.abs(currentSpeedMs - 20) < 8, 'currentSpeedMs=' + currentSpeedMs);
__ok('kalman: spike increments the glitch counter', gpsGlitchCount > __gS, 'glitch=' + gpsGlitchCount);

// --- Teleport: a jump no car could cover must hold, not seed a speed bump ---
__resetEst();
onPositionSuccess(__coords(0, 1));
onPositionSuccess(__coords(4, 1));
onPositionSuccess(__coords(8, 1));
onPositionSuccess(__coords(12, 1));
onPositionSuccess(__coords(16, 1));
onPositionSuccess(__coords(20, 1));
onPositionSuccess(__coords(20, 1));
var __gt = gpsGlitchCount;
var __held = currentSpeedMs;
onPositionSuccess(__coords(20, 1, 5, 5000));   // 5 km hop in 1 s
__ok('teleport: 5 km position jump is held (speed unchanged)', Math.abs(currentSpeedMs - __held) < 1e-9, 'before=' + __held + ' after=' + currentSpeedMs);
__ok('teleport: jump increments the glitch counter', gpsGlitchCount > __gt, 'glitch=' + gpsGlitchCount);
__ok('teleport: Kalman not poisoned by the jump (still initialized & finite)', kalmanInit === true && isFinite(kalmanV), 'kalmanInit=' + kalmanInit + ' kalmanV=' + kalmanV);

// --- P1a: 10 Hz window keeps the full 3 s baseline (was count-capped at 12 = 1.2 s) ---
__resetEst();
onPositionSuccess(__coords(0, 0.1));
var __hz = [2, 4, 6, 8, 10, 12, 14, 16, 18, 20];
for (var __k = 0; __k < __hz.length; __k++) onPositionSuccess(__coords(__hz[__k], 0.1));
for (var __m = 0; __m < 30; __m++) onPositionSuccess(__coords(20, 0.1));
__ok('window: 10 Hz keeps full 3 s baseline (>12, <=30)', fixWindow.length > 12 && fixWindow.length <= 30, 'len=' + fixWindow.length);
__ok('window: 10 Hz converges near true speed', Math.abs(currentSpeedMs - 20) < 3, 'currentSpeedMs=' + currentSpeedMs);

// --- P1b: post-seed settle halves the first steps (gradual lock, no snap) ---
__resetEst();
onPositionSuccess(__coords(0, 1));       // seed stationary
onPositionSuccess(__coords(12, 1, 5, 6));   // UNCONFIRMED 12 m/s step (positions say 6): NIS-clean, old slew allowed ~11.5
__ok('settle: unconfirmed seed step locks gradually (<9, not ~11.5)', currentSpeedMs > 5 && currentSpeedMs < 9, 'currentSpeedMs=' + currentSpeedMs);
onPositionSuccess(__coords(12, 1));
onPositionSuccess(__coords(12, 1));
__ok('settle: counter consumed after 2 updates', seedSettle === 0, 'seedSettle=' + seedSettle);

// --- P1c: LS collapse coasts on prediction (never replays a stale measurement) ---
__resetEst();
kalmanV = 20; prevKalmanV = 20; kalmanP = 1; kalmanInit = true;
prevGpsSpeedMs = 99;             // stale garbage measurement
lastFixClean = true; outlierTimeSec = 0;
fixWindow = [{ t: __t / 1000 - 10, lat: __lat, lon: 0, acc: 5 }];  // aged out -> collapse
lastGpsLat = __lat; lastGpsLon = 0;
lastGpsTime = __t; lastUsableGpsTime = __t;  // normal path (dt=1), not first-fix
var __g0 = gpsGlitchCount;
onPositionSuccess(__coords(null, 1));   // non-Doppler, same spot
__ok('collapse: stale vMeas not replayed (no glitch, still clean)', gpsGlitchCount === __g0 && lastFixClean === true, 'glitch=' + gpsGlitchCount);
__ok('collapse: speed coasts on prediction (exactly 20)', currentSpeedMs === 20, 'currentSpeedMs=' + currentSpeedMs);

// --- Soft jump: medium non-Doppler jump is damped, not bumped ---
__resetEst();
onPositionSuccess(__coords(0, 1));
onPositionSuccess(__coords(4, 1));
onPositionSuccess(__coords(8, 1));
onPositionSuccess(__coords(12, 1));
onPositionSuccess(__coords(16, 1));
onPositionSuccess(__coords(20, 1));
onPositionSuccess(__coords(20, 1));
var __sj = gpsGlitchCount;
var __sp0 = currentSpeedMs;
onPositionSuccess(__coords(null, 1, 5, 38));   // +38 m in 1 s, no Doppler (soft band)
onPositionSuccess(__coords(null, 1, 5, 20));   // follow-up, back on the line
__ok('softjump: medium jump counted as filtered', gpsGlitchCount > __sj, 'glitch=' + gpsGlitchCount);
__ok('softjump: no speed bump from +38 m jump (+follow-up)', Math.abs(currentSpeedMs - 20) < 2.5, 'currentSpeedMs=' + currentSpeedMs + ' was ' + __sp0);

// --- Doppler/delta veto tightened 12 -> 8 m/s ---
__resetEst();
onPositionSuccess(__coords(0, 1));
onPositionSuccess(__coords(4, 1));
onPositionSuccess(__coords(8, 1));
onPositionSuccess(__coords(12, 1));
onPositionSuccess(__coords(16, 1));
onPositionSuccess(__coords(20, 1));
onPositionSuccess(__coords(20, 1));
var __mm = gpsGlitchCount;
var __mv = currentSpeedMs;
var __mu = lastUsableGpsTime;
onPositionSuccess(__coords(20, 1, 5, 30));   // +30 m but Doppler says 20 (10 m/s apart)
__ok('doppler-veto: 10 m/s split counted, no snap (<0.5, still ~20)', gpsGlitchCount > __mm && Math.abs(currentSpeedMs - __mv) < 0.5 && Math.abs(currentSpeedMs - 20) < 1.0, 'glitch=' + gpsGlitchCount + ' before=' + __mv + ' after=' + currentSpeedMs);
__ok('doppler-veto: steady Doppler keeps the fix usable', lastUsableGpsTime > __mu, 'usable=' + lastUsableGpsTime);

// --- Mismatch + jumping Doppler: contradiction still hard-holds ---
__resetEst();
onPositionSuccess(__coords(0, 1));
onPositionSuccess(__coords(4, 1));
onPositionSuccess(__coords(8, 1));
onPositionSuccess(__coords(12, 1));
onPositionSuccess(__coords(16, 1));
onPositionSuccess(__coords(20, 1));
onPositionSuccess(__coords(20, 1));
var __jm = gpsGlitchCount;
var __jv = currentSpeedMs;
onPositionSuccess(__coords(40, 1, 5, 10));   // Doppler 40, delta 10: split 30, Doppler not steady
__ok('mismatch-jump: contradiction hard-holds (byte-identical)', gpsGlitchCount > __jm && Math.abs(currentSpeedMs - __jv) < 1e-9, 'glitch=' + gpsGlitchCount + ' before=' + __jv + ' after=' + currentSpeedMs);

// --- GPS-G sample EMA: one +1.5G sample must not stair the fused estimate ---
__resetEst();
imuFusionActive = true; imuLongG = 0; imuLongGBias = 0; imuLatG = 0; imuLatGBias = 0;
fusedLongG = 0; fusedLatG = 0; gpsLongGSm = 0; gpsLatGSm = 0;
updateImuFusionFromGps(1.5, 0, 1.0, 1.0);
__ok('fusion-ema: single GPS-G sample is smoothed (<0.15, not 0.18)', fusedLongG < 0.15, 'fusedLongG=' + fusedLongG);
__ok('fusion-ema: EMA state tracks the sample', Math.abs(gpsLongGSm - 1.5 * (1 - Math.exp(-1 / 0.8))) < 1e-9, 'gpsLongGSm=' + gpsLongGSm);

// --- RECORD_QUALITY_MIN: mediocre fixes drive the needle, not the records ---
__resetEst();
__resetTimers();   // timer state leaks across scenarios (DONE is retained by design)
onPositionSuccess(__coords(0, 1, 19));
onPositionSuccess(__coords(8, 1, 19));
onPositionSuccess(__coords(16, 1, 19));
onPositionSuccess(__coords(24, 1, 19));
onPositionSuccess(__coords(32, 1, 19));
onPositionSuccess(__coords(40, 1, 19));
__ok('records: 19 m-accuracy fixes drive live speed (~40)', Math.abs(currentSpeedMs - 40) < 6, 'currentSpeedMs=' + currentSpeedMs);
__ok('records: ...but not timers/MAX', timer0_100.state === T_IDLE && maxSpeedKmph === 0, 'tstate=' + timer0_100.state + ' max=' + maxSpeedKmph);
onPositionSuccess(__coords(40, 1, 8));
__ok('records: 8 m fix arms timers (MAX needs one confirm)', timer0_100.state === T_RUNNING && maxSpeedKmph === 0, 'tstate=' + timer0_100.state + ' max=' + maxSpeedKmph);
onPositionSuccess(__coords(40, 1, 8));
__ok('records: second 8 m fix latches MAX', maxSpeedKmph > 100, 'max=' + maxSpeedKmph);

// --- MAX confirmation: lone spike never latches, sustained climb does ---
__resetEst();
__resetTimers();
onPositionSuccess(__coords(0, 1));
onPositionSuccess(__coords(10, 1));
onPositionSuccess(__coords(20, 1));
onPositionSuccess(__coords(20, 1));
onPositionSuccess(__coords(20, 1));
__ok('maxconf: cruise latches MAX (~72)', maxSpeedKmph > 65 && maxSpeedKmph < 80, 'max=' + maxSpeedKmph);
onPositionSuccess(__coords(27.78, 1, 5, 27.78));   // lone 100 km/h spike, one fix
onPositionSuccess(__coords(20, 1));                 // back to cruise
__ok('maxconf: lone spike never latches', maxSpeedKmph < 90, 'max=' + maxSpeedKmph);
onPositionSuccess(__coords(32, 1, 5, 32));
onPositionSuccess(__coords(32, 1, 5, 32));
onPositionSuccess(__coords(32, 1, 5, 32));
__ok('maxconf: sustained climb latches (~115)', maxSpeedKmph > 110, 'max=' + maxSpeedKmph);

// --- Recency-weighted LS: exact on lines, current on ramps ---
var __rLin = lsVelocity(__win([0, 1, 2, 3], [0, 20, 40, 60], [5, 5, 5, 5]));
__ok('ls-recency: straight line still exact (~20)', __rLin !== null && Math.abs(__rLin - 20) < 0.05, 'got ' + __rLin);
var __rFit = lsFit(__win([0, 1, 2, 3], [0, 5, 20, 45], [5, 5, 5, 5]));
__ok('ls-recency: accel ramp reads near-current (>16 vs uniform 15, end truth 30)', __rFit !== null && __rFit.v > 16 && __rFit.v < 28, 'v=' + (__rFit && __rFit.v));
__ok('ls-recency: fit lag reported (<1.2 s, was ~1.5)', __rFit !== null && __rFit.lagSec > 0.4 && __rFit.lagSec < 1.2, 'lag=' + (__rFit && __rFit.lagSec));

// --- GPS-clock dt: delivery jitter must not corrupt intervals ---
__resetEst();
kalmanV = 20; prevKalmanV = 20; prevGpsSpeedMs = 20; currentSpeedMs = 20; kalmanInit = false;
lastGpsTime = __t; lastUsableGpsTime = __t;
lastPosTs = __t - 100;
lastGpsLat = __lat; lastGpsLon = 0;
__t += 1400; __lat += 20 / __MPD;   // truth 20 m/s on GPS clock; arrival jittered +0.4 s
var __stamp = __t - 500;
onPositionSuccess({ coords: { latitude: __lat, longitude: 0, accuracy: 5, altitudeAccuracy: null, speed: null, speedAccuracy: null }, timestamp: __stamp });
__ok('stamp-dt: seed uses GPS-clock interval (~20, not 20/1.4)', Math.abs(currentSpeedMs - 20) < 0.5, 'currentSpeedMs=' + currentSpeedMs);

// --- Settle exemption: IMU-confirmed launch is not clipped ---
__resetEst();
onPositionSuccess(__coords(0, 1));      // seed stationary
var __ex = __coords(12, 1);
lastImuTime = __t - 100; imuFusionActive = true; imuLongG = 0.5; imuLongGBias = 0; imuLatG = 0; imuLatGBias = 0;
onPositionSuccess(__ex);
__ok('settle-exempt: IMU-confirmed launch locks fast (>9, not ~7.9)', currentSpeedMs > 9, 'currentSpeedMs=' + currentSpeedMs);

// --- Parked slow path: 1 s cadence when calm, instant wake on input ---
var __rafN = 0;
requestAnimationFrame = function(){ __rafN++; };
__resetEst(); __resetTimers(); stateDirty = false;
lastGpsTime = __t - 20000; lastUsableGpsTime = __t - 20000;   // stale + calm
lastRenderTime = __t;
var __ptBefore = __pendingTimers.length;
renderLoop();
__ok('parked: calm loop parks on 1 s cadence (no RAF spin)', parkedSlow === true && __rafN === 0 && __pendingTimers.length > __ptBefore && __pendingTimers[__pendingTimers.length - 1].ms === 1000, 'parkedSlow=' + parkedSlow + ' raf=' + __rafN);
wakeRenderLoop();
__ok('parked: sensor wake resumes full rate at once', parkedSlow === false && __rafN === 1, 'parkedSlow=' + parkedSlow + ' raf=' + __rafN);
currentSpeedMs = 5; displaySpeedMs = 5; lastGpsTime = __t;
var __rafWas = __rafN;
renderLoop();
__ok('parked: motion never parks (RAF chain)', parkedSlow === false && __rafN === __rafWas + 1, 'parkedSlow=' + parkedSlow + ' raf=' + __rafN);

// --- Dual-agree launch: GPS-only violent step with agreeing observables ---
__resetEst();
onPositionSuccess(__coords(0, 1));      // seed stationary (Doppler, no IMU)
var __dg = gpsGlitchCount;
onPositionSuccess(__coords(16, 1));     // 0-58 km/h in one fix, positions agree
__ok('dual-agree: confirmed launch step not clipped (>14, settle exempt)', currentSpeedMs > 14 && lastFixClean === true, 'currentSpeedMs=' + currentSpeedMs);
__ok('dual-agree: confirmed step counted as clean (no glitch)', gpsGlitchCount === __dg, 'glitch=' + gpsGlitchCount);

// --- Dual-agree guard: lone Doppler spike without position support still coasts ---
__resetEst();
onPositionSuccess(__coords(0, 1));
onPositionSuccess(__coords(22, 1, 5, 16));   // Doppler 22, delta 16: split 6 (veto 8, agree 4)
__ok('dual-agree: single-observable spike still coasted', currentSpeedMs < 1 && lastFixClean === false, 'currentSpeedMs=' + currentSpeedMs);

// --- Establishment grace: non-Doppler pull-away locks (no veto-freeze) ---
__resetEst();
onPositionSuccess({ coords: { latitude: __lat, longitude: 0, accuracy: 5, altitudeAccuracy: null, speed: null, speedAccuracy: null } });
__t += 1000; __lat += 20 / __MPD;
onPositionSuccess({ coords: { latitude: __lat, longitude: 0, accuracy: 5, altitudeAccuracy: null, speed: null, speedAccuracy: null } });
__ok('coldstart: non-Doppler pull-away locks (no veto-freeze)', currentSpeedMs > 5, 'currentSpeedMs=' + currentSpeedMs);

// --- Phase-2 field log: bounded ring with estimator internals ---
for (var __li = 0; __li < 605; __li++) logFix({ t: __li });
__ok('fixlog: ring caps at 600 (oldest evicted)', fixLog.length === 600 && fixLog[0].t === 5 && fixLog[599].t === 604, 'len=' + fixLog.length);
__resetEst();
onPositionSuccess(__coords(0, 1));
onPositionSuccess(__coords(10, 1));
var __le = fixLog[fixLog.length - 1];
__ok('fixlog: seed/update entries carry flags + finite estimate', fixLog.length === 2 && fixLog[0].fl === 'DF' && __le.fl === 'DU' && isFinite(__le.kv), 'len=' + fixLog.length + ' fl=' + (fixLog[0] && fixLog[0].fl));
onPositionSuccess({ coords: { latitude: __lat, longitude: 0, accuracy: 99, altitudeAccuracy: null, speed: null, speedAccuracy: null } });
var __lw = fixLog[fixLog.length - 1];
__ok('fixlog: weak fixes logged with W flag', __lw.fl.indexOf('W') !== -1, 'fl=' + __lw.fl);

// --- Phase-1b mount-health: flags rattling mounts, ignores calm ones ---
function __mountState() {
  currentSpeedMs = 0; displaySpeedMs = 0; lastGpsConfidence = 0.9;
  lastUsableGpsTime = __t; lastGpsTime = __t;
  mountOffsetX = 0; mountOffsetZ = 0; imuLongGBias = 0; imuLatGBias = 0;
  mountN = 61; mountMeanL = 0; mountMeanT = 0; mountVarL = 0; mountVarT = 0;
  mountBad = false; mountBadT0 = 0; mountOkT0 = 0; mountDismissed = false;
  lastImuTime = 0;
}
function __shake(n, amp) {
  for (var i = 0; i < n; i++) { __t += 100; handleMotion({ acceleration: { x: 0, z: (i % 2 ? amp : -amp) } }); }
}
__mountState();
__shake(10, 30); __t += 3000; __shake(10, 30); __t += 3000; __shake(10, 30);
__ok('mount: rattling mount flagged after sustained noise', mountBad === true, 'mountBad=' + mountBad);
__mountState();
__shake(40, 0);
__ok('mount: calm mount stays clear (learn path ran)', mountBad === false && mountN === 101, 'mountBad=' + mountBad + ' n=' + mountN);
mountBad = true; mountBadT0 = 0; mountOkT0 = 0; mountVarL = 0.002; mountVarT = 0.002;
__shake(25, 0); __t += 4000; __shake(25, 0);
__ok('mount: recovers when vibration stops', mountBad === false, 'mountBad=' + mountBad);

// --- Phase-1a GPS-only hint advertises tap-to-enable motion ---
imuFusionActive = false;
DeviceMotionEvent = { requestPermission: function(){} };
updateFusionStatusUI();
__ok('fusion-hint: GPS-only advertises tap-to-enable motion', String(dom.fusionStatus.title).indexOf('motion') !== -1, 'title=' + dom.fusionStatus.title);
imuFusionActive = true;
updateFusionStatusUI();
__ok('fusion-hint: grant clears the hint affordance', String(dom.fusionStatus.title) === '', 'title=' + dom.fusionStatus.title);
imuFusionActive = false;
DeviceMotionEvent = undefined;

// --- Phase 4.1 ZUPT: still IMU+GPS gates kill creep, moving does not ---
__resetEst();
onPositionSuccess(__coords(5, 1, 5));
onPositionSuccess(__coords(5, 1, 5));
imuFusionActive = true; fusedLongG = 0.02; fusedLatG = 0.01; imuLongG = 0.02; imuLatG = 0.01; imuLongGBias = 0; imuLatGBias = 0;
currentSpeedMs = 0.15; kalmanV = 0.15; prevKalmanV = 0.15; kalmanP = 1.0; distanceMeters = 10; zuptStillMs = 600;
var __zf = __coords(0.15, 1, 5); lastImuTime = __t; onPositionSuccess(__zf);
__ok('zupt: sustained still zeros creep + freezes distance', currentSpeedMs === 0 && kalmanV === 0 && distanceMeters === 10, 'currentSpeedMs=' + currentSpeedMs + ' kalmanV=' + kalmanV + ' dist=' + distanceMeters);
__resetEst();
onPositionSuccess(__coords(5, 1, 5));
onPositionSuccess(__coords(5, 1, 5));
imuFusionActive = true; fusedLongG = 0.5; fusedLatG = 0; imuLongG = 0.5; imuLatG = 0;
currentSpeedMs = 0.35; kalmanV = 0.35; prevKalmanV = 0.35; kalmanInit = true; zuptStillMs = 600;
var __zm = __coords(0.2, 1, 5); lastImuTime = __t; onPositionSuccess(__zm);
__ok('zupt: moving IMU does not zero', currentSpeedMs > 0, 'currentSpeedMs=' + currentSpeedMs);

// --- Phase 4.2 Adaptive R: NIS EMA tracks noise, bounded ---
__resetEst();
onPositionSuccess(__coords(0, 1));
onPositionSuccess(__coords(4, 1));
onPositionSuccess(__coords(8, 1));
onPositionSuccess(__coords(12, 1));
onPositionSuccess(__coords(16, 1));
onPositionSuccess(__coords(20, 1));
onPositionSuccess(__coords(20, 1));
var __nis0 = nisEma;
onPositionSuccess(__coords(22, 1));
onPositionSuccess(__coords(18, 1));
onPositionSuccess(__coords(22, 1));
onPositionSuccess(__coords(18, 1));
__ok('adapt-R: noisy run moves EMA (bounded)', nisEma !== __nis0 && nisEma >= 0.3 && nisEma <= 4.0, 'nis0=' + __nis0 + ' nis=' + nisEma);
__ok('adapt-R: scale applied (R scaled, not NaN)', isFinite(nisEma), 'nisEma=' + nisEma);

// --- Phase 4.3 Drift monitor: 30 s LS vs Kalman honesty ---
__resetEst();
onPositionSuccess(__coords(0, 1, 5));
for (var __di = 0; __di < 32; __di++) {
  __t += 1000;
  __lat += 14 / __MPD;
  onPositionSuccess({ coords: { latitude: __lat, longitude: 0, accuracy: 5, altitudeAccuracy: null, speed: 20, speedAccuracy: 0.5 } });
}
__ok('drift: sustained Doppler/LS divergence flags degraded', driftBad === true, 'driftBad=' + driftBad);
__ok('drift: degraded tightens records (15 m now blocked)', (function(){ var __m0 = maxSpeedKmph; onPositionSuccess({ coords: { latitude: __lat + 20/__MPD, longitude:0, accuracy:15, altitudeAccuracy:null, speed:20, speedAccuracy:0.5 } }); return maxSpeedKmph === __m0; })(), 'max=' + maxSpeedKmph);

// --- Phase 4.4 Provider switch: accuracy jump quarantines one fix ---
__resetEst();
onPositionSuccess(__coords(10, 1, 5));
onPositionSuccess(__coords(10, 1, 5));
var __pLen = fixLog.length;
onPositionSuccess(__coords(10, 1, 20));
var __pFl = fixLog[fixLog.length - 1].fl;
__ok('provider: large acc jump flagged P', __pFl.indexOf('P') !== -1, 'fl=' + __pFl);
__ok('provider: quarantine holds (next fix still needs confirm)', (function(){ onPositionSuccess(__coords(10, 1, 20)); return fixLog[fixLog.length-1].fl.indexOf('P') === -1; })(), 'fl=' + fixLog[fixLog.length-1].fl);

// --- Cruise damping: median |innov| scales Q (acc=15, the noisy case) ---
__resetEst();
onPositionSuccess(__coords(0, 1, 15));
for (var __qi = 0; __qi < 12; __qi++) onPositionSuccess(__coords(20, 1, 15));
var __qk = fixLog[fixLog.length - 1].k;
__ok('damp: steady cruise lowers gain (<0.65, undamped ~0.74)', __qk < 0.65, 'k=' + __qk);
onPositionSuccess(__coords(30, 1, 15));
var __qkR = fixLog[fixLog.length - 1].k;
__ok('damp: confirmed maneuver restores full gain', __qkR > 0.65, 'k=' + __qkR);
for (var __qr = 0; __qr < 8; __qr++) onPositionSuccess(__coords(30, 1, 15));
var __qk2 = fixLog[fixLog.length - 1].k;
__ok('damp: re-damps on new cruise (no latch-up)', __qk2 < 0.65, 'k=' + __qk2);

// --- Stopped snap: Doppler-0 + static + low estimate reads 0 fast ---
__resetEst();
onPositionSuccess(__coords(0, 1));
onPositionSuccess(__coords(5, 1));
onPositionSuccess(__coords(10, 1));
onPositionSuccess(__coords(15, 1));
onPositionSuccess(__coords(20, 1));
onPositionSuccess(__coords(20, 1));
onPositionSuccess(__coords(0, 1, 5, 0.5));
__ok('stopsnap: no snap on first stopped fix (needs confirm)', currentSpeedMs > 3, 'currentSpeedMs=' + currentSpeedMs);
onPositionSuccess(__coords(0, 1, 5, 0.5));
onPositionSuccess(__coords(0, 1, 5, 0.5));
__ok('stopsnap: confirmed stop snaps estimator + display to 0', currentSpeedMs === 0 && displaySpeedMs === 0, 'currentSpeedMs=' + currentSpeedMs + ' display=' + displaySpeedMs);
__ok('stopsnap: latch engaged on snap', stopLatched === true, 'stopLatched=' + stopLatched);
onPositionSuccess(__coords(0, 1, 5, 0.5));
onPositionSuccess(__coords(0, 1, 5, 0.5));
__ok('stopsnap: latched stop stays 0 (no blink)', currentSpeedMs === 0 && displaySpeedMs === 0, 'currentSpeedMs=' + currentSpeedMs + ' display=' + displaySpeedMs);

// --- Stopped snap: crawling (~1 m/s Doppler) never snaps ---
__resetEst();
onPositionSuccess(__coords(0, 1));
onPositionSuccess(__coords(5, 1));
onPositionSuccess(__coords(10, 1));
onPositionSuccess(__coords(1, 1));
onPositionSuccess(__coords(1, 1));
onPositionSuccess(__coords(1, 1));
onPositionSuccess(__coords(1, 1));
__ok('stopsnap: 1 m/s crawl keeps tracking (no false zero)', currentSpeedMs > 0.5, 'currentSpeedMs=' + currentSpeedMs);

// --- Stopped snap: non-Doppler static also snaps (slower arm) ---
__resetEst();
onPositionSuccess(__coords(0, 1));
for (var __si = 0; __si < 6; __si++) onPositionSuccess(__coords(20, 1, 5, 20));
for (var __sj = 0; __sj < 10; __sj++) onPositionSuccess(__coords(null, 1, 5, 0.2));
__ok('stopsnap: non-Doppler standstill stays bounded, no blink', currentSpeedMs < 0.3 && stopLatched === true, 'currentSpeedMs=' + currentSpeedMs);

// --- Ring signal cue: gauge mirrors GNSS tiers (lost red / weak amber) ---
__resetEst(); __resetTimers(); stateDirty = false;
__t += 30000;   // keep lastGpsTime positive (acquired) yet stale
lastGpsTime = __t - 20000; lastUsableGpsTime = __t - 20000;   // stale, no coast
lastRenderTime = __t;
renderLoop();
__ok('ringsig: stale GNSS sets sig-lost on the gauge', dom.speedGauge.classList._t['sig-lost'] === true && dom.speedGauge.classList._t['sig-weak'] !== true, 't=' + JSON.stringify(dom.speedGauge.classList._t));
lastGpsTime = __t; lastUsableGpsTime = __t; lastGpsConfidence = 0.9;
renderLoop();
__ok('ringsig: fresh FIX clears to no class', dom.speedGauge.classList._t['sig-lost'] === false && dom.speedGauge.classList._t['sig-weak'] === false, 't=' + JSON.stringify(dom.speedGauge.classList._t));
lastGpsConfidence = 0.1;
renderLoop();
__ok('ringsig: fresh WEAK sets sig-weak (not lost)', dom.speedGauge.classList._t['sig-weak'] === true && dom.speedGauge.classList._t['sig-lost'] === false, 't=' + JSON.stringify(dom.speedGauge.classList._t));

// --- Motion lifecycle: tracked attach, permission-aware, watchdog ---
window.DeviceMotionEvent = {};
__ok('motion: no permission API + DME present -> should be on', motionShouldBeOn() === true, '');
DeviceMotionEvent = { requestPermission: function(){} };
__lsStore[IOS_CHOICE_KEY] = JSON.stringify({ s: '1', t: Date.now() });
__ok('motion: stored grant -> should be on', motionShouldBeOn() === true, '');
__lsStore[IOS_CHOICE_KEY] = JSON.stringify({ s: '0', t: Date.now() });
__ok('motion: fresh denial -> should be off', motionShouldBeOn() === false, '');
window.DeviceMotionEvent = undefined;
__ok('motion: no hardware -> should be off', motionShouldBeOn() === false, '');
DeviceMotionEvent = undefined;
var __addN = 0, __remN = 0;
window.addEventListener = function(){ __addN++; };
window.removeEventListener = function(){ __remN++; };
window.DeviceMotionEvent = {};
setMotionListening(false); setMotionListening(true); setMotionListening(true);
__ok('motion: setter dedups attach', __addN === 1, 'adds=' + __addN);
setMotionListening(false); setMotionListening(false);
__ok('motion: setter dedups detach', __remN === 1, 'rems=' + __remN);
__lsStore[IOS_CHOICE_KEY] = JSON.stringify({ s: '0', t: Date.now() - 2592000001 });
__ok('motion: stale denial re-asks (not denied forever)', getIosChoice() === 'expired-deny', 'got=' + getIosChoice());
__lsStore[IOS_CHOICE_KEY] = JSON.stringify({ s: '0', t: Date.now() });
__ok('motion: fresh denial stays denied', getIosChoice() === 'denied', 'got=' + getIosChoice());
delete __lsStore[IOS_CHOICE_KEY];
__ok('motion: no record asks (unknown, not denied)', getIosChoice() === 'unknown', 'got=' + getIosChoice());
__resetEst(); __resetTimers(); stateDirty = false;
window.DeviceMotionEvent = {};
setMotionListening(false);
lastImuTime = 0; imuFusionActive = false;
lastGpsTime = __t - 20000; lastUsableGpsTime = __t - 20000;
lastRenderTime = __t; lastMotionCheck = 0; lastMotionKick = 0;
setMotionListening(true);
var __wkA = __addN, __wkR = __remN;
__t += 20000;
renderLoop();
__ok('motion: watchdog kicks silent subscription', __remN > __wkR && __addN > __wkA && motionListening === true && lastMotionKick === __t, 'adds=' + __addN + ' rems=' + __remN);
window.DeviceMotionEvent = undefined;
// --- Motion resume: refocus/bfcache re-attach without a full watchdog wait ---
window.DeviceMotionEvent = {};
setMotionListening(false);
var __rmA = __addN;
resumeMotion();
__ok('motion: resume re-attaches when should-be-on', __addN > __rmA && motionListening === true, 'adds=' + __addN);
window.DeviceMotionEvent = undefined;
setMotionListening(false);
var __rmA2 = __addN;
resumeMotion();
__ok('motion: resume stays off without hardware', __addN === __rmA2 && motionListening === false, 'adds=' + __addN);
DeviceMotionEvent = { requestPermission: function(){} };
window.DeviceMotionEvent = {};
setMotionListening(false);
var __rmA3 = __addN;
resumeMotion();
__ok('motion: resume respects iOS denial', __addN === __rmA3 && motionListening === false, 'adds=' + __addN);
DeviceMotionEvent = undefined;
window.DeviceMotionEvent = undefined;

// --- Stationary re-tare: slow zero-point learn, frozen while moving ---
function __imuState() {
  currentSpeedMs = 0; displaySpeedMs = 0; lastGpsConfidence = 0.9;
  lastUsableGpsTime = __t; lastGpsTime = __t;
  mountOffsetX = 0; mountOffsetZ = 0; imuLongGBias = 0; imuLatGBias = 0;
  lastImuTime = 0;
}
__imuState();
for (var __ri = 0; __ri < 500; __ri++) { __t += 16; handleMotion({ acceleration: { x: 2.0, z: 1.0 } }); }
__ok('retare: stationary re-tare drifts toward filtered (slow)', mountOffsetX > 0.02 && mountOffsetX < 1.0 && mountOffsetZ > 0.02, 'ox=' + mountOffsetX + ' oz=' + mountOffsetZ);
__imuState();
currentSpeedMs = 5;
for (var __rj = 0; __rj < 500; __rj++) { __t += 16; handleMotion({ acceleration: { x: 2.0, z: 1.0 } }); }
__ok('retare: frozen while moving', mountOffsetX === 0 && mountOffsetZ === 0, 'ox=' + mountOffsetX);

// --- Debounced peaks: single spike never latches, sustained does ---
__resetEst(); __resetTimers();
maxGpsAccelG = 0.5; imuFusionActive = false; fusedLongG = 0.9; fusedLatG = 0;
onPositionSuccess(__coords(20, 1));
__ok('peaks: single exceedance arms, does not latch', maxGpsAccelG === 0.5, 'max=' + maxGpsAccelG);
onPositionSuccess(__coords(20, 1));
__ok('peaks: sustained exceedance latches', maxGpsAccelG === 0.9, 'max=' + maxGpsAccelG);
fusedLongG = 2.0;
onPositionSuccess(__coords(20, 1));
__ok('peaks: lone spike does not latch', maxGpsAccelG === 0.9, 'max=' + maxGpsAccelG);
onPositionSuccess(__coords(20, 1));
__ok('peaks: sustained spike latches higher', maxGpsAccelG === 2.0, 'max=' + maxGpsAccelG);
__resetEst(); __resetTimers();
bestGpsBrakingG = 0.4; imuFusionActive = false; fusedLongG = -0.6; fusedLatG = 0;
onPositionSuccess(__coords(20, 1));
__ok('peaks: braking single exceedance arms only', bestGpsBrakingG === 0.4, 'max=' + bestGpsBrakingG);
onPositionSuccess(__coords(20, 1));
__ok('peaks: braking sustained latches', bestGpsBrakingG === 0.6, 'max=' + bestGpsBrakingG);
__resetEst(); __resetTimers();
maxGpsLatG = 0.5; imuFusionActive = false; fusedLongG = 0; fusedLatG = 0.8;
onPositionSuccess(__coords(20, 1));
__ok('peaks: lateral single exceedance arms only', maxGpsLatG === 0.5, 'max=' + maxGpsLatG);
onPositionSuccess(__coords(20, 1));
__ok('peaks: lateral sustained latches', maxGpsLatG === 0.8, 'max=' + maxGpsLatG);

// --- RESET RUN revives motion (same ritual as the hard tare) ---
window.DeviceMotionEvent = {};
motionListening = true;
lastImuTime = 0;
var __rsA = __addN, __rsR = __remN;
resetRun();
__ok('resetrun: revive cycles dead subscription', __remN > __rsR && __addN > __rsA && motionListening === true, 'adds=' + __addN + ' rems=' + __remN);
window.DeviceMotionEvent = undefined;
motionListening = true;
var __rsA2 = __addN, __rsR2 = __remN;
resetRun();
__ok('resetrun: no attach without hardware (denied stays denied)', __addN === __rsA2 && motionListening === false, 'adds=' + __addN + ' flag=' + motionListening);
window.DeviceMotionEvent = {};
lastMotionKick = __t;
resetRun();
__ok('resetrun: revive restarts watchdog clock', lastMotionKick === 0 && motionListening === true, 'kick=' + lastMotionKick);
__resetEst(); __resetTimers();
maxGpsAccelG = 0.5; imuFusionActive = false; fusedLongG = 0.9; fusedLatG = 0;
onPositionSuccess(__coords(20, 1));
__t += 1000;
onPositionSuccess({ coords: { latitude: __lat, longitude: 0, accuracy: 99, altitudeAccuracy: null, speed: null, speedAccuracy: null } });
onPositionSuccess(__coords(20, 1));
__ok('peaks: stale arm disarmed by weak gap (no instant latch)', maxGpsAccelG === 0.5, 'max=' + maxGpsAccelG);
__resetEst(); __resetTimers();
maxGpsAccelG = 0.5; imuFusionActive = false; fusedLongG = 0.9; fusedLatG = 0;
onPositionSuccess(__coords(20, 0.1));
onPositionSuccess(__coords(20, 0.1));
__ok('peaks: 10 Hz needs ~5 fixes (200 ms is not enough)', maxGpsAccelG === 0.5, 'max=' + maxGpsAccelG);
for (var __pz = 0; __pz < 5; __pz++) onPositionSuccess(__coords(20, 0.1));
__ok('peaks: 10 Hz latches after 500 ms wall time', maxGpsAccelG === 0.9, 'max=' + maxGpsAccelG);

// --- RESET RUN preserves live confidence (no phantom WEAK) ---
__resetEst();
lastGpsConfidence = 0.9; lastGpsTime = __t; lastUsableGpsTime = __t;
resetRun();
__ok('resetrun: preserves live confidence (no phantom WEAK)', lastGpsConfidence === 0.9, 'conf=' + lastGpsConfidence);

// --- Non-finite input: one poisoned sample must not brick the session ---
__resetEst();
filteredAccelX = 0; filteredAccelZ = 0;
handleMotion({ acceleration: { x: NaN, z: NaN } });
__ok('nan: poisoned sample dropped (never activates, clock untouched)', imuFusionActive === false && lastImuTime === 0 && filteredAccelX === 0 && filteredAccelZ === 0, 'active=' + imuFusionActive);
handleMotion({ acceleration: { x: Infinity, z: 1 } });
__ok('nan: infinite sample dropped too', imuFusionActive === false && lastImuTime === 0, 'active=' + imuFusionActive);
handleMotion({ acceleration: { x: 0, z: 0.5 } });
__ok('nan: valid samples still work after poison attempts', imuFusionActive === true && isFinite(fusedLongG), 'fused=' + fusedLongG);
__resetEst();
onPositionSuccess(__coords(0, 1));
onPositionSuccess(__coords(20, 1));
__t += 100; handleMotion({ acceleration: { x: 0, z: 0.5 } });
__t += 100; handleMotion({ acceleration: { x: NaN, z: NaN } });
__t += 100; handleMotion({ acceleration: { x: 0, z: 0.5 } });
onPositionSuccess(__coords(20, 1));
onPositionSuccess(__coords(20, 1));
__ok('nan: estimator survives poison attempt (finite)', isFinite(currentSpeedMs) && isFinite(kalmanV) && isFinite(fusedLongG), 'cs=' + currentSpeedMs);
__ok('nan: speed still tracks after poison attempt', Math.abs(currentSpeedMs - 20) < 2, 'cs=' + currentSpeedMs);

// --- Malformed accuracy: distrust, never perfect trust ---
__ok('acc: negative accuracy distrusts fully', gpsConfidence(-5) === 0 && gpsConfidence(-0.1) === 0, 'got ' + gpsConfidence(-5));
__ok('acc: valid accuracy unchanged', gpsConfidence(5) > 0.9 && gpsConfidence(5) < 1.0, 'got ' + gpsConfidence(5));
__resetEst();
onPositionSuccess(__coords(0, 1));
onPositionSuccess(__coords(10, 1));
onPositionSuccess(__coords(20, 1));
__t += 1000; __lat += 20 / __MPD;
onPositionSuccess({ coords: { latitude: __lat, longitude: 0, accuracy: 5, altitudeAccuracy: null, speed: 120, speedAccuracy: -3 } });
__ok('spdacc: negative speedAccuracy falls back to LS (not trusted Doppler)', fixLog[fixLog.length - 1].fl === 'U', 'fl=' + fixLog[fixLog.length - 1].fl);

// --- Mount orientation: RESET RUN gravity snapshot remaps lateral ---
// Driven through real handleMotion events (gravity fallback): the snapshot
// reads the gravity mirror, which works on linear-API phones too.
__resetEst();
mountYawMode = 1;
currentSpeedMs = 0; displaySpeedMs = 0; lastGpsConfidence = 0;
for (var __op = 0; __op < 30; __op++) { __t += 16; handleMotion({ accelerationIncludingGravity: { x: 0.2, y: 9.6, z: 0.3 } }); }
resetRun();
__ok('orient: portrait gravity restores legacy mapping', mountYawMode === 0, 'mode=' + mountYawMode);
__resetEst();
currentSpeedMs = 0; displaySpeedMs = 0; lastGpsConfidence = 0;
for (var __ol = 0; __ol < 30; __ol++) { __t += 16; handleMotion({ accelerationIncludingGravity: { x: 9.6, y: 0.2, z: 0.3 } }); }
resetRun();
__ok('orient: landscape gravity swaps lateral to Y', mountYawMode === 1, 'mode=' + mountYawMode);
__ok('orient: landscape tares all three offsets', mountOffsetX > 9 && mountOffsetY < 1 && mountOffsetZ < 1, 'ox=' + mountOffsetX + ' oy=' + mountOffsetY);
__resetEst();
mountYawMode = 1;
currentSpeedMs = 0; displaySpeedMs = 0; lastGpsConfidence = 0;
for (var __of = 0; __of < 30; __of++) { __t += 16; handleMotion({ accelerationIncludingGravity: { x: 0.5, y: 0.5, z: 9.6 } }); }
resetRun();
__ok('orient: flat/ambiguous never thrashes mapping', mountYawMode === 1, 'mode=' + mountYawMode);
__resetEst();
mountYawMode = 0;
currentSpeedMs = 0; displaySpeedMs = 0;
gravSmX = 9.6; gravSmY = 0.2; gravSmZ = 0.3;
lastImuTime = 0;
resetRun();
__ok('orient: stale gravity never remaps', mountYawMode === 0, 'mode=' + mountYawMode);
__resetEst();
mountYawMode = 1;
currentSpeedMs = 5; displaySpeedMs = 5;
filteredAccelX = 0.2; filteredAccelY = 9.6; filteredAccelZ = 0.3;
mountOffsetX = 0;
resetRun();
__ok('orient: moving reset never re-tares or remaps', mountYawMode === 1 && mountOffsetX === 0, 'mode=' + mountYawMode);
__resetEst();
mountYawMode = 1; mountOffsetX = 0; mountOffsetY = 0; mountOffsetZ = 0;
imuLongGBias = 0; imuLatGBias = 0; lastImuTime = 0; lastGpsConfidence = 0;
for (var __oi = 0; __oi < 30; __oi++) { __t += 16; handleMotion({ acceleration: { x: 0, y: 2.0, z: 0 } }); }
__ok('orient: landscape reads lateral from Y', imuLatG > 0.15 && Math.abs(imuLongG) < 0.05, 'lat=' + imuLatG + ' lon=' + imuLongG);
__resetEst();
handleMotion({ acceleration: { x: 0, y: NaN, z: 0 } });
__ok('orient: NaN Y dropped like other axes', imuFusionActive === false && lastImuTime === 0, 'active=' + imuFusionActive);
// --- Mount orientation: opportunistic still-gated re-snapshot, no press ---
__resetEst();
currentSpeedMs = 0; displaySpeedMs = 0; lastGpsConfidence = 0.8; lastUsableGpsTime = __t; lastGpsTime = __t;
for (var __oa = 0; __oa < 80; __oa++) { __t += 16; handleMotion({ accelerationIncludingGravity: { x: 9.6, y: 0.2, z: 0.3 } }); }
__ok('auto-orient: still rotated cradle re-snaps with no press', mountYawMode === 1 && orientSnapped === true, 'mode=' + mountYawMode);
__resetEst();
currentSpeedMs = 0; displaySpeedMs = 0; lastGpsConfidence = 0.8; lastUsableGpsTime = __t; lastGpsTime = __t;
for (var __ob = 0; __ob < 90; __ob++) { __t += 16; var __s = (__ob % 2 === 0) ? 2.5 : -2.5; handleMotion({ accelerationIncludingGravity: { x: 9.6 + __s, y: 0.2, z: 0.3 } }); }
__ok('auto-orient: acceleration present never re-snaps', mountYawMode === 0 && orientSnapped === false, 'mode=' + mountYawMode);
__resetEst();
currentSpeedMs = 5; displaySpeedMs = 5; lastGpsConfidence = 0.8; lastUsableGpsTime = __t; lastGpsTime = __t;
for (var __oc = 0; __oc < 80; __oc++) { __t += 16; handleMotion({ accelerationIncludingGravity: { x: 9.6, y: 0.2, z: 0.3 } }); }
__ok('auto-orient: moving never re-snaps', mountYawMode === 0 && orientSnapped === false, 'mode=' + mountYawMode);
__resetEst();
currentSpeedMs = 0; displaySpeedMs = 0; lastGpsConfidence = 0.8; lastUsableGpsTime = __t; lastGpsTime = __t;
for (var __od = 0; __od < 80; __od++) { __t += 16; handleMotion({ acceleration: { x: 0.05, y: 0.04, z: 0.02 }, accelerationIncludingGravity: { x: 9.6, y: 0.2, z: 0.3 } }); }
__ok('auto-orient: linear-API still rest re-snaps too', mountYawMode === 1 && orientSnapped === true, 'mode=' + mountYawMode);
// --- Lateral sign: GPS yaw-rate resolves mirrored mounts ---
// 12 m/s with +10 deg/fix turn = +0.21 g signed GPS truth per fix.
function __hfix(head) { __t += 1000; __lat += 12 / __MPD; return { coords: { latitude: __lat, longitude: 0, accuracy: 5, altitudeAccuracy: null, speed: 12, speedAccuracy: 0.5, heading: head } }; }
__resetEst();
imuFusionActive = true; imuLatG = -0.21;
onPositionSuccess(__hfix(0));
onPositionSuccess(__hfix(0));
for (var __sv = 1; __sv <= 30; __sv++) onPositionSuccess(__hfix(__sv * 10));
__ok('latsign: sustained disagreement flips mirrored mount', mountLatSign === -1, 'sign=' + mountLatSign);
resetRun();
__ok('latsign: reset restores standard sign', mountLatSign === 1, 'sign=' + mountLatSign);
__resetEst();
imuFusionActive = true; imuLatG = 0.21;
onPositionSuccess(__hfix(0));
onPositionSuccess(__hfix(0));
for (var __sw = 0; __sw < 30; __sw++) onPositionSuccess(__hfix(300 + __sw * 10));
__ok('latsign: agreement keeps standard sign', mountLatSign === 1, 'sign=' + mountLatSign);
"""


def _shim_for_dukpy(js: str) -> str:
    """dukpy (duktape) is ES5.1-only; convert just the modern syntax the inline
    script actually uses so we can still run tests when V8 isn't installed."""
    # numeric separators: 100_000 -> 100000
    js = re.sub(r"(\d)_(\d{3})", r"\1\2", js)
    # ?? and ?. are too grammar-sensitive to regex safely; convert the known spots.
    js = js.replace("event.accelerationIncludingGravity?.x ?? 0",
                   "(event.accelerationIncludingGravity ? event.accelerationIncludingGravity.x : 0)")
    js = js.replace("event.accelerationIncludingGravity?.z ?? 0",
                   "(event.accelerationIncludingGravity ? event.accelerationIncludingGravity.z : 0)")
    js = js.replace("typeof DeviceMotionEvent?.requestPermission !== 'function'",
                   "(typeof DeviceMotionEvent === 'undefined' || typeof DeviceMotionEvent.requestPermission !== 'function')")
    return js


def run_js(full: str):
    if _USE_RACER:
        ctx = _racer.MiniRacer()
        return ctx.eval(full)
    return dukpy.evaljs(_shim_for_dukpy(full))


def main():
    if not INDEX.exists():
        print(f"FATAL: {INDEX} not found", file=sys.stderr)
        return 2
    body = extract_script_body(INDEX.read_text(encoding="utf-8"))
    full = PRELUDE + "\n" + body + "\n" + POSTLUDE + "\nJSON.stringify(__results);"

    try:
        raw = run_js(full)
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8")
        raw = str(raw)
    except Exception as e:
        print("JS runtime error while running tests:\n" + str(e))
        return 2

    try:
        results = json.loads(raw)
    except json.JSONDecodeError:
        print("Could not parse test result JSON:\n" + str(raw))
        return 2

    passed = sum(1 for r in results if r["ok"])
    failed = len(results) - passed

    for r in results:
        mark = "PASS" if r["ok"] else "FAIL"
        line = f"[{mark}] {r['name']}"
        if not r["ok"] and r["detail"]:
            line += f"  -  {r['detail']}"
        print(line)

    print(f"\n{passed} passed, {failed} failed, {len(results)} total")
    print(f"engine: {'py_mini_racer (V8)' if _USE_RACER else 'dukpy (duktape, ES5 fallback)'}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
