// Score units -> Reachy Mini SDK units: a line-by-line port of reachy_dance/pose.py to_sdk(), so the 3D robots
// move exactly like the real ones (same calibration, same safety limits). tests/test_xr.py checks it against Python.
import type { RobotPose } from "/static/encendido-stage.mjs";

export interface Calibration {
  yaw_deg: number; body_deg: number; pitch_deg: number; z_mm_per_px: number;
  yaw_left_sign: number; roll_sign: number; pitch_down_sign: number; ant_right_out_sign: number; ant_left_out_sign: number;
  ant_swap: boolean; max_pitch_roll_deg: number; max_body_deg: number; max_head_body_delta_deg: number; max_antenna_rad: number; max_z_mm: number;
}
export const DEFAULT_CAL: Calibration = {
  yaw_deg: 40, body_deg: 30, pitch_deg: 25, z_mm_per_px: 0.5, yaw_left_sign: 1, roll_sign: 1, pitch_down_sign: 1,
  ant_right_out_sign: 1, ant_left_out_sign: -1, ant_swap: false, max_pitch_roll_deg: 35, max_body_deg: 155,
  max_head_body_delta_deg: 60, max_antenna_rad: 1.45, max_z_mm: 12,
};
export interface SdkCommand { head_roll_deg: number; head_pitch_deg: number; head_yaw_deg: number; head_z_mm: number; body_yaw_rad: number; antennas_rad: [number, number] }

const clip = (x: number, lim: number) => Math.max(-lim, Math.min(lim, x));
const deg = (r: number) => r * 180 / Math.PI;

export function toSdk(p: RobotPose, cal: Calibration): SdkCommand {
  const bodyDeg = clip(p.body * cal.body_deg + deg(p.turn), cal.max_body_deg);
  const relYaw = clip(p.yaw * cal.yaw_deg, cal.max_head_body_delta_deg);
  const headYaw = cal.yaw_left_sign * (bodyDeg + relYaw);
  const bodyYaw = cal.yaw_left_sign * bodyDeg;
  const roll = cal.roll_sign * clip(deg(p.roll), cal.max_pitch_roll_deg);
  const pitch = cal.pitch_down_sign * clip(-p.pitch * cal.pitch_deg, cal.max_pitch_roll_deg);
  const z = clip(-p.bob * cal.z_mm_per_px, cal.max_z_mm);
  const [camL, camR] = cal.ant_swap ? [p.antR, p.antL] : [p.antL, p.antR];
  const right = cal.ant_right_out_sign * Math.max(-0.3, Math.min(cal.max_antenna_rad, camL));
  const left = cal.ant_left_out_sign * Math.max(-0.3, Math.min(cal.max_antenna_rad, camR));
  return { head_roll_deg: roll, head_pitch_deg: pitch, head_yaw_deg: headYaw, head_z_mm: z, body_yaw_rad: bodyYaw * Math.PI / 180, antennas_rad: [right, left] };
}
