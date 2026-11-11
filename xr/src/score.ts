// Scoring, Just Dance style: every move gets PERFECT / SUPER / GOOD / OK / X from how close your pose is to the
// coach's (position) and whether you moved the same way into it (direction). The best match within ±150 ms of the
// move counts, so camera and tracking latency don't cost points. Pure module (no DOM, no three.js) so
// tests/test_xr.py can run it in node with simulated dancers.
//
// Everything is in the choreography's camera view (aL = the arm on the camera's left), the same frame as the 2D
// rehearsal page's matchAt(); mirroring only changes how the coach is drawn, never what is scored.
import type { HumanPose } from "/static/encendido-stage.mjs";

export type Rating = "PERFECT" | "SUPER" | "GOOD" | "OK" | "X";
export const POINTS: Record<Rating, number> = { PERFECT: 100, SUPER: 80, GOOD: 50, OK: 20, X: 0 };
// Tuned with tests/test_xr.py: a clean copy of the coach (with 100 ms of camera lag and tracking noise) scores
// >= 90 % PERFECT or SUPER; standing still scores < 10 % of the points.
export const THRESHOLDS: [Rating, number][] = [["PERFECT", 0.86], ["SUPER", 0.76], ["GOOD", 0.68], ["OK", 0.6]];
export const STARS = [0.2, 0.4, 0.6, 0.75, 0.9];          // fraction of the maximum points for 1..5 stars
const GOLD_BONUS = 2;                                       // gold moves count double (if GOOD or better)
const WINDOW = 0.15;                                        // ± seconds around the move
const LAND = 0.25;                                          // a move is judged a quarter beat after its count (the snap has landed)
const DIR_SPAN = 0.5;                                       // beats of motion that define a move's direction
const MIN_MOTION = 0.3;                                     // radians: below this a move is a hold, judged on position only

/** One sample of you (or the coach): limb directions in radians, plus head turn, lean and sideways position. */
export interface Features {
  t: number;                    // show time (seconds), already corrected for your input latency
  aL: number | null; uL: number | null; aR: number | null; uR: number | null;   // upper arm / forearm directions
  look: number | null; lean: number | null; x: number | null;                 // x in metres from your centre mark
}
const wrap = (a: number) => Math.atan2(Math.sin(a), Math.cos(a));
const ANGLES = ["aL", "uL", "aR", "uR"] as const;
const WEIGHTS = { aL: 1, uL: 0.7, aR: 1, uR: 0.7, look: 0.35, lean: 0.4, x: 0.5 };
const TOL = { aL: Math.PI / 2.2, uL: Math.PI / 2.2, aR: Math.PI / 2.2, uR: Math.PI / 2.2, look: 1.2, lean: 0.45, x: 0.6 };

export function featuresOf(h: HumanPose, t: number, pxToM: number): Features {
  return { t, aL: h.aL, uL: wrap(h.aL + h.eL), aR: h.aR, uR: wrap(h.aR + h.eR), look: h.look, lean: h.lean, x: h.x * pxToM };
}

/** Your features from MediaPipe landmarks, via the 2D page's myPose(); hips give lean, the shoulders' centre gives x. */
export function featuresFromLandmarks(lm: { x: number; y: number; visibility?: number }[], W: number, H: number, t: number,
    mine: { aL: number; eL: number; aR: number; eR: number; look: number; sw: number; seen: Record<string, boolean> },
    centre: { x: number; sw: number } | null): Features {
  const vis = (i: number) => (lm[i].visibility ?? 1) > 0.5;
  const P = (i: number) => [lm[i].x * W, lm[i].y * H];
  const sh = [(P(11)[0] + P(12)[0]) / 2, (P(11)[1] + P(12)[1]) / 2];
  let lean: number | null = null;
  if (vis(23) && vis(24)) { const hp = [(P(23)[0] + P(24)[0]) / 2, (P(23)[1] + P(24)[1]) / 2]; lean = Math.atan2(sh[0] - hp[0], hp[1] - sh[1]); }
  const ref = centre ?? { x: W / 2, sw: mine.sw };
  return {
    t, aL: mine.seen.aL ? mine.aL : null, uL: mine.seen.eL ? wrap(mine.aL + mine.eL) : null,
    aR: mine.seen.aR ? mine.aR : null, uR: mine.seen.eR ? wrap(mine.aR + mine.eR) : null,
    look: mine.look, lean, x: (sh[0] - ref.x) / (ref.sw || 1) * 0.38,      // shoulders are ~0.38 m apart
  };
}

