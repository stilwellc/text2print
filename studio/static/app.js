import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const $ = (id) => document.getElementById(id);
const el = (tag, attrs = {}, ...kids) => {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") n.className = v; else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else if (v !== undefined && v !== null && v !== false) n.setAttribute(k, v === true ? "" : v);
  }
  for (const k of kids) if (k !== null && k !== undefined) n.append(k);
  return n;
};
const fmt = (n, d = 0) => Number(n).toLocaleString(undefined, { maximumFractionDigits: d, minimumFractionDigits: d });
const minutes = (m) => { const h = Math.floor(m / 60), r = Math.round(m % 60); return `${h ? h + " h " : ""}${r} min`; };
const MAX_SLOTS = 4;
const FAMILY_NAMES = { lattice: "Woven", fabric: "Fabric", droop: "Droop", halftone: "Halftone", spiral: "Vase mode",
  shell: "Shell", flat: "Flat", mix: "Mix" };
// options that only apply to some textures
const ONLY = { folds: ["pleats", "flutes", "twist", "lowpoly", "ribs"], turn: ["twist", "lowpoly"], cell: ["voronoi"],
  noise: ["fuzzy"], fuzzy_bands: ["fuzzy"], picture: ["litho", "halftone", "flatlitho", "cmyk"], length: ["fringe", "swag", "curls", "unraveled", "fur"] };
const IMAGE_TEXTURES = ["halftone", "litho", "flatlitho", "cmyk"];
// mix bands with two colour slots: halftone (picture/background) and woven (one colour per rod direction)
const twoSlot = (t) => t === "halftone" || (CAT && CAT.mix.textures.find((x) => x.key === t)?.family === "lattice");

let CAT = null;
const state = { shape: null, texture: null, nozzle: 0.4, params: {}, colours: [], options: {}, bands: null, mixPreset: null, family: null };
let job = null;
let draped = true;

// ── catalogue helpers ──────────────────────────────────────────────────────────
const shapeOf = (k) => CAT.shapes.find((s) => s.key === k);
const textureOf = (k) => CAT.textures.find((t) => t.key === k);
const fits = (shape, tex) => tex.fits.includes(shape.key);
const nameOfColour = (hex) => Object.entries(CAT.palette).find(([, h]) => h.toLowerCase() === hex.toLowerCase())?.[0] || hex.toUpperCase();
const isMix = () => textureOf(state.texture).family === "mix";
const familyOptions = () => CAT.options[textureOf(state.texture).family] || [];
const zonesOn = () => {
  const fam = textureOf(state.texture).family;
  return fam === "fabric" || fam === "droop" || fam === "shell" || (fam === "lattice" && state.options.colour_by === "height");
};
function slotCount() {
  if (!isMix() && zonesOn()) return Math.max(1, parseInt(state.options.zones || "1", 10));
  if (!isMix()) return textureOf(state.texture).slots;
  return Math.max(1, ...state.bands.flatMap((b) => twoSlot(b.texture) ? [b.slot + 1, (b.slot2 ?? 1) + 1] : [b.slot + 1]));
}

// ── url state ──────────────────────────────────────────────────────────────────
function readUrl() {
  const q = new URLSearchParams(location.search);
  if (q.get("shape") && shapeOf(q.get("shape"))) state.shape = q.get("shape");
  if (q.get("texture") && textureOf(q.get("texture"))) state.texture = q.get("texture");
  if (q.get("nozzle")) state.nozzle = parseFloat(q.get("nozzle"));
  if (q.get("c")) state.colours = q.get("c").split(",").map((h) => "#" + h.replace("#", ""));
  const optKeys = Object.values(CAT.options).flat().map((o) => o.key).concat(["picture", "image", "lid", "lid_colour", "lid_fit"]);
  for (const [k, v] of q) {
    if (k === "mix") { try { state.bands = JSON.parse(v); } catch (e) { /* a bad link keeps the default */ } }
    else if (optKeys.includes(k)) state.options[k] = v === "1" ? true : v === "0" ? false : v;
    else if (!["shape", "texture", "nozzle", "c"].includes(k)) state.params[k] = parseFloat(v);
  }
}
function linkFor() {
  const q = new URLSearchParams({ shape: state.shape, texture: state.texture, nozzle: state.nozzle });
  for (const p of shapeOf(state.shape).params) if (state.params[p.key] !== undefined && state.params[p.key] !== p.default) q.set(p.key, state.params[p.key]);
  q.set("c", state.colours.slice(0, slotCount()).map((h) => h.replace("#", "")).join(","));
  if (isMix()) q.set("mix", JSON.stringify(state.bands));
  for (const o of familyOptions()) {
    const v = state.options[o.key] ?? o.default;
    if (v !== o.default) q.set(o.key, v === true ? "1" : v === false ? "0" : v);
  }
  if (state.options.image && textureOf(state.texture).family === "halftone") q.set("image", state.options.image);
  if (state.options.lid && state.options.lid !== "none" && shapeOf(state.shape).lid) {
    q.set("lid", state.options.lid); if (state.options.lid_colour) q.set("lid_colour", state.options.lid_colour);
    if (state.options.lid_fit) q.set("lid_fit", state.options.lid_fit);
  }
  if (state.options.image && IMAGE_TEXTURES.includes(state.texture)) q.set("image", state.options.image);
  return "?" + q.toString();
}
const writeUrl = () => history.replaceState(null, "", linkFor());

