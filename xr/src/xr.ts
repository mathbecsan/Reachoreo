// VR and AR on the Quest 3 (WebXR in the Meta Quest Browser, no app install).
//
// AR (passthrough) is the default, for the kitchen: you see the real room; the virtual counter's robots sit on the
// real ones once you've placed them (point at, or touch, each real Reachy's base and pinch). The placement is kept
// with WebXR anchors, persistent on the Quest, so next time it comes back by itself.
// VR (the full virtual kitchen) is only for a cleared space with the Guardian boundary set; the boundary is checked.
// Either way a safety check comes before every run, and a pause gesture works at any time: pinch (or pull the
// trigger) and hold for half a second, or squeeze the grip. Taking the headset off or opening the system menu pauses.
//
// Scoring uses the headset and both hands (xrscore.ts). A T-pose calibration sets your origin, facing and arm span.
// The heaviest stretch (phrases 13 to 18) is timed in the headset: the frame rate is shown in the menu and logged.
import * as THREE from "three";
import type * as Stage from "/static/encendido-stage.mjs";
import type { ShowClock } from "./clock";
import type { Kitchen } from "./kitchen";
import { LAYOUT } from "./layout";
import { Lane } from "./lane";
import { Panel } from "./panel";
import type { Reachy } from "./robot";
import { xrFeatures, yawOf, type XrCalibration, type XrFeatures } from "./xrscore";
import type { V3 } from "./body";

/** What the page shows, so the headset can show the same (main.ts fills it every frame). */
export interface Hud {
  count: string; gold: string; label: string; cue: string; act: string; time: string;
  flash: { text: string; color: string; at: number }; scoring: boolean; points: number; combo: number; stars: number; fraction: number;
  summary: string;
}
/** What the headset can do to the show (main.ts). */
export interface Host {
  renderer: THREE.WebGLRenderer; scene: THREE.Scene; world: THREE.Group; kitchen: Kitchen;
  robots: { A: Reachy; B: Reachy }; clock: ShowClock; C: typeof Stage;
  range: { from: number; to: number; loop: boolean };
  play(): Promise<void>;              // start or resume (from the range's lead-in if outside the range)
  again(): Promise<void>;             // the range from its lead-in
  pause(): void; setRange(from: number, to: number, loop: boolean): void;
  mirror: boolean; setMirror(on: boolean): void; setSpeed(r: number): Promise<void>;
  push(f: XrFeatures): void;          // a headset sample for the scorer (if one is running)
  setCoachZ(z: number): void;         // how far in front of the counter the coach dances (world metres)
  modeChanged(mode: "vr" | "ar" | null): void;
}

type Stage_ = "placing" | "warning" | "menu" | "calibrating" | "running";
const HOLD_MS = 500;                       // pinch / trigger held this long = pause
const CLEAR_M = 1.0;                       // free floor you need around you in VR
const AUDIENCE: V3 = [0, 0, LAYOUT.dancer.z + 3];   // where you stand: 3 m in front of the coach, facing it
const HEAVY = { from: 12 * 4, to: 18 * 4 };          // phrases 13 to 18, show seconds
const ANCHOR_KEY = "reachoreo.arAnchors";

interface Input {
  src: XRInputSource; down: number | null; held: boolean;
  ray: THREE.Line; dot: THREE.Mesh; hitTest: XRHitTestSource | null; hitPose: THREE.Vector3 | null;
  joints?: THREE.InstancedMesh;            // your hand, drawn in VR (dots on the 25 joints, built in code)
}

export class XrMode {
  session: XRSession | null = null;
  mode: "vr" | "ar" | null = null;
  calib: XrCalibration | null = null;
  private stage: Stage_ = "menu";
  private host: Host;
  private hud = new Panel(2.2, 0.72);
  private laneP = new Panel(1.6, 0.27, 480);
  private dialog = new Panel(1.0, 1.05);
  private lane: Lane;
  private ring: THREE.Mesh;                       // the "stand here" mark
  private reticle: THREE.Mesh;
  private boundary: THREE.LineLoop | null = null;
  private boundsPoly: V3[] | null = null;
  private inputs = new Map<XRInputSource, Input>();
  private raycaster = new THREE.Raycaster();
  private placed: { A: V3; B: V3 } | null = null;
  private placing: V3[] = [];
  private anchors: XRAnchor[] = [];
  private pendingAnchors: V3[] | null = null;
  private needCenter = false;
  private calibUntil = 0; private calibSamples: { head: V3; r: V3; l: V3; fwd: V3 }[] = [];
  private hudKey = ""; private laneT = 0; private dialogKey = "";
  private note = "";                              // one line of news in the menu
  private perf = { frames: [] as number[], tris: 0, calls: 0, last: 0, result: "" };
  private head: V3 = [0, 1.6, 0]; private fwd: V3 = [0, 0, -1];
  private showRobots = true;
  private fromTop = false;
  private started = false;                      // the clock has run since this run's start
  private pendingBounds: [XRBoundedReferenceSpace, DOMPointReadOnly[]] | null = null;
  private speed = 1;

