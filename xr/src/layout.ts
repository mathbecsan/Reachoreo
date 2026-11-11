// The room, in metres. x: the audience's right, y: up, z: toward the audience (the camera). Origin: floor, under the
// middle of the counter's front edge. Your measurements of the SRC kitchen replace these numbers; nothing else changes.
export const LAYOUT = {
  counter: { length: 3.6, height: 0.9, depth: 0.6, frontZ: 0 },
  robots: { A: { x: -1.25 }, B: { x: 1.25 }, z: -0.22 },     // on the counter, a little behind its front edge
  dancer: { z: 1.2 },                                          // where you dance, in front of the counter
  room: { width: 7, depth: 6, height: 2.7, backZ: -1.1 },
  window: { x: -1.9, y: 1.55, w: 1.1, h: 0.85 },               // on the back wall, left of the counter
  lamp: { x: 0, y: 2.15, z: -0.1 },                            // pendant over the middle
  cabinets: { xs: [0.75, 1.25, 1.75], y: 1.75, w: 0.46, h: 0.7, depth: 0.35 },
  // The 2D preview is 1600 px wide with the robots 880 px apart: stage px -> metres
  pxToM: 2.5 / 880,
};
