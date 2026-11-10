// Listens to a song and finds its beat: tempo, where bar 1 lands, and how loud each 8-count phrase is.
// Pure functions on a Float32Array (no DOM), so tests/test_music_js.py runs them in node on synthetic tracks.

const TARGET_SR = 11025, NFFT = 1024, HOP = 128;
// An attack shows up in the flux as soon as it enters the analysis window, before the frame's start time
// catches up: frame time + this = when the beat is heard (measured on drum tracks, tests/test_music_js.py).
const ONSET_DELAY_S = 0.078;

export function toMono(buffer) {
  const n = buffer.length, ch = buffer.numberOfChannels, out = new Float32Array(n);
  for (let c = 0; c < ch; c++) { const d = buffer.getChannelData(c); for (let i = 0; i < n; i++) out[i] += d[i] / ch; }
  return out;
}

function downsample(x, sr) {
  const f = Math.max(1, Math.round(sr / TARGET_SR)), n = Math.floor(x.length / f), y = new Float32Array(n);
  for (let i = 0; i < n; i++) { let s = 0; for (let k = 0; k < f; k++) s += x[i * f + k]; y[i] = s / f; }
  return { y, sr: sr / f };
}

// In-place radix-2 FFT on (re, im).
function makeFFT(n) {
  const rev = new Uint32Array(n), bits = Math.log2(n);
  for (let i = 0; i < n; i++) { let r = 0; for (let b = 0; b < bits; b++) r |= ((i >> b) & 1) << (bits - 1 - b); rev[i] = r; }
  const cos = new Float32Array(n / 2), sin = new Float32Array(n / 2);
  for (let i = 0; i < n / 2; i++) { cos[i] = Math.cos(-2 * Math.PI * i / n); sin[i] = Math.sin(-2 * Math.PI * i / n); }
  return (re, im) => {
    for (let i = 0; i < n; i++) { const j = rev[i]; if (j > i) { let t = re[i]; re[i] = re[j]; re[j] = t; t = im[i]; im[i] = im[j]; im[j] = t; } }
    for (let size = 2; size <= n; size <<= 1) {
      const half = size >> 1, step = n / size;
      for (let s = 0; s < n; s += size) for (let k = 0; k < half; k++) {
        const a = s + k, b = a + half, wr = cos[k * step], wi = sin[k * step];
        const tr = re[b] * wr - im[b] * wi, ti = re[b] * wi + im[b] * wr;
        re[b] = re[a] - tr; im[b] = im[a] - ti; re[a] += tr; im[a] += ti;
      }
    }
  };
}

// Onset strength (spectral flux), its bass-only version (kick drums mark bar 1), and loudness, one value per hop.
export function features(x, sr) {
  const { y, sr: fs } = downsample(x, sr);
  const frames = Math.max(0, Math.floor((y.length - NFFT) / HOP) + 1);
  const fft = makeFFT(NFFT), win = new Float32Array(NFFT);
  for (let i = 0; i < NFFT; i++) win[i] = 0.5 - 0.5 * Math.cos(2 * Math.PI * i / NFFT);
  const bins = NFFT / 2, bassBins = Math.max(2, Math.round(160 / (fs / NFFT)));
  const flux = new Float32Array(frames), bass = new Float32Array(frames), rms = new Float32Array(frames);
  // timbre: 8 log-spaced bands (60 Hz to 5 kHz) per frame, for telling verse from chorus
  const NB = 8, edges = Array.from({ length: NB + 1 }, (_, i) => Math.max(1, Math.round(60 * Math.pow(5000 / 60, i / NB) / (fs / NFFT))));
  const bands = new Float32Array(frames * NB);
  let prev = new Float32Array(bins), cur = new Float32Array(bins);
  const re = new Float32Array(NFFT), im = new Float32Array(NFFT);
  for (let f = 0; f < frames; f++) {
    let e = 0;
    for (let i = 0; i < NFFT; i++) { const v = y[f * HOP + i]; re[i] = v * win[i]; im[i] = 0; e += v * v; }
    rms[f] = Math.sqrt(e / NFFT);
    fft(re, im);
    let s = 0, sb = 0;
    for (let k = 1; k < bins; k++) {
      cur[k] = Math.log1p(100 * Math.hypot(re[k], im[k]));
      const d = cur[k] - prev[k];
      if (d > 0) { s += d; if (k <= bassBins) sb += d; }
    }
    flux[f] = s; bass[f] = sb;
    for (let bnd = 0; bnd < NB; bnd++) { let m = 0; for (let k = edges[bnd]; k < Math.min(bins, edges[bnd + 1] + 1); k++) m += cur[k]; bands[f * NB + bnd] = m / Math.max(1, edges[bnd + 1] - edges[bnd] + 1); }
    const t = prev; prev = cur; cur = t;
  }
  return { fps: fs / HOP, flux: whiten(flux, fs / HOP), bass: whiten(bass, fs / HOP), rms, frames, duration: x.length / sr, bands, NB };
}

