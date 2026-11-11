// The one master clock: Web Audio time. Robots, lights (and later the coach, pictograms and scoring) all read
// showTime() from here, so what you see stays locked to what you hear.
//
// Music: your own 120 BPM track goes in public/music/encendido.(mp3|m4a|wav|ogg). Until it exists we render a
// simple beat (kick on every count, hats on the off-beats, a clap on 2 4 6 8, a bell on each phrase's count 1)
// with an OfflineAudioContext: synthesized, not a recording, so there is nothing to license.
const BEAT = 0.5, PRE = 8;                        // 120 BPM; 8 counts of count-in before show time 0

async function renderBeat(ctx: BaseAudioContext, seconds: number): Promise<AudioBuffer> {
  const sr = 44100, off = new OfflineAudioContext(2, Math.ceil((seconds + PRE * BEAT) * sr), sr);
  const out = off.createGain(); out.gain.value = 0.8; out.connect(off.destination);
  const noise = off.createBuffer(1, sr, sr); const nd = noise.getChannelData(0);
  for (let i = 0; i < nd.length; i++) nd[i] = Math.random() * 2 - 1;
  const at = (k: number) => (k + PRE) * BEAT;      // count k (negative = count-in) to buffer time
  const kick = (t: number, g: number) => {
    const o = off.createOscillator(), a = off.createGain();
    o.frequency.setValueAtTime(140, t); o.frequency.exponentialRampToValueAtTime(45, t + 0.12);
    a.gain.setValueAtTime(g, t); a.gain.exponentialRampToValueAtTime(0.001, t + 0.25);
    o.connect(a).connect(out); o.start(t); o.stop(t + 0.3);
  };
  const hiss = (t: number, g: number, len: number, hp: number) => {
    const s = off.createBufferSource(), f = off.createBiquadFilter(), a = off.createGain();
    s.buffer = noise; f.type = "highpass"; f.frequency.value = hp;
    a.gain.setValueAtTime(g, t); a.gain.exponentialRampToValueAtTime(0.001, t + len);
    s.connect(f).connect(a).connect(out); s.start(t, Math.random() * 0.5, len + 0.05);
  };
  const bell = (t: number, f0: number, g: number) => {
    const o = off.createOscillator(), a = off.createGain(); o.type = "triangle"; o.frequency.value = f0;
    a.gain.setValueAtTime(g, t); a.gain.exponentialRampToValueAtTime(0.001, t + 0.6);
    o.connect(a).connect(out); o.start(t); o.stop(t + 0.7);
  };
  for (let k = -PRE; k < seconds / BEAT; k++) {
    const t = at(k);
    if (k < 0) { bell(t, k === -PRE || k === -4 ? 1320 : 880, 0.25); continue; }   // count-in: clicks only
    kick(t, k % 8 === 0 ? 0.9 : 0.6);
    hiss(t + BEAT / 2, 0.12, 0.05, 7000);
    if (k % 2 === 1) hiss(t, 0.35, 0.12, 1500);
    if (k % 8 === 0) bell(t, 660, 0.18);
  }
  return off.startRendering();
}

// 16-bit PCM WAV of a buffer, so slowed-down practice can play it through an <audio> element (pitch kept).
function wavBlob(b: AudioBuffer): Blob {
  const ch = b.numberOfChannels, n = b.length, bytes = 44 + n * ch * 2, v = new DataView(new ArrayBuffer(bytes));
  const str = (o: number, s: string) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
  str(0, "RIFF"); v.setUint32(4, bytes - 8, true); str(8, "WAVEfmt "); v.setUint32(16, 16, true); v.setUint16(20, 1, true);
  v.setUint16(22, ch, true); v.setUint32(24, b.sampleRate, true); v.setUint32(28, b.sampleRate * ch * 2, true); v.setUint16(32, ch * 2, true);
  v.setUint16(34, 16, true); str(36, "data"); v.setUint32(40, n * ch * 2, true);
  const data = Array.from({ length: ch }, (_, c) => b.getChannelData(c));
  for (let i = 0, o = 44; i < n; i++) for (let c = 0; c < ch; c++, o += 2) v.setInt16(o, Math.max(-1, Math.min(1, data[c][i])) * 0x7fff, true);
  return new Blob([v.buffer], { type: "audio/wav" });
}

export class ShowClock {
  readonly ctx = new AudioContext({ latencyHint: "interactive" });
  private buffer: AudioBuffer | null = null;
  private src: AudioBufferSourceNode | null = null;
  private t0 = 0;                                  // context time at show time 0
  private held = -PRE * BEAT;                      // show time while paused
  rate = 1;                                        // practice speed: 1, 0.75 or 0.5
  avOffsetMs = (() => { try { return Number(localStorage.getItem("reachoreo.avOffsetMs")) || 0; } catch { return 0; } })();   // from the tap test
  playing = false;
  // At 1x the music is an AudioBufferSourceNode (sample-accurate). Slowed down, an <audio> element plays it with
  // preservesPitch, so the song gets slower without dropping in pitch.
  private media: HTMLAudioElement | null = null;
  private anchor = { perf: 0, show: 0 };
  source = "beat";

  constructor(readonly duration: number) {}

