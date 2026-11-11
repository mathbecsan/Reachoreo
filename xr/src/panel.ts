// A flat panel in the 3D scene with a 2D canvas on it: the HUD, the moves lane and the menus inside the headset
// (a headset shows no page). Buttons are rectangles on the canvas; a controller or hand ray picks them by uv.
import * as THREE from "three";

export interface Button { id: string; x: number; y: number; w: number; h: number; label: string; on?: boolean; primary?: boolean; dim?: boolean }

export class Panel {
  readonly canvas = document.createElement("canvas");
  readonly g: CanvasRenderingContext2D;
  readonly tex: THREE.CanvasTexture;
  readonly mesh: THREE.Mesh;
  buttons: Button[] = [];
  hover: string | null = null;

  /** w x h metres, drawn at pxPerM canvas pixels per metre. */
  constructor(readonly w: number, readonly h: number, pxPerM = 640) {
    this.canvas.width = Math.round(w * pxPerM); this.canvas.height = Math.round(h * pxPerM);
    this.g = this.canvas.getContext("2d")!;
    this.tex = new THREE.CanvasTexture(this.canvas); this.tex.colorSpace = THREE.SRGBColorSpace; this.tex.anisotropy = 4;
    this.mesh = new THREE.Mesh(new THREE.PlaneGeometry(w, h),
      new THREE.MeshBasicMaterial({ map: this.tex, transparent: true, depthWrite: false, toneMapped: false }));
    this.mesh.renderOrder = 10; this.mesh.userData.panel = this;
  }
  get W() { return this.canvas.width; } get H() { return this.canvas.height; }

  /** Redraw: clears, calls fn with the context and canvas size, uploads the texture. */
  draw(fn: (g: CanvasRenderingContext2D, W: number, H: number) => void) {
    this.g.setTransform(1, 0, 0, 1, 0, 0); this.g.clearRect(0, 0, this.W, this.H); this.buttons = [];
    fn(this.g, this.W, this.H); this.tex.needsUpdate = true;
  }

  /** A card background. */
  card(fill = "#17152ef2", stroke = "#2f2a58") {
    const g = this.g; g.fillStyle = fill; g.strokeStyle = stroke; g.lineWidth = 4;
    g.beginPath(); g.roundRect(2, 2, this.W - 4, this.H - 4, 28); g.fill(); g.stroke();
  }
  text(s: string, x: number, y: number, size: number, color = "#ede9ff", weight = 600, align: CanvasTextAlign = "left") {
    const g = this.g; g.font = `${weight} ${size}px -apple-system, "Segoe UI", sans-serif`; g.fillStyle = color; g.textAlign = align; g.textBaseline = "middle";
    g.fillText(s, x, y);
  }
  /** Wrapped text; returns the y after the last line. */
  para(s: string, x: number, y: number, maxW: number, size: number, color = "#ede9ff") {
    const g = this.g; g.font = `500 ${size}px -apple-system, "Segoe UI", sans-serif`; g.fillStyle = color; g.textAlign = "left"; g.textBaseline = "middle";
    let line = "";
    for (const word of s.split(" ")) {
      const next = line ? `${line} ${word}` : word;
      if (g.measureText(next).width > maxW && line) { g.fillText(line, x, y); y += size * 1.3; line = word; } else line = next;
    }
    if (line) { g.fillText(line, x, y); y += size * 1.3; }
    return y;
  }
  button(b: Button) {
    const g = this.g, hot = this.hover === b.id;
    g.fillStyle = b.primary ? (hot ? "#5df0a0" : "#3ddc84") : b.on ? (hot ? "#4a4290" : "#3a3478") : hot ? "#332e60" : "#211e40";
    g.strokeStyle = b.on ? "#7fe3ff" : "#2f2a58"; g.lineWidth = 3;
    g.beginPath(); g.roundRect(b.x, b.y, b.w, b.h, 18); g.fill(); g.stroke();
    this.text(b.label, b.x + b.w / 2, b.y + b.h / 2 + 1, Math.min(34, b.h * 0.42), b.primary ? "#06210f" : b.dim ? "#a9a3cc" : "#ede9ff", 700, "center");
    this.buttons.push(b);
  }
  /** The button under a ray hit (uv from three's raycaster). */
  hit(uv: THREE.Vector2): Button | null {
    const x = uv.x * this.W, y = (1 - uv.y) * this.H;
    return this.buttons.find(b => x >= b.x && x <= b.x + b.w && y >= b.y && y <= b.y + b.h) ?? null;
  }
}
