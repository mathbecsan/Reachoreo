// Reachoreo 3D rehearsal (/rehearse): the kitchen and both Reachys performing Encendido's score at true scale, on the
// audio clock, a life-size coach, the moves lane, practice, webcam scoring on the desktop and, on a Quest, VR and AR
// (xr.ts). URL options: ?t=30 (freeze at 0:30), &compare=1 (the 2D preview beside the 3D view), &mirror=0,
// ?sim=copy|still (a simulated dancer), ?emulate=quest3 (an emulated Quest 3, for testing VR/AR on a desktop).
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { MeshoptDecoder } from "three/examples/jsm/libs/meshopt_decoder.module.js";
import type * as Stage from "/static/encendido-stage.mjs";
import { ShowClock } from "./clock";
import { Kitchen } from "./kitchen";
import { LAYOUT } from "./layout";
import { Coach, mirrorHuman } from "./coach";
import { Ghost } from "./ghost";
import { GOLD, Lane } from "./lane";
import { Reachy } from "./robot";
import { featuresFromLandmarks, featuresOf, nobody, retarget, Scorer, scoredMoves, type Judged } from "./score";
import { coachReference, XR_METRIC, type XrFeatures } from "./xrscore";
import { XrMode, type Hud } from "./xr";
import { DEFAULT_CAL, toSdk, type Calibration } from "./sdk";

const $ = (id: string) => document.getElementById(id)!;
const params = new URLSearchParams(location.search);
const frozen = params.has("t") ? Number(params.get("t")) : null;
const compare = params.get("compare") === "1";
// An emulated Quest 3 (Meta's IWER, the runtime inside the Immersive Web Emulator), for testing VR and AR here.
if (params.get("emulate") === "quest3") {
  const { XRDevice, metaQuest3 } = await import("iwer");
  const dev = new XRDevice(metaQuest3); dev.installRuntime({ forceInstall: true } as never);
  Object.assign(window, { __iwer: dev });
}

const C: typeof Stage = await import(/* @vite-ignore */ "/static/encendido-stage.mjs");
const info = await fetch("/api/library/encendido").then(r => r.json()).catch(() => null);
const cal: Calibration = { ...DEFAULT_CAL, ...(info?.timeline?.cal || {}) };
const phrases: { n: number; name: string; act: string; dancer: string }[] = info?.timeline?.phrases || [];

// ---------- renderer, camera, scene ----------
const view = $("view") as HTMLDivElement;
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFShadowMap;
renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.1;
view.appendChild(renderer.domElement);
const scene = new THREE.Scene(); scene.background = new THREE.Color("#0d0c1c");
const camera = new THREE.PerspectiveCamera(50, 1, 0.05, 50);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
// Your view: standing 3 m in front of the coach at eye height, like the brief (VR does the same with your real head).
// On narrow screens the camera backs off so the counter and both robots still fit.
function resetView() {
  const vfov = camera.fov * Math.PI / 180, hfov = 2 * Math.atan(Math.tan(vfov / 2) * camera.aspect);
  const fitBack = (LAYOUT.counter.length + 0.4) / 2 / Math.tan(hfov / 2) - (LAYOUT.dancer.z - LAYOUT.counter.frontZ);
  const d = Math.max(3.0, fitBack);
  camera.position.set(0, 1.6, LAYOUT.dancer.z + d); controls.target.set(0, 0.62, LAYOUT.dancer.z - 0.6); controls.update();   // aim low: the lane covers the bottom of the screen
}

// everything on stage lives in one group, so AR can set it onto your real counter (and VR around where you stand)
const world = new THREE.Group(); scene.add(world);
const kitchen = new Kitchen(renderer, scene, world);
const loader = new GLTFLoader().setMeshoptDecoder(MeshoptDecoder);
const gltf = await loader.loadAsync(`${import.meta.env.BASE_URL}models/reachy_mini.glb`);
const robots = { A: new Reachy(gltf, "Reachy 1"), B: new Reachy(gltf, "Reachy 2") };
for (const [side, r] of Object.entries(robots)) {
  r.root.position.set(LAYOUT.robots[side as "A" | "B"].x, LAYOUT.counter.height, LAYOUT.robots.z);
  world.add(r.root);
}
// the coach: life-size, where the dancer dances, facing you (the audience / camera)
const coach = new Coach({ color: 0x2fc7ff, glow: 0xb8f4ff });
coach.root.position.set(0, 0, LAYOUT.dancer.z); world.add(coach.root);
let coachZ: number = LAYOUT.dancer.z;            // in AR the coach may stand closer to the counter (xr.ts fitToMe)
const ghostBody = new Coach({ color: 0xf27aa8, glow: 0xf27aa8, opacity: 0.35, outline: false });
ghostBody.root.visible = false; world.add(ghostBody.root);
const ghost = new Ghost();
// where you stand
const mark = new THREE.Mesh(new THREE.RingGeometry(0.28, 0.32, 48), new THREE.MeshBasicMaterial({ color: 0xf27aa8, transparent: true, opacity: 0.55 }));
mark.rotation.x = -Math.PI / 2; mark.position.set(0, 0.003, LAYOUT.dancer.z); world.add(mark);

