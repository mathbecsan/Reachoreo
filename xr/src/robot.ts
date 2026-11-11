// One Reachy Mini in the scene: Pollen's rig (models/reachy_mini.glb, built by tools/build_reachy_glb.py), driven with
// SDK units exactly as the real robot is (head pose in the robot's base frame, body yaw, two antennas).
//
// Bones (docs/RIG_MAPPING.md in pollen-robotics/reachy_mini_blender): Core = body yaw; Core.001 carries the head
// (in Blender it copies Head.001's transform through constraints, which glTF drops, so we place it ourselves);
// Antenna.L/R.002 = the antennas (local Z hinge). The rig is 2.19x real size: we scale it by 0.4575.
import * as THREE from "three";
import type { GLTF } from "three/examples/jsm/loaders/GLTFLoader.js";
import type { SdkCommand } from "./sdk";

const RIG_SCALE = 0.4575;
const d2r = Math.PI / 180;
const inv = new THREE.Matrix4(), tmp = new THREE.Matrix4(), m = new THREE.Matrix4();

// The robot frame (x forward, y left, z up) as seen in the robot's own space here (forward = +z, left = +x, up = +y).
const R2S = new THREE.Matrix4().set(0, 1, 0, 0, 0, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 1);
const S2R = R2S.clone().invert();

export class Reachy {
  readonly root = new THREE.Group();        // place this on the counter; it faces +z (toward the audience)
  private core: THREE.Object3D; private head: THREE.Object3D; private antL: THREE.Object3D; private antR: THREE.Object3D;
  private coreRest: THREE.Quaternion; private antLRest: THREE.Quaternion; private antRRest: THREE.Quaternion;
  private headRest = new THREE.Matrix4();   // Core.001 in root space, at rest
  private pivot = new THREE.Vector3();      // the head's rotation centre (Head.001), root space
  private bodySign = 1; private antSign = { L: 1, R: 1 };
  // the six Stewart-platform rods: a bottom joint on the body (rides on Core) and a top joint on the head
  private rods: THREE.InstancedMesh; private rodBottom: THREE.Object3D[] = []; private rodTopRest: THREE.Vector3[] = [];

  constructor(gltf: GLTF, name: string) {
    const model = gltf.scene.clone(true);
    model.rotation.y = Math.PI;              // the rig faces -z after the Y-up export
    model.scale.setScalar(RIG_SCALE);
    this.root.name = name;
    this.root.add(model);
    const find = (n: string) => { const o = model.getObjectByName(n); if (!o) throw new Error(`rig bone ${n} missing`); return o; };
    this.core = find("Core"); this.head = find("Core001") ?? find("Core.001");
    this.antL = find("AntennaL002"); this.antR = find("AntennaR002");
    this.coreRest = this.core.quaternion.clone(); this.antLRest = this.antL.quaternion.clone(); this.antRRest = this.antR.quaternion.clone();
    this.root.updateMatrixWorld(true);
    this.headRest.copy(this.rel(this.head));
    this.pivot.setFromMatrixPosition(this.rel(find("Head001")));
    model.traverse(o => { if ((o as THREE.Mesh).isMesh) { o.castShadow = true; o.receiveShadow = true; } });
    for (const k of ["A", "B", "C", "D", "E", "F"]) {
      this.rodBottom.push(find(`Neck${k}003`));
      this.rodTopRest.push(new THREE.Vector3().setFromMatrixPosition(this.rel(find(`Head${k}`))));
    }
    this.rods = new THREE.InstancedMesh(new THREE.CylinderGeometry(0.0022, 0.0022, 1, 6), new THREE.MeshStandardMaterial({ color: 0x2a2a30, roughness: 0.5, metalness: 0.6 }), 6);
    this.rods.castShadow = true; this.rods.frustumCulled = false; this.root.add(this.rods);
    this.calibrateSigns(find);
  }

  /** A node's matrix in this robot's root space. */
  private rel(o: THREE.Object3D) {
    inv.copy(this.root.matrixWorld).invert();
    return new THREE.Matrix4().multiplyMatrices(inv, o.matrixWorld);
  }