// ── picker ─────────────────────────────────────────────────────────────────────
function seg(container, items, current, onPick) {
  container.replaceChildren(...items.map(([value, label, title]) => el("button", {
    role: "radio", "aria-checked": String(value === current), title, onclick: () => onPick(value),
  }, label)));
}
function badge(t) {
  const st = t.status?.[state.nozzle];
  if (st === "printed") return el("span", { class: "badge" }, "Printed");
  if (st === "published") return el("span", { class: "badge pub" }, "Published");
  if (st === "failed") return el("span", { class: "badge fail" }, "Failed");
  return null;
}
function card(item, checked, onPick, extra) {
  return el("button", { class: "card", role: "radio", "aria-checked": String(checked), title: item.blurb, onclick: onPick },
    el("img", { src: item.thumb, alt: "", loading: "lazy" }), el("span", {}, item.name), extra || null);
}

function renderNozzles() {
  seg($("nozzles"), CAT.nozzles.map((n) => [n.size, `${n.size}`, `${n.size} mm nozzle · ${n.layer} mm layers${n.verified ? " · print-verified" : ""}`]),
    state.nozzle, (v) => { state.nozzle = v; renderNozzles(); renderTextures(); changed(); });
}
function renderShapes() {
  $("shapes").replaceChildren(...CAT.shapes.map((s) => card(s, s.key === state.shape, () => pickShape(s.key))));
}
function pickShape(key) {
  const prevFamily = textureOf(state.texture)?.family;
  state.shape = key; state.params = {};
  const sh = shapeOf(key);
  if (!fits(sh, textureOf(state.texture))) {
    const same = CAT.textures.find((t) => fits(sh, t) && t.family === prevFamily);
    state.texture = (same || CAT.textures.find((t) => fits(sh, t))).key;
  }
  state.family = textureOf(state.texture).family;
  renderAll(); changed(true);
}
function renderTextures() {
  const sh = shapeOf(state.shape);
  const fams = Object.keys(FAMILY_NAMES).filter((f) => CAT.textures.some((t) => t.family === f && fits(sh, t)));
  if (!fams.includes(state.family)) state.family = textureOf(state.texture).family;
  seg($("families"), fams.map((f) => [f, FAMILY_NAMES[f]]), state.family, (f) => {
    state.family = f;
    if (textureOf(state.texture).family !== f) { state.texture = CAT.textures.find((t) => t.family === f && fits(sh, t)).key; renderAll(); changed(); }
    else renderTextures();
  });
  const list = CAT.textures.filter((t) => t.family === state.family && fits(sh, t));
  $("textures").replaceChildren(
    el("div", { class: "cards" }, ...list.map((t) => card(t, t.key === state.texture, () => { state.texture = t.key; renderAll(); changed(); }, badge(t)))),
    el("p", { class: "desc" }, textureOf(state.texture).family === state.family ? textureOf(state.texture).blurb : "Pick one to switch."));
}

// sizes + the drawn profile for "Your shape"
function renderSizes() {
  const sh = shapeOf(state.shape), fam = textureOf(state.texture).family;
  const curveKeys = ["c0", "c1", "c2", "c3", "c4"];
  const custom = sh.key === "custom";
  $("curve").hidden = !custom;
  if (custom) renderCurve(sh);
  $("sizes").replaceChildren(...sh.params.filter((p) => (!p.family || p.family === fam) && !(custom && curveKeys.includes(p.key))).map((p) => {
    const val = state.params[p.key] ?? p.default;
    const num = el("input", { type: "number", class: "exact", min: p.lo, max: p.hi, step: p.step, value: val, "aria-label": `${p.label} in ${p.unit}` });
    const input = el("input", { type: "range", min: p.lo, max: p.hi, step: p.step, value: val, id: `p_${p.key}`, "aria-label": p.label });
    input.addEventListener("input", () => {
      state.params[p.key] = parseFloat(input.value); num.value = input.value; changed(false, true);
      if (custom) renderCurve(sh);
    });
    input.addEventListener("change", () => changed());
    num.addEventListener("change", () => {
      const v = Math.min(p.hi, Math.max(p.lo, parseFloat(num.value) || p.default));
      num.value = v; input.value = v; state.params[p.key] = v; changed(); if (custom) renderCurve(sh);
    });
    return el("div", { class: "size-row" }, el("label", { for: `p_${p.key}` }, p.label),
      el("span", { class: "exact-wrap" }, num, el("span", { class: "unit" }, p.unit)), input);
  }));
}
function renderCurve(sh) {
  const W = 300, H = 220, pad = 18;
  const get = (k) => state.params[k] ?? sh.params.find((p) => p.key === k).default;
  const pts = [0, 1, 2, 3, 4].map((i) => ({ i, y: H - pad - i * (H - 2 * pad) / 4, x: W / 2 + (get(`c${i}`) / 100) * (W / 2 - pad) }));
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg"); svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("aria-label", "Silhouette: drag the points to shape the profile");
  const mk = (tag, attrs) => { const n = document.createElementNS(ns, tag); for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v); return n; };
  const path = (side) => pts.map((p, j) => `${j ? "L" : "M"}${W / 2 + side * (p.x - W / 2)},${p.y}`).join(" ");
  svg.append(mk("line", { x1: W / 2, y1: pad / 2, x2: W / 2, y2: H - pad / 2, stroke: "#d8d0c3", "stroke-dasharray": "3 4" }));
  svg.append(mk("path", { d: path(-1), fill: "none", stroke: "#c8beb0", "stroke-width": 1.5 }));
  svg.append(mk("path", { d: path(1), fill: "none", stroke: "#1C1915", "stroke-width": 2 }));
  svg.append(mk("line", { x1: W / 2 - (pts[0].x - W / 2), y1: H - pad, x2: pts[0].x, y2: H - pad, stroke: "#1C1915", "stroke-width": 2 }));
  for (const p of pts) {
    const c = mk("circle", { cx: p.x, cy: p.y, r: 9, fill: "#fff", stroke: "#1C1915", "stroke-width": 2, class: "pt", tabindex: 0,
      "aria-label": `${["Foot", "Lower", "Middle", "Upper", "Rim"][p.i]} width` });
    const set = (clientX) => {
      const r = svg.getBoundingClientRect(); const x = (clientX - r.left) / r.width * W;
      state.params[`c${p.i}`] = Math.round(Math.min(100, Math.max(20, (x - W / 2) / (W / 2 - pad) * 100)));
      renderCurve(sh); changed(false, true);
    };
    c.addEventListener("pointerdown", (e) => {
      c.setPointerCapture(e.pointerId);
      const move = (ev) => set(ev.clientX);
      const up = () => { c.removeEventListener("pointermove", move); c.removeEventListener("pointerup", up); changed(); };
      c.addEventListener("pointermove", move); c.addEventListener("pointerup", up);
    });
    c.addEventListener("keydown", (e) => {
      if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
      state.params[`c${p.i}`] = Math.min(100, Math.max(20, get(`c${p.i}`) + (e.key === "ArrowRight" ? 2 : -2)));
      renderCurve(sh); changed(); e.preventDefault();
    });
    svg.append(c);
  }
  $("curve").replaceChildren(svg, el("p", { class: "hint" }, "Drag the points to draw the silhouette. It stays printable: the wall never leans out past about 42°."));
}