// Subtract a moving average (about half a second) and keep what sticks out: the attacks.
function whiten(v, fps) {
  const w = Math.max(1, Math.round(fps * 0.25)), out = new Float32Array(v.length);
  let acc = 0; const pre = new Float64Array(v.length + 1);
  for (let i = 0; i < v.length; i++) { acc += v[i]; pre[i + 1] = acc; }
  let mx = 1e-9;
  for (let i = 0; i < v.length; i++) {
    const a = Math.max(0, i - w), b = Math.min(v.length, i + w + 1), m = (pre[b] - pre[a]) / (b - a);
    out[i] = Math.max(0, v[i] - m); mx = Math.max(mx, out[i]);
  }
  for (let i = 0; i < out.length; i++) out[i] /= mx;
  return out;
}

const at = (v, x) => { const i = Math.floor(x); if (i < 0 || i + 1 >= v.length) return 0; const f = x - i; return v[i] * (1 - f) + v[i + 1] * f; };

// How well a beat grid of this period and phase lines up with the onsets.
function comb(env, period, phase) {
  let s = 0, n = 0;
  for (let x = phase; x < env.length - 1; x += period) { s += Math.max(at(env, x - 1), at(env, x), at(env, x + 1)); n++; }
  return n ? s / n : 0;
}

export function tempo(F, lo = 60, hi = 200) {
  const env = F.flux, fps = F.fps;
  const lagMin = Math.floor(60 * fps / hi), lagMax = Math.ceil(60 * fps / lo);
  const ac = new Float32Array(lagMax * 2 + 2);
  for (let L = 1; L < ac.length; L++) { let s = 0; for (let i = 0; i + L < env.length; i++) s += env[i] * env[i + L]; ac[L] = s / (env.length - L); }
  let best = null;
  for (let L = lagMin; L <= lagMax; L++) {
    const bpm = 60 * fps / L, prior = Math.exp(-0.5 * (Math.log2(bpm / 118) / 0.75) ** 2);
    const score = (ac[L] + 0.5 * at(ac, 2 * L) + 0.25 * at(ac, L / 2)) * prior;
    if (!best || score > best.score) best = { L, score };
  }
  // Refine the period and find the phase together, over the whole song, so long tracks don't drift off the grid.
  let fine = null;
  const L0 = best.L;
  for (let L = L0 * 0.985; L <= L0 * 1.015; L += L0 * 0.0005) {
    for (let ph = 0; ph < L; ph += 0.5) {
      const s = comb(env, L, ph);
      if (!fine || s > fine.s) fine = { L, ph, s };
    }
  }
  const mean = env.reduce((a, b) => a + b, 0) / env.length || 1e-9;
  return { bpm: 60 * fps / fine.L, period: fine.L, phase: fine.ph, confidence: Math.min(1, (fine.s / mean - 1) / 4) };
}

// Follows the actual beats, not a fixed grid: live bands and older records drift by a few BPM over a song,
// which pulls a fixed grid half a beat off within a minute. Dynamic programming (Ellis 2007): each beat is the
// best onset that sits about one period after the previous beat. Returns fractional frame positions.
// Two candidates: the song's average tempo held tightly (best for drummers who swing around a steady beat) and
// a tempo curve that bends (best for songs that really speed up). Keep whichever sits on the onsets better.
export function trackBeats(F, period, tightness = 3000) {   // tuned on a live-band track: 3 ms median from the drum hits
  const n = F.frames, O = new Float32Array(n);
  for (let i = 0; i < n; i++) O[i] = F.flux[i] + 0.5 * F.bass[i];
  const steady = trackWith(O, new Float32Array(n).fill(period), period, tightness);
  const bending = trackWith(O, localPeriods(O, period, F.fps), period, tightness);
  const fitness = fr => { let s = 0; for (const f of fr) { const i = Math.round(f); s += Math.max(O[i - 1] || 0, O[i] || 0, O[i + 1] || 0); } return s / Math.max(1, fr.length); };
  return fitness(bending) > 1.08 * fitness(steady) ? bending : steady;
}

