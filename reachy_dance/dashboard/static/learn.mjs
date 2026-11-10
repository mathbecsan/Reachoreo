// Learning a dance from a video: line the video up with the song, turn the dancer's pose (MediaPipe landmarks)
// into the stage's dancer model on the song's counts, and derive both robots' moves from it.
// No DOM here, so tests/test_learn_js.py runs it in node with synthetic landmarks.
import * as R from "./rehearsal.mjs";
import * as C from "./encendido-stage.mjs";

export const STEPS = 8;                         // samples per count stored in the dance
export const HUMAN_KEYS = ["x", "drop", "lean", "look", "tilt", "headDown", "shrug", "aL", "eL", "aR", "eR", "fLx", "fLy", "fRx", "fRy"];
export const ROBOT_KEYS = ["yaw", "pitch", "roll", "body", "turn", "antL", "antR", "bob"];     // = pose.POSE_KEYS
const clamp = (x, a, b) => Math.min(b, Math.max(a, x));
const median = v => { const s = v.filter(Number.isFinite).sort((a, b) => a - b); return s.length ? s[s.length >> 1] : 0; };

// ---------- 1. where the video sits in the song ----------
// Cross-correlates the onset envelopes (music.mjs features().flux) of the video's soundtrack and the song.
// Returns the song time at video time 0 (seconds) and how sure we are (peak vs the next best, 1 = clear).
export function findOffset(songFlux, videoFlux, fps) {
  const ds = a => { const n = a.length >> 1, o = new Float32Array(n); for (let i = 0; i < n; i++) o[i] = a[2 * i] + a[2 * i + 1]; return o; };
  const S = ds(songFlux), V = ds(videoFlux), f2 = fps / 2;
  // normalised: the dot product over the overlap divided by both sides' energy there, so a loud chorus doesn't win
  // just for being loud (songs repeat, and the right spot must beat a merely similar one)
  const S2 = new Float64Array(S.length + 1), V2 = new Float64Array(V.length + 1);
  for (let i = 0; i < S.length; i++) S2[i + 1] = S2[i] + S[i] * S[i];
  for (let i = 0; i < V.length; i++) V2[i + 1] = V2[i] + V[i] * V[i];
  const score = lag => {
    const i0 = Math.max(0, -lag), i1 = Math.min(V.length, S.length - lag);
    if (i1 - i0 < Math.max(4 * f2, 0.6 * Math.min(V.length, S.length))) return 0;   // most of the video must overlap the song
    let s = 0; for (let i = i0; i < i1; i++) s += V[i] * S[i + lag];
    const e = Math.sqrt((V2[i1] - V2[i0]) * (S2[i1 + lag] - S2[i0 + lag]));
    return e > 0 ? s / e : 0;
  };
  let best = { lag: 0, s: -1 }, scores = [];
  for (let lag = -V.length + Math.round(4 * f2); lag < S.length - Math.round(4 * f2); lag++) {
    const s = score(lag); scores.push([lag, s]);
    if (s > best.s) best = { lag, s };
  }
  // refine at full resolution around the coarse peak
  const full = lag => { let s = 0; for (let i = 0; i < videoFlux.length; i++) { const j = i + lag; if (j >= 0 && j < songFlux.length) s += videoFlux[i] * songFlux[j]; } return s; };
  let fine = { lag: 2 * best.lag, s: -1 };
  for (let lag = 2 * best.lag - 3; lag <= 2 * best.lag + 3; lag++) { const s = full(lag); if (s > fine.s) fine = { lag, s }; }
  // How far the best lag stands out from all the others (z-score). Repeating bars make other lags look decent, but a
  // real match still stands out by many deviations; an unrelated song doesn't.
  const vals = scores.map(([, v]) => v), mean = vals.reduce((p, q) => p + q, 0) / vals.length;
  const sd = Math.sqrt(vals.reduce((p, q) => p + (q - mean) ** 2, 0) / vals.length) || 1e-9;
  const z = (best.s - mean) / sd;
  return { offset_s: fine.lag / fps, confidence: clamp((z - 4) / 4, 0, 1), z: +z.toFixed(1) };
}

