// Plays a library song in step with the conductor's show clock (show time 0 = the song's first downbeat).
// Small drift is absorbed by nudging the playback rate; big jumps (start, seek, resume) re-seek.
export class SongSync {
  constructor(audio) {
    this.audio = audio; this.downbeat = 0; this.enabled = true; this.blocked = false;
    this.outputLatency = () => 0;      // seconds between "playing" and heard (speakers, Bluetooth): set by the page
    try { this.offsetMs = +localStorage.getItem("reachy.musicOffsetMs") || 0; } catch { this.offsetMs = 0; }
  }
  setOffset(ms) { this.offsetMs = ms; try { localStorage.setItem("reachy.musicOffsetMs", String(ms)); } catch {} }
  load(url, downbeat) {
    this.downbeat = downbeat || 0;
    if (!url) { this.audio.removeAttribute("src"); this.audio.load(); return; }
    if (this.audio.dataset.url !== url) { this.audio.dataset.url = url; this.audio.src = url; this.audio.load(); }
  }
  // state: the clock state; showT: the page's estimate of show time now.
  update(state, showT) {
    const a = this.audio;
    if (!a.src || !this.enabled) { if (!a.paused) a.pause(); return; }
    const running = state === "playing" || state === "countdown";
    // play ahead by the output delay, so what you HEAR lands on the show clock (and on the robots' moves)
    const target = this.downbeat + showT + this.offsetMs / 1000 + this.outputLatency();
    if (!running || target < 0 || (a.duration && target >= a.duration)) { if (!a.paused) a.pause(); a.playbackRate = 1; return; }
    if (a.paused) {
      if (this.pending || performance.now() - (this.lastTry || 0) < 1000) return;   // one attempt a second while blocked
      this.lastTry = performance.now(); this.pending = true;
      a.currentTime = target;
      a.play().then(() => { this.blocked = false; }).catch(() => { this.blocked = true; }).finally(() => { this.pending = false; });
      return;
    }
    const drift = a.currentTime - target;
    if (Math.abs(drift) > 0.15) { a.currentTime = target; a.playbackRate = 1; }
    else a.playbackRate = Math.abs(drift) > 0.02 ? 1 - Math.max(-0.05, Math.min(0.05, drift * 0.8)) : 1;
  }
}
