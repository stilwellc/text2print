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
const FAMILY_NAMES = { lattice: "Woven", fabric: "Fabric", droop: "Droop", halftone: "Halftone", colourwork: "Colourwork", spiral: "Vase mode",
  shell: "Shell", flat: "Flat", mix: "Mix" };
// options that only apply to some textures
const ONLY = { course_group: ["grid", "twill", "kagome", "polar", "ripple", "selvedge", "beat"], folds: ["pleats", "flutes", "twist", "lowpoly", "ribs"], turn: ["twist", "lowpoly"], cell: ["voronoi"],
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
function pieceSlotCount() {
  if (!isMix() && zonesOn()) return Math.max(1, parseInt(state.options.zones || "1", 10));
  if (isChart()) return Math.max(1, ...chartBands().flatMap((b) => "plain" in b ? [b.plain + 1] : "stripes" in b ? b.stripes.map((x) => x + 1)
    : (b.colours || [0, 1, 2]).slice(0, (b.art || ((CAT.colourwork.motifs.find((m) => m.key === (b.motif || b.chart)) || {}).art || []).join("").includes("o") || (b.tones || 2) >= 3) ? 3 : 2).map((x) => x + 1)));
  if (!isMix()) return Math.max(textureOf(state.texture).slots, ...ombreStops().map((i) => i + 1));
  return Math.max(1, ...state.bands.flatMap((b) => twoSlot(b.texture) ? [b.slot + 1, (b.slot2 ?? 1) + 1] : [b.slot + 1]));
}
const WEAVE_KEYS = ["weave_twist", "weave_ombre", "weave_picture", "weave_picture_on", "weave_picture_courses"];
function ombreStops() {
  const o = state.options.weave_ombre;
  return o && textureOf(state.texture).family === "lattice" ? String(o).split(",").map((x) => parseInt(x, 10)).filter((x) => x >= 0) : [];
}
function slotCount() {                     // the piece's slots, plus any the lid's own colours use
  return Math.max(pieceSlotCount(), ...(typeof lidSlots === "function" ? lidSlots().map((i) => i + 1) : []));
}

// ── url state ──────────────────────────────────────────────────────────────────
function readUrl() {
  const q = new URLSearchParams(location.search);
  if (q.get("shape") && shapeOf(q.get("shape"))) state.shape = q.get("shape");
  if (q.get("texture") && textureOf(q.get("texture"))) state.texture = q.get("texture");
  if (q.get("nozzle")) state.nozzle = parseFloat(q.get("nozzle"));
  if (q.get("c")) state.colours = q.get("c").split(",").map((h) => "#" + h.replace("#", ""));
  const optKeys = Object.values(CAT.options).flat().map((o) => o.key).concat(["picture", "image"]).concat(TEXT_KEYS).concat(WEAVE_KEYS).concat(["lid", "lid_colour", "lid_fit", "lid_texture", "lid_height", "lid_knob", "lid_slot", "lid_slot2", "lid_plate", "lid_over_w", "lid_over_d", "tower", "engrave_base", "engrave_lid", "engrave_font"]);
  const toggleKeys = Object.values(CAT.options).flat().filter((o) => o.kind === "toggle").map((o) => o.key).concat(["text_invert", "picture_invert"]);
  for (const [k, v] of q) {
    if (k === "mix") { try { state.bands = JSON.parse(v); } catch (e) { /* a bad link keeps the default */ } }
    else if (k === "chart") { try { state.options.chart = JSON.parse(v); } catch (e) { /* a bad link keeps the preset */ } }
    else if (optKeys.includes(k) || k.startsWith("pp_")) state.options[k] = toggleKeys.includes(k) ? v === "1" : v;
    else if (!["shape", "texture", "nozzle", "c"].includes(k)) state.params[k] = parseFloat(v);
  }
}
function linkFor() {
  const q = new URLSearchParams({ shape: state.shape, texture: state.texture, nozzle: state.nozzle });
  for (const p of shapeOf(state.shape).params) if (state.params[p.key] !== undefined && state.params[p.key] !== p.default) q.set(p.key, state.params[p.key]);
  q.set("c", state.colours.slice(0, slotCount()).map((h) => h.replace("#", "")).join(","));
  if (isMix()) q.set("mix", JSON.stringify(state.bands));
  if (isChart() && Array.isArray(state.options.chart)) q.set("chart", JSON.stringify(state.options.chart));
  for (const o of familyOptions()) {
    const v = state.options[o.key] ?? o.default;
    if (v !== o.default) q.set(o.key, v === true ? "1" : v === false ? "0" : v);
  }
  if (state.options.image && textureOf(state.texture).family === "halftone") q.set("image", state.options.image);
  if (IMAGE_TEXTURES.includes(state.texture) || isMix() || isChart() || ["in", "out"].includes(state.options.mask))
    for (const k of TEXT_KEYS) if (state.options[k] !== undefined && state.options[k] !== "") q.set(k, state.options[k] === true ? "1" : state.options[k] === false ? "0" : state.options[k]);
  if (state.options.lid && state.options.lid !== "none" && shapeOf(state.shape).lid) {
    for (const k of ["lid", "lid_colour", "lid_fit", "lid_texture", "lid_height", "lid_knob", "lid_slot", "lid_slot2", "lid_plate", "lid_over_w", "lid_over_d", "tower", "engrave_base", "engrave_lid", "engrave_font"]) if (state.options[k] !== undefined && state.options[k] !== "") q.set(k, state.options[k]);
  }
  if (state.options.image && IMAGE_TEXTURES.includes(state.texture)) q.set("image", state.options.image);
  for (const k of ["engrave_base", "engrave_font"]) if (state.options[k]) q.set(k, state.options[k]);
  for (const [k, v] of Object.entries(state.options)) if (k.startsWith("pp_")) q.set(k, v);
  if (textureOf(state.texture).family === "lattice") {
    for (const k of WEAVE_KEYS) if (state.options[k] !== undefined && state.options[k] !== "") q.set(k, state.options[k]);
    if (state.options.weave_picture) for (const k of TEXT_KEYS) if (state.options[k] !== undefined && state.options[k] !== "") q.set(k, state.options[k] === true ? "1" : state.options[k] === false ? "0" : state.options[k]);
  }
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
// what a texture costs in colour changes, before you pick it (two colours loaded)
function costNote(t) {
  if (t.slots < 2 && t.family !== "mix") return el("span", { class: "c0" }, "1 colour");
  const g = parseInt(state.options.course_group || "1", 10);
  return el("span", { class: t.swaps === "layer" ? "c2" : "c1" },
    { none: "no changes", course: g > 1 ? `change / ${g} courses` : "change / course", layer: "change / layer", band: "change / band" }[t.swaps] || "");
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
  // each card shows the shape in the picked family when we have that render (a knit basket under Fabric)
  const fam = state.family || textureOf(state.texture)?.family;
  $("shapes").replaceChildren(...CAT.shapes.map((s) => card({ ...s, thumb: s.thumbs?.[fam] || s.thumb },
    s.key === state.shape, () => pickShape(s.key))));
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
    el("div", { class: "cards" }, ...list.map((t) => card(t, t.key === state.texture, () => { state.texture = t.key; renderAll(); changed(); },
      el("span", { class: "cost" }, badge(t) || "", costNote(t))))),
    el("p", { class: "desc" }, textureOf(state.texture).family === state.family ? textureOf(state.texture).blurb : "Pick one to switch."));
}

// sizes + the drawn profile for "Your shape"
function renderSizes() {
  const sh = shapeOf(state.shape), fam = textureOf(state.texture).family;
  const curveKeys = ["c0", "c1", "c2", "c3", "c4"];
  const custom = sh.key === "custom";
  $("curve").hidden = !custom;
  if (custom) renderCurve(sh);
  $("sizes").replaceChildren(...sh.params.filter((p) => (!p.family || (p.family.startsWith("!") ? p.family.slice(1) !== fam : p.family === fam)) && !(custom && curveKeys.includes(p.key))).map((p) => {
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
  const all = slotCount(), n = pieceSlotCount(), lidUse = lidSlots();
  $("colours").replaceChildren(...Array.from({ length: all }, (_, i) => el("button", {
    class: "swatch-btn", onclick: (e) => openPalette(i, e.currentTarget),
  }, el("span", { class: "chip", style: `background:${state.colours[i]}` }), el("span", { class: "name" }, nameOfColour(state.colours[i])),
     el("span", { class: "slot" }, `AMS ${i + 1}${i >= n && lidUse.includes(i) ? " · lid" : ""}`))));
  const tw = $("towerToggle");
  tw.hidden = all < 2;
  if (!tw.hidden) {
    const cb = el("input", { type: "checkbox" }); cb.checked = state.options.tower !== "off";
    cb.addEventListener("change", () => { if (cb.checked) delete state.options.tower; else state.options.tower = "off"; changed(); });
    tw.replaceChildren(el("label", { class: "toggle" }, cb, el("span", {}, "Prime tower")),
      el("p", { class: "hint" }, "Off saves the tower's filament and time; the purge still goes out the chute."));
  }
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
    : parseInt(state.options.course_group || "1", 10) > 1
      ? `Colour changes every ${state.options.course_group} courses: woven bands instead of colour by direction, with 1/${state.options.course_group} of the AMS changes.`
    : "Colour follows rod direction: one AMS change per course. More courses per colour (Finish) cuts the changes. Pick the same colour twice for a one-colour print.";
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
  const masked = fam === "fabric" && ["in", "out"].includes(state.options.mask);
  const shown = familyOptions().filter((o) => {
    if (fam === "fabric" && o.key === "picture") return masked;               // picture only drives a mask here
    if (fam === "colourwork" && o.key === "chart_preset") return false;       // lives in the Chart section
    if (fam === "colourwork" && o.key === "picture") return chartBands().some((b) => "picture" in b && !b.picture);
    if (ONLY[o.key] && !ONLY[o.key].includes(state.texture)) return false;
    if (["course_group", "colour_by"].includes(o.key) && ombreStops().length >= 2) return false;   // the ombré sets colour
    if (o.key === "course_group") return state.options.colour_by !== "height" && slotCount() > 1;
    if (o.key === "zones") return zonesOn();
    if (o.key === "zone_style") return zonesOn() && parseInt(state.options.zones || "1", 10) > 1;
    if (o.key === "course_rows") return zonesOn() && parseInt(state.options.zones || "1", 10) > 1
      && (state.options.zone_style ?? "courses") === "courses" && state.texture !== "fur";
    return true;
  });
  const kids = shown.flatMap((o) => o.key === "picture" ? pictureControl(o, after) : optionControl(o, after));
  kids.unshift(...pluginSliders(textureOf(state.texture).params));            // a plugin texture's own sliders
  if (IMAGE_TEXTURES.includes(state.texture) || masked) kids.splice(Math.min(2, kids.length), 0, uploader(state.options.image, (id) => { if (id) state.options.image = id; else delete state.options.image; renderFinish(); changed(); }));
  if (!["lattice", "flat"].includes(fam)) kids.push(...engraveControl("engrave_base", "Words under the base", after));
  if (fam === "lattice") kids.push(...weaveModifiers(after));
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
    if (idx > 0) {                                     // how this band meets the band below it
      const blendable = (k) => M.blendable.includes(k);
      if (blendable(b.texture) && blendable(state.bands[idx - 1].texture)) {
        const bs = el("select", { "aria-label": "Blend into the band below", class: "blend" }, ...M.blends.map(([k, lab]) => {
          const o = el("option", { value: k }, `${lab}${k === "hard" ? "" : " into the band below"}`);
          o.selected = ((b.blend || {}).style || "hard") === k; return o; }));
        bs.addEventListener("change", () => { b.blend = bs.value === "hard" ? undefined : { style: bs.value, size: (b.blend || {}).size || 16 }; edit(); });
        kids.push(el("div", { class: "sub" }, bs));
      }
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

// colourwork chart: bands of motifs / pictures / plain / stripes (options.chart; a preset until edited)
const isChart = () => textureOf(state.texture).family === "colourwork";
function chartBands() {
  if (Array.isArray(state.options.chart)) return state.options.chart;
  const C = CAT.colourwork, key = state.options.chart_preset || C.default;
  return (C.presets.find((p) => p.key === key) || C.presets[0]).bands;
}
function renderChart() {
  $("chartSec").hidden = !isChart();
  if (!isChart()) return;
  const C = CAT.colourwork;
  const edit = () => { renderChart(); renderColours(); renderFinish(); changed(); };
  const mine = () => { if (!Array.isArray(state.options.chart)) state.options.chart = structuredClone(chartBands()); return state.options.chart; };
  const presets = el("div", { class: "seg small", role: "radiogroup", "aria-label": "Chart presets" });
  seg(presets, C.presets.map((p) => [p.key, p.name]), Array.isArray(state.options.chart) ? null : (state.options.chart_preset || C.default),
    (k) => { delete state.options.chart; state.options.chart_preset = k; edit(); });
  const bands = chartBands();
  const chip = (get, set) => {
    const i = get() ?? 0;
    return el("button", { class: "chip-btn", style: `background:${state.colours[i]}`, title: `AMS ${i + 1} — click to change`, "aria-label": `Colour AMS ${i + 1}`,
      onclick: () => { set((i + 1) % MAX_SLOTS); edit(); } }, el("span", {}, String(i + 1)));
  };
  const kindOf = (b) => "plain" in b ? "plain" : "stripes" in b ? "stripes" : "picture" in b ? "picture" : b.art ? "art" : `m:${b.motif || b.chart}`;
  const accent = (b) => {
    const m = C.motifs.find((x) => x.key === (b.motif || b.chart));
    const art = b.art || (m && m.art);
    return art ? art.join("").includes("o") : (b.tones || 2) >= 3;
  };
  const rows = bands.map((b, idx) => {
    const groups = { Motifs: [], "Your charts": [] };
    for (const m of C.motifs) groups[m.group].push([`m:${m.key}`, m.name]);
    const opts = [["Motifs", groups.Motifs], ["Your charts", groups["Your charts"]],
      ["Other", [...(b.art ? [["art", "Pixel art (Claude)"]] : []), ["picture", "Picture"], ["plain", "Plain"], ["stripes", "Stripes"]]]];
    const sel = el("select", { "aria-label": "Band" }, ...opts.filter(([, xs]) => xs.length).map(([g, xs]) =>
      el("optgroup", { label: g }, ...xs.map(([v, n]) => { const o = el("option", { value: v }, n); o.selected = v === kindOf(b); return o; }))));
    sel.addEventListener("change", () => {
      const B = mine(), cols = B[idx].colours || [0, 1, 2], v = sel.value;
      B[idx] = v === "plain" ? { plain: cols[0], mm: 6 } : v === "stripes" ? { stripes: [cols[0], cols[1] ?? 1], mm: 8, layers: 2 }
        : v === "picture" ? { picture: null, fill: true, colours: cols.slice(0, 2) } : { motif: v.slice(2), colours: cols };
      edit();
    });
    const k = kindOf(b), chips = [];
    if (k === "plain") chips.push(chip(() => b.plain, (x) => { mine()[idx].plain = x; }));
    else if (k === "stripes") (b.stripes || [0, 1]).forEach((s_, j) => chips.push(chip(() => s_, (x) => { mine()[idx].stripes[j] = x; })));
    else (b.colours || [0, 1, 2]).slice(0, accent(b) ? 3 : 2).forEach((s_, j) =>
      chips.push(chip(() => s_, (x) => { const B = mine(); B[idx].colours = [...(B[idx].colours || [0, 1, 2])]; B[idx].colours[j] = x; })));
    const kids = [sel, el("div", { class: "chips" }, ...chips),
      el("button", { class: "x", title: "Remove band", "aria-label": "Remove band", disabled: bands.length < 2, onclick: () => { mine().splice(idx, 1); edit(); } }, "×")];
    if (k === "plain" || k === "stripes" || (k === "picture" && !b.fill)) {
      const mm = parseFloat(b.mm || (k === "picture" ? 40 : 6));
      const out = el("output", {}, `${mm} mm`);
      const r = el("input", { type: "range", min: 2, max: k === "picture" ? 200 : 60, step: 1, value: mm, "aria-label": "Band height" });
      r.addEventListener("input", () => { out.textContent = `${r.value} mm`; });
      r.addEventListener("change", () => { mine()[idx].mm = +r.value; edit(); });
      kids.push(el("div", { class: "share" }, r, out));
    }
    if (k === "picture") {
      const f = el("div", { class: "seg small sub" });
      seg(f, [["fill", "Fill the rest"], ["mm", "Fixed height"], ["3", "3 tones"]].map(([v, l]) => [v, l]),
        b.fill ? "fill" : "mm", (v) => { const B = mine()[idx]; if (v === "3") B.tones = (B.tones || 2) >= 3 ? 2 : 3; else if (v === "fill") B.fill = true; else { delete B.fill; B.mm = B.mm || 40; } edit(); });
      kids.push(f);
    } else if (k !== "plain" && k !== "stripes") {
      const f = el("div", { class: "seg small sub" });
      seg(f, [["1", "×1"], ["2", "×2"], ["3", "×3"]], String(b.repeat || 1), (v) => { mine()[idx].repeat = +v; edit(); });
      kids.push(f);
    }
    return el("div", { class: "band" }, ...kids);
  });
  $("chartBands").replaceChildren(presets, ...rows.reverse());
  $("addChartBand").disabled = bands.length >= 12;
}
$("addChartBand").addEventListener("click", () => {
  const B = Array.isArray(state.options.chart) ? state.options.chart : (state.options.chart = structuredClone(chartBands()));
  B.push({ motif: "zigzag", colours: [0, 1] }); renderChart(); renderColours(); changed();
});

let askDrawn = false;
function renderAll() { if (!askDrawn) { askDrawn = true; renderAsk(); } renderShapes(); renderTextures(); renderBands(); renderChart(); renderSizes(); renderColours(); renderFinish(); renderLid(); }

function buildOptions() {
  const lidKeys = ["lid", "lid_colour", "lid_fit", "lid_texture", "lid_height", "lid_knob", "lid_plate", "tower", "engrave_base", "engrave_lid", "engrave_font"];
  const o = isMix() ? { bands: state.bands, purge: state.options.purge } : { ...state.options };
  for (const k of lidKeys) if (state.options[k] !== undefined) o[k] = state.options[k];
  const ls = lidSlots();
  if (ls.length) o.lid_colours = ls.map((i) => state.colours[i]);
  delete o.lid_slot; delete o.lid_slot2;
  return o;
}

// ── ask Claude: a pattern in words -> a plugin written, checked and selected ─────────────────────────────
let askJob = null;
function currentDesign() {
  const o = buildOptions();
  if (isMix()) o.bands = state.bands;
  return { shape: state.shape, texture: state.texture, params: state.params, nozzle: state.nozzle,
           colours: state.colours.slice(0, slotCount()), options: o };
}
function applyDesign(d) {
  if (d.shape && shapeOf(d.shape)) state.shape = d.shape;
  if (d.texture && textureOf(d.texture)) state.texture = d.texture;
  state.params = { ...(d.params || {}) };
  if (d.nozzle) state.nozzle = parseFloat(d.nozzle);
  if (Array.isArray(d.colours) && d.colours.length) {
    d.colours.forEach((c, i) => { state.colours[i] = c; });
  }
  const o = { ...(d.options || {}) };
  if (o.bands) { state.bands = o.bands; delete o.bands; state.mixPreset = null; }
  if (Array.isArray(o.lid_colours)) {                 // lid colours come back as hex: give them AMS slots
    o.lid_colours.forEach((c, i) => {
      let k = state.colours.indexOf(c);
      if (k < 0) { k = Math.min(MAX_SLOTS - 1, slotCount() + i); state.colours[k] = c; }
      o[i ? "lid_slot2" : "lid_slot"] = String(k);
    });
    delete o.lid_colours;
  }
  state.options = o; state.family = textureOf(state.texture).family;
}
let thread = null;
function renderAsk() {
  const box = $("ask");
  const turns = el("div", { class: "turns" });
  const inp = el("textarea", { class: "words", rows: "3", placeholder: "Describe what you want — “a vase that starts as a blue zigzag and drips into cream knit, our name under it”, “three ideas for a planter”, “a matching cup, coaster and tray in autumn colours”, “make something like this photo”…", "aria-label": "Describe a design" });
  const go = el("button", { class: "primary" }, "Design it");
  const ideas = el("label", { class: "toggle" }, el("input", { type: "checkbox" }), el("span", {}, "3 ideas"));
  const lim = (k, ph) => el("input", { type: "number", min: "0", placeholder: ph, class: "lim", "data-k": k, "aria-label": ph });
  const limits = el("details", { class: "limits" }, el("summary", {}, "Limits"),
    el("div", { class: "limrow" }, lim("hours", "max hours"), lim("changes", "max colour changes"), lim("grams", "max grams")));
  const msg = el("p", { class: "hint" }, "Claude composes the whole design — blends, colours, pictures, new patterns and shapes — checks it, and loads it here. Follow up to refine it.");
  const steps = el("ol", { class: "steps" });
  const live = el("img", { class: "live", alt: "Claude's latest preview", hidden: true });
  const cards = el("div", { class: "variants" });
  const after = el("div", { class: "after", hidden: true });
  let photoId = null;
  const photo = uploader(null, (id) => { photoId = id; });
  const budget = () => Object.fromEntries([...limits.querySelectorAll("input")].filter((i) => i.value).map((i) => [i.dataset.k, +i.value]));
  const send = async (mode = "design") => {
    const words = inp.value.trim(); if ((!words && mode !== "review") || askJob) return;
    go.disabled = true; cards.replaceChildren(); after.hidden = true; steps.replaceChildren(); live.hidden = true;
    msg.textContent = mode === "review" ? "Claude is comparing your print with the design…" : "Claude is designing…";
    const body = { request: words, current: currentDesign(), thread, mode, budget: budget(),
                   variations: ideas.querySelector("input").checked ? 3 : 0 };
    if (photoId) body.photo = photoId;
    const r = await fetch("/api/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const d = await r.json();
    if (!r.ok) { msg.textContent = d.error; go.disabled = false; return; }
    thread = d.id; askJob = d.id; inp.value = ""; poll();
  };
  const drawTurns = (ts) => turns.replaceChildren(...(ts || []).map((t) => el("div", { class: `turn ${t.role}` }, t.text)));
  const poll = async () => {
    const d = await (await fetch(`/api/ask/${askJob}`)).json();
    drawTurns(d.turns);
    steps.replaceChildren(...(d.steps || []).map((s) => el("li", {}, s.text)));
    if (d.preview) { live.src = `/api/ask/${askJob}/file/${d.preview}?${d.seconds}`; live.hidden = false; }
    if (d.state === "running") { msg.textContent = `Claude is working… ${d.seconds}s`; return setTimeout(poll, 2500); }
    const tid = askJob; askJob = null; go.disabled = false;
    if (d.state === "error") { msg.textContent = d.error; return; }
    CAT = await (await fetch("/api/catalogue")).json();             // new plugins / pictures / shapes
    const ds = d.result.designs || [];
    msg.textContent = d.result.summary || "Done.";
    live.hidden = true; steps.replaceChildren();
    const load = (x) => { applyDesign(x.design || {}); renderAll(); changed(true); };
    if (ds.length) load(ds[0]);
    if (ds.length > 1) cards.replaceChildren(...ds.map((x, i) => el("button", { class: "variant" + (i === 0 ? " on" : ""),
      onclick: (e) => { cards.querySelectorAll(".variant").forEach((c) => c.classList.remove("on")); e.currentTarget.classList.add("on"); load(x); } },
      x.preview ? el("img", { src: `/api/ask/${tid}/file/${x.preview}`, alt: "" }) : "", el("b", {}, x.label || `Option ${i + 1}`),
      el("span", {}, x.summary || ""))));
    after.hidden = false;
  };
  const noteIn = el("input", { type: "text", class: "lim", placeholder: "What's off? (optional — Claude remembers)", hidden: true });
  const vote = async (verdict) => {
    if (verdict === "dislike" && noteIn.hidden) { noteIn.hidden = false; noteIn.focus(); return; }
    const note = verdict === "dislike" ? noteIn.value.trim() : ""; noteIn.hidden = true; noteIn.value = "";
    await fetch("/api/taste", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ verdict, design: currentDesign(), note }) });
    toast(verdict === "like" ? "Noted — Claude will lean this way" : "Noted — Claude will steer away");
  };
  after.replaceChildren(
    el("button", { class: "ghost small", onclick: () => vote("like") }, "More like this"),
    el("button", { class: "ghost small", onclick: () => vote("dislike") }, "Not this"), noteIn,
    el("button", { class: "ghost small", onclick: () => { thread = null; turns.replaceChildren(); cards.replaceChildren(); after.hidden = true; msg.textContent = "New design — describe it."; } }, "Start over"));
  const review = el("button", { class: "ghost small", title: "Photograph a finished print: Claude compares it with the design, records what it learned and proposes fixes",
    onclick: () => { if (!photoId) { toast("Add a photo of the print first"); return; } send("review"); } }, "Review a print");
  noteIn.addEventListener("keydown", (e) => { if (e.key === "Enter") vote("dislike"); });
  inp.addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) send(); });
  go.addEventListener("click", () => send());
  box.replaceChildren(turns, inp, el("div", { class: "askrow" }, ideas, el("span", { class: "grow" }), go),
    el("div", { class: "askrow" }, photo, review), limits, msg, steps, live, cards, after);
}

// ── pictures: built-ins, text in any font, and library pictures (uploads and ones written from a prompt) ──
const TEXT_KEYS = ["text", "font", "text_layout", "text_invert", "picture_place", "picture_size", "picture_lift", "picture_contrast", "picture_invert"];
// twist / ombré / image in the weave: Claude sets them from a description; the person tunes or removes them here
function weaveModifiers(after) {
  const o = state.options, kids = [];
  const drop = (keys) => el("button", { class: "ghost small", type: "button", onclick: () => { for (const k of keys) delete o[k]; after(); } }, "remove");
  const head = (label, keys) => el("div", { class: "field-label" }, label, " ", el("span", { style: "opacity:.6;font-weight:400" }, "· set by Claude "), drop(keys));
  if (parseFloat(o.weave_twist || "0")) {
    kids.push(head("Twist", ["weave_twist"]));
    kids.push(...rangeCtl("weave_twist", "Degrees per course", -12, 12, 0.5, 0, (v) => `${v > 0 ? "+" : ""}${v}° a course`).slice(1));
  }
  if (ombreStops().length >= 2) {
    kids.push(head("Ombré", ["weave_ombre"]));
    kids.push(el("div", { class: "ombre" }, ...ombreStops().map((i, k, all) => {
      const b = el("button", { class: "chip-btn", style: `background:${state.colours[i]}`, title: `${k ? k === all.length - 1 ? "top" : "middle" : "bottom"}: AMS ${i + 1}, click to change`, "aria-label": `Ombré stop ${k + 1}` },
        el("span", {}, String(i + 1)));
      b.onclick = () => { const s = ombreStops(); s[k] = (s[k] + 1) % MAX_SLOTS; o.weave_ombre = s.join(","); after(); };
      return b;
    })));
  }
  if (o.weave_picture) {
    const pic = (CAT.pictures.choices.find((c) => c.key === o.weave_picture) || {}).name || o.weave_picture;
    kids.push(head(`Image in the weave: ${o.weave_picture === "text" ? `“${o.text || ""}”` : pic}`, ["weave_picture", "weave_picture_on", "weave_picture_courses"]));
    const on = el("div", { class: "seg small", role: "radiogroup", "aria-label": "Where the image shows" });
    seg(on, [["", "Auto"], ["top", "Top"], ["wall", "Wall"]], o.weave_picture_on || "", (v) => { if (v) o.weave_picture_on = v; else delete o.weave_picture_on; after(); });
    kids.push(on);
    if ((o.weave_picture_on || "") !== "wall") kids.push(...rangeCtl("weave_picture_courses", "Courses that carry it (top view)", 1, 8, 1, 3, (v) => `${v}`));
    kids.push(...rangeCtl("picture_contrast", "Contrast", 0.3, 3, 0.1, 1, (v) => v.toFixed(1)));
  }
  return kids;
}
function rangeCtl(key, label, min, max, step, def, show) {
  const v = state.options[key] !== undefined ? parseFloat(state.options[key]) : def;
  const out = el("output", {}, show(v));
  const r = el("input", { type: "range", min: String(min), max: String(max), step: String(step), value: String(v), "aria-label": label });
  r.addEventListener("input", () => { out.textContent = show(parseFloat(r.value)); state.options[key] = r.value; changed(false, true); });
  r.addEventListener("change", () => { state.options[key] = r.value; changed(); });
  return [el("div", { class: "field-label" }, label), el("div", { class: "height" }, r, out)];
}
let textTimer = null;
function pictureControl(o, after) {
  const P = CAT.pictures, val = state.options.picture ?? o.default, groups = {};
  for (const c of P.choices) (groups[c.group] ||= []).push(c);
  const sel = el("select", { "aria-label": "Picture", class: "pic" }, ...Object.entries(groups).map(([g, cs]) =>
    el("optgroup", { label: g }, ...cs.map((c) => { const op = el("option", { value: c.key }, c.name); op.selected = c.key === val; return op; }))));
  sel.addEventListener("change", () => { state.options.picture = sel.value; after(); });
  const kids = [el("div", { class: "field-label" }, "Picture"), sel];
  const picMeta = P.choices.find((c) => c.key === val);
  kids.push(...pluginSliders(picMeta && picMeta.params));                      // a drawn picture's sliders
  if (val === "text") {
    const inp = el("input", { type: "text", class: "words", placeholder: "Your words", value: state.options.text || "", "aria-label": "Words" });
    inp.addEventListener("input", () => { clearTimeout(textTimer); textTimer = setTimeout(() => { state.options.text = inp.value; changed(); }, 350); });
    const font = el("select", { "aria-label": "Font", class: "font" }, ...P.fonts.map(([k, lab]) => {
      const op = el("option", { value: k }, lab); op.selected = (state.options.font || "futura") === k; return op; }));
    font.addEventListener("change", () => { state.options.font = font.value; changed(); });
    kids.push(el("div", { class: "field-label" }, "Words"), inp, el("div", { class: "field-label" }, "Font"), font,
      ...optionControl({ key: "text_layout", label: "Layout", kind: "seg", choices: P.layouts, default: "center" }, after));
  }
  if ((IMAGE_TEXTURES.includes(state.texture) && !["flatlitho", "cmyk"].includes(state.texture)) ||
      (textureOf(state.texture).family === "fabric" && ["in", "out"].includes(state.options.mask))) {   // walls only
    kids.push(...optionControl({ key: "picture_place", label: "Placement", kind: "seg",
      choices: [["wrap", "Wrap around"], ["front", "Front"]], default: "wrap" }, after));
    kids.push(...rangeCtl("picture_size", "Size", 0.15, 1, 0.05, 1, (x) => `${Math.round(x * 100)} % of the height`));
    const sz = state.options.picture_size !== undefined ? parseFloat(state.options.picture_size) : 1;
    if (sz < 0.999) kids.push(...rangeCtl("picture_lift", "Position", 0, 1, 0.05, 0.5, (x) => x < 0.2 ? "Low" : x > 0.8 ? "High" : "Middle"));
  }
  kids.push(...rangeCtl("picture_contrast", "Contrast", 0.3, 3, 0.1, 1, (x) => `${x.toFixed(1)}×`));
  kids.push(...optionControl({ key: "picture_invert", label: "Invert", kind: "toggle", default: false }, after));
  if (Object.keys(P.errors || {}).length)
    kids.push(el("p", { class: "hint" }, `A plugin didn't load: ${Object.keys(P.errors).join(", ")} — run "python -m text2print plugin list".`));
  return kids;
}

function engraveControl(key, label, after) {
  const inp = el("input", { type: "text", class: "words", placeholder: "Optional", value: state.options[key] || "", "aria-label": label });
  inp.addEventListener("input", () => { clearTimeout(textTimer); textTimer = setTimeout(() => { if (inp.value) state.options[key] = inp.value; else delete state.options[key]; changed(); }, 400); });
  const out = [el("div", { class: "field-label" }, label), inp];
  if (state.options.engrave_base || state.options.engrave_lid) {
    const font = el("select", { "aria-label": "Engraving font", class: "font" }, ...CAT.pictures.fonts.map(([k, lab]) => {
      const op = el("option", { value: k }, lab); op.selected = (state.options.engrave_font || "futura") === k; return op; }));
    font.addEventListener("change", () => { state.options.engrave_font = font.value; changed(); });
    if (key === "engrave_base") out.push(el("div", { class: "field-label" }, "Engraving font"), font);
  }
  return out;
}

// sliders a plugin declares (PARAMS): tune what Claude wrote without asking Claude again
function pluginSliders(params) {
  const out = [];
  for (const [k, spec] of Object.entries(params || {})) {
    const step = spec.step ?? ((spec.hi - spec.lo) > 20 ? 1 : 0.05);
    out.push(...rangeCtl(`pp_${k}`, spec.label || k, spec.lo, spec.hi, step, spec.default,
      (x) => (Number.isInteger(step) ? String(Math.round(x)) : x.toFixed(2)) + (spec.unit ? ` ${spec.unit}` : "")));
  }
  return out;
}

// ── lid: its own section — closure, look, fit, height, colours, knob ─────────────────────────────
const lidOn = () => shapeOf(state.shape).lid && textureOf(state.texture).family !== "flat" && state.options.lid && state.options.lid !== "none";
const lidTwoSlot = () => {
  const k = state.options.lid_texture || "match";
  if (k === "match") return false;
  const t = CAT.textures.find((x) => x.key === k);
  return !!t && t.slots > 1;
};
function lidSlots() {
  if (!lidOn() || (state.options.lid_texture || "match") === "match") return [];
  const num = (x, d) => { const n = parseInt(x, 10); return Number.isFinite(n) ? Math.min(MAX_SLOTS - 1, Math.max(0, n)) : d; };
  const a = num(state.options.lid_slot, 0), b = num(state.options.lid_slot2, 1);
  return lidTwoSlot() ? [a, b] : [a];
}
function renderLid() {
  const sh = shapeOf(state.shape), sec = $("lidSec");
  sec.hidden = !sh.lid || textureOf(state.texture).family === "flat";
  if (sec.hidden) return;
  const after = () => { renderLid(); renderColours(); changed(); };
  const kids = [...optionControl({ key: "lid", label: "Lid", kind: "seg",
    choices: sh.round ? [["none", "None"], ["slip", "Slip-on"], ["thread", "Screw"], ["magnets", "Magnets"]]
      : state.shape === "box" && textureOf(state.texture).family === "lattice" ? [["none", "None"], ["slip", "Slip-on"], ["gift", "Gift box"]]
      : [["none", "None"], ["slip", "Slip-on"]],
    default: "none" }, after)];
  // gift box: a flush woven cap over a smooth neck — it matches the piece, has no knob; only fit and depth to pick
  const gift = state.options.lid === "gift";
  if (lidOn() && gift) {
    kids.push(...optionControl({ key: "lid_fit", label: "Fit", kind: "seg", choices: [["snug", "Snug 0.15"], ["slip", "Slip 0.25"], ["loose", "Loose 0.40"]], default: "slip" }, after));
    const h = state.options.lid_height ? parseFloat(state.options.lid_height) : 30;
    const out = el("output", {}, `${h} mm`);
    const rng = el("input", { type: "range", min: "12", max: "60", step: "1", value: String(h), "aria-label": "Lid depth" });
    rng.addEventListener("input", () => { out.textContent = `${rng.value} mm`; });
    rng.addEventListener("change", () => { state.options.lid_height = rng.value; after(); });
    kids.push(el("div", { class: "field-label" }, "Lid depth"), el("div", { class: "height" }, rng, out));
    // over an insert: a liner standing up out of the box is the neck; the lid is sized to slide over it, flush
    const num = (key, label) => {
      const i = el("input", { type: "number", min: "0", step: "0.1", value: state.options[key] || "", placeholder: label, "aria-label": `Insert ${label}`, class: "num" });
      i.addEventListener("change", () => { const x = parseFloat(i.value); if (x > 0) state.options[key] = String(x); else delete state.options[key]; after(); });
      return i;
    };
    kids.push(el("div", { class: "field-label" }, "Fits over an insert (outside, mm)"), el("div", { class: "height" }, num("lid_over_w", "width"), el("span", {}, "×"), num("lid_over_d", "depth")));
    kids.push(el("p", { class: "hint" }, state.options.lid_over_w && state.options.lid_over_d
      ? "Over an insert: no neck. The base is woven to its rim (height = the seam); the insert stands up out of it and the lid slides over the insert, flush with the base."
      : "Closes flush: the weave stops at the seam and the lid slides over a smooth neck. Height is the base up to its rim; the wall needs room for the lid wall, the fit and the neck (10 mm works). Or give an insert's size and the insert becomes the neck."));
  } else if (lidOn()) {
    const L = CAT.lid, groups = {};
    for (const t of L.textures) {
      const fits = t.family === "match" || t.family === "plain" || CAT.textures.find((x) => x.key === t.key)?.fits.includes(sh.round ? "cup" : state.shape);
      if (fits) (groups[t.family] ||= []).push(t);
    }
    const sel = el("select", { "aria-label": "Lid look", class: "lid-look" }, ...Object.entries(groups).map(([fam, ts]) =>
      fam === "match" || fam === "plain" ? ts.map((t) => { const o = el("option", { value: t.key }, t.name); o.selected = (state.options.lid_texture || "match") === t.key; return o; })
      : el("optgroup", { label: FAMILY_NAMES[fam] || fam }, ...ts.map((t) => { const o = el("option", { value: t.key }, t.name); o.selected = state.options.lid_texture === t.key; return o; }))).flat());
    sel.addEventListener("change", () => { state.options.lid_texture = sel.value; after(); });
    kids.push(el("div", { class: "field-label" }, "Look"), sel);
    kids.push(...optionControl({ key: "lid_fit", label: "Fit", kind: "seg", choices: [["snug", "Snug 0.15"], ["slip", "Slip 0.25"], ["loose", "Loose 0.40"]], default: "slip" }, after));
    // height: auto unless set
    const h = state.options.lid_height ? parseFloat(state.options.lid_height) : null;
    const out = el("output", {}, h ? `${h} mm` : "Auto");
    const rng = el("input", { type: "range", min: "5", max: "40", step: "1", value: String(h || 11), "aria-label": "Lid height" });
    rng.addEventListener("input", () => { out.textContent = `${rng.value} mm`; });
    rng.addEventListener("change", () => { state.options.lid_height = rng.value; after(); });
    const auto = h ? el("button", { class: "ghost small", onclick: () => { delete state.options.lid_height; after(); } }, "Auto") : null;
    kids.push(el("div", { class: "field-label" }, "Height"), el("div", { class: "height" }, rng, out, auto));
    if ((state.options.lid_texture || "match") !== "match") {
      const chip = (key, def) => {
        const i = Number.isFinite(parseInt(state.options[key], 10)) ? parseInt(state.options[key], 10) : parseInt(def, 10);
        return el("button", { class: "chip-btn", style: `background:${state.colours[i]}`, title: `AMS ${i + 1} — click to change`, "aria-label": `Lid colour AMS ${i + 1}`,
          onclick: () => { state.options[key] = String((i + 1) % MAX_SLOTS); after(); } }, el("span", {}, String(i + 1)));
      };
      kids.push(el("div", { class: "field-label" }, "Colours"), el("div", { class: "chips" }, chip("lid_slot", "0"), lidTwoSlot() ? chip("lid_slot2", "1") : null));
    }
    kids.push(...optionControl({ key: "lid_knob", label: "Knob", kind: "seg", choices: CAT.lid.knobs, default: "knob" }, after));
    kids.push(...engraveControl("engrave_lid", "Words on the lid", after));
    kids.push(...optionControl({ key: "lid_plate", label: "Print the lid", kind: "seg",
      choices: [["auto", "Auto"], ["same", "With the piece"], ["own", "On its own"]], default: "auto" }, after));
    kids.push(el("p", { class: "hint" }, "Auto prints the lid on its own plate when sharing would add colour changes."));
  }
  $("lid").replaceChildren(...kids);
}

// ── building: drafts while dragging, full on release; newer requests cancel older ones ─────
let timer = null, reqSeq = 0, reframe = true;
// speed: every change shows a quick sketch first, then the full build replaces it quietly (woven pieces have no
// cheaper sketch, so they go straight to the full build)
function changed(newShape = false, dragging = false) {
  if (newShape) reframe = true;
  writeUrl(); clearTimeout(timer);
  timer = setTimeout(async () => {
    if (dragging) return requestBuild(true);
    const sketchFirst = textureOf(state.texture).family !== "lattice";
    if (!sketchFirst) return requestBuild(false);
    const seq = await requestBuild(true);
    if (seq === reqSeq) requestBuild(false, true);
  }, dragging ? 60 : 120);
}
async function requestBuild(draft, quiet = false) {
  const seq = ++reqSeq;
  $("status").hidden = false; $("status").classList.toggle("quiet", quiet);
  $("statusText").textContent = quiet ? "Refining…" : draft ? "Sketching…" : ({ fabric: "Knitting…", droop: "Spinning strands…", halftone: "Screening…", colourwork: "Knitting the chart…", mix: "Stacking bands…", spiral: "Folding…", shell: "Shaping…", flat: "Mapping the picture…" }[textureOf(state.texture).family] || "Weaving…");
  try {
    const res = await fetch("/api/build", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ shape: state.shape, texture: state.texture, nozzle: state.nozzle, params: state.params, draft,
        colours: state.colours.slice(0, pieceSlotCount()), options: buildOptions() }) });
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
  return seq;
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
  if (s.lid) rows.push(["Lid", `${s.lid.cap ? s.lid.cap + " · " : ""}${{ slip: "slip-on", gift: "gift box", thread: "screw", magnets: "magnets" }[s.lid.style] || "lid"} · ${s.lid.clearance} mm fit`
    + (s.lid.style === "gift" ? ` · closed ${s.lid.closed_h} mm, seam ${s.lid.seam} mm${s.lid.mode ? `, over a ${s.lid.over[0]} × ${s.lid.over[1]} insert, ceiling ${s.lid.ceiling} mm` : ""}` : "")
    + (s.lid.plate === "own" ? ` · own plate${s.lid.swaps ? `, ${fmt(s.lid.swaps)} changes` : ""}` : "")]);
  rows.push(["Colours", String(s.colours)]);
  if (s.swaps) rows.push(["AMS changes", `${fmt(s.swaps)} · ≈ ${fmt(s.swap_minutes)} min`]);
  if (s.minutes_est) rows.push(["Print time", `≈ ${s.minutes_est >= 60 ? `${Math.floor(s.minutes_est / 60)} h ${Math.round(s.minutes_est % 60)} min` : `${Math.round(s.minutes_est)} min`}`]);
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
  if (tex.swaps === "layer" && s.colours > 1 && !["halftone", "flat", "colourwork"].includes(tex.family)) notes.push("This pattern changes colour about once per layer — expect a long print, or pick one colour.");
  if ((tex.family === "halftone" || isMix()) && s.swaps > 300) notes.push(`${fmt(s.swaps)} colour changes — Lean purge, a 0.8 nozzle or a shorter halftone band cut that a lot.`);
  notes.push({
    lattice: "No supports, no infill — the rods are the object. Print on a clean plate, no brim.",
    fabric: "Vase mode off. The layer height must stay at " + noz.layer + " mm — the pattern is built on it.",
    droop: state.texture === "fur" ? "Hairs print as fast bridges at full fan, a little cooler, so they stay stiff — keep the project's cooling." : "Glossy or translucent PETG/PLA shows the strands best. Don't slow overhangs down or raise the fan — the strands only droop while molten.",
    halftone: `Prints at ${s.layer_h} mm layers with one ${s.line} mm line — keep those, the picture is built on them.`,
    colourwork: `Prints at ${s.layer_h} mm layers with one ${s.line} mm line, ${s.stitches} stitches around (${s.stitch_mm} mm each) — keep those, the chart is built on them.`,
    ...{},
    shell: { voronoi: "Every cell has a pointed roof, so the holes print without supports.",
      litho: "The picture shows when lit from inside: an LED puck or tealight, never a flame.",
      fuzzy: null }[state.texture],
    mix: "Keep the project's layer heights — each band is built on its own. Halftone bands print at their recipe height through a layer range.",
  }[tex.family]);
  if (s.lid) notes.push("The lid is a short cap of the piece itself, printed top-face down; its rim sits on the piece's rim so the texture carries across. Press the knob in from the top.");
  $("notes").replaceChildren(...notes.filter(Boolean).map((n) => el("li", {}, n)));
  const bl = $("backlit"); bl.hidden = !s.backlit;
  if (s.backlit) bl.replaceChildren(el("img", { src: s.backlit, alt: "The picture as it shows lit from behind" }),
    el("figcaption", {}, textureOf(state.texture).family === "shell" ? "Lit from inside, unrolled (estimate)" : "Lit from behind (estimate)"));
  const set = [["Printer", CAT.printer.name], ["Nozzle", `${s.nozzle} mm`], ["Layer height", `${s.layer_h} mm`],
    ...({ lattice: [["Rod", s.rod], ["Rod spacing", `${s.pitch} mm`], ["Walls", "rods only"], ["Infill", "0%"]],
          fabric: [["Walls", "2 loops"], ["Infill", "0%"], ["Top layers", "0"]],
          mix: [["Walls", "2 loops"], ["Infill", "0%"], ["Bands", `${s.bands}`]],
          spiral: [["Mode", "spiral vase"], ["Walls", "1"], ["Infill", "0%"]],
          shell: [["Walls", state.texture === "litho" ? "solid (lithophane)" : "2–4 loops"], ["Infill", "0%"]],
          flat: [["Layer height", `${s.layer_h} mm`], ["Pixel", `${s.pixel} mm`], ["Solid", "100%"]],
          halftone: [["Line width", `${s.line} mm, 1 wall`], ["Infill", "0%"], ["Colour changes", "every layer"]],
          colourwork: [["Line width", `${s.line} mm, 1 wall`], ["Infill", "0%"], ["Colour changes", "every layer in 2–3 colour bands"]],
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
    el("span", { class: "sub" }, `${fmt(sl.grams, 0)} g · ${fmt(sl.layers)} layers${sl.changes !== undefined ? ` · ${fmt(sl.changes)} colour changes` : ""}`), el("br"),
    el("span", { class: "sub" }, `Bambu Studio's own numbers for the P2S, AMS changes and purge included.`),
    sl.preview && job ? el("figure", { class: "sliced" }, el("img", { src: `/api/job/${job.id}/sliced.png?${Date.now()}`, alt: "The sliced print paths, seen from the front" }),
      el("figcaption", {}, "As sliced — the paths the printer lays, from the front")) : "");
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
      el("button", { class: "secondary", type: "button", onclick: async (e) => {
        const btn = e.currentTarget; btn.disabled = true; btn.textContent = "Testing…";
        const r = await fetch("/api/printer/test", { method: "POST" }); const d = await r.json();
        btn.disabled = false; btn.textContent = "Test connection";
        if (!r.ok) return toast(d.error);
        const ams = (d.ams || []).map((t) => `AMS ${t.slot}: ${t.type} ${t.colour}`).join(" · ");
        result.textContent = `Files: ${d.ftps}. Status: ${d.mqtt}${d.state ? ` (${d.state})` : ""}.${ams ? " " + ams : ""}`;
      } }, "Test connection"),
      el("button", { class: "primary", type: "submit" }, "Save")));
  const result = el("p", { class: "hint" }, "Test connection checks the login and reads the printer's status — it never starts a print.");
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
    form, result);
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
// lighting: Studio (even) or Raking (low, from the side — how halftone ribs and fine texture read on a real print)
const hemi = scene.children.find((c) => c.isHemisphereLight);
let lighting = "studio";
const keyHome = key.position.clone();
function setLighting(mode) {
  lighting = mode;
  if (mode === "raking") { hemi.intensity = 0.45; key.intensity = 3.2; key.position.set(260, 40, 60); rim.intensity = 0.15; }
  else { hemi.intensity = 1.35; key.intensity = 2.0; key.position.copy(keyHome); rim.intensity = 0.6; }
  seg($("lightView"), [["studio", "Studio light", "Even light"], ["raking", "Raking light", "Low light from the side — how halftone and fine texture read on the print"]],
    lighting, setLighting);
}
setTimeout(() => setLighting("studio"), 0);
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
const PERF = (window.__t2pPerf = window.__t2pPerf || []);
async function showModel(d) {
  const t0 = performance.now(); let tNorm = 0;
  const list = (d.preview && draped ? d.preview : d.parts).concat(d.lid || []);
  const meshes = await Promise.all(list.map(async (p) => {
    const buf = await (await fetch(p.url)).arrayBuffer();
    const [nv, nf] = new Uint32Array(buf, 0, 2);
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(buf, 8, nv * 3), 3));
    g.setIndex(new THREE.BufferAttribute(new Uint32Array(buf, 8 + nv * 12, nf * 3), 1));
    const tn = performance.now(); g.rotateX(-Math.PI / 2); g.computeVertexNormals(); tNorm += performance.now() - tn;
    const m = new THREE.Mesh(g, new THREE.MeshStandardMaterial({ color: new THREE.Color(p.colour), roughness: 0.82, metalness: 0 }));
    m.castShadow = true; m.receiveShadow = true; return m;
  }));
  const next = new THREE.Group(); meshes.forEach((m) => next.add(m));
  const box = new THREE.Box3().setFromObject(next), c = box.getCenter(new THREE.Vector3());
  next.position.set(-c.x, -box.min.y, -c.z);
  scene.remove(model); model.traverse((o) => { if (o.geometry) { o.geometry.dispose(); o.material.dispose(); } });
  model = next; scene.add(model);
  if (reframe) { frame(); reframe = false; }
  const tr = performance.now(); renderer.render(scene, camera);
  PERF.push({ texture: state.texture, total: Math.round(performance.now() - t0), normals: Math.round(tNorm), firstFrame: Math.round(performance.now() - tr),
              tris: d.parts.reduce((a, p) => a + p.triangles, 0) });
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
