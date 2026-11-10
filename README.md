# Reachoreo

**Dance with two Reachy Mini robots.** Pick a dance, or make one from any song, and both robots learn it.
Then rehearse together in the browser: the page watches you through the camera, shows each robot live with its
own head-camera view, scores how in sync the three of you are, and records everything.

It started as **Encendido** ("switched on"), a 76-second piece for two Reachy Minis and a human dancer, staged in the
Stanford Robotics Center kitchen mockup. Encendido is still the built-in dance; every other dance is built from its moves.

What it does:

- **Make a dance from a song**: finds the song's real beats (live-band tempo drift included), bars and parts
  (verse, chorus...), then builds a dance whose hits land on the song's accents and whose moves flow into each other.
- **Learn from a dance video**: follows a dancer in a video, turns it into your part, and has both robots dance along.
- **Robots learn it automatically**: load a dance and both Reachys switch to it; each robot is tuned so its moves
  land on the beat, together.
- **Rehearse & record**: your camera, both robots, their head cameras and the choreography side by side, with live sync
  scores, the song in step, and one-button recording (everything at once, or just the parts you pick).
- **Set up my Reachys**: a six-step wizard that finds the robots, pairs left and right, checks their directions,
  tunes their timing and matches their head cameras.

### Get it running

```bash
uv venv .venv && uv pip install -e ".[dev]"       # or: python -m venv .venv && .venv/bin/pip install -e ".[dev]"
bash tools/fetch_camera_assets.sh                 # the browser pose model (MediaPipe), kept out of git
.venv/bin/python -m reachy_dance.dashboard        # then open http://localhost:8080
```

