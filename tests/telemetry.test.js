/**
 * Telemetry gate — Node fallback for tests.py (Gate 4)
 * Run: node tests/telemetry.test.js  (no python needed)
 * Same coverage: gpsConfidence, calculateVehicleScore, updateTimers sub-sample
 * Extracted from tests.py PRELUDE/POSTLUDE — keep in sync.
 */
const fs = require('fs'), path = require('path'), vm = require('vm');
const INDEX = path.join(__dirname, '..', 'index.html');
const body = (()=>{ const m=fs.readFileSync(INDEX,'utf8').match(/<script>([\s\S]*?)<\/script>/); if(!m) throw new Error('no <script>'); return m[1]; })();

const PRELUDE = `
var __results = [];
function __ok(name, cond, detail) { __results.push({ name: String(name), ok: !!cond, detail: detail || '' }); }
function __stubEl(){ return { style:{}, textContent:'', className:'', innerHTML:'', appendChild:function(){return arguments[0]}, removeChild:function(){return arguments[0]}, addEventListener:function(){}, setAttribute:function(){}, getContext:function(){return null} }; }
var document = { getElementById:function(){return __stubEl();}, createElement:function(){return __stubEl();}, querySelector:function(){return __stubEl();}, querySelectorAll:function(){return [];}, addEventListener:function(){}, visibilityState:'visible', body: __stubEl(), documentElement: { style:{ setProperty:function(){} } } };
var window = { addEventListener:function(){}, DeviceMotionEvent: undefined };
var navigator = {};
var performance = { now:function(){return 0;} };
var __lsStore = {};
var localStorage = { getItem:function(k){return Object.prototype.hasOwnProperty.call(__lsStore,k)?__lsStore[k]:null;}, setItem:function(k,v){__lsStore[k]=String(v);}, removeItem:function(k){delete __lsStore[k];} };
var indexedDB = undefined;
var URL = { createObjectURL:function(){return 'blob:x';}, revokeObjectURL:function(){} };
function Blob(){} function TextEncoder(){} function TextDecoder(){}
var Intl = (function(){ function FakeFmt(opts){ this.opts=opts||{}; this.format=function(n){ var min=this.opts.minimumFractionDigits||0; var max=this.opts.maximumFractionDigits||3; var s=Number(n).toFixed(max); var dot=s.indexOf('.'); if(dot==-1) return s; var intPart=s.substring(0,dot); var frac=s.substring(dot+1); while(frac.length>min && frac.charAt(frac.length-1)==='0') frac=frac.substring(0,frac.length-1); return frac.length?intPart+'.'+frac:intPart; }; } return { NumberFormat: FakeFmt }; })();
`;

