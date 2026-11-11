// The bar at the top of every page: where you are, what's loaded, whether the robots are ready, and a
// one-click fix when they aren't. import { mountNav } from "/static/nav.mjs"; mountNav("perform").
const CSS = `
.topnav { position: sticky; top: 0; z-index: 50; display: flex; align-items: center; gap: 6px; padding: 8px 16px;
  background: #0b0a18ee; backdrop-filter: blur(8px); border-bottom: 1px solid #2f2a58; font: 14px/1.3 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #ede9ff; flex-wrap: wrap; }
.topnav .brand { font-weight: 800; letter-spacing: .01em; margin-right: 12px; color: #ede9ff; text-decoration: none; display: flex; align-items: center; gap: 8px; }
.topnav .brand i { display: inline-block; width: 10px; height: 10px; border-radius: 50%; background: #7fe3ff; box-shadow: 14px 0 0 #ffb35c; margin-right: 14px; }
.topnav a.tab { color: #a9a3cc; text-decoration: none; padding: 7px 12px; border-radius: 9px; font-weight: 600; }
.topnav a.tab:hover { color: #ede9ff; background: #211e40; }
.topnav a.tab.on { color: #0d0c1c; background: #ede9ff; }
.topnav a.tab .n { display: inline-grid; place-items: center; width: 18px; height: 18px; border-radius: 50%; font-size: 11px; margin-right: 6px; background: #2f2a58; color: #ede9ff; }
.topnav a.tab.on .n { background: #0d0c1c; color: #ede9ff; }
.topnav .sp { flex: 1; }
.topnav .chip { display: flex; align-items: center; gap: 6px; font-size: 12px; color: #a9a3cc; padding: 5px 10px; border-radius: 99px; background: #17152e; border: 1px solid #2f2a58; white-space: nowrap; }
.topnav .chip b { color: #ede9ff; font-weight: 600; max-width: 180px; overflow: hidden; text-overflow: ellipsis; }
.topnav .dot { width: 8px; height: 8px; border-radius: 50%; background: #ff6b6b; display: inline-block; }
.topnav .dot.on { background: #3ddc84; } .topnav .dot.warn { background: #ffcc4d; }
.topnav button { font: inherit; font-size: 12px; font-weight: 700; color: #06210f; background: #3ddc84; border: 0; border-radius: 99px; padding: 6px 12px; cursor: pointer; }
.topnav button.q { background: #211e40; color: #ede9ff; width: 28px; padding: 6px 0; }
.navtoast { position: fixed; left: 50%; bottom: 24px; transform: translateX(-50%); background: #ede9ff; color: #0d0c1c; padding: 10px 16px; border-radius: 12px;
  font: 600 13px -apple-system, sans-serif; box-shadow: 0 10px 40px #0008; z-index: 100; opacity: 0; transition: opacity .2s; pointer-events: none; max-width: 90vw; }
.navtoast.on { opacity: 1; }
.helpdlg { border: 1px solid #2f2a58; background: #17152e; color: #ede9ff; border-radius: 16px; padding: 22px 26px; max-width: 620px; font: 14px/1.55 -apple-system, sans-serif; }
.helpdlg::backdrop { background: #000a; }
.helpdlg h3 { margin: 0 0 8px; font-size: 18px; } .helpdlg h4 { margin: 16px 0 4px; font-size: 13px; color: #a9a3cc; text-transform: uppercase; letter-spacing: .06em; }
.helpdlg ol { margin: 0; padding-left: 20px; } .helpdlg kbd { background: #2f2a58; border-radius: 5px; padding: 1px 6px; font: 12px ui-monospace, monospace; }
.helpdlg button { margin-top: 14px; font: inherit; background: #ede9ff; color: #0d0c1c; border: 0; border-radius: 9px; padding: 7px 16px; font-weight: 700; cursor: pointer; }
@media (max-width: 900px) { .topnav .chip.robot, .topnav .chip.clock { display: none; } }
`;

const TABS = [["home", "/", "Home"], ["create", "/create", "Make a dance"], ["perform", "/perform", "Rehearse & record"], ["rehearse3d", "/rehearse", "3D / VR"], ["control", "/control", "Control room"]];

export function toast(msg, ms = 3500) {
  let el = document.querySelector(".navtoast");
  if (!el) { el = document.createElement("div"); el.className = "navtoast"; document.body.appendChild(el); }
  el.textContent = msg; el.classList.add("on");
  clearTimeout(el._t); el._t = setTimeout(() => el.classList.remove("on"), ms);
}