// colours
function renderColours() {
  const tex = textureOf(state.texture);
  while (state.colours.length < MAX_SLOTS) state.colours.push(CAT.colours[state.colours.length % CAT.colours.length]);
  const n = slotCount();
  $("colours").replaceChildren(...Array.from({ length: n }, (_, i) => el("button", {
    class: "swatch-btn", onclick: (e) => openPalette(i, e.currentTarget),
  }, el("span", { class: "chip", style: `background:${state.colours[i]}` }), el("span", { class: "name" }, nameOfColour(state.colours[i])),
     el("span", { class: "slot" }, `AMS ${i + 1}`))));
  $("colourHint").textContent = isMix() ? (n === 1 ? "One colour — no AMS changes. Give a band another colour in Bands."
      : "Each band picks its AMS slot. Changes happen where bands meet, every layer inside a halftone band, and every course inside a woven band.")
    : zonesOn() && n > 1 && tex.family === "droop" && (state.options.zone_style ?? "courses") === "courses"
      ? "Courses, like woven: each row of strands and the wall it hangs from take the next colour — one AMS change per course. More rows per colour, fewer changes."
    : zonesOn() && n > 1 ? (state.options.zone_style === "stripes" ? "Stripes repeat the colours up the piece — one AMS change per stripe." : "Colours stack in bands from the bottom — one AMS change where each band starts.")
    : zonesOn() ? "One colour — add colours under Finish › Colours."
    : tex.slots === 1 ? "One colour — no AMS changes."
    : state.texture === "cmyk" ? "Load cyan, magenta, yellow and white in slots 1–4. The AMS changes only where an ink starts or stops."
    : tex.family === "halftone" ? "Colour 1 paints the picture, colour 2 the background. The AMS changes every layer — pick strong contrast."
    : tex.swaps === "layer" ? "Colours mix inside every course, so the AMS changes about once per layer. Pick the same colour twice for a one-colour print."
    : "Colour follows rod direction: one AMS change per course. Pick the same colour twice for a one-colour print.";
}
function openPalette(slot, anchor) {
  const pop = $("palette"), r = anchor.getBoundingClientRect();
  const name = el("div", { class: "pname" }, nameOfColour(state.colours[slot]));
  pop.replaceChildren(...Object.entries(CAT.palette).map(([n, hex]) => el("button", {
    style: `background:${hex}`, title: n, "aria-label": n, "aria-checked": String(hex.toLowerCase() === state.colours[slot].toLowerCase()),
    onmouseenter: () => { name.textContent = n; },
    onclick: () => { state.colours[slot] = hex; pop.hidden = true; renderColours(); renderBands(); changed(); },
  })), name);
  pop.hidden = false;
  pop.style.left = `${Math.min(r.left, innerWidth - 284)}px`; pop.style.top = `${Math.min(r.bottom + 8, innerHeight - pop.offsetHeight - 12)}px`;
}
document.addEventListener("pointerdown", (e) => {
  if (!$("palette").hidden && !$("palette").contains(e.target) && !e.target.closest(".swatch-btn")) $("palette").hidden = true;
});

// image upload (halftone)
function uploader(current, onDone) {
  const input = el("input", { type: "file", accept: "image/png,image/jpeg,image/webp", hidden: true });
  input.addEventListener("change", async () => {
    const f = input.files[0]; if (!f) return;
    const fd = new FormData(); fd.append("image", f);
    const r = await fetch("/api/upload", { method: "POST", body: fd }); const d = await r.json();
    if (!r.ok) { toast(d.error || "Upload failed"); return; }
    onDone(d.id);
  });
  return el("div", { class: "upload" }, input,
    current ? el("img", { src: `/api/image/${current}`, alt: "Your picture" }) : null,
    el("button", { class: "ghost", onclick: () => input.click() }, current ? "Change picture" : "Use your own picture…"),
    current ? el("button", { class: "linkbtn", onclick: () => onDone(null) }, "Remove") : null);
}

