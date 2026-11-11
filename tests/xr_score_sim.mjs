// Headset scoring with a simulated Quest dancer (run by tests/test_xr.py): node --experimental-strip-types xr_score_sim.mjs <repo root>
// A dancer with a 1.55 m arm span (the coach: 1.68 m), facing 40° off, 1 cm tracking noise, controller grips 6 cm off
// the wrist, 30 ms of lag, at 72 fps.
const S = await import(process.argv[2] + "/xr/src/score.ts"), X = await import(process.argv[2] + "/xr/src/xrscore.ts");
const C = await import(process.argv[2] + "/reachy_dance/dashboard/static/encendido-stage.mjs");
const PX = 2.5 / 880, at = t => C.poseAt(Math.max(0, Math.min(C.DUR - 1e-3, t))).H;
const gold = new Set([[8,7],[9,2],[12,3],[15,7],[19,5]].map(([p,c]) => (p-1)*8+c-1));
const ref = X.coachReference(at, PX);
const moves = S.retarget(S.scoredMoves(at, C.BEAT, C.N * 8, PX, k => gold.has(k)), ref.at);
let seed = 3; const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
const g = () => Math.sqrt(-2 * Math.log(rnd() + 1e-12)) * Math.cos(2 * Math.PI * rnd());
function run(canonAt, lag, span = 1.55, yaw = 0.7) {
  const origin = [0.3, 1.62, 4.0], f = [-Math.sin(yaw), 0, -Math.cos(yaw)], r = [Math.cos(yaw), 0, -Math.sin(yaw)];
  const world = (c, n = 0.01) => [0, 1, 2].map(i => origin[i] + span * (-c[0] * r[i] + c[2] * f[i]) + (i === 1 ? span * c[1] : 0) + n * g());
  const cal = { origin, yaw, span };
  const sc = new S.Scorer(moves, C.BEAT, 0, Infinity, X.XR_METRIC);
  for (let t = 0; t < C.DUR + 1; t += 1 / 72) {
    const c = canonAt(t - lag);
    const grip = p => world(p).map((v, i) => v + 0.06 * (i === 1 ? -1 : 0));   // controller grip a little off the wrist
    sc.push(X.xrFeatures(t, world(c.head, 0.004), grip(c.wL), grip(c.wR), cal)); sc.judge(t);
  }
  const seen = sc.judged.filter(j => !j.skipped), ps = seen.filter(j => j.rating === "PERFECT" || j.rating === "SUPER").length;
  return { moves: seen.length, ps: +(ps / seen.length).toFixed(3), points: +sc.fraction.toFixed(3), stars: sc.stars };
}
const still = X.coachReference(() => ({ ...at(0), aL: 0.12, aR: 0.12, eL: 0.1, eR: 0.1 }), PX).at(0);
const sloppy = t => { const c = ref.at(t); const j = p => p.map(v => v + 0.08 * Math.sin(t * 2.1 + v * 9)); return { head: c.head, wL: j(c.wL), wR: j(c.wR) }; };
const swapped = t => { const c = ref.at(t); return { head: c.head, wL: [-c.wR[0], c.wR[1], c.wR[2]], wR: [-c.wL[0], c.wL[1], c.wL[2]] }; };  // copying un-mirrored
console.log(JSON.stringify({ span: ref.span.toFixed(3), copy: run(ref.at, 0.03), still: run(() => still, 0), late: run(ref.at, 0.6), sloppy: run(sloppy, 0.03), wrongSide: run(swapped, 0.03) }));
