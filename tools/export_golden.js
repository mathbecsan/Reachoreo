const BPM = 120, BEAT = 0.5, PH = 4, N = 19, DUR = 76;
  const clamp = (x,a=0,b=1) => Math.min(b, Math.max(a, x));
  const ease = x => { x = clamp(x); return x*x*(3-2*x); };
  const lerp = (a,b,k) => a + (b-a)*k;
  const pulse = b => b < 0 ? 0 : Math.exp(-(b % 1) * 6);
  const snap = f => ease(f / 0.16);
  const seq = (arr, bl) => { const c = Math.min(arr.length - 1, Math.floor(bl)), f = bl - c; return lerp(c > 0 ? arr[c-1] : arr[0], arr[c], snap(f)); };
  const bump = (x, c, w) => Math.max(0, 1 - Math.abs(x - c) / w);
  const POS = { L: 360, C: 800, R: 1240 };
  const toward = (fromX, toX) => clamp((toX - fromX) / 600, -1, 1);

  const robot = () => ({ yaw:0, pitch:0, roll:0, body:0, turn:0, antL:0.3, antR:0.3, bob:0, glow:1 });
  const human = () => ({ x:0, depth:0, face:0, drop:0, lean:0, look:0, tilt:0, shrug:0, sit:0, headDown:0, hood:0,
    aL:0.15, eL:0.15, aR:0.15, eR:0.15, fLx:0, fLy:0, fRx:0, fRy:0, rotL:0, rotR:0 });
  const base = () => ({ L:robot(), R:robot(), H:human(), lt:{ L:1, C:1, R:1, M:1, warm:1, party:0, lamp:1 } });

  function asleep(r, u) { r.pitch = -1; r.antL = r.antR = 1.4; r.glow = 0; r.bob = 2*Math.sin(2*Math.PI*u/4); }
  function curled(H, u) {
    H.headDown = 1; H.hood = 1; H.aL = 0.05; H.aR = 0.07; H.eL = H.eR = 0.05;
    H.shrug = -9; H.drop = 14; H.lean = 0.04; H.tilt = 0.14;
  }
  function groove(r, s, bl, amt) {
    const p = pulse(bl), sw = Math.sin(Math.PI*bl/2);
    r.bob += -5*p*amt; r.body += 0.22*sw*amt; r.roll += 0.08*sw*amt;
    r.antL += 0.3*p*amt; r.antR += 0.3*p*amt; r.pitch += 0.08*p*amt;
  }
  function runningMan(H, bl) {
    const cl = Math.cos(Math.PI * bl), liftL = Math.pow(Math.max(0, cl), 1.5), liftR = Math.pow(Math.max(0, -cl), 1.5);
    H.fLy = 90*liftL; H.fRy = 90*liftR; H.fLx = 10*liftL; H.fRx = -10*liftR; H.drop = 14*(1 - Math.abs(cl));
    H.aL = 0.35 + 0.5*liftR; H.aR = 0.35 + 0.5*liftL; H.eL = H.eR = 2.9;
    return { liftL, liftR, cl };
  }
  function steps(H, bl, every, lift) {
    const ph = Math.PI * bl / every, s = Math.sin(ph);
    H.fLy = lift * Math.pow(Math.max(0, s), 2); H.fRy = lift * Math.pow(Math.max(0, -s), 2);
    H.drop = (lift * 0.3) * (1 - Math.abs(s));
  }

  function raw(i, t) {
    const S = base(), A = S.L, B = S.R, H = S.H, lt = S.lt;
    const u = t - i*PH, bl = u / BEAT, p = pulse(bl), c = Math.floor(bl), f = bl - c;
    const hxAbs = () => POS.C + H.x;
    if (i <= 3) { lt.warm = 0; lt.lamp = 0; }
    if (i === 0) {
      asleep(A, u); asleep(B, u); curled(H, u);
      lt.M = 0.45 + 0.15*ease(u/2); lt.C = 0.35; lt.L = lt.R = 0;
    } else if (i === 1) {
      asleep(B, u); B.antR += -0.5*bump(bl, 2.5, 0.4); B.roll = 0.12*bump(bl, 6.4, 0.7); B.bob += -4*bump(bl, 6.4, 0.7);
      curled(H, u); H.tilt = 0.14 - 0.5*bump(bl, 5.4, 0.5);
      A.glow = seq([0,0,0,.7,.15,1,1,1], bl);
      A.pitch = c >= 6 ? -0.55 : lerp(-1, -0.3, ease((bl - 3)/2));
      A.yaw = seq([0,0,0,0,0,-.6,.5,.73], bl); A.body = seq([0,0,0,0,0,-.9,.8,.3], bl);
      A.antL = A.antR = lerp(1.4, 0.5, ease((bl - 3)/3));
      lt.M = 0.6; lt.C = 0.35; lt.L = 0.65*ease((bl - 3)/1); lt.R = 0;
    } else if (i === 2) {
      curled(H, u);
      H.headDown = seq([1,1,1,1,1,.45,.45,1], bl); H.look = seq([0,0,0,0,0,-.4,-.4,0], bl);
      H.tilt = seq([.14,.14,.14,.14,.14,0,0,.14], bl);
      A.glow = 1; A.yaw = seq([.73,.73,.73,1,1,1,.73,.73], bl); A.pitch = seq([-.55,-.6,-.6,-.2,-.2,-.2,-.55,-.55], bl);
      A.roll = seq([.2,.2,.2,0,0,0,.15,.15], bl);
      A.antL = 0.5; A.antR = seq([.5,.9,.9,.4,.4,.4,.5,.5], bl) + (c === 4 || c === 5 ? 0.9*Math.exp(-f*5) : 0);
      B.glow = seq([0,0,0,0,0,1,1,1], bl);
      B.pitch = c < 5 ? -1 : lerp(-1, -0.55, ease((bl - 5)/2)); B.yaw = c >= 7 ? -0.73 : 0;
      B.antL = B.antR = c < 5 ? 1.4 : (c === 6 ? 0.45 + 0.4*Math.sin(4*Math.PI*bl) : 0.6);
      lt.M = 0.65; lt.C = 0.4; lt.L = 0.7; lt.R = 0.6*ease((bl - 5)/1);
    } else if (i === 3) {
      curled(H, u);
      [[A,1],[B,-1]].forEach(([r,s]) => {
        r.glow = 0.65; r.yaw = s*seq([.73,.73,.73,.73,1,1,1,1], bl);
        r.pitch = seq([-.6,-.7,-.8,-.8,-.4,-.4,-.4,-.4], bl) + (c >= 6 ? 0.3*p : 0);
        r.antL = r.antR = seq([.8,1,1.2,1.2,1.1,1.1,.5,.4], bl); r.roll = s*seq([0,0,0,0,.12,.12,0,0], bl);
      });
      lt.M = 0.65; lt.C = 0.4; lt.L = lt.R = 0.55;
    } else if (i === 4) {
      curled(H, u);
      H.shrug = -9 + 7*p; H.headDown = c < 4 ? 1 : seq([1,1,1,1,.8,.6,.4,.3], bl); H.tilt = c < 4 ? 0.14 : 0;
      [[A,1],[B,-1]].forEach(([r,sd]) => {
        r.yaw = sd*0.73; r.pitch = -0.15 + 0.15*p; r.roll = sd*0.15; r.body = sd*0.25 + 0.1*Math.sin(Math.PI*bl/2);
        r.bob = -4*p; r.glow = 1;
        if (sd > 0) { r.antR = 1.35 - 0.25*p; r.antL = 0.3; } else { r.antL = 1.35 - 0.25*p; r.antR = 0.3; }
      });
      lt.warm = 0.15; lt.lamp = 0; lt.M = 0.75; lt.C = 0.45 + 0.25*p; lt.L = lt.R = 0.65;
    } else if (i === 5) {
      H.hood = 1;
      H.headDown = seq([0,0,0,0,0,0,0,0], bl); H.shrug = seq([-9,0,0,0,0,0,0,0], bl); H.drop = seq([14,6,6,6,6,6,0,0], bl);
      H.aL = seq([.05,.05,1.57,1.57,1.57,1.57,1.57,1.57], bl); H.eL = seq([0,0,0,1.57,1.57,1.57,1.57,1.57], bl);
      H.aR = seq([.07,.07,.07,.07,1.57,1.57,1.57,1.57], bl); H.eR = seq([0,0,0,0,0,-1.57,-1.57,-1.57], bl);
      H.look = seq([0,0,0,0,0,0,-.8,.8], bl); H.tilt = seq([.14,0,0,0,0,0,0,0], bl);
      [[A,1,0],[B,-1,1]].forEach(([r,sd,lag]) => {
        r.yaw = sd*0.73; r.glow = 1; const b2 = bl - lag;
        const cheer = (b2 >= 2 && b2 < 3) || (b2 >= 4 && b2 < 5) || (b2 >= 6 && b2 < 7) ? pulse(b2) : 0;
        r.pitch = 0.35*cheer; r.bob = -9*cheer;
        r.antL = 0.3 + 0.9*cheer; r.antR = 0.3 + 0.9*cheer; r.roll = sd*0.15*cheer;
      });
      lt.warm = 0.25; lt.lamp = 0; lt.M = 0.8; lt.C = seq([.45,.6,.6,.7,.7,.8,.8,.9], bl); lt.L = lt.R = 0.65;
    } else if (i === 6) {
      H.hood = 1;
      H.x = c < 4 ? -150*ease(bl/3.4) : lerp(-150, 150, ease((bl - 4)/3.4));
      if (c !== 3 && c !== 7) steps(H, bl, 1, 24);
      const swing = Math.sin(Math.PI*bl);
      H.aL = 0.15 + Math.max(0, swing)*0.55; H.aR = 0.15 + Math.max(0, -swing)*0.55; H.eL = H.eR = 0;
      H.look = c === 3 ? -0.7 : (c === 7 ? 0.7 : 0); H.headDown = 0;
      const greetA = c === 3 ? pulse(bl) : 0, greetB = c === 7 ? pulse(bl) : 0;
      A.yaw = toward(POS.L, hxAbs()); A.body = A.yaw*0.4; A.pitch = 0.4*greetA; A.antL = A.antR = 0.3 + 1.0*greetA; A.bob = -12*greetA;
      B.yaw = toward(POS.R, hxAbs()); B.body = B.yaw*0.4; B.pitch = 0.4*greetB; B.antL = B.antR = 0.3 + 1.0*greetB; B.bob = -12*greetB;
      lt.warm = 0.35; lt.lamp = 0; lt.M = 0.85; lt.C = 0.7; lt.L = c < 4 ? 0.85 : 0.6; lt.R = c < 4 ? 0.6 : 0.85;
    } else if (i === 7) {
      H.hood = 1; H.x = c < 1 ? lerp(150, 0, ease(bl)) : 0; if (c < 1) steps(H, bl, 1, 20);
      H.look = seq([0,0,-.7,.7,0,0,0,0], bl);
      H.lean = seq([0,0,-.12,.12,0,0,0,0], bl); H.shrug = seq([0,0,10,10,0,0,0,0], bl) + (c === 7 ? 8*p : 0);
      H.aL = H.aR = seq([.12,.12,.12,.12,.35,.35,1.2,.3], bl); H.eL = H.eR = seq([.1,.1,.1,.1,2.75,2.75,1.3,.2], bl);
      [[A,1,2],[B,-1,3]].forEach(([r,sd,popAt]) => {
        const hidden = c < popAt || c === 4 || c === 5 ? (c < popAt ? 1 : 0.6) : 0;
        r.pitch = lerp(0.25, -0.9, hidden); r.bob = lerp(-4, 18, hidden); r.antL = r.antR = lerp(0.15, 1.3, hidden);
        r.roll = c === popAt ? sd*0.35 : 0; r.yaw = sd*0.73;
        if (c === 6) { r.pitch = 0.4; r.bob = -10; r.antL = r.antR = 1.0; r.roll = sd*0.2; }
        if (c === 7) { r.roll = 0.22*Math.sin(6*Math.PI*bl); r.bob = -6*Math.abs(Math.sin(6*Math.PI*bl)); r.antL = r.antR = 0.5 + 0.4*Math.sin(6*Math.PI*bl); r.pitch = 0.2; }
      });
      lt.warm = 0.45; lt.lamp = 0; lt.M = 0.9; lt.C = 0.8; lt.L = c === 2 ? 1 : 0.7; lt.R = c === 3 ? 1 : 0.7;
    } else if (i === 8) {
      H.hood = c < 1 ? 1 : 1 - ease(bl - 1);
      H.x = seq([0,0,0,0,-45,-45,45,45], bl);
      if (c < 2) { H.aL = H.aR = seq([2.6,2.2], bl); H.eL = H.eR = seq([1.4,0], bl); }
      else if (c < 4) { H.aL = 0.4 + 0.25*Math.sin(8*Math.PI*bl); H.aR = 0.4 - 0.25*Math.sin(8*Math.PI*bl); H.eL = H.eR = 0.3; H.shrug = 6*Math.sin(8*Math.PI*bl); }
      else { steps(H, bl, 1, 24); H.aL = 0.4 + 0.3*Math.sin(Math.PI*bl); H.aR = 0.4 - 0.3*Math.sin(Math.PI*bl); H.eL = H.eR = 1.2; }
      H.look = c >= 4 ? (c < 6 ? -0.5 : 0.5) : 0;
      [[A,POS.L],[B,POS.R]].forEach(([r,x]) => {
        r.yaw = toward(x, hxAbs()); r.glow = 1;
        if (c === 1) { r.pitch = 0.5; r.bob = -8; r.antL = r.antR = 1.3; }
        else if (c >= 2) { r.pitch = 0.05 + 0.35*p; r.antL = r.antR = 0.2 + 0.6*p; r.bob = -3*p;
          const mine = (x === POS.L && (c === 4 || c === 5)) || (x === POS.R && (c === 6 || c === 7));
          if (mine) { r.roll = (x === POS.L ? 0.2 : -0.2); r.antL = r.antR = 0.2 + 0.9*p; } }
      });
      lt.warm = c < 1 ? 0.45 : 1; lt.lamp = c < 1 ? 0 : 1; lt.M = 1; lt.C = lt.L = lt.R = 1;
    } else if (i === 9) {
      H.aL = H.aR = 0.6 + 0.6*p; H.eL = H.eR = -2.4; H.headDown = 0.25*p; H.drop = 10*p;
      if (c >= 4) { H.fLy = (c % 2 === 0 ? 22 : 0)*p; H.fRy = (c % 2 === 1 ? 22 : 0)*p; }
      [[A,1,0],[B,-1,1]].forEach(([r,s,ofs]) => {
        const mine = c >= 4 || c % 2 === ofs, pp = mine ? p : 0;
        r.pitch = -0.45*pp; r.bob = 6*pp; r.yaw = s*0.5; r.antL = 0.2 + 0.9*pp*(c % 2 ? 1 : 0.3); r.antR = 0.2 + 0.9*pp*(c % 2 ? 0.3 : 1);
      });
    } else if (i === 10) {
      const th = 2*Math.PI*bl/8;
      H.x = -230*Math.sin(th); H.depth = (1 - Math.cos(th))/2; H.face = th;
      const cl = Math.cos(Math.PI*bl);
      H.fLy = 35*Math.pow(Math.max(0, cl), 2); H.fRy = 35*Math.pow(Math.max(0, -cl), 2); H.drop = 8*(1 - Math.abs(cl));
      H.aL = 0.5 + 0.4*Math.max(0, -cl); H.aR = 0.5 + 0.4*Math.max(0, cl); H.eL = H.eR = 1.0;
      [[A,POS.L],[B,POS.R]].forEach(([r,x]) => { r.yaw = toward(x, hxAbs()); r.body = 0.7*r.yaw; r.antL = r.antR = 0.25 + 0.5*p; r.pitch = 0.1*p - 0.1*H.depth; });
    } else if (i === 11) {
      H.face = 2*Math.PI*ease(bl/2);
      H.aL = H.aR = seq([1.4,1.4,2.5,2.5,.6,.6,.6,.6], bl); H.eL = H.eR = seq([0,0,0,0,-2.2,-2.2,-2.2,-2.2], bl);
      H.look = c >= 4 ? (c < 6 ? -0.6 : 0.6) : 0; H.drop = c >= 4 ? 5*p : 0;
      [[A,1],[B,-1]].forEach(([r,s]) => {
        if (c < 4) { r.roll = 0.3*Math.sin(Math.PI*bl); r.pitch = 0.3*Math.cos(Math.PI*bl); r.yaw = s*0.2; }
        else {
          const out = ease((bl - 4)/2), back = ease((bl - 6)/0.6);
          r.turn = s*2.8*out*(1 - back); r.antL = r.antR = c === 7 ? 1.2 : 0.4; r.pitch = c === 7 ? 0.3 : 0;
        }
      });
    } else if (i === 12 || i === 13 || (i === 17 && c < 4)) {
      const m = runningMan(H, bl);
      if (i === 13) H.face = 2*Math.PI*bl/8;
      [[A,1],[B,-1]].forEach(([r,s]) => {
        r.pitch = 0.5*p - 0.1; r.bob = -9*p; r.antL = 0.1 + 1.15*m.liftL; r.antR = 0.1 + 1.15*m.liftR; r.yaw = s*0.35;
        if (i === 12) r.turn = s*0.7*Math.sin(Math.PI*bl/4);
        if (i === 13) { r.yaw = s*0.3 + 0.5*Math.sin(Math.PI*bl/2); r.pitch = 0.3*Math.sin(Math.PI*bl) + 0.3*p; r.roll = 0.22*Math.sin(3*Math.PI*bl/4); r.body = 0.5*Math.sin(2*Math.PI*bl/8)*s; }
      });
      lt.party = i === 12 ? ease(u/0.5) : 1;
    } else if (i === 14) {
      H.x = 28*Math.sin(Math.PI*bl); H.fLy = 18*Math.max(0, -Math.sin(Math.PI*bl)); H.fRy = 18*Math.max(0, Math.sin(Math.PI*bl)); H.drop = 6*p;
      if (c < 2) { const w = 2*Math.PI*bl/2; H.aL = 1.57 + 1.2*Math.sin(w); H.aR = 1.57 + 1.2*Math.sin(w + Math.PI); H.eL = H.eR = 0.2; }
      else if (c < 4) { H.aL = H.aR = 0.5; H.eL = 2.6 + 0.35*Math.sin(4*Math.PI*bl); H.eR = 2.6 + 0.35*Math.sin(4*Math.PI*bl + Math.PI); }
      else if (c === 4) { H.aL = 1.7; H.eL = 0; H.aR = -1.1; H.eR = 0; H.look = -0.7; H.lean = -0.1; }
      else if (c === 5) { H.aR = 1.7; H.eR = 0; H.aL = -1.1; H.eL = 0; H.look = 0.7; H.lean = 0.1; }
      else { H.aL = H.aR = 2.6; H.eL = H.eR = 1.0; H.tilt = c === 6 ? 0.15 : -0.15; }
      [[A,1,4],[B,-1,5]].forEach(([r,sd,popAt]) => {
        const w = 2*Math.PI*bl/2 + (sd > 0 ? 0 : Math.PI);
        r.antL = 0.7 + 0.6*Math.sin(w); r.antR = 0.7 + 0.6*Math.sin(w + Math.PI); r.yaw = sd*0.35;
        if (c >= 2 && c < 4) r.roll = 0.18*Math.sin(4*Math.PI*bl);
        if (c === popAt) { const pp = pulse(bl); r.pitch = 0.45*pp + 0.1; r.bob = -12*pp; r.antL = r.antR = 0.2 + 1.1*pp; r.yaw = sd*0.73; }
        if (c >= 6) { r.antL = r.antR = 0.05; r.roll = (c === 6 ? 0.18 : -0.18); r.pitch = 0.25; r.yaw = sd*0.4; }
      });
      lt.party = 1;
    } else if (i === 15 || i === 17) {
      const eL = [1.57,-1.57,1.57,-1.57,1.57,-1.57,1.57,1.57], eR = [-1.57,1.57,-1.57,1.57,1.57,-1.57,-1.57,1.57];
      const pingpong = i === 15 && c < 4;
      if (pingpong) { H.aL = H.aR = 0.3; H.eL = H.eR = 0.4; H.look = seq([-.7,.7,-.7,.7,0,0,0,0], bl); H.shrug = 8*p; H.drop = 6*p; }
      else { H.aL = H.aR = 1.57; H.eL = seq(eL, bl); H.eR = seq(eR, bl); H.look = seq([-.6,-.6,.6,.6,0,0,-.6,.6], bl); H.drop = 6*p; }
      const yA = [.45,.45,-.45,-.45,.45,-.45,-.45,.45], pA = [.35,.35,-.25,-.25,.35,.35,-.25,-.25];
      const yB = [0,-.45,-.45,.45,.45,-.45,-.45,.45], pB = [0,.35,.35,-.25,.35,.35,-.25,-.25];
      [[A,1,yA,pA],[B,-1,i === 15 ? yB : yA,i === 15 ? pB : pA]].forEach(([r,s,yy,pp]) => {
        r.yaw = s*0.25 + seq(yy, bl); r.pitch = seq(pp, bl); r.body = 0.35*seq(yy, bl);
        r.antL = seq(eL.map(v => v > 0 ? .1 : 1.25), bl); r.antR = seq(eR.map(v => v > 0 ? .1 : 1.25), bl); r.bob = -4*p;
      });
      if (i === 15) { lt.L = c < 4 && c % 2 === 0 ? 1 : 0.7; lt.R = c < 4 && c % 2 === 1 ? 1 : 0.7; }
      lt.party = 1;
    } else if (i === 16) {
      const w = c < 4 ? bl/4 : 1 - (bl - 4)/4, g = (c0, s=0.07) => Math.exp(-Math.pow((w - c0)/s, 2));
      A.antL = 0.25 + 1.1*g(.04); A.antR = 0.25 + 1.1*g(.14); A.roll = 0.3*g(.09); A.pitch = 0.35*g(.09); A.bob = -10*g(.09);
      B.antL = 0.25 + 1.1*g(.86); B.antR = 0.25 + 1.1*g(.96); B.roll = -0.3*g(.91); B.pitch = 0.35*g(.91); B.bob = -10*g(.91);
      const xw = lerp(250, 1350, w); A.yaw = toward(POS.L, xw); B.yaw = toward(POS.R, xw); A.body = A.yaw*0.4; B.body = B.yaw*0.4;
      const wh = (w - 0.2)/0.6, gh = c0 => Math.exp(-Math.pow((wh - c0)/0.11, 2));
      H.aL = 1.57 + 0.4*gh(.22) + 0.2*gh(.38); H.eL = 0.9*gh(.04) - 0.8*gh(.22);
      H.aR = 1.57 + 0.4*gh(.78) + 0.2*gh(.62); H.eR = 0.9*gh(.96) - 0.8*gh(.78);
      H.shrug = 16*gh(.5); H.look = clamp((w - 0.5)*2, -1, 1)*0.6; H.drop = 4*p;
      lt.party = 1;
    } else {
      const jump = (c === 0 || c === 2) ? Math.sin(Math.PI*f) : 0;
      if (c < 4) { H.drop = -45*jump; H.fLy = H.fRy = 30*jump; H.aL = H.aR = 2.5; H.eL = H.eR = 0; }
      else { H.aL = 2.65; H.eL = 0; H.aR = 0.75; H.eR = -2.3; H.tilt = 0.12; H.drop = seq([0,0,0,0,12,4,4,4], bl); }
      [[A,1],[B,-1]].forEach(([r,s]) => {
        if (c < 4) { r.antL = 0.6 + 0.5*Math.sin(4*Math.PI*bl); r.antR = 0.6 - 0.5*Math.sin(4*Math.PI*bl); r.bob = -10*p; r.pitch = 0.1 + 0.35*p; r.yaw = s*0.3; r.turn = s*0.5*Math.sin(Math.PI*bl); }
        else { const k = ease((bl - 4)/1); r.yaw = s*lerp(0.3, 0.73, k); r.pitch = lerp(0.1, 0.35, k); r.roll = s*0.22*k; r.antL = r.antR = lerp(0.6, 0.05, k); }
      });
      lt.party = 1 - 0.4*ease((bl - 4)/2); lt.L = lt.R = 1 - 0.7*ease((u - 3.4)/0.5); lt.M = 1 - ease((u - 3.5)/0.5);
    }
    // groove layer: the robots are never static once the beat is in
    const amt = (i >= 4 && i <= 7) ? 0.45 : (i >= 8 ? 1 : 0);
    const still = (i === 11 && c >= 4) || (i === 18 && c >= 4) || i === 16 || (i === 7 && c === 7);
    if (amt > 0 && !still) { groove(A, 1, bl, amt); groove(B, -1, bl, amt); }
    return S;
  }

  function mix(a, b, k) {
    if (typeof a === 'number') return lerp(a, b, k);
    const o = {}; for (const key in b) o[key] = mix(a[key], b[key], k); return o;
  }
  const phraseAt = t => clamp(Math.floor(t / PH), 0, N - 1);
  function poseAt(t) {
    t = Math.min(t, DUR - 1e-4);
    const i = phraseAt(t), r = raw(i, t), d = t - i*PH;
    if (i > 0 && d < 0.3) return mix(raw(i - 1, i*PH - 1e-4), r, ease(d/0.3));
    return r;
  }


const KEYS = ["yaw","pitch","roll","body","turn","antL","antR","bob"];
const out = { step: 0.05, keys: KEYS, A: [], B: [] };
for (let k = 0; k * 0.05 < DUR; k++) {
  const S = poseAt(k * 0.05);
  out.A.push(KEYS.map(q => +S.L[q].toFixed(5))); out.B.push(KEYS.map(q => +S.R[q].toFixed(5)));
}
require('fs').writeFileSync(process.argv[2], JSON.stringify(out));
console.log('samples', out.A.length);
