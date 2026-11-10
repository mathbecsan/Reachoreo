# Encendido: project context

*Encendido* ("switched on") is a 76-second dance for two Reachy Mini robots and one human dancer, staged in the Stanford Robotics Center kitchen mockup. Reachy A sits on the counter on the camera's left, Reachy B on the camera's right, and the dancer performs in the middle.

## What's in this folder

- `preview/encendido-preview.html`: the animated preview. Open it in any browser. It is the reference for every movement, with practice controls (half speed, mirror view, loop a phrase, on-screen counts) and the full script below the stage.
- `reachy-dance/`: the control software. The robot score in `reachy_dance/choreography/encendido.py` is ported from the preview and tested against it (`tests/golden/encendido_robots.json` is the preview's exact robot motion). See its `README.md` and `CLAUDE.md`.

## The story

1. **I. Off:** cold blue light. The dancer stands frozen like a powered-off humanoid robot, hood up; both Reachys are asleep. Reachy A wakes, finds him, and wakes Reachy B.
2. **II. The reboot:** the robots charge him with antenna pulses. He boots up in robot ticks, robot-walks to greet each Reachy, and plays peekaboo with both.
3. **III. The spark:** hood off and the lights snap warm. Chicken pecks, a circle the robots follow, a spin, and the robots turn their backs and whip around.
4. **IV. Switched on:** party lights. Running man, a running-man turn, electro arms, ping-pong robot hits, a wave both ways, and a full-power finale pose.

## Design rules

- 19 phrases of 8 counts at 120 BPM (one phrase = 4 seconds).
- Balance: every interaction is shared. When one robot leads, the other grooves to the beat and watches the leader or the dancer, and each robot gets its own moment before they act together.
- Once the beat is in, the robots are never static: a groove layer of bounce, sway, antenna pops and nods runs under every phrase except deliberate freezes.
- The light tells the story: cold blue, then warm, then pink and cyan party light. The only prop is a dark hoodie.
- Robot limits: body rotation stops at ±160°, so the spin turns each robot until its back faces the camera, then whips it back.

## The script

Counts are 1-based here, as on the page. Library names are the closest moves in Pollen's official Reachy Mini dance and emotion libraries.

### I. Off

**1. Powered off** (0:00 to 0:04)

- Reachy A: Asleep: head down, antennas drooped, eyes dark. Breathes slowly. (library: `sleep1`)
- Dancer: Stand frozen like a switched-off humanoid: knees soft, arms dead, head hanging, hood up.
- Reachy B: Asleep. (library: `sleep1`)

**2. A flicker** (0:04 to 0:08)

- Reachy A: Eyes flicker on (counts 3 to 5). Head lifts, scans the kitchen with a big body turn, finds you on count 7. (library: `curious1, attentive1`)
- Dancer: Stay frozen. One glitch on count 6: your head twitches sideways and drops again.
- Reachy B: Still asleep, but dreaming: an antenna twitches on 3 and it shifts in its sleep on 7. (library: `sleep1`)

**3. Anyone there?** (0:08 to 0:12)

- Reachy A: Leans toward you, tilting, antennas reaching. Turns to B and taps the air twice with its near antenna. (library: `inquiring1`)
- Dancer: Failed boot: head jerks halfway up on 5, collapses on 7.
- Reachy B: Wakes on count 6, stretches its antennas, looks at you. (library: `attentive2`)

**4. Lonely** (0:12 to 0:16)

- Reachy A: Droops toward you. On 5 looks at B. On 7 and 8, two small nods: they have a plan. (library: `lonely1, then yes1`)
- Dancer: Frozen.
- Reachy B: Droops, then looks at A and nods back. (library: `sad1, then yes1`)

### II. The reboot

**5. Charging** (0:16 to 0:20)

- Reachy A: Points its near antenna at you and pulses it on every beat, rocking in to send energy. (library: `custom antenna pulse`)
- Dancer: A small jolt on every beat: shoulders twitch. On 5 to 8, head rises in ticks.
- Reachy B: Same, from the other side. (library: `custom antenna pulse`)

**6. Reboot** (0:20 to 0:24)

- Reachy A: Watches, then cheers each tick: antennas pop up on 3, 5 and 7. (library: `attentive1, then cheerful1`)
- Dancer: Boot sequence: head up on 1, right arm out on 3, forearm up on 4, left arm out on 5, forearm down on 6, head ticks to A on 7 and B on 8.
- Reachy B: Same as A, one beat later. (library: `attentive2, then cheerful1`)

**7. First steps** (0:24 to 0:28)

- Reachy A: Greets you with an antenna pop and a bounce when you reach it on 4, then turns to watch you cross to B. (library: `attentive1, then cheerful1`)
- Dancer: Robot walk: stiff steps to Reachy A on 1 to 4 (look up at it on 4), then across to Reachy B on 5 to 8 (look up on 8).
- Reachy B: Grooves and tracks you on 1 to 4, then greets you on 8 with its own antenna pop. (library: `attentive2, then cheerful1`)

**8. Peekaboo** (0:28 to 0:32)

- Reachy A: Both hide on 1 and 2. A pops up on 3. Both wait while you hide, both pop on 7, both laugh on 8. (library: `side_peekaboo, laughing1`)
- Dancer: Back at center. Lean back surprised at A on 3 and at B on 4. Hands over your face on 5 and 6, open them on 7. Laugh on 8.
- Reachy B: Pops up on 4, a beat after A. Pops with A on 7 and laughs on 8. (library: `side_peekaboo, laughing2`)

### III. The spark

**9. Hood off** (0:32 to 0:36)

- Reachy A: Recoils in surprise on 2, then nods yes on every beat; leans in when you step its way on 5. (library: `neck_recoil, then yeah_nod`)
- Dancer: Hands to your hood on 1, throw it back on 2. Shake out on 3 and 4. Step-touch toward A on 5 and 6, toward B on 7 and 8.
- Reachy B: Same, leaning in when you step its way on 7. (library: `surprised1, then yeah_nod`)

**10. Chicken peck** (0:36 to 0:40)

- Reachy A: Pecks on odd counts, then in unison with B on 5 to 8; antennas flap. (library: `chicken_peck`)
- Dancer: Funky chicken: elbows flap on every beat, head pecks forward; add knee pops on 5 to 8.
- Reachy B: Pecks on even counts, then in unison. (library: `chicken_peck`)

**11. Circle** (0:40 to 0:44)

- Reachy A: Turns head and body to follow you all the way around, bouncing. (library: `custom tracking (or face tracking)`)
- Dancer: Skip a full circle in 8 counts: toward A, upstage, past B, back to center.
- Reachy B: Same, from the other side. (library: `custom tracking`)

**12. Spin** (0:44 to 0:48)

- Reachy A: Dizzy head circles on 1 to 4. Turns its back on 5 and 6, whips around on 7, ta-da on 8. (library: `dizzy_spin, then body turn`)
- Dancer: Spin once with arms out on 1 and 2, land in a V on 3. Watch them spin on 5 to 8.
- Reachy B: Same, turning the opposite way. (library: `dizzy_spin, then body turn`)

### IV. Switched on

**13. Running man** (0:48 to 0:52)

- Reachy A: Head-bangs on every beat; antennas run like arms; body swings a quarter turn each bar. (library: `headbanger_combo`)
- Dancer: Running man, full energy.
- Reachy B: Same as A, swinging the other way. (library: `headbanger_combo`)

**14. Running man turn** (0:52 to 0:56)

- Reachy A: Spiral head moves while turning its body to keep facing you. (library: `interwoven_spirals`)
- Dancer: Running man while turning a full circle over 8 counts.
- Reachy B: Same, mirrored. (library: `interwoven_spirals`)

**15. Electro arms** (0:56 to 1:00)

- Reachy A: Antennas circle like arms. Pops up when you sweep toward it on 5. Halo pose with you on 7 and 8. (library: `custom antenna circles`)
- Dancer: Tecktonik arms over a step-touch: windmills on 1 and 2, hand roll on 3 and 4, sweep to A on 5 and to B on 6, arms in a halo around your head on 7 and 8.
- Reachy B: Antennas circle, opposite phase to A. Pops when you sweep its way on 6, halo on 7 and 8. (library: `custom antenna circles`)

**16. Robot square** (1:00 to 1:04)

- Reachy A: Ping-pong: snaps to a new corner of a square on counts 1 and 3, holding while B answers. Unison with B on 5 to 8. (library: `jackson_square, grid_snap`)
- Dancer: Counts 1 to 4: your head ticks to whichever robot just moved. Counts 5 to 8: robot arm hits with both of them.
- Reachy B: Answers on counts 2 and 4, then unison. (library: `jackson_square, grid_snap`)

**17. The wave** (1:04 to 1:08)

- Reachy A: Starts the wave on 1, catches it back on 8. (library: `custom wave`)
- Dancer: The wave crosses your arms toward B on 2 and 3, then back toward A on 6 and 7.
- Reachy B: Catches the wave on 4 and sends it back on 5. (library: `custom wave`)

**18. Everybody** (1:08 to 1:12)

- Reachy A: Head-bangs on 1 to 4, then robot-square hits on 5 to 8, all in unison with you. (library: `headbanger_combo, then grid_snap`)
- Dancer: Running man on 1 to 4, robot arm hits on 5 to 8.
- Reachy B: Same as A. (library: `headbanger_combo, then grid_snap`)

**19. Full power** (1:12 to 1:16)

- Reachy A: Celebrates on 1 to 4, then leans in toward you, eyes bright, antennas high. (library: `enthusiastic1, then loving1`)
- Dancer: Jump with arms up on 1 and 3. On 5, snap into a power pose: one arm straight up, other hand on hip. Hold.
- Reachy B: Same as A. (library: `enthusiastic2, then loving1`)
