// Comparing the dancer's live pose with the choreography. No DOM here, so tests/test_rehearsal_js.py can run it in node.
import * as C from "./encendido-stage.mjs";
// Whose choreography to compare against: Encendido by default, or a show from choreo.mjs.
let poseAt = C.poseAt;
export function useShow(show) { poseAt = show ? show.poseAt : C.poseAt; }
const clamp = (x, a, b) => Math.min(b, Math.max(a, x));
export const wrap = a => Math.atan2(Math.sin(a), Math.cos(a));
let base = null;                    // calibration: neck length from an upright, relaxed pose
export function calibrate(me) { if (me) base = { neck: me.neck }; }
export const vis = p => (p.visibility ?? 1) > 0.5;

// Your pose in the preview's terms (camera's view: the screen-left arm is your right arm).
// aL/eL: arm on the camera's left, aR/eR: on the camera's right. a = upper-arm angle from hanging down (pi/2 straight out,
// pi straight up), e = elbow bend added to it; look: head turned toward A (-) or B (+); headDown 0..1; tilt in radians.
export function myPose(L, W, H) {
  const P = i => [L[i].x * W, L[i].y * H];
  const sh = { L: P(12), R: P(11) }, el = { L: P(14), R: P(13) }, wr = { L: P(16), R: P(15) };
  const sw = Math.hypot(sh.R[0] - sh.L[0], sh.R[1] - sh.L[1]) || 1;
  const out = { sw, seen: {} };
  for (const [k, sx, ie, iw] of [["L", -1, 14, 16], ["R", 1, 13, 15]]) {
    const ux = el[k][0] - sh[k][0], uy = el[k][1] - sh[k][1], fx = wr[k][0] - el[k][0], fy = wr[k][1] - el[k][1];
    const a = Math.atan2(sx * ux, uy), a2 = Math.atan2(sx * fx, fy);
    out["a" + k] = a; out["e" + k] = wrap(a2 - a);
    out.seen["a" + k] = vis(L[ie]); out.seen["e" + k] = vis(L[ie]) && vis(L[iw]);
  }
  const mid = [(sh.L[0] + sh.R[0]) / 2, (sh.L[1] + sh.R[1]) / 2], nose = P(0);
  out.look = clamp((nose[0] - mid[0]) / (0.35 * sw), -1, 1);
  const neck = (mid[1] - nose[1]) / sw;
  out.headDown = clamp(((base?.neck ?? 0.75) - neck) / (0.45 * (base?.neck ?? 0.75)), 0, 1);
  out.tilt = vis(L[7]) && vis(L[8]) ? Math.atan2((L[7].y - L[8].y) * H, (L[7].x - L[8].x) * W) : 0;
  out.neck = neck;
  return out;
}

// How closely your upper body matches the choreography at show time t (0..1).
const JOINTS = [["aL", 1], ["aR", 1], ["eL", .6], ["eR", .6]];
export function matchAt(me, t) {
  const R = poseAt(Math.max(0, t)).H;
  let s = 0, w = 0;
  for (const [k, wt] of JOINTS) {
    if (!me.seen[k]) continue;
    const ref = k[0] === "e" ? wrap(R["a" + k[1]] + R[k]) : R[k];       // compare forearm direction, not the raw bend
    const mine = k[0] === "e" ? wrap(me["a" + k[1]] + me[k]) : me[k];
    s += wt * Math.max(0, 1 - Math.abs(wrap(mine - ref)) / (Math.PI / 2)); w += wt;
  }
  s += 0.5 * Math.max(0, 1 - Math.abs(me.look - R.look) / 1.2); w += 0.5;
  return w ? s / w : null;
}

// Your timing: the delay (ms, + = late) that best lines up your last 4 s of arm motion with the choreography's.
// hist: [{t: show time, me: myPose(...)}]. Null while the choreography holds still (nothing to time).
export function estimateOffset(hist, now) {
  const win = hist.filter(h => now - h.t < 4 && h.t > 0);
  if (win.length < 40) return null;
  const refs = win.map(h => poseAt(h.t).H);
  const spread = k => { const v = refs.map(r => r[k]); return Math.max(...v) - Math.min(...v); };
  if (Math.max(spread("aL"), spread("aR"), spread("eL"), spread("eR")) < 0.5) return null;
  let best = null;
  for (let L = -600; L <= 600; L += 20) {
    let s = 0, n = 0;
    for (const h of win) { const m = matchAt(h.me, h.t - L / 1000); if (m != null) { s += m; n++; } }
    if (n && (!best || s / n > best.s)) best = { L, s: s / n };
  }
  return best && best.s > 0.55 ? best.L : null;
}

// A measured robot pose (SDK units: yaw, pitch, roll deg, z mm, body deg, antennas rad) in the preview's units,
// inverting pose.to_sdk. cal = show.yaml's calibration section.
export function measuredToScore(m, ref, k = {}) {
  const ys = k.yaw_left_sign ?? 1, yawDeg = k.yaw_deg ?? 40, bodyDeg = k.body_deg ?? 30, pitchDeg = k.pitch_deg ?? 25;
  const bodyTot = m[4] / ys, rel = m[0] / ys - bodyTot, r = { ...ref };
  r.yaw = rel / yawDeg;
  if (Math.abs(bodyTot) <= bodyDeg) { r.body = bodyTot / bodyDeg; r.turn = 0; }
  else { const s = Math.sign(bodyTot); r.body = s; r.turn = (bodyTot - s * bodyDeg) * Math.PI / 180; }
  r.pitch = -(m[1] / (k.pitch_down_sign ?? 1)) / pitchDeg;
  r.roll = (m[2] / (k.roll_sign ?? 1)) * Math.PI / 180;
  r.bob = -m[3] / (k.z_mm_per_px ?? 0.5);
  r.antL = m[5] / (k.ant_right_out_sign ?? 1); r.antR = m[6] / (k.ant_left_out_sign ?? -1);
  return r;
}

// Landmarks a camera would see for the preview dancer's pose H (for tests and demos): shoulders level, arms per H.
export function landmarksFor(H, W = 1280, Hpx = 720) {
  const L = Array.from({ length: 33 }, () => ({ x: 0.5, y: 1.3, visibility: 0.1 }));
  const sw = 260, cx = 640 + (H.x || 0) * 0.3, sy = 470, ua = 150, fa = 140;
  const put = (i, x, y) => { L[i] = { x: x / W, y: y / Hpx, visibility: 0.99 }; };
  for (const [sx, a, e, si, ei, wi] of [[-1, H.aL, H.eL, 12, 14, 16], [1, H.aR, H.eR, 11, 13, 15]]) {
    const s = [cx + sx * sw / 2, sy], el = [s[0] + sx * Math.sin(a) * ua, s[1] + Math.cos(a) * ua];
    const wr = [el[0] + sx * Math.sin(a + e) * fa, el[1] + Math.cos(a + e) * fa];
    put(si, ...s); put(ei, ...el); put(wi, ...wr);
  }
  put(0, cx + (H.look || 0) * 0.35 * sw, sy - 0.75 * sw);
  put(7, cx + 40, sy - 0.75 * sw); put(8, cx - 40, sy - 0.75 * sw);
  return L;
}