// ---------- 2. landmarks to the stage's dancer ----------
// frames: [{t: video seconds, lm: 33 landmarks {x, y, visibility} | null}], W/H the video size.
// mirrored: the video is a mirror tutorial (the dancer's right is on screen-right): flip it to the audience's view.
export function framesToPoses(frames, W, H, mirrored = false) {
  const seen = frames.filter(f => f.lm);
  if (!seen.length) return [];
  const P = (lm, i) => [lm[i].x * W, lm[i].y * H];
  const mid = (a, b) => [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
  const vis = (lm, i) => (lm[i].visibility ?? 1) > 0.5;
  // body-size reference and resting positions from the whole clip, so one odd frame can't skew them
  const sw = median(seen.map(f => Math.hypot(...[0, 1].map(k => P(f.lm, 11)[k] - P(f.lm, 12)[k])))) || 0.2 * W;
  const k = 80 / sw;                                                       // stage px per video px (shoulders ~80 px on stage)
  const cx0 = median(seen.map(f => mid(P(f.lm, 23), P(f.lm, 24))[0]));
  const hy0 = median(seen.map(f => mid(P(f.lm, 23), P(f.lm, 24))[1]));
  const legs = seen.filter(f => vis(f.lm, 27) && vis(f.lm, 28));
  const ay0 = legs.length > seen.length * 0.3 ? median(legs.map(f => (P(f.lm, 27)[1] + P(f.lm, 28)[1]) / 2)) : null;
  R.calibrate({ neck: median(seen.map(f => R.myPose(f.lm, W, H).neck)) });
  return frames.map(f => {
    if (!f.lm) return { t: f.t, H: null };
    let lm = f.lm;
    if (mirrored) lm = mirrorLandmarks(lm);
    const me = R.myPose(lm, W, H);
    const hip = mid(P(lm, 23), P(lm, 24)), sh = mid(P(lm, 11), P(lm, 12));
    const h = {
      x: clamp((hip[0] - (mirrored ? W - cx0 : cx0)) * k, -320, 320),
      drop: clamp((hip[1] - hy0) * k, -50, 60),
      lean: clamp(Math.atan2(sh[0] - hip[0], hip[1] - sh[1]), -0.5, 0.5),
      look: me.look, tilt: clamp(me.tilt, -0.5, 0.5), headDown: me.headDown, shrug: 0,
      aL: me.aL, eL: me.seen.eL ? me.eL : 0.15, aR: me.aR, eR: me.seen.eR ? me.eR : 0.15,
      fLx: 0, fLy: 0, fRx: 0, fRy: 0,
    };
    if (ay0 != null && vis(lm, 27) && vis(lm, 28)) {                      // feet: camera-left foot is landmark 28
      const fl = P(lm, 28), fr = P(lm, 27);
      h.fLx = clamp((fl[0] - hip[0]) * k + 46, -60, 60); h.fRx = clamp((fr[0] - hip[0]) * k - 46, -60, 60);
      h.fLy = clamp((ay0 - fl[1]) * k, 0, 60); h.fRy = clamp((ay0 - fr[1]) * k, 0, 60);
    }
    return { t: f.t, H: h };
  });
}

// Swap left and right landmarks and flip x (a mirror tutorial seen from the audience).
const PAIRS = [[1, 4], [2, 5], [3, 6], [7, 8], [9, 10], [11, 12], [13, 14], [15, 16], [17, 18], [19, 20], [21, 22], [23, 24], [25, 26], [27, 28], [29, 30], [31, 32]];
export function mirrorLandmarks(lm) {
  const out = lm.map(p => ({ ...p, x: 1 - p.x }));
  for (const [a, b] of PAIRS) { const t = out[a]; out[a] = out[b]; out[b] = t; }
  return out;
}

// ---------- 3. onto the song's counts ----------
// poses: framesToPoses output; offset_s: song time at video time 0; countTimes: song seconds of every count.
// Returns per phrase i a track of 8 * STEPS + 1 samples (count 8i to 8i+8), or null where the video doesn't cover it.
export function trackOnCounts(poses, offset_s, countTimes) {
  const ok = poses.filter(p => p.H);
  const nPh = Math.floor((countTimes.length - 1) / 8), out = [];
  const songT = p => p.t + offset_s;
  const at = t => {                                                      // the pose at song time t: average frames within ±40 ms
    let lo = 0, hi = ok.length; while (lo < hi) { const m = (lo + hi) >> 1; if (songT(ok[m]) < t) lo = m + 1; else hi = m; }
    const near = []; for (let j = Math.max(0, lo - 3); j < Math.min(ok.length, lo + 3); j++) if (Math.abs(songT(ok[j]) - t) <= 0.04) near.push(ok[j].H);
    if (!near.length) {                                                    // gap: interpolate between neighbours up to 0.5 s apart
      const a = ok[lo - 1], b = ok[lo];
      if (!a || !b || songT(b) - songT(a) > 0.5) return null;
      const f = (t - songT(a)) / (songT(b) - songT(a));
      return Object.fromEntries(HUMAN_KEYS.map(key => [key, a.H[key] + f * (b.H[key] - a.H[key])]));
    }
    return Object.fromEntries(HUMAN_KEYS.map(key => [key, near.reduce((s, h) => s + h[key], 0) / near.length]));
  };
  for (let i = 0; i < nPh; i++) {
    const track = [];
    for (let s = 0; s <= 8 * STEPS; s++) {
      const c = 8 * i + s / STEPS, k0 = Math.min(Math.floor(c), countTimes.length - 2), f = c - k0;
      const h = at(countTimes[k0] + f * (countTimes[k0 + 1] - countTimes[k0]));
      if (!h) { track.length = 0; break; }
      track.push(h);
    }
    out.push(track.length ? track : null);
  }
  return out;
}

// ---------- 4. the robots dance with the dancer ----------
// Both robots copy the dancer as the audience sees them: antennas follow the arms on their side, heads bounce with
// the dancer's knees and nod on arm hits, tilt with the dancer, and keep facing the dancer as they move.
export function robotsFor(track) {
  const toward = (from, to) => clamp((to - from) / 600, -1, 1);
  const armUp = a => clamp(a / Math.PI, 0, 1);                           // 0 down, 0.5 out, 1 straight up
  return track.map((h, s) => {
    const prev = track[Math.max(0, s - 1)], dA = Math.abs(h.aL - prev.aL) + Math.abs(h.aR - prev.aR);
    const hit = clamp(dA * STEPS / 6, 0, 1);                               // a fast arm move reads as a hit
    const up = Math.max(armUp(h.aL), armUp(h.aR));
    const out = {};
    for (const [side, pos] of [["A", C.POS.L], ["B", C.POS.R]]) {
      const yaw = clamp(toward(pos, C.POS.C + h.x) + 0.15 * h.look, -1, 1);
      out[side] = {
        yaw, pitch: clamp(0.08 + 0.35 * (up - 0.3) + 0.2 * hit - 0.006 * h.drop, -0.6, 0.6),
        roll: clamp(0.8 * h.tilt + 0.5 * h.lean, -0.4, 0.4), body: clamp(0.4 * yaw + 0.3 * h.lean, -0.8, 0.8), turn: 0,
        antL: clamp(0.1 + 1.2 * armUp(h.aL) + 0.15 * Math.abs(h.eL) / Math.PI, 0.05, 1.35),
        antR: clamp(0.1 + 1.2 * armUp(h.aR) + 0.15 * Math.abs(h.eR) / Math.PI, 0.05, 1.35),
        bob: clamp(0.35 * h.drop - 4 * hit, -10, 12),
      };
    }
    return out;
  });
}

// Smooths a track (3-sample moving average per key), keeping the end points, so detector jitter doesn't reach the motors.
export function smooth(track, keys) {
  return track.map((h, s) => {
    if (s === 0 || s === track.length - 1) return h;
    const o = {}; for (const k of keys) o[k] = (track[s - 1][k] + h[k] + track[s + 1][k]) / 3; return o;
  });
}

const r3 = v => Math.round(v * 1000) / 1000;
// Everything the dance stores for one learned phrase: arrays in HUMAN_KEYS / ROBOT_KEYS order.
export function learnedPhrase(track) {
  const H = smooth(track, HUMAN_KEYS), rob = robotsFor(H);
  return { H: H.map(h => HUMAN_KEYS.map(k => r3(h[k]))), A: rob.map(r => ROBOT_KEYS.map(k => r3(r.A[k]))), B: rob.map(r => ROBOT_KEYS.map(k => r3(r.B[k]))) };
}