Plug in both robots and follow **Home → Set up my Reachys**. No robots? Tick "no robots here" on Home to rehearse with
simulated ones. (The Python package is still called `reachy_dance`, from the project's first name.)

## Repository layout: one repo, split by layer

Use **one repository**, and organize it by what the code does, not by which robot runs it.
"Left" and "right" are a config value (`--side A` / `--side B`), not separate code.

Why not one repo per robot:

- Both robots and the dancer share one score. In Encendido the parts are written against each other
  (call and response, ping-pong hits, mirrored spins), so they must change together in one commit.
- The robots coordinate through a message protocol and a shared clock. If they lived in separate repos,
  a protocol change in one would silently break the other.
- The left and right robots run the same control code. Two copies would drift apart.

Independence comes from processes, not repos: each robot runs its own agent, can be started, stopped,
calibrated and tested alone, and keeps dancing if the camera or the other robot drops out.

```
Reachoreo/
├── config/show.yaml                 hosts, ports, latency, calibration: the only per-robot settings (the setup wizard edits it)
├── reachy_dance/
│   ├── choreography/
│   │   ├── encendido.py             the robot score: both robots, ported from the preview, tested against it
│   │   ├── encendido.yaml           phrase sheet: dancer cues + how robots may react in each phrase
│   │   ├── library.py               dances made from songs: generator (rhythm, flow, structure), playback, library/
│   │   └── move_profiles.json       hits, energy and start/end pose of every 4-count piece (generated)
│   ├── conductor.py                 show clock, music, dancer prompter, health monitor
│   ├── agent.py                     one robot's process (run once per robot)
│   ├── reactive.py                  reactions layered on the score: gaze, tracking, lean, cue triggers, echoes
│   ├── clock.py                     show clock and clock follower (network-delay tolerant)
│   ├── bus.py                       ZeroMQ publish/subscribe
│   ├── pose.py                      pose units, SDK conversion, safety limits, slew limiting
│   ├── robot_io.py                  Reachy Mini SDK wrapper, and a dry-run stand-in
│   ├── dashboard/                   the web app: server.py (HTTP + bus), monitor.py, sync.py, launcher.py,
│   │                                setup.py (wizard), tuning.py, static/ (pages, music.mjs, learn.mjs, choreo.mjs)
│   └── perception/
│       ├── pose_tracker.py          camera + MediaPipe Pose → dancer state and cue events
│       ├── features.py              landmark → feature/event logic (pure, unit-tested)
│       └── fake_dancer.py           scripted dancer for rehearsing without a camera
├── library/                         your dances (choreo.json; songs and videos stay local, gitignored)
├── preview/encendido-preview.html   the animated preview: the reference for every movement
├── docs/encendido-context.md        the original piece: story, design rules, full script
├── tests/                           85 tests: score vs preview, music, generator, learning, setup, sync...
└── tools/                           build_stage_js.py, build_move_profiles.mjs, measure_arrival.py, asset scripts
```

How this maps to the structure you proposed: `choreography/left_reachy` and `right_reachy` become one score
with a side parameter; `human_dancer` becomes the phrase sheet (what the dancer does and which cues the robots
listen for); `controllers/*_reachy_controller` become one `agent.py`; `coordination/` is `clock.py`, `bus.py`
and `conductor.py`; `perception/` is the same.

## Architecture

```
                 ┌──────────────┐  clock (100 Hz): state, show time
                 │  conductor   │───────────────────────────────┐
   music ◀───────│ prompter for │                               │
                 │ the dancer   │◀── status ───┐                 │
                 └──────────────┘              │                 ▼
┌──────────────┐  dancer (30 Hz):     ┌────────┴─────┐  peer   ┌──────────────┐
│ pose_tracker │  x, depth, energy,   │  agent  A    │◀───────▶│  agent  B    │
│ (camera)     │──cue events─────────▶│ score(side A)│reactions│ score(side B)│
└──────────────┘                      │ + reactions  │         │ + reactions  │
                                      └──────┬───────┘         └──────┬───────┘
                                       set_target 50 Hz         set_target 50 Hz
                                         Reachy A                 Reachy B
```

Every pose is computed fresh from the show time, never queued or replayed, so the robots cannot drift
from the music or from each other. Three layers combine each tick:

1. **Score**: the exact choreography for this instant, identical to the preview. This alone is a complete show.
2. **Reactions**: in phrases that allow it, gaze toward the dancer, follow them as they move, lean in when they
   come close, and fire short moves (pop, recoil, cheer, laugh) when perception sees a cue in its window.
   If the dancer is lost, reactions fade to zero within 0.7 s and the score carries on.
3. **Coordination**: each robot publishes its reactions. The other answers one beat later at half strength
   (an echo) in phrases marked `echo`, unless it already reacted to the same moment itself.

Safety sits on top: pitch and roll are kept under 35°, body under 155°, head-to-body under 60°, and every
channel is slew-limited. If the conductor's clock stops, robots freeze, then ease to rest after 3 s.

## Setup

```bash
pip install -e ".[perception,dev]"
pip show reachy-mini            # must match the version on both robots; pin it in pyproject.toml
pytest                          # 85 tests, no robots needed (node runs the page's math)
```

Give each robot a fixed IP and put both in `config/show.yaml` (A = camera's left, B = camera's right).
Wireless Reachy Minis can all be driven from one laptop. Two Lites over USB need their own daemons,
one per laptop or on different ports.

## Quick start: one command, then the browser

```bash
.venv/bin/python -m reachy_dance.dashboard      # open http://localhost:8080
```

Press **Start everything** on the Home page (or in the top bar of any page). It starts whatever isn't running yet:
each robot's daemon (from `robots.X.serial` in `config/show.yaml`), the conductor and both agents, with logs in
`runs/logs/`. Anything you started yourself in a terminal is detected and left alone; **Stop** stops only what the
page started. Tick "no robots here" to rehearse with simulated robots (`--dry-run` agents).

**First time (or new robots): Home → Set up my Reachys** (`/setup`). Six steps, about five minutes:
1. *Connect*: finds the robots on USB, pairs them to Reachy 1 / Reachy 2 if needed and starts everything.
2. *Left or right*: Reachy 1 wiggles; if the one on the right moved, the page swaps them (port, serial, timing) and restarts the agents.
3. *Directions*: both robots turn right, look up and raise the camera-left antenna; each "no" flips the matching
   calibration sign (or the antenna wiring) live and in show.yaml, and replays the move.
4. *Timing*: they dance two phrases; the page measures when their moves land and tunes each robot's lead time.
5. *Head cameras*: Reachy 1 nods; the head-camera view that moves most is its own (saved for the rehearsal page).
6. *Your camera*: framing guide.
Progress lives in `config/setup.json` (gitignored); Home shows "Ready to dance" or what's still missing.
Code: `dashboard/setup.py` (tests/test_setup.py), the agents' test moves are `setup_pose()` in `agent.py`.

The site has four pages, linked from the top bar (which also shows the loaded dance and whether the clock and
both robots are up):

- **Home** (`/`): the three steps (wake the robots, choose the dance, rehearse) and your library of dances.
  Loading a dance teaches it to both robots: the conductor switches (`load <slug>`), the agents follow at the next
  idle moment and report what they know, so each card shows "✓ Reachy 1 knows it".
- **Make a dance** (`/create`): drop in a song. `static/music.mjs` finds the tempo, count 1 and the 8-count
  phrase lines in the browser (fix them with ½×, 2×, ±0.5, tap, or nudge count 1 a beat). Fast songs (over 145 BPM)
  are counted every other beat, slow ones twice per beat. `choreography/library.py` then builds a dance from
  Encendido's 19 phrases used as a move library: the robots wake up over a quiet intro, calm moves go on quiet
  phrases, big ones on loud phrases, a surprise or spin on the drop, Full power at the end, some phrases mirrored
  so Reachy 2 leads. Change any phrase's move, preview it with the music, then **Save & teach both robots** and
  **Watch them dance it**. Songs and dances are kept in `library/<slug>/` (song files are gitignored). The page can't
  turn dance videos into robot moves, so for a known routine it links to YouTube and TikTok tutorials for the human part.
  How the beat is found (`static/music.mjs`): a beat tracker follows the song's real beats (dynamic programming,
  holding the tempo tightly or along a measured tempo curve, whichever sits better on the drum hits), so live-band
  recordings that drift a few BPM stay on the beat (a fixed grid drifted ±185 ms on Blondie's *One Way or Another*;
  tracked beats sit a median 3 ms from the drums). Count 1 sits on the kick and re-aligns if the strong beat moves.
  Phrases are grouped into song parts by timbre and loudness (intro A, verse B, chorus C...): the chorus (the part
  that returns most and closes the song) gets the big moves, other parts groove, and a returning part is danced
  the same way. A dance stores every count's time (`counts` in choreo.json); robots, dancer animation, counts,
  metronome, cue grading and reactions all follow those times instead of an even tempo.
  How moves are chosen: every phrase is two 4-count pieces, cut from Encendido's 19 phrases (38 pieces, both
  halves of a move, or halves of two moves stitched). `tools/build_move_profiles.mjs` measures each piece from the
  stage module: where its hits land (per half-count, robots and dancer), how much it moves, and its start and end
  pose (`choreography/move_profiles.json`; rerun it after editing the preview). The page measures where the song
  accents on each half-count; a beam search then picks pieces by rhythm (hits on the song's accents), flow (small pose
  jumps; carrying a move on is preferred), energy and variety. Joins between unrelated pieces crossfade from half a
  count before to a quarter after, so motion never jumps. The page shows the result as *♪ rhythm* and *⤳ smooth
  joins* scores, per phrase too, and re-scores after every edit. On Blondie: rhythm 52% → 66%, smooth joins 62% → 87%.
  The ceiling is the move library: with only Encendido's pieces, the best possible rhythm match there is ~85%.
  **Learn moves from a dance video** (Make a dance, optional): drop a video of someone dancing to the song (a
  tutorial, or your own recording from the rehearsal page). The page finds where it sits in the song from its soundtrack
  (or you type the start time), follows the dancer with the pose model at 2× speed, maps the body onto the stage
  dancer on the song's counts, and derives both robots' moves from it (antennas copy the arms on their side, heads bounce
  with the knees, nod on arm hits, tilt with the dancer and keep facing them). Pick which phrases use it; robot values
  are clamped to safe ranges. Keep the video and the rehearsal page shows it next to the choreography, in step
  (`library/<slug>/video.*`, gitignored). Code: `static/learn.mjs` (tests/test_learn_js.py).