function trackWith(O, P, period, tightness) {
  const n = O.length;
  const score = new Float32Array(n), back = new Int32Array(n).fill(-1);
  for (let t = 0; t < n; t++) {
    const pt = P[t], lo = Math.round(pt / 2), hi = Math.round(pt * 2);
    let best = 0, arg = -1;
    for (let d = lo; d <= hi && t - d >= 0; d++) { const v = score[t - d] - tightness * Math.log(d / pt) ** 2; if (v > best || arg < 0) { best = v; arg = t - d; } }
    score[t] = O[t] + Math.max(0, best); back[t] = best > 0 ? arg : -1;
  }
  // end on the best-scoring frame in the last period, then walk back
  let t = n - 1, top = -Infinity;
  for (let i = Math.max(0, n - Math.round(period)); i < n; i++) if (score[i] > top) { top = score[i]; t = i; }
  const out = [];
  while (t >= 0) { out.push(t); t = back[t]; }
  out.reverse();
  // the chain can start late: extend it backwards over the intro on the same period
  while (out[0] - P[Math.max(0, Math.round(out[0]))] > 0) {
    const pp = P[Math.max(0, Math.round(out[0]))], g = out[0] - pp; let bi = Math.round(g), bv = -1;
    for (let i = Math.round(g - pp * 0.1); i <= Math.round(g + pp * 0.1); i++) if (i >= 0 && O[i] > bv) { bv = O[i]; bi = i; }
    out.unshift(bv > 0.05 ? bi : g);
  }
  // sub-frame peak: parabola through the neighbours
  return out.map(i => { const k = Math.round(i), a = O[k - 1] ?? 0, b = O[k], c = O[k + 1] ?? 0, den = a - 2 * b + c; return Number.isInteger(i) && den < 0 ? k + Math.max(-0.5, Math.min(0.5, 0.5 * (a - c) / den)) : i; });
}

// The beat period (frames) at every frame: autocorrelation in 8 s windows, within 10% of the song's tempo,
// smoothed, so a song that speeds up or slows down is followed without letting one weak window wander.
export function localPeriods(O, period, fps) {
  const n = O.length, win = Math.round(8 * fps), hop = Math.round(2 * fps), centres = [], vals = [];
  for (let c = Math.floor(win / 2); c < n; c += hop) {
    const a = Math.max(0, c - (win >> 1)), b = Math.min(n, c + (win >> 1));
    let best = null;
    for (let L = Math.floor(period * 0.9); L <= Math.ceil(period * 1.1); L++) {
      let s = 0; for (let i = a; i + L < b; i++) s += O[i] * O[i + L];
      if (!best || s > best.s) best = { L, s, prev: best };
    }
    // parabolic refinement around the best lag
    const ac = L => { let s = 0; for (let i = a; i + L < b; i++) s += O[i] * O[i + L]; return s; };
    const y0 = ac(best.L - 1), y1 = best.s, y2 = ac(best.L + 1), den = y0 - 2 * y1 + y2;
    centres.push(c); vals.push(den < 0 ? best.L + 0.5 * (y0 - y2) / den : best.L);
  }
  if (!vals.length) return new Float32Array(n).fill(period);
  const sm = vals.map((_, i) => { const w = vals.slice(Math.max(0, i - 2), i + 3).sort((p, q) => p - q); return w[w.length >> 1]; });   // median of 5
  const out = new Float32Array(n);
  for (let t = 0, j = 0; t < n; t++) {
    while (j + 1 < centres.length && centres[j + 1] <= t) j++;
    if (t <= centres[0]) out[t] = sm[0];
    else if (j + 1 >= centres.length) out[t] = sm[sm.length - 1];
    else { const f = (t - centres[j]) / (centres[j + 1] - centres[j]); out[t] = sm[j] + f * (sm[j + 1] - sm[j]); }
  }
  return out;
}

