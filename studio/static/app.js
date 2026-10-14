import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const $ = (id) => document.getElementById(id);
const el = (tag, attrs = {}, ...kids) => {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") n.className = v; else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else if (v !== undefined && v !== null) n.setAttribute(k, v);
  }
  for (const k of kids) n.append(k);
  return n;
};
const fmt = (n, d = 0) => Number(n).toLocaleString(undefined, { maximumFractionDigits: d, minimumFractionDigits: d });

let CAT = null;
const state = { shape: null, texture: null, nozzle: 0.4, params: {}, colours: [], options: {}, bands: null };
const MAX_SLOTS = 4;
let job = null;
let draped = true;               // droop pieces: show strands hung as gravity will hang them

// ── catalogue + url state ──────────────────────────────────────────────────────
const shapeOf = (k) => CAT.shapes.find((s) => s.key === k);
const textureOf = (k) => CAT.textures.find((t) => t.key === k);
const fits = (shape, tex) => tex.fits.includes(shape.key);
const nameOfColour = (hex) => Object.entries(CAT.palette).find(([, h]) => h.toLowerCase() === hex.toLowerCase())?.[0] || hex.toUpperCase();

function readUrl() {
  const q = new URLSearchParams(location.search);
  if (q.get("shape") && shapeOf(q.get("shape"))) state.shape = q.get("shape");
  if (q.get("texture") && textureOf(q.get("texture"))) state.texture = q.get("texture");
  if (q.get("nozzle")) state.nozzle = parseFloat(q.get("nozzle"));
  if (q.get("c")) state.colours = q.get("c").split(",").map((h) => "#" + h.replace("#", ""));
  const optKeys = Object.values(CAT.options).flat().map((o) => o.key);
  for (const [k, v] of q) {
    if (k === "mix") { try { state.bands = JSON.parse(v); } catch (e) { /* ignore a bad link */ } }
    else if (optKeys.includes(k)) state.options[k] = v === "1" ? true : v === "0" ? false : v;
    else if (!["shape", "texture", "nozzle", "c"].includes(k)) state.params[k] = parseFloat(v);
  }
}
function writeUrl() {
  const q = new URLSearchParams({ shape: state.shape, texture: state.texture, nozzle: state.nozzle });
  const sh = shapeOf(state.shape);
  for (const p of sh.params) if (state.params[p.key] !== undefined && state.params[p.key] !== p.default) q.set(p.key, state.params[p.key]);
  q.set("c", state.colours.slice(0, slotCount()).map((h) => h.replace("#", "")).join(","));
  if (isMix()) q.set("mix", JSON.stringify(state.bands));
  for (const o of familyOptions()) {
    const v = state.options[o.key] ?? o.default;
    if (v !== o.default) q.set(o.key, v === true ? "1" : v === false ? "0" : v);
  }
  history.replaceState(null, "", "?" + q.toString());
}

const isMix = () => textureOf(state.texture).family === "mix";
function slotCount() {
  if (!isMix()) return textureOf(state.texture).slots;
  return Math.max(1, ...state.bands.flatMap((b) => b.texture === "halftone" ? [b.slot + 1, (b.slot2 ?? 1) + 1] : [b.slot + 1]));
}

// ── picker ─────────────────────────────────────────────────────────────────────
function seg(container, items, current, onPick) {
  container.replaceChildren(...items.map(([value, label, title]) => el("button", {
    role: "radio", "aria-checked": String(value === current), title,
    onclick: () => onPick(value),
  }, label)));
}

function card(item, checked, onPick) {
  return el("button", { class: "card", role: "radio", "aria-checked": String(checked), title: item.blurb, onclick: onPick },
    el("img", { src: item.thumb, alt: "", loading: "lazy" }), el("span", {}, item.name));
}

