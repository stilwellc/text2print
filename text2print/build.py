"""Pick a shape, pick a texture, set sizes and colours -> a Bambu P2S project.

    from text2print import build
    b = build.make("tray", "selvedge", {"width": 117}, nozzle=0.4, colours=["#8B3A2F", "#EDE3D1"])
    b.write_3mf("tray.3mf"); print(b.stats)
"""
import json
import math
import pathlib
from dataclasses import dataclass, field

import numpy as np
import trimesh

from . import bambu, compose, droop, extras, fabric, fittings, flat, halftone, lattice, printer, shell, spiral, verify
from .shapes import SHAPES

# Bambu PLA Matte, approximate swatches (preview + 3MF colour only; the real colour is your spool)
PALETTE = {
    "Terracotta": "#A8543A", "Brick": "#8B3A2F", "Bone White": "#EDE3D1", "Ivory White": "#F4F1E8",
    "Desert Tan": "#D2B48C", "Latte Brown": "#A0785A", "Caramel": "#C58A3F", "Dark Chocolate": "#4A2F27",
    "Lemon Yellow": "#F3D34A", "Mandarin Orange": "#E8752F", "Sakura Pink": "#E9B7C4", "Scarlet Red": "#C3302C",
    "Lilac Purple": "#A99BC8", "Sky Blue": "#86B5DA", "Marine Blue": "#2E4E7E", "Dark Blue": "#1F2A44",
    "Grass Green": "#5E9E4A", "Dark Green": "#2F4F3A", "Ash Gray": "#9C9C98", "Charcoal": "#2B2B2B",
}
DEFAULT_COLOURS = ["#8B3A2F", "#EDE3D1", "#C58A3F"]

TEXTURES = {**{k: dict(family="lattice", **{kk: vv for kk, vv in v.items() if kk != "fn"})
               for k, v in lattice.PATTERNS.items()},
            **{k: dict(family="fabric", slots=1, swaps="none", **v) for k, v in fabric.STITCHES.items()},
            **{k: dict(family="droop", slots=1, swaps="none", **v) for k, v in droop.STYLES.items()},
            "halftone": dict(family="halftone", slots=2, swaps="layer", name="Halftone",
                             blurb="Two colours alternate every layer; the one that ribs outward paints a picture"),
            **{k: dict(family="spiral", slots=1, swaps="none", **v) for k, v in spiral.STYLES.items()},
            **{k: dict(family="shell", slots=1, swaps="none", **v) for k, v in shell.STYLES.items()},
            "flatlitho": dict(family="flat", slots=1, swaps="none", **flat.STYLES["litho"]),
            "cmyk": dict(family="flat", slots=4, swaps="layer", **flat.STYLES["cmyk"]),
            "mix": dict(family="mix", slots=4, swaps="band", name="Mix",
                        blurb="Stack textures in bands up the wall — woven, fabric, droop, halftone and plain")}

ZONES = [("zones", "Colours", "seg", [("1", "1"), ("2", "2"), ("3", "3"), ("4", "4")], "1"),
         ("zone_style", "Colour layout", "seg", [("bands", "Bands"), ("stripes", "Stripes")], "bands")]
LID = [("lid", "Lid", "seg", [("none", "None"), ("slip", "Slip-on"), ("thread", "Screw"), ("magnets", "Magnets")], "none"),
       ("lid_fit", "Lid fit", "seg", [("snug", "Snug 0.15"), ("slip", "Slip 0.25"), ("loose", "Loose 0.40")], "slip")]

# options each family offers in the picker: key -> (label, kind, choices, default)
OPTIONS = {
    "fabric": [("rim_loops", "Loop edge at the rim", "toggle", None, False),
               ("floor", "Floor", "seg", [("solid", "Solid"), ("diamonds", "Diamonds"), ("lens", "Eyes")], "solid")] + ZONES,
    "droop": [("density", "Density", "seg", [("sparse", "Sparse"), ("medium", "Medium"), ("dense", "Dense")], "medium"),
              ("length", "Loop length", "seg", [("short", "Short"), ("medium", "Medium"), ("long", "Long")], "medium"),
              ZONES[0],
              ("zone_style", "Colour layout", "seg", [("courses", "Courses"), ("bands", "Bands"), ("stripes", "Stripes")], "courses"),
              ("course_rows", "Rows per colour", "seg", [("1", "1"), ("2", "2"), ("3", "3"), ("4", "4")], "1")],
    "lattice": [("colour_by", "Colour by", "seg", [("direction", "Rod direction"), ("height", "Height")], "direction")] + ZONES,
    "shell": [("cell", "Cell size", "seg", [("small", "Small"), ("medium", "Medium"), ("large", "Large")], "medium"),
              ("noise", "Fuzzy pattern", "seg", [(k, v) for k, v in shell.NOISE.items()], "perlin"),
              ("fuzzy_bands", "Fuzzy where", "seg", [("all", "Everywhere"), ("thirds", "Bands"), ("stripes", "Stripes")], "all"),
              ("picture", "Picture", "seg", [("moon", "Moon"), ("flames", "Flames"), ("waves", "Waves"), ("dots", "Dots")], "moon")]
             + ZONES,
    "flat": [("picture", "Picture", "seg", [("sunset", "Sunset")], "sunset")],
    "spiral": [("folds", "Folds", "seg", [("8", "8"), ("16", "16"), ("24", "24"), ("36", "36")], "24"),
               ("turn", "Twist", "seg", [("0", "None"), ("60", "60°"), ("120", "120°"), ("240", "240°")], "120")],
    "mix": [("purge", "Purge", "seg", [("standard", "Standard"), ("lean", "Lean — less waste, slight tint")], "standard")],
    "halftone": [("picture", "Picture", "seg", [(k, v["name"]) for k, v in halftone.PICTURES.items()], "flames"),
                 ("band", "Layers per colour", "seg", [("1", "1 — sharpest"), ("2", "2"), ("3", "3 — a third")], "1"),
                 ("area", "Picture on", "seg", [("full", "Whole piece"), ("half", "Lower half"), ("third", "Lower third")], "full"),
                 ("silk", "Filament", "seg", [("ams", "Two colours (AMS)"), ("silk", "Dual-colour silk — no changes")], "ams"),
                 ("purge_piece", "Purge into", "seg", [("tower", "Prime tower"), ("coaster", "A coaster too")], "tower"),
                 ("purge", "Purge", "seg", [("standard", "Standard"), ("lean", "Lean — less waste, slight tint")], "standard")],
}