  constructor(host: Host) {
    this.host = host;
    const r = host.renderer;
    r.xr.enabled = true; r.xr.setReferenceSpaceType("local-floor");
    this.lane = new Lane(this.laneP.canvas, host.C);
    // stage-fixed panels (they move with the world): the HUD above the coach, the lane low in front of you
    this.hud.mesh.position.set(0, 2.38, LAYOUT.dancer.z - 0.2);
    this.laneP.mesh.position.set(0, 0.78, AUDIENCE[2] - 1.15); this.laneP.mesh.rotation.x = -0.55;
    this.ring = new THREE.Mesh(new THREE.RingGeometry(0.3, 0.36, 48), new THREE.MeshBasicMaterial({ color: 0x7fe3ff, transparent: true, opacity: 0.7 }));
    this.ring.rotation.x = -Math.PI / 2; this.ring.position.set(AUDIENCE[0], 0.004, AUDIENCE[2]);
    for (const m of [this.hud.mesh, this.laneP.mesh, this.ring]) { m.visible = false; host.world.add(m); }
    this.dialog.mesh.visible = false; host.scene.add(this.dialog.mesh);
    this.reticle = new THREE.Mesh(new THREE.RingGeometry(0.03, 0.045, 32), new THREE.MeshBasicMaterial({ color: 0xf2b544 }));
    this.reticle.rotation.x = -Math.PI / 2; this.reticle.visible = false; host.scene.add(this.reticle);
  }

  static async supported(mode: "immersive-vr" | "immersive-ar") {
    try { return !!navigator.xr && await navigator.xr.isSessionSupported(mode); } catch { return false; }
  }

  // ---------- sessions ----------
  async enter(mode: "vr" | "ar") {
    if (this.session) return;
    await this.host.clock.ctx.resume();                   // the button press unlocks audio for the whole session
    this.host.pause();
    const optionalFeatures = ["local-floor", "hand-tracking", ...(mode === "ar" ? ["hit-test", "anchors", "plane-detection"] : ["bounded-floor"])];
    const session = await navigator.xr!.requestSession(mode === "ar" ? "immersive-ar" : "immersive-vr", { optionalFeatures });
    this.session = session; this.mode = mode;
    const r = this.host.renderer;
    r.xr.setFoveation(0.7);
    await r.xr.setSession(session);
    // the Quest 3 runs 72, 90 or 120 Hz: ask for 90 (the brief's target), never below 72
    const rates = session.supportedFrameRates;
    if (rates && session.updateTargetFrameRate) { const want = [...rates].includes(90) ? 90 : Math.max(...rates); session.updateTargetFrameRate(want).catch(() => {}); }
    session.addEventListener("end", () => this.exited());
    session.addEventListener("selectstart", e => this.selectStart(e as XRInputSourceEvent));
    session.addEventListener("selectend", e => this.selectEnd(e as XRInputSourceEvent));
    session.addEventListener("squeezestart", () => this.pauseGesture());
    session.addEventListener("visibilitychange", () => { if (session.visibilityState !== "visible") this.pauseGesture(); });
    session.addEventListener("inputsourceschange", e => this.inputsChanged(e as XRInputSourcesChangeEvent));
    this.host.kitchen.setMode(mode); this.host.scene.background = mode === "ar" ? null : new THREE.Color("#0d0c1c");
    for (const m of [this.hud.mesh, this.laneP.mesh, this.ring]) m.visible = true;
    this.host.modeChanged(mode);
    this.placed = null; this.placing = []; this.anchors = [];
    if (mode === "vr") { this.resetRobots(); this.needCenter = true; this.setStage("menu"); this.note = "Welcome to the kitchen. Stand where you'll dance."; }
    else { this.setStage("placing"); this.restoreAnchors(); }
    if (mode === "vr") this.readBoundary();
  }
  exit() { this.session?.end(); }
  private exited() {
    for (const inp of this.inputs.values()) { inp.ray.removeFromParent(); inp.dot.removeFromParent(); inp.joints?.removeFromParent(); inp.hitTest?.cancel(); }
    this.inputs.clear();
    this.boundary?.removeFromParent(); this.boundary = null; this.boundsPoly = null;
    this.session = null; this.mode = null;
    for (const m of [this.hud.mesh, this.laneP.mesh, this.ring, this.dialog.mesh, this.reticle]) m.visible = false;
    this.host.world.position.set(0, 0, 0); this.host.world.rotation.set(0, 0, 0); this.resetRobots();
    this.host.kitchen.setMode("desktop"); this.host.scene.background = new THREE.Color("#0d0c1c");
    this.host.pause(); this.host.modeChanged(null);
  }