// finish options (texture options, colour zones, lid)
function optionControl(o, onChange) {
  const val = state.options[o.key] ?? o.default;
  if (o.kind === "toggle") {
    const input = el("input", { type: "checkbox" }); input.checked = !!val;
    input.addEventListener("change", () => { state.options[o.key] = input.checked; onChange(); });
    return [el("label", { class: "toggle" }, input, el("span", {}, o.label))];
  }
  const box = el("div", { class: "seg small", role: "radiogroup", "aria-label": o.label });
  seg(box, o.choices.map(([v, l]) => [v, l]), val, (v) => { state.options[o.key] = v; onChange(); });
  return [el("div", { class: "field-label" }, o.label), box];
}
function renderFinish() {
  const fam = textureOf(state.texture).family, sh = shapeOf(state.shape);
  const after = () => { renderFinish(); renderColours(); changed(); };
  const shown = familyOptions().filter((o) => {
    if (ONLY[o.key] && !ONLY[o.key].includes(state.texture)) return false;
    if (o.key === "zones") return zonesOn();
    if (o.key === "zone_style") return zonesOn() && parseInt(state.options.zones || "1", 10) > 1;
    if (o.key === "course_rows") return zonesOn() && parseInt(state.options.zones || "1", 10) > 1
      && (state.options.zone_style ?? "courses") === "courses" && state.texture !== "fur";
    return true;
  });
  const kids = shown.flatMap((o) => optionControl(o, after));
  if (IMAGE_TEXTURES.includes(state.texture)) kids.splice(Math.min(2, kids.length), 0, uploader(state.options.image, (id) => { if (id) state.options.image = id; else delete state.options.image; renderFinish(); changed(); }));
  if (sh.lid && fam !== "flat") {
    kids.push(...optionControl({ key: "lid", label: "Lid", kind: "seg", choices: [["none", "None"], ["slip", "Slip-on"], ["thread", "Screw"], ["magnets", "Magnets"]], default: "none" }, after));
    if (state.options.lid && state.options.lid !== "none")
      kids.push(...optionControl({ key: "lid_fit", label: "Lid fit", kind: "seg", choices: [["snug", "Snug 0.15"], ["slip", "Slip 0.25"], ["loose", "Loose 0.40"]], default: "slip" }, after));
    if (state.options.lid && state.options.lid !== "none" && slotCount() > 1)
      kids.push(...optionControl({ key: "lid_colour", label: "Lid colour", kind: "seg",
        choices: Array.from({ length: slotCount() }, (_, i) => [String(i + 1), `AMS ${i + 1}`]), default: "1" }, after));
  }
  $("finishSec").hidden = !kids.length;
  $("finish").replaceChildren(...kids);
}

// mix bands
function renderBands() {
  $("mixSec").hidden = !isMix();
  if (!isMix()) return;
  const M = CAT.mix;
  seg($("mixPresets"), M.presets.map((p) => [p.key, p.name]), state.mixPreset,
    (k) => { state.mixPreset = k; state.bands = structuredClone(M.presets.find((p) => p.key === k).bands); renderBands(); renderColours(); changed(); });
  const total = state.bands.reduce((a, b) => a + b.share, 0);
  const edit = () => { state.mixPreset = null; renderBands(); renderColours(); changed(); };
  const chip = (b, key) => {
    const i = b[key] ?? 0;
    return el("button", { class: "chip-btn", style: `background:${state.colours[i]}`, title: `AMS ${i + 1} — click to change`, "aria-label": `Colour AMS ${i + 1}`,
      onclick: () => { b[key] = (i + 1) % MAX_SLOTS; edit(); } }, el("span", {}, String(i + 1)));
  };
  const rows = state.bands.map((b, idx) => {
    const groups = {};
    for (const t of M.textures) (groups[t.family] ||= []).push(t);
    const sel = el("select", { "aria-label": "Band texture" }, ...Object.entries(groups).map(([fam, ts]) =>
      el("optgroup", { label: fam === "plain" ? "Plain" : (FAMILY_NAMES[fam] || fam) }, ...ts.map((t) => {
        const o = el("option", { value: t.key }, t.name); if (t.key === b.texture) o.selected = true; return o; }))));
    sel.addEventListener("change", () => { b.texture = sel.value; b.options = {}; if (twoSlot(b.texture) && b.slot2 === undefined) b.slot2 = (b.slot + 1) % MAX_SLOTS; edit(); });
    const out = el("output", {}, `${Math.round(100 * b.share / total)}%`);
    const range = el("input", { type: "range", min: 3, max: 90, step: 1, value: b.share, "aria-label": "Band height" });
    range.addEventListener("input", () => { b.share = +range.value; out.textContent = `${Math.round(100 * b.share / state.bands.reduce((a, x) => a + x.share, 0))}%`; state.mixPreset = null; changed(false, true); });
    range.addEventListener("change", () => changed());
    const kids = [sel, el("div", { class: "chips" }, chip(b, "slot"), twoSlot(b.texture) ? chip(b, "slot2") : null),
      el("button", { class: "x", title: "Remove band", "aria-label": "Remove band", disabled: state.bands.length < 2, onclick: () => { state.bands.splice(idx, 1); edit(); } }, "×"),
      el("div", { class: "share" }, range, out)];
    const fam = M.textures.find((t) => t.key === b.texture).family;
    if (fam === "droop" || b.texture === "halftone" || b.texture === "fuzzy") {
      const key = fam === "droop" ? "density" : b.texture === "fuzzy" ? "noise" : "picture";
      const box = el("div", { class: "seg small sub" });
      seg(box, fam === "droop" ? M.droop_options : b.texture === "fuzzy" ? M.noises : M.pictures,
        (b.options || {})[key] ?? (fam === "droop" ? "medium" : b.texture === "fuzzy" ? "perlin" : "flames"),
        (v) => { b.options = { ...(b.options || {}), [key]: v }; edit(); });
      kids.push(box);
      if (b.texture === "halftone") kids.push(el("div", { class: "sub" }, uploader((b.options || {}).image, (id) => { b.options = { ...(b.options || {}) }; if (id) b.options.image = id; else delete b.options.image; edit(); })));
    }
    return el("div", { class: "band" }, ...kids);
  });
  $("bands").replaceChildren(...rows.reverse());
  $("addBand").disabled = state.bands.length >= 6;
}
$("addBand").addEventListener("click", () => {
  const top = state.bands[state.bands.length - 1];
  state.bands.push({ texture: "plain", share: 15, slot: top ? top.slot : 0 }); state.mixPreset = null;
  renderBands(); renderColours(); changed();
});