function renderNozzles() {
  seg($("nozzles"), CAT.nozzles.map((n) => [n.size, `${n.size}`, `${n.size} mm nozzle · ${n.layer} mm layers · rods ${n.rod} mm${n.verified ? " · print-verified" : ""}`]),
    state.nozzle, (v) => { state.nozzle = v; renderNozzles(); changed(); });
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
  renderAll(); changed(true);
}

function renderTextures() {
  const sh = shapeOf(state.shape);
  const groups = [["lattice", "Woven rods"], ["fabric", "Printed fabric"], ["droop", "Droop"], ["halftone", "Halftone"], ["mix", "Mix"]].filter(([f]) => sh.families.includes(f));
  const kids = [];
  for (const [fam, label] of groups) {
    if (groups.length > 1) kids.push(el("div", { class: "group-label" }, label));
    kids.push(el("div", { class: "cards" }, ...CAT.textures.filter((t) => t.family === fam && fits(sh, t))
      .map((t) => card(t, t.key === state.texture, () => { state.texture = t.key; renderAll(); changed(); }))));
  }
  kids.push(el("p", { class: "desc" }, textureOf(state.texture).blurb));
  $("textures").replaceChildren(...kids);
}

function renderSizes() {
  const sh = shapeOf(state.shape), fam = textureOf(state.texture).family;
  $("sizes").replaceChildren(...sh.params.filter((p) => !p.family || p.family === fam).map((p) => {
    const val = state.params[p.key] ?? p.default;
    const out = el("output", {}, `${fmt(val, p.step < 1 ? 1 : 0)} ${p.unit}`);
    const input = el("input", { type: "range", min: p.lo, max: p.hi, step: p.step, value: val, id: `p_${p.key}`, "aria-label": p.label });
    input.addEventListener("input", () => {
      state.params[p.key] = parseFloat(input.value);
      out.textContent = `${fmt(input.value, p.step < 1 ? 1 : 0)} ${p.unit}`; changed();
    });
    return el("div", { class: "size-row" }, el("label", { for: `p_${p.key}` }, p.label), out, input);
  }));
}

function renderColours() {
  const tex = textureOf(state.texture);
  while (state.colours.length < 3) state.colours.push(CAT.colours[state.colours.length]);
  const n = slotCount();
  $("colours").replaceChildren(...Array.from({ length: n }, (_, i) => el("button", {
    class: "swatch-btn", onclick: (e) => openPalette(i, e.currentTarget),
  }, el("span", { class: "chip", style: `background:${state.colours[i]}` }), el("span", { class: "name" }, nameOfColour(state.colours[i])),
     el("span", { class: "slot" }, `AMS ${i + 1}`))));
  $("colourHint").textContent = isMix() ? (n === 1 ? "One colour — no AMS changes. Give a band another colour in Bands."
      : "Each band picks its AMS slot. Changes happen where bands meet, and every layer inside a halftone band.")
    : tex.slots === 1 ? "One colour — no AMS changes."
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
  const top = Math.min(r.bottom + 8, innerHeight - pop.offsetHeight - 12);
  pop.style.left = `${Math.min(r.left, innerWidth - 284)}px`; pop.style.top = `${top}px`;
}
document.addEventListener("pointerdown", (e) => {
  if (!$("palette").hidden && !$("palette").contains(e.target) && !e.target.closest(".swatch-btn")) $("palette").hidden = true;
});