// Which beat starts phrase 1. Kicks usually land on 1 and 3 (bass on the "strong" half of the bar); which strong
// beat starts the phrase comes from where the music changes most (the 8-count phrase lines).
export function downbeatIndex(F, beatFrames, beatsPerCount = 1) {
  const nB = beatFrames.length;
  const peakNear = (v, x) => { const i = Math.round(x); let m = 0; for (let d = -2; d <= 2; d++) m = Math.max(m, v[i + d] || 0); return m; };
  const kick = [0, 0, 0, 0], cnt = [0, 0, 0, 0];
  for (let k = 0; k < nB; k++) { kick[k % 4] += peakNear(F.bass, beatFrames[k]); cnt[k % 4]++; }
  for (let m = 0; m < 4; m++) kick[m] /= cnt[m] || 1;
  const cls = kick[0] + kick[2] >= kick[1] + kick[3] ? 0 : 1;
  const phraseBeats = Math.max(4, Math.round(8 * beatsPerCount)), options = [];
  for (let o = cls; o < phraseBeats; o += 2) options.push(o);
  options.sort((a, b) => kick[b % 4] - kick[a % 4]);
  const loud = k => { const a = Math.floor(beatFrames[k]), b = Math.floor(beatFrames[Math.min(nB - 1, k + phraseBeats)]); let s = 0, n = 0; for (let i = Math.max(0, a); i < Math.min(F.frames, b); i++) { s += F.rms[i]; n++; } return n ? s / n : 0; };
  let pick = null;
  for (const o of options) {
    let s = 0;
    for (let k = o + phraseBeats; k + phraseBeats < nB; k += phraseBeats) s += (loud(k) - loud(k - phraseBeats)) ** 2;      // squared: a sharp change on the line beats two half-changes around it
    if (!pick || s > pick.s * 1.1) pick = { o, s };
  }
  return pick.o;
}

// Beat indices where the kick moves to the other half of the bar and stays there (strong evidence only).
export function strongBeatFlips(F, frames, k0, win = 8, need = 3, thresh = 0.3) {
  const peakNear = (v, x) => { const i = Math.round(x); let m = 0; for (let d = -2; d <= 2; d++) m = Math.max(m, v[i + d] || 0); return m; };
  const ev = [];                    // + = kick on the counted beats, - = on the others, per window of `win` beats
  for (let w = k0; w + win <= frames.length; w += win) {
    let a = 0, b = 0; for (let k = w; k < w + win; k++) ((k - k0) % 2 === 0 ? (a += peakNear(F.bass, frames[k])) : (b += peakNear(F.bass, frames[k])));
    ev.push(a + b > 0 ? (a - b) / (a + b) : 0);
  }
  const out = []; let sign = 1;
  for (let i = 0; i + need <= ev.length; i++) {
    if (ev.slice(i, i + need).every(e => sign * e < -thresh)) { out.push(k0 + i * win + out.length); sign = -sign; i += need - 1; }
  }
  return out;
}

// Loudness and busyness of each 8-count phrase, from the count times, 0..1 relative to the song's loudest.
export function phraseEnergy(F, countTimes) {
  const out = [];
  for (let i = 0; 8 * i + 8 < countTimes.length; i++) {
    const a = Math.max(0, Math.floor(countTimes[8 * i] * F.fps)), b = Math.min(F.frames, Math.floor(countTimes[8 * i + 8] * F.fps));
    let r = 0, f = 0; for (let k = a; k < b; k++) { r += F.rms[k]; f += F.flux[k]; }
    out.push(b > a ? { r: r / (b - a), f: f / (b - a) } : { r: 0, f: 0 });
  }
  const rm = Math.max(1e-9, ...out.map(o => o.r)), fm = Math.max(1e-9, ...out.map(o => o.f));
  let e = out.map(o => 0.7 * o.r / rm + 0.3 * o.f / fm);
  while (e.length > 2 && e[e.length - 1] < 0.08) e.pop();       // a silent tail is not a phrase
  return e.map(v => +v.toFixed(3));
}