// ---------- the clock and the transport ----------
const clock = new ShowClock(C.DUR);
if (frozen != null) clock.seek(frozen);
const ready = clock.load().then(() => { ($("play") as HTMLButtonElement).disabled = false; });   // the track is built before you press Play
($("play") as HTMLButtonElement).disabled = true;
// Practice: a phrase range, looped, at 50/75/100 %, with a countdown before each pass. "Full run" = phrases 1 to 19.
const COUNTDOWN = 4;                                             // counts of lead-in before each pass
const range = { from: 1, to: C.N, loop: false };
const startOf = (n: number) => (n - 1) * C.PH, endOf = (n: number) => n * C.PH;
const lead = () => startOf(range.from) - (range.from === 1 ? 8 : COUNTDOWN) * C.BEAT;   // phrase 1 keeps the 8-count count-in
const opts = C.PHRASES.map((p: { you: string }, i: number) => `<option value="${i + 1}">${i + 1}. ${p.you}</option>`).join("");
const selFrom = $("from") as HTMLSelectElement, selTo = $("to") as HTMLSelectElement;
selFrom.innerHTML = opts; selTo.innerHTML = opts; selTo.value = String(C.N);
const applyRange = () => {
  range.from = Number(selFrom.value); range.to = Math.max(range.from, Number(selTo.value)); selTo.value = String(range.to);
  range.loop = ($("loop") as HTMLInputElement).checked; clock.seek(lead());
};
selFrom.onchange = selTo.onchange = applyRange;
($("loop") as HTMLInputElement).onchange = () => { range.loop = ($("loop") as HTMLInputElement).checked; };
($("speed") as HTMLSelectElement).onchange = e => clock.setRate(Number((e.target as HTMLSelectElement).value));
async function play() {                  // start or resume
  await ready;
  const t = clock.showTime();
  if (t >= endOf(range.to) - 0.01 || t < lead() - 0.01) { clock.seek(lead()); newPass(); } else if (!scorer) newPass();   // at the end: start over
  await clock.play();
}
async function again() { await ready; clock.seek(lead()); newPass(); await clock.play(); }
$("play").onclick = () => (clock.playing ? clock.pause() : play());
$("restart").onclick = again;
const mirrorBox = $("mirror") as HTMLInputElement, laneBox = $("lanebox") as HTMLInputElement;
if (params.get("mirror") === "0") mirrorBox.checked = false;
// ---------- the webcam: your ghost, and scoring ----------
const showGhost = $("ghostbox") as HTMLInputElement;
$("camera").onclick = async () => {
  const b = $("camera") as HTMLButtonElement;
  if (ghost.on) { ghost.stop(); ghostBody.root.visible = false; b.textContent = "📷 Camera: off"; b.classList.remove("on"); scorer = null; scoreUi(); return; }
  b.textContent = "📷 starting…";
  try {
    const label = await ghost.start(); b.textContent = "📷 Camera: on"; b.classList.add("on"); b.title = `tracking you with ${label}`;
    flash("Stand where you'll dance, arms relaxed, then press Calibrate", "#ede9ff");
  } catch (e) { b.textContent = "📷 Camera: off"; alert(`Camera unavailable: ${(e as Error).message}`); }
};
$("calibrate").onclick = () => flash(ghost.calibrate() ? "Calibrated: this spot is your centre mark" : "Turn the camera on and step into view first", "#ede9ff");
// tap test: tap along to 16 clicks (Space or click); the median lateness becomes the page's audio/visual offset
const tapDlg = $("tapdlg") as HTMLDialogElement;
$("taptest").onclick = async () => {
  if (clock.playing) clock.pause();
  const taps: number[] = [], tap = (e: Event) => { e.preventDefault(); taps.push(performance.now()); $("tapdot").classList.add("hit"); setTimeout(() => $("tapdot").classList.remove("hit"), 90); };
  tapDlg.showModal(); $("tapmsg").textContent = "Tap Space (or click) on every click…";
  addEventListener("keydown", tap); tapDlg.addEventListener("pointerdown", tap);
  const ms = await clock.tapTest((n, N) => { $("tapn").textContent = `${n} / ${N}`; }, () => taps);
  removeEventListener("keydown", tap); tapDlg.removeEventListener("pointerdown", tap);
  $("tapmsg").textContent = ms == null ? "Not enough taps on the beat: try again." : `Your offset: ${ms > 0 ? "+" : ""}${ms} ms. Saved, and the page now lines up with what you hear.`;
  $("avoff").textContent = `${clock.avOffsetMs} ms`;
};
$("tapclose").onclick = () => tapDlg.close();
$("avoff").textContent = `${clock.avOffsetMs} ms`;
const lane = new Lane($("lane") as HTMLCanvasElement, C);
const goldAt = (i: number, count: number) => GOLD.find(g => g.phrase === i + 1 && g.count === count);
const goldK = new Set(GOLD.map(g => (g.phrase - 1) * 8 + g.count - 1));
const poseH = (t: number) => C.poseAt(Math.max(0, Math.min(C.DUR - 1e-3, t))).H;
const MOVES = scoredMoves(poseH, C.BEAT, C.N * 8, LAYOUT.pxToM, k => goldK.has(k));
const XR_MOVES = retarget(MOVES, coachReference(poseH, LAYOUT.pxToM).at);      // the same moves, scored on head + hands
const CAMERA_LAG = 0.08;                // seconds from the camera seeing you to the pose arriving here
// ?sim=copy | still: a simulated dancer instead of the webcam (for demos and for testing the scoring screens)
const sim = params.get("sim");
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let scorer: Scorer<any> | null = null;
function newPass() {                    // each run (and each loop pass) is scored on its own
  scorer = xr.session ? new Scorer<XrFeatures>(XR_MOVES, C.BEAT, startOf(range.from), endOf(range.to), XR_METRIC)
    : ghost.on || sim ? new Scorer(MOVES, C.BEAT, startOf(range.from), endOf(range.to)) : null;
  $("summary").hidden = true; hud.summary = ""; scoreUi();
}
const COLORS: Record<string, string> = { PERFECT: "#3ddc84", SUPER: "#7fe3ff", GOOD: "#b46bff", OK: "#f2b544", X: "#ff6b6b" };
let flashT = 0;
function flash(text: string, color: string) {
  hud.flash = { text, color, at: performance.now() };
  const el = $("rating"); el.textContent = text; el.style.color = color; el.classList.remove("pop"); void el.offsetWidth; el.classList.add("pop"); flashT = performance.now();
}
function scoreUi() {
  const box = $("scorebox"); box.hidden = !scorer;
  if (!scorer) return;
  $("points").textContent = Math.round(scorer.points).toLocaleString();
  $("combo").textContent = scorer.combo >= 3 ? `combo ×${scorer.combo}` : "";
  const f = Math.min(1, scorer.fraction / 0.9);
  ($("starfill") as HTMLElement).style.width = `${100 * f}%`;
  $("starcount").textContent = `pts · ${scorer.stars}/5 ★`;
}
function judged(j: Judged) {
  if (j.skipped) return;                // the page stalled: nothing to show
  flash(j.gold && j.points > 0 ? `★ ${j.rating} ★` : j.rating, j.gold && j.points > 0 ? "#f2b544" : COLORS[j.rating]);
  scoreUi();
}
function passDone() {
  if (!scorer || !scorer.judged.length) return;
  const seen = scorer.judged.filter(j => !j.skipped), missed = scorer.judged.length - seen.length;
  const ps = seen.filter(j => j.rating === "PERFECT" || j.rating === "SUPER").length;
  $("summary").innerHTML = `<b>${scorer.stars} ★ · ${Math.round(scorer.points).toLocaleString()} points</b> · ${seen.length ? Math.round(100 * ps / seen.length) : 0} % PERFECT or SUPER · best combo ${scorer.bestCombo}`
    + (missed ? `<br><span style="color:var(--dim)">${missed} move${missed > 1 ? "s" : ""} not scored: the page dropped frames there</span>` : "");
  $("summary").hidden = false;
  hud.summary = $("summary").textContent || "";
}