  // ---------- where the virtual kitchen sits ----------
  private resetRobots() {
    for (const [k, r] of Object.entries(this.host.robots)) { r.root.position.set(LAYOUT.robots[k as "A" | "B"].x, LAYOUT.counter.height, LAYOUT.robots.z); r.root.visible = true; }
  }
  /** VR: put the stage so that you stand on the audience mark, facing the coach. */
  private centreOnMe() {
    const yaw = yawOf(this.fwd), w = this.host.world;
    w.rotation.set(0, yaw, 0);
    const a = new THREE.Vector3(...AUDIENCE).applyEuler(w.rotation);
    w.position.set(this.head[0] - a.x, 0, this.head[2] - a.z);
  }
  /** AR: from the two real robots' bases (Reachy 1 on your left as you face the counter, Reachy 2 on your right). */
  private placeFrom(A: V3, B: V3) {
    const dx = B[0] - A[0], dz = B[2] - A[2], d = Math.hypot(dx, dz);
    if (d < 0.3) return false;
    const yaw = Math.atan2(-dz / d, dx / d), w = this.host.world;
    w.rotation.set(0, yaw, 0);
    const z = new THREE.Vector3(0, 0, 1).applyEuler(w.rotation), mid = new THREE.Vector3((A[0] + B[0]) / 2, 0, (A[2] + B[2]) / 2);
    w.position.copy(mid).addScaledVector(z, -LAYOUT.robots.z);          // the world origin: under the counter's front edge
    const top = (A[1] + B[1]) / 2;
    this.host.robots.A.root.position.set(-d / 2, top, LAYOUT.robots.z); this.host.robots.B.root.position.set(d / 2, top, LAYOUT.robots.z);
    this.placed = { A, B };
    return true;
  }
  private async restoreAnchors() {
    const s = this.session as XRSession & { restorePersistentAnchor?(uuid: string): Promise<XRAnchor> };
    let ids: string[] = [];
    try { ids = JSON.parse(localStorage.getItem(ANCHOR_KEY) || "[]"); } catch { /* none */ }
    if (ids.length !== 2 || !s.restorePersistentAnchor) return;
    try {
      this.anchors = await Promise.all(ids.map(id => s.restorePersistentAnchor!(id)));
      this.note = "Your counter placement is back (from last time). Re-place it in the menu if the robots are off.";
      this.setStage("menu");
    } catch { this.anchors = []; }
  }
  private async saveAnchors(frame: XRFrame, pts: V3[], ref: XRReferenceSpace) {
    if (!frame.createAnchor) { this.note = "Placed. (This browser can't keep anchors: you'll place it again next time.)"; return; }
    const s = this.session as XRSession & { deletePersistentAnchor?(uuid: string): Promise<void> };
    try {
      const old: string[] = JSON.parse(localStorage.getItem(ANCHOR_KEY) || "[]");
      for (const id of old) s.deletePersistentAnchor?.(id).catch(() => {});
    } catch { /* nothing stored */ }
    try {
      this.anchors = await Promise.all(pts.map(p => frame.createAnchor!(new XRRigidTransform({ x: p[0], y: p[1], z: p[2] }), ref)!));
      const ids = await Promise.all(this.anchors.map(a => (a as XRAnchor & { requestPersistentHandle?(): Promise<string> }).requestPersistentHandle?.()));
      if (ids.every(Boolean)) localStorage.setItem(ANCHOR_KEY, JSON.stringify(ids));
      this.note = "Placed and anchored: the Quest keeps it, so next time it comes back by itself.";
    } catch { this.note = "Placed (anchors unavailable: you'll place it again next time)."; }
  }

  // ---------- your Guardian boundary (VR) ----------
  private async readBoundary() {
    try {
      const bounded = await this.session!.requestReferenceSpace("bounded-floor") as XRBoundedReferenceSpace;
      const pts = bounded.boundsGeometry;
      if (!pts?.length) return;
      // the bounds are in bounded-floor space: carry them into ours with the space-to-space pose on the next frame
      this.pendingBounds = [bounded, [...pts]];
    } catch { /* no boundary available: the warning says so */ }
  }
  private clearance(): number | null {
    const P = this.boundsPoly; if (!P) return null;
    const x = this.head[0], z = this.head[2];
    let inside = false, d = Infinity;
    for (let i = 0, j = P.length - 1; i < P.length; j = i++) {
      const [ax, , az] = P[i], [bx, , bz] = P[j];
      if ((az > z) !== (bz > z) && x < (bx - ax) * (z - az) / (bz - az) + ax) inside = !inside;
      const ex = bx - ax, ez = bz - az, t = Math.max(0, Math.min(1, ((x - ax) * ex + (z - az) * ez) / (ex * ex + ez * ez || 1)));
      d = Math.min(d, Math.hypot(x - ax - t * ex, z - az - t * ez));
    }
    return inside ? d : 0;
  }

