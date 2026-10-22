// Clawd, drawn the same way the desktop pet draws him (pet.py): a 12x8 pixel grid at any cell size.
// Used by the motion ad (ad.html).
const BODY = "#D97757", EYE = "#000", INK = "#1a1b26";
const CONFETTI = ["#f7768e", "#e0af68", "#9ece6a", "#7dcfff", "#bb9af7"];
const HEART = [".##.##.", "#######", ".#####.", "..###..", "...#..."];
const SAYS = {   // state: [default bubble, accent]
  waiting: ["Needs you!", "#f7768e"], celebrate: ["All done!", "#9ece6a"], tired: ["Context 92% full", "#e0af68"],
  juice: ["Out of juice · back 8:10pm", "#e0af68"], oops: ["Oops!", "#f7768e"], push: ["Pushed!", "#9ece6a"], commit: ["Committed!", "#9ece6a"],
};

function clawd(ctx, o) {
  // o: {x, ground, cell, t, state, walking, dir, outfit, bubble, energy, age}
  // states: idle working waiting celebrate tired sleeping juice oops push commit petted
  // `age` is seconds into a reaction (push/commit fireworks, petted hearts); it loops when left out.
  const C = o.cell, k = C / 5, t = o.t, st = o.state, ox = o.x - 6 * C;
  const px = (col, row, oy, color = BODY, w = 1, h = 1) => { ctx.fillStyle = color; ctx.fillRect(ox + col * C, oy + row * C, w * C, h * C); };
  const asleep = st === "sleeping" || st === "juice", cheer = st === "celebrate" || st === "push" || st === "commit";
  const age = o.age ?? (t % 2.4);
  let bob = 0;
  if (o.walking) bob = Math.floor(t * 6) % 2 ? 1 : 0;
  else if (st === "waiting") bob = Math.round(Math.abs(Math.sin(t * 4)) * 3);
  else if (cheer) bob = Math.round(Math.abs(Math.sin(t * 7)) * 14);
  else if (st === "petted") bob = age < .5 ? Math.round(Math.sin(age / .5 * Math.PI) * 8) : 0;
  else if (asleep) bob = Math.sin(t * 1.2) > .4 ? 1 : 0;
  bob *= k;
  const oy = o.ground - 8 * C - bob, working = st === "working";
  const tired = st === "tired" ? 3 : 0;
  if (st === "celebrate") for (let i = 0; i < 16; i++) {
    const ph = (t * 1.1 + i * .37) % 1, x = o.x + (i - 8) * 2.2 * C + Math.sin(t * 3 + i) * 6 * k, y = 4 * k + ph * (o.ground - 4 * k);
    ctx.fillStyle = CONFETTI[i % 5]; ctx.fillRect(x - 2 * k, y - 2 * k, 4 * k, 4 * k);
  }
  if (st === "push" || st === "commit") fireworks(ctx, o.x, oy, C, age);
  px(2, 0, oy, BODY, 8, 6);
  if (working) { const f = Math.floor(t * 8) % 2 ? .5 : 0; px(0, 3.4 + f, oy, BODY, 3, 1.4); px(9, 3.9 - f, oy, BODY, 3, 1.4); }
  else if (st === "oops") { px(0, 2, oy, BODY, 2, 2); px(9, 2, oy, BODY, 3, 2); }
  else { const up = cheer || (st === "waiting" && Math.floor(t * 4) % 2 === 0); px(0, up ? 1 : 2, oy, BODY, 12, 2); }
  const step = Math.floor(t * 6) % 2;
  [2, 4, 7, 9].forEach((col, i) => { const drop = o.walking && i % 2 === step ? 1 : 0; px(col, 6, oy, BODY, 1, 2 - drop); });
  const blink = st === "idle" && !o.walking && (t % 4.5) < .15;
  const yawn = tired && (t % 6) < 1.4;
  const shift = o.walking ? (o.dir > 0 ? 1 : -1) * k : 0;
  const lid = [0, 1, 2.5, 3.8][tired] * k;
  for (const col of [3, 8]) {
    const x0 = ox + col * C + shift, y0 = oy + C;
    if (asleep || blink || yawn) px(col, 1.3, oy, EYE, 1, .4);
    else if (cheer || st === "petted") { ctx.strokeStyle = EYE; ctx.lineWidth = Math.max(2, C / 2.5); ctx.beginPath(); ctx.moveTo(x0, y0 + C); ctx.lineTo(x0 + C / 2, y0); ctx.lineTo(x0 + C, y0 + C); ctx.stroke(); }
    else { ctx.fillStyle = EYE; ctx.fillRect(x0, y0, C, C); if (lid) { ctx.fillStyle = BODY; ctx.fillRect(x0 - k, y0 - k, C + 2 * k, lid + k); } }
  }
  if (yawn) px(5, 3, oy, EYE, 2, 1.2);
  if (tired || st === "oops") { const dx = ox + (st === "oops" ? 10 : 9.5) * C + Math.sin(t * 2) * 1.5 * k; ctx.fillStyle = "#7dcfff"; ctx.beginPath(); ctx.moveTo(dx, oy - 1.6 * C); ctx.lineTo(dx - .6 * C, oy - .4 * C); ctx.lineTo(dx + .6 * C, oy - .4 * C); ctx.fill(); }
  outfit(ctx, o.outfit, px, oy, ox, C);
  if (st === "oops") px(1.6, .6, oy, "#b85f42", 4.6, 1.3);   // forearm across his eyes
  if (working) {
    px(1.6, 2.3, oy, "#3b3b44", 8.8, 3.5); px(2, 2.7, oy, "#1f2430", 8, 2.7);
    for (let i = 0; i < 3; i++) px(2.4, 3 + i * .8, oy, ["#9ece6a", "#7dcfff", "#e0af68"][(Math.floor(t * 3) + i) % 3], 2 + ((Math.floor(t * 3) + i * 3) % 5), .4);
    px(1, 5.8, oy, "#8a8a92", 10, .7);
  }
  if (st === "petted") hearts(ctx, o.x, oy, C, [age, age - .25, age - .5], [-14, 10, -2]);
  if (asleep) for (let i = 0; i < 3; i++) {
    const ph = (t * .45 + i / 3) % 1; ctx.fillStyle = "#7a7f99"; ctx.font = `700 ${Math.round((8 + ph * 6) * k)}px "DM Sans", sans-serif`;
    ctx.fillText("z", o.x + 4.8 * C + ph * 3.2 * C, oy - .4 * C - ph * 5.2 * C);
  }
  if (o.bubble !== false) {
    if (working) bubble(ctx, o.x, oy, C, o.bubble || "Working…", BODY);
    else if (SAYS[st] && (st !== "push" && st !== "commit" || age > .3)) bubble(ctx, o.x, oy, C, o.bubble || SAYS[st][0], SAYS[st][1]);
  }
  if (o.energy != null) {   // the context bar: fills up as context is used
    const w = 8 * C, l = o.x - w / 2, top = o.ground + 2 * k, used = o.energy;
    ctx.fillStyle = "#232433"; ctx.fillRect(l - k, top - k, w + 2 * k, 4 * k);
    ctx.fillStyle = used < .5 ? "#9ece6a" : used < .75 ? "#e0af68" : "#f7768e"; ctx.fillRect(l, top, w * used, 2 * k);
  }
}