SOLID_OBJECT = {"wall_loops": "3", "sparse_infill_density": "20%", "top_shell_layers": "4", "bottom_shell_layers": "4",
                "spiral_mode": "0", "fuzzy_skin": "none"}
SWAP_SECONDS = 45          # P2S AMS filament change incl. flush (rough)
SWAP_GRAMS = 0.45          # flush + prime tower per change at the project's 280 mm3 flush volume


def compatible(shape_key, texture_key):
    s, t = SHAPES[shape_key], TEXTURES[texture_key]
    return t["family"] in s.families and (not t.get("round_only") or s.round)


@dataclass
class Build:
    shape: str
    texture: str
    nozzle: float
    params: dict
    family: str
    parts: list                       # [(name, mesh, slot_index_1_based, colour_hex)]
    stats: dict
    overrides: dict
    warnings: list = field(default_factory=list)
    preview: list = None              # [(name, mesh, slot, colour)] — droop: strands hung as gravity will hang them
    ranges: list = field(default_factory=list)          # [(z0, z1, {option: value})] Bambu layer ranges
    per_filament: dict = None                            # filament-level settings per part colour
    flush_mult: float = 1.0
    draft: bool = False
    extras: list = field(default_factory=list)          # lid + knob: [(name, mesh, slot, colour)] in print orientation
    assembled: list = field(default_factory=list)       # the same, placed on the piece for the viewer

    @property
    def colours(self):
        out = []
        for _, _, _, c in self.parts:
            if c not in out:
                out.append(c)
        return out

    def title(self):
        return f"{SHAPES[self.shape].name} — {TEXTURES[self.texture]['name']}"

    def write_3mf(self, path):
        """The piece (with its layer ranges) and, if any, the lid and knob laid out flat beside it."""
        half = max(np.abs(m.bounds[:, :2]).max() for _, m, _, _ in self.parts)
        cols = list(self.colours)
        for _, _, _, c in self.extras:
            if c not in cols:
                cols.append(c)
        idx = lambda c: cols.index(c) + 1
        safe = printer.TOWER[0] - printer.TOWER[2] / 2 - 8
        objects = [{"name": self.title(), "position": None, "parts": [(n, m, idx(c)) for n, m, _, c in self.parts],
                    "ranges": self.ranges}]
        extra_halves = [float(np.abs(m.bounds[:, :2]).max()) for _, m, _, _ in self.extras]
        row = 2 * half + sum(2 * h + 8 for h in extra_halves)
        if self.extras and row + 16 <= printer.BED:
            x = 8 + half; objects[0]["position"] = (x, printer.BED / 2); x += half + 8
            for (n, m, _, c), h in zip(self.extras, extra_halves):
                # lids, knobs and coasters are solid parts: their own walls, infill and top/bottom shells, whatever
                # the piece uses (a fabric piece runs 0 % infill and no top layers)
                st = dict(SOLID_OBJECT)
                if n == "Purge coaster":
                    st["flush_into_objects"] = "1"
                objects.append({"name": n, "position": (x + h, min(printer.BED / 2, safe - h)), "parts": [(n, m, idx(c))],
                                "settings": st})
                x += 2 * h + 8
        else:
            objects[0]["position"] = self._centre(half)
            if self.extras:                                        # too big to share a plate: their own project
                lid_objects, x = [], 8
                for (n, m, _, c), h in zip(self.extras, extra_halves):
                    lid_objects.append({"name": n, "position": (x + h, printer.BED / 2), "parts": [(n, m, 1)]}); x += 2 * h + 8
                over = dict(self.overrides); over.update(SOLID_OBJECT); over["enable_prime_tower"] = "0"
                bambu.write_3mf(str(pathlib.Path(path).with_name(pathlib.Path(path).stem + "-lid.3mf")), lid_objects,
                                title=self.title() + " — lid", colours=(self.extras[0][3],), overrides=over,
                                base=printer.base_config(self.nozzle))
        over = dict(self.overrides); over["flush_multiplier"] = [f"{self.flush_mult:g}"]
        pf = self.per_filament
        if pf and len(cols) > len(self.colours):                    # the lid's own filament keeps stock cooling
            base = printer.filament_settings(self.nozzle, ["normal"])
            pf = {k: list(v) + base[k] * (len(cols) - len(v)) for k, v in pf.items()}
        bambu.write_3mf(str(path), objects, title=self.title(), colours=tuple(cols),
                        overrides=over, base=printer.base_config(self.nozzle), per_filament=pf)
        return pathlib.Path(path)

    def _centre(self, half):
        """Where the piece goes. One colour: no prime tower, so dead centre. With a tower: dodge it, or for round
        pieces up to ~116 mm radius sit in the centre and park the tower in the far corner instead. Three or more
        colours make a deep tower: park it front-right where it can grow backwards, and keep the piece left of it."""
        c = printer.BED / 2
        if len(self.colours) == 1 or self.overrides.get("enable_prime_tower") == "0":
            return (c, c)
        if len(self.colours) >= 3:
            tx = printer.BED - printer.TOWER[2] - 20                 # 20 mm margins: the tower's brim and growth
            self.overrides = dict(self.overrides, wipe_tower_x=[f"{tx:g}"], wipe_tower_y=["20"])
            x = min(c, tx - 8 - half)
            return (max(half + 6, x), c)
        safe = printer.TOWER[0] - printer.TOWER[2] / 2 - 8
        if c + half <= safe:
            return (c, c)
        if half <= c - 10 and self.round_footprint():
            self.overrides = dict(self.overrides, wipe_tower_x=["218"], wipe_tower_y=["218"])
            return (c, c)
        return (max(half + 8, safe - half), max(half + 8, safe - half))

    def round_footprint(self):
        v = np.vstack([m.vertices for _, m, _, _ in self.parts])
        r = np.hypot(v[:, 0], v[:, 1]).max(); half = np.abs(v[:, :2]).max()
        return r < half * 1.2                                         # circle-ish, not a square corner

    def write_stls(self, folder, stem):
        folder = pathlib.Path(folder); folder.mkdir(parents=True, exist_ok=True); out = []
        for name, m, s, _ in self.parts:
            p = folder / f"{stem}_{s}_{name.split()[0].lower()}.stl"; m.export(p); out.append(p)
        return out