// ---------- the 2D preview beside it, for comparing ----------
const flat = $("flat") as HTMLCanvasElement;
if (compare) { document.body.classList.add("compare"); }
function drawFlat(t: number) {
  const w = flat.clientWidth, h = flat.clientHeight, dpr = Math.min(devicePixelRatio, 2);
  if (flat.width !== Math.round(w * dpr)) { flat.width = Math.round(w * dpr); flat.height = Math.round(h * dpr); }
  const g = flat.getContext("2d")!; const S = C.poseAt(t);
  const s = Math.min(flat.width / C.VW, flat.height / C.VH);
  g.setTransform(1, 0, 0, 1, 0, 0); g.fillStyle = "#0d0c1c"; g.fillRect(0, 0, flat.width, flat.height);
  g.setTransform(s, 0, 0, s, (flat.width - C.VW * s) / 2, (flat.height - C.VH * s) / 2);
  C.setContext(g); C.drawKitchen({ ...S.lt, M: 1 }, C.POS.C + S.H.x, t);
  C.drawRobot(C.POS.L, S.L); C.drawRobot(C.POS.R, S.R); C.drawHuman(S.H);
}

// ---------- VR and AR on a Quest ----------
const hud: Hud = { count: "", gold: "", label: "", cue: "", act: "", time: "", flash: { text: "", color: "", at: 0 }, scoring: false,
  points: 0, combo: 0, stars: 0, fraction: 0, summary: "" };
