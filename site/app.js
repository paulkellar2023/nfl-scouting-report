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
function sgn(v, d) { return (v > 0 ? "+" : v < 0 ? MINUS : "") + Math.abs(v).toFixed(d); }
function fmt(v, k) {
  if (v === null || v === undefined || isNaN(v)) return "";
  switch (k) {
    case "epa": return Math.abs(v) < 0.005 ? "0" : sgn(v, 2);
    case "pct": return Math.round(v * 100) + "%";
    case "pct1": return (v * 100).toFixed(1) + "%";
    case "pct_pm": return sgn(v * 100, 1) + "%";
    case "yds": return sgn(v, 1);
    case "num1": return v.toFixed(1);
    default: return v.toFixed(2);
  }
}
function tickFmt(v, k, step) {
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
const T = t => S.teams[t] || { accent: "#BBBBBB", color: "#444", label: t, nick: t, abbr: t };
async function getJSON(p) { const r = await fetch(p, { cache: "no-cache" }); if (!r.ok) throw new Error(p); return r.json(); }
function preload(urls) {
  return Promise.all([...new Set(urls.filter(Boolean))].filter(u => !(u in S.ok)).map(u => new Promise(res => {
    const i = new Image(); const done = ok => { S.ok[u] = ok; res(); };
    i.onload = () => done(true); i.onerror = () => done(false); setTimeout(() => done(false), 4000); i.src = u;
  })));
}
function logoSrc(m) { return S.ok[m.logo] ? m.logo : S.ok[m.logo_url] ? m.logo_url : null; }
function logoHTML(t, cls = "") {
  const m = T(t), src = logoSrc(m);
  return src ? `<img class="${cls}" src="${src}" alt="${esc(m.name || t)} logo">`
    : `<span class="fb ${cls}" style="background:${m.color}" role="img" aria-label="${esc(m.name || t)}">${t}</span>`;
}

/* ---------- svg primitives ---------- */
function logo(g, team, cx, cy, size, { hl = false, dim = false } = {}) {
  const m = T(team), grp = el("g", {}, g);
  if (hl) el("circle", { cx, cy, r: size / 2 + 5, fill: "#F4F4F2", stroke: m.accent, "stroke-width": 4 }, grp);
  const s = hl ? size * 0.74 : size;
  const src = logoSrc(m);
  if (src) el("image", { href: src, x: cx - s / 2, y: cy - s / 2, width: s, height: s, preserveAspectRatio: "xMidYMid meet" }, grp);
  else {
    el("circle", { cx, cy, r: s / 2.2, fill: m.color || "#555", stroke: hl ? "none" : "#0B0B0C", "stroke-width": 2 }, grp);
    txt(grp, cx, cy + s * 0.11, team, { "text-anchor": "middle", "font-size": s * 0.3, "font-weight": 900, fill: "#fff" });
  }
  if (dim) grp.setAttribute("opacity", 0.42);
  return grp;
}
function face(svg, g, p, cx, cy, r) {
  const m = T(p.team), id = "c" + (++clipN);
  const cp = el("clipPath", { id }, svg.querySelector("defs"));
  el("circle", { cx, cy, r }, cp);
  el("circle", { cx, cy, r: r + 4, fill: "#26262B", stroke: m.accent, "stroke-width": 4 }, g);
  if (p.img && S.ok[p.img]) el("image", { href: p.img, x: cx - r, y: cy - r, width: 2 * r, height: 2 * r, "clip-path": `url(#${id})`, preserveAspectRatio: "xMidYMid slice" }, g);
  else {
    const ini = (p.name || "?").split(" ").map(s => s[0]).slice(0, 2).join("");
    el("circle", { cx, cy, r, fill: m.color || "#444" }, g);
    txt(g, cx, cy + r * 0.32, ini, { "text-anchor": "middle", "font-size": r * 0.85, "font-weight": 900, fill: "#fff" });
  }
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
function bars(c) {
  const svg = newSvg(), box = { l: 110, r: W - 20, t: 30, b: H - 40 };
  const vals = c.pts.map(p => p.v), lo = Math.min(0, ...vals), hi = Math.max(0, ...vals);
  const [y0, y1] = extent([lo, hi], 0.14), Y = lin(y0, y1, box.b, box.t), yt = nice(y0, y1, 5);
  for (const v of yt.ticks) {
    el("line", { x1: box.l, x2: box.r, y1: Y(v), y2: Y(v), stroke: C.grid, "stroke-width": 1.2 }, svg);
    txt(svg, box.l - 14, Y(v) + 8, tickFmt(v, c.fmt, yt.step), { "text-anchor": "end", "font-size": 24, "font-weight": 300, fill: C.tick });
  }
  const n = c.pts.length, bw = (box.r - box.l) / n, hl = new Set(c.hl);
  c.pts.forEach((p, i) => {
    const x = box.l + i * bw, yv = Y(p.v), y0p = Y(0), on = hl.has(p.team), m = T(p.team);
    el("rect", { x: x + bw * 0.14, y: Math.min(yv, y0p), width: bw * 0.72, height: Math.max(1, Math.abs(yv - y0p)), fill: on ? m.accent : C.bar }, svg);
    const ly = p.v >= 0 ? yv - 18 : yv + 18;
    logo(svg, p.team, x + bw / 2, ly, on ? 34 : 24, {});
    if (on) txt(svg, x + bw / 2 + (i > n * 0.7 ? -26 : 26), p.v >= 0 ? yv - 50 : yv + 64, fmt(p.v, c.fmt),
      { "text-anchor": i > n * 0.7 ? "end" : "start", "font-size": 46, style: "font-family:var(--num)", "font-weight": 600, fill: m.accent });
  });
  el("line", { x1: box.l, x2: box.r, y1: Y(0), y2: Y(0), stroke: "#55555B", "stroke-width": 2 }, svg);
  if (c.med !== null) {
    dashed(svg, box.l, Y(c.med), box.r, Y(c.med));
    txt(svg, box.r, Y(c.med) - 12, "League median " + fmt(c.med, c.fmt), { "text-anchor": "end", "font-size": 22, "font-weight": 300, fill: "#BDBDBD" });
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
  const svg = newSvg(380), l = 150, r = W - 30, A = T(c.away), Hm = T(c.home);
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
  dashed(svg, lin(0, 1, l, r)(0.5), 96, lin(0, 1, l, r)(0.5), 360);
  return svg;
}
function waterfall(c) {
  const rows = [...c.items, { label: "PROJECTED MARGIN", pts: c.total, total: true }];
  const h = 90 + rows.length * 66, svg = newSvg(h), l = 300, r = W - 90;
  let run = 0; const spans = rows.map(it => { if (it.total) return [0, it.pts]; const s0 = run; run += it.pts; return [s0, run]; });
  const ext = Math.max(2, ...spans.flat().map(Math.abs)) * 1.15, X = lin(-ext, ext, l, r);
  el("line", { x1: X(0), x2: X(0), y1: 40, y2: h - 20, stroke: "#55555B", "stroke-width": 2 }, svg);
  txt(svg, l, 30, "← " + T(c.away).nick.toUpperCase(), { "font-size": 18, "font-weight": 900, fill: T(c.away).accent, "letter-spacing": ".08em" });
  txt(svg, r, 30, T(c.home).nick.toUpperCase() + " →", { "text-anchor": "end", "font-size": 18, "font-weight": 900, fill: T(c.home).accent, "letter-spacing": ".08em" });
  rows.forEach((it, i) => {
    const y = 60 + i * 66, [a, b] = spans[i], col = (it.total ? it.pts : it.pts) >= 0 ? T(c.home).accent : T(c.away).accent;
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
    el("line", { x1: X(c.market), x2: X(c.market), y1: Y(0), y2: Y(0.86), stroke: "#F2B33D", "stroke-width": 3, "stroke-dasharray": "8 6" }, svg);
    txt(svg, X(c.market), Y(0.86) - 12, "MARKET", { "text-anchor": "middle", "font-size": 18, "font-weight": 900, fill: "#F2B33D" });
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
  for (const p of c.pts) el("circle", { cx: X(p.pred), cy: Y(p.obs), r: 7 + 14 * Math.sqrt(p.n / mx), fill: "#F2B33D", opacity: 0.85 }, svg);
  txt(svg, (box.l + box.r) / 2, box.b + 72, "MODEL WIN PROBABILITY", { "text-anchor": "middle", "font-size": 20, "font-weight": 900, fill: C.title });
  const g = el("g", { transform: `translate(40,${(box.t + box.b) / 2}) rotate(-90)` }, svg);
  txt(g, 0, 0, "ACTUAL WIN RATE", { "text-anchor": "middle", "font-size": 20, "font-weight": 900, fill: C.title });
  const sx = 640, sr = W - 30, bs = c.seasons, all = bs.flatMap(s => [s.model_brier, s.mkt_brier]);
  const lo = Math.min(...all) - 0.005, hi = Math.max(...all) + 0.005, BX = lin(lo, hi, sx + 70, sr), rh = Math.min(48, 420 / Math.max(1, bs.length));
  txt(svg, sx, 20, "BRIER BY SEASON", { "font-size": 18, "font-weight": 900, fill: C.title, "letter-spacing": ".06em" });
  el("circle", { cx: sx + 8, cy: 46, r: 7, fill: "#F2B33D" }, svg); txt(svg, sx + 22, 52, "Model", { "font-size": 17, fill: C.sub });
  el("circle", { cx: sx + 100, cy: 46, r: 7, fill: "none", stroke: "#F4F4F2", "stroke-width": 2.5 }, svg); txt(svg, sx + 114, 52, "Market", { "font-size": 17, fill: C.sub });
  bs.forEach((s, i) => {
    const y = 90 + i * rh;
    txt(svg, sx, y + 6, String(s.season), { "font-size": 18, "font-weight": 800, fill: C.tick });
    el("line", { x1: BX(s.model_brier), x2: BX(s.mkt_brier), y1: y, y2: y, stroke: "#4A4A50", "stroke-width": 3 }, svg);
    el("circle", { cx: BX(s.mkt_brier), cy: y, r: 7, fill: "#0B0B0C", stroke: "#F4F4F2", "stroke-width": 2.5 }, svg);
    el("circle", { cx: BX(s.model_brier), cy: y, r: 7, fill: "#F2B33D" }, svg);
  });
  txt(svg, (sx + 70 + sr) / 2, 90 + bs.length * rh + 24, "← BETTER (LOWER)", { "text-anchor": "middle", "font-size": 15, "font-weight": 800, fill: "#6E6E75", "letter-spacing": ".08em" });
  return svg;
}
const CHARTS = { scatter, pscatter, duel, bars, gaps, splits, trend, pstrip, probbars, waterfall, dist, injuries, units, calib };


/* ---------- card ---------- */
function cardEl(c, g) {
  const m = T(c.owner), card = h("article", { class: "card", style: `--acc:${m.accent}` });
  card.innerHTML = `<div class="top"><div class="kicker">${esc(g.kicker)}</div>
    <div class="logos">${logoHTML(g.away)}${logoHTML(g.home)}
      <button type="button" class="info" aria-label="Source and notes" data-tip="SOURCE: ${esc(c.source)} · ${esc(c.note)}">i</button></div></div>
    <h3 class="t1">${esc(c.t1)}</h3><h3 class="t2">${esc(c.t2)}</h3>
    <p class="sub">${esc(c.sub)}</p>
    <div class="chart"></div>
    <div class="foot"><small><b>SOURCE: ${esc(c.source)}</b> &middot; ${esc(c.note)}</small>${S.handle ? `<strong>${esc(S.handle)}</strong>` : ""}</div>
    <div class="card-actions"><button type="button" data-act="png">PNG</button><button type="button" data-act="link">LINK</button></div>`;
  const f = CHARTS[c.chart.type];
  if (f) $(".chart", card).appendChild(f(c.chart));
  card.querySelector('[data-act="png"]').onclick = () => exportPng(card, c);
  card.querySelector('[data-act="link"]').onclick = e => {
    navigator.clipboard?.writeText(location.href.split("?")[0] + "?card=" + encodeURIComponent(c.id));
    e.target.textContent = "COPIED"; setTimeout(() => (e.target.textContent = "LINK"), 1200);
  };
  card.id = "card-" + c.id.replace(/[^a-z0-9]/gi, "-");
  return card;
}
let h2i = null;
async function exportPng(card, c) {
  const btn = card.querySelector('[data-act="png"]'); btn.textContent = "…";
  try {
    if (!h2i) {
      await new Promise((res, rej) => { const s = document.createElement("script");
        s.src = "https://cdn.jsdelivr.net/npm/html-to-image@1.11.11/dist/html-to-image.js"; s.onload = res; s.onerror = rej; document.head.appendChild(s); });
      h2i = window.htmlToImage;
    }
    const stage = h("div", { class: "export-stage" }), clone = card.cloneNode(true);
    clone.querySelector(".card-actions").remove(); clone.querySelector(".info")?.remove(); clone.classList.add("exporting"); clone.style.animation = "none"; clone.style.borderRadius = "0"; clone.style.border = "0";
    stage.appendChild(clone); document.body.appendChild(stage);
    const url = await h2i.toPng(clone, { pixelRatio: 2, backgroundColor: "#0B0B0C", width: 1080 });
    stage.remove();
    const a = document.createElement("a"); a.href = url; a.download = (c.id.replace(/[^a-z0-9]/gi, "_") || "card") + ".png"; a.click();
  } catch (e) { console.error(e); alert("PNG export failed. Try again after the page finishes loading."); }
  btn.textContent = "PNG";
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
function board() {
  const app = $("#app"), G = S.games;
  const maxLev = Math.max(0.01, ...G.games.map(g => g.leverage));
  app.innerHTML = `<div class="board-head"><h1>Week ${G.week} <span>matchups</span></h1>
    <p>Ordered by playoff leverage. Edges: offense vs. opposing defense, z-units.</p></div><div class="grid"></div>`;
  const grid = $(".grid", app);
  G.games.forEach((g, i) => {
    const a = T(g.away), hm = T(g.home), tile = h("a", { class: "tile", href: `#/${G.season}/${G.week}/${g.id}`,
      style: `--a:${a.accent};--h:${hm.accent};--acc:${T(g.tease_owner || g.home).accent};animation-delay:${i * 30}ms` });
    const imp = g.line && g.line.implied ? `${g.away} ${g.line.implied[g.away]} · ${g.home} ${g.line.implied[g.home]}` : "";
    tile.innerHTML = `<div class="tile-meta"><span>${esc(g.kickoff)}</span>${g.primetime ? '<span class="chip prime">PRIMETIME</span>' : ""}</div>
      <div class="teams"><div class="team">${logoHTML(g.away)}<div><b>${esc(a.nick)}</b><small>${g.away}</small></div></div>
      <span class="at">at</span><div class="team home">${logoHTML(g.home)}<div><b>${esc(hm.nick)}</b><small>${g.home}</small></div></div></div>
      <div class="line">${g.line ? esc(g.line.text) : "Line pending"}<span>${esc(imp)}</span></div>
      ${heatHTML(g.heat, g.away, g.home)}
      ${g.model ? `<div class="mline"><span>MODEL</span><b>${g.home} ${Math.round(g.model.p_home * 100)}%</b>${g.model.mkt !== null ? `<span>MKT</span><b>${g.home} ${Math.round(g.model.mkt * 100)}%</b>` : ""}</div>` : ""}
      ${g.tease ? `<p class="tease">${esc(g.tease[0])}<span>${esc(g.tease[1])}</span></p>` : ""}
      <div class="lev" title="Playoff leverage"><i style="width:${(g.leverage / maxLev) * 100}%"></i></div>`;
    grid.appendChild(tile);
  });
}
async function matchup(id, tab, focus) {
  const G = S.games, app = $("#app");
  const g = await getJSON(`data/${G.season}/wk${String(G.week).padStart(2, "0")}/${id}.json`);
  const imgs = [...g.team_cards, ...g.player_cards].flatMap(c => (c.chart.pts || []).map(p => p.img));
  await preload(imgs);
  const a = T(g.away), hm = T(g.home);
  const imp = g.line && g.line.implied ? `Implied: ${g.away} ${g.line.implied[g.away]} · ${g.home} ${g.line.implied[g.home]}` : "";
  const stake = t => g.leverage.p_playoffs && g.leverage.p_playoffs[t] !== undefined
    ? `<span class="chip">${t} playoff odds ${Math.round(g.leverage.p_playoffs[t] * 100)}% · swing ${Math.round(Math.abs(g.leverage.by_team[t] || 0) * 100)} pts</span>` : "";
  app.innerHTML = `<section class="hero" style="--a:${a.accent};--h:${hm.accent}">
      <div class="side">${logoHTML(g.away)}<div><h2>${esc(a.nick)}</h2><small>${esc(a.name)}</small></div></div>
      <div class="mid"><div class="k">${esc(g.kickoff)}${g.primetime ? " · PRIMETIME" : ""}${g.after_kickoff ? " · BUILT AFTER KICKOFF (PRE-WEEK DATA ONLY)" : ""}</div>
        <div class="ln">${g.line ? esc(g.line.text) : "Line pending"}</div><div class="imp">${esc(imp)}${g.line_asof ? ` · line as of ${esc(g.line_asof.slice(5, 10).replace("-", "/"))}` : ""}</div>
        <div class="stakes">${stake(g.away)}${stake(g.home)}</div></div>
      <div class="side home">${logoHTML(g.home)}<div><h2>${esc(hm.nick)}</h2><small>${esc(hm.name)}</small></div></div>
    </section>
    ${g.summary ? `<p class="summary"><b>THE PREVIEW</b>${esc(g.summary)}</p>` : ""}
    <section class="keys">${[g.away, g.home].map(t => `<div class="keyset" style="--acc:${T(t).accent}">
      <h3>${logoHTML(t)}${esc(T(t).nick)}: 3 keys to success</h3><ol>${(g.keys[t] || []).map((k, i) => `<li><i>${i + 1}</i><div>
        <b>${esc(k.phrase)}<em class="${k.favorable ? "up" : "dn"}">${k.favorable ? "EDGE" : "WATCH"}</em></b><p>${esc(k.detail)}</p></div></li>`).join("")}</ol></div>`).join("")}</section>
    <div class="tabs"><div role="tablist"><button role="tab" data-tab="team">TEAM</button><button role="tab" data-tab="players">PLAYERS</button>${(g.model_cards || []).length ? '<button role="tab" data-tab="model">MODEL</button>' : ""}</div>
      <label class="topn">SHOW <select aria-label="How many cards to show"><option value="auto">Top picks</option><option value="10">Top 10</option></select></label></div>
    <div class="cards"></div>`;
  const topSel = $(".topn select", app);
  try { topSel.value = localStorage.getItem("topn") || "auto"; } catch (e) { /* storage blocked */ }
  let cur = "team";
  const show = t => {
    cur = t;
    app.querySelectorAll(".tabs button").forEach(b => b.setAttribute("aria-selected", String(b.dataset.tab === t)));
    const box = $(".cards", app); box.innerHTML = "";
    $(".topn", app).style.visibility = t === "model" ? "hidden" : "visible";
    const all = t === "players" ? g.player_cards : t === "model" ? g.model_cards : g.team_cards;
    const n = t === "model" ? all.length : topSel.value === "10" ? 10 : (t === "players" ? g.player_n : g.team_n) ?? all.length;
    const list = all.slice(0, n);
    if (t === "model" && g.model) box.insertAdjacentHTML("beforeend", `<p class="summary model-sum"><b>OUR NUMBER VS. THE MARKET</b>${esc(g.model.summary)}<span>A different lens on the data, not betting advice.</span></p>`);
    if (!list.length) box.innerHTML = '<p class="empty">No cards cleared the sample-size bar for this matchup.</p>';
    list.forEach((c, i) => { const e = cardEl(c, g); e.style.animationDelay = `${i * 60}ms`; box.appendChild(e); });
  };
  topSel.onchange = () => { try { localStorage.setItem("topn", topSel.value); } catch (e) { /* storage blocked */ } show(cur); };
  app.querySelectorAll(".tabs button").forEach(b => b.onclick = () => {
    show(b.dataset.tab); history.replaceState(null, "", `#/${G.season}/${G.week}/${id}` + (b.dataset.tab !== "team" ? "?tab=" + b.dataset.tab : ""));
  });
  if (focus && ![...g.team_cards.slice(0, g.team_n), ...g.player_cards.slice(0, g.player_n)].some(c => c.id === focus)) topSel.value = "10";
  const ftab = focus && [...g.player_cards].some(c => c.id === focus) ? "players" : tab;
  show(["players", "model"].includes(ftab) && (ftab !== "model" || (g.model_cards || []).length) ? ftab : "team");
  if (focus) { const e = document.getElementById("card-" + focus.replace(/[^a-z0-9]/gi, "-")); if (e) e.scrollIntoView({ block: "center" }); }
}

/* ---------- routing ---------- */
async function loadWeek(season, week) {
  if (S.week && S.week.season === season && S.week.week === week) return;
  S.games = await getJSON(`data/${season}/wk${String(week).padStart(2, "0")}/games.json`);
  S.week = { season, week };
  await preload(Object.values(S.teams).map(t => t.logo));
  await preload(Object.values(S.teams).filter(t => !S.ok[t.logo]).map(t => t.logo_url));
  const gs = $("#game-select");
  gs.innerHTML = `<option value="">All games (board)</option>` + S.games.games.map(g =>
    `<option value="${g.id}">${g.away} at ${g.home} · ${esc(g.kickoff.split(" · ")[0])}${g.primetime ? " · PRIME" : ""}</option>`).join("");
  const b = $("#banner");
  b.hidden = !S.games.synthetic; b.textContent = "SYNTHETIC TEST DATA · NOT REAL NFL STATS";
  $("#built").textContent = `Built ${S.games.built} · ${S.games.span}`;
}
async function route() {
  const [path, q] = location.hash.replace(/^#\/?/, "").split("?");
  const params = new URLSearchParams(q || location.search);
  const parts = path.split("/").filter(Boolean);
  const latest = S.idx.latest;
  const season = +(parts[0] || latest.season), week = +(parts[1] || latest.week), id = parts[2] || "";
  try { await loadWeek(season, week); } catch (e) { $("#app").innerHTML = '<p class="empty">That week has no report yet.</p>'; return; }
  $("#week-select").value = `${season}/${week}`;
  $("#game-select").value = id;
  window.scrollTo(0, 0);
  if (id) await matchup(id, params.get("tab"), params.get("card")); else board();
}
async function init() {
  S.idx = await getJSON("data/index.json");
  S.teams = await getJSON("data/teams.json");
  S.handle = S.idx.handle || "";
  const ws = $("#week-select");
  ws.innerHTML = [...S.idx.weeks].reverse().map(w => `<option value="${w.season}/${w.week}">Week ${w.week}, ${w.season}${w.synthetic ? " (test)" : ""}</option>`).join("");
  ws.onchange = () => { location.hash = `#/${ws.value}`; };
  $("#game-select").onchange = e => { const [s, w] = ws.value.split("/"); location.hash = `#/${s}/${w}${e.target.value ? "/" + e.target.value : ""}`; };
  window.addEventListener("hashchange", route);
  route();
}
init().catch(e => { console.error(e); $("#app").innerHTML = '<p class="empty">No reports built yet. Run the weekly workflow.</p>'; });