  // ---------- input: rays, clicks, the pause gesture ----------
  private inputsChanged(e: XRInputSourcesChangeEvent) {
    for (const src of e.removed) { const i = this.inputs.get(src); i?.ray.removeFromParent(); i?.dot.removeFromParent(); i?.joints?.removeFromParent(); i?.hitTest?.cancel(); this.inputs.delete(src); }
    for (const src of e.added) {
      if (src.targetRayMode !== "tracked-pointer") continue;
      const ray = new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), new THREE.Vector3(0, 0, -1)]),
        new THREE.LineBasicMaterial({ color: 0x7fe3ff, transparent: true, opacity: 0.8 }));
      const dot = new THREE.Mesh(new THREE.SphereGeometry(0.008, 12, 8), new THREE.MeshBasicMaterial({ color: 0xffffff }));
      ray.visible = dot.visible = false; this.host.scene.add(ray, dot);
      const inp: Input = { src, down: null, held: false, ray, dot, hitTest: null, hitPose: null };
      if (src.hand && this.mode === "vr") {
        inp.joints = new THREE.InstancedMesh(new THREE.SphereGeometry(1, 10, 8), new THREE.MeshStandardMaterial({ color: 0xf27aa8, roughness: 0.6 }), 25);
        inp.joints.frustumCulled = false; this.host.scene.add(inp.joints);
      }
      if (this.mode === "ar") this.session!.requestHitTestSource?.({ space: src.targetRaySpace })?.then(h => { inp.hitTest = h; }).catch(() => {});
      this.inputs.set(src, inp);
    }
  }
  private selectStart(e: XRInputSourceEvent) { const i = this.inputs.get(e.inputSource); if (i) { i.down = performance.now(); i.held = false; } }
  private selectEnd(e: XRInputSourceEvent) {
    const i = this.inputs.get(e.inputSource); if (!i) return;
    const wasHeld = i.held; i.down = null; i.held = false;
    if (!wasHeld) this.clicks.push(i);         // handled in the next frame: an XRFrame is only valid inside its callback
  }
  /** Pause at once and bring up the menu (the brief's pause gesture). */
  pauseGesture() {
    if (this.stage === "running") { this.host.pause(); this.note = "Paused."; this.setStage("menu"); }
  }
  private rayFrom(i: Input, frame: XRFrame, ref: XRReferenceSpace) {
    const pose = frame.getPose(i.src.targetRaySpace, ref); if (!pose) return null;
    const m = new THREE.Matrix4().fromArray(pose.transform.matrix);
    const o = new THREE.Vector3().setFromMatrixPosition(m), d = new THREE.Vector3(0, 0, -1).transformDirection(m);
    return { o, d };
  }
  private clicks: Input[] = [];
  private click(i: Input, frame: XRFrame, ref: XRReferenceSpace) {
    const ray = this.rayFrom(i, frame, ref);
    if (ray && this.dialog.mesh.visible) {
      this.raycaster.set(ray.o, ray.d);
      const hit = this.raycaster.intersectObject(this.dialog.mesh)[0];
      if (hit?.uv) { const b = this.dialog.hit(hit.uv); if (b) { this.press(b.id); return; } }
    }
    if (this.stage === "placing") this.placePoint(i, frame, ref);
  }
  /** AR placement: the hit-test point you're pointing at, or (no hit test) where your hand or controller is. */
  private placePoint(i: Input, frame: XRFrame, ref: XRReferenceSpace) {
    let p: V3 | null = i.hitPose ? [i.hitPose.x, i.hitPose.y, i.hitPose.z] : null;
    if (!p) {
      const space = i.src.gripSpace ?? i.src.targetRaySpace, pose = frame.getPose(space, ref);
      if (pose) { const q = pose.transform.position; p = [q.x, q.y, q.z]; }
    }
    if (!p) return;
    this.placing.push(p); this.dialogKey = "";
    if (this.placing.length === 2) {
      const [A, B] = this.placing; this.placing = [];
      if (this.placeFrom(A, B)) { this.pendingAnchors = [A, B]; this.note = "Placed."; this.setStage("menu"); }
      else this.note = "Those two points were too close: Reachy 1, then Reachy 2.";
    }
  }

  // ---------- the menu ----------
  private setStage(s: Stage_) {
    this.stage = s; this.dialogKey = "";
    if (s !== "running") this.placeDialog();
    this.dialog.mesh.visible = s !== "running";
    this.reticle.visible = false;
  }
  /** Dialogs open in front of you, a little below eye level, facing you. */
  private placeDialog() {
    const f = new THREE.Vector3(this.fwd[0], 0, this.fwd[2]).normalize();
    this.dialog.mesh.position.set(this.head[0] + f.x * 0.85, this.head[1] - 0.18, this.head[2] + f.z * 0.85);
    this.dialog.mesh.lookAt(this.head[0], this.head[1] - 0.1, this.head[2]);
  }
  private async press(id: string) {
    const h = this.host, C = h.C;
    switch (id) {
      case "play": this.fromTop = false; this.setStage("warning"); break;
      case "again": this.fromTop = true; this.setStage("warning"); break;
      case "go":                                   // the safety check comes before every run, even a resume
        this.fitToMe();
        if (!this.calib) this.autoCalibrate();
        this.note = ""; this.started = false; this.setStage("running"); this.perf.frames = []; this.perf.tris = this.perf.calls = 0;
        await (this.fromTop ? h.again() : h.play()); break;
      case "back": this.setStage("menu"); break;
      case "exit": this.exit(); break;
      case "from-": h.setRange(Math.max(1, h.range.from - 1), h.range.to, h.range.loop); break;
      case "from+": h.setRange(Math.min(C.N, h.range.from + 1), Math.max(h.range.to, h.range.from + 1), h.range.loop); break;
      case "to-": h.setRange(Math.min(h.range.from, h.range.to - 1) || 1, Math.max(1, h.range.to - 1), h.range.loop); break;
      case "to+": h.setRange(h.range.from, Math.min(C.N, h.range.to + 1), h.range.loop); break;
      case "full": h.setRange(1, C.N, false); break;
      case "loop": h.setRange(h.range.from, h.range.to, !h.range.loop); break;
      case "speed": this.speed = this.speed === 1 ? 0.75 : this.speed === 0.75 ? 0.5 : 1; await h.setSpeed(this.speed); break;
      case "mirror": h.setMirror(!h.mirror); break;
      case "robots": this.showRobots = !this.showRobots; h.robots.A.root.visible = h.robots.B.root.visible = this.showRobots; break;
      case "calibrate": this.calibSamples = []; this.calibUntil = performance.now() + 3600; this.setStage("calibrating"); break;
      case "recenter": this.needCenter = true; this.note = "Centred: you're on the mark, facing the coach."; break;
      case "replace": this.placing = []; this.setStage("placing"); break;
      case "skipplace": this.resetRobots(); this.needCenter = true; this.placed = null; this.note = "Using the layout in front of you (not on your counter)."; this.setStage("menu"); break;
    }
    this.dialogKey = "";
  }
  /** Stand the coach ~3 m in front of you, between you and the counter (a real kitchen may be shorter than the
   *  4.2 m the layout wants), and the lane low in front of you. */
  private fitToMe() {
    const me = this.host.world.worldToLocal(new THREE.Vector3(...this.head));
    const z = THREE.MathUtils.clamp(me.z - 3, 0.6, LAYOUT.dancer.z);
    this.host.setCoachZ(z);
    this.hud.mesh.position.z = z - 0.2;
    this.laneP.mesh.position.set(me.x, 0.78, me.z - 1.15);
    this.ring.position.set(0, 0.004, z + 3);
  }
  private autoCalibrate() {
    // no T-pose yet: your head now is the origin, and your arm span is about your height
    this.calib = { origin: [...this.head], yaw: yawOf(this.fwd), span: Math.max(1.2, this.head[1] + 0.1) };
    this.note = "Scoring with an estimated arm span: Calibrate (T-pose) for better scores.";
  }

  private drawDialog() {
    const P = this.dialog, h = this.host, C = h.C, ar = this.mode === "ar";
    const clr = this.clearance();
    const key = [this.stage, this.note, h.range.from, h.range.to, h.range.loop, this.speed, h.mirror, this.showRobots, this.placing.length, P.hover,
      Math.ceil((this.calibUntil - performance.now()) / 1000), clr == null ? "" : clr.toFixed(1), this.perf.result, this.calib?.span].join("|");
    if (key === this.dialogKey) return;
    this.dialogKey = key;
    P.draw((g, W, H) => {
      P.card();
      const pad = 36, bw = (W - pad * 2 - 24) / 3, bh = 70, row = (n: number) => 176 + n * (bh + 16);
      const col = (n: number) => pad + n * (bw + 12);
      if (this.stage === "placing") {
        P.text("Place the robots on your counter", pad, 52, 36, "#ede9ff", 800);
        const step = this.placing.length === 0 ? "1. Point at (or touch) the counter at Reachy 1's base, on your LEFT, and pinch or pull the trigger."
          : "2. Now Reachy 2's base, on your RIGHT.";
        let y = P.para(step, pad, 120, W - pad * 2, 30);
        y = P.para("The virtual robots will stand exactly there, at that height. Stay where you are while you do it.", pad, y + 12, W - pad * 2, 24, "#a9a3cc");
        if (this.note) P.para(this.note, pad, y + 12, W - pad * 2, 24, "#f2b544");
        P.button({ id: "skipplace", x: pad, y: H - bh - 30, w: W - pad * 2, h: bh, label: "Skip: use the layout in front of me" });
        return;
      }
      if (this.stage === "warning") {
        P.text("⚠ Before you dance", pad, 52, 40, "#f2b544", 800);
        const lines = ar
          ? ["Passthrough is on: you can see your kitchen.", "Clear the floor around you, and keep at least 1 m from the counter and both robots.",
            "Stand on the cyan ring (or anywhere with clear floor), facing the coach."]
          : ["Full VR: you can't see the room.", "Only in a cleared space, with your Guardian boundary set.",
            clr == null ? "⚠ No boundary found: set your Guardian (Quest Settings → Boundary) before you dance."
              : clr >= CLEAR_M ? `Boundary ✓  ${clr.toFixed(1)} m of clear floor around you.` : `⚠ Only ${clr.toFixed(1)} m to your boundary: move toward the middle of your play area.`];
        let y = 112;
        for (const l of lines) y = P.para(l, pad, y, W - pad * 2, 27, l.startsWith("⚠") ? "#ff9f6b" : "#ede9ff") + 6;
        P.para("To pause any time: pinch (or pull the trigger) and hold, or squeeze the grip.", pad, y + 6, W - pad * 2, 24, "#7fe3ff");
        P.button({ id: "go", x: pad, y: H - bh - 30, w: (W - pad * 2) * 0.62, h: bh, label: "I'm clear: start", primary: true });
        P.button({ id: "back", x: pad + (W - pad * 2) * 0.62 + 16, y: H - bh - 30, w: (W - pad * 2) * 0.38 - 16, h: bh, label: "Back" });
        return;
      }
      if (this.stage === "calibrating") {
        const n = Math.ceil((this.calibUntil - performance.now()) / 1000) - 1;
        P.text("Calibrate: T-pose", pad, 52, 40, "#ede9ff", 800);
        P.para("Stand on your spot facing the coach, arms straight out to the sides, palms down.", pad, 130, W - pad * 2, 30);
        P.text(n > 0 ? String(n) : "Hold still…", W / 2, H * 0.66, 120, "#f2b544", 900, "center");
        return;
      }
      // the menu
      const r = h.range, ph = (n: number) => `${n}. ${C.PHRASES[n - 1].you}`;
      P.text(this.note === "Paused." ? "Paused" : "Menu", pad, 52, 40, "#ede9ff", 800);
      P.text(ar ? "AR · passthrough" : "VR", W - pad, 52, 26, "#a9a3cc", 600, "right");
      if (this.note) P.para(this.note, pad, 102, W - pad * 2, 23, "#f2b544");
      P.button({ id: "play", x: col(0), y: row(0), w: bw, h: bh, label: "▶ Play", primary: true });
      P.button({ id: "again", x: col(1), y: row(0), w: bw, h: bh, label: "↺ From the top" });
      P.button({ id: "exit", x: col(2), y: row(0), w: bw, h: bh, label: "Exit " + (ar ? "AR" : "VR") });
      const small = 84;
      for (const [k, label, n] of [["from", "from", r.from], ["to", "to", r.to]] as const) {
        const y = row(k === "from" ? 1 : 2);
        P.button({ id: `${k}-`, x: pad, y, w: small, h: bh, label: "◀" });
        P.text(`${label}  ${ph(n)}`, pad + small + 18, y + bh / 2, 28);
        P.button({ id: `${k}+`, x: W - pad - small, y, w: small, h: bh, label: "▶" });
      }
      P.button({ id: "loop", x: col(0), y: row(3), w: bw, h: bh, label: `loop ${r.loop ? "on" : "off"}`, on: r.loop });
      P.button({ id: "speed", x: col(1), y: row(3), w: bw, h: bh, label: `speed ${Math.round(this.speed * 100)}%`, on: this.speed !== 1 });
      P.button({ id: "mirror", x: col(2), y: row(3), w: bw, h: bh, label: `mirror ${h.mirror ? "on" : "off"}`, on: h.mirror });
      P.button({ id: "calibrate", x: col(0), y: row(4), w: bw, h: bh, label: "Calibrate", on: !!this.calib });
      P.button(ar ? { id: "replace", x: col(1), y: row(4), w: bw, h: bh, label: "Re-place" } : { id: "recenter", x: col(1), y: row(4), w: bw, h: bh, label: "Recentre" });
      P.button(ar ? { id: "robots", x: col(2), y: row(4), w: bw, h: bh, label: `robots ${this.showRobots ? "on" : "off"}`, on: this.showRobots }
        : { id: "full", x: col(2), y: row(4), w: bw, h: bh, label: "Full song" });
      const foot = [this.calib ? `arm span ${this.calib.span.toFixed(2)} m` : "not calibrated", this.perf.result].filter(Boolean).join(" · ");
      P.text(foot, pad, H - 26, 22, "#a9a3cc", 500);
    });
  }

  private drawHud(hud: Hud) {
    const age = performance.now() - hud.flash.at, flashing = age < 700;
    const key = [hud.count, hud.gold, hud.label, hud.cue, hud.act, hud.scoring, hud.points, hud.combo, hud.stars, flashing ? hud.flash.text + hud.flash.at : ""].join("|");
    if (key === this.hudKey) return;
    this.hudKey = key;
    this.hud.draw((g, W, H) => {
      const P = this.hud;
      g.fillStyle = "#0b0a18b0"; g.beginPath(); g.roundRect(0, 0, W, H, 30); g.fill();
      P.text(hud.count, 40, H * 0.36, 190, hud.gold ? "#f2b544" : "#ede9ff", 900);
      P.text(hud.label, W - 40, 62, 62, "#ede9ff", 800, "right");
      P.text(hud.act, W - 40, 124, 36, "#a9a3cc", 600, "right");
      if (hud.gold) P.text(hud.gold, W / 2, 62, 46, "#f2b544", 800, "center");
      P.para(hud.cue, 40, H - 96, W - 80, 44, "#f2b544");
      if (hud.scoring) {
        P.text(`${"★".repeat(hud.stars)}${"☆".repeat(5 - hud.stars)}  ${Math.round(hud.points).toLocaleString()}`, W - 40, 192, 56, "#f2b544", 800, "right");
        if (hud.combo >= 3) P.text(`combo ×${hud.combo}`, W - 40, 252, 40, "#7fe3ff", 800, "right");
      }
      if (flashing) P.text(hud.flash.text, W / 2, H * 0.56, 96, hud.flash.color, 900, "center");
    });
  }

  // ---------- every XR frame ----------
  update(frame: XRFrame, t: number, hud: Hud) {
    const ref = this.host.renderer.xr.getReferenceSpace(); if (!ref || !this.session) return;
    const vp = frame.getViewerPose(ref);
    if (vp) {
      const p = vp.transform.position, m = new THREE.Matrix4().fromArray(vp.transform.matrix), f = new THREE.Vector3(0, 0, -1).transformDirection(m);
      this.head = [p.x, p.y, p.z];
      if (Math.hypot(f.x, f.z) > 0.2) this.fwd = [f.x, 0, f.z];
    }
    if (this.needCenter && vp) { this.needCenter = false; this.centreOnMe(); if (this.stage !== "running") this.placeDialog(); }
    // the Guardian boundary, carried into our space and drawn on the floor
    const pb = this.pendingBounds;
    if (pb) {
      const pose = frame.getPose(pb[0], ref);
      if (pose) {
        const m = new THREE.Matrix4().fromArray(pose.transform.matrix);
        this.boundsPoly = pb[1].map(q => { const v = new THREE.Vector3(q.x, 0, q.z).applyMatrix4(m); return [v.x, 0.01, v.z] as V3; });
        this.boundary = new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(this.boundsPoly.map(q => new THREE.Vector3(...q))),
          new THREE.LineBasicMaterial({ color: 0xf2b544 }));
        this.host.scene.add(this.boundary);
        this.pendingBounds = null;
      }
    }
    // anchors: create the ones we just placed; follow the tracked ones (the Quest corrects drift)
    if (this.pendingAnchors) { const pts = this.pendingAnchors; this.pendingAnchors = null; this.saveAnchors(frame, pts, ref); }
    if (this.anchors.length === 2 && frame.trackedAnchors) {
      const pts = this.anchors.map(a => frame.trackedAnchors!.has(a) ? frame.getPose(a.anchorSpace, ref)?.transform.position : undefined);
      if (pts[0] && pts[1]) {
        const A: V3 = [pts[0].x, pts[0].y, pts[0].z], B: V3 = [pts[1].x, pts[1].y, pts[1].z];
        if (!this.placed || Math.hypot(A[0] - this.placed.A[0], A[2] - this.placed.A[2]) > 0.005) this.placeFrom(A, B);
      }
    }
    for (const i of this.clicks.splice(0)) this.click(i, frame, ref);
    // hands and controllers: rays over dialogs, the AR reticle, hold-to-pause, your hand joints, and scoring samples
    let right: V3 | null = null, left: V3 | null = null, hover: string | null = null;
    const now = performance.now();
    for (const i of this.inputs.values()) {
      if (i.down != null && !i.held && now - i.down > HOLD_MS) { i.held = true; this.pauseGesture(); }
      const ray = this.rayFrom(i, frame, ref);
      let len = 2;
      if (ray && this.dialog.mesh.visible) {
        this.raycaster.set(ray.o, ray.d);
        const hit = this.raycaster.intersectObject(this.dialog.mesh)[0];
        if (hit) { len = hit.distance; if (hit.uv) hover = this.dialog.hit(hit.uv)?.id ?? hover; }
      }
      i.hitPose = null;
      if (this.stage === "placing" && i.hitTest) {
        const r = frame.getHitTestResults(i.hitTest)[0]?.getPose(ref);
        if (r) { i.hitPose = new THREE.Vector3(r.transform.position.x, r.transform.position.y, r.transform.position.z); this.reticle.position.copy(i.hitPose); this.reticle.visible = true; }
      }
      const showRay = !!ray && this.stage !== "running";
      i.ray.visible = i.dot.visible = showRay;
      if (ray && showRay) {
        i.ray.position.copy(ray.o); i.ray.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, -1), ray.d); i.ray.scale.set(1, 1, len);
        i.dot.position.copy(ray.o).addScaledVector(ray.d, len);
      }
      // where your wrist is: the hand's wrist joint, or the controller's grip
      let wrist: V3 | null = null;
      if (i.src.hand && frame.getJointPose) {
        const jp = frame.getJointPose(i.src.hand.get("wrist")!, ref);
        if (jp) wrist = [jp.transform.position.x, jp.transform.position.y, jp.transform.position.z];
        if (i.joints) {
          const mm = new THREE.Matrix4(); let n = 0;
          for (const space of i.src.hand.values()) {
            const j = frame.getJointPose(space, ref);
            if (j) { const pp = j.transform.position, r = Math.max(0.006, j.radius ?? 0.008); mm.makeScale(r, r, r).setPosition(pp.x, pp.y, pp.z); i.joints.setMatrixAt(n++, mm); }
          }
          i.joints.count = n; i.joints.instanceMatrix.needsUpdate = true;
        }
      } else if (i.src.gripSpace) {
        const gp = frame.getPose(i.src.gripSpace, ref);
        if (gp) wrist = [gp.transform.position.x, gp.transform.position.y, gp.transform.position.z];
      }
      if (i.src.handedness === "right") right = wrist; else if (i.src.handedness === "left") left = wrist;
    }
    if (hover !== this.dialog.hover) { this.dialog.hover = hover; }
    // the T-pose: sample for half a second at the end of the countdown
    if (this.stage === "calibrating") {
      if (now > this.calibUntil - 800 && right && left) this.calibSamples.push({ head: [...this.head], r: right, l: left, fwd: [...this.fwd] });
      if (now > this.calibUntil) {
        const S = this.calibSamples;
        if (S.length >= 3) {
          const avg = (f: (s: typeof S[0]) => V3): V3 => [0, 1, 2].map(k => S.reduce((a, s) => a + f(s)[k], 0) / S.length) as V3;
          const r = avg(s => s.r), l = avg(s => s.l), span = Math.hypot(r[0] - l[0], r[1] - l[1], r[2] - l[2]);
          this.calib = { origin: avg(s => s.head), yaw: yawOf(avg(s => s.fwd)), span: Math.max(1, span) };
          this.note = `Calibrated: arm span ${span.toFixed(2)} m. Scoring is relative to this spot and facing.`;
        } else this.note = "Couldn't see both hands: hold both controllers (or show both hands) and try again.";
        this.setStage("menu");
      }
    }
    // scoring sample
    if (this.calib && this.host.clock.playing && this.stage === "running")
      this.host.push(xrFeatures(t, this.head, right, left, this.calib));
    // the run ended by itself (end of the range): show the menu with the result
    if (this.stage === "running" && this.host.clock.playing) this.started = true;
    if (this.stage === "running" && this.started && !this.host.clock.playing) { this.note = hud.summary || "Done."; this.setStage("menu"); }
    // frame timing in the heaviest stretch (phrases 13 to 18) at full speed
    this.meter(t, now);
    // panels
    this.drawHud(hud);
    if (now - this.laneT > 33) { this.laneT = now; this.lane.draw(t, this.host.mirror, t > -8 * this.host.C.BEAT); this.laneP.tex.needsUpdate = true; }
    if (this.dialog.mesh.visible) this.drawDialog();
  }

  private meter(t: number, now: number) {
    const p = this.perf, inHeavy = this.host.clock.playing && this.host.clock.rate === 1 && t >= HEAVY.from && t < HEAVY.to;
    if (inHeavy) {
      if (p.last) p.frames.push(now - p.last);
      const info = this.host.renderer.info.render; p.tris = Math.max(p.tris, info.triangles); p.calls = Math.max(p.calls, info.calls);
    }
    p.last = now;
    if (!inHeavy && p.frames.length > 120) {
      const f = [...p.frames].sort((a, b) => a - b), avg = 1000 / (f.reduce((a, b) => a + b, 0) / f.length);
      const low = 1000 / f[Math.floor(f.length * 0.99)], slow = f.filter(d => d > 1000 / 72 * 1.15).length / f.length;
      const rate = this.session?.frameRate;
      p.result = `phrases 13–18: ${avg.toFixed(0)} fps (1% low ${low.toFixed(0)})${rate ? ` at ${rate} Hz` : ""}`;
      const rec = { at: new Date().toISOString(), mode: this.mode, device: navigator.userAgent, frames: f.length, fps_avg: +avg.toFixed(1), fps_1pct_low: +low.toFixed(1),
        share_slower_than_72: +slow.toFixed(4), display_hz: rate ?? null, max_triangles_both_eyes: p.tris, max_draw_calls_both_eyes: p.calls };
      fetch("/api/xr/perf", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(rec) }).catch(() => {});
      try { localStorage.setItem("reachoreo.xrPerf", JSON.stringify(rec)); } catch { /* private mode */ }
      p.frames = [];
    }
  }
}