export async function post(url, body) {
  try {
    const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
    return await r.json();
  } catch { return { ok: false, msg: "the dashboard server isn't reachable: is python -m reachy_dance.dashboard running?" }; }
}

export async function startEverything(dry = false) {
  toast("Starting the show system…", 8000);
  const r = await post("/api/system", { action: "start", dry_run: dry });
  toast(r.msg || "done", 5000);
  return r;
}

const HELP = `
<h3>How this works</h3>
<ol>
  <li><b>Home</b>: start the robots and choose which dance is loaded.</li>
  <li><b>Make a dance</b>: drop in any song. The page finds the beat and builds a dance for you and both Reachys, then teaches it to the robots.</li>
  <li><b>Rehearse &amp; record</b>: see yourself, both robots and the choreography side by side, with a live sync score. The red button records everything.</li>
  <li><b>Control room</b>: the technical view, with every robot's numbers, alerts and the event log.</li>
</ol>
<h4>Keyboard (rehearsal page)</h4>
<kbd>Space</kbd> start or pause · <kbd>Esc</kbd> stop · <kbd>R</kbd> record or stop recording · <kbd>M</kbd> metronome
<h4>First time, or new robots?</h4>
<a href="/setup" style="color:#7fe3ff">Set up my Reachys</a>: six short steps that find both robots, pair them to left and right, check that they turn the right way, tune their timing and match their head cameras.
<h4>If something says offline</h4>
Press <b>Start everything</b> in the top bar. It starts whatever isn't running yet (each robot's daemon, the conductor and both robot agents) and leaves anything you started in a terminal alone.
<div><button>Got it</button></div>`;

export function mountNav(active) {
  const style = document.createElement("style"); style.textContent = CSS; document.head.appendChild(style);
  const nav = document.createElement("nav"); nav.className = "topnav";
  nav.innerHTML = `<a class="brand" href="/"><i></i>Reachoreo</a>` +
    TABS.map(([k, href, label], i) => `<a class="tab ${k === active ? "on" : ""}" href="${href}">${k === "control" || k === "rehearse3d" ? "" : `<span class="n">${i || "⌂"}</span>`}${label}</a>`).join("").replace('<span class="n">⌂</span>', "") +
    `<span class="sp"></span>
     <span class="chip" title="The dance loaded on the conductor and both robots">Dance <b id="nav-dance">…</b></span>
     <span class="chip clock" title="The conductor keeps the show clock"><span class="dot" id="nav-clock"></span>Clock</span>
     <span class="chip robot" title="Reachy 1, camera's left"><span class="dot" id="nav-A"></span>Reachy 1</span>
     <span class="chip robot" title="Reachy 2, camera's right"><span class="dot" id="nav-B"></span>Reachy 2</span>
     <button id="nav-start" hidden title="Starts whatever isn't running: robot daemons, conductor, robot agents">Start everything</button>
     <button class="q" id="nav-help" title="Help and keyboard shortcuts">?</button>`;
  document.body.prepend(nav);
  const dlg = document.createElement("dialog"); dlg.className = "helpdlg"; dlg.innerHTML = HELP; document.body.appendChild(dlg);
  dlg.querySelector("button").onclick = () => dlg.close();
  nav.querySelector("#nav-help").onclick = () => dlg.showModal();
  nav.querySelector("#nav-start").onclick = () => startEverything();
  const listeners = [];
  async function poll() {
    try {
      const s = await fetch("/api/state").then(r => r.json());
      const set = (id, on, title) => { const d = nav.querySelector(id); d.className = "dot" + (on ? " on" : ""); if (title) d.parentElement.title = title; };
      set("#nav-clock", s.clock.connected);
      for (const side of "AB") {
        const r = s.robots[side], learned = r.connected && r.choreo && s.choreo && r.choreo === s.choreo.name;
        const d = nav.querySelector("#nav-" + side);
        d.className = "dot" + (r.connected ? (learned || !r.choreo ? " on" : " warn") : "");
        d.parentElement.title = !r.connected ? "offline" : learned ? `knows ${s.choreo.title}` : r.choreo ? `still learning (has ${r.choreo})` : r.state;
      }
      nav.querySelector("#nav-dance").textContent = s.choreo?.title || "–";
      nav.querySelector("#nav-start").hidden = s.clock.connected && s.robots.A.connected && s.robots.B.connected;
      listeners.forEach(f => f(s));
    } catch {
      nav.querySelector("#nav-dance").textContent = "server offline";
    }
  }
  poll(); setInterval(poll, 1000);
  return { onState: f => listeners.push(f) };
}