function renderAll() { renderShapes(); renderTextures(); renderBands(); renderSizes(); renderColours(); renderFinish(); }

// ── building: drafts while dragging, full on release; newer requests cancel older ones ─────
let timer = null, reqSeq = 0, reframe = true;
function changed(newShape = false, dragging = false) {
  if (newShape) reframe = true;
  writeUrl(); clearTimeout(timer);
  timer = setTimeout(() => requestBuild(dragging), dragging ? 90 : 220);
}
async function requestBuild(draft) {
  const seq = ++reqSeq;
  $("status").hidden = false;
  $("statusText").textContent = draft ? "Sketching…" : ({ fabric: "Knitting…", droop: "Spinning strands…", halftone: "Screening…", mix: "Stacking bands…", spiral: "Folding…", shell: "Shaping…", flat: "Mapping the picture…" }[textureOf(state.texture).family] || "Weaving…");
  try {
    const res = await fetch("/api/build", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ shape: state.shape, texture: state.texture, nozzle: state.nozzle, params: state.params, draft,
        colours: state.colours.slice(0, slotCount()), options: isMix() ? { bands: state.bands, purge: state.options.purge, lid: state.options.lid, lid_colour: state.options.lid_colour, lid_fit: state.options.lid_fit } : state.options }) });
    const data = await res.json();
    if (res.status === 409 || seq !== reqSeq) return;               // superseded by a newer request
    if (!res.ok) throw new Error(data.error || "Build failed");
    job = data; $("error").hidden = true;
    renderDropView(data); await showModel(data); renderPrint(data);
  } catch (e) {
    if (seq === reqSeq) { $("error").textContent = e.message; $("error").hidden = false; }
  } finally {
    if (seq === reqSeq) $("status").hidden = true;
  }
}

// ── print panel ────────────────────────────────────────────────────────────────
function renderPrint(d) {
  const tex = textureOf(state.texture), s = d.stats;
  $("title").textContent = d.title; $("blurb").textContent = `${shapeOf(state.shape).blurb}. ${tex.blurb}.`;
  const rows = [["Size", `${fmt(s.size[0])} × ${fmt(s.size[1])} × ${fmt(s.size[2], 1)} mm`]];
  if (s.rods) rows.push(["Rods", `${fmt(s.rods)} · ${s.courses} courses`]);
  if (s.stitches) rows.push(["Stitches around", fmt(s.stitches)]);
  if (s.bands) rows.push(["Bands × layers", `${s.bands} × ${fmt(s.layers)}`]);
  if (s.ribs) rows.push(["Ribs × layers", `${fmt(s.ribs)} × ${fmt(s.layers)}`]);
  if (s.strands) rows.push(["Strands", `${fmt(s.strands)} · up to ${fmt(s.reach)} mm out`]);
  if (s.lid) rows.push(["Lid", `${{ slip: "Slip-on", thread: "Screw", magnets: "Magnets" }[s.lid.style] || "Lid"} · plug ${fmt(s.lid.plug, 1)} mm · ${s.lid.clearance} mm fit`]);
  rows.push(["Colours", String(s.colours)]);
  if (s.swaps) rows.push(["AMS changes", `${fmt(s.swaps)} · ≈ ${fmt(s.swap_minutes)} min`]);
  rows.push(["Filament", s.grams_purge ? `≈ ${fmt(s.grams_part)} g + ${fmt(s.grams_purge)} g purge` : `≈ ${fmt(s.grams_est)} g`]);
  $("stats").replaceChildren(...rows.flatMap(([k, v]) => [el("dt", {}, k), el("dd", {}, v)]));
  $("dims").replaceChildren(`${fmt(s.size[0])} × ${fmt(s.size[1])} × ${fmt(s.size[2], 1)} mm`,
    el("span", { class: "tris" }, d.draft ? " · sketch" : ` · ${fmt(s.triangles / 1e6, 2)} M triangles`));
  renderSlice(d.slice);
  $("openBtn").textContent = CAT.slicer ? "Open in Bambu Studio" : "Save to Downloads";
  $("sendBtn").hidden = !CAT.lan.configured || !CAT.slicer;
  $("dl3mf").href = `/api/job/${d.id}/download`; $("dlStl").href = `/api/job/${d.id}/stls`;
  const noz = CAT.nozzles.find((n) => n.size === s.nozzle);
  const notes = [...d.warnings];
  if (tex.swaps === "layer" && s.colours > 1 && !["halftone", "flat"].includes(tex.family)) notes.push("This pattern changes colour about once per layer — expect a long print, or pick one colour.");
  if ((tex.family === "halftone" || isMix()) && s.swaps > 300) notes.push(`${fmt(s.swaps)} colour changes — Lean purge, a 0.8 nozzle or a shorter halftone band cut that a lot.`);
  notes.push({
    lattice: "No supports, no infill — the rods are the object. Print on a clean plate, no brim.",
    fabric: "Vase mode off. The layer height must stay at " + noz.layer + " mm — the pattern is built on it.",
    droop: state.texture === "fur" ? "Hairs print as fast bridges at full fan, a little cooler, so they stay stiff — keep the project's cooling." : "Glossy or translucent PETG/PLA shows the strands best. Don't slow overhangs down or raise the fan — the strands only droop while molten.",
    halftone: `Prints at ${s.layer_h} mm layers with one ${s.line} mm line — keep those, the picture is built on them.`,
    ...{},
    shell: { voronoi: "Every cell has a pointed roof, so the holes print without supports.",
      litho: "The picture shows when lit from inside: an LED puck or tealight, never a flame.",
      fuzzy: null }[state.texture],
    mix: "Keep the project's layer heights — each band is built on its own. Halftone bands print at their recipe height through a layer range.",
  }[tex.family]);
  if (s.lid) notes.push("The lid and knob print top-face down beside the piece; press the knob into the lid from the top.");
  $("notes").replaceChildren(...notes.filter(Boolean).map((n) => el("li", {}, n)));
  const bl = $("backlit"); bl.hidden = !s.backlit;
  if (s.backlit) bl.replaceChildren(el("img", { src: s.backlit, alt: "The picture as it shows lit from behind" }),
    el("figcaption", {}, "Lit from behind (estimate)"));
  const set = [["Printer", CAT.printer.name], ["Nozzle", `${s.nozzle} mm`], ["Layer height", `${s.layer_h} mm`],
    ...({ lattice: [["Rod", s.rod], ["Rod spacing", `${s.pitch} mm`], ["Walls", "rods only"], ["Infill", "0%"]],
          fabric: [["Walls", "2 loops"], ["Infill", "0%"], ["Top layers", "0"]],
          mix: [["Walls", "2 loops"], ["Infill", "0%"], ["Bands", `${s.bands}`]],
          spiral: [["Mode", "spiral vase"], ["Walls", "1"], ["Infill", "0%"]],
          shell: [["Walls", state.texture === "litho" ? "solid (lithophane)" : "2–4 loops"], ["Infill", "0%"]],
          flat: [["Layer height", `${s.layer_h} mm`], ["Pixel", `${s.pixel} mm`], ["Solid", "100%"]],
          halftone: [["Line width", `${s.line} mm, 1 wall`], ["Infill", "0%"], ["Colour changes", "every layer"]],
          droop: [["Walls", "2 loops, strands 1 line"], ["Overhang slow-down", "off"], ["Fan", "≤ 20%"], ["Nozzle", "+5 °C"]] }[tex.family]),
    ["Supports", "none"], ["Filament", "Bambu PLA Matte"]];
  $("settings").replaceChildren(...set.flatMap(([k, v]) => [el("dt", {}, k), el("dd", {}, v)]));
}
function renderSlice(sl) {
  const btn = $("sliceBtn");
  btn.disabled = !CAT.slicer; btn.textContent = "Get exact print time";
  if (!sl || sl.state === "idle") { $("slice").replaceChildren(); return; }
  if (sl.state === "running") { btn.disabled = true; btn.textContent = "Slicing in Bambu Studio…"; $("slice").replaceChildren(el("span", { class: "sub" }, "Slicing on the real P2S profile, colour changes included.")); return; }
  if (sl.state === "error") { $("slice").replaceChildren(el("span", { class: "sub" }, `Slicer: ${sl.error}${sl.detail ? " — " + sl.detail : ""}`)); return; }
  btn.disabled = true; btn.textContent = "Sliced";
  $("slice").replaceChildren(el("span", { class: "big" }, minutes(sl.minutes)),
    el("span", { class: "sub" }, `${fmt(sl.grams, 0)} g · ${fmt(sl.layers)} layers`), el("br"),
    el("span", { class: "sub" }, `Bambu Studio's own numbers for the P2S, AMS changes and purge included.`));
}