  /** Which way each hinge turns is read off the geometry once, so a sign convention can't be silently wrong:
   *  +body yaw turns the robot's front toward its left (+x here); +antenna "out" swings the tip away from the head. */
  private calibrateSigns(find: (n: string) => THREE.Object3D) {
    const probe = (o: THREE.Object3D, f: () => void) => {
      const p = new THREE.Vector3(); f(); this.root.updateMatrixWorld(true); p.setFromMatrixPosition(this.rel(o)); return p;
    };
    const front = new THREE.Object3D(); this.core.add(front);
    front.position.copy(this.core.worldToLocal(this.root.localToWorld(this.pivot.clone().add(new THREE.Vector3(0, 0, 0.05)))));
    const yAxis = new THREE.Vector3(0, 1, 0), zAxis = new THREE.Vector3(0, 0, 1);
    const x0 = probe(front, () => this.core.quaternion.copy(this.coreRest)).x;
    const x1 = probe(front, () => this.core.quaternion.copy(this.coreRest).multiply(new THREE.Quaternion().setFromAxisAngle(yAxis, 0.3))).x;
    this.bodySign = x1 > x0 ? 1 : -1;
    this.core.quaternion.copy(this.coreRest); this.core.remove(front);
    for (const [side, node, rest, tipName, outX] of [["L", this.antL, this.antLRest, "AntennaL003", 1], ["R", this.antR, this.antRRest, "AntennaR003", -1]] as const) {
      const tip = find(tipName);
      const a = probe(tip, () => node.quaternion.copy(rest)).x;
      const b = probe(tip, () => node.quaternion.copy(rest).multiply(new THREE.Quaternion().setFromAxisAngle(zAxis, 0.4))).x;
      this.antSign[side] = Math.sign((b - a) * outX) || 1;
      node.quaternion.copy(rest);
    }
    this.root.updateMatrixWorld(true);
  }

  /** Pose the robot from SDK units (pose.to_sdk / sdk.ts toSdk). */
  setPose(c: SdkCommand) {
    this.core.quaternion.copy(this.coreRest).multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), this.bodySign * c.body_yaw_rad));
    // head: create_head_pose = R.from_euler("xyz", [roll, pitch, yaw]) in the base frame, plus z up
    const rRobot = new THREE.Matrix4().makeRotationFromEuler(new THREE.Euler(c.head_roll_deg * d2r, c.head_pitch_deg * d2r, c.head_yaw_deg * d2r, "ZYX"));
    const rScene = new THREE.Matrix4().multiplyMatrices(R2S, rRobot).multiply(S2R);
    const lift = new THREE.Vector3(0, c.head_z_mm / 1000, 0);
    m.makeTranslation(this.pivot.x + lift.x, this.pivot.y + lift.y, this.pivot.z + lift.z)
      .multiply(rScene).multiply(tmp.makeTranslation(-this.pivot.x, -this.pivot.y, -this.pivot.z)).multiply(this.headRest);
    this.root.updateMatrixWorld(true);
    const parentRel = this.rel(this.head.parent!);
    const local = parentRel.invert().multiply(m);
    local.decompose(this.head.position, this.head.quaternion, this.head.scale);
    // rods: bottom joints move with the body; top joints with the head (the head's motion from rest, applied to them)
    this.root.updateMatrixWorld(true);
    const delta = m.clone().multiply(this.headRest.clone().invert());
    const up = new THREE.Vector3(0, 1, 0), q = new THREE.Quaternion(), mat = new THREE.Matrix4();
    for (let k = 0; k < 6; k++) {
      const a = new THREE.Vector3().setFromMatrixPosition(this.rel(this.rodBottom[k]));
      const b = this.rodTopRest[k].clone().applyMatrix4(delta);
      const dir = b.clone().sub(a), len = dir.length();
      q.setFromUnitVectors(up, dir.normalize());
      mat.compose(a.add(b).multiplyScalar(0.5), q, new THREE.Vector3(1, len, 1));
      this.rods.setMatrixAt(k, mat);
    }
    this.rods.instanceMatrix.needsUpdate = true;
    // antennas: SDK [right, left]; on the real robot +right and -left are "out" (pose.py calibration)
    const [right, left] = c.antennas_rad;
    this.antR.quaternion.copy(this.antRRest).multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 0, 1), this.antSign.R * right));
    this.antL.quaternion.copy(this.antLRest).multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 0, 1), this.antSign.L * -left));
  }
}