/** How close two poses are, 0..1, over the joints both have. */
export function positionMatch(me: Features, ref: Features): number | null {
  let s = 0, w = 0;
  for (const k of ["aL", "uL", "aR", "uR", "look", "lean", "x"] as const) {
    const a = me[k], b = ref[k];
    if (a == null || b == null || !Number.isFinite(a) || !Number.isFinite(b)) continue;   // a glitchy tracker frame
    const d = k === "look" || k === "x" || k === "lean" ? Math.abs(a - b) : Math.abs(wrap(a - b));
    s += WEIGHTS[k] * Math.max(0, 1 - d / TOL[k]); w += WEIGHTS[k];
  }
  return w >= 1 ? s / w : null;                              // at least one arm's worth of evidence
}

function delta(a: Features, b: Features): number[] {
  return ANGLES.map(k => (a[k] != null && b[k] != null ? wrap((a[k] as number) - (b[k] as number)) : 0));
}

/** How a kind of input is compared: the webcam's limb angles (below) or the headset's head and hands (xrscore.ts). */
export interface Metric<F extends { t: number }> {
  match(me: F, ref: F): number | null;       // 0..1, or null when there's too little of you to judge
  delta(a: F, b: F): number[];               // a's change from b, for the direction of a move
  still: number;                             // below this much change you didn't move into the move
}
export const ANGLE_METRIC: Metric<Features> = { match: positionMatch, delta, still: 0.08 };

export interface Move<F = Features> { k: number; phrase: number; count: number; time: number; gold: boolean; ref: F; refPrev: F; moving: boolean }
export interface Judged<F = Features> extends Move<F> { score: number; rating: Rating; points: number; offset_ms: number | null; pos: number | null; dir: number | null;
  skipped: boolean }   // no camera frame at all inside the window (the page stalled): not judged, not counted

/** The same moves with another kind of reference (the coach's head and hands for the headset), same timing. */
export function retarget<F>(moves: Move[], refAt: (t: number) => F): Move<F>[] {
  return moves.map(m => ({ ...m, ref: refAt(m.time), refPrev: refAt(m.refPrev.t) }));
}

/** A camera frame in which nobody was tracked: it still proves the camera was looking, so a missed move is an X. */
export const nobody = (t: number): Features => ({ t, aL: null, uL: null, aR: null, uR: null, look: null, lean: null, x: null });

/** The moves to score: counts where the coach strikes a new pose or moves (holds in a freeze aren't moves). */
export function scoredMoves(poseAt: (t: number) => HumanPose, beat: number, counts: number, pxToM: number,
    gold: (k: number) => boolean): Move[] {
  const out: Move[] = [];
  let last: Features | null = null;
  for (let k = 0; k < counts; k++) {
    const time = (k + LAND) * beat;
    const ref = featuresOf(poseAt(time), time, pxToM), refPrev = featuresOf(poseAt(time - DIR_SPAN * beat), time - DIR_SPAN * beat, pxToM);
    const motion = Math.hypot(...delta(ref, refPrev));
    const changed = !last || Math.hypot(...delta(ref, last)) > 0.35 || Math.abs((ref.x ?? 0) - (last.x ?? 0)) > 0.12;
    if (motion > MIN_MOTION || changed || gold(k)) {
      out.push({ k, phrase: Math.floor(k / 8) + 1, count: (k % 8) + 1, time, gold: gold(k), ref, refPrev, moving: motion > MIN_MOTION });
      last = ref;
    }
  }
  return out;
}