- **Rehearse & record** (`/perform`): below. After a run, **Tune the robots' timing** adds each robot's measured
  lateness to its `latency_s` (live, and saved in show.yaml), so both land on the count and together.
- **Control room** (`/control`): the technical dashboard described below.

Under each robot on the rehearsal page, four tiles answer: *following the dance* (its measured head, body and
antennas against the choreography, 0-100%, naming the part that's off; turning to follow you counts as right in
phrases meant for that), *on the beat* (on time / late / early, and against the other robot), *watching you*
(can it see you, how far its head is from you) and *answering you* (its last reaction and which gesture caused it,
or the next gesture it's waiting for).

The rehearsal page plays the dance's song itself, locked to the show clock (Settings → song timing nudges it), so
all three of you hear the same downbeat. Keyboard: Space start or pause, Esc stop, R record, M metronome.

## Run the show

### Two Reachy Mini Lites over USB on one laptop

Each Lite needs its own daemon on its own port, from this project's venv (so SDK and daemon versions match).
On this laptop, the robot on the camera's LEFT (A) is `usbmodem5B7B0101971`, the RIGHT one (B) is
`usbmodem5B7B0111871` (re-check with `ls /dev/cu.usbmodem*` if you swap cables or ports):

```bash
.venv/bin/reachy-mini-daemon -p /dev/cu.usbmodem5B7B0101971 --fastapi-port 8000 --robot-name reachy_port8000 --no-media --headless
.venv/bin/reachy-mini-daemon -p /dev/cu.usbmodem5B7B0111871 --fastapi-port 8001 --robot-name reachy_port8001 --no-media --headless
```

`--no-media` keeps the robots' cameras free and avoids the two daemons fighting over them.
`config/show.yaml` points A at localhost:8000 and B at localhost:8001. Then start the agents (without `--dry-run`),
perception, the conductor and the dashboard as below.

Open four terminals:

```bash
python -m reachy_dance.agent --side A          # wakes Reachy A, takes the opening pose, waits
python -m reachy_dance.agent --side B
python -m reachy_dance.perception.pose_tracker # or: python -m reachy_dance.perception.fake_dancer
python -m reachy_dance.conductor               # type: start   (or start 13 to rehearse from phrase 13)
```

Or run the show from the browser: start a fifth process and open http://localhost:8080 (the control room is /control).

```bash
python -m reachy_dance.dashboard
```

The dashboard joins the bus and sends commands to the conductor (which still owns the clock). It shows:
the clock, phrase and count with the dancer's cue; each robot's state, clock drift, dancer confidence and
commanded pose against the pure score (with an 8 s trace); the dancer on a stage strip; a timeline of the
19 phrases with cue windows, cues seen and every reaction; and an event log you can export as CSV or JSON.
It flags inconsistencies between the robots: a process not publishing, a robot in a different state or
phrase than the conductor, drift beyond `dashboard.drift_warn_ms`, a robot that lost the clock, and a
reaction on one side only in a phrase that expects both to react. Space pauses and resumes.

### Live rehearsal with the camera (http://localhost:8080/perform)

You, Reachy A and Reachy B on one page, live, compared against the choreography:

- **You:** the laptop camera, mirrored, with your skeleton, and gold **target arms** drawn from your own shoulders
  showing where the choreography wants your arms right now. Count, what to do, next cue, metronome.
- **Stage:** the preview's own kitchen and drawings. Reachy A and B are drawn from where each robot *measures* itself,
  you are drawn from the camera, and the choreography (all three performers) is drawn faintly behind, so a wrong arm,
  a late robot or a robot out of step shows up at a glance.
- **Synchronization:** your pose match (%), your timing against the choreography (the delay that best lines up your
  arm motion with the preview's), when each robot's head actually lands relative to the count, A against B, and
  robots against you, with a 12 s chart of all three timings. Cue table and an end-of-run summary below.

The page runs MediaPipe in the browser (served locally, works offline) and sends landmarks to the dashboard,
which runs `FeatureTracker` in upper-body framing and publishes the dancer on the bus for the robots' reactions.
Don't run `fake_dancer` or `pose_tracker` at the same time.

```bash
./tools/fetch_camera_assets.sh     # once: MediaPipe browser build + pose model (about 35 MB)
```

Press **Start camera**, stand where you'll dance and press **Calibrate**, pick a section and **Start**.

**Recording.** Each Reachy's head camera (a USB "Reachy Mini Camera"; free because the daemons run with
`--no-media`) is shown under its panel as "what Reachy N sees" (swap with ⇄ if they're on the wrong robot).
The **record dock** stays at the bottom of the page: one big red button (or R) and presets for what to
record: *everything, separately* (your camera, Reachy 1 view, Reachy 2 view and the split-screen as four files at
once), *one split-screen video*, *just the cameras* (the three raw camera files) or *just me*. Tick the chips to make
your own mix (add *this screen* for a tab recording); the choice is remembered. *♪ song in the videos* puts the
song's audio in each file. Your camera is cropped by the format (wide, 4:3, vertical, square, close-up). Files
land in Downloads as `reachoreo-<dance>-<date>-<time>-<source>.mp4`, plus a `-sync.json` with each file's start offset and
the show time at start, to line them up in an editor; the dock lists what was saved. *auto-record each run* starts
with ▶ Start and stops when the run ends.

The choreography module (`static/encendido-stage.mjs`) is generated from `preview/encendido-preview.html` by
`python tools/build_stage_js.py`; rerun it after editing the preview (tests check it against the golden motion).
The pose comparison is in `static/rehearsal.mjs` and is tested in node. `tools/measure_arrival.py 6 9` measures
when each robot's head lands relative to the beat; use it to set `latency_s` per robot.

The expected cues live in `encendido.yaml` (`cues:` per phrase); the fake dancer performs the same list.

The conductor prints each phrase's dancer cue as it begins, and every 2 s shows each robot's clock drift
and whether the dancer is seen. Commands: `start [phrase] [last phrase]`, `pause`, `resume`, `stop`, `quit`.

Add `--dry-run` to an agent to print commands instead of moving a robot, and `--log run.csv` to record every
commanded pose and reaction (useful for timing analysis and for your write-up).

## Before the first real run

1. **Dry run everything:** two dry-run agents, the fake dancer and the conductor, with no robots.
   Try `fake_dancer --sloppy` to see the robots cope with late and missed cues.
2. **Check signs in simulation:** run one agent against the Reachy Mini simulator, start at phrase 7
   (Reachy A should turn toward the camera's right as you walk to it) and phrase 15 (antennas open outward).
   Flip any sign under `calibration:` that moves the wrong way.
3. **One robot at a time:** start a single agent on a real robot with the conductor, phrases 1 to 6.
4. **Measure latency (clap test):** film both robots doing phrase 9's nods next to the music. If a robot looks
   late, raise its `latency_s` by that amount.
5. **Calibrate the camera:** put the camera at the audience position, stand on the center mark facing it,
   press `c` in the tracker window. Walk to each robot and check that `x` moves the right way.

## Editing the choreography

- Robot motion lives in `choreography/encendido.py`, one block per phrase. Units match the preview
  (see `pose.py`). After changing motion that should also change the preview, update both and regenerate
  the golden file: `node tools/export_golden.js tests/golden/encendido_robots.json`.
- How robots may react lives in `choreography/encendido.yaml`. Change gaze, tracking, lean or echo there
  without touching code. Trigger counts are 0-based.
- A new piece is a new pair of files in `choreography/` plus `choreography: <name>` in the config.

## Using Pollen's recorded moves

The dance and emotion libraries (`side_peekaboo`, `sad1`, …) are good references for tuning each phrase's
motion, but this system does not play them directly: recorded moves block and run on their own timing,
which would break beat sync and reactions. Recreate the parts you like inside the score instead.

## Known limits

- MediaPipe sees one dancer, from the front. Spins and upstage moments lower confidence; the score covers them.
- Cue detection is heuristic. Tune the thresholds in `perception/features.py` with your real camera and lighting.
- The Reachy Mini has no eye lights, so the preview's eye glow is conveyed with posture only.