const xr: XrMode = new XrMode({
  renderer, scene, world, kitchen, robots, clock, C, range, play, again,
  pause: () => { if (clock.playing) clock.pause(); },
  setRange(from, to, loop) {
    selFrom.value = String(from); selTo.value = String(Math.max(from, to)); ($("loop") as HTMLInputElement).checked = loop; applyRange();
    scorer = null; scoreUi();
  },
  get mirror() { return mirrorBox.checked; }, setMirror(on) { mirrorBox.checked = on; },
  setSpeed: async r => { ($("speed") as HTMLSelectElement).value = String(r); await clock.setRate(r); },
  push(f) { if (scorer && clock.playing) scorer.push(f); },
  setCoachZ(z) { coachZ = z; mark.position.z = z; },
  modeChanged(mode) {
    if (mode && ghost.on) $("camera").click();          // the webcam doesn't score in the headset
    scorer = null; scoreUi();
    if (!mode) { coachZ = LAYOUT.dancer.z; mark.position.z = coachZ; resize(); resetView(); }
  },
});
for (const [id, m] of [["enterar", "immersive-ar"], ["entervr", "immersive-vr"]] as const) {
  const b = $(id) as HTMLButtonElement;
  XrMode.supported(m).then(ok => { b.hidden = !ok; });
  b.onclick = () => xr.enter(m === "immersive-ar" ? "ar" : "vr").catch(e => alert(`Couldn't start ${m === "immersive-ar" ? "AR" : "VR"}: ${(e as Error).message}`));
}

