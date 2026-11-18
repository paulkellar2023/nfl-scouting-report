"use strict";
const S = { idx: null, teams: {}, week: null, games: null, ok: {}, handle: "" };
const NS = "http://www.w3.org/2000/svg";
const W = 1000, H = 660;
const $ = (s, el = document) => el.querySelector(s);
let clipN = 0;

/* ---------- helpers ---------- */
function el(tag, attrs = {}, parent) {
  const e = document.createElementNS(NS, tag);
  for (const k in attrs) if (attrs[k] !== null && attrs[k] !== undefined) e.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(e);
  return e;
}
function txt(parent, x, y, s, attrs = {}) { const t = el("text", { x, y, ...attrs }, parent); t.textContent = s; return t; }
function h(tag, attrs = {}, html = "") { const e = document.createElement(tag); for (const k in attrs) e.setAttribute(k, attrs[k]); if (html) e.innerHTML = html; return e; }
function esc(s) { return String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }
const MINUS = "−";
function sgn(v, d) { const a = Math.abs(v).toFixed(d); return (+a === 0 ? "" : v > 0 ? "+" : MINUS) + a; }
function fmt(v, k) {
  if (v === null || v === undefined || isNaN(v)) return "";
  switch (k) {
    case "epa": return Math.abs(v) < 0.005 ? "0" : sgn(v, 2);
    case "pct": return Math.round(v * 100) + "%";
    case "pct1": return (v * 100).toFixed(1) + "%";
    case "pct_pm": return sgn(v * 100, 1) + "%";
    case "yds": return sgn(v, 1);
    case "num1": return v.toFixed(1);
    case "sec": return v.toFixed(2) + "s";
    default: return v.toFixed(2);
  }
}
function tickFmt(v, k, step) {
  if (k === "b3") return v.toFixed(3);
  if (Math.abs(v) < 1e-9) return "0";
  if (k === "pct" || k === "pct1") return (v * 100).toFixed(step * 100 < 1 ? 1 : 0) + "%";
  if (k === "pct_pm") return sgn(v * 100, step * 100 < 1 ? 1 : 0) + "%";
  const d = step < 0.1 ? 2 : step < 1 ? 1 : 0;
  if (k === "epa" || k === "yds") return sgn(v, d);
  return v.toFixed(d);
}
function lin(d0, d1, r0, r1) { const f = v => r0 + (v - d0) / (d1 - d0 || 1) * (r1 - r0); return f; }
function nice(min, max, n = 5) {
  const span = max - min || 1;
  let step = Math.pow(10, Math.floor(Math.log10(span / n)));
  const err = span / n / step;
  if (err >= 7.5) step *= 10; else if (err >= 3.5) step *= 5; else if (err >= 1.5) step *= 2;
  const ticks = [];
  for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) ticks.push(+v.toFixed(10));
  return { ticks, step };
}
function extent(a, pad = 0.08) {
  let lo = Math.min(...a), hi = Math.max(...a);
  if (lo === hi) { lo -= 1; hi += 1; }
  const p = (hi - lo) * pad; return [lo - p, hi + p];
}
function favTxt(p, home, away) {
  if (p === null || p === undefined) return "\u2013";
  const r = Math.round(p * 100);
  return r === 50 ? "EVEN" : r > 50 ? `${home} ${r}%` : `${away} ${100 - r}%`;
}
function numsHTML(m, home, away) {
  return `<div class="mline"><div><span>MODEL</span><b>${favTxt(m.p_home, home, away)}</b></div><div><span>MARKET</span><b>${favTxt(m.mkt, home, away)}</b></div><div><span>ELO</span><b>${favTxt(m.elo, home, away)}</b></div></div>`;
}
const wkLabel = w => w.week === "PO" ? `Playoffs${w.projected ? " (projected)" : ""}` : `Week ${w.week}${w.projected ? " (projected)" : w.backfill ? " (backfilled)" : ""}`;
// Matchup colors: the home team keeps its accent; the away team switches to its first alternate color that is
// clearly different, so two gold or two orange teams never share a color in the same game.
function rgbDist(c1, c2) {
  const p = c => [1, 3, 5].map(i => parseInt(c.slice(i, i + 2), 16)), [r1, g1, b1] = p(c1), [r2, g2, b2] = p(c2), rm = (r1 + r2) / 2;
  return Math.sqrt((2 + rm / 256) * (r1 - r2) ** 2 + 4 * (g1 - g2) ** 2 + (2 + (255 - rm) / 256) * (b1 - b2) ** 2);
}
function hsv(c) {
  const [r, g, b] = [1, 3, 5].map(i => parseInt(c.slice(i, i + 2), 16) / 255), mx = Math.max(r, g, b), d = mx - Math.min(r, g, b);
  let hh = 0;
  if (d) hh = mx === r ? ((g - b) / d + 6) % 6 : mx === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return [hh * 60, mx ? d / mx : 0, mx];
}
// Same color = close in RGB, or the same hue family (gold vs. yellow) with both colors saturated.
function clash(c1, c2) {
  if (rgbDist(c1, c2) < 120) return true;
  const [h1, s1, v1] = hsv(c1), [h2, s2, v2] = hsv(c2), dh = Math.abs(h1 - h2);
  return Math.min(dh, 360 - dh) < 35 && Math.min(s1, s2) > 0.35 && Math.min(v1, v2) > 0.25;
}
// Kickoff weather: small line icons (stroke uses currentColor) plus a one-line text label.
const WX_ICON = {
  clear: '<circle cx="12" cy="12" r="4.5"/><path d="M12 2v2.5M12 19.5V22M2 12h2.5M19.5 12H22M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M4.9 19.1l1.8-1.8M17.3 6.7l1.8-1.8"/>',
  cloud: '<path d="M7 18h10a4 4 0 0 0 .4-8A6 6 0 0 0 6 9.5 4.3 4.3 0 0 0 7 18z"/>',
  fog: '<path d="M4 9h16M2 13h20M5 17h14"/>',
  rain: '<path d="M7 14h10a4 4 0 0 0 .4-8A6 6 0 0 0 6 5.5 4.3 4.3 0 0 0 7 14z"/><path d="M8 17l-1 3M12 17l-1 3M16 17l-1 3"/>',
  snow: '<path d="M7 13h10a4 4 0 0 0 .4-8A6 6 0 0 0 6 4.5 4.3 4.3 0 0 0 7 13z"/><path d="M8 17v.01M12 19v.01M16 17v.01M10 21v.01M14 21v.01"/>',
  storm: '<path d="M7 13h10a4 4 0 0 0 .4-8A6 6 0 0 0 6 4.5 4.3 4.3 0 0 0 7 13z"/><path d="M12 14l-2 4h3l-2 4"/>',
  wind: '<path d="M3 8h11a3 3 0 1 0-3-3M3 12h16a3 3 0 1 1-3 3M3 16h8"/>',
  indoor: '<path d="M3 19a9 9 0 0 1 18 0M3 19h18M12 10v9"/>',
};
const WX_WORD = { clear: "Clear", cloud: "Cloudy", fog: "Fog", rain: "Rain", snow: "Snow", storm: "Storms", wind: "Windy" };
function wxHTML(w, full) {
  if (!w) return "";
  const k = w.indoor ? "indoor" : w.kind, tip = w.indoor ? "Indoors (dome or closed roof)"
    : `Kickoff forecast: ${w.t}°F, ${WX_WORD[k] || ""}${w.pp !== null && w.pp !== undefined ? `, ${w.pp}% chance of rain or snow` : ""}, wind ${w.wind} mph (${w.src})`;
  const svg = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${WX_ICON[k] || WX_ICON.cloud}</svg>`;
  const txt = full ? (w.indoor ? "INDOORS" : `${w.t}°F${w.wind >= 15 ? ` · ${w.wind} MPH` : ""}${w.pp >= 40 ? ` · ${w.pp}% ${k === "snow" ? "SNOW" : "RAIN"}` : ""}`) : (w.indoor ? "" : `${w.t}°`);
  return `<span class="wx${full ? " full" : ""} wx-${k}" title="${esc(tip)}" aria-label="${esc(tip)}">${svg}${txt ? `<b>${txt}</b>` : ""}</span>`;
}
function pairColors(a, h) {
  const A = S.teams[a], H = S.teams[h];
  if (!A || !H) return null;
  const pick = [A.accent, ...(A.alts || [])].find(c => !clash(c, H.accent)) || "#E8E8E8";
  return { [a]: pick, [h]: H.accent };
}
const T = t => {
  const m = S.teams[t] || { accent: "#BBBBBB", color: "#444", label: t, nick: t, abbr: t };
  return S.pair && S.pair[t] ? { ...m, accent: S.pair[t] } : m;
};
async function getJSON(p) { const r = await fetch(p, { cache: "no-cache" }); if (!r.ok) throw new Error(p); return r.json(); }
const gameCache = {};
function getGame(season, week, id) {
  const p = `data/${season}/wk${String(week).padStart(2, "0")}/${id}.json`;
  if (!gameCache[p]) gameCache[p] = getJSON(p).catch(e => { delete gameCache[p]; throw e; });
  return gameCache[p];
}
/* Images render right away; on error the local logo falls back to ESPN, then to a colored circle. */
window.__lgErr = img => {
  if (img.dataset.alt && !img.dataset.tried) { img.dataset.tried = "1"; img.src = img.dataset.alt; return; }
  const t = img.dataset.team, m = T(t);
  img.outerHTML = `<span class="fb ${img.className}" style="background:${m.color}" role="img" aria-label="${esc(m.name || t)}">${t}</span>`;
};
function logoHTML(t, cls = "") {
  const m = T(t);
  return `<img class="${cls}" src="${m.logo}" data-alt="${m.logo_url || ""}" data-team="${t}" alt="${esc(m.name || t)} logo" decoding="async" onerror="__lgErr(this)">`;
}
function svgImg(parent, srcs, attrs, fallback) {
  const im = el("image", { href: srcs[0], ...attrs }, parent);
  let i = 0;
  im.addEventListener("error", () => {
    i += 1;
    if (srcs[i]) { im.setAttribute("href", srcs[i]); return; }
    im.remove(); fallback.removeAttribute("visibility");
  });
  return im;
}

/* ---------- svg primitives ---------- */
function logo(g, team, cx, cy, size, { hl = false, dim = false } = {}) {
  const m = T(team), grp = el("g", {}, g);
  if (hl) el("circle", { cx, cy, r: size / 2 + 5, fill: "#F4F4F2", stroke: m.accent, "stroke-width": 4 }, grp);
  const s = hl ? size * 0.74 : size;
  const fb = el("g", { visibility: "hidden" }, grp);
  el("circle", { cx, cy, r: s / 2.2, fill: m.color || "#555", stroke: hl ? "none" : "#0B0B0C", "stroke-width": 2 }, fb);
  txt(fb, cx, cy + s * 0.11, team, { "text-anchor": "middle", "font-size": s * 0.3, "font-weight": 900, fill: "#fff" });
  svgImg(grp, [m.logo, m.logo_url].filter(Boolean), { x: cx - s / 2, y: cy - s / 2, width: s, height: s, preserveAspectRatio: "xMidYMid meet" }, fb);
  if (dim) grp.setAttribute("opacity", 0.42);
  return grp;
}
function face(svg, g, p, cx, cy, r) {
  const m = T(p.team), id = "c" + (++clipN);
  const cp = el("clipPath", { id }, svg.querySelector("defs"));
  el("circle", { cx, cy, r }, cp);
  el("circle", { cx, cy, r: r + 4, fill: "#26262B", stroke: m.accent, "stroke-width": 4 }, g);
  const ini = (p.name || "?").split(" ").map(s => s[0]).slice(0, 2).join("");
  const fb = el("g", p.img ? { visibility: "hidden" } : {}, g);
  el("circle", { cx, cy, r, fill: m.color || "#444" }, fb);
  txt(fb, cx, cy + r * 0.32, ini, { "text-anchor": "middle", "font-size": r * 0.85, "font-weight": 900, fill: "#fff" });
  if (p.img) svgImg(g, [p.img], { x: cx - r, y: cy - r, width: 2 * r, height: 2 * r, "clip-path": `url(#${id})`, preserveAspectRatio: "xMidYMid slice" }, fb);
}
function newSvg(h = H) { const s = el("svg", { viewBox: `0 0 ${W} ${h}`, role: "img" }); el("defs", {}, s); return s; }
const C = { grid: "#26262A", tick: "#8E8E93", title: "#CFCFCB", sub: "#9C9CA0", dash: "#6B6B70", quad: "#8C8C90", bar: "#4A4A4F", dot: "#5C5C62" };
function axes(svg, X, Y, xt, yt, fx, fy, box) {
  const g = el("g", {}, svg);
  for (const v of xt.ticks) {
    el("line", { x1: X(v), x2: X(v), y1: box.t, y2: box.b, stroke: C.grid, "stroke-width": 1.2 }, g);
    txt(g, X(v), box.b + 36, tickFmt(v, fx, xt.step), { "text-anchor": "middle", "font-size": 24, "font-weight": 300, fill: C.tick });
  }
  for (const v of yt.ticks) {
    el("line", { x1: box.l, x2: box.r, y1: Y(v), y2: Y(v), stroke: C.grid, "stroke-width": 1.2 }, g);
    txt(g, box.l - 14, Y(v) + 8, tickFmt(v, fy, yt.step), { "text-anchor": "end", "font-size": 24, "font-weight": 300, fill: C.tick });
  }
}
function axisTitles(svg, c, box) {
  const cx = (box.l + box.r) / 2;
  txt(svg, cx, box.b + 82, c.x_label || "", { "text-anchor": "middle", "font-size": 25, "font-weight": 900, fill: C.title, "letter-spacing": ".02em" });
  if (c.x_sub) txt(svg, cx, box.b + 112, c.x_sub, { "text-anchor": "middle", "font-size": 22, "font-weight": 300, fill: C.sub });
  const cy = (box.t + box.b) / 2;
  const g = el("g", { transform: `translate(${box.l - 128},${cy}) rotate(-90)` }, svg);
  txt(g, 0, 0, c.y_label || "", { "text-anchor": "middle", "font-size": 25, "font-weight": 900, fill: C.title, "letter-spacing": ".02em" });
  if (c.y_sub) txt(g, 0, 28, c.y_sub, { "text-anchor": "middle", "font-size": 22, "font-weight": 300, fill: C.sub });
}
function dashed(svg, x1, y1, x2, y2) { el("line", { x1, y1, x2, y2, stroke: C.dash, "stroke-width": 2, "stroke-dasharray": "7 7" }, svg); }
function quads(svg, q, box) {
  if (!q) return;
  const a = { "font-size": 19, "font-weight": 800, fill: C.quad, "letter-spacing": ".03em" };
  const put = (s, x, y, anchor) => s.split(", ").forEach((ln, i, arr) =>
    txt(svg, x, y + i * 24, ln + (i < arr.length - 1 ? "," : ""), { ...a, "text-anchor": anchor }));
  put(q[0], box.l + 14, box.t + 26, "start"); put(q[1], box.r - 14, box.t + 26, "end");
  put(q[2], box.l + 14, box.b - 34, "start"); put(q[3], box.r - 14, box.b - 34, "end");
}
function ols(pts) {
  const n = pts.length, mx = pts.reduce((s, p) => s + p.x, 0) / n, my = pts.reduce((s, p) => s + p.y, 0) / n;
  let sxy = 0, sxx = 0; for (const p of pts) { sxy += (p.x - mx) * (p.y - my); sxx += (p.x - mx) ** 2; }
  const b = sxx ? sxy / sxx : 0; return { slope: b, intercept: my - b * mx };
}

/* ---------- chart types ---------- */
function scatterBase(c, players) {
  const svg = newSvg(), box = { l: 156, r: W - 30, t: 20, b: H - 130 };
  const xs = c.pts.map(p => p.x), ys = c.pts.map(p => p.y);
  let [x0, x1] = extent(xs, 0.07), [y0, y1] = extent(ys, 0.1);
  if (c.diag) { const lo = Math.min(x0, y0), hi = Math.max(x1, y1); x0 = y0 = lo; x1 = y1 = hi; }
  const X = lin(x0, x1, box.l, box.r), Y = c.invert_y ? lin(y0, y1, box.t, box.b) : lin(y0, y1, box.b, box.t);
  axes(svg, X, Y, nice(x0, x1, 5), nice(y0, y1, 5), c.fmt_x, c.fmt_y, box);
  if (c.med) {
    if (c.med[0] !== null && c.med[0] >= x0 && c.med[0] <= x1) dashed(svg, X(c.med[0]), box.t, X(c.med[0]), box.b);
    if (c.med[1] !== null && c.med[1] >= y0 && c.med[1] <= y1) dashed(svg, box.l, Y(c.med[1]), box.r, Y(c.med[1]));
  }
  quads(svg, c.quad, box);
  const cid = "pc" + (++clipN);
  el("rect", { x: box.l, y: box.t, width: box.r - box.l, height: box.b - box.t }, el("clipPath", { id: cid }, svg.querySelector("defs")));
  const clipLine = (sl, ic, style) => {
    el("line", { x1: X(x0), y1: Y(sl * x0 + ic), x2: X(x1), y2: Y(sl * x1 + ic), "clip-path": `url(#${cid})`, ...style }, svg);
  };
  if (c.line) clipLine(c.line.slope, c.line.intercept, { stroke: "#BDBDBD", "stroke-width": 3, "stroke-dasharray": "3 9", "stroke-linecap": "round" });
  if (c.diag) {
    clipLine(1, 0, { stroke: "#BDBDBD", "stroke-width": 2.5, "stroke-dasharray": "12 10" });
    const g = el("g", { transform: `translate(${X(x0 + (x1 - x0) * 0.78)},${Y(y0 + (y1 - y0) * 0.78) - 14}) rotate(${-Math.atan2(Y(y0) - Y(y1), X(x1) - X(x0)) * 180 / Math.PI})` }, svg);
    txt(g, 0, 0, c.diag, { "text-anchor": "middle", "font-size": 20, "font-weight": 300, fill: "#BDBDBD" });
  }
  if (c.trend) { const f = ols(c.pts); clipLine(f.slope, f.intercept, { stroke: "#CFCFCF", "stroke-width": 4 }); }
  axisTitles(svg, c, box);
  return { svg, X, Y, box };
}
function scatter(c) {
  const { svg, X, Y } = scatterBase(c);
  const hl = new Set(c.hl || []);
  for (const p of c.pts) if (!hl.has(p.team)) logo(svg, p.team, X(p.x), Y(p.y), 46, { dim: true });
  for (const p of c.pts) if (hl.has(p.team)) logo(svg, p.team, X(p.x), Y(p.y), 74, { hl: true });
  return svg;
}
function pscatter(c) {
  const { svg, X, Y, box } = scatterBase(c, true);
  const g = el("g", {}, svg);
  for (const p of c.pts) if (!p.hl) el("circle", { cx: X(p.x), cy: Y(p.y), r: 9, fill: C.dot, opacity: 0.85 }, g);
  const hp = c.pts.filter(p => p.hl).map(p => ({ ...p, cx: X(p.x), cy: Y(p.y) }));
  const boxes = hp.map(p => [p.cx - 42, p.cy - 42, p.cx + 42, p.cy + 42]);
  const hit = b => boxes.some(o => b[0] < o[2] && b[2] > o[0] && b[1] < o[3] && b[3] > o[1]);
  for (const p of hp) face(svg, g, p, p.cx, p.cy, 36);
  for (const p of hp.sort((a, b) => a.cy - b.cy)) {
    const w = p.name.length * 14.5, opts = [[0, -52, "middle"], [0, 76, "middle"], [50, 9, "start"], [-50, 9, "end"], [0, -88, "middle"], [0, 112, "middle"]];
    let pick = opts[0], bb;
    for (const o of opts) {
      const x = p.cx + o[0], y = p.cy + o[1], x0 = o[2] === "middle" ? x - w / 2 : o[2] === "end" ? x - w : x;
      bb = [x0, y - 24, x0 + w, y + 6];
      if (!hit(bb) && bb[0] > 0 && bb[2] < W && bb[1] > 0) { pick = o; break; }
    }
    boxes.push(bb);
    txt(g, p.cx + pick[0], p.cy + pick[1], p.name, { "text-anchor": pick[2], "font-size": 26, "font-weight": 900, fill: T(p.team).accent });
  }
  return svg;
}
function swarm(vals, X, gap = 34, steps = [0, -26, 26, -52, 52, -78, 78]) {
  const placed = [], out = [];
  for (const v of [...vals].sort((a, b) => a.x - b.x)) {
    const px = X(v.x);
    const dy = steps.find(d => !placed.some(p => Math.abs(p.x - px) < gap && p.dy === d)) ?? 0;
    placed.push({ x: px, dy }); out.push({ ...v, px, dy });
  }
  return out;
}
function duel(c) {
  const svg = newSvg(600), box = { l: 40, r: W - 40 };
  const all = c.rows.flatMap(r => r.pts.map(p => p.v));
  const [x0, x1] = extent(all, 0.06), X = lin(x0, x1, box.l + 30, box.r - 30);
  const xt = nice(x0, x1, 6), ys = [190, 420];
  dashed(svg, X(c.avg), 70, X(c.avg), 520);
  txt(svg, X(c.avg), 56, "LEAGUE AVG " + fmt(c.avg, c.fmt), { "text-anchor": "middle", "font-size": 18, "font-weight": 800, fill: C.quad });
  c.rows.forEach((row, i) => {
    const cy = ys[i], m = T(row.hl);
    txt(svg, box.l, cy - 92, row.label, { "font-size": 22, "font-weight": 900, fill: m.accent, "letter-spacing": ".03em" });
    const goodRight = (row.side === "off") === (c.better_off === "right");
    txt(svg, goodRight ? box.r : box.l, cy + 100, goodRight ? "BETTER →" : "← BETTER", { "text-anchor": goodRight ? "end" : "start", "font-size": 16, "font-weight": 800, fill: "#6E6E75", "letter-spacing": ".1em" });
    el("line", { x1: box.l, x2: box.r, y1: cy, y2: cy, stroke: C.grid, "stroke-width": 2 }, svg);
    const pts = swarm(row.pts.filter(p => p.team !== row.hl).map(p => ({ ...p, x: p.v })), X);
    for (const p of pts) logo(svg, p.team, p.px, cy + p.dy, 34, { dim: true });
    const me = row.pts.find(p => p.team === row.hl);
    if (me) {
      logo(svg, me.team, X(me.v), cy, 80, { hl: true });
      txt(svg, X(me.v), cy + 82, fmt(me.v, c.fmt), { "text-anchor": "middle", "font-size": 40, style: "font-family:var(--num)", "font-weight": 600, fill: m.accent });
    }
  });
  for (const v of xt.ticks) txt(svg, X(v), 572, tickFmt(v, c.fmt, xt.step), { "text-anchor": "middle", "font-size": 22, "font-weight": 300, fill: C.tick });
  txt(svg, (box.l + box.r) / 2, 600, c.axis, { "text-anchor": "middle", "font-size": 22, "font-weight": 900, fill: C.title });
  svg.setAttribute("viewBox", `0 0 ${W} 612`);
  return svg;
}
const BG_SVG = "#141417";  // fill for open dots, close to the card background
const HALO = { stroke: "#0B0B0C", "stroke-width": 8, "paint-order": "stroke", "stroke-linejoin": "round" };
function bars(c) {
  const svg = newSvg(), box = { l: 110, r: W - 20, t: 100, b: H - 40 };  // top room for the value callouts
  const vals = c.pts.map(p => p.v), lo = Math.min(0, ...vals), hi = Math.max(0, ...vals);
  const [y0, y1] = extent([lo, hi], 0.14), Y = lin(y0, y1, box.b, box.t), yt = nice(y0, y1, 5);
  for (const v of yt.ticks) {
    el("line", { x1: box.l, x2: box.r, y1: Y(v), y2: Y(v), stroke: C.grid, "stroke-width": 1.2 }, svg);
    txt(svg, box.l - 14, Y(v) + 8, tickFmt(v, c.fmt, yt.step), { "text-anchor": "end", "font-size": 24, "font-weight": 300, fill: C.tick });
  }
  const n = c.pts.length, bw = (box.r - box.l) / n, hl = new Set(c.hl), callouts = [];
  c.pts.forEach((p, i) => {
    const x = box.l + i * bw, yv = Y(p.v), y0p = Y(0), on = hl.has(p.team), m = T(p.team);
    el("rect", { x: x + bw * 0.14, y: Math.min(yv, y0p), width: bw * 0.72, height: Math.max(1, Math.abs(yv - y0p)), fill: on ? m.accent : C.bar }, svg);
    const ly = p.v >= 0 ? yv - 18 : yv + 18;
    logo(svg, p.team, x + bw / 2, ly, on ? 34 : 24, {});
    if (on) callouts.push({ x: x + bw / 2, y: p.v >= 0 ? yv - 70 : yv + 70, s: fmt(p.v, c.fmt), col: m.accent, right: i > n * 0.6 });
  });
  el("line", { x1: box.l, x2: box.r, y1: Y(0), y2: Y(0), stroke: "#55555B", "stroke-width": 2 }, svg);
  if (c.med !== null) {
    dashed(svg, box.l, Y(c.med), box.r, Y(c.med));
    // Median label goes on the side away from the highlighted bars, with a dark halo so bars behind it don't hide it.
    const left = callouts.some(k => k.right);
    txt(svg, left ? box.l + 8 : box.r, Y(c.med) - 12, "League median " + fmt(c.med, c.fmt),
      { "text-anchor": left ? "start" : "end", "font-size": 24, "font-weight": 400, fill: "#D6D6D6", ...HALO });
  }
  // Value callouts last, so they sit on top: a dark pill with the team color as border, centered over the bar.
  callouts.sort((p, q) => p.x - q.x);
  callouts.forEach((k, i) => {  // keep each pill inside the plot, and push neighbors apart so two never overlap
    k.w = 22 * k.s.length + 28;
    k.cx = Math.min(box.r - k.w / 2, Math.max(box.l + k.w / 2, k.x));
    const prev = callouts[i - 1];
    if (prev && k.cx - prev.cx < (k.w + prev.w) / 2 + 8) {
      k.cx = prev.cx + (k.w + prev.w) / 2 + 8;
      if (k.cx + k.w / 2 > box.r) { k.cx = box.r - k.w / 2; prev.cx = k.cx - (k.w + prev.w) / 2 - 8; }
    }
  });
  for (const k of callouts) {
    const w = k.w, cx = k.cx;
    el("rect", { x: cx - w / 2, y: k.y - 30, width: w, height: 52, rx: 10, fill: "#0B0B0C", stroke: k.col, "stroke-width": 3 }, svg);
    txt(svg, cx, k.y + 10, k.s, { "text-anchor": "middle", "font-size": 36, style: "font-family:var(--num)", "font-weight": 600, fill: "#F4F4F2" });
  }
  const g = el("g", { transform: `translate(26,${(box.t + box.b) / 2}) rotate(-90)` }, svg);
  txt(g, 0, 0, c.y_label || "", { "text-anchor": "middle", "font-size": 22, "font-weight": 900, fill: C.title });
  return svg;
}
function gaps(c) {
  const svg = newSvg(), box = { l: 110, r: W - 20, t: 70, b: H - 70 };
  const all = c.series.flatMap(s => s.vals).concat(c.league).filter(v => v !== null);
  const [y0, y1] = extent([Math.min(0, ...all), Math.max(0, ...all)], 0.12), Y = lin(y0, y1, box.b, box.t), yt = nice(y0, y1, 5);
  for (const v of yt.ticks) {
    el("line", { x1: box.l, x2: box.r, y1: Y(v), y2: Y(v), stroke: C.grid, "stroke-width": 1.2 }, svg);
    txt(svg, box.l - 14, Y(v) + 8, tickFmt(v, c.fmt, yt.step), { "text-anchor": "end", "font-size": 24, "font-weight": 300, fill: C.tick });
  }
  const gw = (box.r - box.l) / c.cats.length, bw = gw * 0.32;
  c.cats.forEach((cat, i) => {
    const gx = box.l + i * gw + gw / 2;
    c.series.forEach((s, j) => {
      const v = s.vals[i]; if (v === null) return;
      const x = gx + (j === 0 ? -bw - 3 : 3);
      el("rect", { x, y: Math.min(Y(v), Y(0)), width: bw, height: Math.max(1, Math.abs(Y(v) - Y(0))), fill: T(s.team).accent, opacity: j === 0 ? 1 : 0.55 }, svg);
    });
    if (c.league[i] !== null) el("line", { x1: gx - bw - 10, x2: gx + bw + 10, y1: Y(c.league[i]), y2: Y(c.league[i]), stroke: "#F4F4F2", "stroke-width": 3 }, svg);
    txt(svg, gx, box.b + 40, cat, { "text-anchor": "middle", "font-size": 20, "font-weight": 800, fill: C.title });
  });
  el("line", { x1: box.l, x2: box.r, y1: Y(0), y2: Y(0), stroke: "#55555B", "stroke-width": 2 }, svg);
  let lx = box.l;
  c.series.forEach((s, j) => {
    el("rect", { x: lx, y: 14, width: 22, height: 22, fill: T(s.team).accent, opacity: j === 0 ? 1 : 0.55 }, svg);
    txt(svg, lx + 32, 33, s.label, { "font-size": 22, "font-weight": 800, fill: C.title });
    lx += 60 + s.label.length * 12.5;
  });
  el("line", { x1: lx, x2: lx + 26, y1: 25, y2: 25, stroke: "#F4F4F2", "stroke-width": 3 }, svg);
  txt(svg, lx + 36, 33, "League", { "font-size": 22, "font-weight": 800, fill: C.title });
  const g = el("g", { transform: `translate(26,${(box.t + box.b) / 2}) rotate(-90)` }, svg);
  txt(g, 0, 0, c.y_label || "", { "text-anchor": "middle", "font-size": 22, "font-weight": 900, fill: C.title });
  return svg;
}
function splits(c) {
  const svg = newSvg(520), n = c.panels.length, lw = 150, pw = (W - lw) / n;
  const all = c.panels.flatMap(p => p.rows.map(r => r.v)).filter(v => v !== null);
  const span = Math.max(...all.map(Math.abs), 0.05) * 1.35;
  const rows = c.panels[0].rows, rh = 120, top = 170;
  rows.forEach((r, j) => txt(svg, lw - 20, top + j * rh + rh / 2 + 10, r.label, { "text-anchor": "end", "font-size": 28, "font-weight": 900,
    fill: r.team ? T(r.team).accent : C.sub }));
  c.panels.forEach((p, i) => {
    const x0 = lw + i * pw, cx = x0 + pw / 2, X = lin(-span, span, x0 + 16, x0 + pw - 16);
    txt(svg, cx, 60, p.title, { "text-anchor": "middle", "font-size": 30, "font-weight": 900, fill: "#F4F4F2" });
    if (p.sub) txt(svg, cx, 94, p.sub, { "text-anchor": "middle", "font-size": 20, "font-weight": 300, fill: C.sub });
    el("line", { x1: X(0), x2: X(0), y1: top - 10, y2: top + rows.length * rh + 10, stroke: "#4A4A50", "stroke-width": 2 }, svg);
    p.rows.forEach((r, j) => {
      if (r.v === null) return;
      const y = top + j * rh + 20, col = r.team ? T(r.team).accent : "#6A6A70";
      el("rect", { x: Math.min(X(0), X(r.v)), y, width: Math.max(2, Math.abs(X(r.v) - X(0))), height: rh - 40, fill: col }, svg);
      txt(svg, r.v >= 0 ? X(r.v) + 8 : X(r.v) - 8, y + (rh - 40) / 2 + 13, fmt(r.v, c.fmt),
        { "text-anchor": r.v >= 0 ? "start" : "end", "font-size": 36, style: "font-family:var(--num)", "font-weight": 600, fill: col });
    });
  });
  return svg;
}
function trend(c) {
  const svg = newSvg(), box = { l: 140, r: W - 90, t: 30, b: H - 130 };
  const all = c.series.flatMap(s => s.vals).filter(v => v !== null);
  const [y0, y1] = extent([Math.min(0, ...all), Math.max(0, ...all)], 0.12);
  const X = lin(c.weeks[0], c.weeks[c.weeks.length - 1], box.l, box.r), Y = lin(y0, y1, box.b, box.t);
  const xt = { ticks: c.weeks, step: 1 };
  axes(svg, X, Y, xt, nice(y0, y1, 5), "num0", c.fmt, box);
  dashed(svg, box.l, Y(0), box.r, Y(0));
  for (const s of c.series) {
    const m = T(s.team), pts = c.weeks.map((w, i) => [w, s.vals[i]]).filter(p => p[1] !== null);
    el("polyline", { points: pts.map(p => `${X(p[0])},${Y(p[1])}`).join(" "), fill: "none", stroke: m.accent, "stroke-width": 5, "stroke-linejoin": "round" }, svg);
    for (const p of pts) el("circle", { cx: X(p[0]), cy: Y(p[1]), r: 6, fill: m.accent }, svg);
    const last = pts[pts.length - 1]; if (last) logo(svg, s.team, X(last[0]) + 46, Y(last[1]), 52, { hl: true });
  }
  axisTitles(svg, { x_label: "WEEK", y_label: c.y_label, y_sub: "3-week rolling mean" }, box);
  return svg;
}
function pstrip(c) {
  const svg = newSvg(600), box = { l: 40, r: W - 40 }, cy = 380;
  const vals = c.pts.map(p => p.v), [x0, x1] = extent(vals, 0.08), X = lin(x0, x1, box.l + 20, box.r - 20);
  el("line", { x1: box.l, x2: box.r, y1: cy, y2: cy, stroke: C.grid, "stroke-width": 3 }, svg);
  if (c.avg !== null) {
    dashed(svg, X(c.avg), 40, X(c.avg), cy + 40);
    txt(svg, X(c.avg) + 10, 28, "League avg. " + fmt(c.avg, c.fmt), { "font-size": 24, "font-weight": 300, fill: "#CFCFCB" });
  }
  for (const p of swarm(c.pts.filter(p => !p.hl).map(p => ({ ...p, x: p.v })), X, 20, [0, -18, 18, -36, 36]))
    el("circle", { cx: p.px, cy: cy + p.dy, r: 10, fill: C.dot }, svg);
  const hls = c.pts.filter(p => p.hl).sort((a, b) => a.v - b.v), lastX = [-1e9, -1e9, -1e9], lift = [0, 120, 230];
  for (const p of hls) {
    const px = X(p.v), lv = Math.max(0, lastX.findIndex(x => px - x >= 120));
    lastX[lv] = px;
    const fy = cy - lift[lv], g = el("g", {}, svg);
    if (lv) el("line", { x1: px, x2: px, y1: fy + 46, y2: cy, stroke: T(p.team).accent, "stroke-width": 2 }, g);
    face(svg, g, p, px, fy, 46);
    const right = px < W - 200, lx = lv ? px + (right ? 58 : -58) : px, ly = lv ? fy - 4 : cy + 96, an = lv ? (right ? "start" : "end") : "middle";
    txt(g, lx, ly, p.short, { "text-anchor": an, "font-size": 30, "font-weight": 900, fill: T(p.team).accent });
    txt(g, lx, ly + 36, fmt(p.v, c.fmt), { "text-anchor": an, "font-size": 36, style: "font-family:var(--num)", "font-weight": 600, fill: T(p.team).accent });
  }
  txt(svg, (box.l + box.r) / 2, 590, c.axis, { "text-anchor": "middle", "font-size": 22, "font-weight": 900, fill: C.title });
  return svg;
}

/* ---------- model charts ---------- */
function probbars(c) {
  const svg = newSvg(120 + c.rows.length * 130), l = 150, r = W - 30, A = T(c.away), Hm = T(c.home);
  logo(svg, c.away, l + 26, 40, 46, {}); logo(svg, c.home, r - 26, 40, 46, {});
  txt(svg, l + 60, 50, A.nick.toUpperCase(), { "font-size": 22, "font-weight": 900, fill: A.accent });
  txt(svg, r - 60, 50, Hm.nick.toUpperCase(), { "text-anchor": "end", "font-size": 22, "font-weight": 900, fill: Hm.accent });
  c.rows.forEach((row, i) => {
    const y = 110 + i * 130, X = lin(0, 1, l, r), xa = X(1 - row.p);
    txt(svg, l - 18, y + 52, row.label, { "text-anchor": "end", "font-size": 24, "font-weight": 900, fill: C.title });
    el("rect", { x: l, y, width: xa - l, height: 80, fill: A.accent, opacity: i ? 0.5 : 1 }, svg);
    el("rect", { x: xa, y, width: r - xa, height: 80, fill: Hm.accent, opacity: i ? 0.5 : 1 }, svg);
    el("line", { x1: xa, x2: xa, y1: y - 8, y2: y + 88, stroke: "#0B0B0C", "stroke-width": 4 }, svg);
    txt(svg, l + 14, y + 54, fmt(1 - row.p, "pct"), { "font-size": 44, style: "font-family:var(--num)", "font-weight": 600, fill: "#0B0B0C" });
    txt(svg, r - 14, y + 54, fmt(row.p, "pct"), { "text-anchor": "end", "font-size": 44, style: "font-family:var(--num)", "font-weight": 600, fill: "#0B0B0C" });
  });
  dashed(svg, lin(0, 1, l, r)(0.5), 96, lin(0, 1, l, r)(0.5), 100 + c.rows.length * 130);
  return svg;
}
function waterfall(c) {
  const rows = [...c.items, { label: "PROJECTED MARGIN", pts: c.total, total: true }];
  const GAP = 22, h = 90 + rows.length * 66 + GAP, svg = newSvg(h), l = 300, r = W - 90;
  let run = 0; const spans = rows.map(it => { if (it.total) return [0, it.pts]; const s0 = run; run += it.pts; return [s0, run]; });
  const ext = Math.max(2, ...spans.flat().map(Math.abs)) * 1.15, X = lin(-ext, ext, l, r);
  el("line", { x1: X(0), x2: X(0), y1: 40, y2: h - 20, stroke: "#55555B", "stroke-width": 2 }, svg);
  txt(svg, l, 30, "← " + T(c.away).nick.toUpperCase(), { "font-size": 18, "font-weight": 900, fill: T(c.away).accent, "letter-spacing": ".08em" });
  txt(svg, r, 30, T(c.home).nick.toUpperCase() + " →", { "text-anchor": "end", "font-size": 18, "font-weight": 900, fill: T(c.home).accent, "letter-spacing": ".08em" });
  rows.forEach((it, i) => {
    const y = 60 + i * 66 + (it.total ? GAP : 0), [a, b] = spans[i], col = it.pts >= 0 ? T(c.home).accent : T(c.away).accent;
    if (it.total) {
      // sum rule: the margin is the total of the factors above
      el("line", { x1: 40, x2: W - 10, y1: y - 6, y2: y - 6, stroke: "#9C9CA0", "stroke-width": 2.5 }, svg);
      el("line", { x1: X(b), x2: X(b), y1: y - 14 - GAP, y2: y + 6, stroke: "#6B6B70", "stroke-width": 1.5, "stroke-dasharray": "3 3" }, svg);
    }
    txt(svg, l - 18, y + 33, it.total ? it.label : it.label.toUpperCase(), { "text-anchor": "end", "font-size": 21, "font-weight": it.total ? 900 : 800, fill: it.total ? "#F4F4F2" : C.title });
    el("rect", { x: Math.min(X(a), X(b)), y: y + 6, width: Math.max(3, Math.abs(X(b) - X(a))), height: 40, fill: col, opacity: it.total ? 1 : 0.85 }, svg);
    if (i < rows.length - 1 && !rows[i + 1].total) el("line", { x1: X(b), x2: X(b), y1: y + 46, y2: y + 72, stroke: "#6B6B70", "stroke-width": 1.5, "stroke-dasharray": "3 3" }, svg);
    txt(svg, W - 10, y + 36, (it.pts > 0 ? "+" : it.pts < 0 ? MINUS : "") + Math.abs(it.pts).toFixed(1),
      { "text-anchor": "end", "font-size": 28, style: "font-family:var(--num)", "font-weight": 600, fill: col });
  });
  return svg;
}
function dist(c) {
  const svg = newSvg(560), box = { l: 60, r: W - 40, t: 60, b: 470 };
  const lo = Math.min(c.mu - 3.2 * c.sigma, c.market ?? 0, -5), hi = Math.max(c.mu + 3.2 * c.sigma, c.market ?? 0, 5);
  const X = lin(lo, hi, box.l, box.r), pdf = x => Math.exp(-0.5 * ((x - c.mu) / c.sigma) ** 2), Y = lin(0, 1.08, box.b, box.t);
  const pts = []; for (let i = 0; i <= 160; i++) { const x = lo + (hi - lo) * i / 160; pts.push([x, pdf(x)]); }
  const area = (pred, col) => {
    const seg = pts.filter(p => pred(p[0])); if (!seg.length) return;
    el("path", { d: `M${X(seg[0][0])},${Y(0)} ` + seg.map(p => `L${X(p[0])},${Y(p[1])}`).join(" ") + ` L${X(seg[seg.length - 1][0])},${Y(0)} Z`, fill: col, opacity: 0.45 }, svg);
  };
  area(x => x <= 0, T(c.away).accent); area(x => x >= 0, T(c.home).accent);
  el("polyline", { points: pts.map(p => `${X(p[0])},${Y(p[1])}`).join(" "), fill: "none", stroke: "#F4F4F2", "stroke-width": 3 }, svg);
  el("line", { x1: box.l, x2: box.r, y1: Y(0), y2: Y(0), stroke: "#55555B", "stroke-width": 2 }, svg);
  const xt = nice(lo, hi, 8);
  for (const v of xt.ticks) txt(svg, X(v), box.b + 36, (v > 0 ? "+" : v < 0 ? MINUS : "") + Math.abs(v), { "text-anchor": "middle", "font-size": 22, "font-weight": 300, fill: C.tick });
  txt(svg, (box.l + box.r) / 2, box.b + 76, `${T(c.home).nick.toUpperCase()} MARGIN (POINTS)`, { "text-anchor": "middle", "font-size": 22, "font-weight": 900, fill: C.title });
  el("line", { x1: X(c.mu), x2: X(c.mu), y1: Y(0), y2: Y(1.02), stroke: "#F4F4F2", "stroke-width": 3 }, svg);
  txt(svg, X(c.mu), Y(1.02) - 12, "MODEL", { "text-anchor": "middle", "font-size": 18, "font-weight": 900, fill: "#F4F4F2" });
  if (c.market !== null && c.market !== undefined) {
    el("line", { x1: X(c.market), x2: X(c.market), y1: Y(0), y2: Y(0.86), stroke: "#FB4F14", "stroke-width": 3, "stroke-dasharray": "8 6" }, svg);
    txt(svg, X(c.market), Y(0.86) - 12, "MARKET", { "text-anchor": "middle", "font-size": 18, "font-weight": 900, fill: "#FB4F14" });
  }
  return svg;
}
function injuries(c) {
  const n = Math.max(1, ...c.teams.map(t => t.rows.length)), h = 110 + n * 58, svg = newSvg(h), cw = (W - 40) / 2;
  c.teams.forEach((tm, j) => {
    const x0 = 20 + j * cw, m = T(tm.team);
    logo(svg, tm.team, x0 + 24, 36, 42, {});
    txt(svg, x0 + 56, 46, m.nick.toUpperCase(), { "font-size": 24, "font-weight": 900, fill: m.accent });
    if (!tm.rows.length) txt(svg, x0, 110, "No listed absences", { "font-size": 22, "font-weight": 300, fill: C.sub });
    tm.rows.forEach((r, i) => {
      const y = 90 + i * 58, bw = (cw - 60) * Math.min(1, r.weight);
      el("rect", { x: x0, y: y + 30, width: cw - 60, height: 10, fill: "#1E1E23", rx: 5 }, svg);
      el("rect", { x: x0, y: y + 30, width: Math.max(4, bw), height: 10, fill: m.accent, rx: 5, opacity: r.status === "Questionable" ? 0.5 : 1 }, svg);
      txt(svg, x0, y + 20, r.name, { "font-size": 21, "font-weight": 800, fill: "#F4F4F2" });
      txt(svg, x0 + cw - 60, y + 20, `${r.pos} · ${r.status.toUpperCase()} · ${r.side === "off" ? "O" : "D"}`, { "text-anchor": "end", "font-size": 16, "font-weight": 800, fill: C.sub, "letter-spacing": ".05em" });
    });
  });
  return svg;
}
function units(c) {
  const svg = newSvg(560), l = 230, r = W - 50;
  const vals = c.rows.flatMap(x => [x[c.home], x[c.away]]), ext = Math.max(0.05, ...vals.map(Math.abs)) * 1.2, X = lin(-ext, ext, l, r);
  dashed(svg, X(0), 20, X(0), 400);
  txt(svg, X(0), 14, "LEAGUE AVG", { "text-anchor": "middle", "font-size": 16, "font-weight": 800, fill: C.quad });
  txt(svg, r, 14, "BETTER →", { "text-anchor": "end", "font-size": 16, "font-weight": 800, fill: "#6E6E75", "letter-spacing": ".1em" });
  c.rows.forEach((row, i) => {
    const y = 70 + i * 88, xa = X(row[c.away]), xh = X(row[c.home]);
    txt(svg, l - 24, y + 8, row.label, { "text-anchor": "end", "font-size": 21, "font-weight": 900, fill: C.title });
    el("line", { x1: xa, x2: xh, y1: y, y2: y, stroke: "#4A4A50", "stroke-width": 6, "stroke-linecap": "round" }, svg);
    logo(svg, c.away, xa, y, 46, { hl: false }); logo(svg, c.home, xh, y, 46, { hl: false });
  });
  c.qb.forEach((q, j) => {
    const x = j ? W - 40 : 40, m = T(q.team);
    txt(svg, x, 470, `${m.nick.toUpperCase()} QB`, { "text-anchor": j ? "end" : "start", "font-size": 18, "font-weight": 800, fill: C.sub, "letter-spacing": ".08em" });
    txt(svg, x, 512, q.name, { "text-anchor": j ? "end" : "start", "font-size": 30, "font-weight": 900, fill: m.accent });
    txt(svg, x, 548, `${fmt(q.v, "epa")} EPA/dropback (shrunk)`, { "text-anchor": j ? "end" : "start", "font-size": 22, "font-weight": 300, fill: C.sub });
  });
  return svg;
}
function calib(c) {
  const svg = newSvg(600), box = { l: 120, r: 560, t: 30, b: 470 }, X = lin(0, 1, box.l, box.r), Y = lin(0, 1, box.b, box.t);
  for (const v of [0, 0.25, 0.5, 0.75, 1]) {
    el("line", { x1: X(v), x2: X(v), y1: box.t, y2: box.b, stroke: C.grid }, svg); el("line", { x1: box.l, x2: box.r, y1: Y(v), y2: Y(v), stroke: C.grid }, svg);
    txt(svg, X(v), box.b + 32, Math.round(v * 100) + "%", { "text-anchor": "middle", "font-size": 20, "font-weight": 300, fill: C.tick });
    txt(svg, box.l - 12, Y(v) + 7, Math.round(v * 100) + "%", { "text-anchor": "end", "font-size": 20, "font-weight": 300, fill: C.tick });
  }
  el("line", { x1: X(0), y1: Y(0), x2: X(1), y2: Y(1), stroke: "#BDBDBD", "stroke-width": 2, "stroke-dasharray": "10 8" }, svg);
  const mx = Math.max(1, ...c.pts.map(p => p.n));
  for (const p of c.pts) el("circle", { cx: X(p.pred), cy: Y(p.obs), r: 7 + 14 * Math.sqrt(p.n / mx), fill: "#FB4F14", opacity: 0.85 }, svg);
  txt(svg, (box.l + box.r) / 2, box.b + 72, "MODEL WIN PROBABILITY", { "text-anchor": "middle", "font-size": 20, "font-weight": 900, fill: C.title });
  const g = el("g", { transform: `translate(40,${(box.t + box.b) / 2}) rotate(-90)` }, svg);
  txt(g, 0, 0, "ACTUAL WIN RATE", { "text-anchor": "middle", "font-size": 20, "font-weight": 900, fill: C.title });
  const sx = 640, sr = W - 30, bs = c.seasons, all = bs.flatMap(s => [s.model_brier, s.mkt_brier]);
  const lo = Math.min(...all) - 0.005, hi = Math.max(...all) + 0.005, BX = lin(lo, hi, sx + 70, sr), rh = Math.min(48, 420 / Math.max(1, bs.length));
  txt(svg, sx, 20, "BRIER BY SEASON", { "font-size": 18, "font-weight": 900, fill: C.title, "letter-spacing": ".06em" });
  el("circle", { cx: sx + 8, cy: 46, r: 7, fill: "#FB4F14" }, svg); txt(svg, sx + 22, 52, "Model", { "font-size": 17, fill: C.sub });
  el("circle", { cx: sx + 100, cy: 46, r: 7, fill: "none", stroke: "#F4F4F2", "stroke-width": 2.5 }, svg); txt(svg, sx + 114, 52, "Market", { "font-size": 17, fill: C.sub });
  bs.forEach((s, i) => {
    const y = 90 + i * rh;
    txt(svg, sx, y + 6, String(s.season), { "font-size": 18, "font-weight": 800, fill: C.tick });
    el("line", { x1: BX(s.model_brier), x2: BX(s.mkt_brier), y1: y, y2: y, stroke: "#4A4A50", "stroke-width": 3 }, svg);
    el("circle", { cx: BX(s.mkt_brier), cy: y, r: 7, fill: "#0B0B0C", stroke: "#F4F4F2", "stroke-width": 2.5 }, svg);
    el("circle", { cx: BX(s.model_brier), cy: y, r: 7, fill: "#FB4F14" }, svg);
  });
  txt(svg, (sx + 70 + sr) / 2, 90 + bs.length * rh + 24, "← BETTER (LOWER)", { "text-anchor": "middle", "font-size": 15, "font-weight": 800, fill: "#6E6E75", "letter-spacing": ".08em" });
  return svg;
}
function lineChart(series, opt) {
  const svg = newSvg(560), box = { l: 130, r: W - 150, t: 30, b: 450 };
  const weeks = [...new Set(series.flatMap(s => s.pts.map(p => p[0])))].sort((a, b) => a - b);
  const all = series.flatMap(s => s.pts.map(p => p[1]));
  if (!weeks.length || !all.length) return svg;
  const [y0, y1] = extent(opt.zero ? [Math.min(0, ...all), Math.max(0, ...all)] : all, 0.12);
  const X = lin(weeks[0], weeks[weeks.length - 1] + (weeks.length === 1 ? 1 : 0), box.l, box.r), Y = lin(y0, y1, box.b, box.t);
  axes(svg, X, Y, { ticks: weeks, step: 1 }, nice(y0, y1, 5), "num0", opt.fy, box);
  if (opt.zero) dashed(svg, box.l, Y(0), box.r, Y(0));
  for (const s of series) {
    const pts = s.pts;
    el("polyline", { points: pts.map(p => `${X(p[0])},${Y(p[1])}`).join(" "), fill: "none", stroke: s.color, "stroke-width": 5, "stroke-linejoin": "round", "stroke-dasharray": s.dash || null }, svg);
    for (const p of pts) el("circle", { cx: X(p[0]), cy: Y(p[1]), r: 6, fill: s.dash ? "#0B0B0C" : s.color, stroke: s.color, "stroke-width": 3 }, svg);
    const last = pts[pts.length - 1];
    if (last) txt(svg, X(last[0]) + 16, Y(last[1]) + 8 + (s.dy || 0), s.label, { "font-size": 22, "font-weight": 900, fill: s.color });
  }
  axisTitles(svg, { x_label: "WEEK", y_label: opt.y_label, y_sub: opt.y_sub || "" }, box);
  return svg;
}
function cumline(c) {
  const m = c.cum.map(r => [r.week, r.model]), k = c.cum.map(r => [r.week, r.market]);
  const gapDy = m.length && Math.abs(m[m.length - 1][1] - k[k.length - 1][1]) < 0.004 ? 14 : 0;
  return lineChart([{ label: "MODEL", color: "#FB4F14", pts: m, dy: m.length && m[m.length - 1][1] > k[k.length - 1][1] ? gapDy : -gapDy },
    { label: "MARKET", color: "#F4F4F2", dash: "10 8", pts: k, dy: m.length && m[m.length - 1][1] > k[k.length - 1][1] ? -gapDy : gapDy }],
    { fy: "b3", y_label: "BRIER SCORE TO DATE", y_sub: "Lower is better" });
}
function roll(pts, n = 3) { return pts.map((p, i) => { const w = pts.slice(Math.max(0, i - n + 1), i + 1); return [p[0], w.reduce((a, q) => a + q[1], 0) / w.length]; }); }
function tline(c) {
  const off = roll(c.trend.filter(r => r.off !== null).map(r => [r.week, r.off])), def = roll(c.trend.filter(r => r.def !== null).map(r => [r.week, r.def]));
  return lineChart([{ label: "OFFENSE", color: T(c.team).accent, pts: off }, { label: "DEF. ALLOWED", color: "#9C9CA0", dash: "10 8", pts: def }],
    { fy: "epa", zero: true, y_label: "EPA PER PLAY", y_sub: "3-week rolling mean" });
}
function pbars(c) {
  const rows = c.rows, rh = 64, svg = newSvg(70 + rows.length * rh + 60), l = 330, r = W - 120;
  const vals = rows.map(x => x.v), lo = Math.min(0, ...vals), hi = Math.max(0, ...vals), pad = (hi - lo || 1) * 0.08;
  const X = lin(lo - pad, hi + pad, l, r), x0 = X(0);
  rows.forEach((x, i) => {
    const y = 50 + i * rh, m = T(x.team), col = x.hl ? m.accent : "#5A5A62";
    logo(svg, x.team, 40, y + rh / 2 - 6, 30, {});
    txt(svg, 70, y + rh / 2 + 2, x.name, { "font-size": 26, "font-weight": x.hl ? 900 : 600, fill: x.hl ? C.title : "#BDBDBD" });
    el("rect", { x: Math.min(x0, X(x.v)), y: y + 8, width: Math.max(2, Math.abs(X(x.v) - x0)), height: rh - 28, rx: 6, fill: col }, svg);
    txt(svg, x.v >= 0 ? X(x.v) + 12 : X(x.v) - 12, y + rh / 2 + 2, fmt(x.v, c.fmt), { "text-anchor": x.v >= 0 ? "start" : "end", "font-size": 28,
      style: "font-family:var(--num)", "font-weight": 600, fill: x.hl ? m.accent : "#BDBDBD" });
  });
  el("line", { x1: x0, x2: x0, y1: 40, y2: 50 + rows.length * rh, stroke: "#55555B", "stroke-width": 2 }, svg);
  txt(svg, (l + r) / 2, 50 + rows.length * rh + 44, c.axis || "", { "text-anchor": "middle", "font-size": 22, "font-weight": 900, fill: C.title });
  return svg;
}
function elotrend(c) {
  return lineChart(c.series.filter(s => s.pts.length).map((s, i) => ({ label: s.team, color: i ? T(s.team).accent : T(s.team).accent, dash: i ? null : "10 8", pts: s.pts })),
    { fy: "num0", y_label: "ELO RATING", y_sub: "1505 = average" });
}
function zones(c) {
  const svg = newSvg(560), pw = 440, gap = 80, x0s = [(W - 2 * pw - gap) / 2, (W - 2 * pw - gap) / 2 + pw + gap], top = 70, ch = 190, cw = pw / 3;
  [c.off, c.def].forEach((side, k) => {
    const x0 = x0s[k], m = T(side.team), vals = side.cells.map(q => q.v).filter(v => v !== null);
    txt(svg, x0 + pw / 2, top - 22, side.label, { "text-anchor": "middle", "font-size": 20, "font-weight": 900, fill: m.accent, "letter-spacing": ".06em" });
    el("rect", { x: x0, y: top, width: pw, height: 2 * ch, rx: 10, fill: "#16161A", stroke: "#2A2A30", "stroke-width": 2 }, svg);
    side.cells.forEach(q => {
      const col = ["left", "middle", "right"].indexOf(q.side), row = q.depth === "deep" ? 0 : 1, x = x0 + col * cw, y = top + row * ch;
      // offense: share vs. league share; defense: EPA allowed vs. league EPA in that zone (higher = worse defense)
      const rel = q.v === null ? 0 : k === 0 ? (q.v / (q.lg || 1) - 1) * 2.5 : (q.v - q.lg) * 4;
      const a = Math.max(0, Math.min(0.85, rel));
      el("rect", { x: x + 4, y: y + 4, width: cw - 8, height: ch - 8, rx: 8, fill: m.accent, opacity: (0.08 + a).toFixed(2) }, svg);
      if (q.zone === c.hl) el("rect", { x: x + 4, y: y + 4, width: cw - 8, height: ch - 8, rx: 8, fill: "none", stroke: "#F4F4F2", "stroke-width": 4 }, svg);
      txt(svg, x + cw / 2, y + ch / 2 + 6, q.v === null ? "\u2013" : fmt(q.v, side.fmt), { "text-anchor": "middle", "font-size": 36, style: "font-family:var(--num)", "font-weight": 600, fill: "#F4F4F2" });
      txt(svg, x + cw / 2, y + ch / 2 + 40, "avg " + fmt(q.lg, side.fmt), { "text-anchor": "middle", "font-size": 18, "font-weight": 300, fill: "#BDBDBD" });
    });
    el("line", { x1: x0, x2: x0 + pw, y1: top + ch, y2: top + ch, stroke: "#55555B", "stroke-width": 2, "stroke-dasharray": "8 6" }, svg);
    txt(svg, x0 - 12, top + ch / 2, "DEEP", { "text-anchor": "end", "font-size": 16, "font-weight": 900, fill: C.tick });
    txt(svg, x0 - 12, top + 1.5 * ch, "SHORT", { "text-anchor": "end", "font-size": 16, "font-weight": 900, fill: C.tick });
    ["LEFT", "MIDDLE", "RIGHT"].forEach((l, i) => txt(svg, x0 + (i + 0.5) * cw, top + 2 * ch + 30, l, { "text-anchor": "middle", "font-size": 16, "font-weight": 900, fill: C.tick }));
  });
  txt(svg, W / 2, 540, "LINE OF SCRIMMAGE AT THE BOTTOM · DEEP = 10+ AIR YARDS", { "text-anchor": "middle", "font-size": 16, "font-weight": 300, fill: "#BDBDBD" });
  return svg;
}
function strips(c) {
  const svg = newSvg(160 + c.rows.length * 240), box = { l: 60, r: W - 60 };
  c.rows.forEach((row, i) => {
    const y = 120 + i * 240, vals = row.pts.map(p => p.v), [x0, x1] = extent(vals, 0.08), X = lin(x0, x1, box.l, box.r), m = T(row.hl);
    txt(svg, box.l, y - 70, row.label, { "font-size": 20, "font-weight": 900, fill: m.accent, "letter-spacing": ".05em" });
    el("line", { x1: box.l, x2: box.r, y1: y, y2: y, stroke: "#2A2A30", "stroke-width": 2 }, svg);
    const avg = vals.reduce((s, v) => s + v, 0) / vals.length;
    dashed(svg, X(avg), y - 40, X(avg), y + 40);
    row.pts.filter(p => p.team !== row.hl).forEach(p => logo(svg, p.team, X(p.v), y, 34, { dim: true }));
    const hp = row.pts.find(p => p.team === row.hl);
    if (hp) {
      logo(svg, hp.team, X(hp.v), y, 74, { hl: true });
      txt(svg, X(hp.v), y + 70, fmt(hp.v, row.fmt), { "text-anchor": "middle", "font-size": 34, style: "font-family:var(--num)", "font-weight": 600, fill: m.accent });
    }
    txt(svg, box.l, y + 110, "\u2190 " + row.left, { "font-size": 15, "font-weight": 900, fill: C.tick });
    txt(svg, box.r, y + 110, row.right + " \u2192", { "text-anchor": "end", "font-size": 15, "font-weight": 900, fill: C.tick });
  });
  return svg;
}

// Dumbbell: one row per team, two values joined by a line (filled dot = a, open dot = b). Sorted by a; one team highlighted.
function dumbbell(c) {
  const rows = [...c.rows].sort((p, q) => q.a - p.a), rh = 26, top = 90, svg = newSvg(top + rows.length * rh + 70);
  const box = { l: 90, r: W - 40 }, [x0, x1] = extent(rows.flatMap(r => [r.a, r.b]).concat([0]), 0.06), X = lin(x0, x1, box.l, box.r);
  const m = T(c.hl);
  el("line", { x1: X(0), x2: X(0), y1: top - 20, y2: top + rows.length * rh, stroke: "#3A3A40", "stroke-width": 2 }, svg);
  el("circle", { cx: box.l, cy: 34, r: 8, fill: "#F4F4F2" }, svg);
  txt(svg, box.l + 16, 41, c.la, { "font-size": 18, "font-weight": 900, fill: "#C9C9C6", "letter-spacing": ".05em" });
  el("circle", { cx: box.l + 300, cy: 34, r: 7, fill: BG_SVG, stroke: "#F4F4F2", "stroke-width": 3 }, svg);
  txt(svg, box.l + 316, 41, c.lb, { "font-size": 18, "font-weight": 900, fill: "#C9C9C6", "letter-spacing": ".05em" });
  rows.forEach((r, i) => {
    const y = top + i * rh, on = r.team === c.hl, col = on ? m.accent : "#5A5A60";
    if (on) el("rect", { x: 0, y: y - rh / 2, width: W, height: rh, fill: m.accent, opacity: 0.1 }, svg);
    logo(svg, r.team, 50, y, on ? 30 : 20, on ? { hl: true } : { dim: true });
    el("line", { x1: X(r.a), x2: X(r.b), y1: y, y2: y, stroke: col, "stroke-width": on ? 4 : 2 }, svg);
    el("circle", { cx: X(r.b), cy: y, r: on ? 8 : 6, fill: BG_SVG, stroke: col, "stroke-width": 3 }, svg);
    el("circle", { cx: X(r.a), cy: y, r: on ? 9 : 6, fill: col }, svg);
    if (on) txt(svg, Math.max(X(r.a), X(r.b)) + 16, y + 8, fmt(r.a, c.fmt), { "font-size": 26, "font-weight": 600, style: "font-family:var(--num)", fill: m.accent, ...HALO });
  });
  const yb = top + rows.length * rh + 30;
  [x0, 0, x1].forEach(v => txt(svg, X(v), yb, fmt(v, c.fmt), { "text-anchor": "middle", "font-size": 18, fill: C.tick }));
  txt(svg, box.l, yb + 32, "\u2190 STINGIER THAN THE RECEIVER'S AVERAGE", { "font-size": 15, "font-weight": 900, fill: C.tick });
  txt(svg, box.r, yb + 32, "MORE GENEROUS \u2192", { "text-anchor": "end", "font-size": 15, "font-weight": 900, fill: C.tick });
  return svg;
}

/* ---------- field visuals (pass chart, run chart, receiver chart, drives, 4th-down map) ---------- */
const RED = "#FF5A5A", GREEN = "#4FC3A1";
function pfield(svg, ox, opt) {
  // Tilted field: depth d0..d1 yards, lateral x in -1.1..1.1, wider at the bottom.
  const { d0 = -8, d1 = 42, yb = 560, yt = 80, w0 = 215, w1 = 140, lines = 5, title = "", col = "#F4F4F2", lanes = ["LEFT", "MIDDLE", "RIGHT"] } = opt;
  const Y = d => yb - (d - d0) / (d1 - d0) * (yb - yt), half = d => w0 + (w1 - w0) * (d - d0) / (d1 - d0);
  const P = (x, d) => [ox + x * half(d) / 1.1, Y(d)];
  el("polygon", { points: [P(-1.1, d0), P(1.1, d0), P(1.1, d1), P(-1.1, d1)].map(q => q.join(",")).join(" "), fill: "#16161A", stroke: "#2A2A30", "stroke-width": 2 }, svg);
  for (let d = Math.ceil(d0 / lines) * lines; d <= d1; d += lines) {
    const [x1, y] = P(-1.1, d), [x2] = P(1.1, d);
    el("line", { x1, x2, y1: y, y2: y, stroke: d === 0 ? "#5B8DEF" : "#2E2E35", "stroke-width": d === 0 ? 3 : d % (2 * lines) ? 1 : 2 }, svg);
    if (d > 0 && d % (2 * lines) === 0) { txt(svg, x1 - 10, y + 6, "+" + d, { "text-anchor": "end", "font-size": 17, "font-weight": 800, fill: C.tick }); txt(svg, x2 + 10, y + 6, "+" + d, { "font-size": 17, "font-weight": 800, fill: C.tick }); }
  }
  txt(svg, P(-1.1, 0)[0] - 10, Y(0) + 6, "LOS", { "text-anchor": "end", "font-size": 16, "font-weight": 900, fill: "#5B8DEF" });
  if (title) txt(svg, ox, 40, title, { "text-anchor": "middle", "font-size": 20, "font-weight": 900, fill: col, "letter-spacing": ".06em" });
  lanes.forEach((l, i) => txt(svg, P(-1.1 + (i + 0.5) * 2.2 / lanes.length, d0)[0], yb + 28, l, { "text-anchor": "middle", "font-size": 14, "font-weight": 900, fill: C.tick }));
  return { P, Y };
}
function passDot(svg, x, y, r, acc, s = 1) {
  if (r === "inc") el("circle", { cx: x, cy: y, r: 6 * s, fill: "none", stroke: "#8A8A90", "stroke-width": 1.8, opacity: 0.85 }, svg);
  else if (r === "comp") el("circle", { cx: x, cy: y, r: 6.5 * s, fill: acc, opacity: 0.92 }, svg);
  else if (r === "td") { el("circle", { cx: x, cy: y, r: 11 * s, fill: "none", stroke: "#F4F4F2", "stroke-width": 3 }, svg); el("circle", { cx: x, cy: y, r: 6.5 * s, fill: acc }, svg); }
  else el("path", { d: `M${x - 7},${y - 7}L${x + 7},${y + 7}M${x + 7},${y - 7}L${x - 7},${y + 7}`, stroke: RED, "stroke-width": 3.5 }, svg);
}
function passLegend(svg, x0, y, acc) {
  [["comp", "COMPLETE"], ["inc", "INCOMPLETE"], ["td", "TOUCHDOWN"], ["int", "INTERCEPTION"]].forEach(([k, l], i) => {
    const x = x0 + i * 135; passDot(svg, x, y - 5, k, acc); txt(svg, x + 16, y, l, { "font-size": 14, "font-weight": 800, fill: C.tick });
  });
}
function heatKey(svg, x, y) {
  el("rect", { x, y: y - 12, width: 18, height: 13, fill: RED, opacity: 0.75 }, svg); txt(svg, x + 24, y, "WORSE THAN LEAGUE", { "font-size": 14, "font-weight": 800, fill: C.tick });
  el("rect", { x: x + 200, y: y - 12, width: 18, height: 13, fill: GREEN, opacity: 0.75 }, svg); txt(svg, x + 224, y, "BETTER", { "font-size": 14, "font-weight": 800, fill: C.tick });
}
function passchart(c) {
  const svg = newSvg(640), ao = T(c.off).accent, ad = T(c.def).accent;
  const L = pfield(svg, 250, { title: `${T(c.off).nick} passes`.toUpperCase(), col: ao });
  const ord = { inc: 0, comp: 1, int: 2, td: 3 };
  c.dots.filter(d => d.y <= 42 && d.y >= -8).sort((a, b) => ord[a.r] - ord[b.r]).forEach(d => { const [x, y] = L.P(d.x, d.y); passDot(svg, x, y, d.r, ao); });
  const R = pfield(svg, 750, { title: `${T(c.def).nick} D: completion % allowed`.toUpperCase(), col: ad });
  const band = { "BEHIND": [-8, 0], "0-9": [0, 10], "10-19": [10, 20], "20+": [20, 42] }, lane = { left: [-1.1, -0.37], middle: [-0.37, 0.37], right: [0.37, 1.1] };
  c.cells.forEach(q => {
    const [d0, d1] = band[q.band], [x0, x1] = lane[q.lane], pts = [R.P(x0, d0), R.P(x1, d0), R.P(x1, d1), R.P(x0, d1)].map(p => p.join(",")).join(" ");
    const rel = q.comp === null ? 0 : q.comp - q.lg;
    el("polygon", { points: pts, fill: rel >= 0 ? RED : GREEN, opacity: Math.min(0.8, 0.1 + Math.abs(rel) * 3.2).toFixed(2), stroke: "#0B0B0C", "stroke-width": 3 }, svg);
    if (`${q.band}|${q.lane}` === c.hl) el("polygon", { points: pts, fill: "none", stroke: "#F4F4F2", "stroke-width": 4 }, svg);
    const [cx, cy] = R.P((x0 + x1) / 2, (d0 + d1) / 2);
    txt(svg, cx, cy + 4, q.comp === null ? "–" : Math.round(q.comp * 100) + "%", { "text-anchor": "middle", "font-size": 26, style: "font-family:var(--num)", "font-weight": 600, fill: "#F4F4F2" });
    txt(svg, cx, cy + 26, `avg ${Math.round(q.lg * 100)}% · ${q.n}`, { "text-anchor": "middle", "font-size": 13, "font-weight": 600, fill: "#D0D0D4" });
  });
  passLegend(svg, 40, 630, ao); heatKey(svg, 620, 630);
  return svg;
}
function rcvchart(c) {
  const svg = newSvg(640), acc = T(c.team).accent;
  const F = pfield(svg, 500, { title: `${c.name}: every target`.toUpperCase(), col: acc, w0: 300, w1: 200 });
  const ord = { inc: 0, comp: 1, int: 2, td: 3 };
  c.dots.filter(d => d.y <= 42 && d.y >= -8).sort((a, b) => ord[a.r] - ord[b.r]).forEach(d => { const [x, y] = F.P(d.x, d.y); passDot(svg, x, y, d.r, acc, 1.2); });
  passLegend(svg, 230, 630, acc);
  return svg;
}
function runchart(c) {
  const svg = newSvg(640), ao = T(c.off).accent, ad = T(c.def).accent, n = c.gaps.length;
  const short = ["L END", "L TKL", "L GRD", "MID", "R GRD", "R TKL", "R END"];
  const gx = g => -1.1 + (g + 0.5) * 2.2 / n;
  const L = pfield(svg, 250, { d0: -6, d1: 30, title: `${T(c.off).nick} runs`.toUpperCase(), col: ao, lanes: short });
  c.dots.forEach(d => {
    const [x, y] = L.P(gx(d.g) + d.x * 2.2 / n, d.y);
    if (d.y <= 0) el("circle", { cx: x, cy: y, r: 6, fill: "none", stroke: RED, "stroke-width": 2 }, svg);
    else if (d.y >= 10) { el("circle", { cx: x, cy: y, r: 10, fill: "none", stroke: "#F4F4F2", "stroke-width": 2.5 }, svg); el("circle", { cx: x, cy: y, r: 6, fill: ao }, svg); }
    else el("circle", { cx: x, cy: y, r: 6, fill: ao, opacity: 0.85 }, svg);
  });
  const R = pfield(svg, 750, { d0: -6, d1: 30, title: `${T(c.def).nick} D: yards per carry allowed`.toUpperCase(), col: ad, lanes: short });
  c.cells.forEach((q, i) => {
    const x0 = -1.1 + i * 2.2 / n, x1 = x0 + 2.2 / n, pts = [R.P(x0, 0), R.P(x1, 0), R.P(x1, 30), R.P(x0, 30)].map(p => p.join(",")).join(" ");
    const rel = q.ypc === null ? 0 : q.ypc - q.lg;
    el("polygon", { points: pts, fill: rel >= 0 ? RED : GREEN, opacity: Math.min(0.8, 0.1 + Math.abs(rel) * 0.28).toFixed(2), stroke: "#0B0B0C", "stroke-width": 3 }, svg);
    if (q.gap === c.hl) el("polygon", { points: pts, fill: "none", stroke: "#F4F4F2", "stroke-width": 4 }, svg);
    const [cx, cy] = R.P((x0 + x1) / 2, 6);
    txt(svg, cx, cy, q.ypc === null ? "–" : q.ypc.toFixed(1), { "text-anchor": "middle", "font-size": 24, style: "font-family:var(--num)", "font-weight": 600, fill: "#F4F4F2" });
    txt(svg, cx, cy + 22, `avg ${q.lg.toFixed(1)}`, { "text-anchor": "middle", "font-size": 12, "font-weight": 600, fill: "#D0D0D4" });
    txt(svg, cx, cy + 40, `${q.n}`, { "text-anchor": "middle", "font-size": 12, "font-weight": 600, fill: "#9C9CA0" });
  });
  el("circle", { cx: 46, cy: 625, r: 6, fill: ao }, svg); txt(svg, 60, 630, "1-9 YARDS", { "font-size": 14, "font-weight": 800, fill: C.tick });
  el("circle", { cx: 176, cy: 625, r: 10, fill: "none", stroke: "#F4F4F2", "stroke-width": 2.5 }, svg); el("circle", { cx: 176, cy: 625, r: 6, fill: ao }, svg);
  txt(svg, 192, 630, "10+ YARDS", { "font-size": 14, "font-weight": 800, fill: C.tick });
  el("circle", { cx: 312, cy: 625, r: 6, fill: "none", stroke: RED, "stroke-width": 2 }, svg); txt(svg, 326, 630, "NO GAIN OR LOSS", { "font-size": 14, "font-weight": 800, fill: C.tick });
  heatKey(svg, 620, 630);
  return svg;
}
function drives(c) {
  const rowsN = Math.max(...c.teams.map(t => t.rows.length)), rh = 18, h = 130 + rowsN * rh, svg = newSvg(h);
  const COL = res => /Touchdown/.test(res) ? "TD" : /Field goal/.test(res) ? "FG" : /Punt/.test(res) ? "PUNT" : /End of half|Opp touchdown/.test(res) ? "END" : "TO";
  c.teams.forEach((tm, k) => {
    const x0 = k ? 530 : 40, x1 = x0 + 430, X = v => x0 + (x1 - x0) * v / 100, acc = T(tm.team).accent;
    txt(svg, x0, 36, `${T(tm.team).nick}: ${tm.ppd.toFixed(1)} points per drive`.toUpperCase(), { "font-size": 18, "font-weight": 900, fill: acc });
    el("rect", { x: x0, y: 54, width: x1 - x0, height: rowsN * rh + 10, fill: "#16161A", rx: 6 }, svg);
    [0, 20, 50, 80, 100].forEach(v => el("line", { x1: X(v), x2: X(v), y1: 54, y2: 64 + rowsN * rh, stroke: v === 50 ? "#3A3A42" : "#26262C", "stroke-width": v === 50 ? 2 : 1 }, svg));
    [[0, "OWN GOAL", "start"], [50, "50", "middle"], [100, "END ZONE", "end"]].forEach(([v, l, an]) => txt(svg, X(v), 84 + rowsN * rh, l, { "text-anchor": an, "font-size": 12, "font-weight": 800, fill: C.tick }));
    let wk = null;
    tm.rows.forEach((r, i) => {
      const y = 60 + i * rh, kind = COL(r.res);
      if (r.wk !== wk) { wk = r.wk; if (i) el("line", { x1: x0, x2: x1, y1: y - 1, y2: y - 1, stroke: "#3A3A42", "stroke-width": 1.5, "stroke-dasharray": "4 4" }, svg); }
      const fill = kind === "TD" ? acc : kind === "FG" ? acc : kind === "TO" ? RED : "#55555B", op = kind === "FG" ? 0.5 : 1;
      el("rect", { x: X(Math.min(r.s, r.e)), y: y + 2, width: Math.max(4, Math.abs(X(r.e) - X(r.s))), height: rh - 6, rx: 3, fill, opacity: op }, svg);
    });
  });
  const lg = [["TOUCHDOWN", T(c.teams[0].team).accent, 1], ["FIELD GOAL", T(c.teams[0].team).accent, 0.5], ["TURNOVER OR DOWNS", RED, 1], ["PUNT OR END OF HALF", "#55555B", 1]];
  lg.forEach(([l, col, op], i) => { const x = 40 + i * 230; el("rect", { x, y: h - 24, width: 22, height: 12, rx: 3, fill: col, opacity: op }, svg); txt(svg, x + 30, h - 13, l, { "font-size": 14, "font-weight": 800, fill: C.tick }); });
  return svg;
}
function fourthmap(c) {
  const svg = newSvg(620), acc = T(c.team).accent, box = { l: 150, r: W - 30, t: 40, b: 520 }, nx = c.xl.length, ny = c.yl.length;
  const cw = (box.r - box.l) / nx, chh = (box.b - box.t) / ny, X = i => box.l + i * cw, Y = j => box.t + j * chh;
  c.bg.forEach(q => {
    el("rect", { x: X(q.x) + 3, y: Y(q.y) + 3, width: cw - 6, height: chh - 6, rx: 8, fill: "#F4F4F2", opacity: (0.03 + q.go * 0.32).toFixed(2) }, svg);
    txt(svg, X(q.x) + cw - 12, Y(q.y) + 22, `lg ${Math.round(q.go * 100)}% go`, { "text-anchor": "end", "font-size": 13, "font-weight": 700, fill: "#9C9CA0" });
  });
  c.pts.forEach(p => {
    const x = X(p.x) + cw / 2 + p.j * cw * 0.8, y = Y(p.y) + chh / 2 + 8 + p.k * chh * 0.6;
    if (p.d === "go") el("circle", { cx: x, cy: y, r: 9, fill: acc, stroke: "#0B0B0C", "stroke-width": 2 }, svg);
    else if (p.d === "punt") el("circle", { cx: x, cy: y, r: 7, fill: "none", stroke: "#9C9CA0", "stroke-width": 2 }, svg);
    else el("rect", { x: x - 6, y: y - 6, width: 12, height: 12, fill: "none", stroke: "#F4F4F2", "stroke-width": 2, transform: `rotate(45 ${x} ${y})` }, svg);
  });
  c.xl.forEach((l, i) => txt(svg, X(i) + cw / 2, box.b + 28, l, { "text-anchor": "middle", "font-size": 15, "font-weight": 800, fill: C.tick }));
  c.yl.forEach((l, j) => txt(svg, box.l - 16, Y(j) + chh / 2 + 6, l, { "text-anchor": "end", "font-size": 18, "font-weight": 800, fill: C.tick }));
  txt(svg, 30, (box.t + box.b) / 2, "YARDS TO GO", { "font-size": 16, "font-weight": 900, fill: C.title, transform: `rotate(-90 30 ${(box.t + box.b) / 2})`, "text-anchor": "middle" });
  txt(svg, (box.l + box.r) / 2, box.b + 56, "FIELD POSITION → (DRIVING TOWARD THE END ZONE)", { "text-anchor": "middle", "font-size": 15, "font-weight": 900, fill: C.title });
  [["go", "WENT FOR IT"], ["punt", "PUNTED"], ["fg", "FIELD GOAL"]].forEach(([k, l], i) => {
    const x = box.l + i * 170, y = 604;
    if (k === "go") el("circle", { cx: x, cy: y - 5, r: 8, fill: acc }, svg); else if (k === "punt") el("circle", { cx: x, cy: y - 5, r: 7, fill: "none", stroke: "#9C9CA0", "stroke-width": 2 }, svg);
    else el("rect", { x: x - 6, y: y - 11, width: 12, height: 12, fill: "none", stroke: "#F4F4F2", "stroke-width": 2, transform: `rotate(45 ${x} ${y - 5})` }, svg);
    txt(svg, x + 16, y, l, { "font-size": 14, "font-weight": 800, fill: C.tick });
  });
  return svg;
}

/* ---------- second batch of visuals ---------- */
function relFill(rel, k) { return { fill: rel >= 0 ? RED : GREEN, opacity: Math.min(0.8, 0.1 + Math.abs(rel) * k).toFixed(2) }; }
function redzone(c) {
  const svg = newSvg(620), ao = T(c.off).accent, ad = T(c.def).accent;
  // flat close-up field: goal line at top, the 20 at the bottom
  const panel = (x0, title, col) => {
    const w = 400, top = 90, bot = 540, Y = yl => top + (yl / 20) * (bot - top), X = x => x0 + w / 2 + x * w / 2.4;
    txt(svg, x0 + w / 2, 40, title, { "text-anchor": "middle", "font-size": 20, "font-weight": 900, fill: col, "letter-spacing": ".06em" });
    el("rect", { x: x0, y: top - 50, width: w, height: 50, fill: col, opacity: 0.18, rx: 6 }, svg);
    txt(svg, x0 + w / 2, top - 18, "END ZONE", { "text-anchor": "middle", "font-size": 16, "font-weight": 900, fill: col, opacity: 0.9 });
    el("rect", { x: x0, y: top, width: w, height: bot - top, fill: "#16161A", stroke: "#2A2A30", "stroke-width": 2 }, svg);
    for (let yl = 5; yl <= 20; yl += 5) { el("line", { x1: x0, x2: x0 + w, y1: Y(yl), y2: Y(yl), stroke: "#2E2E35", "stroke-width": yl % 10 ? 1 : 2 }, svg); txt(svg, x0 - 10, Y(yl) + 6, String(yl), { "text-anchor": "end", "font-size": 16, "font-weight": 800, fill: C.tick }); }
    return { Y, X, w, top, bot };
  };
  const L = panel(60, `${T(c.off).nick} inside the 20`.toUpperCase(), ao);
  c.dots.forEach(d => {
    const x = L.X(d.x), y = L.Y(d.y);
    if (d.p) el("circle", { cx: x, cy: y, r: d.td ? 9 : 6, fill: d.td ? ao : "none", stroke: d.td ? "#F4F4F2" : ao, "stroke-width": d.td ? 2.5 : 2 }, svg);
    else el("rect", { x: x - 6, y: y - 6, width: 12, height: 12, fill: d.td ? ao : "none", stroke: d.td ? "#F4F4F2" : ao, "stroke-width": d.td ? 2.5 : 2 }, svg);
  });
  const R = panel(540, `${T(c.def).nick} D: TD rate allowed`.toUpperCase(), ad);
  const bands = { "1-5": [0, 5], "6-10": [5, 10], "11-20": [10, 20] };
  c.cells.forEach(q => {
    const [a0, a1] = bands[q.band], f = relFill(q.v === null ? 0 : q.v - q.lg, 2.2);
    el("rect", { x: 542, y: R.Y(a0) + 2, width: R.w - 4, height: R.Y(a1) - R.Y(a0) - 4, ...f }, svg);
    const cy = (R.Y(a0) + R.Y(a1)) / 2;
    txt(svg, 540 + R.w / 2, cy + 6, q.v === null ? "–" : Math.round(q.v * 100) + "% TD", { "text-anchor": "middle", "font-size": 26, style: "font-family:var(--num)", "font-weight": 600, fill: "#F4F4F2" });
    txt(svg, 540 + R.w / 2, cy + 28, `per play inside the ${q.band.split("-")[1]} · avg ${Math.round(q.lg * 100)}% · ${q.n}`, { "text-anchor": "middle", "font-size": 13, "font-weight": 600, fill: "#D0D0D4" });
  });
  [["PASS", "circle"], ["RUN", "rect"], ["TOUCHDOWN", "td"]].forEach(([l, k], i) => {
    const x = 70 + i * 120, y = 590;
    if (k === "circle") el("circle", { cx: x, cy: y - 5, r: 6, fill: "none", stroke: ao, "stroke-width": 2 }, svg);
    else if (k === "rect") el("rect", { x: x - 6, y: y - 11, width: 12, height: 12, fill: "none", stroke: ao, "stroke-width": 2 }, svg);
    else el("circle", { cx: x, cy: y - 5, r: 9, fill: ao, stroke: "#F4F4F2", "stroke-width": 2.5 }, svg);
    txt(svg, x + 16, y, l, { "font-size": 14, "font-weight": 800, fill: C.tick });
  });
  heatKey(svg, 560, 590);
  return svg;
}
function downs(c) {
  const svg = newSvg(560), dists = ["1-3", "4-7", "8+"], dn = ["1ST", "2ND", "3RD"], dl = ["SHORT (1-3)", "MEDIUM (4-7)", "LONG (8+)"];
  const grid = (x0, cells, title, col, off) => {
    const cw = 130, ch = 130, top = 90;
    txt(svg, x0 + 1.5 * cw + 50, 40, title, { "text-anchor": "middle", "font-size": 20, "font-weight": 900, fill: col, "letter-spacing": ".06em" });
    dl.forEach((l, j) => txt(svg, x0 + 50 + (j + 0.5) * cw, top - 12, l, { "text-anchor": "middle", "font-size": 13, "font-weight": 900, fill: C.tick }));
    dn.forEach((l, i) => txt(svg, x0 + 40, top + (i + 0.5) * ch + 6, l, { "text-anchor": "end", "font-size": 16, "font-weight": 900, fill: C.tick }));
    cells.forEach(q => {
      const [d, ds] = q.cell.split("|"), i = +d - 1, j = dists.indexOf(ds), x = x0 + 50 + j * cw, y = top + i * ch;
      const rel = q.sr === null ? 0 : (off ? q.sr - q.lg : q.sr - q.lg), f = relFill(off ? -rel : rel, 3.5);
      el("rect", { x: x + 3, y: y + 3, width: cw - 6, height: ch - 6, rx: 8, ...(off ? { fill: rel >= 0 ? GREEN : RED, opacity: f.opacity } : f) }, svg);
      if (q.cell === c.hl) el("rect", { x: x + 3, y: y + 3, width: cw - 6, height: ch - 6, rx: 8, fill: "none", stroke: "#F4F4F2", "stroke-width": 4 }, svg);
      txt(svg, x + cw / 2, y + ch / 2, q.sr === null ? "–" : Math.round(q.sr * 100) + "%", { "text-anchor": "middle", "font-size": 30, style: "font-family:var(--num)", "font-weight": 600, fill: "#F4F4F2" });
      txt(svg, x + cw / 2, y + ch / 2 + 24, `avg ${Math.round(q.lg * 100)}%`, { "text-anchor": "middle", "font-size": 13, "font-weight": 600, fill: "#D0D0D4" });
      if (off && q.pr !== null) txt(svg, x + cw / 2, y + ch / 2 + 42, `${Math.round(q.pr * 100)}% pass`, { "text-anchor": "middle", "font-size": 13, "font-weight": 600, fill: "#BDBDBD" });
    });
  };
  grid(20, c.o, `${T(c.off).nick} offense: success rate`.toUpperCase(), T(c.off).accent, true);
  grid(510, c.d, `${T(c.def).nick} D: success allowed`.toUpperCase(), T(c.def).accent, false);
  el("rect", { x: 70, y: 512, width: 18, height: 13, fill: GREEN, opacity: 0.75 }, svg); txt(svg, 94, 524, "GOOD FOR THAT TEAM", { "font-size": 14, "font-weight": 800, fill: C.tick });
  el("rect", { x: 300, y: 512, width: 18, height: 13, fill: RED, opacity: 0.75 }, svg); txt(svg, 324, 524, "BAD FOR THAT TEAM", { "font-size": 14, "font-weight": 800, fill: C.tick });
  return svg;
}
function explmap(c) {
  const svg = newSvg(640), ao = T(c.off).accent, ad = T(c.def).accent, x0 = 70, x1 = W - 40, X = v => x0 + (x1 - x0) * v / 100;
  const panel = (y0, title, col, arr) => {
    const h = 220, laneY = l => y0 + h / 2 + l * (h / 3.2);
    txt(svg, x0, y0 - 12, title, { "font-size": 18, "font-weight": 900, fill: col, "letter-spacing": ".05em" });
    el("rect", { x: x0, y: y0, width: x1 - x0, height: h, fill: "#16161A", rx: 6 }, svg);
    el("rect", { x: X(100) - 1, y: y0, width: 40, height: h, fill: col, opacity: 0.15 }, svg);
    for (let v = 10; v < 100; v += 10) el("line", { x1: X(v), x2: X(v), y1: y0, y2: y0 + h, stroke: v === 50 ? "#3A3A42" : "#26262C", "stroke-width": v === 50 ? 2 : 1 }, svg);
    arr.forEach(a => {
      const y = laneY(a.l + a.j * 0.5), xs = X(a.s), xe = X(a.e);
      el("line", { x1: xs, x2: xe - 6, y1: y, y2: y, stroke: col, "stroke-width": a.p ? 3 : 4, opacity: 0.85, "stroke-dasharray": a.p ? null : "2 0" }, svg);
      el("path", { d: `M${xe},${y}L${xe - 10},${y - 6}L${xe - 10},${y + 6}Z`, fill: a.td ? "#F4F4F2" : col }, svg);
      el("circle", { cx: xs, cy: y, r: 4, fill: a.p ? col : "#0B0B0C", stroke: col, "stroke-width": 2 }, svg);
    });
    return h;
  };
  panel(60, `${T(c.off).nick} offense: ${c.a.length} plays of 20+ yards`.toUpperCase(), ao, c.a);
  panel(345, `${T(c.def).nick} defense: ${c.b.length} allowed`.toUpperCase(), ad, c.b);
  [[0, "OWN GOAL", "start"], [50, "50", "middle"], [100, "END ZONE", "end"]].forEach(([v, l, an]) => txt(svg, X(v), 590, l, { "text-anchor": an, "font-size": 13, "font-weight": 800, fill: C.tick }));
  txt(svg, x0, 622, "● PASS (DOT AT THE SNAP)   ○ RUN   WHITE TIP = TOUCHDOWN   DRIVING LEFT TO RIGHT", { "font-size": 13, "font-weight": 800, fill: C.tick });
  return svg;
}
function wpline(c) {
  const svg = newSvg(650), box = { l: 90, r: W - 40, t: 50, b: 520 }, X = s => box.l + (box.r - box.l) * s / 3600, Y = p => box.b - (box.b - box.t) * p;
  [0, 0.25, 0.5, 0.75, 1].forEach(p => { el("line", { x1: box.l, x2: box.r, y1: Y(p), y2: Y(p), stroke: p === 0.5 ? "#55555B" : C.grid, "stroke-width": p === 0.5 ? 2 : 1, "stroke-dasharray": p === 0.5 ? "8 6" : null }, svg);
    txt(svg, box.l - 12, Y(p) + 6, Math.round(p * 100) + "%", { "text-anchor": "end", "font-size": 18, "font-weight": 300, fill: C.tick }); });
  [900, 1800, 2700].forEach(s => el("line", { x1: X(s), x2: X(s), y1: box.t, y2: box.b, stroke: C.grid }, svg));
  ["Q1", "Q2", "Q3", "Q4"].forEach((q, i) => txt(svg, X(450 + i * 900), box.b + 30, q, { "text-anchor": "middle", "font-size": 18, "font-weight": 900, fill: C.tick }));
  const legend = [];
  c.teams.forEach((tm, k) => tm.games.forEach((g, i) => {
    const col = T(tm.team).accent, dash = i === tm.games.length - 1 ? null : "8 6";
    el("polyline", { points: g.pts.map(p => `${X(p[0])},${Y(p[1])}`).join(" "), fill: "none", stroke: col, "stroke-width": i === tm.games.length - 1 ? 4.5 : 3, "stroke-dasharray": dash, opacity: i === tm.games.length - 1 ? 1 : 0.7 }, svg);
    legend.push([col, dash, `${tm.team} WK ${g.wk} vs ${g.opp}: ${g.won ? "W" : "L"}`]);
  }));
  legend.forEach(([col, dash, l], i) => { const x = box.l + (i % 2) * 440, y = 592 + Math.floor(i / 2) * 26;
    el("line", { x1: x, x2: x + 34, y1: y - 5, y2: y - 5, stroke: col, "stroke-width": 4, "stroke-dasharray": dash }, svg); txt(svg, x + 44, y, l, { "font-size": 14, "font-weight": 800, fill: C.tick }); });
  return svg;
}
function quarters(c) {
  const svg = newSvg(560), mid = 290, sc = 18, all = c.rows.flatMap(r => r.for.concat(r.against)), mx = Math.max(7, ...all);
  const k = 220 / mx;
  el("line", { x1: 60, x2: W - 30, y1: mid, y2: mid, stroke: "#55555B", "stroke-width": 2 }, svg);
  txt(svg, 50, mid - 200, "SCORED", { "text-anchor": "end", "font-size": 14, "font-weight": 900, fill: C.tick, transform: `rotate(-90 50 ${mid - 200})` });
  txt(svg, 50, mid + 200, "ALLOWED", { "text-anchor": "end", "font-size": 14, "font-weight": 900, fill: C.tick, transform: `rotate(-90 50 ${mid + 120})` });
  const gw = (W - 120) / 4, bw = gw * 0.3;
  [0, 1, 2, 3].forEach(q => {
    const gx = 80 + q * gw;
    if (q === c.hl) el("rect", { x: gx - 8, y: 40, width: gw - 14, height: 480, rx: 10, fill: "#F4F4F2", opacity: 0.05 }, svg);
    txt(svg, gx + gw / 2 - 10, 540, ["1ST", "2ND", "3RD", "4TH"][q] + " QTR", { "text-anchor": "middle", "font-size": 16, "font-weight": 900, fill: C.title });
    c.rows.forEach((r, i) => {
      const col = T(r.team).accent, x = gx + 20 + i * (bw + 12);
      el("rect", { x, y: mid - r.for[q] * k, width: bw, height: r.for[q] * k, fill: col, rx: 4 }, svg);
      el("rect", { x, y: mid, width: bw, height: r.against[q] * k, fill: col, opacity: 0.45, rx: 4 }, svg);
      txt(svg, x + bw / 2, mid - r.for[q] * k - 10, r.for[q].toFixed(1), { "text-anchor": "middle", "font-size": 18, style: "font-family:var(--num)", "font-weight": 600, fill: col });
      txt(svg, x + bw / 2, mid + r.against[q] * k + 24, r.against[q].toFixed(1), { "text-anchor": "middle", "font-size": 18, style: "font-family:var(--num)", "font-weight": 600, fill: col, opacity: 0.85 });
      if (q === 0) txt(svg, x + bw / 2, 30, r.team, { "text-anchor": "middle", "font-size": 14, "font-weight": 900, fill: col });
    });
  });
  return svg;
}
function tree(c) {
  const svg = newSvg(620), box = { t: 60, b: 540 }, all = c.teams.flatMap(t => t.players.map(p => p.adot)), mx = Math.max(15, ...all) + 2, mn = Math.min(0, ...all) - 1;
  const Y = v => box.b - (box.b - box.t) * (v - mn) / (mx - mn);
  c.teams.forEach((tm, k) => {
    const x0 = k ? 540 : 80, w = 400, col = T(tm.team).accent;
    txt(svg, x0 + w / 2, 30, `${T(tm.team).nick} targets`.toUpperCase(), { "text-anchor": "middle", "font-size": 18, "font-weight": 900, fill: col });
    el("line", { x1: x0 + w / 2, x2: x0 + w / 2, y1: Y(mn), y2: Y(mx), stroke: "#2E2E35", "stroke-width": 3 }, svg);
    tm.players.forEach((p, i) => {
      const x = x0 + (i + 0.5) * w / tm.players.length, y = Y(p.adot), r = 12 + p.share * 80, below = i % 2 === 0;
      el("line", { x1: x0 + w / 2, y1: Y(0), x2: x, y2: y, stroke: col, "stroke-width": 2, opacity: 0.4 }, svg);
      el("circle", { cx: x, cy: y, r, fill: p.epa >= 0 ? col : RED, opacity: 0.25 + Math.min(0.6, Math.abs(p.epa) * 1.5), stroke: col, "stroke-width": 2.5 }, svg);
      txt(svg, x, y + 6, Math.round(p.share * 100) + "%", { "text-anchor": "middle", "font-size": 18, style: "font-family:var(--num)", "font-weight": 600, fill: "#F4F4F2" });
      const ly = below ? y + r + 20 : y - r - 26;
      txt(svg, x, ly, p.short, { "text-anchor": "middle", "font-size": 14, "font-weight": 900, fill: C.title });
      txt(svg, x, ly + 16, `${p.adot.toFixed(1)} yds · ${fmt(p.epa, "epa")}`, { "text-anchor": "middle", "font-size": 12, "font-weight": 600, fill: C.tick });
    });
  });
  [0, 10, 20].filter(v => v >= mn && v <= mx).forEach(v => txt(svg, 40, Y(v) + 5, v ? `+${v}` : "LOS", { "text-anchor": "middle", "font-size": 14, "font-weight": 800, fill: v ? C.tick : "#5B8DEF" }));
  txt(svg, W / 2, 600, "HEIGHT = AVERAGE DEPTH OF TARGET · SIZE = SHARE OF TARGETS · RED = NEGATIVE EPA PER TARGET", { "text-anchor": "middle", "font-size": 13, "font-weight": 800, fill: C.tick });
  return svg;
}
function tug(c) {
  const svg = newSvg(420), x0 = 70, x1 = W - 40, X = v => x0 + (x1 - x0) * v / 100;
  el("rect", { x: x0, y: 70, width: x1 - x0, height: 250, fill: "#16161A", rx: 8 }, svg);
  for (let v = 10; v < 100; v += 10) el("line", { x1: X(v), x2: X(v), y1: 70, y2: 320, stroke: v === 50 ? "#3A3A42" : "#26262C", "stroke-width": v === 50 ? 2 : 1 }, svg);
  dashed(svg, X(c.lg), 60, X(c.lg), 330); txt(svg, X(c.lg), 52, `LEAGUE AVG: OWN ${Math.round(c.lg)}`, { "text-anchor": "middle", "font-size": 13, "font-weight": 800, fill: C.quad });
  c.rows.forEach((r, i) => {
    const y = 140 + i * 110, col = T(r.team).accent;
    el("line", { x1: X(Math.min(r.own, r.opp)), x2: X(Math.max(r.own, r.opp)), y1: y, y2: y, stroke: col, "stroke-width": 6, opacity: 0.5 }, svg);
    el("circle", { cx: X(r.own), cy: y, r: 14, fill: col }, svg);
    el("circle", { cx: X(r.opp), cy: y, r: 12, fill: "#0B0B0C", stroke: col, "stroke-width": 3 }, svg);
    txt(svg, X(r.own), y - 24, `${r.team} START: OWN ${Math.round(r.own)}`, { "text-anchor": "middle", "font-size": 15, "font-weight": 900, fill: col });
    txt(svg, X(r.opp), y + 38, `OPPONENTS: ${Math.round(r.opp)}`, { "text-anchor": "middle", "font-size": 14, "font-weight": 800, fill: C.tick });
  });
  [[0, "OWN GOAL", "start"], [50, "50", "middle"], [100, "END ZONE", "end"]].forEach(([v, l, an]) => txt(svg, X(v), 350, l, { "text-anchor": an, "font-size": 13, "font-weight": 800, fill: C.tick }));
  txt(svg, x0, 395, "● THE TEAM'S OWN DRIVES   ○ ITS OPPONENTS' DRIVES   (BOTH MEASURED FROM THE DRIVING TEAM'S GOAL LINE)", { "font-size": 13, "font-weight": 800, fill: C.tick });
  return svg;
}
function thirds(c) {
  const svg = newSvg(520), x0 = 90, x1 = W - 40, X = v => x0 + (x1 - x0) * (v - 0.5) / 15;
  const row = (y, arr, col, title) => {
    txt(svg, x0, y - 80, title, { "font-size": 18, "font-weight": 900, fill: col, "letter-spacing": ".05em" });
    el("rect", { x: x0, y: y - 60, width: x1 - x0, height: 120, fill: "#16161A", rx: 8 }, svg);
    arr.forEach(d => { const x = X(d.x) + d.j * 22, yy = y + (d.c ? -25 : 25) + d.j * 30;
      if (d.c) el("circle", { cx: x, cy: yy, r: 6, fill: col }, svg); else el("circle", { cx: x, cy: yy, r: 5.5, fill: "none", stroke: "#8A8A90", "stroke-width": 1.8 }, svg); });
    txt(svg, x0 - 10, y - 20, "MADE", { "text-anchor": "end", "font-size": 12, "font-weight": 900, fill: C.tick });
    txt(svg, x0 - 10, y + 30, "FAILED", { "text-anchor": "end", "font-size": 12, "font-weight": 900, fill: C.tick });
  };
  const rate = a => a.length ? Math.round(100 * a.filter(d => d.c).length / a.length) : 0;
  row(150, c.a, T(c.off).accent, `${T(c.off).nick} offense on 3rd down: ${rate(c.a)}% converted`.toUpperCase());
  row(370, c.b, T(c.def).accent, `${T(c.def).nick} defense on 3rd down: ${rate(c.b)}% allowed`.toUpperCase());
  for (let v = 1; v <= 15; v += 1) if (v === 1 || v % 2 === 1 || v === 15) txt(svg, X(v), 470, v === 15 ? "15+" : String(v), { "text-anchor": "middle", "font-size": 14, "font-weight": 800, fill: C.tick });
  txt(svg, (x0 + x1) / 2, 500, "YARDS TO GO", { "text-anchor": "middle", "font-size": 15, "font-weight": 900, fill: C.title });
  return svg;
}
function penalties(c) {
  const svg = newSvg(480), mx = Math.max(0.5, ...c.rows.flatMap(r => r.types.map(t => t.v)));
  c.rows.forEach((r, k) => {
    const x0 = k ? 520 : 40, w = 440, col = T(r.team).accent;
    txt(svg, x0, 40, `${T(r.team).nick}: ${r.per_game.toFixed(1)} flags per game`.toUpperCase(), { "font-size": 18, "font-weight": 900, fill: col });
    r.types.forEach((t, i) => {
      const y = 80 + i * 74, bw = (w - 60) * t.v / mx;
      txt(svg, x0, y + 16, t.k.toUpperCase(), { "font-size": 14, "font-weight": 800, fill: C.title });
      el("rect", { x: x0, y: y + 26, width: Math.max(4, bw), height: 26, rx: 4, fill: col, opacity: 0.85 }, svg);
      txt(svg, x0 + bw + 10, y + 46, t.v.toFixed(2), { "font-size": 18, style: "font-family:var(--num)", "font-weight": 600, fill: col });
    });
  });
  txt(svg, 40, 465, "PER GAME, TOP 5 PENALTY TYPES FOR EACH TEAM", { "font-size": 13, "font-weight": 800, fill: C.tick });
  return svg;
}
function splits(c) {
  const svg = newSvg(480), vals = c.rows.flatMap(r => [r.with, r.without]), lo = Math.min(-0.1, ...vals), hi = Math.max(0.1, ...vals);
  const X = lin(lo - 0.05, hi + 0.05, 330, W - 60);
  el("line", { x1: X(0), x2: X(0), y1: 50, y2: 420, stroke: "#55555B", "stroke-width": 2 }, svg);
  txt(svg, X(0), 40, "0 EPA", { "text-anchor": "middle", "font-size": 14, "font-weight": 800, fill: C.tick });
  c.rows.forEach((r, i) => {
    const y = 90 + i * 180, col = T(r.team).accent;
    txt(svg, 40, y + 4, r.label, { "font-size": 17, "font-weight": 900, fill: col });
    [["WITH " + c.word, r.with, 1], ["WITHOUT", r.without, 0.45]].forEach(([l, v, op], j) => {
      const yy = y + 30 + j * 56;
      txt(svg, 40, yy + 26, l, { "font-size": 14, "font-weight": 800, fill: C.title });
      el("rect", { x: Math.min(X(0), X(v)), y: yy, width: Math.max(3, Math.abs(X(v) - X(0))), height: 38, rx: 4, fill: col, opacity: op }, svg);
      txt(svg, v >= 0 ? X(v) + 10 : X(v) - 10, yy + 28, fmt(v, "epa"), { "text-anchor": v >= 0 ? "start" : "end", "font-size": 22, style: "font-family:var(--num)", "font-weight": 600, fill: col });
    });
  });
  txt(svg, 40, 460, "EPA PER DROPBACK · DEFENSE ROWS = WHAT IT ALLOWS", { "font-size": 13, "font-weight": 800, fill: C.tick });
  return svg;
}
const CHARTS = { dumbbell, redzone, downs, explmap, wpline, quarters, tree, tug, thirds, penalties, splits, passchart, runchart, rcvchart, drives, fourthmap, zones, strips, elotrend, pbars, cumline, tline, scatter, pscatter, duel, bars, gaps, splits, trend, pstrip, probbars, waterfall, dist, injuries, units, calib };


/* ---------- card ---------- */
const GLOSS = [
  [/\bEPA\b/i, "epa", "EPA: change in expected points from a play (down, distance, field position, time). 0 = average."],
  [/success/i, "success", "Success rate: share of plays with positive EPA."],
  [/explosive|big-play/i, "explosive", "Explosive: 20+ yard dropbacks or 10+ yard designed runs."],
  [/over expected|PROE|throws (more|early)/i, "proe", "Over expected: actual minus nflverse's expected rate for the same situations."],
  [/completion %|CPOE/i, "cpoe", "CPOE: completion % over expected, given throw depth and situation."],
  [/aDOT|depth of target|air yards/i, "adot", "aDOT: average air yards per pass attempt."],
  [/\bYAC\b/i, "yacoe", "YAC over expected: yards after catch minus nflverse's expected YAC."],
  [/stuff/i, "stuff", "Stuff rate: designed runs for 0 yards or less."],
  [/pressure|QB hit/i, "pressure", "Pressure rate. If charted pressure is unavailable, QB hits + sacks are used instead."],
  [/opponent-adjusted/i, "adjust", "Opponent-adjusted: ridge regression of offense + defense + home field."],
  [/shrunk/i, "shrunk", "Shrunk: small samples pulled toward league average in proportion to noise."],
  [/brier/i, "brier", "Brier score: squared error of win probabilities. Lower is better; 0.250 = coin flip."],
  [/SHAP|factor/i, "shap", "Factor values: each input's push on the projected margin, in points."],
];
function tipHTML(c) {
  const text = [c.t1, c.t2, c.sub, c.note, c.chart.x_label, c.chart.y_label, c.chart.axis].filter(Boolean).join(" ");
  const defs = GLOSS.filter(([re]) => re.test(text)).slice(0, 4);
  return `<b>SOURCE:</b> ${esc(c.source)} · ${esc(c.note)}` + defs.map(d => `<span>${esc(d[2])}</span>`).join("") +
    `<a href="methods.html#${defs[0] ? defs[0][1] : "metrics"}">How we calculate this &rarr;</a>`;
}

function cardEl(c, g) {
  const m = T(c.owner), card = h("article", { class: "card", style: `--acc:${m.accent}` });
  card.innerHTML = `<div class="top"><div class="kicker">${esc(g.kicker)}</div>
    <div class="logos">${logoHTML(g.away)}${logoHTML(g.home)}
      <span class="info-wrap"><button type="button" class="info" aria-label="Source, definitions and method">i</button><span class="tip" role="tooltip">${tipHTML(c)}</span></span></div></div>
    <h3 class="t1">${esc(c.t1)}</h3><h3 class="t2">${esc(c.t2)}</h3>
    <p class="sub">${esc(c.sub)}</p>
    <div class="chart"></div>
    <div class="foot"><small><b>SOURCE: ${esc(c.source)}</b> &middot; ${esc(c.note)}</small>${S.handle ? `<strong>${esc(S.handle)}</strong>` : ""}</div>
    <div class="card-actions"><button type="button" data-act="copy">COPY IMAGE</button><button type="button" data-act="png">PNG</button><button type="button" data-act="link">LINK</button></div>`;
  const f = CHARTS[c.chart.type];
  if (f) $(".chart", card).appendChild(f(c.chart));
  card.querySelector('[data-act="png"]').onclick = () => exportPng(card, c);
  card.querySelector('[data-act="copy"]').onclick = () => copyPng(card);
  card.querySelector('[data-act="link"]').onclick = e => {
    navigator.clipboard?.writeText(shareURL(g.id) + "?card=" + encodeURIComponent(c.id));
    e.target.textContent = "COPIED"; setTimeout(() => (e.target.textContent = "LINK"), 1200);
  };
  card.id = "card-" + c.id.replace(/[^a-z0-9]/gi, "-");
  return card;
}
function shareURL(id) { return (S.idx.site_url || location.href.split("#")[0]) + "g/" + id + ".html"; }
let h2i = null;
async function cardBlob(card) {
  if (!h2i) {
    await new Promise((res, rej) => { const sc = document.createElement("script");
      sc.src = "https://cdn.jsdelivr.net/npm/html-to-image@1.11.11/dist/html-to-image.js"; sc.onload = res; sc.onerror = rej; document.head.appendChild(sc); });
    h2i = window.htmlToImage;
  }
  const stage = h("div", { class: "export-stage" }), clone = card.cloneNode(true);
  clone.querySelector(".card-actions").remove(); clone.querySelector(".info-wrap")?.remove();
  clone.classList.add("exporting"); clone.style.animation = "none"; clone.style.borderRadius = "0"; clone.style.border = "0";
  stage.appendChild(clone); document.body.appendChild(stage);
  try { return await h2i.toBlob(clone, { pixelRatio: 2, backgroundColor: "#0B0B0C", width: 1080 }); }
  finally { stage.remove(); }
}
async function exportPng(card, c) {
  const btn = card.querySelector('[data-act="png"]'); btn.textContent = "\u2026";
  try {
    const url = URL.createObjectURL(await cardBlob(card));
    const a = document.createElement("a"); a.href = url; a.download = (c.id.replace(/[^a-z0-9]/gi, "_") || "card") + ".png"; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  } catch (e) { console.error(e); alert("PNG export failed. Try again after the page finishes loading."); }
  btn.textContent = "PNG";
}
async function copyPng(card) {
  const btn = card.querySelector('[data-act="copy"]');
  if (!navigator.clipboard || !window.ClipboardItem) { btn.textContent = "USE PNG"; setTimeout(() => (btn.textContent = "COPY IMAGE"), 1500); return; }
  btn.textContent = "\u2026";
  try {
    // Safari needs the ClipboardItem created synchronously in the click, with a promise for the data.
    await navigator.clipboard.write([new ClipboardItem({ "image/png": cardBlob(card) })]);
    btn.textContent = "COPIED";
  } catch (e) { console.error(e); btn.textContent = "FAILED"; }
  setTimeout(() => (btn.textContent = "COPY IMAGE"), 1500);
}

/* ---------- views ---------- */
function heatHTML(heat, away, home) {
  return `<div class="heat">${heat.map(x => {
    const opp = x.team === away ? home : away, v = Math.max(-3, Math.min(3, x.edge)), w = Math.abs(v) / 3 * 50;
    const col = v >= 0 ? T(x.team).accent : T(opp).accent;
    return `<div class="heat-row"><span>${x.team} ${x.unit}</span><div class="heat-track" title="${x.team} ${x.unit.toLowerCase()} offense vs ${opp} defense">
      <div class="heat-fill" style="left:${v >= 0 ? 50 : 50 - w}%;width:${w}%;background:${col}"></div></div><em>${sgn(x.edge, 1)}</em></div>`;
  }).join("")}</div>`;
}
function showLoading(msg) {
  $("#app").innerHTML = `<div class="loading" role="status"><svg viewBox="0 0 64 64" aria-hidden="true"><path d="M11 53C11 30 30 11 53 11C53 34 34 53 11 53Z" fill="var(--brand)"/><path d="M25 39L39 25M27 33.5L30.5 37M30.5 30L34 33.5M34 26.5L37.5 30" stroke="#0B0B0C" stroke-width="2.6" stroke-linecap="round"/></svg><span>${esc(msg)}&hellip;</span></div>`;
}
function board() {
  const app = $("#app"), G = S.games;
  const maxLev = Math.max(0.01, ...G.games.map(g => g.leverage));
  let sortBy = "leverage";
  try { sortBy = localStorage.getItem("boardSort") || "leverage"; } catch (e) { /* storage blocked */ }
  const gap = g => g.model && g.model.mkt !== null && g.model.mkt !== undefined ? Math.abs(g.model.p_home - g.model.mkt) : -1;
  const dis = G.games.filter(g => gap(g) >= 0.08).sort((x, y) => gap(y) - gap(x)).slice(0, 3);
  const proj = G.backfill ? `<p class="proj-note">BACKFILLED: built after the season started, using only data from before week ${G.week}. Lines are closing lines. Recaps show how each game went. These picks are not counted in the published track record.</p>` : G.projected ? `<p class="proj-note">PROJECTED: built from data to date. Model numbers use today's ratings and starters with no injury report; most lines are not posted yet. Updates every Thursday, Saturday and Sunday.</p>` : "";
  app.innerHTML = `<div class="board-head"><h1>${G.week === "PO" ? "Playoff" : "Week " + G.week} <span>${G.projected ? "projections" : "matchups"}</span></h1>
    <label class="sortby">SORT <select aria-label="Sort games"><option value="leverage">Playoff leverage</option><option value="gap">Model vs. market gap</option><option value="ko">Kickoff time</option></select></label></div>
    ${dis.length ? `<section class="disagree"><h2>Where the model disagrees most</h2><div>${dis.map(g => {
      const side = g.model.p_home > g.model.mkt ? g.home : g.away, pm = side === g.home ? g.model.p_home : 1 - g.model.p_home, pk = side === g.home ? g.model.mkt : 1 - g.model.mkt;
      return `<a class="dis" href="#/${G.season}/${G.week}/${g.id}?tab=model" style="--acc:${T(side).accent}">${logoHTML(side)}<span><b>${esc(T(side).nick)}</b> model ${Math.round(pm * 100)}% · market ${Math.round(pk * 100)}%</span><em>+${Math.round((pm - pk) * 100)}</em></a>`;
    }).join("")}</div></section>` : ""}
    ${proj}<p class="board-note"><b>Click any game</b> for the full matchup: keys to success, Team, Players, Fantasy and Model cards. Edges: offense vs. opposing defense, in z-units. <a href="methods.html#cards">How it works</a>${G.week === "PO" ? ' · <a href="#/bracket">See the bracket</a>' : ""}</p><div class="grid"></div>`;
  const sel = $(".sortby select", app); sel.value = sortBy;
  sel.onchange = () => { try { localStorage.setItem("boardSort", sel.value); } catch (e) { /* storage blocked */ } board(); };
  const order = [...G.games];
  if (sortBy === "gap") order.sort((x, y) => gap(y) - gap(x));
  else if (sortBy === "ko") order.sort((x, y) => (x.ko || "").localeCompare(y.ko || ""));
  const grid = $(".grid", app);
  order.forEach((g, i) => {
    S.pair = pairColors(g.away, g.home);
    const a = T(g.away), hm = T(g.home), tile = h("a", { class: "tile", href: `#/${G.season}/${G.week}/${g.id}`,
      style: `--a:${a.accent};--h:${hm.accent};--acc:${T(g.tease_owner || g.home).accent};animation-delay:${i * 30}ms` });
    const imp = g.line && g.line.implied ? `${g.away} ${g.line.implied[g.away]} · ${g.home} ${g.line.implied[g.home]}` : "";
    tile.innerHTML = `<div class="tile-meta"><span>${esc(g.kickoff)}${wxHTML(g.weather, false)}</span>${g.primetime ? '<span class="chip prime">PRIMETIME</span>' : ""}</div>
      <div class="teams"><div class="team">${logoHTML(g.away)}<div><b>${esc(a.nick)}</b><small>${g.away}</small></div></div>
      <span class="at">at</span><div class="team home">${logoHTML(g.home)}<div><b>${esc(hm.nick)}</b><small>${g.home}</small></div></div></div>
      ${g.final ? `<div class="line final">FINAL · ${g.away} ${g.final[g.away]} · ${g.home} ${g.final[g.home]}${g.model_ok === true ? '<span class="ok">MODEL ✓</span>' : g.model_ok === false ? '<span class="no">MODEL ✗</span>' : ""}</div>`
        : `<div class="line">${g.line ? esc(g.line.text) : "Line pending"}<span>${esc(imp)}</span></div>`}
      ${heatHTML(g.heat, g.away, g.home)}
      ${g.model ? numsHTML(g.model, g.home, g.away) : ""}
      ${g.tease ? `<p class="tease">${esc(g.tease[0])}<span>${esc(g.tease[1])}</span></p>` : ""}
      <div class="lev" title="Playoff leverage"><i style="width:${(g.leverage / maxLev) * 100}%"></i></div>
      <span class="tile-cta">FULL MATCHUP: KEYS, CARDS &amp; MODEL <b aria-hidden="true">&rarr;</b></span>`;
    const pre = () => getGame(G.season, G.week, g.id).catch(() => {});
    tile.addEventListener("mouseenter", pre, { once: true });
    tile.addEventListener("touchstart", pre, { once: true, passive: true });
    tile.addEventListener("focus", pre, { once: true });
    grid.appendChild(tile);
  });
  S.pair = null;
}
function keyRes(rc, t, i) {
  const r = rc && rc.keys[t] && rc.keys[t][i];
  if (!r) return "";
  if (r.status === "na") return '<span class="kres na">NOT GRADED</span>';
  if (r.status === "low") return `<span class="kres na">TOO FEW PLAYS TO GRADE (${r.n})</span>`;
  return `<span class="kres ${r.status === "won" ? "ok" : "no"}">${r.status === "won" ? "✓ WON" : "✗ LOST"}</span><small class="kval">In the game: ${r.off} ${fmt(r.value, r.fmt)} ${esc(r.label)} (league avg ${fmt(r.avg, r.fmt)}, ${r.n} ${r.label.includes("red-zone") ? "trips" : "plays"})</small>`;
}
// Default card count is even: an odd count rounds up when another card exists (5 -> 6); 5 with no 6th card shows 4.
function evenN(target, avail) {
  let k = Math.min(Math.max(target, 0), avail, 6);
  if (k % 2 && k >= 3) k = avail > k ? k + 1 : k >= 5 ? k - 1 : k;
  return k;
}
const CAT_TEAM = [["FIELD CHARTS", ["passchart", "runchart", "drives", "fourthmap", "redzone", "downs", "explosive_map", "wpline", "quarters", "tug", "thirds", "penalties", "splits"]],
  ["PASSING", ["pass_epa", "early_down", "depth", "yacoe", "play_action", "man_zone", "shell", "zone", "explosive"]],
  ["RUSHING", ["rush_epa", "stuff", "short_yd", "gap", "box"]],
  ["PRESSURE", ["pressure", "four_man", "blitz"]],
  ["TENDENCIES", ["lean", "wr1", "motion", "tackling", "red_zone"]],
  ["SPECIAL TEAMS & 4TH", ["st", "fg", "fourth"]],
  ["FORM & LUCK", ["form", "luck"]]];
const CAT_PLAYER = [["FIELD CHARTS", ["rcvchart", "pressmap", "tree"]], ["QUARTERBACKS", ["qb_"]], ["RUSHING", ["rb"]], ["RECEIVING", ["wr_", "rec_"]]];
function catOf(id, tab) {
  const k = id.split(":")[0], list = tab === "players" ? CAT_PLAYER : CAT_TEAM;
  for (const [name, keys] of list) if (keys.some(x => x.endsWith("_") ? k.startsWith(x) : k === x || (x === "rb" && k.startsWith("rb")))) return name;
  return "OTHER";
}
async function matchup(id, tab, focus) {
  const G = S.games, app = $("#app");
  showLoading("Loading matchup");
  const g = await getGame(G.season, G.week, id);
  S.pair = pairColors(g.away, g.home);
  const a = T(g.away), hm = T(g.home);
  const imp = g.line && g.line.implied ? `Implied: ${g.away} ${g.line.implied[g.away]} · ${g.home} ${g.line.implied[g.home]}` : "";
  const rc = g.recap;
  const call = (lab, c) => c ? `<span class="${c.ok ? "ok" : c.ok === false ? "no" : ""}">${lab}: ${c.team} ${Math.round(c.p * 100)}%${c.ok ? " ✓" : c.ok === false ? " ✗" : ""}</span>` : "";
  const stake = t => g.leverage.p_playoffs && g.leverage.p_playoffs[t] !== undefined
    ? `<span class="chip">${t} playoff odds ${Math.round(g.leverage.p_playoffs[t] * 100)}% · swing ${Math.round(Math.abs(g.leverage.by_team[t] || 0) * 100)} pts</span>` : "";
  app.innerHTML = `<section class="hero" style="--a:${a.accent};--h:${hm.accent}">${wxHTML(g.weather, true)}
      <div class="side">${teamLogoLink(g.away)}<div><h2>${esc(a.nick)}</h2><small>${esc(a.name)}</small></div></div>
      <div class="mid"><div class="k">${esc(g.kickoff)}${g.primetime ? " · PRIMETIME" : ""}${g.backfill ? " · BACKFILLED (PRE-WEEK DATA ONLY)" : g.after_kickoff ? " · BUILT AFTER KICKOFF (PRE-WEEK DATA ONLY)" : ""}</div>
        <div class="ln">${g.line ? esc(g.line.text) : "Line pending"}</div><div class="imp">${esc(imp)}${g.backfill && g.line ? " · closing line" : g.line && g.line_asof ? ` · line as of ${esc(g.line_asof.slice(5, 10).replace("-", "/"))}` : ""}</div>
        ${g.model ? numsHTML({ p_home: g.model.p_home, mkt: g.model.market ? g.model.market.p_home : null, elo: g.elo ? g.elo.p_home : null }, g.home, g.away) : ""}
        <div class="stakes">${stake(g.away)}${stake(g.home)}</div>${g.mode && g.mode !== "live" ? "" : '<button type="button" class="share-btn">COPY SHARE LINK</button>'}</div>
      <div class="side home">${teamLogoLink(g.home)}<div><h2>${esc(hm.nick)}</h2><small>${esc(hm.name)}</small></div></div>
    </section>
    ${rc ? `<section class="recap"><b>FINAL</b><div class="score">${[g.away, g.home].map(t => `<span class="${rc.winner === t ? "w" : ""}">${teamLogoLink(t)}<em>${rc.final[t]}</em></span>`).join("")}</div>
      <p>${esc(rc.text)}</p><div class="calls">${call("MODEL", rc.model)}${call("MARKET", rc.market)}</div></section>` : ""}
    ${g.summary ? `<p class="summary"><b>WHO HAS THE EDGE</b>${esc(g.summary)}<span class="src">${g.summary_src === "llm" ? "AI summary of the keys and cards below, not betting advice." : "Rule-based summary of the keys below."}</span></p>` : ""}
    <section class="keys">${[g.away, g.home].map(t => `<div class="keyset" style="--acc:${T(t).accent}">
      <h3>${teamLogoLink(t)}${esc(T(t).nick)}: 3 keys to success${rc && rc.keys_won[t] && rc.keys_won[t][1] ? ` <small>won ${rc.keys_won[t][0]} of ${rc.keys_won[t][1]}</small>` : ""}</h3><ol>${(g.keys[t] || []).map((k, i) => `<li><i>${i + 1}</i><div>
        <b>${esc(k.phrase)}<em class="${k.favorable ? "up" : "dn"}">${k.favorable ? "EDGE" : "WATCH"}</em></b><p>${esc(k.detail)}</p>${keyRes(rc, t, i)}</div></li>`).join("")}</ol></div>`).join("")}</section>
    <div class="tabs"><div role="tablist"><button role="tab" data-tab="team">TEAM</button><button role="tab" data-tab="players">PLAYERS</button>${(g.fantasy_cards || []).length ? '<button role="tab" data-tab="fantasy">FANTASY</button>' : ""}${(g.model_cards || []).length ? '<button role="tab" data-tab="model">MODEL</button>' : ""}</div>
      <label class="topn">SHOW <select aria-label="How many cards to show"><option value="auto">Top picks</option><option value="10">Top 10</option></select></label></div>
    <div class="catbar" role="group" aria-label="Card types"></div>
    <div class="cards"></div>`;
  if (g.mode && g.mode !== "live") app.insertAdjacentHTML("afterbegin", `<p class="proj-note">PROJECTED${g.round ? " " + esc(g.round.toUpperCase()) : ""} MATCHUP: built from data through week ${g.through_week}. The model uses today's ratings and starters with no injury report. The summary is rule-based.</p>`);
  const sb = $(".share-btn", app);
  if (sb) sb.onclick = e => { navigator.clipboard?.writeText(shareURL(id)); e.target.textContent = "COPIED"; setTimeout(() => (e.target.textContent = "COPY SHARE LINK"), 1200); };
  const topSel = $(".topn select", app);
  try { topSel.value = localStorage.getItem("topn") || "auto"; } catch (e) { /* storage blocked */ }
  let cur = "team";
  const filt = {};
  const show = t => {
    cur = t;
    app.querySelectorAll(".tabs button").forEach(b => b.setAttribute("aria-selected", String(b.dataset.tab === t)));
    const box = $(".cards", app); box.innerHTML = "";
    $(".topn", app).style.visibility = t === "model" || t === "fantasy" ? "hidden" : "visible";
    const all = t === "players" ? g.player_cards : t === "model" ? g.model_cards : t === "fantasy" ? g.fantasy_cards : g.team_cards;
    const n = t === "model" || t === "fantasy" ? evenN(all.length, all.length) : topSel.value === "10" ? 10 : evenN((t === "players" ? g.player_n : g.team_n) ?? all.length, all.length);
    const rec = all.slice(0, n);
    // Category filter: preset = the categories in the ranked default view; turning a category on adds all its cards.
    const F = (filt[t] = filt[t] || { add: new Set(), del: new Set() });
    const cats = [...new Set(all.map(c => catOf(c.id, t)))];
    const active = new Set([...rec.map(c => catOf(c.id, t)), ...F.add].filter(k => !F.del.has(k)));
    const list = all.filter(c => active.has(catOf(c.id, t)) && (rec.includes(c) || F.add.has(catOf(c.id, t))));
    const bar = $(".catbar", app);
    bar.hidden = t === "model" || t === "fantasy" || cats.length < 2;
    const hidden = k => all.filter(c => catOf(c.id, t) === k && !list.includes(c)).length;
    bar.innerHTML = `<span>CARD TYPES</span>${cats.map(k => { const hd = active.has(k) ? hidden(k) : 0;
      return `<button type="button" class="cat ${active.has(k) ? "on" : ""}" data-cat="${k}" aria-pressed="${active.has(k)}" title="${active.has(k) ? (hd ? "Show all " + k.toLowerCase() : "Hide " + k.toLowerCase()) : "Show " + k.toLowerCase()}">${k}${hd ? ` <i>+${hd}</i>` : ""}</button>`; }).join("")}${F.add.size || F.del.size ? '<button type="button" class="cat reset">RECOMMENDED</button>' : ""}`;
    bar.querySelectorAll(".cat[data-cat]").forEach(b => b.onclick = () => {
      // off -> show all of that type; on with hidden cards -> show the rest; fully shown -> hide
      const k = b.dataset.cat;
      if (!active.has(k) || hidden(k)) { F.add.add(k); F.del.delete(k); } else { F.del.add(k); F.add.delete(k); }
      show(t);
    });
    const rs = bar.querySelector(".reset");
    if (rs) rs.onclick = () => { filt[t] = null; show(t); };
    if (t === "model" && g.model) box.insertAdjacentHTML("beforeend", `<p class="summary model-sum"><b>OUR NUMBER VS. THE MARKET</b>${esc(g.model.summary)}<span>A different lens on the data, not betting advice.</span></p>`);
    if (t === "fantasy") box.insertAdjacentHTML("beforeend", `<p class="summary model-sum"><b>FANTASY LENS</b>Who is scoring more or less than their usage predicts, PPR scoring. Expected points come from each player's targets, carries, depth and field position.<span>For fun, not betting advice.</span></p>`);
    if (!list.length) box.innerHTML = '<p class="empty">No cards cleared the sample-size bar for this matchup.</p>';
    list.forEach((c, i) => { const e = cardEl(c, g); e.style.animationDelay = `${i * 60}ms`; box.appendChild(e); });
  };
  topSel.onchange = () => { try { localStorage.setItem("topn", topSel.value); } catch (e) { /* storage blocked */ } show(cur); };
  app.querySelectorAll(".tabs button").forEach(b => b.onclick = () => {
    show(b.dataset.tab); history.replaceState(null, "", `#/${G.season}/${G.week}/${id}` + (b.dataset.tab !== "team" ? "?tab=" + b.dataset.tab : ""));
  });
  if (focus && ![...g.team_cards.slice(0, evenN(g.team_n ?? 99, g.team_cards.length)), ...g.player_cards.slice(0, evenN(g.player_n ?? 99, g.player_cards.length)),
    ...(g.fantasy_cards || [])].some(c => c.id === focus)) topSel.value = "10";
  const ftab = focus && [...g.player_cards].some(c => c.id === focus) ? "players" : focus && (g.fantasy_cards || []).some(c => c.id === focus) ? "fantasy" : tab;
  const okTab = t => t === "players" || (t === "model" && (g.model_cards || []).length) || (t === "fantasy" && (g.fantasy_cards || []).length);
  show(okTab(ftab) ? ftab : "team");
  if (focus) { const e = document.getElementById("card-" + focus.replace(/[^a-z0-9]/gi, "-")); if (e) e.scrollIntoView({ block: "center" }); }
}


/* ---------- season views: track record, league table, team pages ---------- */
const seasonCache = {};
function getSeason(file) {
  const p = `data/${S.idx.latest.season}/${file}.json`;
  if (!seasonCache[p]) seasonCache[p] = getJSON(p).catch(e => { delete seasonCache[p]; throw e; });
  return seasonCache[p];
}
// End-of-season outcomes: record on the left, split into playoffs vs. out, then how far a playoff run goes and
// which draft slot a miss lands in. Widths are probabilities from the 10,000 season simulations.
function outcomeFlow(c) {
  const o = c.o, m = T(c.team), svg = newSvg(620), x0 = 160, xm = 440, x1 = 680, top = 120, H0 = 380, GAP = 14;
  const OUT = "#8A6A4A";
  const rows = [
    ["champ", "Win Super Bowl", m.accent], ["r_sb", "Lose Super Bowl", m.accent], ["r_conf", "Out in conf. final", m.accent],
    ["r_div", "Out in divisional", m.accent], ["r_wc", "Out in wild card", m.accent],
    ["p11_18", "Pick 11\u201318", OUT], ["p4_10", "Pick 4\u201310", OUT], ["top3", "Top-3 pick", OUT]];
  const pct = v => v <= 0 ? "0%" : v < 0.01 ? "<1%" : Math.round(v * 100) + "%";
  const defs = $("defs", svg);
  [["po", m.accent], ["out", OUT]].forEach(([id, col]) => {
    const g = el("linearGradient", { id: `of-${id}-${c.team}`, x1: 0, x2: 1, y1: 0, y2: 0 }, defs);
    el("stop", { offset: "0%", "stop-color": col, "stop-opacity": 0.25 }, g);
    el("stop", { offset: "100%", "stop-color": col, "stop-opacity": 0.95 }, g);
  });
  // left stack: playoffs on top, then out
  let yl = top, yr = top - GAP * 0;
  const shown = rows.filter(([k]) => o[k] > 0);
  const nGaps = Math.max(0, shown.length - 1), Hr = H0 + nGaps * GAP;
  yr = top + (H0 - Hr) / 2;
  const labels = [];
  shown.forEach(([k, lab, col], i) => {
    const h = Math.max(1.5, o[k] * H0), po = k.startsWith("r_") || k === "champ";
    const fill = `url(#of-${po ? "po" : "out"}-${c.team})`;
    const a0 = yl, a1 = yl + h, b0 = yr, b1 = yr + h, mx = (xm + x1) / 2;
    el("path", { d: `M${x0},${a0} L${xm},${a0} C${mx},${a0} ${mx},${b0} ${x1},${b0} L${x1},${b1} C${mx},${b1} ${mx},${a1} ${xm},${a1} L${x0},${a1} Z`,
      fill, stroke: "none", opacity: o[k] < 0.01 ? 0.6 : 1 }, svg);
    el("rect", { x: x1, y: b0, width: 8, height: h, fill: col }, svg);
    labels.push({ y: (b0 + b1) / 2, v: pct(o[k]), lab, col, ny: b0 + h / 2 });
    yl = a1; yr = b1 + GAP;
  });
  // labels: keep 52 units apart, inside the chart
  const SP = 40;  // number and label on one line
  for (let i = 1; i < labels.length; i++) labels[i].y = Math.max(labels[i].y, labels[i - 1].y + SP);
  const over = labels.length ? labels[labels.length - 1].y - 580 : 0;
  if (over > 0) labels.forEach(L => { L.y -= over; });
  for (let i = labels.length - 2; i >= 0; i--) labels[i].y = Math.min(labels[i].y, labels[i + 1].y - SP);
  if (labels.length && labels[0].y < 40) { const d = 40 - labels[0].y; labels.forEach(L => { L.y += d; }); }
  labels.forEach(L => {
    if (Math.abs(L.y - L.ny) > 8) el("path", { d: `M${x1 + 10},${L.ny} L${x1 + 22},${L.y}`, stroke: "#55555B", "stroke-width": 1.5, fill: "none" }, svg);
    txt(svg, x1 + 28 + 78, L.y + 11, L.v, { "text-anchor": "end", "font-size": 32, "font-weight": 600, style: "font-family:var(--num)", fill: L.col === OUT ? "#C9A27E" : m.accent, ...HALO });
    txt(svg, x1 + 28 + 92, L.y + 9, L.lab, { "font-size": 23, "font-weight": 600, fill: "#C9C9C6", ...HALO });
  });
  // left bar, record, and the two big numbers
  el("rect", { x: x0 - 10, y: top, width: 10, height: H0, fill: "#F4F4F2" }, svg);
  txt(svg, x0 - 24, top + H0 / 2 - 14, "RECORD", { "text-anchor": "end", "font-size": 18, "font-weight": 800, fill: C.tick, "letter-spacing": 2 });
  txt(svg, x0 - 24, top + H0 / 2 + 24, c.record, { "text-anchor": "end", "font-size": 34, "font-weight": 600, style: "font-family:var(--num)", fill: "#F4F4F2" });
  const pPo = o.po, xb = (x0 + xm) / 2;
  txt(svg, xb, top - 62, "MAKE PLAYOFFS", { "text-anchor": "middle", "font-size": 20, "font-weight": 900, fill: m.accent, "letter-spacing": 2, ...HALO });
  txt(svg, xb, top - 14, pct(pPo), { "text-anchor": "middle", "font-size": 50, "font-weight": 600, style: "font-family:var(--num)", fill: m.accent, ...HALO });
  txt(svg, xb, top + H0 + 52, pct(1 - pPo), { "text-anchor": "middle", "font-size": 50, "font-weight": 600, style: "font-family:var(--num)", fill: "#C9A27E", ...HALO });
  txt(svg, xb, top + H0 + 84, "MISS PLAYOFFS", { "text-anchor": "middle", "font-size": 20, "font-weight": 900, fill: "#C9A27E", "letter-spacing": 2, ...HALO });
  return svg;
}
// A team logo that opens that team's page (matchup page: header, final score, keys).
const teamLogoLink = t => `<a class="tlogo" href="#/team/${t}" title="${esc(T(t).name)}: team page" aria-label="${esc(T(t).name)} team page">${logoHTML(t)}</a>`;
function chartBox(title, sub, svg, note) {
  const b = h("article", { class: "card wide" });
  b.innerHTML = `<h3 class="t1">${esc(title)}</h3><p class="sub">${esc(sub)}</p><div class="chart"></div>${note ? `<div class="foot" style="display:block"><small>${esc(note)}</small></div>` : ""}`;
  $(".chart", b).appendChild(svg);
  return b;
}
const pctS = v => (v === null || v === undefined) ? "–" : Math.round(v * 100) + "%";
const ord = n => n === null || n === undefined ? "–" : n + (["th", "st", "nd", "rd"][(n % 100 > 10 && n % 100 < 14) ? 0 : Math.min(n % 10, 4) % 4] || "th");
function statTile(label, m, k, note, e) {
  if (!m || !k) return `<div class="stat"><span>${esc(label)}</span><b>No graded games yet</b><small>${esc(note)}</small></div>`;
  const all = [["MODEL", m], ["MARKET", k]].concat(e ? [["ELO", e]] : []), best = Math.min(...all.map(x => x[1].brier));
  return `<div class="stat"><span>${esc(label)}</span>
    <div class="vs ${e ? "three" : ""}">${all.map(([lab, x]) => `<div><em>${lab}</em><b class="${x.brier === best ? "up" : ""}">${x.brier.toFixed(3)}</b><small>${Math.round(x.acc * 100)}% picks right</small></div>`).join("")}</div>
    <small>Brier score, lower is better · ${m.n} games · ${esc(note)}</small></div>`;
}
async function recordView() {
  showLoading("Loading track record");
  const r = await getSeason("record"), app = $("#app");
  app.innerHTML = `<div class="board-head"><h1>Model <span>track record</span></h1></div>
    <p class="board-note">Our win probabilities vs. the betting market, graded after every game. <a href="methods.html#record">How it is graded</a></p>
    <section class="stats">${statTile("Published picks, " + r.season, r.published.model, r.published.market, "the last version on this site before kickoff", r.published.elo)}
    ${r.backfill && r.backfill.model ? statTile(`Backfilled picks, weeks ${r.backfill.weeks[0]}-${r.backfill.weeks[r.backfill.weeks.length - 1]}`, r.backfill.model, r.backfill.market, "rebuilt after the fact with pre-week data only, closing line", r.backfill.elo) : ""}
    ${statTile("Season walk-forward, " + r.season, r.walk.model, r.walk.market, "every game, each week fit only on earlier games", r.walk.elo)}</section>
    <div class="cards rec-cards"></div>
    <section class="log"><h2>Picks on this site</h2>${(r.site || r.published).games.length ? `<div class="tbl-wrap"><table class="tbl"><thead><tr><th>WK</th><th>GAME</th><th>MODEL</th><th>MARKET</th><th>ELO</th><th>FINAL</th></tr></thead><tbody>
    ${(r.site || r.published).games.map(x => { const ph = x.p, pk = x.pm, mt = ph >= 0.5 ? x.home : x.away, kt = pk === null ? null : pk >= 0.5 ? x.home : x.away, win = x.y ? x.home : x.away;
      return `<tr><td>${x.week}</td><td><a href="#/${r.season}/${x.week}/${x.id}">${x.away} at ${x.home}</a>${x.backfill ? ' <small class="pj">BACKFILL</small>' : ""}</td>
      <td class="${mt === win ? "ok" : "no"}">${mt} ${pctS(Math.max(ph, 1 - ph))} ${mt === win ? "✓" : "✗"}</td>
      <td class="${kt === win ? "ok" : "no"}">${kt ? `${kt} ${pctS(Math.max(pk, 1 - pk))} ${kt === win ? "✓" : "✗"}` : "–"}</td>
      ${x.pe === null || x.pe === undefined ? "<td>\u2013</td>" : (() => { const et = x.pe >= 0.5 ? x.home : x.away; return `<td class="${et === win ? "ok" : "no"}">${et} ${pctS(Math.max(x.pe, 1 - x.pe))} ${et === win ? "✓" : "✗"}</td>`; })()}
      <td>${x.away} ${x.final[x.away]} · ${x.home} ${x.final[x.home]}</td></tr>`; }).join("")}</tbody></table></div>` : '<p class="empty">Picks are graded the week after they are published.</p>'}</section>`;
  const box = $(".rec-cards", app);
  if (r.walk.cum.length) box.appendChild(chartBox("Season to date: model vs. market", "Brier score of every game this season, walk-forward", cumline({ cum: r.walk.cum }),
    "Walk-forward: week N uses a model fit only on games before week N. Uses the starting QB who actually played. Market = closing line, vig removed."));
  const sc = (r.site || r.published).cum;
  if (sc.length > 1) box.appendChild(chartBox("Picks on this site: model vs. market", "Brier score to date, backfilled and published picks together", cumline({ cum: sc }),
    "Backfilled weeks use the closing line; published weeks use the line at our last pre-kickoff build."));
  if (r.calib.length) box.appendChild(chartBox("Calibration and past seasons", "When the model says 70%, does the team win about 70% of the time?", calib({ pts: r.calib, seasons: r.backtest }),
    "Walk-forward backtest: each season predicted by a model fit only on earlier seasons."));
}
function rankCell(r) {
  if (r === null || r === undefined) return "<td>–</td>";
  const a = Math.pow((33 - r) / 32, 2) * 0.55;
  return `<td class="rk" style="background:rgba(251,79,20,${a.toFixed(2)})">${r}</td>`;
}
async function bracketView() {
  showLoading("Loading bracket");
  const B = await getSeason("bracket"), app = $("#app");
  const L = await getSeason("league").catch(() => null);
  const sl = (gm, t) => gm.seeds && gm.seeds[t] ? `<i>${gm.seeds[t]}</i>` : "<i></i>";
  const pr = (gm, t) => gm.final ? `<em>${gm.final[t]}</em>` : gm.p_home === null || gm.p_home === undefined ? "<em>\u2013</em>" : `<em>${Math.round((t === gm.home ? gm.p_home : 1 - gm.p_home) * 100)}%</em>`;
  const box = gm => `<a class="bg ${gm.actual ? "real" : ""}" href="#/${B.season}/PO/${gm.id}">${[gm.away, gm.home].map(t => `<span class="${gm.winner === t ? "w" : "l"}">${sl(gm, t)}${logoHTML(t)}<b><span class="nk">${esc(T(t).nick)}</span><span class="ab">${t}</span></b>${pr(gm, t)}</span>`).join("")}</a>`;
  const col = (code, conf) => { const r = B.rounds.find(x => x.code === code); return r ? r.games.filter(gm => gm.conf === conf).map(box).join("") : ""; };
  const bye = c => { const s1 = (B.seeds[c] || [])[0]; return s1 ? `<div class="bye"><span><i>1</i>${logoHTML(s1.team)}<b><span class="nk">${esc(T(s1.team).nick)}</span><span class="ab">${s1.team}</span></b><em>BYE</em></span></div>` : ""; };
  const rcol = (code, c, label, side) => `<div class="bcol ${side} r-${code}"><h3><b>${c}</b> ${label}</h3><div class="bgames">${code === "WC" ? bye(c) : ""}${col(code, c)}</div></div>`;
  const sb = B.rounds.find(x => x.code === "SB");
  const confs = ["AFC", "NFC"].filter(c => B.seeds[c]);
  const cols = [];
  if (confs[0]) cols.push(rcol("WC", confs[0], "WILD CARD", "L"), rcol("DIV", confs[0], "DIVISIONAL", "L"), rcol("CON", confs[0], "CONFERENCE", "L"));
  cols.push(`<div class="bcol sb"><h3><b>SUPER BOWL</b></h3><div class="bgames">${sb ? sb.games.map(box).join("") : '<p class="empty">Not set yet</p>'}
    ${B.champion ? `<p class="champ">${logoHTML(B.champion)}<b>${esc(T(B.champion).nick)}</b><small>${B.status === "final" ? "CHAMPION" : "MODEL FAVORITE"}</small></p>` : ""}</div></div>`);
  if (confs[1]) cols.push(rcol("CON", confs[1], "CONFERENCE", "R"), rcol("DIV", confs[1], "DIVISIONAL", "R"), rcol("WC", confs[1], "WILD CARD", "R"));
  // Compact bracket for tablets and phones: each conference as rows of rounds, then the Super Bowl.
  const crow = (code, c, label) => { const g = (code === "WC" ? bye(c) : "") + col(code, c); return g ? `<div class="bkr"><h4>${label}</h4><div class="bkg r-${code}">${g}</div></div>` : ""; };
  const compact = `<div class="bk-compact">${confs.map(c => `<section class="bkc"><h3><b>${c}</b></h3>${crow("WC", c, "WILD CARD")}${crow("DIV", c, "DIVISIONAL")}${crow("CON", c, "CONFERENCE")}</section>`).join("")}
    <section class="bkc sb"><h3><b>SUPER BOWL</b></h3><div class="bkg r-SB">${sb ? sb.games.map(box).join("") : '<p class="empty">Not set yet</p>'}${B.champion ? `<p class="champ">${logoHTML(B.champion)}<b>${esc(T(B.champion).nick)}</b><small>${B.status === "final" ? "CHAMPION" : "MODEL FAVORITE"}</small></p>` : ""}</div></section></div>`;
  app.innerHTML = `<div class="board-head"><h1>Playoff <span>${B.status === "final" ? "bracket" : "picture"}</span></h1></div>
    <p class="board-note">${B.status === "final" ? "Regular season is over. Real matchups and results are shown; rounds not yet set are filled with the model favorite." : (B.seed_basis === "projected" ? `Seeds from projected final records (10,000 simulations of the rest of the season, data through week ${B.through_week}); every round is filled by the model favorite.` : `If the season ended today: seeds from current standings (through week ${B.through_week}), every later round filled by the model favorite. Tiebreakers are approximate.`)} Click any matchup for its full cards. Model odds are luck-adjusted: ratings are corrected for the injuries each team played through${B.luck && B.luck.turnover_adjusted ? " and fumble-recovery luck is removed" : ""}, and every team is projected at full health. <a href="methods.html#luck">How it works</a></p>
    <div class="bracket">${cols.join("")}</div>${compact}
    <section class="log"><h2>Seeds</h2><div class="seed-grid">${["AFC", "NFC"].filter(c => B.seeds[c]).map(c => `<div class="tbl-wrap"><table class="tbl seeds">
      <thead><tr><th>${c}</th><th>TEAM</th><th>W-L</th><th title="Pythagorean expected record from points scored and allowed">EXP W-L</th><th title="Average final record in 10,000 season simulations">PROJ</th></tr></thead><tbody>
      ${B.seeds[c].map(sd => { const x = (L && L.teams[sd.team]) || {}, g = (x.w ?? 0) + (x.l ?? 0) + (x.t ?? 0);
        return `<tr><td>${sd.seed}</td><td class="tm"><a href="#/team/${sd.team}">${logoHTML(sd.team)}<b>${esc(T(sd.team).nick)}</b></a></td>
        <td>${sd.w}-${sd.l}${sd.t ? "-" + sd.t : ""}</td>
        <td>${x.xw === null || x.xw === undefined ? "\u2013" : `${Math.round(x.xw)}-${g - Math.round(x.xw)}`}</td>
        <td>${x.proj ? `${Math.round(x.proj[0])}-${Math.round(x.proj[0] + x.proj[1]) - Math.round(x.proj[0])}` : "\u2013"}</td></tr>`; }).join("")}
      </tbody></table></div>`).join("")}</div>
    <p class="board-note">EXP W-L = record the points scored and allowed would predict (Pythagorean, exponent 2.37). PROJ = average final record in 10,000 simulations of the rest of the season.</p></section>`;
}
async function teamsView(sortKey) {
  showLoading("Loading teams");
  const L = await getSeason("league"), app = $("#app");
  const rows = Object.entries(L.teams).map(([t, x]) => ({ t, x }));
  const u = (x, id, side) => x.units[id] ? x.units[id][side].r : null;
  const cols = [["net", "NET", r => r.x.net.r], ["rec", "W-L", r => -(r.x.w + 0.5 * r.x.t) / Math.max(1, r.x.w + r.x.l + r.x.t)], ["pd", "PD", r => -r.x.pd], ["proj", "PROJ", r => -((r.x.proj || [0])[0])], ["luck", "LUCK", r => -(r.x.luck ?? -99)],
    ["chg", "TREND", r => -(r.x.net.chg ?? -99)], ["po", "PASS O", r => u(r.x, "pass_epa", "off")], ["ro", "RUSH O", r => u(r.x, "rush_epa", "off")],
    ["pdf", "PASS D", r => u(r.x, "pass_epa", "def")], ["rd", "RUSH D", r => u(r.x, "rush_epa", "def")], ["pl", "PLAYOFFS", r => -(r.x.p_playoffs ?? -1)]];
  const key = cols.find(c => c[0] === sortKey) ? sortKey : "net", f = cols.find(c => c[0] === key)[2];
  rows.sort((a, b) => (f(a) ?? 99) - (f(b) ?? 99));
  app.innerHTML = `<div class="board-head"><h1>League <span>table</span></h1></div>
    <p class="board-note">Opponent-adjusted ranks through week ${L.week - 1}. NET = offense minus defense EPA per play. TREND = change in NET rank over the last ${L.trend_weeks} weeks. PROJ = average final record in 10,000 season simulations. LUCK = wins minus Pythagorean expected wins from points scored and allowed (positive = winning more than the scoring says). Click a column to sort. <a href="methods.html#teams">How it works</a></p>
    <div class="tbl-wrap"><table class="tbl league"><thead><tr><th>TEAM</th>${cols.map(c => `<th><a href="#/teams?sort=${c[0]}" class="${c[0] === key ? "on" : ""}">${c[1]}</a></th>`).join("")}</tr></thead><tbody>
    ${rows.map(({ t, x }) => `<tr><td class="tm"><a href="#/team/${t}">${logoHTML(t)}<b>${esc(T(t).nick)}</b></a></td>${rankCell(x.net.r)}
      <td>${x.w}-${x.l}${x.t ? "-" + x.t : ""}</td><td>${x.pd > 0 ? "+" : ""}${x.pd}</td>
      <td>${x.proj ? `${Math.round(x.proj[0])}-${Math.round(x.proj[0] + x.proj[1]) - Math.round(x.proj[0])}` : "\u2013"}</td>
      <td class="chg ${x.luck >= 1 ? "up" : x.luck <= -1 ? "dn" : ""}">${x.luck === null || x.luck === undefined ? "\u2013" : (x.luck > 0 ? "+" : "") + x.luck.toFixed(1)}</td>
      <td class="chg ${x.net.chg > 0 ? "up" : x.net.chg < 0 ? "dn" : ""}">${x.net.chg === null ? "–" : x.net.chg > 0 ? "▲" + x.net.chg : x.net.chg < 0 ? "▼" + -x.net.chg : "="}</td>
      ${rankCell(u(x, "pass_epa", "off"))}${rankCell(u(x, "rush_epa", "off"))}${rankCell(u(x, "pass_epa", "def"))}${rankCell(u(x, "rush_epa", "def"))}
      <td>${pctS(x.p_playoffs)}</td></tr>`).join("")}</tbody></table></div>`;
}
async function teamView(t) {
  showLoading("Loading team");
  const L = await getSeason("league"), x = L.teams[t], app = $("#app"), m = T(t);
  if (!x) { app.innerHTML = '<p class="empty">No data for that team.</p>'; return; }
  const next = x.games.find(gm => !gm.final && gm.week === S.idx.latest.week);
  const wkPath = gm => `#/${L.season}/${gm.week}/${gm.id}`;
  app.innerHTML = `<section class="team-hero" style="--acc:${m.accent}">${logoHTML(t)}<div><h1>${esc(m.name)}</h1>
      <p>${x.w}-${x.l}${x.t ? "-" + x.t : ""} · PD ${x.pd > 0 ? "+" : ""}${x.pd} · ${ord(x.net.r)} in NET${x.net.chg ? ` (${x.net.chg > 0 ? "▲" : "▼"}${Math.abs(x.net.chg)})` : ""} · playoff odds ${pctS(x.p_playoffs)}${x.proj ? ` · projected ${x.proj[0].toFixed(1)}-${x.proj[1].toFixed(1)}` : ""}${x.luck !== null && x.luck !== undefined ? ` · luck ${x.luck > 0 ? "+" : ""}${x.luck.toFixed(1)} wins` : ""}${x.qb ? ` · QB ${esc(x.qb)}` : ""}</p></div>
      ${next ? `<a class="follow-btn" href="#/${L.season}/${next.week}/${next.id}">WEEK ${next.week}: ${next.home ? "VS" : "AT"} ${next.opp} &rarr;</a>` : ""}</section>
    <section class="profile"><h2>Unit profile <small>rank of 32, opponent-adjusted where noted</small></h2><div class="units-grid">
    ${Object.values(x.units).map(un => ["off", "def"].map(sd => { const r = un[sd].r; return `<div class="unit"><span>${esc((sd === "off" ? un.unit_off : un.unit_def).toUpperCase())}</span>
      <div class="ubar"><i style="width:${r ? (33 - r) / 32 * 100 : 0}%;background:${m.accent}"></i></div><b>${ord(r)}</b><small>${fmt(un[sd].v, un.fmt)} ${esc(un.label)}${sd === "def" ? " allowed" : ""}</small></div>`; }).join("")).join("")}
    </div></section><div class="cards team-cards"></div>
    <section class="log"><h2>Season</h2><div class="tbl-wrap"><table class="tbl"><thead><tr><th>WK</th><th>OPPONENT</th><th>MODEL</th><th>RESULT</th></tr></thead><tbody>
    ${x.games.map(gm => { const f = gm.final, my = f ? f[t] : null, op = f ? f[gm.opp] : null, res = f ? (my > op ? "W" : my < op ? "L" : "T") : "";
      return `<tr><td>${gm.week}</td><td class="tm"><a href="#/${L.season}/${gm.week}/${gm.id}">${gm.home ? "vs" : "at"} ${logoHTML(gm.opp)}<b>${esc(T(gm.opp).nick)}</b></a></td>
      <td>${gm.p === null ? "–" : pctS(gm.p)}${gm.proj ? ' <small class="pj">PROJ</small>' : ""}</td><td class="${res === "W" ? "ok" : res === "L" ? "no" : ""}">${f ? `${res} ${my}-${op}` : esc(gm.kickoff || "")}</td></tr>`; }).join("")}
    </tbody></table></div><p class="board-note">Only weeks with a report on this site are listed. PROJ = projected matchup, model only.</p></section>`;
  if (x.outcomes) {
    const oc = x.outcomes, seedTxt = `Bye ${pctS(oc.bye)} · division title without a bye ${pctS(oc.div)} · wild card ${pctS(oc.wc)}`;
    const reach = `Reach the divisional round ${pctS(oc.r_div + oc.r_conf + oc.r_sb + oc.champ)} · conference final ${pctS(oc.r_conf + oc.r_sb + oc.champ)} · Super Bowl ${pctS(oc.r_sb + oc.champ)}`;
    $(".team-cards", app).appendChild(chartBox("End-of-season outcomes", `${m.nick}: where the season ends across 10,000 simulations of the remaining games (each season counts once, in the round it ends). ${seedTxt}. ${reach}.`,
      outcomeFlow({ team: t, o: oc, record: `${x.w}-${x.l}${x.t ? "-" + x.t : ""}` }),
      "Playoff games use the same ratings as the season simulations; higher seed at home, Super Bowl neutral. Draft slots: non-playoff teams pick 1-18 by fewest wins (tiebreaks approximate)."));
  }
  $(".team-cards", app).appendChild(chartBox(`${m.nick} by week`, "Offense EPA per play vs. EPA per play allowed", tline({ team: t, trend: x.trend }), "Raw game values, so opponent strength is not removed here."));
}

/* ---------- routing ---------- */
async function loadWeek(season, week) {
  if (S.week && S.week.season === season && S.week.week === week) return;
  S.games = await getJSON(`data/${season}/wk${String(week).padStart(2, "0")}/games.json`);
  S.week = { season, week };

  const gs = $("#game-select");
  gs.innerHTML = `<option value="">All games (board)</option>` + S.games.games.map(g =>
    `<option value="${g.id}">${g.away} at ${g.home} · ${esc(g.kickoff.split(" · ")[0])}${g.primetime ? " · PRIME" : ""}</option>`).join("");
  const b = $("#banner");
  b.hidden = !S.games.synthetic; b.textContent = "SYNTHETIC TEST DATA · NOT REAL NFL STATS";
  $("#built").textContent = `Built ${S.games.built} · ${S.games.span}`;
  getJSON("data/health.json").then(hl => {
    const el2 = $("#health"), n = hl.warnings.length + hl.errors.length;
    el2.className = "health " + hl.status;
    el2.textContent = hl.status === "ok" ? "Data checks OK" : `${n} data check${n > 1 ? "s" : ""} flagged`;
    el2.title = [...hl.errors, ...hl.warnings].join("\n") || `Checked ${hl.checked}`;
  }).catch(() => {});
}
function track() {
  try { window.goatcounter?.count?.({ path: location.pathname + location.hash.replace(/\?.*$/, ""), title: document.title }); } catch (e) { /* analytics optional */ }
}
async function route() {
  const [path, q] = location.hash.replace(/^#\/?/, "").split("?");
  const params = new URLSearchParams(q || location.search);
  const parts = path.split("/").filter(Boolean);
  S.pair = null;
  const latest = S.idx.latest;
  if (["record", "teams", "team", "bracket"].includes(parts[0])) {
    try { await loadWeek(latest.season, latest.week); $("#week-select").value = `${latest.season}/${latest.week}`; } catch (e) { /* footer only */ }
    $("#game-select").value = ""; window.scrollTo(0, 0);
    document.querySelectorAll(".navlink").forEach(a => a.classList.toggle("on", a.dataset.nav === (parts[0] === "team" ? "teams" : parts[0])));
    try {
      if (parts[0] === "record") await recordView(); else if (parts[0] === "bracket") await bracketView(); else if (parts[0] === "teams") await teamsView(params.get("sort")); else await teamView((parts[1] || "").toUpperCase());
    } catch (e) { console.error(e); $("#app").innerHTML = '<p class="empty">Not built yet. It appears after the next weekly run.</p>'; }
    track(); return;
  }
  document.querySelectorAll(".navlink").forEach(a => a.classList.toggle("on", a.dataset.nav === "home"));
  const season = +(parts[0] || latest.season), week = parts[1] ? (isNaN(+parts[1]) ? parts[1] : +parts[1]) : latest.week, id = parts[2] || "";
  if (!S.week || S.week.season !== season || S.week.week !== week) showLoading("Loading week " + week);
  try { await loadWeek(season, week); } catch (e) { $("#app").innerHTML = '<p class="empty">That week has no report yet.</p>'; return; }
  $("#week-select").value = `${season}/${week}`;
  $("#game-select").value = id;
  window.scrollTo(0, 0);
  if (id) await matchup(id, params.get("tab"), params.get("card")); else board();
  track();
}
function setupFollow() {
  const dlg = $("#follow"), sel = $("#follow-team"), base = S.idx.site_url || location.href.split("#")[0];
  const teams = Object.values(S.teams).sort((a, b) => a.name.localeCompare(b.name));
  sel.innerHTML = `<option value="ALL">All games (weekly digest)</option>` + teams.map(t => `<option value="${t.abbr}">${esc(t.name)}</option>`).join("");
  const sync = () => {
    $("#feed-url").value = `${base}feeds/${sel.value === "ALL" ? "all" : sel.value}.xml`;
    if ($("#email-tag")) $("#email-tag").value = sel.value;
    try { localStorage.setItem("follow", sel.value); } catch (e) { /* storage blocked */ }
  };
  try { const v = localStorage.getItem("follow"); if (v) sel.value = v; } catch (e) { /* storage blocked */ }
  if (S.idx.buttondown) {
    $("#email-box").hidden = false;
    if (!S.idx.email_per_team) { $("#email-tag").remove(); $("#email-box p").textContent = "One email a week with every matchup preview. Unsubscribe in any email. For one team, use its RSS feed above."; }
    $("#email-form").action = `https://buttondown.com/api/emails/embed-subscribe/${encodeURIComponent(S.idx.buttondown)}`;
  }
  sel.onchange = sync; sync();
  $("#feed-copy").onclick = e => { navigator.clipboard?.writeText($("#feed-url").value); e.target.textContent = "COPIED"; setTimeout(() => (e.target.textContent = "COPY"), 1200); };
  $("#follow-btn").onclick = () => dlg.showModal();
}
async function init() {
  S.idx = await getJSON("data/index.json");
  S.teams = await getJSON("data/teams.json");
  S.handle = S.idx.handle || "";
  const ws = $("#week-select");
  const wsort = w => (w.projected || w.week === "PO") ? 1000 - (w.week === "PO" ? 99 : w.week) : -w.week;
  ws.innerHTML = [...S.idx.weeks].filter(w => w.season === S.idx.latest.season || !w.projected).sort((a, b) => (b.season - a.season) || (wsort(a) - wsort(b)))
    .map(w => `<option value="${w.season}/${w.week}">${wkLabel(w)}, ${w.season}${w.synthetic ? " (test)" : ""}</option>`).join("");
  ws.onchange = () => { location.hash = `#/${ws.value}`; };
  $("#game-select").onchange = e => { const [s, w] = ws.value.split("/"); location.hash = `#/${s}/${w}${e.target.value ? "/" + e.target.value : ""}`; };
  setupFollow();
  if (S.idx.goatcounter) {
    const gc = document.createElement("script");
    gc.async = true; gc.src = "https://gc.zgo.at/count.js";
    gc.dataset.goatcounter = `https://${S.idx.goatcounter}.goatcounter.com/count`;
    gc.dataset.goatcounterSettings = JSON.stringify({ no_onload: true });
    gc.onload = track; document.head.appendChild(gc);
  }
  window.addEventListener("hashchange", route);
  route();
}
init().catch(e => { console.error(e); $("#app").innerHTML = '<p class="empty">No reports built yet. Run the weekly workflow.</p>'; });
