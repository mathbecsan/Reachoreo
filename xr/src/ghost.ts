// Your ghost: the webcam (laptop camera) + MediaPipe Pose, the same vendored model the 2D rehearsal page uses,
// turned into the coach's pose model so it can be drawn as a see-through figure over the coach.
// Arms, head turn, head tilt and lean are tracked; legs follow the coach (the webcam frames your upper body).
import type { HumanPose } from "/static/encendido-stage.mjs";

type Landmark = { x: number; y: number; visibility?: number };
export interface Mine { aL: number; eL: number; aR: number; eR: number; look: number; headDown: number; tilt: number; sw: number; neck: number; seen: Record<string, boolean> }

export class Ghost {
  private video = document.createElement("video");
  private landmarker: { detectForVideo(v: HTMLVideoElement, t: number): { landmarks?: Landmark[][] } } | null = null;
  private R: { myPose(l: Landmark[], w: number, h: number): Mine; calibrate(me: Mine): void } | null = null;
  private lastT = -1;
  me: Mine | null = null;
  lm: Landmark[] | null = null;           // the latest landmarks (for scoring)
  fresh = false;                          // a new camera frame was tracked since the last update()
  centre: { x: number; sw: number } | null = null;   // where you stand and how wide your shoulders are (Calibrate)
  on = false;
  get size() { return { w: this.video.videoWidth, h: this.video.videoHeight }; }

  /** Stand where you'll dance, arms relaxed: that spot becomes your centre mark, and your neck sets "head down". */
  calibrate(): boolean {
    if (!this.lm || !this.me || !this.R) return false;
    const W = this.video.videoWidth;
    this.centre = { x: (this.lm[11].x + this.lm[12].x) / 2 * W, sw: this.me.sw };
    this.R.calibrate(this.me);
    return true;
  }

  async start(): Promise<string> {
    const stream = await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false });
    this.video.srcObject = stream; this.video.muted = true; this.video.playsInline = true; await this.video.play();
    this.R = await import(/* @vite-ignore */ "/static/rehearsal.mjs");
    const { PoseLandmarker, FilesetResolver } = await import(/* @vite-ignore */ "/static/vendor/mediapipe/vision_bundle.mjs");
    const files = await FilesetResolver.forVisionTasks("/static/vendor/mediapipe/wasm");
    const opts = (d: string) => ({ baseOptions: { modelAssetPath: "/models/pose_landmarker_full.task", delegate: d }, runningMode: "VIDEO", numPoses: 1 });
    try { this.landmarker = await PoseLandmarker.createFromOptions(files, opts("GPU")); }
    catch { this.landmarker = await PoseLandmarker.createFromOptions(files, opts("CPU")); }
    this.on = true;
    return stream.getVideoTracks()[0].label || "camera";
  }
  stop() { (this.video.srcObject as MediaStream | null)?.getTracks().forEach(t => t.stop()); this.on = false; this.me = null; }

  /** Call every frame. Returns your pose in the coach's model (camera's view), or null if you're not in frame. */
  update(base: HumanPose): HumanPose | null {
    if (!this.on || !this.landmarker || !this.R || this.video.readyState < 2) return null;
    if (this.video.currentTime !== this.lastT) {
      this.lastT = this.video.currentTime;
      const lm = this.landmarker.detectForVideo(this.video, performance.now()).landmarks?.[0];
      this.me = lm ? this.R.myPose(lm, this.video.videoWidth, this.video.videoHeight) : null;
      this.lm = lm || null; this.fresh = true;
    }
    const m = this.me;
    if (!m) return null;
    return { ...base, aL: m.aL, eL: m.seen.eL ? m.eL : base.eL, aR: m.aR, eR: m.seen.eR ? m.eR : base.eR,
             look: m.look, headDown: m.headDown, tilt: m.tilt, hood: 0 };
  }
}