function outfit(ctx, fit, px, oy, ox, C) {
  if (fit === "party hat") { px(4.5, -1, oy, "#bb9af7", 3); px(5.25, -2, oy, "#bb9af7", 1.5); px(5.5, -3, oy, "#f7768e", 1); }
  else if (fit === "cap") { px(2.5, -1.4, oy, "#7aa2f7", 7, 1.4); px(8.5, -.4, oy, "#5a7fd0", 3, .6); }
  else if (fit === "crown") { px(2.5, -1, oy, "#e0af68", 7); for (const c of [2.5, 5.5, 8.5]) px(c, -2, oy, "#e0af68"); px(5.5, -.6, oy, "#f7768e", 1, .5); }
  else if (fit === "glasses") {
    ctx.strokeStyle = INK; ctx.lineWidth = Math.max(2, C / 2.5);
    for (const col of [3, 8]) ctx.strokeRect(ox + col * C - .6 * C, oy + C - .6 * C, C * 2.2, C * 2.2);
    ctx.beginPath(); ctx.moveTo(ox + 4.6 * C, oy + 1.5 * C); ctx.lineTo(ox + 7.4 * C, oy + 1.5 * C); ctx.stroke();
  } else if (fit === "bow tie") {
    const cx = ox + 6 * C, ty = oy + 5.2 * C, s = C / 5;
    ctx.fillStyle = "#f7768e"; ctx.strokeStyle = INK; ctx.lineWidth = s;
    for (const d of [-1, 1]) { ctx.beginPath(); ctx.moveTo(cx + d * 14 * s, ty - 6 * s); ctx.lineTo(cx + d * 14 * s, ty + 6 * s); ctx.lineTo(cx, ty); ctx.closePath(); ctx.fill(); ctx.stroke(); }
    ctx.fillStyle = "#d4382c"; ctx.fillRect(cx - 3 * s, ty - 3 * s, 6 * s, 6 * s);
  } else if (fit === "witch hat") {   // seasonal hats, from pet_menu.draw_seasonal
    px(1.5, -.8, oy, "#3d2a5c", 9, .8); px(3.5, -2, oy, "#3d2a5c", 5, 1.2); px(3.5, -1.6, oy, "#e0af68", 5, .4);
    px(4.5, -3, oy, "#3d2a5c", 3, 1); px(5.5, -3.8, oy, "#3d2a5c", 2, .8); px(7.2, -4.3, oy, "#3d2a5c", 1.2, .6);
  } else if (fit === "pumpkin") {
    px(4, -2.2, oy, "#ff9e3b", 4, 2.2); px(3.6, -1.8, oy, "#ff9e3b", 4.8, 1.4); px(5.6, -2.2, oy, "#d9771f", .8, 2.2);
    px(5.6, -3, oy, "#5b8c3a", .8, .8); px(6.4, -3, oy, "#5b8c3a", .8, .4);
  } else if (fit === "santa hat") {
    px(2.5, -1, oy, "#f4f4f4", 7, 1); px(3, -2, oy, "#e0453a", 6, 1); px(4.5, -3, oy, "#e0453a", 4, 1);
    px(7.5, -3.6, oy, "#e0453a", 1.5, .8); px(9, -3.9, oy, "#f4f4f4", 1.2, 1.2);
  }
}

