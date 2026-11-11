// Headset scoring (VR and AR): the Quest tracks your head and both hands (controllers or hand tracking), not your
// whole body, so a move is scored on where your head and wrists are, compared with the coach's head and wrists.
// Pure maths, run in node by tests/test_xr.py.
//
// Both bodies go into one frame, the dancer's: origin = the head standing neutral (yours: at calibration), x = the
// audience's right, y = up, z = toward the audience; distances in arm spans (wrist to wrist in a T-pose), so a
// 1.5 m dancer copying a 1.75 m coach matches. You face the coach and copy it like a mirror, so your RIGHT hand is
// compared with the dancer's right hand: the "L" wrist (the audience's left), as on the webcam.
import type { HumanPose } from "/static/encendido-stage.mjs";
import { bodyJoints, onStage, type V3 } from "./body.ts";
import type { Metric } from "./score";

export interface XrFeatures { t: number; head: V3 | null; wL: V3 | null; wR: V3 | null }

const sub = (a: V3, b: V3): V3 => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const dist = (a: V3, b: V3) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
const scale = (a: V3, k: number): V3 => [a[0] * k, a[1] * k, a[2] * k];

/** Standing neutral: the same body, upright, facing you, on the mark, arms where they are. */
const neutral = (h: HumanPose): HumanPose => ({ ...h, lean: 0, drop: 0, sit: 0, look: 0, headDown: 0, tilt: 0, shrug: 0, x: 0, depth: 0, face: 0 });

/** The coach's reference: head and wrists at show time t, in the dancer frame, in coach arm spans. */
export function coachReference(poseAt: (t: number) => HumanPose, pxToM: number) {
  const h0 = poseAt(0);
  const origin = bodyJoints(neutral(h0)).head;
  const T = bodyJoints({ ...neutral(h0), aL: Math.PI / 2, aR: Math.PI / 2, eL: 0, eR: 0 });
  const span = dist(T.L.wrist, T.R.wrist);
  return {
    span,
    at(t: number): XrFeatures {
      const h = poseAt(t), B = bodyJoints(h), f = (p: V3) => scale(sub(onStage(p, h, pxToM), origin), 1 / span);
      return { t, head: f(B.head), wL: f(B.L.wrist), wR: f(B.R.wrist) };
    },
  };
}

/** Your calibration: head position and facing at the T-pose, and your arm span (metres, XR reference space). */
export interface XrCalibration { origin: V3; yaw: number; span: number }

/** The facing (yaw about +y, three.js convention: 0 = looking down -z) of a forward vector. */
export const yawOf = (fwd: V3) => Math.atan2(-fwd[0], -fwd[2]);

/** A tracked point (XR reference space, metres) into the dancer frame, in your arm spans. */
export function toDancerFrame(p: V3, c: XrCalibration): V3 {
  const d = sub(p, c.origin), f: V3 = [-Math.sin(c.yaw), 0, -Math.cos(c.yaw)], r: V3 = [Math.cos(c.yaw), 0, -Math.sin(c.yaw)];
  // you face the coach, the dancer faces the audience: your right is the audience's left (-x), your forward is +z
  return scale([-(d[0] * r[0] + d[2] * r[2]), d[1], d[0] * f[0] + d[2] * f[2]], 1 / c.span);
}

/** One headset frame: head, right hand, left hand (any may be untracked). */
export function xrFeatures(t: number, head: V3 | null, right: V3 | null, left: V3 | null, c: XrCalibration): XrFeatures {
  return { t, head: head && toDancerFrame(head, c), wL: right && toDancerFrame(right, c), wR: left && toDancerFrame(left, c) };
}

// Tolerances in arm spans (about 1.6 m): a wrist within ~10 cm is perfect, ~50 cm away scores nothing.
const TOL = { head: 0.16, wrist: 0.32 }, W = { head: 0.6, wrist: 1 };

export const XR_METRIC: Metric<XrFeatures> = {
  match(me, ref) {
    let s = 0, w = 0;
    const add = (a: V3 | null, b: V3 | null, tol: number, wt: number) => {
      if (!a || !b || !a.every(Number.isFinite)) return;
      s += wt * Math.max(0, 1 - dist(a, b) / tol); w += wt;
    };
    add(me.wL, ref.wL, TOL.wrist, W.wrist); add(me.wR, ref.wR, TOL.wrist, W.wrist); add(me.head, ref.head, TOL.head, W.head);
    return w >= 1 ? s / w : null;                     // at least one hand
  },
  delta(a, b) {
    const d = (p: V3 | null, q: V3 | null) => (p && q ? sub(p, q) : [0, 0, 0]);
    return [...d(a.wL, b.wL), ...d(a.wR, b.wR), ...d(a.head, b.head).map(v => v * 0.6)];
  },
  still: 0.04,                                        // under ~6 cm of hand travel: you didn't move into it
};
