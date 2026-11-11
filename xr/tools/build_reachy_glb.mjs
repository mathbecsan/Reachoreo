// npm run assets:reachy: rebuild public/models/reachy_mini.glb from Pollen's official Blender rig.
// Needs Blender 5.1 and the repo cloned with Git LFS into ../assets-src/reachy_mini_blender (gitignored):
//   git lfs install && git clone https://github.com/pollen-robotics/reachy_mini_blender.git ../assets-src/reachy_mini_blender
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url)), xr = path.resolve(here, "..");
const blend = path.resolve(xr, "../assets-src/reachy_mini_blender/reachy_mini_link/assets/reachy_mini.blend");
const blender = process.env.BLENDER || ["/Applications/Blender.app/Contents/MacOS/Blender", "blender"].find(p => p === "blender" || existsSync(p));
if (!existsSync(blend) || statSync(blend).size < 1e6) {
  console.error(`missing ${blend} (or it's a Git LFS pointer): clone the repo with Git LFS installed, see this file's header`);
  process.exit(1);
}
const tmp = path.resolve(xr, "../assets-src/out"); mkdirSync(tmp, { recursive: true });
const raw = path.join(tmp, "reachy_mini_rehearse_raw.glb"), out = path.join(xr, "public/models/reachy_mini.glb");
execFileSync(blender, ["--background", blend, "--python", path.join(here, "build_reachy_glb.py"), "--", "--out", raw], { stdio: "inherit" });
execFileSync(path.join(xr, "node_modules/.bin/gltfpack"), ["-i", raw, "-o", out, "-kn", "-cc"], { stdio: "inherit" });   // meshopt compression, bones kept
console.log(`wrote ${path.relative(xr, out)} (${Math.round(statSync(out).size / 1024)} KB)`);
