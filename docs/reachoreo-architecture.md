# Reachoreo architecture: one system for the web app, the robots and the VR game

Written 2026-11-10 from a read-only audit of this repo and the Unity project (`~/Unity/Reachoreo`).
**Reachoreo** is the project. **Encendido** is one dance (76 s, 120 BPM, 19 phrases) and, today, the only source of moves.

## 1. Where things stand

| Part | Where | Status |
|---|---|---|
| Music analysis (tempo, tracked beats, count 1, 8-count phrases, song parts, accents) | browser, `reachy_dance/dashboard/static/music.mjs` | Good. Beats sit ~3 ms from the drums on live recordings. Reusable as is. |
| Dance generator (beam search: rhythm, energy, flow, variety) | `reachy_dance/choreography/library.py` (+ JS twin `static/choreo.mjs`) | Good cost structure, but **hard-wired to Encendido**: pieces are `(src, half)` indices into code (`encendido.py`, `encendido-stage.mjs`), intro/finale indices fixed, `MOVES == E.N_PHRASES`. |
| Dance file `library/<slug>/choreo.json` (format 2) | `library/` | Stores timing (`counts`, phrases, accents, quality) and **references** to Encendido pieces. No motion inside, so every player must run Encendido's code. |
| Dancer (human) part | `static/encendido-stage.mjs` HumanPose, `xr/src/body.ts` 3D joints | A 2D-preview parameterisation (arms, lean, look, feet offsets); 3D joints derived. Enough for a coach; too thin for hips/footwork styles. |
| Learn from video | `static/learn.mjs` | Makes per-dance phrase tracks (`learned`). Not promoted to reusable library pieces. |
| Robot output | `agent.py` → `pose.py to_sdk` → `robot_io.py` | Good: SDK units, limits, per-robot latency. |
| Web VR rehearsal | `xr/` | Plays Encendido only. |
| Unity VR game | `~/Unity/Reachoreo` | Menus, coach, mirror, body tracking, scoring; **now plays dance files** (section 3). |

## 2. Target architecture

```
            ┌────────────── Reachoreo engine (this repo) ──────────────┐
 song  ───► │ music analysis ─► generator ◄── movement database          │ ───► dance file
 (yours or  │  (music.mjs)       (library.py)   (move sets: Encendido,   │      reachoreo.dance/1
  curated)  │                                    salsa, bachata, ...)   │        │
            └───────────────────────────────────────────────────────────┘        │
                                                                                  ├──► real Reachy Minis (agents)
                                                                                  ├──► web dashboard / rehearsal
                                                                                  └──► VR game (Quest)
```

Rules:
1. **One engine.** Analysis and generation live here only. Players (VR, web, robots) never re-implement them.
2. **The dance file is the contract.** It is self-contained: song facts, every count's time, phrases, and **baked motion**
   for Reachy A, Reachy B and the dancer. Any player can play it without Encendido's code.
3. **Moves are data.** The movement database is a set of move-set files, one per style; Encendido is the first set.
4. **Personal songs stay personal.** A dance made from your own song has no licence: it is "My songs", stays on your
   devices, is never committed or shipped. Curated songs carry their licence and credit inside the dance file.

## 3. Formats (implemented)

### Dance file `reachoreo.dance/1` (`tools/export_dance.py` → `<out>/<slug>/dance.json` + `song.ogg`)