def _cut_handles(parts, v, info, mix_preview=None):
    """Basket handle slots through both short walls: 14 mm straight, then a 45 deg pointed arch (no overhang)."""
    import manifold3d as m3d
    from .meshops import manifold_to_trimesh
    W, D, H = v["width"], v["depth"], v["height"]
    hw = min(32.0, D / 2 - 14.0); hz1 = H - 6.0; hz0 = hz1 - (14.0 + hw)
    if hw < 8 or hz0 < 10:
        return parts
    yz = [(-hw, hz0), (hw, hz0), (hw, hz0 + 14.0), (0.0, hz0 + 14.0 + hw), (-hw, hz0 + 14.0)]
    prism = []                                               # the slot profile (y, z) swept across each short wall
    for sign in (1, -1):
        x_in, x_out = sign * (W / 2 - 16.0), sign * (W / 2 + 45.0)
        lo, hi = min(x_in, x_out), max(x_in, x_out)
        pts = np.array([[x, y, z] for x in (lo, hi) for (y, z) in yz], float)
        prism.append(trimesh.convex.convex_hull(pts))
    cutter = trimesh.util.concatenate(prism)
    to_m = lambda t: m3d.Manifold(m3d.Mesh(vert_properties=np.asarray(t.vertices, np.float32), tri_verts=np.asarray(t.faces, np.int32)))
    cut = to_m(prism[0]) + to_m(prism[1])
    out = []
    for name, m, slot_, col in parts:
        out.append((name, manifold_to_trimesh(to_m(m) - cut), slot_, col))
    def face_cut(m):                                         # previews: drop faces inside the slots (display only)
        if m is None:
            return
        keep = ~cutter.contains(m.triangles_center) if len(m.faces) < 400000 else np.ones(len(m.faces), bool)
        m.update_faces(keep); m.remove_unreferenced_vertices()
    face_cut(info.get("draped"))
    if info.get("drape_pieces"):
        face_cut(info["drape_pieces"][0])
    for _, m, _, _ in (mix_preview or []):
        face_cut(m)
    return out


