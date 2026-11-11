// The coach: a life-size dancer driven by the choreography's own dancer pose (stage poseAt(t).H, the 2D preview's
// figure), so every count is the real Encendido move. Built in code from ellipsoids (no third-party asset): one
// instanced body (1 draw call), a glowing inverted-hull outline (1 draw call) and a hood for Acts I and II.
// When you add the Mixamo Y Bot (assets-private/), the same HumanPose will drive its bones instead.
import * as THREE from "three";
import type { HumanPose } from "/static/encendido-stage.mjs";
import { bodyJoints, type V3 } from "./body.ts";

const SEGMENTS = 18;               // 2 legs x 3, pelvis, torso, neck, head, 2 arms x 4

export interface CoachStyle { color: number; glow: number; opacity?: number; outline?: boolean }

/** The dance seen in a mirror: left and right swap (Just Dance's default, so the coach moves like your reflection). */
export function mirrorHuman(h: HumanPose): HumanPose {
  return { ...h, x: -h.x, look: -h.look, tilt: -h.tilt, lean: -h.lean, face: -h.face,
    aL: h.aR, eL: h.eR, aR: h.aL, eR: h.eL, fLx: -h.fRx, fRx: -h.fLx, fLy: h.fRy, fRy: h.fLy, rotL: h.rotR, rotR: h.rotL };
}

export class Coach {
  readonly root = new THREE.Group();          // stand it where the dancer stands; it faces +z
  private body: THREE.InstancedMesh;
  private outline: THREE.InstancedMesh | null = null;
  private hood: THREE.Mesh;
  private m = new THREE.Matrix4(); private q = new THREE.Quaternion(); private up = new THREE.Vector3(0, 1, 0);

  constructor(style: CoachStyle) {
    const geo = new THREE.SphereGeometry(1, 20, 14);
    const mat = new THREE.MeshStandardMaterial({ color: style.color, roughness: 0.55, emissive: style.color, emissiveIntensity: 0.25,
      transparent: style.opacity !== undefined, opacity: style.opacity ?? 1, depthWrite: style.opacity === undefined });
    this.body = new THREE.InstancedMesh(geo, mat, SEGMENTS);
    this.body.castShadow = style.opacity === undefined; this.body.frustumCulled = false;
    this.root.add(this.body);
    if (style.outline !== false) {
      // inverted hull: the same ellipsoids a little larger, back faces only, unlit glow colour
      this.outline = new THREE.InstancedMesh(geo, new THREE.MeshBasicMaterial({ color: style.glow, side: THREE.BackSide }), SEGMENTS);
      this.outline.frustumCulled = false; this.root.add(this.outline);
    }
    const hoodGeo = new THREE.SphereGeometry(1, 20, 12, 0, Math.PI * 2, 0, Math.PI * 0.62);
    this.hood = new THREE.Mesh(hoodGeo, new THREE.MeshStandardMaterial({ color: 0x3a2236, roughness: 0.9, side: THREE.DoubleSide }));
    this.root.add(this.hood);
  }

  /** An ellipsoid from joint a to joint b (metres, in the coach's space) with radius r. */
  private seg(i: number, a: THREE.Vector3, b: THREE.Vector3, r: number) {
    const d = b.clone().sub(a), len = d.length();
    this.q.setFromUnitVectors(this.up, len > 1e-6 ? d.normalize() : this.up);
    this.m.compose(a.clone().add(b).multiplyScalar(0.5), this.q, new THREE.Vector3(r, len / 2 + r * 0.6, r));
    this.body.setMatrixAt(i, this.m);
    if (this.outline) {
      this.m.compose(a.clone().add(b).multiplyScalar(0.5), this.q, new THREE.Vector3(r + 0.012, len / 2 + r * 0.6 + 0.012, r + 0.012));
      this.outline.setMatrixAt(i, this.m);
    }
  }
  private ball(i: number, c: THREE.Vector3, r: THREE.Vector3, q = new THREE.Quaternion()) {
    this.m.compose(c, q, r); this.body.setMatrixAt(i, this.m);
    if (this.outline) { this.m.compose(c, q, r.clone().addScalar(0.012)); this.outline.setMatrixAt(i, this.m); }
  }

  /** Pose from the preview's dancer model (camera's view: aL is the arm on the audience's left). */
  setPose(h: HumanPose) {
    const B = bodyJoints(h), V = (p: V3) => new THREE.Vector3(...p);
    let i = 0;
    for (const S of [B.L, B.R]) {               // legs: hip, knee, foot and a toe
      const hip = V(S.hip), knee = V(S.knee), foot = V(S.foot);
      this.seg(i++, hip, knee, 0.075); this.seg(i++, knee, foot, 0.062);
      this.ball(i++, V(S.toe), new THREE.Vector3(0.05, 0.035, 0.11));
    }
    this.ball(i++, V(B.pelvis), new THREE.Vector3(0.15 * B.af + 0.04, 0.11, 0.11));
    this.seg(i++, V(B.spine[0]), V(B.spine[1]), 0.15 * B.af + 0.03);
    this.seg(i++, V(B.neck[0]), V(B.neck[1]), 0.045);
    const head = V(B.head), hq = new THREE.Quaternion().setFromEuler(new THREE.Euler(...B.headRot, "YXZ"));
    this.ball(i++, head, new THREE.Vector3(0.105, 0.125, 0.11), hq);
    for (const S of [B.L, B.R]) {               // arms: shoulder, upper arm, forearm, hand
      const Sh = V(S.shoulder), E = V(S.elbow), W = V(S.wrist);
      this.ball(i++, Sh, new THREE.Vector3(0.06, 0.06, 0.06));
      this.seg(i++, Sh, E, 0.048); this.seg(i++, E, W, 0.042);
      this.ball(i++, V(S.hand), new THREE.Vector3(0.045, 0.06, 0.035));
    }
    for (; i < SEGMENTS; i++) { this.m.makeScale(0, 0, 0); this.body.setMatrixAt(i, this.m); this.outline?.setMatrixAt(i, this.m); }
    this.body.instanceMatrix.needsUpdate = true; if (this.outline) this.outline.instanceMatrix.needsUpdate = true;
    // hood over the head in Acts I and II (it comes off in phrase 9)
    this.hood.visible = h.hood > 0.02;
    if (this.hood.visible) { this.hood.position.copy(head).add(new THREE.Vector3(0, 0.015, -0.01)); this.hood.quaternion.copy(hq); this.hood.scale.setScalar(0.128 + 0.01 * h.hood); }
    // spin and the circle upstage
    this.root.rotation.y = h.face;
  }
}