// The song's structure: phrases that sound alike get the same letter (intro A, verse B, chorus C, verse B...).
// Each phrase is described by its average timbre (8 bands), loudness and busyness, normalised across the song,
// then grouped: a phrase joins the closest group if it is close enough, else starts a new one.
export function structure(F, countTimes, maxGroups = 6) {
  const n = Math.floor((countTimes.length - 1) / 8), NB = F.NB, vec = [];
  for (let i = 0; i < n; i++) {
    const a = Math.max(0, Math.floor(countTimes[8 * i] * F.fps)), b = Math.min(F.frames, Math.floor(countTimes[8 * i + 8] * F.fps));
    const v = new Array(NB + 2).fill(0), m = Math.max(1, b - a);
    for (let f = a; f < b; f++) { for (let k = 0; k < NB; k++) v[k] += F.bands[f * NB + k]; v[NB] += F.rms[f]; v[NB + 1] += F.flux[f]; }
    vec.push(v.map(x => x / m));
  }
  if (n < 3) return vec.map(() => "A");
  for (let d = 0; d < NB + 2; d++) {             // z-score each dimension, loudness counted twice as much as one band
    const col = vec.map(v => v[d]), mu = col.reduce((p, q) => p + q, 0) / n, sd = Math.sqrt(col.reduce((p, q) => p + (q - mu) ** 2, 0) / n) || 1;
    const w = d >= NB ? 1.4 : 1;
    vec.forEach(v => { v[d] = w * (v[d] - mu) / sd; });
  }
  const dist = (p, q) => Math.sqrt(p.reduce((s2, x, k) => s2 + (x - q[k]) ** 2, 0));
  const all = []; for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) all.push(dist(vec[i], vec[j]));
  all.sort((p, q) => p - q);
  let thr = 0.5 * all[Math.floor(all.length / 2)], labels;
  for (let tries = 0; tries < 12; tries++) {
    const cent = [], members = [];
    labels = vec.map(v => {
      let best = -1, bd = Infinity;
      cent.forEach((c, k) => { const d = dist(v, c); if (d < bd) { bd = d; best = k; } });
      if (best < 0 || bd > thr) { cent.push([...v]); members.push(1); return cent.length - 1; }
      members[best]++; cent[best] = cent[best].map((x, k) => x + (v[k] - x) / members[best]);
      return best;
    });
    // refine like k-means: recompute each group's centre, move every phrase to its nearest centre
    for (let it = 0; it < 4; it++) {
      const sums = cent.map(() => new Array(NB + 2).fill(0)), cnt = cent.map(() => 0);
      labels.forEach((l, i) => { cnt[l]++; vec[i].forEach((x, k) => sums[l][k] += x); });
      sums.forEach((sv, l) => { if (cnt[l]) cent[l] = sv.map(x => x / cnt[l]); });
      labels = vec.map(v => { let best = 0, bd = Infinity; cent.forEach((c, k) => { if (!cnt[k]) return; const d = dist(v, c); if (d < bd) { bd = d; best = k; } }); return best; });
    }
    // a group of one phrase is a fill or a transition: give it to the nearest group if it isn't far off
    const sizes = {}; labels.forEach(l => sizes[l] = (sizes[l] || 0) + 1);
    labels = labels.map((l, i) => {
      if (sizes[l] > 1 || i === 0 || i === n - 1) return l;
      let best = l, bd = Infinity; cent.forEach((c, k) => { if (k === l || !sizes[k]) return; const d = dist(vec[i], c); if (d < bd) { bd = d; best = k; } });
      return bd < 1.6 * thr ? best : l;
    });
    // a lone phrase between two of the same group is usually a fill, not a new section
    for (let i = 1; i + 1 < n; i++) if (labels[i - 1] === labels[i + 1] && labels[i] !== labels[i - 1] && dist(vec[i], cent[labels[i - 1]]) < 1.4 * thr) labels[i] = labels[i - 1];
    if (new Set(labels).size <= maxGroups) break;
    thr *= 1.15;
  }
  const order = []; labels.forEach(l => { if (!order.includes(l)) order.push(l); });
  return labels.map(l => String.fromCharCode(65 + order.indexOf(l)));
}

// Where the music hits inside each phrase: onset strength (drums, guitar stabs) on each of its 16 half-counts.
// The generator lines move pieces up with these, so steps land where the song accents, not just on the count.
export function phraseAccents(F, countTimes) {
  const out = [], win = [Math.round(-0.03 * F.fps), Math.round(0.05 * F.fps)];
  const hit = t => { const c = Math.round((t - ONSET_DELAY_S) * F.fps); let m = 0; for (let i = c + win[0]; i <= c + win[1]; i++) m = Math.max(m, (F.flux[i] || 0) + 0.7 * (F.bass[i] || 0)); return m; };
  for (let i = 0; 8 * i + 8 < countTimes.length; i++) {
    const row = [];
    for (let k = 0; k < 8; k++) { const a = countTimes[8 * i + k], b = countTimes[8 * i + k + 1]; row.push(+hit(a).toFixed(3), +hit((a + b) / 2).toFixed(3)); }
    out.push(row);
  }
  return out;
}

export const countsFor = bpm => bpm > 145 ? 2 : bpm < 73 ? 0.5 : 1;      // same rule as library.count_tempo

// Everything the Create page needs. beats[] are seconds; firstDownbeat is where count 1 of phrase 1 lands.
export function analyze(x, sr) {
  const F = features(x, sr);
  const T = tempo(F);
  return withTempo(F, T.bpm, null, T);
}

