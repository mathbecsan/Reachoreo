// Bake Encendido's 38 four-count pieces into a move set file (schema "reachoreo.moveset/1"): the first set of
// Reachoreo's movement database. Each piece carries its robot and dancer tracks as data (not code), plus the
// profile the generator already uses (hits per half-count, energy, start/end pose) and its texts.
// New sets (salsa, bachata, hip-hop...) use the same schema, made from recordings of real dancers.
//
//   node tools/bake_moveset.mjs <moves_meta.json> <out/moveset.json>      (run via tools/export_moveset.py)
import { readFileSync, writeFileSync } from "node:fs";
import * as C from "../reachy_dance/dashboard/static/encendido-stage.mjs";

const [, , metaPath, outPath] = process.argv;
const meta = JSON.parse(readFileSync(metaPath, "utf8"));
const profiles = JSON.parse(readFileSync(new URL("../reachy_dance/choreography/move_profiles.json", import.meta.url), "utf8"));
const ROBOT_KEYS = ["yaw", "pitch", "roll", "body", "turn", "antL", "antR", "bob"];
const HUMAN_KEYS = Object.keys(C.human());
const STEPS = 8;   // samples per count (the learned-from-video format uses 8 too)
const r4 = x => Math.round(x * 1e4) / 1e4;

const pieces = [];
for (let src = 0; src < C.N; src++) for (const half of [0, 1]) {
  const m = meta.moves[src], prof = profiles.pieces.find(p => p.src === src && p.half === half);
  const A = [], B = [], H = [];
  for (let k = 0; k <= 4 * STEPS; k++) {
    const c = Math.min(3.999, k / STEPS), S = C.raw(src, src * C.PH + (4 * half + c) * C.BEAT);
    for (const key of ROBOT_KEYS) { A.push(r4(S.L[key] ?? 0)); B.push(r4(S.R[key] ?? 0)); }
    for (const key of HUMAN_KEYS) H.push(r4(+S.H[key] || 0));
  }
  pieces.push({
    id: `encendido:${src}${"ab"[half]}`,
    name: `${m.name}${half ? " (counts 5-8)" : " (counts 1-4)"}`,
    style: "robot-electro", tags: [m.kind].filter(Boolean),
    counts: 4, energy: prof.energy, kind: m.kind || null,
    mirrorable: true,
    text: { you: (meta.you_halves[src] || [])[half] || m.you || "", A: m.A || "", B: m.B || "" },
    profile: { accents: prof.accents, robotAccents: prof.robot_accents, humanAccents: prof.human_accents, start: prof.start, end: prof.end },
    robotA: A, robotB: B, human: H,
  });
}
const set = {
  schema: "reachoreo.moveset/1", id: "encendido", name: "Encendido", style: "robot-electro",
  source: "Encendido (Reachoreo original): preview/encendido-preview.html via static/encendido-stage.mjs",
  stepsPerCount: STEPS, robotKeys: ROBOT_KEYS, humanKeys: HUMAN_KEYS,
  units: "robot: score units (reachy_dance/pose.py); human: HumanPose (xr/src/stage-types.d.ts), 3D joints via xr/src/body.ts",
  pieces,
};
writeFileSync(outPath, JSON.stringify(set));
console.log(`baked move set ${set.id}: ${pieces.length} pieces, ${(JSON.stringify(set).length / 1e6).toFixed(2)} MB`);
