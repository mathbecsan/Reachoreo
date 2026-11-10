// The loaded choreography as the pages see it: poses for both robots and the dancer at any show time.
// Encendido plays as written; a dance made from a song strings Encendido's phrases together at the song's
// count speed, some mirrored left-to-right (the same mapping as reachy_dance/choreography/library.py).
import * as C from "./encendido-stage.mjs";
const clamp = (x, a, b) => Math.min(b, Math.max(a, x));
const ease = x => { x = clamp(x, 0, 1); return x * x * (3 - 2 * x); };

function mix(a, b, k) {
  if (typeof a === "number") return a + (b - a) * k;
  const o = {}; for (const key in b) o[key] = mix(a[key], b[key], k); return o;
}
const flipRobot = r => ({ ...r, yaw: -r.yaw, roll: -r.roll, body: -r.body, turn: -r.turn, antL: r.antR, antR: r.antL });
function flipHuman(h) {
  return { ...h, x: -h.x, look: -h.look, tilt: -h.tilt, lean: -h.lean, face: -h.face,
           aL: h.aR, eL: h.eR, aR: h.aL, eR: h.eL, fLx: -h.fRx, fRx: -h.fLx, fLy: h.fRy, fRy: h.fLy, rotL: h.rotR, rotR: h.rotL };
}
export function mirrorStage(S) {
  return { L: flipRobot(S.R), R: flipRobot(S.L), H: flipHuman(S.H), lt: { ...S.lt, L: S.lt.R, R: S.lt.L } };
}

