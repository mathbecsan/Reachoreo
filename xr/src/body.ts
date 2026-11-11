// The coach's skeleton, from the choreography's dancer pose (stage poseAt(t).H), in metres. Pure maths (no three.js)
// so the coach mesh, headset scoring and the node tests all use exactly the same joints.
//
// Frame: the coach's own space before its spin, like the 2D preview: x = the audience's right, y = up from the floor,
// z = toward the audience. "L" joints are on the audience's left (the aL arm: the dancer's right arm).
import type { HumanPose } from "/static/encendido-stage.mjs";

export type V3 = [number, number, number];
const PX = 1.75 / 480;            // the preview's figure is ~480 px from floor to head top; the coach is 1.75 m

export interface Side { hip: V3; knee: V3; foot: V3; toe: V3; shoulder: V3; elbow: V3; wrist: V3; hand: V3 }
export interface Body {
  L: Side; R: Side; pelvis: V3; spine: [V3, V3]; neck: [V3, V3]; head: V3;
  headRot: V3;                    // Euler "YXZ" (x, y, z) of the head
  af: number;                     // how much of the body's width you see (1 = facing you, 0.3 = side on)
}

export function bodyJoints(h: HumanPose): Body {
  const P = (x: number, y: number, z = 0): V3 => [x * PX, y * PX, z];
  const cf = Math.cos(h.face), af = 0.3 + 0.7 * Math.abs(cf);
  const hipY = 200 - h.drop - 145 * h.sit;                            // above the floor (the preview's FLOOR - hipStand)
  const tl = 175 - 25 * h.sit;
  const sh = [Math.sin(h.lean) * tl, hipY + Math.cos(h.lean) * tl + h.shrug];
  const px = Math.cos(h.lean), py = Math.sin(h.lean);
  const side = (sx: -1 | 1, fxo: number, fyo: number, a: number, e: number): Side => {
    const s0 = [sh[0] + sx * 40 * px * af, sh[1] - sx * 40 * py - 6];
    const ang = a + h.lean * -sx, el = [s0[0] + sx * Math.sin(ang) * 98 * af, s0[1] - Math.cos(ang) * 98];
    const ang2 = ang + e, wr = [el[0] + sx * Math.sin(ang2) * 92 * af, el[1] - Math.cos(ang2) * 92];
    const E = P(el[0], el[1], 0.03), W = P(wr[0], wr[1], 0.04);
    const d = [W[0] - E[0], W[1] - E[1], W[2] - E[2]], n = Math.hypot(...d) || 1;
    return {
      hip: P(sx * 22 * af, hipY), foot: P(sx * 46 * af + fxo, Math.max(8, fyo + 8)),
      knee: P((sx * 22 * af + sx * 46 * af + fxo) / 2 + sx * (8 + 0.4 * Math.max(0, h.drop) + 0.12 * fyo), (hipY + fyo + 8) / 2 + 4, 0.02),
      toe: P(sx * 46 * af + fxo + sx * 6, Math.max(4, fyo + 3), 0.05),
      shoulder: P(s0[0], s0[1]), elbow: E, wrist: W, hand: [W[0] + d[0] / n * 0.05, W[1] + d[1] / n * 0.05, W[2] + d[2] / n * 0.05],
    };
  };
  return {
    L: side(-1, h.fLx, h.fLy, h.aL, h.eL), R: side(1, h.fRx, h.fRy, h.aR, h.eR),
    pelvis: P(0, hipY + 10),
    spine: [P(Math.sin(h.lean) * 40, hipY + Math.cos(h.lean) * 40), P(sh[0] * 0.92, sh[1] - 20)],
    neck: [P(sh[0], sh[1]), P(sh[0] + Math.sin(h.lean) * 34, sh[1] + Math.cos(h.lean) * 34 - 18 * h.headDown)],
    head: P(sh[0] + Math.sin(h.lean) * 68 + h.look * 6, sh[1] + 68 - 26 * h.headDown, 0.01),
    headRot: [0.6 * h.headDown, 0.8 * h.look, -h.tilt], af,
  };
}

/** A joint as placed on stage, relative to the dancer's mark: turned by the spin (the coach's root rotation.y =
 *  face), moved to x on stage and upstage by depth (the coach's root position, see main.ts). */
export function onStage(p: V3, h: HumanPose, pxToM: number): V3 {
  const c = Math.cos(h.face), s = Math.sin(h.face);
  return [p[0] * c + p[2] * s + h.x * pxToM, p[1], -p[0] * s + p[2] * c - 0.8 * h.depth];
}