  async load() {
    for (const ext of ["mp3", "m4a", "wav", "ogg"]) {
      try {
        const r = await fetch(`${import.meta.env.BASE_URL}music/encendido.${ext}`);
        if (r.ok && (r.headers.get("content-type") || "").match(/audio|octet/)) {
          this.buffer = await this.ctx.decodeAudioData(await r.arrayBuffer()); this.source = `your track (encendido.${ext})`; return;
        }
      } catch { /* try the next one */ }
    }
    this.buffer = await renderBeat(this.ctx, this.duration + 2);
  }

  /** Show time now, as heard: corrected for the output latency, so visuals match the speakers. */
  showTime(): number {
    if (!this.playing) return this.held;
    if (this.media && this.rate !== 1) {
      const predicted = this.anchor.show + (performance.now() - this.anchor.perf) / 1000 * this.rate;
      const actual = this.media.currentTime - PRE * BEAT;
      if (Math.abs(actual - predicted) > 0.04) { this.anchor = { perf: performance.now(), show: actual }; return actual - this.avOffsetMs / 1000; }
      return predicted - this.avOffsetMs / 1000;
    }
    const ts = this.ctx.getOutputTimestamp?.();
    const heard = ts && ts.contextTime !== undefined && ts.performanceTime !== undefined
      ? ts.contextTime + (performance.now() - ts.performanceTime) / 1000 : this.ctx.currentTime - (this.ctx.outputLatency || 0);
    return (heard - this.t0) * this.rate - this.avOffsetMs / 1000;
  }

  async play(from = this.held) {
    if (!this.buffer) await this.load();
    await this.ctx.resume();
    this.stopSource();
    from = Math.max(from, -PRE * BEAT);
    if (this.rate !== 1) {                         // slowed practice: the <audio> element, pitch preserved
      await this.prepareSlow();
      this.media!.playbackRate = this.rate; this.media!.currentTime = from + PRE * BEAT;
      await this.media!.play();
      this.anchor = { perf: performance.now(), show: from }; this.playing = true;
      return;
    }
    const start = this.ctx.currentTime + 0.08;     // schedule slightly ahead: sample-accurate start
    const offset = Math.max(0, from + PRE * BEAT);  // the buffer begins with the count-in
    this.src = this.ctx.createBufferSource(); this.src.buffer = this.buffer; this.src.playbackRate.value = this.rate;
    this.src.connect(this.ctx.destination); this.src.start(start, offset);
    this.t0 = start - from / this.rate;
    this.playing = true;
  }

  pause() { this.held = this.showTime(); this.playing = false; this.stopSource(); }
  seek(t: number) { const was = this.playing; this.held = t; if (was) this.play(t); }
  private stopSource() {
    try { this.src?.stop(); } catch { /* already stopped */ }
    this.src = null; this.media?.pause();
  }
  /** The tap test: you tap along to 16 clicks; the median of (tap - when the click reached your ears) is how much
   *  later you hear (and react to) the music than the page thinks. Saved, and applied to showTime(). */
  async tapTest(onTick: (n: number, total: number) => void, getTaps: () => number[]): Promise<number | null> {
    await this.ctx.resume();
    const N = 16, start = this.ctx.currentTime + 0.6, lat = (this.ctx.outputLatency || 0) + (this.ctx.baseLatency || 0);
    for (let i = 0; i < N; i++) {
      const o = this.ctx.createOscillator(), g = this.ctx.createGain(), t = start + i * BEAT;
      o.frequency.value = i % 4 ? 880 : 1320; g.gain.setValueAtTime(0.3, t); g.gain.exponentialRampToValueAtTime(0.001, t + 0.07);
      o.connect(g).connect(this.ctx.destination); o.start(t); o.stop(t + 0.08);
    }
    const perfAtStart = performance.now() + (start - this.ctx.currentTime + lat) * 1000;   // when the first click is heard
    for (let i = 0; i < N; i++) { onTick(i + 1, N); await new Promise(r => setTimeout(r, BEAT * 1000)); }
    await new Promise(r => setTimeout(r, 700));
    const offs = getTaps().map(tp => { const k = Math.round((tp - perfAtStart) / (BEAT * 1000)); return k >= 2 && k < N ? tp - perfAtStart - k * BEAT * 1000 : null; })
      .filter((v): v is number => v != null).sort((a, b) => a - b);
    if (offs.length < 6) return null;
    this.avOffsetMs = Math.round(offs[offs.length >> 1]);
    try { localStorage.setItem("reachoreo.avOffsetMs", String(this.avOffsetMs)); } catch { /* private mode */ }
    return this.avOffsetMs;
  }

  /** Builds the slowed-practice player ahead of time, so pressing Play starts at once (browsers only allow audio
   *  to start straight from a click). */
  async prepareSlow() {
    if (this.media) return;
    if (!this.buffer) await this.load();
    const m = new Audio(URL.createObjectURL(wavBlob(this.buffer!)));
    m.preservesPitch = true; m.preload = "auto";
    await new Promise(r => m.addEventListener("canplaythrough", r, { once: true }));
    this.media = m;
  }
  /** Change the practice speed; keeps the current spot. */
  async setRate(r: number) {
    const t = this.showTime(), was = this.playing; this.pause(); this.rate = r; this.held = t;
    if (r !== 1) await this.prepareSlow();
    if (was) await this.play(t);
  }
}