const POSTLUDE = `
function nearly(a,b,eps){eps=eps||1e-9; return Math.abs(a-b)<eps;}
__ok('gpsConf: <= trust_min -> 1.0', nearly(gpsConfidence(0),1.0) && nearly(gpsConfidence(GPS_ACC_TRUST_MIN_M),1.0), gpsConfidence(GPS_ACC_TRUST_MIN_M)+" expected 1.0");
__ok('gpsConf: >= trust_max -> 0.0', nearly(gpsConfidence(GPS_ACC_TRUST_MAX_M),0.0) && nearly(gpsConfidence(1000),0.0), gpsConfidence(1000)+" expected 0.0");
__ok('gpsConf: midpoint -> 0.5 (linear interp)', nearly(gpsConfidence((GPS_ACC_TRUST_MIN_M+GPS_ACC_TRUST_MAX_M)/2),0.5), "expected 0.5 at midpoint");
__ok('gpsConf: NaN / undefined / string -> 0.0', nearly(gpsConfidence(NaN),0.0) && nearly(gpsConfidence(undefined),0.0) && nearly(gpsConfidence('x'),0.0), "non-number inputs must clamp to 0");
__ok('gpsConf: monotonic non-increasing in accuracy radius', gpsConfidence(2) >= gpsConfidence(5) && gpsConfidence(10) >= gpsConfidence(15) && gpsConfidence(20) >= gpsConfidence(25), "confidence must not increase as accuracy radius grows");
function __setPeaks(maxSpd, maxAcc, maxBrk, maxLat){ maxSpeedKmph=maxSpd; maxGpsAccelG=maxAcc; bestGpsBrakingG=maxBrk; maxGpsLatG=maxLat; }
__setPeaks(0,0,0,0); var z=calculateVehicleScore(); __ok('vScore: all-zero -> all-zero', z.total===0 && z.spd===0 && z.acc===0 && z.brk===0 && z.hdl===0, 'got total='+z.total);
__setPeaks(200,1.0,1.2,1.1); var full=calculateVehicleScore(); __ok('vScore: ceiling caps -> spd20/acc10/brk15/hdl25/total70', full.spd===20 && full.acc===10 && full.brk===15 && full.hdl===25 && full.total===70, 'got '+JSON.stringify(full));
__setPeaks(1000,50,50,50); var cap=calculateVehicleScore(); __ok('vScore: absurd inputs do not exceed ceilings', cap.total===70 && cap.spd===20 && cap.acc===10 && cap.brk===15 && cap.hdl===25, 'got '+JSON.stringify(cap));
__setPeaks(100,0.5,0.6,0.55); var half=calculateVehicleScore(); __ok('vScore: half-peak proportional with native rounding', half.spd===10 && half.acc===5 && half.brk===8 && half.hdl===13 && half.total===35, 'got '+JSON.stringify(half));
function __resetTimers(){ timer0_60.state=T_IDLE; timer0_60.start=0; timer0_60.result=0; timer0_100.state=T_IDLE; timer0_100.start=0; timer0_100.result=0; timer100_200.state=T_IDLE; timer100_200.start=0; timer100_200.result=0; timerQuarter.state=T_IDLE; timerQuarter.start=0; timerQuarter.result=0; timerQuarter.startDist=0; timer100_0.state=T_IDLE; timer100_0.start=0; timer100_0.startDist=0; timer100_0.result=0; lastTimerSpeedKmh=NaN; lastTimerDistM=NaN; lastTimerTimeMs=NaN; stateDirty=false; }
__resetTimers(); updateTimers(0,0,1000); __ok('t0_100: stopped keeps IDLE', timer0_100.state===T_IDLE && timer0_100.result===0, 'state='+timer0_100.state);
updateTimers(5,2,2000); __ok('t0_100: launch arms RUNNING with interpolated start timestamp', timer0_100.state===T_RUNNING && nearly(timer0_100.start,1300,1e-6), 'state='+timer0_100.state+' start='+timer0_100.start);
var __expFinish = 2000 + (14500-2000)*(100-5)/(104-5); updateTimers(104,100,14500); __ok('t0_100: cross threshold -> DONE with interpolated elapsed', timer0_100.state===T_DONE && nearly(timer0_100.result,__expFinish-1300,1e-6), 'state='+timer0_100.state+' result='+timer0_100.result+' expected='+(__expFinish-1300));
__resetTimers(); updateTimers(5,2,1000); updateTimers(0,5,5000); __ok('t0_100: abort on stop returns IDLE without writing result', timer0_100.state===T_IDLE && timer0_100.result===0, 'state='+timer0_100.state+' result='+timer0_100.result);
__resetTimers(); updateTimers(5,1,1000); updateTimers(105,80,7000); updateTimers(0,82,15000); __ok('t0_100: completed result is preserved across a subsequent stop (DONE retained)', timer0_100.state===T_DONE && nearly(timer0_100.result,5700,1e-6), 'state='+timer0_100.state+' result='+timer0_100.result);
__ok('t100_200 vs t0_100 re-arm asymmetry documented', true, '100-200 resets DONE->IDLE on stop; 0-60/0-100 retain DONE until RESET');
__resetTimers(); updateTimers(99,5,1000); __ok('t100_200: stays IDLE below 100', timer100_200.state===T_IDLE, 'state='+timer100_200.state); updateTimers(100,6,2000); updateTimers(150,60,3000); __ok('t100_200: arms at >= 100 -> RUNNING, stays RUNNING at 150', timer100_200.state===T_RUNNING && timer100_200.start===2000, 'state='+timer100_200.state); updateTimers(205,200,6000); __ok('t100_200: cross 200 -> DONE with interpolated elapsed', timer100_200.state===T_DONE && nearly(timer100_200.result,3000+3000*50/55-2000,1e-6), 'state='+timer100_200.state+' result='+timer100_200.result);
__resetTimers(); updateTimers(5,0,1000); __ok('tQuarter: arm from rest sets start AND startDist', timerQuarter.state===T_RUNNING && nearly(timerQuarter.start,1000,1e-6) && timerQuarter.startDist===0, 'state='+timerQuarter.state+' start='+timerQuarter.start+' startDist='+timerQuarter.startDist); updateTimers(50,300,4000); __ok('tQuarter: distance < quarter mile -> still RUNNING', timerQuarter.state===T_RUNNING, 'state='+timerQuarter.state); var __expQ=(4000+7000*(402.336-300)/200)-1000; updateTimers(120,500,11000); __ok('tQuarter: once distance delta >= 402.336 m -> DONE with interpolated elapsed', timerQuarter.state===T_DONE && nearly(timerQuarter.result,__expQ,1e-6), 'state='+timerQuarter.state+' result='+timerQuarter.result+' expected='+__expQ);
__resetTimers(); updateTimers(80,0,1000); __ok('t100_0: below 100 -> stays IDLE', timer100_0.state===T_IDLE, 'state='+timer100_0.state); updateTimers(110,50,2000); __ok('t100_0: cruise >= 100 arms RUNNING with startDist', timer100_0.state===T_RUNNING && timer100_0.startDist===50 && timer100_0.start===2000, 'state='+timer100_0.state+' startDist='+timer100_0.startDist); var __expBrake=(50+370*(110-SPEED_ZERO_SNAP_KMPH)/110)-50; updateTimers(0,420,30000); __ok('t100_0: stop -> DONE with interpolated positive braking distance', timer100_0.state===T_DONE && nearly(timer100_0.result,__expBrake,1e-6), 'state='+timer100_0.state+' result='+timer100_0.result+' expected='+__expBrake);
__resetTimers(); updateTimers(1,0,5000); updateTimers(51,5,7000); updateTimers(101,40,9000); __ok('interpolation: threshold crossings land between fixes (3940ms, not 2000ms)', timer0_100.state===T_DONE && nearly(timer0_100.result,3940,1e-6), 'result='+timer0_100.result);
// === Tests: GPS session preservation (frequent SIGNAL LOSS fix) ===
// ES5-only: mirrored verbatim in tests/tests.py (dukpy fallback).
var __pendingTimers = [];
setTimeout = function(fn, ms) { __pendingTimers.push({ fn: fn, ms: ms }); return __pendingTimers.length; };
var __geoSpy = { watch: 0, clear: 0 };
navigator.geolocation = {
  watchPosition: function() { __geoSpy.watch++; return 1000 + __geoSpy.watch; },
  clearWatch: function() { __geoSpy.clear++; }
};
function __mkErr(code) { return { code: code, PERMISSION_DENIED: 1, POSITION_UNAVAILABLE: 2, TIMEOUT: 3 }; }
function __resetGeo() { __geoSpy.watch = 0; __geoSpy.clear = 0; __pendingTimers.length = 0; gpsRetryPending = false; gpsFailCount = 0; lastGpsTime = -1; }
__ok('gpsBackoff: 5s,10s,20s,30s cap', gpsBackoffDelay(0)===5000 && gpsBackoffDelay(1)===10000 && gpsBackoffDelay(2)===20000 && gpsBackoffDelay(3)===30000 && gpsBackoffDelay(99)===30000 && gpsBackoffDelay(-5)===5000, 'got '+gpsBackoffDelay(0)+','+gpsBackoffDelay(1)+','+gpsBackoffDelay(2)+','+gpsBackoffDelay(3));
__resetGeo(); onPositionError(__mkErr(3));
__ok('gpsErr: TIMEOUT never tears down the warm watch', __geoSpy.clear===0 && __geoSpy.watch===0 && __pendingTimers.length===0, 'clear='+__geoSpy.clear+' watch='+__geoSpy.watch+' pending='+__pendingTimers.length);
__ok('gpsErr: TIMEOUT still surfaces status', String(prev.status).indexOf('TIMEOUT') !== -1, 'status='+prev.status);
__resetGeo(); onPositionError(__mkErr(2)); onPositionError(__mkErr(2)); onPositionError(__mkErr(2));
__ok('gpsErr: repeat UNAVAILABLE schedules exactly one recovery', __pendingTimers.length===1 && __geoSpy.clear===0 && __geoSpy.watch===0, 'pending='+__pendingTimers.length);
__ok('gpsErr: first retry is fast (5s)', __pendingTimers[0].ms===5000, 'ms='+(__pendingTimers[0] && __pendingTimers[0].ms));
lastGpsTime = -99999; gpsWatchId = 7; var __recFn = __pendingTimers[0].fn; __recFn();
__ok('gpsErr: recovery replaces watch once and frees the slot', __geoSpy.watch===1 && __geoSpy.clear===1 && gpsRetryPending===false, 'watch='+__geoSpy.watch+' clear='+__geoSpy.clear);
__resetGeo(); onPositionError(__mkErr(1));
__ok('gpsErr: PERMISSION_DENIED schedules nothing, kills nothing', __pendingTimers.length===0 && __geoSpy.clear===0 && __geoSpy.watch===0, 'pending='+__pendingTimers.length);
__resetGeo(); onPositionError({}); onPositionError(null); onPositionError(undefined);
__ok('gpsErr: malformed errors are inert', __pendingTimers.length===0 && __geoSpy.clear===0, 'pending='+__pendingTimers.length);
`;

const full = PRELUDE + "\n" + body + "\n" + POSTLUDE + "\nJSON.stringify(__results);";
try {
  const ctx = vm.createContext({});
  const res = vm.runInContext(full, ctx, { timeout: 5000 });
  const results = JSON.parse(res);
  let passed=0, failed=0;
  for(const r of results){ const mark=r.ok?"PASS":"FAIL"; console.log(`[${mark}] ${r.name}` + (!r.ok && r.detail?`  -  ${r.detail}`:"")); if(r.ok) passed++; else failed++; }
  console.log(`\n${passed} passed, ${failed} failed, ${results.length} total`);
  console.log(`engine: node vm`);
  process.exit(failed===0?0:1);
} catch(e){ console.error("JS runtime error:", e); process.exit(2); }
