# ASSETS.md: 3D rehearsal mode (/rehearse)

**Status: milestone 4** (VR/AR added no art assets: the in-headset panels, rays, hand dots and rings are drawn in code;
no controller or hand models are downloaded). Picks approved 2026-11-10 ("use your picks"). Assets in use are listed first, with exact
versions and every change we made; the rest stay as candidates for later milestones.

Rules, from the brief:

- No AI-generated models, textures or animations.
- Allowed licenses: CC0, CC-BY 4.0 (credited on the in-app credits page), Pollen Robotics' published Reachy Mini files
  under their stated license, and Mixamo (embedded use only).
- The repo is **public**: raw Mixamo files live in `assets-private/` (gitignored), and the repo ships a script that
  converts your local copies.

Checked on 2026-11-10. Prices and plan limits change: re-check before paying for anything.

## In use

| Asset | File(s) in the repo | Source and version | Author | License | What we changed |
|---|---|---|---|---|---|
| Reachy Mini rigged model (A1) | `xr/public/models/reachy_mini.glb` (+ `NOTICE.txt`, `LICENSE-Apache-2.0.txt`) | [pollen-robotics/reachy_mini_blender](https://github.com/pollen-robotics/reachy_mini_blender) commit `bfa02cf` (2026-08-04), `reachy_mini.blend` | Clément Plays (model and rig), Pollen Robotics | Apache-2.0 | `xr/tools/build_reachy_glb.py`: procedural materials → flat colors baked into vertex colors (1 material); parts merged per bone; decimated (head 632k → 30k, body 114k → 8k, base 38k → 6k, antennas 8.7k → 2k each; ~850k → 51k triangles, ~400 → 6 draw calls); Stewart rod meshes left out (the page draws 6 rods); antenna rods made rigid; meshopt compression (gltfpack 1.3.0) |
| Counter top texture (B5) | `xr/public/tex/marble_01_{diff,nor_gl}_1k.jpg` | [polyhaven.com/a/marble_01](https://polyhaven.com/a/marble_01), 1k JPG | Rob Tuytel | CC0 | none (tinted in the material) |
| Floor relief (B5) | `xr/public/tex/laminate_floor_02_nor_gl_1k.jpg` | [polyhaven.com/a/laminate_floor_02](https://polyhaven.com/a/laminate_floor_02), 1k JPG | Dario Barresi, Charlotte Baglioni | CC0 | normal map only (the brown diffuse made the room red) |
| Reflections HDRI (E1) | `xr/public/hdri/blinds_1k.hdr` | [polyhaven.com/a/blinds](https://polyhaven.com/a/blinds), 1k HDR | Greg Zaal | CC0 | none (used at 25% for reflections only) |
| Coach (C, placeholder) | none: built in code | `xr/src/coach.ts`: ellipsoids, instanced (body + glow outline = 2 draw calls), a hood for Acts I–II | ours | ours | driven by the choreography's own dancer pose (the preview's figure), so every count is the real move. Swap in Mixamo Y Bot when you've downloaded it to `assets-private/` |
| Pictograms | none: drawn at run time | `xr/src/lane.ts`: the preview's `drawHuman` at the coach's pose for each count, recoloured | ours | ours | not drawn by hand, not generated |
| Beat track (F, placeholder) | none: rendered in the browser | `xr/src/clock.ts` (synthesized) | — | ours | until your 120 BPM track exists: drop it in `xr/public/music/encendido.mp3` |

Not yet used: the Kenney Furniture Kit (B4). Its download sits behind a form on kenney.nl, so milestone 1 builds the
counter, walls, window, cabinets and lamp from simple shapes in the preview's palette instead. Your scan (B1) will
replace them.

## Candidates

### A. Reachy Mini (robot model)

| # | Candidate | Source | Author | License | Triangles | Format | Preview |
|---|---|---|---|---|---|---|---|
| A1 ★ | Reachy Mini rigged model (`reachy_mini.blend`, 59-bone armature: Stewart neck IK, antennas, body yaw) | [pollen-robotics/reachy_mini_blender](https://github.com/pollen-robotics/reachy_mini_blender) | 3D model and rig by Clément Plays ([ArtStation](https://clementplays.artstation.com/)), repo by Pollen Robotics | **Apache-2.0** (repo LICENSE) | not stated: measure at export (the .blend is 17.2 MB) | .blend → GLB via the repo's `export_gltf.py` (Y-up, Draco, procedural materials baked to flat PBR) | README images in the repo |
| A2 | URDF/MJCF description with 159 CAD STL parts | [pollen-robotics/reachy_mini](https://github.com/pollen-robotics/reachy_mini), `src/reachy_mini/descriptions/reachy_mini/` | Pollen Robotics | Apache-2.0 | high: mechanical CAD, needs decimating | STL + MJCF/URDF | — |

Notes:

- The brief expected CC BY-NC-SA. That license is for Pollen's **hardware** designs. The Blender repo and the SDK repo
  are both Apache-2.0, which allows commercial use, needs no share-alike, and only asks us to keep the license and a
  NOTICE. Credit Clément Plays anyway.
- Exporting needs **Blender 5.1** (installed here: `/Applications/Blender.app`; version to confirm) and **Git LFS**
  (not installed: `brew install git-lfs`). Without LFS the .blend arrives as a 130-byte pointer file.
- The repo's `docs/RIG_MAPPING.md` documents the controls: `Head.001` is the 6-DoF head, `Core` carries body yaw
  (local Y), and `Antenna.R/L.002+.003` the antennas, with `[right, left]` order on the wire. The neck IK does
  not survive glTF export, so in three.js we drive `Head.001` as a transform and either aim the six rods or hide them.
- The motion source stays `static/encendido-stage.mjs`, generated from the preview and already tested against the
  golden data within 1e-4. The 3D page imports that module rather than porting the score a third time.

### B. Kitchen (SRC mockup)

You can scan the room (answered 2026-11-10), so the plan is: **the scan is the kitchen**, and CC0 pieces fill any gaps.
In **AR**, the real kitchen is visible through passthrough, so we don't render it at all: we only detect the real
counter to anchor the coach and the ghost robots. The kitchen model matters for desktop and full VR.

Scan apps (the scan is your own capture, so there's nothing to license; the app's terms still apply to exports):

| # | App | Cost and limits | Exports | Notes |
|---|---|---|---|---|
| B1 ★ | [Scaniverse](https://scaniverse.com/) (Niantic) | free app; commercial use reportedly on a paid plan | Gaussian splat as PLY or SPZ; mesh as GLB/OBJ in the app (check the export menu) | iOS and Android. Splats look photoreal; meshes are lighter for the Quest |
| B2 | [Polycam](https://poly.cam/pricing) | free plan exports **glTF/GLB only** ([help](https://learn.poly.cam/hc/en-us/articles/27756102599572-What-File-Types-Can-Polycam-Export)); Basic $30/month for OBJ/FBX | GLB mesh (free), splats | Good LiDAR meshes on an iPhone Pro |
| B3 | [Luma 3D Capture](https://apps.apple.com/us/app/luma-3d-capture/id1615849914) | free, but development appears frozen ([report](https://thepostflow.com/post-production/visual-effects-vfx/luma-ai-gaussian-splatting/)) | PLY splat, low-detail mesh | Not recommended for new work |

For the Quest, use a **decimated mesh** (target ≤ 150k triangles for the room, baked lighting). A splat of a whole
room is too heavy for 72 fps in the headset, so it's for desktop only, rendered with Spark (see G).

CC0 / CC-BY fallbacks and gap-fillers:

| # | Candidate | Source | Author | License | Triangles | Format | Preview |
|---|---|---|---|---|---|---|---|
| B4 ★ | Furniture Kit (140 files: low-poly interior pieces) | [kenney.nl/assets/furniture-kit](https://kenney.nl/assets/furniture-kit) | Kenney | CC0 | very low (hundreds per piece) | GLB / FBX / OBJ (verify in the download) | [preview](https://kenney.nl/media/pages/assets/furniture-kit/d049bcc581-1677580840/preview.png) |
| B5 | Poly Haven textures plus props: counter tops built as simple boxes with CC0 PBR textures; pendant and stools from [metal_stool_01](https://polyhaven.com/a/metal_stool_01) (8.3k tris) and [bar_chair_round_01](https://polyhaven.com/a/bar_chair_round_01) (14.4k) | [polyhaven.com](https://polyhaven.com/models) | Ulan Cabanilla (stool), Dairon Sanchez (bar chair) | CC0 | per prop, as listed | glTF + 1k–8k textures | [stool](https://cdn.polyhaven.com/asset_img/thumbs/metal_stool_01.png?height=400) |
| B6 | "Modern kitchen" | [Sketchfab 95163e53…](https://sketchfab.com/3d-models/95163e53ab694ed6bcec1ae50158bc94) | ChoboiAssets | CC-BY 4.0 | 7.4k | glTF download | [thumb](https://media.sketchfab.com/models/95163e53ab694ed6bcec1ae50158bc94/thumbnails/d15adcdc60084eecb38a5dde99388556/0693beb404834d299afb70db0deaa849.jpeg) |
| B7 | "Kitchen Cabinet Set - Functional Elegance" | [Sketchfab 4ab19cb3…](https://sketchfab.com/3d-models/4ab19cb3602e4ab9804acc8a37efe360) | Tom Au | CC-BY 4.0 | 108k | glTF download | [thumb](https://media.sketchfab.com/models/4ab19cb3602e4ab9804acc8a37efe360/thumbnails/3852b439735348bf9d94d323f014d729/b3ac558cb5e04d03aa55a4479142df1e.jpeg) |

Layout until you measure: one long counter 0.9 m high, the robots at its two ends 2.5 m apart, open floor in front,
window on the left, pendant lamp in the center. It lives in one config file, so real numbers drop in later.

### C. Coach avatar

| # | Candidate | Source | License | Triangles | Format | Preview |
|---|---|---|---|---|---|---|
| C1 ★ | **Y Bot**: plain mannequin, easy to give one bright color and a glow outline | [Mixamo](https://www.mixamo.com/) (Adobe) | Mixamo terms: royalty-free in projects, **raw files may not be redistributed** ([FAQ thread](https://community.adobe.com/questions-696/mixamo-faq-licensing-royalties-ownership-eula-and-tos-589400)) | measure at download | FBX → GLB via our conversion script | mixamo.com character list |
| C2 | Universal Base Characters: 6 humanoids (Regular, Teen, Superhero; male and female), humanoid rig with Mixamo-style bone names | [quaternius.com](https://quaternius.com/packs/universalbasecharacters.html) / [itch.io](https://quaternius.itch.io/universal-base-characters) | page says **CC0**, but reports say a newer "Quaternius Asset Licence" restricts redistribution ([note](https://app.cinevva.com/guides/free-rigged-3d-character-models)). **Unclear: needs your call or a check of the license file in the download** | ~13k average | glTF / FBX / Blend | [preview](https://quaternius.com/assets/images/fullres/universalbasecharacters.jpg) |
| C3 | VRoid β-era AvatarSample models (anime style) | [VRoid FAQ](https://vroid.pixiv.help/hc/en-us/articles/4402614652569-Do-VRoid-Studio-s-sample-models-come-with-conditions-of-use), [OpenGameArt mirror](https://opengameart.org/content/vroid-studio-cc0-models) | CC0 for the β samples only (AvatarSample_A/B/C are **not** CC0) | typically 30–70k | VRM (via `@pixiv/three-vrm`) | on the OpenGameArt page |

Just Dance look: we restyle the material in code (one solid color, rim glow, inverted-hull outline). The model itself
isn't changed, so we stay inside every license above.

Hoodie for Acts I and II: none of these ship with a hoodie. Options: Quaternius's modular outfit packs (same license
question as C2), or a hood made from simple primitives in code. Pick at milestone 2.

### D. Coach animation (motion capture of you)

| # | Tool | Cost for the 76 s piece plus pickups (~3 min of footage) | Output | Notes |
|---|---|---|---|---|
| D1 ★ | [FreeMoCap](https://github.com/freemocap/freemocap) | free; the software is AGPL-3.0, but your capture data is yours | Blender scene with a rig; FBX/BVH from Blender | 2–3 synced webcams for best results; latest release v2.0.0-alpha.25 (2026-09-24), actively developed |
| D2 | [Rokoko Vision](https://www.rokoko.com/products/vision) | free tier: **30 s a month**, FBX only. Not enough. Basic, about $12 for one month, reportedly includes 600 s and BVH ([pricing](https://www.rokoko.com/pricing)) | FBX (BVH on paid) | one or two cameras; easiest to use |
| D3 | [Move One](https://docs.move.ai/knowledge/move-one-pricing) (Move.ai) | free: 30 credits once, 30 s clips. Starter $18/month for 60 credits; Free/Personal are non-commercial | FBX, BVH, USD, Blend | iPhone app (Android via web upload) |

Mixamo dance clips are placeholders only, until your capture exists (milestone 2). We already own a body tracker
(MediaPipe in `static/learn.mjs`, built for "Learn from a video"), but it's single-camera and best for arms; studio
mocap from D1–D3 is still the plan for the coach.

### E. Lighting

| # | HDRI | Source | Author | License | Preview |
|---|---|---|---|---|---|
| E1 ★ | Blinds (kitchen, window, counter) | [polyhaven.com/a/blinds](https://polyhaven.com/a/blinds) | Greg Zaal | CC0 | [thumb](https://cdn.polyhaven.com/asset_img/thumbs/blinds.png?height=400) |
| E2 | Kiara Interior (tiles, fridge, window, kitchen) | [polyhaven.com/a/kiara_interior](https://polyhaven.com/a/kiara_interior) | Greg Zaal | CC0 | [thumb](https://cdn.polyhaven.com/asset_img/thumbs/kiara_interior.png?height=400) |
| E3 | Brown Photostudio 02 (studio with kitchen corner) | [polyhaven.com/a/brown_photostudio_02](https://polyhaven.com/a/brown_photostudio_02) | Sergej Majboroda | CC0 | [thumb](https://cdn.polyhaven.com/asset_img/thumbs/brown_photostudio_02.png?height=400) |

Used at 1k–2k for reflections only. The story's light arc (cold blue, warm, then pink and cyan) uses scene lights
keyed to the show clock.

### F. Music

Your own 120 BPM track. Open question: Encendido has no music file in the repo yet (`conductor.music: null`), and the
existing song library holds commercial tracks (Blondie, Tori el Robot) that stay out of /rehearse per the brief.

### G. Code libraries (not art assets, listed for completeness)

| Library | Version (latest on 2026-11-10) | License | Use |
|---|---|---|---|
| three | 0.187.0 (2026-10-30). We'll pin **0.186.1** (2026-09-24) unless 0.187 has passed two weeks by milestone 1 | MIT | renderer, WebXR |
| @sparkjsdev/spark | 2.4.0 | MIT | Gaussian splat rendering (desktop, if we use a splat scan) |
| @pixiv/three-vrm | 3.5.5 | MIT | only if C3 is picked |
| meshoptimizer / gltfpack | 1.3.0 | MIT | meshopt compression |
| vite, typescript | pinned at milestone 1 (two weeks or older) | MIT, Apache-2.0 | build |
| MediaPipe Tasks Vision | 1.1.1 (already vendored) | Apache-2.0 | desktop webcam scoring |
| iwer (Meta's Immersive Web Emulation Runtime) | **2.7.0** (2026-10-21), dev dependency | MIT | `?emulate=quest3`: an emulated Quest 3 for testing VR/AR; loaded only with that option |