$("sliceBtn").addEventListener("click", async () => {
  if (!job) return;
  const id = job.id;
  renderSlice({ state: "running" });
  await fetch(`/api/job/${id}/slice`, { method: "POST" });
  for (;;) {
    await new Promise((r) => setTimeout(r, 1500));
    if (!job || job.id !== id) return;
    const s = await (await fetch(`/api/job/${id}/slice`)).json();
    if (s.state === "running") continue;
    job.slice = s; renderSlice(s); return;
  }
});
$("openBtn").addEventListener("click", async () => {
  if (!job) return;
  $("openBtn").disabled = true;
  try {
    const r = await (await fetch(`/api/job/${job.id}/open`, { method: "POST" })).json();
    toast(`Saved to ${r.saved.replace(/^\/Users\/[^/]+/, "~")}${CAT.slicer ? " — opening Bambu Studio" : ""}`);
  } finally { $("openBtn").disabled = false; }
});

// ── dialogs ────────────────────────────────────────────────────────────────────
function sheet(...kids) {
  $("sheetCard").replaceChildren(...kids); $("sheet").hidden = false;
  const first = $("sheetCard").querySelector("input, button"); first?.focus();
}
const closeSheet = () => { $("sheet").hidden = true; };
$("sheet").addEventListener("pointerdown", (e) => { if (e.target === $("sheet")) closeSheet(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("sheet").hidden) closeSheet(); });

// send to printer — always confirmed in-app
$("sendBtn").addEventListener("click", () => {
  if (!job) return;
  const s = job.stats;
  sheet(el("h3", {}, "Start this print?"),
    el("p", {}, `${job.title} goes to ${CAT.lan.name || "your P2S"} (${CAT.lan.ip}) and starts right away. ` +
      `${s.colours > 1 ? `It uses AMS slots 1–${s.colours} in the order shown under Colour. ` : "It uses AMS slot 1. "}Make sure the plate is clear.`),
    el("div", { class: "row" }, el("button", { class: "secondary", onclick: closeSheet }, "Cancel"),
      el("button", { class: "primary", onclick: async (e) => {
        e.target.disabled = true; e.target.textContent = "Slicing and sending…";
        const r = await fetch(`/api/job/${job.id}/send`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ confirm: true }) });
        const d = await r.json(); closeSheet();
        toast(r.ok ? `Sent “${d.sent}” to the printer` : `Couldn't send: ${d.error}`);
      } }, "Start print")));
});