export function rate(score: number): Rating {
  for (const [r, th] of THRESHOLDS) if (score >= th) return r;
  return "X";
}

/** Live scorer: push your samples as they arrive, call judge(t) every frame to get the moves that just closed. */
export class Scorer<F extends { t: number } = Features> {
  private samples: F[] = [];
  private next = 0;
  judged: Judged<F>[] = [];
  combo = 0; bestCombo = 0; points = 0;
  maxPoints: number;
  readonly moves: Move<F>[]; readonly beat: number; private to: number; private metric: Metric<F>;

  // (plain fields, no parameter properties: node's type stripping runs this file in the tests)
  constructor(moves: Move<F>[], beat: number, from = 0, to = Infinity, metric?: Metric<F>) {
    this.moves = moves; this.beat = beat; this.to = to; this.metric = metric ?? (ANGLE_METRIC as unknown as Metric<F>);
    this.maxPoints = moves.filter(m => m.time >= from && m.time < to).reduce((s, m) => s + 100 * (m.gold ? GOLD_BONUS : 1), 0);
    this.next = moves.findIndex(m => m.time >= from); if (this.next < 0) this.next = moves.length;
  }

  push(f: F) {
    this.samples.push(f);
    const old = f.t - 3; while (this.samples.length && this.samples[0].t < old) this.samples.shift();
  }

  private sampleAt(t: number): F | null {
    let best: F | null = null, bd = Infinity;
    for (const s of this.samples) { const d = Math.abs(s.t - t); if (d < bd) { bd = d; best = s; } }
    return best && bd < 0.08 ? best : null;
  }

  private score(m: Move<F>): Judged<F> {
    let best = { s: -1, pos: null as number | null, dir: null as number | null, off: null as number | null }, frames = 0;
    for (const me of this.samples) {
      const off = me.t - m.time;
      if (Math.abs(off) > WINDOW) continue;
      frames++;
      const pos = this.metric.match(me, m.ref);
      if (pos == null) continue;
      let dir: number | null = null;
      if (m.moving) {
        const prev = this.sampleAt(me.t - DIR_SPAN * this.beat);
        const rd = this.metric.delta(m.ref, m.refPrev), md = prev ? this.metric.delta(me, prev) : rd.map(() => 0);
        const rn = Math.hypot(...rd), mn = Math.hypot(...md);
        dir = mn < this.metric.still || rn < 1e-9 ? 0 : Math.max(0, rd.reduce((s, v, i) => s + v * md[i], 0) / (rn * mn));
      }
      const s = dir == null ? pos : 0.65 * pos + 0.35 * dir;
      if (s > best.s) best = { s, pos, dir, off };
    }
    const score = Math.max(0, best.s), rating = best.s < 0 ? "X" : rate(score);
    const points = POINTS[rating] * (m.gold && POINTS[rating] >= POINTS.GOOD ? GOLD_BONUS : 1);
    return { ...m, score, rating, points, offset_ms: best.off == null ? null : Math.round(best.off * 1000), pos: best.pos, dir: best.dir,
      skipped: frames === 0 };
  }

  /** Judge every move whose window has closed by show time t. */
  judge(t: number): Judged<F>[] {
    const out: Judged<F>[] = [];
    while (this.next < this.moves.length && this.moves[this.next].time < this.to && this.moves[this.next].time + WINDOW + 0.03 <= t) {
      const j = this.score(this.moves[this.next++]);
      this.judged.push(j); out.push(j);
      if (j.skipped) { this.maxPoints -= 100 * (j.gold ? GOLD_BONUS : 1); continue; }   // the combo carries on
      this.points += j.points;
      this.combo = POINTS[j.rating] >= POINTS.GOOD ? this.combo + 1 : 0; this.bestCombo = Math.max(this.bestCombo, this.combo);
    }
    return out;
  }

  get fraction() { return this.maxPoints ? this.points / this.maxPoints : 0; }
  get stars() { return STARS.filter(s => this.fraction >= s).length; }
  get done() { return this.next >= this.moves.length || this.moves[this.next].time >= this.to; }
}