function bubble(ctx, cx, oy, C, text, accent) {
  const k = C / 5, fs = Math.round(C * 1.9);
  ctx.font = `700 ${fs}px "DM Mono", Consolas, monospace`;
  const w = ctx.measureText(text).width, h = fs * 1.15, pad = 2 * C;
  const cy = Math.max(h / 2 + 2 * C, oy - 3.6 * C - 8 * k);
  const l = cx - w / 2 - pad, r = cx + w / 2 + pad, t = cy - h / 2 - C, b = cy + h / 2 + C, n = 3 * k;
  const notched = (l, t, r, b, fill) => { ctx.fillStyle = fill; ctx.beginPath();
    [[l + n, t], [r - n, t], [r - n, t + n], [r, t + n], [r, b - n], [r - n, b - n], [r - n, b], [l + n, b], [l + n, b - n], [l, b - n], [l, t + n], [l + n, t + n]].forEach(([x, y], i) => i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)); ctx.fill(); };
  notched(l - 2 * k, t - 2 * k, r + 2 * k, b + 2 * k, accent);
  ctx.fillRect(cx - 6 * k, b, 12 * k, 4 * k); ctx.fillRect(cx - 4 * k, b + 4 * k, 8 * k, 3 * k); ctx.fillRect(cx - 2 * k, b + 7 * k, 4 * k, 2 * k);
  notched(l, t, r, b, "#232433");
  ctx.fillRect(cx - 4 * k, b - k, 8 * k, 4 * k); ctx.fillRect(cx - 2 * k, b + 3 * k, 4 * k, 2 * k);
  ctx.fillStyle = "#e8e6f0"; ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText(text, cx, cy + k);
  ctx.textAlign = "start"; ctx.textBaseline = "alphabetic";
}