const median = v => { const s = [...v].sort((a, b) => a - b); return s.length ? s[Math.floor(s.length / 2)] : 0; };

// The beat, count and phrase grid for a tempo (and optionally a first downbeat, or a counting choice) the user picked.
// count_times: song seconds of every count from count 1 of phrase 1, one more than 8 × phrases (the end of the last).
export function withTempo(F, bpm, firstDownbeat = null, T0 = null, beatsPerCount = null) {
  const period = 60 * F.fps / bpm;
  const frames = trackBeats(F, period);
  const beats = frames.map(f => f / F.fps + ONSET_DELAY_S);
  const ivs = beats.slice(1).map((b, i) => b - beats[i]);
  const realBpm = beats.length > 8 ? 60 * (beats.length - 1) / (beats[beats.length - 1] - beats[0]) : 60 / median(ivs);   // average over the song, not one quantized interval
  const bpc = beatsPerCount ?? countsFor(realBpm);
  // local tempo, for "tempo varies 158-166" (8-beat windows, outer 10% trimmed)
  const loc = []; for (let i = 0; i + 8 < beats.length; i += 4) loc.push(480 / (beats[i + 8] - beats[i]));
  const ls = [...loc].sort((a, b) => a - b), range = ls.length ? [ls[Math.floor(ls.length * 0.1)], ls[Math.floor(ls.length * 0.9)]] : [realBpm, realBpm];
  const phraseBeats = Math.max(4, Math.round(8 * bpc));
  let k0;
  if (firstDownbeat != null) {
    k0 = 0; for (let k = 1; k < beats.length; k++) if (Math.abs(beats[k] - firstDownbeat) < Math.abs(beats[k0] - firstDownbeat)) k0 = k;
  } else {
    k0 = downbeatIndex(F, frames, bpc);
    // start at the first phrase line where the music has begun (skip leading silence, keep quiet intros)
    const peak = Math.max(1e-9, ...F.rms);
    const quiet = k => { const a = Math.floor(frames[k]), b = Math.floor(frames[Math.min(frames.length - 1, k + phraseBeats)]); let m = 0; for (let i = Math.max(0, a); i < Math.min(F.frames, b); i++) m = Math.max(m, F.rms[i]); return m < 0.05 * peak; };
    while (k0 + phraseBeats < frames.length && quiet(k0)) k0 += phraseBeats;
    while (k0 - phraseBeats >= 0 && !quiet(k0 - phraseBeats)) k0 -= phraseBeats;
  }
  // Counts from the beats: every beat, every other beat (fast songs) or beats and half-beats (slow songs).
  // If the strong beat (the kick) clearly moves to the other beats for 24+ beats, the tracker slipped a beat or the
  // song has an odd bar: re-align so count 1 stays on the kick (that one count lasts a beat longer).
  const flips = strongBeatFlips(F, frames, k0), flips0 = [...flips];
  const counts = [];
  let k = k0, shiftAt = flips.shift();
  while (k < beats.length) {
    if (shiftAt != null && k >= shiftAt) { k++; shiftAt = flips.shift(); if (k >= beats.length) break; }
    counts.push(beats[k]);
    if (bpc <= 0.5 && k + 1 < beats.length) counts.push((beats[k] + beats[k + 1]) / 2);
    k += bpc >= 2 ? 2 : 1;
  }
  const whole = Math.floor((counts.length - 1) / 8);
  const countTimes = counts.slice(0, whole * 8 + 1).map(v => +v.toFixed(4));
  return { bpm: +realBpm.toFixed(2), beat: 60 / realBpm, beats_per_count: bpc, realigned: flips0.length, confidence: T0?.confidence ?? null,
           tempo_range: range.map(v => +v.toFixed(1)), beats, first_downbeat_s: countTimes[0] ?? 0,
           duration_s: +F.duration.toFixed(2), count_times: countTimes, phrase_energy: phraseEnergy(F, countTimes),
           phrase_labels: structure(F, countTimes), phrase_accents: phraseAccents(F, countTimes) };
}

// A compact waveform for drawing: max |amplitude| in `n` buckets.
export function peaks(x, n = 900) {
  const out = new Float32Array(n), step = x.length / n;
  for (let i = 0; i < n; i++) { let m = 0; const a = Math.floor(i * step), b = Math.floor((i + 1) * step); for (let k = a; k < b; k += 4) { const v = Math.abs(x[k]); if (v > m) m = v; } out[i] = m; }
  return out;
}
