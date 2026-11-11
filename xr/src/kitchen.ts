// The SRC kitchen mockup, until your scan replaces it: simple shapes in the 2D preview's palette, the counter top and
// floor with CC0 Poly Haven textures (marble_01 by Rob Tuytel; laminate_floor_02 by Dario Barresi and Charlotte
// Baglioni), reflections from the CC0 "Blinds" HDRI (Greg Zaal). See ASSETS.md.
// Lights follow the preview's light arc: cold blue, warm, then pink and cyan party washes.
import * as THREE from "three";
import { HDRLoader } from "three/examples/jsm/loaders/HDRLoader.js";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import type { Lights } from "/static/encendido-stage.mjs";
import { LAYOUT as L } from "./layout";

const base = import.meta.env.BASE_URL;
const cold = (a: string, b: string, w: number) => new THREE.Color(a).lerp(new THREE.Color(b), w);

function tex(loader: THREE.TextureLoader, name: string, repeat: [number, number], srgb: boolean) {
  const t = loader.load(`${base}tex/${name}`);
  t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(...repeat); t.anisotropy = 4;
  if (srgb) t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

export class Kitchen {
  readonly group = new THREE.Group();
  private mats: Record<string, THREE.MeshStandardMaterial> = {};
  private hemi = new THREE.HemisphereLight(0x6f7fb0, 0x14182a, 0.6);
  private spots: Record<"L" | "C" | "R", THREE.SpotLight> = {} as never;
  private cones: Record<"L" | "C" | "R", THREE.Mesh> = {} as never;   // the preview's visible light beams
  private lampLight = new THREE.PointLight(0xffd696, 0, 6, 2);
  private lampBulb: THREE.MeshBasicMaterial;
  private fill = new THREE.DirectionalLight(0x8a7ad0, 2);    // soft light from the audience, so the counter front reads
  private party = [new THREE.PointLight(0xf27aa8, 0, 8, 1.5), new THREE.PointLight(0x7fe3ff, 0, 8, 1.5)];

  constructor(renderer: THREE.WebGLRenderer, scene: THREE.Scene, parent: THREE.Object3D = scene) {
    const tl = new THREE.TextureLoader();
    const std = (k: string, color: string, extra: THREE.MeshStandardMaterialParameters = {}) =>
      (this.mats[k] = new THREE.MeshStandardMaterial({ color, roughness: 0.85, ...extra }));
    const box = (w: number, h: number, d: number, mat: THREE.Material, x: number, y: number, z: number) => {
      const mesh = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat);
      mesh.position.set(x, y, z); mesh.castShadow = mesh.receiveShadow = true; this.group.add(mesh); return mesh;
    };
    const { counter: c, room } = L;
    // floor and walls
    const floor = new THREE.Mesh(new THREE.PlaneGeometry(room.width, room.depth),
      // the plank texture's relief and gloss, the preview's color (its brown diffuse turned the room red)
      std("floor", "#3a3170", { normalMap: tex(tl, "laminate_floor_02_nor_gl_1k.jpg", [4, 4], false),
        roughness: 0.8 }));
    floor.rotation.x = -Math.PI / 2; floor.position.z = room.backZ + room.depth / 2; floor.receiveShadow = true; this.group.add(floor);
    const wallMat = std("wall", "#2a2152", { roughness: 0.95 });
    box(room.width, room.height, 0.05, wallMat, 0, room.height / 2, room.backZ - 0.025);
    box(0.05, room.height, room.depth, wallMat, -room.width / 2, room.height / 2, room.backZ + room.depth / 2);
    box(0.05, room.height, room.depth, wallMat, room.width / 2, room.height / 2, room.backZ + room.depth / 2);
    // counter: cabinets with door seams, and a marble top
    const cz = c.frontZ - c.depth / 2;
    box(c.length, c.height - 0.04, c.depth, std("cabinet", "#3b3470"), 0, (c.height - 0.04) / 2, cz);
    const seam = std("seam", "#2e2862");
    for (let x = -c.length / 2; x <= c.length / 2 + 1e-6; x += c.length / 8) box(0.012, c.height - 0.12, 0.01, seam, x, (c.height - 0.04) / 2, c.frontZ + 0.003);
    box(c.length + 0.06, 0.04, c.depth + 0.04, std("top", "#544a96", { map: tex(tl, "marble_01_diff_1k.jpg", [3, 0.6], true),
      normalMap: tex(tl, "marble_01_nor_gl_1k.jpg", [3, 0.6], false), roughness: 0.35 }), 0, c.height - 0.02, cz + 0.01);
    // window (night sky) and upper cabinets
    const w = L.window;
    box(w.w + 0.08, w.h + 0.08, 0.04, std("frame", "#4a3f80"), w.x, w.y, room.backZ + 0.02);
    box(w.w, w.h, 0.02, std("sky", "#3b2f6b", { emissive: new THREE.Color("#22344f"), emissiveIntensity: 0.6 }), w.x, w.y, room.backZ + 0.045);
    const moon = new THREE.Mesh(new THREE.CircleGeometry(0.045, 24), new THREE.MeshBasicMaterial({ color: 0xe6ecff, transparent: true, opacity: 0.6 }));
    moon.position.set(w.x + w.w * 0.27, w.y + w.h * 0.3, room.backZ + 0.06); this.group.add(moon);
    for (const x of L.cabinets.xs) box(L.cabinets.w, L.cabinets.h, L.cabinets.depth, std("upper", "#2e2660"), x, L.cabinets.y, room.backZ + L.cabinets.depth / 2);
    // pendant lamp
    const lamp = L.lamp;
    const cord = new THREE.Mesh(new THREE.CylinderGeometry(0.004, 0.004, room.height - lamp.y), new THREE.MeshBasicMaterial({ color: 0x8888a0 }));
    cord.position.set(lamp.x, (room.height + lamp.y) / 2, lamp.z); this.group.add(cord);
    const shade = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.16, 0.12, 32, 1, true), std("shade", "#5a4a7a", { side: THREE.DoubleSide }));
    shade.position.set(lamp.x, lamp.y, lamp.z); this.group.add(shade);
    this.lampBulb = new THREE.MeshBasicMaterial({ color: 0xffecbe });
    const bulb = new THREE.Mesh(new THREE.SphereGeometry(0.035, 16, 12), this.lampBulb); bulb.position.set(lamp.x, lamp.y - 0.05, lamp.z); this.group.add(bulb);
    this.lampLight.position.set(lamp.x, lamp.y - 0.1, lamp.z);   // no shadow: a point light's shadow renders the scene 6 more times
    // spots over each robot and over you, like the preview's light cones
    for (const [k, x] of [["L", L.robots.A.x], ["C", 0], ["R", L.robots.B.x]] as const) {
      const s = new THREE.SpotLight(0xffe4aa, 0, 7, 0.42, 0.6, 1.2);
      s.position.set(x, room.height - 0.05, k === "C" ? L.dancer.z - 0.3 : L.robots.z + 0.4);
      s.target.position.set(x, k === "C" ? 0 : c.height, k === "C" ? L.dancer.z : L.robots.z);
      s.castShadow = k !== "C"; s.shadow.mapSize.set(1024, 1024);
      this.group.add(s, s.target); this.spots[k] = s;
      // a soft additive beam from the light to where it lands, brightest at the top (vertex alpha)
      const top = s.position.clone(), bottom = s.target.position.clone(), h = top.distanceTo(bottom);
      const geo = new THREE.CylinderGeometry(0.06, Math.tan(0.42) * h * 0.85, h, 32, 1, true);
      const col = new Float32Array(geo.attributes.position.count * 4);
      for (let v = 0; v < geo.attributes.position.count; v++) { const y = geo.attributes.position.getY(v) / h + 0.5; col.set([1, 1, 1, 0.15 + 0.85 * y], v * 4); }
      geo.setAttribute("color", new THREE.BufferAttribute(col, 4));
      const cone = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color: 0xffe4aa, transparent: true, opacity: 0, vertexColors: true, depthWrite: false,
        blending: THREE.AdditiveBlending, side: THREE.DoubleSide }));
      cone.position.copy(top).add(bottom).multiplyScalar(0.5);
      cone.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), top.clone().sub(bottom).normalize());
      this.group.add(cone); this.cones[k] = cone;
    }
    this.party[0].position.set(-1.6, 1.8, 0.6); this.party[1].position.set(1.6, 1.8, 0.6);
    this.fill.position.set(0.5, 2.2, 5); this.fill.target.position.set(0, 0.8, -0.5);
    this.group.add(this.hemi, this.lampLight, this.fill, this.fill.target, ...this.party);
    this.mergeStatic();
    parent.add(this.group);
    // reflections only: a dim CC0 interior HDRI
    new HDRLoader().load(`${base}hdri/blinds_1k.hdr`, t => {
      const pm = new THREE.PMREMGenerator(renderer); scene.environment = pm.fromEquirectangular(t).texture; scene.environmentIntensity = 0.25; t.dispose(); pm.dispose();
    });
  }

  /** Static boxes that share a material (door seams, walls, upper cabinets) become one mesh each: fewer draw calls,
   *  which matters on the Quest, where every object is drawn once per eye. */
  private mergeStatic() {
    const byMat = new Map<THREE.Material, THREE.Mesh[]>();
    for (const o of this.group.children)
      if (o instanceof THREE.Mesh && o.geometry instanceof THREE.BoxGeometry && !Array.isArray(o.material)) byMat.set(o.material, [...(byMat.get(o.material) ?? []), o]);
    for (const [mat, meshes] of byMat) {
      if (meshes.length < 2) continue;
      const geo = mergeGeometries(meshes.map(m => { m.updateMatrix(); return m.geometry.clone().applyMatrix4(m.matrix); }));
      if (!geo) continue;
      const merged = new THREE.Mesh(geo, mat); merged.castShadow = meshes[0].castShadow; merged.receiveShadow = meshes[0].receiveShadow;
      for (const m of meshes) { m.removeFromParent(); m.geometry.dispose(); }
      this.group.add(merged);
    }
  }

  /** desktop: everything. vr: no shadow passes (they render the scene twice more per eye on the Quest). ar: your
   *  real kitchen shows through, so the room's surfaces hide and only its lights stay, lighting the robots and coach. */
  setMode(mode: "desktop" | "vr" | "ar") {
    for (const o of this.group.children) if (!(o instanceof THREE.Light) && !(o.type === "Object3D")) o.visible = mode !== "ar";
    this.spots.L.castShadow = this.spots.R.castShadow = mode === "desktop";
  }

  /** The preview's light state lt (stage poseAt(t).lt) and your x on stage. */
  update(lt: Lights, dancerX: number, t: number) {
    const w = lt.warm;
    this.mats.wall.color.copy(cold("#1a2230", "#2a2152", w));
    this.mats.cabinet.color.copy(cold("#2a3244", "#3b3470", w));
    this.mats.top.color.copy(cold("#3e485e", "#544a96", w));
    this.mats.floor.color.copy(cold("#1e2434", "#2b2556", w));
    this.mats.upper.color.copy(cold("#1e2636", "#2e2660", w));
    this.fill.color.copy(cold("#5a6fae", "#8a7ad0", w)); this.fill.intensity = 1.6 + 1.4 * lt.M;
    this.hemi.color.copy(cold("#4a5f9a", "#8a72c8", w)); this.hemi.intensity = 1.6 + 1.2 * lt.M;
    const spot = w > 0.5 ? new THREE.Color(255 / 255, 228 / 255, 170 / 255)
      : new THREE.Color(THREE.MathUtils.lerp(170, 255, w * 2) / 255, THREE.MathUtils.lerp(195, 228, w * 2) / 255, THREE.MathUtils.lerp(235, 170, w * 2) / 255);
    for (const k of ["L", "C", "R"] as const) { this.spots[k].color.copy(spot); this.spots[k].intensity = (k === "C" ? 7 : 14) * lt[k]; }
    this.spots.C.position.x = this.spots.C.target.position.x = this.cones.C.position.x = dancerX;
    for (const k of ["L", "C", "R"] as const) {
      const mat = this.cones[k].material as THREE.MeshBasicMaterial; mat.color.copy(spot); mat.opacity = 0.11 * lt[k];
    }
    this.lampLight.intensity = 4 * lt.lamp; this.lampBulb.color.setRGB(1, 0.93, 0.75).multiplyScalar(0.25 + 0.75 * lt.lamp);
    this.party[0].intensity = this.party[1].intensity = 6 * lt.party;
    this.party[0].position.x = -1.6 + 0.4 * Math.sin(t * 1.3); this.party[1].position.x = 1.6 + 0.4 * Math.sin(t * 1.1 + 2);
  }
}