function fireworks(ctx, cx, oy, C, age) {
  // three bursts popping one after another above his head
  [[-12, -6], [12, -8], [15, -1]].forEach(([dx, dy], i) => {
    const ph = (age - i * .35) / 1.1;
    if (ph < 0 || ph > 1) return;
    const r = (3 + ph * 17) * C / 5, s = (2.5 * (1 - ph) + 1) * C / 5;
    ctx.fillStyle = CONFETTI[(i * 2) % 5];
    for (let j = 0; j < 10; j++) {
      const a = j / 10 * Math.PI * 2, x = cx + dx * C + Math.cos(a) * r, y = oy + dy * C + Math.sin(a) * r + ph * ph * 8 * C / 5;
      ctx.fillRect(x - s, y - s, 2 * s, 2 * s);
    }
  });
}

function hearts(ctx, cx, oy, C, ages, offsets) {
  // pixel hearts floating up after he's petted
  const s = 2 * C / 5;
  ctx.fillStyle = "#f7768e";
  ages.forEach((a, i) => {
    if (a < 0 || a >= 1.3) return;
    const x0 = cx + offsets[i] * C / 5 - 7 * s / 2, y0 = oy - 18 * C / 5 - a * 28 * C / 5;
    ctx.globalAlpha = Math.min(1, (1.3 - a) * 3);
    HEART.forEach((line, row) => [...line].forEach((ch, col) => { if (ch === "#") ctx.fillRect(x0 + col * s, y0 + row * s, s, s); }));
  });
  ctx.globalAlpha = 1;
}

function mini(ctx, x, y, cell, fit = "none") {
  // a small static Clawd, top-left at (x, y)
  const px = (col, row, oy, color = BODY, w = 1, h = 1) => { ctx.fillStyle = color; ctx.fillRect(x + col * cell, oy + row * cell, w * cell, h * cell); };
  px(2, 0, y, BODY, 8, 6); px(0, 2, y, BODY, 12, 2);
  for (const col of [2, 4, 7, 9]) px(col, 6, y, BODY, 1, 2);
  for (const col of [3, 8]) px(col, 1, y, EYE);
  outfit(ctx, fit, px, y, x, cell);
}

function buddies(ctx, cx, ground, C, t, list) {
  // tiny Clawds for running subagents: [{slot, born, gone}] in seconds; a hop on arrival, a walk off when done
  const offsets = [-10, 10, -15.6, 15.6], mc = .4 * C;
  let extra = 0;
  for (const b of list) {
    if (b.born > t) continue;
    if (b.slot >= offsets.length) { if (b.gone == null || t < b.gone) extra++; continue; }
    const dx = offsets[b.slot] * C, a = t - b.born;
    let x = cx + dx - 6 * mc, y = ground - 8 * mc;
    if (a < .4) y -= Math.sin(a / .4 * Math.PI) * 1.6 * C;
    else if (b.gone != null && t >= b.gone) { const g = t - b.gone; x += Math.sign(dx) * g * 12 * C; y -= Math.floor(g * 8) % 2 ? C / 5 : 0; }
    else y -= Math.floor((t + b.slot) * 4) % 2 ? C / 5 : 0;
    mini(ctx, x, y, mc);
  }
  if (extra) {
    ctx.fillStyle = BODY; ctx.font = `700 ${Math.round(1.8 * C)}px "DM Mono", Consolas, monospace`; ctx.textAlign = "left";
    ctx.fillText(`+${extra}`, cx + 18.4 * C, ground - 1.2 * C); ctx.textAlign = "start";
  }
}