// TL: /api/timeline (name, beat, phrase_s, duration, phrases[{src, mirror, name, dancer, robots, act, cues}]).
export function makeShow(TL) {
  const N = TL.phrases.length;
  // Show time of every count: the song's tracked beats when the dance has them, else an even grid.
  const counts = TL.counts && TL.counts.length >= 8 * N + 1 ? TL.counts : Array.from({ length: 8 * N + 1 }, (_, k) => k * TL.beat);
  const DUR = counts[8 * N], BEAT = DUR / (8 * N), PH = 8 * BEAT;
  const first = counts[1] - counts[0], last = counts[8 * N] - counts[8 * N - 1];
  function countOf(t) {
    if (t <= counts[0]) return (t - counts[0]) / first;
    if (t >= counts[8 * N]) return 8 * N + (t - counts[8 * N]) / last;
    let lo = 0, hi = 8 * N;
    while (hi - lo > 1) { const m = (lo + hi) >> 1; if (counts[m] <= t) lo = m; else hi = m; }
    return lo + (t - counts[lo]) / (counts[lo + 1] - counts[lo]);
  }
  function timeOf(c) {
    if (c <= 0) return counts[0] + c * first;
    if (c >= 8 * N) return counts[8 * N] + (c - 8 * N) * last;
    const k = Math.floor(c); return counts[k] + (c - k) * (counts[k + 1] - counts[k]);
  }
  const blend = Math.min(0.3, 0.6 * BEAT);
  const phraseAt = t => clamp(Math.floor(countOf(t) / 8), 0, N - 1);
  // 4-count pieces, two per phrase (same rules as library.py: pieces_of, joint, XF_BEFORE/XF_AFTER)
  const piecesOf = (p, i) => p.learned ? [0, 1].map(half => ({ src: p.src ?? 0, half, mirror: false, learned: i }))
    : p.halves?.length === 2 ? p.halves.map(h => ({ src: h.src, half: h.half, mirror: !!h.mirror }))
    : [0, 1].map(half => ({ src: p.src ?? 0, half, mirror: !!p.mirror }));
  const segs = TL.phrases.flatMap((p, i) => piecesOf({ src: i, ...p }, i));
  const joint = (a, b) => {
    if (a.learned != null || b.learned != null)
      return a.learned != null && b.learned != null && ((a.learned === b.learned && a.half === 0 && b.half === 1) || (b.learned === a.learned + 1 && a.half === 1 && b.half === 0)) ? "inside" : "cross";
    return a.src === b.src && a.mirror === b.mirror && a.half === 0 && b.half === 1 ? "inside"
      : !a.mirror && !b.mirror && a.half === 1 && b.half === 0 && b.src === a.src + 1 ? "encendido" : "cross";
  };
  // phrases learned from a video: stored tracks (learn.mjs HUMAN_KEYS / ROBOT_KEYS), STEPS samples per count
  const LR = TL.learned?.phrases || {}, LSTEPS = TL.learned?.steps || 8;
  const HK = ["x", "drop", "lean", "look", "tilt", "headDown", "shrug", "aL", "eL", "aR", "eR", "fLx", "fLy", "fRx", "fRy"];
  const RK = ["yaw", "pitch", "roll", "body", "turn", "antL", "antR", "bob"];
  const LIGHT = { L: 1, C: 1, R: 1, M: 1, warm: 1, party: 0.5, lamp: 1 };
  function learnedAt(j, t) {
    const g = segs[j], tr = LR[String(g.learned)], x = (4 * g.half + clamp(countOf(t) - 4 * j, 0, 4)) * LSTEPS;
    const k = Math.min(Math.floor(x), tr.A.length - 2), f = x - k, lerpRow = rows => rows[k].map((v, n) => v + f * (rows[k + 1][n] - v));
    const as = (keys, vals, base) => { const o = { ...base }; keys.forEach((key, n) => o[key] = vals[n]); return o; };
    return { L: as(RK, lerpRow(tr.A), C.robot()), R: as(RK, lerpRow(tr.B), C.robot()), H: as(HK, lerpRow(tr.H), C.human()), lt: { ...LIGHT } };
  }
  const joints = ["start", ...segs.slice(1).map((g, j) => joint(segs[j], g))];
  const XF_BEFORE = 0.5, XF_AFTER = 0.25, span = XF_BEFORE + XF_AFTER;
  function segRaw(j, t) {
    if (segs[j].learned != null) return learnedAt(j, t);
    const g = segs[j], c = clamp(countOf(t) - 4 * j, 0, 4 - 1e-4);
    const S = C.raw(g.src, g.src * C.PH + (4 * g.half + c) * C.BEAT);
    return g.mirror ? mirrorStage(S) : S;
  }
  function raw(i, t) { return segRaw(2 * i + (countOf(t) - 8 * i >= 4 ? 1 : 0), t); }
  function poseAt(t) {
    t = clamp(t, 0, DUR - 1e-4);
    const c = countOf(t), j = clamp(Math.floor(c / 4), 0, segs.length - 1), cur = segRaw(j, t);
    if (j > 0) {
      const kind = joints[j], tb = timeOf(4 * j);
      if (kind === "encendido" && t - tb < blend) return mix(segRaw(j - 1, tb - 1e-4), cur, ease((t - tb) / blend));
      if (kind === "cross" && c - 4 * j < XF_AFTER) return mix(segRaw(j - 1, t), cur, ease((c - (4 * j - XF_BEFORE)) / span));
    }
    if (j + 1 < segs.length && joints[j + 1] === "cross" && c > 4 * j + 4 - XF_BEFORE) return mix(cur, segRaw(j + 1, t), ease((c - (4 * j + 4 - XF_BEFORE)) / span));
    return cur;
  }
  const PHRASES = TL.phrases.map((p, i) => ({ n: p.n, you: p.name, act: p.act, Y: p.dancer,
    A: p.robots?.A ?? C.PHRASES[p.src ?? i]?.A ?? "", B: p.robots?.B ?? C.PHRASES[p.src ?? i]?.B ?? "", cues: p.cues || [] }));
  // Sections for the "what to rehearse" menu: the whole dance, each act, a few short loops.
  const sections = [[`1 ${N}`, `Whole dance · 1–${N} (${fmt(DUR)})`]];
  let a0 = 0;
  for (let i = 1; i <= N; i++) {
    if (i === N || TL.phrases[i].act !== TL.phrases[a0].act) {
      if (i - a0 < N) sections.push([`${a0 + 1} ${i}`, `${TL.phrases[a0].act || "Part"} · ${a0 + 1}${i - 1 > a0 ? "–" + i : ""}`]);
      a0 = i;
    }
  }
  TL.phrases.forEach((p, i) => sections.push([`${i + 1} ${i + 1}`, `Loop phrase ${i + 1} · ${p.name}`]));
  return { name: TL.name, title: TL.title, N, PH, BEAT, DUR, poseAt, raw, phraseAt, countOf, timeOf, segs, joints, PHRASES, sections, song: TL.song, TL };
}
export const fmt = s => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`;