// printer settings (typed by the user)
$("printerBtn").addEventListener("click", async () => {
  const cur = await (await fetch("/api/printer")).json();
  const f = (label, key, type, hint) => el("label", { class: "field" }, el("span", {}, label),
    el("input", { name: key, type, value: key === "access_code" ? "" : (cur[key] || ""), placeholder: hint, autocomplete: "off" }));
  const form = el("form", {}, f("Name", "name", "text", "Studio P2S"), f("IP address", "ip", "text", "192.168.1.40"),
    f("Serial number", "serial", "text", "From the printer: Settings › Device"),
    f("LAN access code", "access_code", "password", cur.configured ? "Saved — type to replace" : "From the printer: Settings › Network"),
    el("div", { class: "row" }, el("button", { class: "secondary", type: "button", onclick: closeSheet }, "Cancel"),
      el("button", { class: "primary", type: "submit" }, "Save")));
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const body = Object.fromEntries(new FormData(form));
    if (!body.access_code && cur.configured) delete body.access_code;
    const r = await (await fetch("/api/printer", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...cur, ...body }) })).json();
    CAT.lan = { configured: r.configured, name: r.name, ip: r.ip }; renderPrinter(); closeSheet();
    if (job) renderPrint(job);
    toast(r.configured ? "Printer saved on this Mac" : "Saved — fill in all fields to enable sending");
  });
  sheet(el("h3", {}, "Your printer"),
    el("p", {}, "To send prints straight to your P2S over your network. Everything stays on this Mac (~/.text2print). Sending is experimental and always asks first."),
    form);
});
function renderPrinter() {
  $("printerName").textContent = CAT.lan.configured ? (CAT.lan.name || "Bambu Lab P2S") : "Bambu Lab P2S";
  $("printerDot").classList.toggle("off", !CAT.lan.configured);
  $("printerBtn").title = CAT.lan.configured ? `Connected settings for ${CAT.lan.ip}` : "Set up sending to your printer";
}

// test plates
$("platesBtn").addEventListener("click", () => {
  const go = async (key, btn) => {
    btn.disabled = true; btn.textContent = "Building…";
    const r = await (await fetch("/api/plates", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ plate: key, nozzle: state.nozzle }) })).json();
    btn.disabled = false; btn.textContent = "Open";
    toast(`Saved ${r.saved.length} plate${r.saved.length > 1 ? "s" : ""} to ~/Downloads/text2print/test-plates`);
  };
  sheet(el("h3", {}, "Test plates"),
    el("p", {}, `A small coupon of every texture on the ${state.nozzle} mm nozzle, one family per plate. Print one, then record what you saw: python -m text2print verify <texture> ${state.nozzle} ok — the Printed badges come from that.`),
    ...CAT.plates.map((p) => { const b = el("button", { class: "secondary" }, "Open"); b.addEventListener("click", () => go(p.key, b));
      return el("div", { class: "plate" }, el("strong", {}, p.name), b, el("small", {}, p.coupons.join(" · "))); }),
    el("div", { class: "row" }, el("button", { class: "secondary", onclick: closeSheet }, "Close")));
});

// saved designs
$("saveBtn").addEventListener("click", () => {
  if (!job) return;
  const input = el("input", { name: "name", value: job.title, autocomplete: "off" });
  const form = el("form", {}, el("label", { class: "field" }, el("span", {}, "Name"), input),
    el("div", { class: "row" }, el("button", { class: "secondary", type: "button", onclick: closeSheet }, "Cancel"), el("button", { class: "primary", type: "submit" }, "Save")));
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    renderer.render(scene, camera);
    const thumb = squareThumb();
    await fetch("/api/designs", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: input.value || job.title, link: linkFor(), stats: { ...job.stats, slice: job.slice }, thumb }) });
    closeSheet(); toast("Saved");
  });
  sheet(el("h3", {}, "Save design"), form);
});
$("savedBtn").addEventListener("click", async () => {
  const list = await (await fetch("/api/designs")).json();
  const open = (d) => { location.search = d.link; };
  const grid = el("div", { class: "saved-grid" }, ...list.map((d) => {
    const del = el("button", { class: "del", title: "Delete", "aria-label": `Delete ${d.name}` }, "×");
    del.addEventListener("click", async (e) => { e.stopPropagation(); await fetch(`/api/designs/${d.id}`, { method: "DELETE" }); e.target.closest(".saved").remove(); });
    const sl = d.stats?.slice;
    const meta = sl && sl.state === "done" ? `${minutes(sl.minutes)} · ${fmt(sl.grams)} g` : d.stats ? `≈ ${fmt(d.stats.grams_est)} g` : "";
    return el("div", { class: "saved", role: "button", tabindex: 0, onclick: () => open(d), onkeydown: (e) => { if (e.key === "Enter") open(d); } },
      el("img", { src: `/api/designs/${d.id}/thumb`, alt: "" }), el("span", { class: "nm" }, d.name), el("span", { class: "meta" }, meta), del);
  }));
  sheet(el("h3", {}, "Saved designs"), list.length ? grid : el("div", { class: "empty" }, "Nothing saved yet — use Save design under the print buttons."),
    el("div", { class: "row" }, el("button", { class: "secondary", onclick: closeSheet }, "Close")));
});

function toast(msg) {
  const t = $("toast"); t.textContent = msg; t.hidden = false;
  clearTimeout(toast.t); toast.t = setTimeout(() => { t.hidden = true; }, 4200);
}

