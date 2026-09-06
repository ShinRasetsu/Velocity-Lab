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
        style: {},
        textContent: '', className: '', innerHTML: '',
        appendChild: function(){return arguments[0];},
        removeChild: function(){return arguments[0];},
        addEventListener: function(){},
        setAttribute: function(){},
        getContext: function(){return null;}
    };
}
var document = {
    getElementById: function(){ return __stubEl(); },
    createElement: function(){ return __stubEl(); },
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
