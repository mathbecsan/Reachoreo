// Bake a dance into a self-contained Reachoreo dance file (schema "reachoreo.dance/1").
// The motion comes from the app's own code, so every player (the VR game, later the robots or other clients) gets
// exactly what the dashboard shows: static/choreo.mjs makeShow(timeline).poseAt(t) for both robots and the dancer,
// and xr/src/body.ts bodyJoints() for the dancer's 3D joints.
//
//   node --experimental-strip-types tools/bake_dance.mjs <timeline.json> <out/dance.json> [--fps 20]
// Normally run through tools/export_dance.py, which builds the timeline with the app's Python first.
import { readFileSync, writeFileSync } from "node:fs";
import { makeShow } from "../reachy_dance/dashboard/static/choreo.mjs";
import { bodyJoints } from "../xr/src/body.ts";

const [, , tlPath, outPath, ...rest] = process.argv;
if (!tlPath || !outPath) { console.error("usage: bake_dance.mjs <timeline.json> <out.json> [--fps 20]"); process.exit(2); }
const fps = Number(rest[rest.indexOf("--fps") + 1]) || 20;
const TL = JSON.parse(readFileSync(tlPath, "utf8"));
const meta = JSON.parse(readFileSync(tlPath.replace(/\.json$/, ".meta.json"), "utf8"));
const show = makeShow(TL);

const ROBOT_KEYS = ["yaw", "pitch", "roll", "body", "turn", "antL", "antR", "bob"];   // score units (reachy_dance/pose.py)
const SIDE = ["hip", "knee", "foot", "toe", "shoulder", "elbow", "wrist", "hand"];
const JOINTS = ["pelvis", "spine1", "spine2", "neck1", "neck2", "head", ...SIDE.map(j => "L_" + j), ...SIDE.map(j => "R_" + j)];
const PX = 1.75 / 480;   // preview px -> metres (xr/src/body.ts)
const r4 = x => Math.round(x * 1e4) / 1e4;

const counts = TL.counts && TL.counts.length >= 8 * show.N + 1 ? TL.counts : Array.from({ length: 8 * show.N + 1 }, (_, k) => r4(k * TL.beat));
const n = Math.floor(show.DUR * fps) + 1;
const robotA = [], robotB = [], dancer = [], dancerRoot = [];
for (let i = 0; i < n; i++) {
  const t = i / fps, S = show.poseAt(t);
  for (const k of ROBOT_KEYS) robotA.push(r4(S.L[k] ?? 0));
  for (const k of ROBOT_KEYS) robotB.push(r4(S.R[k] ?? 0));
  const b = bodyJoints(S.H);
  const pts = [b.pelvis, b.spine[0], b.spine[1], b.neck[0], b.neck[1], b.head, ...SIDE.map(j => b.L[j]), ...SIDE.map(j => b.R[j])];
  for (const p of pts) dancer.push(r4(p[0]), r4(p[1]), r4(p[2]));
  dancerRoot.push(r4((S.H.x || 0) * PX), r4(S.H.depth || 0), r4(S.H.face || 0));
}

const [artist, title] = TL.title && TL.title.includes(" - ") ? TL.title.split(" - ", 2) : [meta.artist || "", TL.title || TL.name];
const file = {
  schema: "reachoreo.dance/1",
  id: TL.name,
  title: meta.title || title,
  artist: meta.artist || artist,
  style: meta.style || "unknown",
  tags: meta.tags || [],
  difficulty: meta.difficulty || 2,
  license: meta.license || null,          // for curated songs: {name, url, credit}; null = personal, never ship
  song: TL.song ? { file: meta.songFile || TL.song.file, bpm: TL.song.bpm, firstDownbeat: TL.song.first_downbeat_s, duration: TL.song.duration_s } : null,
  countBpm: r4(60 / show.BEAT),
  beatsPerCount: TL.beats_per_count || 1,
  duration: r4(show.DUR),
  counts,                                  // show time (s) of every count; 0 = the first downbeat
  phrases: TL.phrases.map((p, i) => ({
    n: p.n, name: p.name, act: p.act || "", start: r4(show.timeOf(8 * i)), end: r4(show.timeOf(8 * i + 8)),
    pieces: show.segs.slice(2 * i, 2 * i + 2).map(s => s.learned != null ? `learned:${s.learned}.${s.half}` : `encendido:${s.src}${"ab"[s.half]}${s.mirror ? "~" : ""}`),
  })),
  frameRate: fps,
  frames: n,
  robotKeys: ROBOT_KEYS,
  robotA, robotB,                          // flat: frames x robotKeys (score units; convert with pose.py to_sdk)
  dancerFrame: "metres; x = audience's right, y = up from the floor, z = toward the audience; L_ joints are on the audience's left (the dancer's right side)",
  dancerJoints: JOINTS,
  dancer,                                  // flat: frames x joints x 3
  dancerRootKeys: ["x_m", "depth", "face_rad"],
  dancerRoot,                              // flat: frames x 3 (travel on stage and spin; joints above are before these)
  source: { app: "reachy-dance", choreo: meta.choreo || null, baked: new Date().toISOString().slice(0, 16).replace("T", " ") },
};
writeFileSync(outPath, JSON.stringify(file));
console.log(`baked ${file.id}: ${n} frames at ${fps} fps, ${file.phrases.length} phrases, ${(JSON.stringify(file).length / 1e6).toFixed(1)} MB`);