// ---------- every frame ----------
function resize() {
  if (renderer.xr.isPresenting) return;            // the headset sets its own size
  const w = view.clientWidth, h = view.clientHeight;
  renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix();
}
addEventListener("resize", resize); resize(); resetView();
$("reset").onclick = resetView;
let lastLabel = "";
function frame(_time: number, xrFrame?: XRFrame) {
  const t = clock.showTime(), tt = Math.min(Math.max(t, 0), C.DUR - 1e-3);
  const S = C.poseAt(tt);
  robots.A.setPose(toSdk(S.L, cal)); robots.B.setPose(toSdk(S.R, cal));      // A = camera's left = the preview's L
  // the coach performs the dancer's part; mirrored (default) it moves like your reflection
  const mirror = mirrorBox.checked, H = mirror ? mirrorHuman(S.H) : S.H;
  coach.setPose(H);
  coach.root.position.set(H.x * LAYOUT.pxToM, 0, coachZ - 0.8 * H.depth);
  const me = ghost.update(S.H);
  ghostBody.root.visible = !!me && showGhost.checked;
  if (ghost.fresh) {
    ghost.fresh = false;
    if (scorer && clock.playing) scorer.push(ghost.lm && ghost.me
      ? featuresFromLandmarks(ghost.lm, ghost.size.w, ghost.size.h, t - CAMERA_LAG, ghost.me, ghost.centre) : nobody(t - CAMERA_LAG));
  }
  if (sim && scorer && clock.playing) {
    const ref = C.poseAt(Math.max(0, Math.min(C.DUR - 1e-3, t - 0.12))).H, f = featuresOf(sim === "still" ? { ...ref, aL: 0.12, eL: 0.1, aR: 0.12, eR: 0.1, x: 0, lean: 0, look: 0 } : ref, t - CAMERA_LAG, LAYOUT.pxToM);
    for (const k of ["aL", "uL", "aR", "uR"] as const) f[k] = (f[k] as number) + 0.12 * (Math.random() - 0.5);
    scorer.push(f);
  }
  const lag = xr.session ? 0 : CAMERA_LAG;                // the headset's poses are predicted for the display: no lag
  if (scorer) for (const j of scorer.judge(t - lag)) judged(j);
  if (me) { ghostBody.setPose(mirror ? mirrorHuman(me) : me); ghostBody.root.position.copy(coach.root.position).add(new THREE.Vector3(0, 0, 0.06)); }
  lane.draw(t, mirror, laneBox.checked && t > -8 * C.BEAT);
  // practice loop: at the end of the range, count in again and repeat
  if (clock.playing && t >= endOf(range.to) + 0.3) {
    if (scorer) { scorer.judge(endOf(range.to) + 1); passDone(); }
    if (range.loop) { clock.seek(lead()); newPass(); if (scorer) $("summary").hidden = false; clock.play(); } else { clock.pause(); clock.seek(endOf(range.to) - 1e-3); }
  }
  if (performance.now() - flashT > 700) $("rating").classList.remove("pop");
  kitchen.update(S.lt, S.H.x * LAYOUT.pxToM, tt);
  if (xr.session && xrFrame) xr.update(xrFrame, t, hud); else controls.update();
  renderer.render(scene, camera);
  if (compare) drawFlat(tt);
  // counts and cue, like the 2D preview
  const i = Math.min(C.N - 1, Math.floor(tt / C.PH)), count = Math.floor((tt - i * C.PH) / C.BEAT) + 1;
  const preRoll = t < startOf(range.from);
  $("count").textContent = preRoll ? String(Math.max(1, Math.ceil((startOf(range.from) - t) / C.BEAT))) : t >= C.DUR ? "" : String(count);
  const gold = !preRoll && goldAt(i, count);
  $("count").classList.toggle("gold", !!gold);
  $("gold").textContent = gold ? `★ GOLD MOVE: ${gold.name}` : "";
  const label = preRoll ? (range.loop || range.from > 1 ? `Get ready: ${range.from}. ${C.PHRASES[range.from - 1].you}` : "Get ready") : `${i + 1}. ${C.PHRASES[i].you}`;
  if (label !== lastLabel) { lastLabel = label; $("pname").textContent = label; $("cue").textContent = t < 0 ? "" : (phrases[i]?.dancer || C.PHRASES[i].Y); $("act").textContent = t < 0 ? "" : C.ACTS[C.PHRASES[i].act].name; }
  $("time").textContent = `${Math.max(0, tt).toFixed(1)} s / ${C.DUR} s${clock.rate !== 1 ? ` · ${Math.round(clock.rate * 100)}%` : ""}`;
  ($("play") as HTMLButtonElement).textContent = clock.playing ? "❚❚ Pause" : "▶ Play";
  const r = renderer.info.render; $("perf").textContent = `${r.triangles.toLocaleString()} triangles · ${r.calls} draw calls · ${clock.source}`;
  Object.assign(hud, { count: $("count").textContent, gold: $("gold").textContent, label: $("pname").textContent, cue: $("cue").textContent,
    act: $("act").textContent, time: $("time").textContent, scoring: !!scorer, points: scorer?.points ?? 0, combo: scorer?.combo ?? 0,
    stars: scorer?.stars ?? 0, fraction: scorer?.fraction ?? 0 });
}
renderer.setAnimationLoop(frame);              // (not requestAnimationFrame: the headset drives the loop in VR/AR)
$("loading").remove();
Object.assign(window, { __xr: { clock, robots, coach, scene, world, renderer, camera, controls, C, cal, range, MOVES, XR_MOVES, xr, hud, coachRef: coachReference(poseH, LAYOUT.pxToM), get scorer() { return scorer; } } });

// Demo/test hook, only with ?sim: &from=14&to=15 picks the range and &autoplay=1 starts it without a click
// (needs a browser that allows autoplay, e.g. headless Chrome with --autoplay-policy=no-user-gesture-required).
if (sim) {
  if (params.has("from")) selFrom.value = params.get("from")!;
  if (params.has("to")) selTo.value = params.get("to")!;
  if (params.has("from") || params.has("to")) applyRange();
  if (params.get("autoplay") === "1") ready.then(() => $("play").click());
}
