// The pictogram lane, Just Dance style: upcoming moves slide in from the right and reach the "now" line on their
// count. Each pictogram is drawn from the coach's own pose at that count (the preview's drawHuman, in the coach's
// colour), never drawn by hand or generated. A count that looks like the one before it isn't repeated.
import type * as Stage from "/static/encendido-stage.mjs";
import type { HumanPose } from "/static/encendido-stage.mjs";
import { mirrorHuman } from "./coach";

/** Gold moves (phrase, page count): highlighted in the lane and, from milestone 3, worth bonus points. */
export const GOLD: { phrase: number; count: number; name: string }[] = [
  { phrase: 8, count: 7, name: "peekaboo reveal" }, { phrase: 9, count: 2, name: "hood off" },
  { phrase: 12, count: 3, name: "V landing" }, { phrase: 15, count: 7, name: "electro halo" }, { phrase: 19, count: 5, name: "power pose" },
];
const isGold = (k: number) => GOLD.some(g => (g.phrase - 1) * 8 + g.count - 1 === k);
const AHEAD = 2.5;                 // beats of lane to the right of the now line

export class Lane {
  private cache = new Map<string, HTMLCanvasElement>();
  constructor(private canvas: HTMLCanvasElement, private C: typeof Stage) {}

  /** The pose a pictogram shows for count k (0-based from the downbeat): a quarter beat in, when the snap has landed. */
  private poseFor(k: number, mirror: boolean): HumanPose {
    const H = this.C.poseAt(Math.min(this.C.DUR - 1e-3, (k + 0.3) * this.C.BEAT)).H;
    return mirror ? mirrorHuman(H) : H;
  }
  private differs(a: HumanPose, b: HumanPose) {
    return Math.abs(a.aL - b.aL) + Math.abs(a.aR - b.aR) + 0.6 * (Math.abs(a.eL - b.eL) + Math.abs(a.eR - b.eR))
      + Math.abs(a.look - b.look) + Math.abs(a.drop - b.drop) / 40 + Math.abs(a.face - b.face) > 0.35;
  }
  private card(k: number, mirror: boolean, size: number): HTMLCanvasElement {
    const key = `${k}:${mirror}:${size}`;
    let c = this.cache.get(key);
    if (c) return c;
    c = document.createElement("canvas"); c.width = size; c.height = size;
    const g = c.getContext("2d")!, H = { ...this.poseFor(k, mirror), x: 0, depth: 0 };
    const s = size / 560;
    g.setTransform(s, 0, 0, s, size / 2 - this.C.POS.C * s, size - (this.C.FLOOR + 30) * s);
    this.C.setContext(g); this.C.drawHuman(H);
    // recolour the figure: the coach's colour, or gold
    g.setTransform(1, 0, 0, 1, 0, 0); g.globalCompositeOperation = "source-in";
    g.fillStyle = isGold(k) ? "#f2b544" : "#7fe3ff"; g.fillRect(0, 0, size, size);
    g.globalCompositeOperation = "source-over";
    this.cache.set(key, c);
    return c;
  }

  draw(t: number, mirror: boolean, visible = true) {
    // on the page it fills its CSS box; off the page (the headset's lane panel) it keeps the canvas's own size
    const cv = this.canvas, onPage = cv.isConnected, dpr = onPage ? Math.min(devicePixelRatio, 2) : 1;
    const w = onPage ? cv.clientWidth : cv.width, h = onPage ? cv.clientHeight : cv.height;
    if (onPage && cv.width !== Math.round(w * dpr)) { cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); }
    const g = cv.getContext("2d")!; g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, w, h);
    if (!visible) return;
    const C = this.C, c = t / C.BEAT, nowX = w * 0.16, per = (w - nowX - 20) / AHEAD, size = Math.round(h * 0.86 * dpr);
    g.fillStyle = "#0b0a18aa"; g.fillRect(0, 0, w, h);
    g.strokeStyle = "#ede9ff"; g.lineWidth = 3; g.beginPath(); g.moveTo(nowX, 6); g.lineTo(nowX, h - 6); g.stroke();
    g.fillStyle = "#a9a3cc"; g.font = "600 11px sans-serif"; g.fillText("NOW", nowX - 34, 16);
    const first = Math.max(0, Math.floor(c) - 1), last = Math.min(C.N * 8 - 1, Math.ceil(c + AHEAD));
    let prev: HumanPose | null = first > 0 ? this.poseFor(first - 1, mirror) : null;
    for (let k = first; k <= last; k++) {
      const H = this.poseFor(k, mirror), show = !prev || this.differs(H, prev) || k % 8 === 0 || isGold(k);
      prev = H;
      if (!show) continue;
      const x = nowX + (k - c) * per, alpha = x < nowX ? Math.max(0, 1 - (nowX - x) / (per * 0.8)) : 1;
      if (alpha <= 0) continue;
      g.globalAlpha = alpha;
      const cardW = size / dpr;
      if (isGold(k)) { g.fillStyle = "#f2b54433"; g.beginPath(); g.roundRect(x - cardW / 2, 4, cardW, h - 8, 12); g.fill(); }
      g.drawImage(this.card(k, mirror, size), x - cardW / 2, 4, cardW, h - 8);
      g.fillStyle = isGold(k) ? "#f2b544" : "#ede9ff"; g.font = "800 13px ui-monospace, monospace";
      g.fillText(String((k % 8) + 1), x - 4, h - 6);
      g.globalAlpha = 1;
    }
  }
}