| Key | Meaning |
|---|---|
| `schema`, `id`, `title`, `artist`, `style`, `tags`, `difficulty` | identity; `style` drives the game's filters (salsa, cumbia, bachata, marinera, merengue, pop, electronic, hip-hop, funk, world...) |
| `license` | `{name, url, credit}` for curated songs; `null` = personal |
| `song` | `{file: "song.ogg", bpm, firstDownbeat, duration}`; audio time = dance time + `firstDownbeat` |
| `countBpm`, `beatsPerCount`, `duration` | the dance's count speed (fast songs are counted every other beat) |
| `counts[]` | dance time of every count (0 = first downbeat), from the tracked beats |
| `phrases[]` | `{n, name, act, start, end, pieces: ["encendido:5a", "encendido:9b~", "learned:3.0"]}` (`~` = mirrored) |
| `frameRate`, `frames` | sampling of the motion below (20 fps) |
| `robotKeys`, `robotA[]`, `robotB[]` | flat `frames × 8` in score units (`yaw pitch roll body turn antL antR bob`); convert with `pose.py to_sdk` (A = left robot) |
| `dancerJoints`, `dancer[]` | flat `frames × 22 × 3`, metres, frame of `xr/src/body.ts` (x = audience's right, y up, z toward the audience) |
| `dancerRootKeys`, `dancerRoot[]` | flat `frames × 3`: stage travel (m), depth, spin (rad) |

Checked: Encendido's baked robot motion matches `tests/golden/encendido_robots.json` to 5e-5 (rounding).
Songs are converted to OGG Vorbis (same length, so counts still land) because Unity decodes OGG on every platform.

### Move set `reachoreo.moveset/1` (`tools/export_moveset.py` → `moves/encendido/moveset.json`)

Per set: `id, name, style, stepsPerCount (8), robotKeys, humanKeys, units`. Per piece: `id ("encendido:4b"), name,
style, tags, counts (4), energy, kind, mirrorable, text {you, A, B}, profile {accents, robotAccents, humanAccents,
start, end}` and tracks `robotA[], robotB[], human[]` sampled per count step. This is exactly what the generator
needs, as data.

## 4. How the pieces connect

- **Make a dance (your song)**: web app `/create` → analysis → generator → `library/<slug>/choreo.json` →
  `tools/export_dance.py <slug> <dir>` → copy `<dir>/<slug>/` to the headset's private folder
  `/sdcard/Android/data/com.reachoreo.vr/files/Dances/` → it appears under **My songs**.
  Next: a "Send to headset" button (dashboard serves `GET /api/dance/<slug>.json` + song; the game downloads it over
  Wi-Fi). Needs one port change first: the dashboard and the Unity editor link (MCP for Unity) both use 8080.
- **Curated songs**: check the licence → `/create` → tune → `export_dance.py --style ... --license-name ... --credit ...`
  → `Assets/StreamingAssets/Dances/<id>/` + `index.json` → credits appear in the game's Settings.
- **Real robots**: unchanged today (agents read the score). Later they can play `robotA/robotB` from a dance file too.

## 5. The movement database: plan

1. **Generator reads move sets** (`library.py`): candidates = pieces from the sets allowed for the song's style
   (plus Encendido as a fallback), costs from `profile`, intro/finale chosen by `kind`/`tags` instead of fixed
   indices. `choreo.json` refers to `set:piece` ids. Bake keeps working unchanged.
2. **Per-style phrase rules**: salsa (1-2-3, 5-6-7, breaks on 4/8), bachata (8 with a tap on 4 and 8), cumbia,
   marinera (6/8 feel, handkerchief), hip-hop, house... as data in the set (`phraseCounts`, accent templates).
3. **Promote learned moves**: a learned phrase (video or the user's own recording) can be profiled and saved into a
   move set, so the library grows from real dancers.
4. **Richer dancer data for styles**: recognisable salsa/bachata/marinera lives mostly in the human part (steps, hips,
   arms). Add hip/torso rotation and foot placement to the dancer track (or store full 3D joints per step from
   motion capture). The Reachys carry the style through accent timing, sways, head and antenna character: they have
   no legs (head pose, body yaw, two antennas).
5. **Go deep before wide**: one style end to end first (e.g. salsa with a Stanford dancer: 20-40 pieces, 2-3 songs),
   then the others.

## 6. Curated songs: first shortlist (not downloaded yet)

All from Kevin MacLeod (incompetech.com), **CC BY 4.0**; credit: "Title Kevin MacLeod (incompetech.com), Licensed
under Creative Commons: By Attribution 4.0, https://creativecommons.org/licenses/by/4.0/", shown on the game's
credits screen. Check each track's page before use.

| Style | Track | BPM | Length |
|---|---|---|---|
| Salsa | No Frills Salsa | 144 | 2:47 |
| Cumbia | No Frills Cumbia | 96 | 3:27 |
| Merengue | Notanico Merengue | 120 | 3:01 |
| Samba | Samba Isobel | 95 | 4:10 |
| Tango | Tango de Manzana | 127 | 3:02 |
| Funk / disco | Funky Chunk / Disco con Tutti | 115 | ~4:00 |
| Electronic | Brain Dance | 124 | 3:35 |
| Hip-hop | Wepa | 120 | 3:15 |
| World (West African) | Allada | 100 | 3:43 |

Gaps: **bachata and marinera** (and reggaeton) are not in that catalogue. Best source: Stanford musicians and student
groups, with written permission (most authentic, and it fits the Stanford places). Avoid AI-generated music.

## 7. Open decisions

- Where the engine runs: on a laptop (songs never leave your devices) or a server (easier, but uploads leave the device).
- Which style to take end to end first, and with which dancer.
- Port for the dashboard vs MCP for Unity (both 8080).