def _course_edges(starts, gap, top, n, rows=1):
    """Woven-style colour for droop: each strand row (course) and the wall it hangs from take the next colour.
    `starts` are cut-safe row boundaries; keep every `rows`-th one at least rows x row-gap apart."""
    picked, last = [], -1e9
    for z in starts:
        if z - last >= rows * gap - 1e-6 and 0 < z < top:
            picked.append(z); last = z
    edges = [0.0] + picked + [top]
    return edges, [0] + [(i + 1) % n for i in range(len(picked))]


def _png_data_url(rgba, max_px=480):
    """Small PNG data URL of the backlit estimate (the studio shows it beside the 3D view)."""
    import base64, io
    from PIL import Image
    im = Image.fromarray(rgba, "RGBA"); im.thumbnail((max_px, max_px), Image.LANCZOS)
    buf = io.BytesIO(); im.save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def make(shape, texture, params=None, nozzle=printer.DEFAULT_NOZZLE, colours=None, options=None, draft=False):
    if shape not in SHAPES:
        raise ValueError(f"unknown shape {shape!r}")
    if texture not in TEXTURES:
        raise ValueError(f"unknown texture {texture!r}")
    if not compatible(shape, texture):
        raise ValueError(f"{TEXTURES[texture]['name']} doesn't fit a {SHAPES[shape].name.lower()}")
    S = SHAPES[shape]; T = TEXTURES[texture]; nz = printer.nozzle(nozzle); options = dict(options or {})
    from . import store
    if options.get("image") and not pathlib.Path(str(options["image"])).exists():
        options["image"] = store.image_path(options["image"])           # an uploaded picture's id
    if options.get("bands"):
        options["bands"] = [dict(b, options={**(b.get("options") or {}),
                                             **({"image": store.image_path((b.get("options") or {}).get("image"))}
                                                if (b.get("options") or {}).get("image") else {})})
                            for b in options["bands"]]
    v = S.resolve(params or {}); warnings = []
    colours = list(colours or []) + DEFAULT_COLOURS[len(colours or []):]
    vstat, vnote = verify.status(texture, nz.size)
    if vstat == "failed":
        warnings.append(f"Last print of this on {nz.size} mm failed: {vnote}")
    elif vstat == "published":
        warnings.append(f"Uses {vnote}; not yet printed on your P2S")
    elif vstat == "untested":
        warnings.append(f"Not printed yet on a {nz.size} mm nozzle — the test plate checks it")
    ranges, per_filament, kinds = [], None, None
    flush_mult = 0.6 if options.get("purge") == "lean" else 1.0
    transitions = []                   # (from colour, to colour) for every AMS change, for the purge estimate

    if T["family"] == "lattice":
        region = S.lattice(v, nz.rod_h)
        rods = lattice.weave(region, nz, texture)
        by_slot = rods.meshes()
        # same colour on two slots -> one part, one filament, no swaps between them
        merged = {}
        for slot, mesh in sorted(by_slot.items()):
            merged.setdefault(colours[slot], []).append(mesh)
        parts = []
        for k, (col, ms) in enumerate(merged.items(), 1):
            parts.append((f"colour {k}", trimesh.util.concatenate(ms), k, col))
        swaps = 0 if len(parts) == 1 else rods.swap_estimate(nz.layer_h)
        cyc = [c for _, _, _, c in parts]
        transitions = [(cyc[i % len(cyc)], cyc[(i + 1) % len(cyc)]) for i in range(swaps)] if len(cyc) > 1 else []
        over = printer.overrides(nz.size, "lattice", slots=len(parts))
        extra = dict(rods=rods.count(), courses=region.n, rod=f"{nz.rod_w:.2f} × {nz.rod_h:.2f} mm",
                     pitch=nz.pitch)
    elif T["family"] == "mix":
        meshes, prev, info = compose.build(S, v, nz, options.get("bands") or compose.PRESETS[compose.DEFAULT_PRESET]["bands"],
                                           draft=draft)
        merged, mprev, mkind = {}, {}, {}
        for slot in sorted(meshes):
            col = colours[slot]
            merged.setdefault(col, []).append(meshes[slot]); mprev.setdefault(col, []).append(prev[slot])
            if info["kinds"].get(slot) == "droop" or mkind.get(col) == "droop":
                mkind[col] = "droop"
            else:
                mkind[col] = "normal"
        parts = [(f"colour {k}", trimesh.util.concatenate(ms), k, col) for k, (col, ms) in enumerate(merged.items(), 1)]
        mix_preview = [(f"colour {k}", trimesh.util.concatenate(mprev[col]), k, col) for k, col in enumerate(merged, 1)]
        seq = [colours[s_] for _, _, s_ in info["layer_slots"]]
        transitions = [(a, b) for a, b in zip(seq, seq[1:]) if a != b]
        swaps = len(transitions)
        over = printer.overrides(nz.size, "droop" if info["droop"] else "fabric", slots=len(parts),
                                 floor_layers=info["floor_layers"])
        if info.get("woven"):                                     # rod spans are short bridges: woven speeds
            lat = printer.overrides(nz.size, "lattice", slots=len(parts))
            over.update({k: lat[k] for k in ("overhang_3_4_speed", "overhang_4_4_speed", "overhang_totally_speed",
                                             "bridge_speed", "wall_generator", "detect_thin_wall", "detect_overhang_wall")})
        ranges = info["ranges"]
        if ranges and ranges[0][0] < 1e-6:                       # bottom band is halftone: its grid starts the print
            over["initial_layer_print_height"] = ranges[0][2]["layer_height"]
        per_filament = printer.filament_settings(nz.size, [mkind[c] for _, _, _, c in parts])
        extra = dict(layers=info["layers"], bands=len(info["bands"]))
        if info["strands"]:
            extra.update(strands=info["strands"], reach=info["reach"])
            if all(mkind[c] == "droop" for _, _, _, c in parts) and len(info["bands"]) > len(
                    [b for b, _ in info["bands"] if b in droop.STYLES]):
                warnings.append("A droop band shares its colour with other bands, so those print at the droop fan too. "
                                "Give the droop band its own AMS slot to keep full cooling elsewhere.")
    elif T["family"] == "flat":
        style = "cmyk" if texture == "cmyk" else "litho"
        meshes, info = flat.build(S, v, nz, style, image=options.get("image"), picture=options.get("picture", "sunset"),
                                  draft=draft)
        cols = list(colours) if (colours and style == "cmyk" and options.get("own_colours")) else (
            flat.CMYK if style == "cmyk" else [colours[0] if colours and colours[0] != DEFAULT_COLOURS[0] else "#FFFFFF"])
        if style == "cmyk":
            parts = [(f"colour {k + 1}", meshes[k], k + 1, cols[k]) for k in sorted(meshes)]
            transitions = [(cols[a], cols[b]) for a, b in info["transitions"]]; swaps = len(transitions)
        else:
            parts = [("colour 1", meshes[3], 1, cols[0])]; swaps = 0
        lhs = f"{info['layer_h']:.2f}"
        over = printer.overrides(nz.size, "fabric", slots=len(parts), floor_layers=4)
        over.update({"layer_height": lhs, "initial_layer_print_height": lhs, "wall_loops": "3",
                     "top_shell_layers": "40", "bottom_shell_layers": "40", "sparse_infill_density": "15%",
                     "detect_thin_wall": "1", "seam_position": "back"})
        extra = dict(layers=info["layers"], pixel=info["pixel"], layer_h=info["layer_h"],
                     backlit=_png_data_url(info["backlit"]))
        warnings.append("Print it face-down on a smooth plate and hang it in front of a light — the picture only "
                        "appears backlit." + (" Load cyan, magenta, yellow and white in AMS slots 1–4." if style == "cmyk" else ""))
    elif T["family"] == "shell":
        mesh, ranges, info = shell.build(S, v, nz, texture, options, draft=draft)
        parts = [("colour 1", mesh, 1, colours[0])]; swaps = 0
        fam = "litho" if texture == "litho" else "fabric"
        over = printer.overrides(nz.size, fam, slots=1, floor_layers=int(round(1.6 / nz.layer_h)))
        if texture == "voronoi":
            over["wall_loops"] = "4"
        extra = {k: info[k] for k in ("cells",) if k in info}
        if info.get("note"):
            warnings.append(info["note"])
        if texture == "fuzzy":
            warnings.append("Fuzzy skin is made by Bambu Studio at slice time: the preview shows the plain wall, "
                            "the texture appears in the sliced preview and the print.")
    elif T["family"] == "spiral":
        sv = dict(v, folds=float(options.get("folds", 7 if texture == "lowpoly" else 24)), turn=float(options.get("turn", 120)))
        mesh, info = spiral.build(S, sv, nz, style=texture, draft=draft)
        parts = [("colour 1", mesh, 1, colours[0])]; swaps = 0
        over = printer.overrides(nz.size, "spiral", slots=1, floor_layers=int(round(1.2 / nz.layer_h)), solid=info["slits"])
        extra = dict(sections=info["sections"])
        warnings.append("Prints in spiral vase mode — one seamless wall, no colour changes. Dual or tri-colour silk "
                        "makes the folds flash between colours.")
    elif T["family"] == "halftone":
        meshes, info = halftone.build(S, v, nz, picture_name=options.get("picture", "flames"),
                                      image_path=options.get("image"), band=int(options.get("band", 1)), draft=draft,
                                      area=options.get("area", "full"), silk=options.get("silk") == "silk")
        merged = {}
        for slot, mesh in sorted(meshes.items()):
            merged.setdefault(colours[slot], []).append(mesh)
        parts = [(f"colour {k}", trimesh.util.concatenate(ms), k, col) for k, (col, ms) in enumerate(merged.items(), 1)]
        swaps = info["swaps"] if len(parts) > 1 else 0
        if swaps:
            a, b = parts[0][3], parts[1][3]
            transitions = [(b, a) if i % 2 else (a, b) for i in range(swaps)]
        over = printer.overrides(nz.size, "halftone", slots=len(parts), floor_layers=info["floor_layers"],
                                 layer_h=info["layer_h"], line_w=info["line_w"])
        extra = dict(ribs=info["ribs"], layers=info["layers"], line=info["line_w"])
        if options.get("silk") == "silk":
            warnings.append("Dual-colour silk: one spool, no AMS changes — the ribs turn the sheen to draw the picture.")
        elif len(parts) == 1:
            warnings.append("Both colours are the same — the picture only shows as rib texture.")
    elif T["family"] == "droop":
        mesh, info = droop.build(S, v, nz, style=texture, density=options.get("density", "medium"),
                                 length=options.get("length", "medium"), preview=True, draft=draft,
                                 aligned=int(options.get("zones", 1) or 1) > 1 and options.get("zone_style", "courses") == "courses")
        parts = [("colour 1", mesh, 1, colours[0])]; swaps = 0
        over = printer.overrides(nz.size, "droop", slots=1, floor_layers=info["floor_layers"], solid=info["solid"])
        per_filament = printer.filament_settings(nz.size, ["fur" if texture == "fur" else "droop"])
        if texture == "fur":                  # hairs are bridges: quick, a touch less flow, full fan, 5 C cooler
            over.update({"bridge_flow": "0.85", "bridge_speed": [str(60)] * len(printer.base_config(nz.size)["bridge_speed"]),
                         "thick_bridges": "0"})
        extra = dict(strands=info["strands"], reach=info["reach"])
        warnings.append("Fur: after printing, cut the hairs at the outer shell, peel it away and brush the fur out "
                        "(a little warm air helps it lie down)." if texture == "fur" else
                        "Strands droop under gravity — the preview shows them hung. The project already runs the fan "
                        "low and the nozzle 5 °C hotter.")
    else:
        mesh, info = fabric.build(S, v, nz.size, stitch=texture, rim_loops=bool(options.get("rim_loops")),
                                  floor=options.get("floor", "solid"), draft=draft)
        parts = [("colour 1", mesh, 1, colours[0])]; swaps = 0
        over = printer.overrides(nz.size, "fabric", slots=1, floor_layers=info["floor_layers"],
                                 wall_speed=info["wall_speed"])
        extra = dict(stitches=info["stitches"], swing_ratio=info["swing_ratio"])

    # ── clean-up: zero-volume flaps (a relief at an unlucky radius) would make a part read as leaking ──
    from .meshops import drop_flaps
    parts = [(n_, drop_flaps(m_), s_, c_) for n_, m_, s_, c_ in parts]
    # ── non-round plans: the wall families built a round piece of the outline's circumference; map it on ──
    outline = S.outline(v) if (T["family"] not in ("lattice", "flat") and hasattr(S, "outline")) else None
    if outline is not None:
        seen = set()
        def _w(m):
            if m is not None and id(m) not in seen:
                seen.add(id(m)); outline.warp(m)
        for _, m, _, _ in parts:
            _w(m)
        inf = locals().get("info") or {}
        _w(inf.get("draped"))
        if inf.get("drape_pieces"):
            _w(inf["drape_pieces"][0])
            for _, r_ in inf["drape_pieces"][1]:
                _w(r_)
        for _, m, _, _ in (locals().get("mix_preview") or []):
            _w(m)
        if shape == "basket" and v.get("handles", 0) > 0:
            if T["family"] == "spiral":
                warnings.append("Vase mode prints one unbroken wall, so this basket has no handle slots.")
            else:
                parts = _cut_handles(parts, v, inf, locals().get("mix_preview"))
    # ── colour zones: up to 4 colours by height (fabric, droop, and woven when coloured by height) ──
    zones = int(options.get("zones", 1) or 1)
    zoned = zones > 1 and (T["family"] in ("fabric", "droop", "shell") or
                           (T["family"] == "lattice" and options.get("colour_by") == "height"))
    if T["family"] == "lattice" and options.get("colour_by") == "height" and zones == 1:
        zoned, zones = True, 1
    if zoned:
        top = max(float(m.bounds[1][2]) for _, m, _, _ in parts)
        grid = nz.rod_h if T["family"] == "lattice" else (fabric.fabric_preset(nz.size, diameter=100)["fabric"]["layer_h"]
                                                           if T["family"] == "fabric" else nz.layer_h)
        style_z = options.get("zone_style", "courses" if T["family"] == "droop" else "bands")
        if T["family"] == "droop" and style_z == "courses" and texture != "fur" and info.get("courses"):
            edges, zone_of = _course_edges(info["courses"], info["course_gap"], top, zones, int(options.get("course_rows", 1) or 1))
        else:
            edges, zone_of = extras.zone_edges(top, zones, grid, "stripes" if style_z == "courses" else style_z)
        if T["family"] == "lattice":
            pieces = [(p_, zi) for p_, zi in zip(extras.split_by_bodies([m for _, m, _, _ in parts], edges), zone_of)]
        else:                                              # split each part on its own (fittings overlap the wall)
            pieces = []
            for _, m, _, _ in parts:
                pieces += list(zip(extras.split_by_height(m, edges, draft=draft), zone_of))
        by_col = {}
        for piece, zi in pieces:
            if piece is not None:
                by_col.setdefault(colours[zi], []).append(piece)
        parts = [(f"colour {k}", trimesh.util.concatenate(ms), k, col) for k, (col, ms) in enumerate(by_col.items(), 1)]
        seq = [colours[z] for z in zone_of]
        transitions = [(a, b) for a, b in zip(seq, seq[1:]) if a != b]; swaps = len(transitions)
        if len({c for _, _, _, c in parts}) > 1:
            over["enable_prime_tower"] = "1"
            if per_filament:
                per_filament = printer.filament_settings(nz.size, ["droop"] * len(parts))
        extra["zones"] = zones
    # ── fittings (after zones, so the fitting takes the bottom zone's colour): collars, pockets, plinths, foot rings, crush ribs ──
    if shape in ("pendant", "puck", "lantern", "cachepot", "candle") and T["family"] != "lattice":
        parts = fittings.apply(parts, shape, v, S.profile(v)[0], 1.0)
    if shape in fittings.NOTES:
        warnings.append(fittings.NOTES[shape])
    zmin = min(float(m.bounds[0][2]) for _, m, _, _ in parts)
    for _, m, _, _ in parts:                      # sit exactly on the bed (tilted curved-bead sections can dip µm)
        if abs(zmin) > 1e-9:
            m.apply_translation([0, 0, -zmin])
    for _, m, _, _ in parts:
        if not m.is_watertight:
            warnings.append("a part is not watertight — report this build")
    all_v = np.vstack([m.vertices for _, m, _, _ in parts])
    lo, hi = all_v.min(0), all_v.max(0)
    vol = sum(m.volume for _, m, _, _ in parts) / 1000.0
    if T["family"] == "droop" and info.get("solid"):          # solid body prints as 2 walls + 15 % infill
        m0 = parts[0][1]; skin = m0.area * 2 * nz.line_w / 1000.0
        vol = min(vol, skin + 0.15 * max(vol - skin, 0.0))
    if T["family"] == "spiral":                               # vase mode lays one wall on a solid body + a floor
        m0 = parts[0][1]
        sec = m0.section(plane_origin=[0, 0, 0.1], plane_normal=[0, 0, 1])
        base = float(sec.to_planar()[0].area) if sec is not None else 0.0
        vol = min(vol, ((m0.area - 2 * base) * nz.line_w * 1.05 + base * 1.2) / 1000.0)
    # purge: each change flushes the colour pair's volume (x the multiplier) + a sliver of prime tower
    purge_g = sum(bambu.flush_volume(a, b) for a, b in transitions) * flush_mult * 1.26 / 1000 + 0.12 * len(transitions)
    stats = dict(size=[round(float(hi[0] - lo[0]), 1), round(float(hi[1] - lo[1]), 1), round(float(hi[2]), 1)],
                 triangles=int(sum(len(m.faces) for _, m, _, _ in parts)), colours=len({c for _, _, _, c in parts}), swaps=int(swaps),
                 grams_est=int(round(float(vol) * 1.26 + purge_g)),
                 grams_part=int(round(float(vol) * 1.26)), grams_purge=int(round(purge_g)), swap_minutes=round(swaps * SWAP_SECONDS / 60),
                 layer_h=extra.pop("layer_h", None) or (halftone.RECIPE[nz.size][0] if T["family"] == "halftone" else nz.layer_h),
                 nozzle=nz.size, verified=vstat, **extra)
    if max(hi[0] - lo[0], hi[1] - lo[1]) > 2 * printer.SAFE_HALF + 1:
        warnings.append("wider than 200 mm — the prime tower may not fit beside it")
    preview = None
    if T["family"] == "mix" and info["strands"]:            # the drape switch only matters when strands exist
        preview = mix_preview
        for _, m, _, _ in preview:
            m.apply_translation([0, 0, -zmin])
    if T["family"] == "droop" and info.get("draped") is not None:
        dm = info["draped"]; dm.apply_translation([0, 0, -zmin])
        if zoned and len({c for _, _, _, c in parts}) > 1 and info.get("drape_pieces"):
            wall_m, hung = info["drape_pieces"]                     # each hung strand keeps its anchor's colour
            dcol = {}
            for piece, zi in zip(extras.split_by_height(wall_m, edges, draft=True), zone_of):
                if piece is not None:
                    dcol.setdefault(colours[zi], []).append(piece)
            for z0, rib in hung:
                zi = zone_of[max(0, min(len(zone_of) - 1, int(np.searchsorted(edges, z0 + 1e-6, side="right") - 1)))]
                dcol.setdefault(colours[zi], []).append(rib)
            for ms in dcol.values():
                for m_ in ms:
                    m_.apply_translation([0, 0, -zmin])
            preview = [(f"colour {k}", trimesh.util.concatenate(ms), k, col) for k, (col, ms) in enumerate(dcol.items(), 1)]
        elif zoned and len({c for _, _, _, c in parts}) > 1:
            pieces = extras.split_by_height(dm, edges, draft=True)
            dcol = {}
            for piece, zi in zip(pieces, zone_of):
                if piece is not None:
                    dcol.setdefault(colours[zi], []).append(piece)
            preview = [(f"colour {k}", trimesh.util.concatenate(ms), k, col) for k, (col, ms) in enumerate(dcol.items(), 1)]
        else:
            preview = [("colour 1", dm, 1, colours[0])]
    # ── lid ──
    lid_parts, assembled = [], []
    style = options.get("lid", "none")
    style = "slip" if style == "lid" else style
    if outline is not None and style in ("slip", "thread", "magnets") and shape in extras.LID_SHAPES:
        if style != "slip":
            warnings.append("Threads and magnets need a round rim — this piece gets a slip lid.")
        ls = extras.lid_outline(parts, options.get("lid_fit", "slip"))
        if ls is None:
            warnings.append("This piece has no opening at the top to fit a lid into.")
        else:
            top = stats["size"][2]
            lc = colours[int(options.get("lid_colour", 1)) - 1] if options.get("lid_colour") else parts[0][3]
            lid_parts = [("Lid", ls["lid"], 1, lc), ("Knob", ls["knob"], 1, lc)]
            a_ = ls["lid"].copy(); a_.apply_transform(trimesh.transformations.rotation_matrix(math.pi, [1, 0, 0]))
            a_.apply_translation([0, 0, top + extras.LID_T - a_.bounds[1][2]])
            kb = ls["knob"].copy(); kb.apply_transform(trimesh.transformations.rotation_matrix(math.pi, [1, 0, 0]))
            kb.apply_translation([0, 0, a_.bounds[1][2] - kb.bounds[0][2] - (extras.LID_T + 0.6)])
            assembled = [("Lid", a_, 1, lc), ("Knob", kb, 1, lc)]
            stats["lid"] = dict(plug=ls["plug_d"], clearance=ls["clearance"], style="slip")
            warnings.extend(ls["notes"])
        style = "none"
    elif outline is not None and style in ("slip", "thread", "magnets"):
        warnings.append("This piece has no lid."); style = "none"
    if style in ("slip", "thread", "magnets") and shape in extras.LID_SHAPES:
        tmp = Build(shape, texture, nz.size, v, T["family"], parts, stats, over)
        op = extras.opening(tmp, S, v)
        if op is None:
            warnings.append("This piece has no opening at the top to fit a lid into.")
        else:
            rim, open_r = op
            if style != "slip" and shape in ("dish", "tray") and T["family"] == "lattice":
                warnings.append("Threads and magnets need a round rim — this dish gets a slip lid."); style = "slip"
            top = stats["size"][2]
            ls = extras.lid_set(style, rim, open_r, top, options.get("lid_fit", "slip"),
                                square=v.get("width") if shape == "tray" else None, corner=v.get("corner", 0.0))
            lc = colours[int(options.get("lid_colour", 1)) - 1] if options.get("lid_colour") else parts[0][3]
            top_part = max(parts, key=lambda p_: p_[1].bounds[1][2])
            for rp in ls["rim"]:                       # thread ring / magnet land: a same-colour part of the piece
                parts.append(("rim", rp, top_part[2], top_part[3]))
            lid_parts = [("Lid", ls["lid"], 1, lc), ("Knob", ls["knob"], 1, lc)]
            a_ = ls["lid"].copy(); a_.apply_transform(trimesh.transformations.rotation_matrix(math.pi, [1, 0, 0]))
            t_plate = 3.6 if style == "magnets" else extras.LID_T     # the flipped plate's underside rests on the rim
            a_.apply_translation([0, 0, top + t_plate - a_.bounds[1][2]])
            kb = ls["knob"].copy(); kb.apply_transform(trimesh.transformations.rotation_matrix(math.pi, [1, 0, 0]))
            kb.apply_translation([0, 0, a_.bounds[1][2] - kb.bounds[0][2] - (extras.LID_T + 0.6)])
            assembled = [("Lid", a_, 1, lc), ("Knob", kb, 1, lc)]
            stats["lid"] = dict(plug=ls["plug_d"], clearance=ls["clearance"], style=style)
            warnings.extend(ls["notes"])
    if options.get("purge_piece") == "coaster" and len({c for _, _, _, c in parts}) > 1:
        coaster = trimesh.creation.cylinder(radius=45.0, height=6.0, sections=96); coaster.apply_translation([0, 0, 3.0])
        lid_parts = list(lid_parts) + [("Purge coaster", coaster, 1, parts[0][3])]
        warnings.append("The coaster soaks up part of the purge (Bambu's flush-into-object). In a test it took about "
                        "3 g per 40 mm block — a modest saving that turns waste into a coaster.")
    return Build(shape, texture, nz.size, v, T["family"], parts, stats, over, warnings, preview,
                 ranges=ranges, per_filament=per_filament, flush_mult=flush_mult, draft=draft,
                 extras=lid_parts, assembled=assembled)