// ── viewer ─────────────────────────────────────────────────────────────────────
const canvas = $("view");
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.outputColorSpace = THREE.SRGBColorSpace;
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(35, 1, 1, 6000);
const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true; controls.dampingFactor = 0.08; controls.autoRotateSpeed = 1.2;
controls.maxPolarAngle = Math.PI * 0.495;
scene.add(new THREE.HemisphereLight(0xfffaf2, 0xd9cfbf, 1.35));
const key = new THREE.DirectionalLight(0xffffff, 2.0);
key.position.set(160, 260, 140); key.castShadow = true; key.shadow.mapSize.set(2048, 2048); key.shadow.bias = -0.0004;
Object.assign(key.shadow.camera, { left: -180, right: 180, top: 180, bottom: -180, near: 10, far: 900 });
scene.add(key);
const rim = new THREE.DirectionalLight(0xfff1e0, 0.6); rim.position.set(-200, 120, -160); scene.add(rim);
const BED = 256;
const plate = new THREE.Mesh(new THREE.PlaneGeometry(BED, BED), new THREE.MeshStandardMaterial({ color: 0xe4ddd1, roughness: 0.95 }));
plate.rotation.x = -Math.PI / 2; plate.position.y = -0.05; plate.receiveShadow = true; scene.add(plate);
const grid = new THREE.GridHelper(BED, 16, 0xcfc6b8, 0xd8d0c3); grid.position.y = 0.01; scene.add(grid);
const edge = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.PlaneGeometry(BED, BED)), new THREE.LineBasicMaterial({ color: 0xb9ae9e }));
edge.rotation.x = -Math.PI / 2; edge.position.y = 0.02; scene.add(edge);
let model = new THREE.Group(); scene.add(model);

function renderDropView(d) {
  const box = $("dropView"); box.hidden = !d.preview;
  if (!d.preview) return;
  const fur = state.texture === "fur";
  seg(box, [[true, fur ? "Trimmed" : "After droop", fur ? "Hairs cut free of the outer shell (preview)" : "Strands hung as gravity will hang them (preview)"],
    [false, "As printed", fur ? "Hairs bridged to the shell you cut away" : "The flat strands the printer lays"]],
    draped, async (v) => { draped = v; renderDropView(job); await showModel(job); });
}
async function showModel(d) {
  const list = (d.preview && draped ? d.preview : d.parts).concat(d.lid || []);
  const meshes = await Promise.all(list.map(async (p) => {
    const buf = await (await fetch(p.url)).arrayBuffer();
    const [nv, nf] = new Uint32Array(buf, 0, 2);
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(buf, 8, nv * 3), 3));
    g.setIndex(new THREE.BufferAttribute(new Uint32Array(buf, 8 + nv * 12, nf * 3), 1));
    g.rotateX(-Math.PI / 2); g.computeVertexNormals();
    const m = new THREE.Mesh(g, new THREE.MeshStandardMaterial({ color: new THREE.Color(p.colour), roughness: 0.82, metalness: 0 }));
    m.castShadow = true; m.receiveShadow = true; return m;
  }));
  const next = new THREE.Group(); meshes.forEach((m) => next.add(m));
  const box = new THREE.Box3().setFromObject(next), c = box.getCenter(new THREE.Vector3());
  next.position.set(-c.x, -box.min.y, -c.z);
  scene.remove(model); model.traverse((o) => { if (o.geometry) { o.geometry.dispose(); o.material.dispose(); } });
  model = next; scene.add(model);
  if (reframe) { frame(); reframe = false; }
}
function frame() {
  const box = new THREE.Box3().setFromObject(model), size = box.getSize(new THREE.Vector3());
  const r = Math.max(size.length() * 0.5, 40);
  const vfov = THREE.MathUtils.degToRad(camera.fov), hfov = 2 * Math.atan(Math.tan(vfov / 2) * camera.aspect);
  const dist = r / Math.sin(Math.min(vfov, hfov) / 2) * 0.96;
  const target = new THREE.Vector3(0, size.y * 0.42, 0);
  camera.position.copy(target).add(new THREE.Vector3(0.62, 0.52, 0.86).normalize().multiplyScalar(dist));
  controls.target.copy(target); controls.update();
}
function squareThumb() {
  const s = Math.min(canvas.width, canvas.height), c = document.createElement("canvas"); c.width = c.height = 360;
  c.getContext("2d").drawImage(canvas, (canvas.width - s) / 2, (canvas.height - s) / 2, s, s, 0, 0, 360, 360);
  return c.toDataURL("image/png");
}
$("resetBtn").addEventListener("click", frame);
$("spinBtn").addEventListener("click", (e) => {
  controls.autoRotate = !controls.autoRotate; e.currentTarget.setAttribute("aria-pressed", String(controls.autoRotate));
});
function resize() {
  const w = canvas.clientWidth, h = canvas.clientHeight;
  if (canvas.width !== Math.round(w * renderer.getPixelRatio()) || canvas.height !== Math.round(h * renderer.getPixelRatio())) {
    renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix();
  }
}
renderer.setAnimationLoop(() => { resize(); controls.update(); renderer.render(scene, camera); });

// ── boot ───────────────────────────────────────────────────────────────────────
(async () => {
  CAT = await (await fetch("/api/catalogue")).json();
  state.shape = CAT.defaults.shape; state.texture = CAT.defaults.texture; state.nozzle = CAT.defaults.nozzle;
  state.colours = [...CAT.colours];
  readUrl();
  if (!state.bands) { state.mixPreset = CAT.mix.default; state.bands = structuredClone(CAT.mix.presets.find((p) => p.key === CAT.mix.default).bands); }
  if (!fits(shapeOf(state.shape), textureOf(state.texture))) state.texture = CAT.textures.find((t) => fits(shapeOf(state.shape), t)).key;
  state.family = textureOf(state.texture).family;
  renderPrinter(); renderNozzles(); renderAll(); changed(true);
})();