const familyOptions = () => CAT.options[textureOf(state.texture).family] || [];
function renderFinish() {
  const opts = familyOptions();
  $("finishSec").hidden = !opts.length;
  $("finish").replaceChildren(...opts.flatMap((o) => {
    const val = state.options[o.key] ?? o.default;
    if (o.kind === "toggle") {
      const input = el("input", { type: "checkbox" }); input.checked = !!val;
      input.addEventListener("change", () => { state.options[o.key] = input.checked; changed(); });
      return [el("label", { class: "toggle" }, input, el("span", {}, o.label))];
    }
    const box = el("div", { class: "seg small", role: "radiogroup", "aria-label": o.label });
    seg(box, o.choices.map(([v, l]) => [v, l]), val, (v) => { state.options[o.key] = v; renderFinish(); changed(); });
    return [el("div", { class: "field-label" }, o.label), box];
  }));
}

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
    return el("button", { class: "chip-btn", style: `background:${state.colours[i]}`, title: `AMS ${i + 1} — click to change`,
      onclick: () => { b[key] = (i + 1) % MAX_SLOTS; edit(); } }, el("span", {}, String(i + 1)));
  };
  const rows = state.bands.map((b, idx) => {
    const sel = el("select", { "aria-label": "Band texture" }, ...M.textures.map((t) => {
      const o = el("option", { value: t.key }, t.name); if (t.key === b.texture) o.selected = true; return o; }));
    sel.addEventListener("change", () => { b.texture = sel.value; b.options = {}; if (b.texture === "halftone" && b.slot2 === undefined) b.slot2 = (b.slot + 1) % MAX_SLOTS; edit(); });
    const out = el("output", {}, `${Math.round(100 * b.share / total)}%`);
    const range = el("input", { type: "range", min: 3, max: 90, step: 1, value: b.share, "aria-label": "Band height" });
    range.addEventListener("input", () => { b.share = +range.value; out.textContent = `${Math.round(100 * b.share / state.bands.reduce((a, x) => a + x.share, 0))}%`; state.mixPreset = null; writeUrl(); changed(); });
    const kids = [sel, el("div", { class: "chips" }, chip(b, "slot"), ...(b.texture === "halftone" ? [chip(b, "slot2")] : [])),
      el("button", { class: "x", title: "Remove band", "aria-label": "Remove band", disabled: state.bands.length < 2 ? "" : null,
        onclick: () => { state.bands.splice(idx, 1); edit(); } }, "×"),
      el("div", { class: "share" }, range, out)];
    const fam = M.textures.find((t) => t.key === b.texture).family;
    if (fam === "droop" || b.texture === "halftone") {
      const key = fam === "droop" ? "density" : "picture";
      const choices = fam === "droop" ? M.droop_options : M.pictures;
      const box = el("div", { class: "seg small sub" });
      seg(box, choices, (b.options || {})[key] ?? (fam === "droop" ? "medium" : "flames"), (v) => { b.options = { ...(b.options || {}), [key]: v }; edit(); });
      kids.push(box);
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

// ── building ───────────────────────────────────────────────────────────────────
let timer = null, inflight = false, pending = false, reframe = true;
function changed(newShape = false) {
  if (newShape) reframe = true;
  writeUrl(); clearTimeout(timer); timer = setTimeout(requestBuild, 280);
}
async function requestBuild() {
  if (inflight) { pending = true; return; }
  inflight = true; pending = false;
  $("status").hidden = false; $("statusText").textContent = { fabric: "Knitting…", droop: "Spinning strands…", halftone: "Screening…", mix: "Stacking bands…" }[textureOf(state.texture).family] || "Weaving…";
  try {
    const res = await fetch("/api/build", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ shape: state.shape, texture: state.texture, nozzle: state.nozzle, params: state.params,
        colours: state.colours.slice(0, slotCount()), options: isMix() ? { bands: state.bands } : state.options }) });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Build failed");
    if (!pending) {
      job = data; $("error").hidden = true;
      renderDropView(data); await showModel(data); renderPrint(data);
    }
  } catch (e) {
    $("error").textContent = e.message; $("error").hidden = false;
  } finally {
    inflight = false; $("status").hidden = !pending;
    if (pending) requestBuild();
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
  rows.push(["Colours", String(s.colours)]);
  if (s.swaps) rows.push(["AMS changes", `${fmt(s.swaps)} · ≈ ${fmt(s.swap_minutes)} min`]);
  rows.push(["Filament", s.grams_purge ? `≈ ${fmt(s.grams_part)} g + ${fmt(s.grams_purge)} g purge` : `≈ ${fmt(s.grams_est)} g`]);
  $("stats").replaceChildren(...rows.flatMap(([k, v]) => [el("dt", {}, k), el("dd", {}, v)]));
  $("dims").replaceChildren(`${fmt(s.size[0])} × ${fmt(s.size[1])} × ${fmt(s.size[2], 1)} mm`,
    el("span", { class: "tris" }, ` · ${fmt(s.triangles / 1e6, 2)} M triangles`));
  $("slice").replaceChildren();
  $("sliceBtn").disabled = !CAT.slicer; $("sliceBtn").textContent = "Get exact print time";
  $("openBtn").textContent = CAT.slicer ? "Open in Bambu Studio" : "Save to Downloads";
  $("dl3mf").href = `/api/job/${d.id}/download`; $("dlStl").href = `/api/job/${d.id}/stls`;
  const noz = CAT.nozzles.find((n) => n.size === s.nozzle);
  const notes = [...d.warnings];
  if (tex.swaps === "layer" && s.colours > 1 && tex.family !== "halftone") notes.push("This pattern changes colour about once per layer — expect a long print, or pick one colour.");
  if (tex.family === "halftone" && s.swaps > 400) notes.push(`${fmt(s.swaps)} colour changes — a bigger nozzle or 2 layers per colour cuts that a lot.`);
  notes.push({
    lattice: "No supports, no infill — the rods are the object. Print on a clean plate, no brim.",
    fabric: "Vase mode off. The layer height must stay at " + noz.layer + " mm — the pattern is built on it.",
    mix: "One layer height and one wall for every band. Vase mode off; keep the project's layer height — the bands are built on it.",
    halftone: `Prints at ${s.layer_h} mm layers with one ${s.line} mm line — keep those, the picture is built on them.`,
    droop: "Glossy or translucent PETG/PLA shows the strands best. Don't slow overhangs down or raise the fan — the strands only droop while molten.",
  }[tex.family]);
  $("notes").replaceChildren(...notes.map((n) => el("li", {}, n)));
  const set = [["Printer", CAT.printer.name], ["Nozzle", `${s.nozzle} mm`], ["Layer height", `${s.layer_h} mm`],
    ...({ lattice: [["Rod", s.rod], ["Rod spacing", `${s.pitch} mm`], ["Walls", "rods only"], ["Infill", "0%"]],
          fabric: [["Walls", "2 loops"], ["Infill", "0%"], ["Top layers", "0"]],
          mix: [["Walls", "2 loops"], ["Infill", "0%"], ["Bands", `${s.bands}`]],
          halftone: [["Line width", `${s.line} mm, 1 wall`], ["Infill", "0%"], ["Colour changes", "every layer"]],
          droop: [["Walls", "2 loops, strands 1 line"], ["Overhang slow-down", "off"], ["Fan", "≤ 20%"], ["Nozzle", "+5 °C"]] }[tex.family]),
    ["Supports", "none"], ["Filament", "Bambu PLA Matte"]];
  $("settings").replaceChildren(...set.flatMap(([k, v]) => [el("dt", {}, k), el("dd", {}, v)]));
}

$("sliceBtn").addEventListener("click", async () => {
  if (!job) return;
  const id = job.id; $("sliceBtn").disabled = true; $("sliceBtn").textContent = "Slicing in Bambu Studio…";
  $("slice").replaceChildren(el("span", { class: "sub" }, "Slicing on the real P2S profile — about a minute."));
  await fetch(`/api/job/${id}/slice`, { method: "POST" });
  for (;;) {
    await new Promise((r) => setTimeout(r, 1500));
    if (!job || job.id !== id) return;
    const s = await (await fetch(`/api/job/${id}/slice`)).json();
    if (s.state === "running") continue;
    $("sliceBtn").disabled = false; $("sliceBtn").textContent = "Get exact print time";
    if (s.state === "error") { $("slice").replaceChildren(el("span", { class: "sub" }, `Slicer: ${s.error}${s.detail ? " — " + s.detail : ""}`)); return; }
    const total = s.minutes + (job.stats.swap_minutes || 0), h = Math.floor(total / 60), m = Math.round(total % 60);
    $("slice").replaceChildren(el("span", { class: "big" }, `${h ? h + " h " : ""}${m} min`),
      el("span", { class: "sub" }, `${fmt(s.grams + (job.stats.swaps * 0.45), 0)} g · ${s.layers} layers`),
      el("br"), el("span", { class: "sub" }, job.stats.swaps ? `Includes ≈ ${job.stats.swap_minutes} min for ${job.stats.swaps} colour changes. Printing alone: ${s.time}.` : `Bambu Studio: ${s.time}.`));
    $("sliceBtn").textContent = "Sliced"; $("sliceBtn").disabled = true;
    return;
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

function toast(msg) {
  const t = $("toast"); t.textContent = msg; t.hidden = false;
  clearTimeout(toast.t); toast.t = setTimeout(() => { t.hidden = true; }, 4200);
}

// ── viewer ─────────────────────────────────────────────────────────────────────
const canvas = $("view");
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
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
key.position.set(160, 260, 140); key.castShadow = true;
key.shadow.mapSize.set(2048, 2048); key.shadow.bias = -0.0004;
Object.assign(key.shadow.camera, { left: -180, right: 180, top: 180, bottom: -180, near: 10, far: 900 });
scene.add(key);
const rim = new THREE.DirectionalLight(0xfff1e0, 0.6); rim.position.set(-200, 120, -160); scene.add(rim);

const BED = 256;
const plate = new THREE.Mesh(new THREE.PlaneGeometry(BED, BED), new THREE.MeshStandardMaterial({ color: 0xe4ddd1, roughness: 0.95 }));
plate.rotation.x = -Math.PI / 2; plate.position.y = -0.05; plate.receiveShadow = true; scene.add(plate);
const grid = new THREE.GridHelper(BED, 16, 0xcfc6b8, 0xd8d0c3); grid.position.y = 0.01; scene.add(grid);
const edge = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.PlaneGeometry(BED, BED)),
  new THREE.LineBasicMaterial({ color: 0xb9ae9e })); edge.rotation.x = -Math.PI / 2; edge.position.y = 0.02; scene.add(edge);

let model = new THREE.Group(); scene.add(model);

function renderDropView(d) {
  const box = $("dropView"); box.hidden = !d.preview;
  if (!d.preview) return;
  seg(box, [[true, "After droop", "Strands hung as gravity will hang them (preview)"], [false, "As printed", "The flat strands the printer lays"]],
    draped, async (v) => { draped = v; renderDropView(job); await showModel(job); });
}

async function showModel(d) {
  const list = d.preview && draped ? d.preview : d.parts;
  const meshes = await Promise.all(list.map(async (p) => {
    const buf = await (await fetch(p.url)).arrayBuffer();
    const [nv, nf] = new Uint32Array(buf, 0, 2);
    const pos = new Float32Array(buf, 8, nv * 3), idx = new Uint32Array(buf, 8 + nv * 12, nf * 3);
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(pos, 3)); g.setIndex(new THREE.BufferAttribute(idx, 1));
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
  $("printerName").textContent = CAT.printer.name;
  state.shape = CAT.defaults.shape; state.texture = CAT.defaults.texture; state.nozzle = CAT.defaults.nozzle;
  state.colours = [...CAT.colours];
  readUrl();
  if (!state.bands) { state.mixPreset = CAT.mix.default; state.bands = structuredClone(CAT.mix.presets.find((p) => p.key === CAT.mix.default).bands); }
  if (!fits(shapeOf(state.shape), textureOf(state.texture))) state.texture = CAT.textures.find((t) => fits(shapeOf(state.shape), t)).key;
  renderNozzles(); renderAll(); changed(true);
})();
