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

from . import bambu, colourwork, compose, droop, extras, fabric, fittings, flat, halftone, lattice, printer, shell, spiral, verify
from .meshops import volume as _vol, watertight as _wt
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
            **{k: dict(family="colourwork", swaps="layer", **v) for k, v in colourwork.STYLES.items()},
            **{k: dict(family="spiral", slots=1, swaps="none", **v) for k, v in spiral.STYLES.items()},
            **{k: dict(family="shell", slots=1, swaps="none", **v) for k, v in shell.STYLES.items()},
            "flatlitho": dict(family="flat", slots=1, swaps="none", **flat.STYLES["litho"]),
            "cmyk": dict(family="flat", slots=4, swaps="layer", **flat.STYLES["cmyk"]),
            "mix": dict(family="mix", slots=4, swaps="band", name="Mix",
                        blurb="Stack textures in bands up the wall — woven, fabric, droop, halftone and plain")}

ZONES = [("zones", "Colours", "seg", [("1", "1"), ("2", "2"), ("3", "3"), ("4", "4")], "1"),
         ("zone_style", "Colour layout", "seg", [("bands", "Bands"), ("stripes", "Stripes")], "bands")]
LID = [("lid", "Lid", "seg", [("none", "None"), ("slip", "Slip-on"), ("gift", "Gift box"), ("thread", "Screw"), ("magnets", "Magnets")], "none"),
       ("lid_fit", "Lid fit", "seg", [("snug", "Snug 0.15"), ("slip", "Slip 0.25"), ("loose", "Loose 0.40")], "slip")]

# options each family offers in the picker: key -> (label, kind, choices, default)
OPTIONS = {
    "fabric": [("rim_loops", "Loop edge at the rim", "toggle", None, False),
               ("floor", "Floor", "seg", [("solid", "Solid"), ("diamonds", "Diamonds"), ("lens", "Eyes")], "solid"),
               ("mask", "Texture", "seg", [("off", "Everywhere"), ("in", "Inside a picture"), ("out", "Around a picture")], "off"),
               ("picture", "Picture", "seg", [("text", "Text")], "text")] + ZONES,
    "droop": [("density", "Density", "seg", [("sparse", "Sparse"), ("medium", "Medium"), ("dense", "Dense")], "medium"),
              ("length", "Loop length", "seg", [("short", "Short"), ("medium", "Medium"), ("long", "Long")], "medium"),
              ZONES[0],
              ("zone_style", "Colour layout", "seg", [("courses", "Courses"), ("bands", "Bands"), ("stripes", "Stripes")], "courses"),
              ("course_rows", "Rows per colour", "seg", [("1", "1"), ("2", "2"), ("3", "3"), ("4", "4")], "1")],
    "lattice": [("colour_by", "Colour by", "seg", [("direction", "Rod direction"), ("height", "Height")], "direction"),
                ("course_group", "Courses per colour", "seg", [("1", "1"), ("2", "2"), ("3", "3"), ("4", "4")], "1")] + ZONES,
    "shell": [("cell", "Cell size", "seg", [("small", "Small"), ("medium", "Medium"), ("large", "Large")], "medium"),
              ("noise", "Fuzzy pattern", "seg", [(k, v) for k, v in shell.NOISE.items()], "perlin"),
              ("fuzzy_bands", "Fuzzy where", "seg", [("all", "Everywhere"), ("thirds", "Bands"), ("stripes", "Stripes")], "all"),
              ("picture", "Picture", "seg", [("moon", "Moon"), ("flames", "Flames"), ("waves", "Waves"), ("dots", "Dots")], "moon")]
             + ZONES,
    "flat": [("picture", "Picture", "seg", [("sunset", "Sunset")], "sunset")],
    "spiral": [("folds", "Folds", "seg", [("8", "8"), ("16", "16"), ("24", "24"), ("36", "36")], "24"),
               ("turn", "Twist", "seg", [("0", "None"), ("60", "60°"), ("120", "120°"), ("240", "240°")], "120")],
    "mix": [("purge", "Purge", "seg", [("standard", "Standard"), ("lean", "Lean — less waste, slight tint")], "standard")],
    "colourwork": [("chart_preset", "Chart", "seg", [(k, p_["name"]) for k, p_ in colourwork.PRESETS.items()], colourwork.DEFAULT_PRESET),
                   ("picture", "Picture", "seg", [(k, v["name"]) for k, v in halftone.PICTURES.items()], "flames"),
                   ("stitch_size", "Stitch", "seg", [("fine", "Fine"), ("regular", "Regular"), ("bold", "Bold")], "regular"),
                   ("rim", "Rim", "seg", [("none", "Plain"), ("braid", "Braid"), ("rope", "Rope")], "none"),
                   ("band", "Layers per colour", "seg", [("1", "1 — sharpest"), ("2", "2 — half the changes")], "1"),
                   ("purge_piece", "Purge into", "seg", [("tower", "Prime tower"), ("coaster", "A coaster too")], "tower"),
                   ("purge", "Purge", "seg", [("standard", "Standard"), ("lean", "Lean — less waste, slight tint")], "standard")],
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
    lid_plate: str = "same"                              # "same": lid beside the piece; "own": its own project
    tower: bool = True                                   # prime tower for multi-colour prints

    @property
    def colours(self):
        out = []
        for _, _, _, c in self.parts:
            if c not in out:
                out.append(c)
        return out

    def title(self):
        return f"{SHAPES[self.shape].name} — {TEXTURES[self.texture]['name']}"

    def lid_shares_plate(self):
        """Do the lid, knob (and coaster) fit on the piece's plate? Same rule write_3mf uses."""
        if not self.extras or self.lid_plate == "own":
            return False
        half = max(np.abs(m.bounds[:, :2]).max() for _, m, _, _ in self.parts)
        groups = {}
        for n, m, _, c in self.extras:
            groups.setdefault(n, []).append(m)
        halves = [max(float(np.abs(m.bounds[:, :2]).max()) for m in g) for g in groups.values()]
        return 2 * half + sum(2 * h + 8 for h in halves) + 16 <= printer.BED

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
        groups = {}                                             # a textured lid is one object of several parts
        for n, m, _, c in self.extras:
            groups.setdefault(n, []).append((m, c))
        extra_halves = [max(float(np.abs(m.bounds[:, :2]).max()) for m, _ in g) for g in groups.values()]
        row = 2 * half + sum(2 * h + 8 for h in extra_halves)
        if self.extras and row + 16 <= printer.BED and self.lid_plate != "own":
            x = 8 + half; objects[0]["position"] = (x, printer.BED / 2); x += half + 8
            for (n, g), h in zip(groups.items(), extra_halves):
                # lids, knobs and coasters are solid parts: their own walls, infill and top/bottom shells, whatever
                # the piece uses (a fabric piece runs 0 % infill and no top layers)
                st = dict(SOLID_OBJECT)
                if n == "Purge coaster":
                    st["flush_into_objects"] = "1"
                objects.append({"name": n, "position": (x + h, min(printer.BED / 2, safe - h)),
                                "parts": [(f"{n} {k + 1}" if len(g) > 1 else n, m, idx(c)) for k, (m, c) in enumerate(g)],
                                "settings": st})
                x += 2 * h + 8
        else:
            objects[0]["position"] = self._centre(half)
            if self.extras:                                        # too big to share a plate: their own project
                lcols = list(dict.fromkeys(c for _, _, _, c in self.extras)); lidx = lambda c: lcols.index(c) + 1
                row = sum(2 * h for h in extra_halves) + 8 * (len(extra_halves) - 1)
                lid_objects, x = [], max(2.0, min(8.0, (printer.BED - row) / 2))   # a 250 mm lid still lands on the bed
                first_hy = None
                for (n, g), h in zip(groups.items(), extra_halves):
                    pos = (x + h, printer.BED / 2)
                    if x + 2 * h > printer.BED - 2 and first_hy is not None:
                        # no room left on the row (a long lid): small pieces (the knob) go front-left, under it
                        pos = (8 + h, max(8 + h, printer.BED / 2 - first_hy - 8 - h))
                    lid_objects.append({"name": n, "position": pos,
                                        "parts": [(f"{n} {k + 1}" if len(g) > 1 else n, m, lidx(c)) for k, (m, c) in enumerate(g)]})
                    if first_hy is None:
                        first_hy = max(float(np.abs(m.bounds[:, 1]).max()) for m, _ in g)
                    x += 2 * h + 8
                over = dict(self.overrides); over.update(SOLID_OBJECT)
                over["enable_prime_tower"] = "1" if len(lcols) > 1 and self.tower else "0"
                if len(lcols) > 1:                                 # park the tower front-right, clear of the lids
                    over["wipe_tower_x"] = [f"{printer.BED - printer.TOWER[2] - 20:g}"]; over["wipe_tower_y"] = ["20"]
                bambu.write_3mf(str(pathlib.Path(path).with_name(pathlib.Path(path).stem + "-lid.3mf")), lid_objects,
                                title=self.title() + " — lid", colours=tuple(lcols), overrides=over,
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
        # a long, narrow piece (a 250 x 79 case): centred, it can clear the back-right tower on y alone
        v = np.vstack([m.vertices for _, m, _, _ in self.parts])
        hx, hy = float(np.abs(v[:, 0]).max()), float(np.abs(v[:, 1]).max())
        tx, ty, tw = printer.TOWER
        if hx <= c - 2 and hy <= c - 2 and (c + hy <= ty - tw / 2 - 8 or c + hx <= tx - tw / 2 - 8):
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


def lid_textures():
    """What a lid can look like: match the piece, plain, or any wall/woven look that makes sense on a short cap
    (not droop: strands would point up once the lid is flipped on; not fuzzy/litho/flat)."""
    out = [dict(key="match", name="Match the piece", family="match"), dict(key="plain", name="Plain", family="plain")]
    for k, t in TEXTURES.items():
        if t["family"] in ("lattice", "fabric", "halftone", "colourwork", "spiral") or k == "voronoi":
            out.append(dict(key=k, name=t["name"], family=t["family"]))
    return out


LID_KNOBS = [("knob", "Knob"), ("button", "Flat button"), ("tube", "Tube"), ("none", "None")]
LID_SKIP = ("lid", "lid_fit", "lid_over_w", "lid_over_d", "weave_courses", "lid_colour", "lid_texture", "lid_height", "lid_knob", "lid_colours", "engrave_base",
            "engrave_lid", "zones", "zone_style", "course_rows", "purge_piece", "floor", "rim_loops",
            "purge", "handles")


def _cap_or_plain(lid_parts, assembled, *a):
    """Textured lid (a short cap of the piece itself), or the plain lid if the cap can't be built."""
    warnings = a[-1]
    try:
        cap = _lid_cap(*a[:-2], a[-2])
    except Exception as e:                                   # never lose the lid: fall back to the plain plate
        warnings.append(f"The lid is plain: its texture couldn't be built ({type(e).__name__}).")
        return lid_parts, assembled
    if cap and a[-2].get("lid", {}).get("note"):
        warnings.append(a[-2]["lid"]["note"])
    return cap if cap else (lid_parts, assembled)


def _lid_cap(shape, S, T, texture, v, nz, colours, options, parts, ls, t_plate, style, open_r, top, draft, stats):
    """The lid gets the piece's own treatment: a short cap of the same shape, texture and colours (top face on the
    bed), its rim landing on the piece's rim so the texture carries across; the plain lid's plug (slip, thread) or
    a magnet pedestal is grafted inside, plus a solid boss for the knob. Droop, fuzzy and lithophane pieces get a
    plain cap: strands printed on a lid would point up once it is flipped onto the piece."""
    import manifold3d as m3d
    fam = T["family"]
    cap_tex = texture; cap_opts = {k: x for k, x in options.items() if k not in LID_SKIP}; cap_cols = list(colours)
    top_col = max(parts, key=lambda p_: p_[1].bounds[1][2])[3]
    plain = fam in ("droop", "flat") or texture in ("litho", "fuzzy")
    if fam == "mix":
        b = (options.get("bands") or compose.PRESETS[compose.DEFAULT_PRESET]["bands"])[-1]; t_ = b.get("texture")
        if t_ in TEXTURES and TEXTURES[t_]["family"] in ("fabric", "halftone", "lattice"):
            sl = int(b.get("slot", 0)); sl2 = int(b.get("slot2", 1 if sl == 0 else 0))
            cap_tex, cap_opts = t_, dict(b.get("options") or {})
            cap_cols = [colours[sl], colours[sl2]] if t_ in compose.TWO_SLOT else [colours[sl]]
        else:
            plain = True
    if int(options.get("zones", 1) or 1) > 1:
        cap_cols = [top_col]
    if plain:
        cap_tex, cap_opts, cap_cols = "mix", {"bands": [dict(texture="plain", share=100, slot=0)]}, [top_col]
    if options.get("lid_colour") and len(set(cap_cols)) == 1:
        cap_cols = [colours[int(options["lid_colour"]) - 1]]
    pick = options.get("lid_texture") or "match"                # the Lid section: any look, colours, height
    if pick == "plain":
        cap_tex, cap_opts = "mix", {"bands": [dict(texture="plain", share=100, slot=0)]}
    elif pick != "match" and pick in TEXTURES:
        cap_tex, cap_opts = pick, {}
    if pick != "match":
        cap_cols = [c for c in (options.get("lid_colours") or []) if isinstance(c, str) and c.startswith("#")] or cap_cols
        two = cap_tex != "mix" and TEXTURES[cap_tex].get("slots", 1) >= 2
        if not two:
            cap_cols = cap_cols[:1]
        elif len(cap_cols) < 2:                                 # a woven/halftone lid needs a second colour
            other = [c for c in colours if c != cap_cols[0]]
            cap_cols = cap_cols + (other[:1] or cap_cols[:1])
    elif options.get("lid_colours"):
        lc = list(options["lid_colours"])
        cap_cols = (lc + lc)[:max(1, len(set(cap_cols)))] if len(set(cap_cols)) > 1 else lc[:1]
    lat = TEXTURES[cap_tex]["family"] == "lattice"
    Hs = float(min(14.0, max(8.0, round(0.12 * top))))
    if options.get("lid_height"):
        Hs = float(min(40.0, max(5.0, float(options["lid_height"]))))
    if not getattr(S, "round", False):                          # same outline: tray, basket, catch-all, platter
        cap_shape, cp = shape, dict(v, height=Hs, handles=0)
        if lat and "dish" in v:
            cp.update(dish=0, pillow=0, floor=Hs)
        elif lat:
            cp.update(floor=4)
    else:
        cap_shape = "cup"
        if lat and fam != "lattice":                            # a woven lid on a fabric/halftone/... piece
            prof, h_, _ = S.profile(v)
            cp = dict(diameter=2 * prof(h_), height=Hs, wall=6.0, floor=4)
        elif lat:
            reg = S.lattice(v, nz.rod_h); xs = np.linspace(0, reg.extent + 6, 3000)
            ins = xs[reg.sdf(reg.z(reg.n - 1))(xs, np.zeros_like(xs)) <= 0]
            ro = float(ins.max()); wall = float(min(16.0, max(4.0, ro - ins.min())))
            cp = dict(diameter=2 * ro, height=Hs, wall=wall, floor=4)
        else:
            prof, h_, _ = S.profile(v)
            cp = dict(diameter=2 * prof(h_), height=Hs)
    if not compatible(cap_shape, cap_tex):                    # e.g. Rose window on a square tray
        stats.setdefault("lid", {})["note"] = f"{TEXTURES[cap_tex]['name']} doesn't fit this outline — plain lid."
        cap_tex, cap_opts, cap_cols = "mix", {"bands": [dict(texture="plain", share=100, slot=0)]}, cap_cols[:1]
        lat = False
    if not getattr(S, "round", False) and TEXTURES[cap_tex]["family"] == "lattice" and fam != "lattice":
        cp.setdefault("wall", 9.0); cp.setdefault("floor", 4.0)
        if "dish" in v:
            cp.update(dish=0, pillow=0, floor=Hs)
    if TEXTURES[cap_tex]["family"] == "lattice":
        cap_opts["weave_face"] = "bottom"                       # the lid's top prints on the bed
    if cap_tex != "mix" and TEXTURES[cap_tex].get("slots", 1) >= 3 and len(cap_cols) < 3:
        more = [c for c in list(colours) + DEFAULT_COLOURS if c not in cap_cols]
        cap_cols = cap_cols + more[:3 - len(cap_cols)]
    cap = make(cap_shape, cap_tex, cp, nz.size, cap_cols, cap_opts, draft=draft, _raw=True)
    cparts = [(n_, m_, s_, c_) for n_, m_, s_, c_ in cap.parts]
    # the cap's floor (= the lid's top) thickness: where a vertical probe near the centre leaves the solid
    zs = np.arange(0.05, Hs, 0.1); F = 0.0
    for dx, dy in ((6, 0), (0, 6), (-6, 0), (0, -6), (9, 9), (-9, -9), (9, -9), (-9, 9)):
        pts = np.column_stack([np.full(len(zs), dx), np.full(len(zs), dy), zs])
        inside = np.zeros(len(zs), bool)
        for _, m_, _, _ in cparts:
            inside |= m_.contains(pts)
        out_ = np.where(~inside)[0]
        F = max(F, float(zs[out_[0]]) if len(out_) else Hs)
    F = max(F, 0.8)
    plug, foot = extras.plug_of(ls["lid"], t_plate)
    adds = [plug.translate([0, 0, Hs - t_plate]), extras.prism(foot, F - 0.3, Hs + 0.1)]
    knob_style = options.get("lid_knob", "knob")
    boss_h = max(F, extras.LID_T) + 0.01; cuts = []
    if knob_style != "none":
        adds.append(m3d.Manifold.cylinder(boss_h, extras.KNOB_HOLE / 2 + 3.5, extras.KNOB_HOLE / 2 + 3.5, 48))
        cuts = [m3d.Manifold.cylinder(boss_h + 2, extras.KNOB_HOLE / 2, extras.KNOB_HOLE / 2, 48).translate([0, 0, -1])]
    if style == "magnets" and open_r:                           # pedestal over the land, magnet pockets in its face
        M = extras.MAGNET; clear = ls["clearance"]
        r_in = open_r - M["land"] - clear; r_out = open_r - clear; n_ = max(96, int(2 * math.pi * r_out / 1.2))
        ped = (m3d.Manifold.cylinder(Hs - F + 0.3, r_out, r_out, n_) - m3d.Manifold.cylinder(Hs - F + 1, r_in - 0.01, r_in - 0.01, n_)
               .translate([0, 0, -0.3])).translate([0, 0, F - 0.3])
        adds.append(ped)
        rp = open_r - M["land"] / 2; pd = M["d"] + M["clear_d"]; ph = M["h"] + M["clear_h"]
        cuts += [m3d.Manifold.cylinder(ph + 1, pd / 2, pd / 2, 32).translate([rp, 0, Hs - ph]).rotate([0, 0, 360 * k / M["n"]])
                 for k in range(M["n"])]
    words = (options.get("engrave_lid") or "").strip()
    if words and not lat:                                       # words on the lid's top (its print-bottom face)
        sec = trimesh.util.concatenate([m_ for _, m_, _, _ in cparts]).section(plane_origin=[0, 0, 0.05], plane_normal=[0, 0, 1])
        if sec is not None:
            (x0, y0), (x1, y1) = sec.bounds[0][:2], sec.bounds[1][:2]; w_, h_ = x1 - x0, y1 - y0
            th = min(12.0, 0.2 * min(w_, h_))
            knob_r = 0.0 if options.get("lid_knob", "knob") == "none" else max(9.0, min(16.0, min(w_, h_) / 2 * 0.18)) + 2.5
            off = knob_r + th / 2 if knob_r else 0.0                 # below the knob, seen from above
            cut_w = extras.engrave_cut(words, options.get("engrave_font", "futura"), 0.6 * min(w_, h_), th, mirror="y",
                                       offset=((x0 + x1) / 2, (y0 + y1) / 2 + off))
            if cut_w is not None:
                cuts.append(cut_w)
    grafted = extras.graft(cparts, adds, cuts)
    if lat and len(set(cap_cols)) > 1:                          # woven: the hidden plug follows the rods' colour
        g = [x for x in grafted if x[0] == "graft"]              # course by course, so a layer stays one colour
        if g:
            gm = g[0][1]; edges = list(np.arange(0.0, float(gm.bounds[1][2]) + nz.rod_h, nz.rod_h))
            if edges[-1] < gm.bounds[1][2]:
                edges.append(float(gm.bounds[1][2]) + 0.01)
            rest = [x for x in grafted if x[0] != "graft"]
            for i, piece in enumerate(extras.split_by_height(gm, edges, draft=False)):
                if piece is not None and len(piece.faces):
                    rest.append(("graft", piece, 1 + i % 2, cap_cols[i % 2]))
            grafted = rest
    kc = cap_cols[0] if len(set(cap_cols)) == 1 else (cap_cols[0] if pick != "match" else top_col)
    knob_m = None if knob_style == "none" else (extras.button(ls["knob"]) if knob_style == "button" else
                                                   extras.tube(ls["knob"]) if knob_style == "tube" else ls["knob"])
    lid_parts = [("Lid", m_, s_, c_) for _, m_, s_, c_ in grafted] + ([("Knob", knob_m, 1, kc)] if knob_m is not None else [])
    flip = trimesh.transformations.rotation_matrix(math.pi, [1, 0, 0])
    assembled = []
    for _, m_, s_, c_ in grafted:                               # flipped: plane z = Hs lands on the piece's rim
        a_ = m_.copy(); a_.apply_transform(flip); a_.apply_translation([0, 0, top + Hs]); assembled.append(("Lid", a_, s_, c_))
    if knob_m is not None:
        kb = knob_m.copy(); kb.apply_transform(flip)
        kb.apply_translation([0, 0, top + Hs - kb.bounds[0][2] - (extras.LID_T + 0.6)])
        assembled.append(("Knob", kb, 1, kc))
    stats.setdefault("lid", {}).update(cap=TEXTURES[cap_tex]["name"] if cap_tex != "mix" else "Plain", cap_h=Hs,
                                       knob=knob_style)
    return lid_parts, assembled


GIFT_NECK_MIN = 2.0                 # smooth neck wall (mm): the lid slides on it
GIFT_LID_WALL = 6.0                 # the lid's woven wall, thinned toward 4 when the base wall is thin


def _rrect(hw, hd, r):
    from shapely.geometry import box as _box
    r = max(0.01, min(r, hw - 0.01, hd - 0.01))
    return _box(-hw + r, -hd + r, hw - r, hd - r).buffer(r, resolution=24)


def _gift_box(shape, S, texture, v, nz, colours, options, parts, top, draft, stats, warnings):
    """Gift-box lid, flush (Oct 25 2026): the closed box is one block. The base's weave stops at the seam and a smooth
    neck steps in by the lid's wall + the fit; the lid is a short woven cap of the same outline that slides down over
    the neck, its outside flush with the base and its ceiling resting on the neck's rim. Woven Lidded box only.
    Over an insert (lid_over_w / lid_over_d = the outside of a liner standing up out of the box): no neck — the base
    is woven to its rim, the liner is the neck, and the lid's wall is sized to slide over the liner and still close
    flush; its bottom edge rests on the base's rim.
    -> (base parts, lid parts, assembled lid) or None when the wall is too thin to hold a lid wall and a neck."""
    import manifold3d as m3d
    clear = extras.FITS.get(options.get("lid_fit", "slip"), 0.25)
    W, D = float(v["width"]), float(v["depth"]); corner = S._v(v)["corner"]; wall = float(v["wall"])
    try:
        over = (float(options.get("lid_over_w") or 0), float(options.get("lid_over_d") or 0))
    except (TypeError, ValueError):
        over = (0.0, 0.0)
    over = over if min(over) > 0 else None
    if over:
        lw = min(W - over[0], D - over[1]) / 2 - clear           # flush outside, `clear` a side over the liner
        if lw < 4.0:
            warnings.append(f"The insert is too big for a woven lid wall: {W:g} x {D:g} over {over[0]:g} x {over[1]:g} "
                            f"leaves {lw:.2f} mm (needs 4) — this piece gets a slip lid.")
            return None
        if W - 2 * wall < over[0] + 0.4 or D - 2 * wall < over[1] + 0.4:
            warnings.append(f"The insert ({over[0]:g} x {over[1]:g}) won't drop into the box: inside is "
                            f"{W - 2 * wall:g} x {D - 2 * wall:g} — thin the wall or grow the box.")
        neck = 0.0
    else:
        lw = min(GIFT_LID_WALL, wall - clear - GIFT_NECK_MIN)
        if lw < 4.0:
            warnings.append(f"A gift-box lid needs a wall of at least {4 + clear + GIFT_NECK_MIN:.1f} mm "
                            f"(lid {4:g} + fit {clear} + neck {GIFT_NECK_MIN:g}) — this piece gets a slip lid.")
            return None
        neck = wall - clear - lw
    Hs = float(min(60.0, max(12.0, float(options.get("lid_height") or 30.0))))
    cp = dict(v, height=Hs, wall=lw, floor=2.5)
    copts = {"weave_face": "bottom", **{k: x for k, x in options.items() if k not in LID_SKIP and k not in ("weave_face", "weave_courses")}}
    if options.get("weave_twist") or options.get("weave_ombre"):      # the lid carries on the base's twist and fade
        nb, nl = S.lattice(v, nz.rod_h).n, S.lattice(cp, nz.rod_h).n
        copts["weave_courses"] = (nb + nl - 1, -1, nb + nl)
    cap = make(shape, texture, cp, nz.size, colours, copts, draft=draft, _raw=True)
    cparts = [(n_, m_, s_, c_) for n_, m_, s_, c_ in cap.parts]
    # the lid's ceiling: the top of its (woven) top inside the walls; its real height: the rods' top course
    hx, hy = W / 2 - lw - 2.0, D / 2 - lw - 2.0
    Hc = max(float(m_.bounds[1][2]) for _, m_, _, _ in cparts)
    gx, gy = np.meshgrid(np.linspace(-hx, hx, 41), np.linspace(-hy, hy, 17))
    o = np.column_stack([gx.ravel(), gy.ravel(), np.full(gx.size, Hc + 1.0)])
    hits = trimesh.util.concatenate([m_ for _, m_, _, _ in cparts]).ray.intersects_location(
        o, np.tile([0.0, 0.0, -1.0], (len(o), 1)), multiple_hits=False)[0]
    F = float(hits[:, 2].max()) if len(hits) else 2.5          # rests on the highest rod of the top
    # a hidden skin inside the woven top: the weave still shows outside, but the top is closed (no dust on what the
    # box holds, no looking down the wall's rods), and the gaps show the skin's colour — the top course's colour
    import manifold3d as m3d
    if F > 1.2:
        from shapely.geometry.polygon import orient
        ring = [list(c) for c in np.asarray(orient(_rrect(W / 2 - 0.4, D / 2 - 0.4, max(corner - 0.4, 1.0)), 1.0).exterior.coords)[:-1]]
        skin = m3d.Manifold.extrude(m3d.CrossSection([ring]), F - 0.8).translate([0, 0, 0.4])
        ti = max(range(len(cparts)), key=lambda i: int((cparts[i][1].vertices[:, 2] < 0.5).sum()))   # the top course's colour
        cparts = [(n_, m_, s_, c_) for n_, m_, s_, c_ in extras.graft(cparts, [skin], [], into=ti)]
    lid_parts = [("Lid", m_, s_, c_) for _, m_, s_, c_ in cparts]
    flip = trimesh.transformations.rotation_matrix(math.pi, [1, 0, 0])
    if over:                                                    # the lid's bottom edge sits on the base's rim
        assembled = []
        for _, m_, s_, c_ in cparts:
            a_ = m_.copy(); a_.apply_transform(flip); a_.apply_translation([0, 0, top + Hc]); assembled.append(("Lid", a_, s_, c_))
        cx, cy = (W - 2 * lw - over[0]) / 2, (D - 2 * lw - over[1]) / 2
        stats["lid"] = dict(style="gift", mode="over insert", clearance=round(min(cx, cy), 2), cap="match", cap_h=round(Hc, 1),
                            seam=round(top, 1), lid_wall=round(lw, 2), closed_h=round(top + Hc, 1),
                            ceiling=round(top + Hc - F, 1), over=[over[0], over[1]], knob="none")
        warnings.append(f"Gift-box lid over a {over[0]:g} x {over[1]:g} insert: {lw:.2f} mm woven wall, {cx:.2f} / {cy:.2f} mm a "
                        f"side over it, flush outside; closed {W:g} x {D:g} x {top + Hc:.1f} mm, seam at {top:.1f} mm, "
                        f"lid ceiling {top + Hc - F:.1f} mm up — the insert must stand above the rim and stay under that.")
        return list(parts), lid_parts, assembled
    seam = top + F - Hc                                         # the lid's bottom edge when closed
    if seam < 10:
        warnings.append("The gift-box lid is taller than the box — this piece gets a slip lid."); return None
    base = []
    for n_, m_, s_, c_ in parts:                                # the weave stops at the seam: flat-topped rods
        cut = m_.slice_plane([0, 0, seam], [0, 0, -1], cap=True) if m_.bounds[1][2] > seam else m_
        if cut is not None and len(cut.faces):
            base.append((n_, cut, s_, c_))
    pocket = _rrect(W / 2 - wall, D / 2 - wall, max(corner - wall, 2.0))
    n_out = _rrect(W / 2 - lw - clear, D / 2 - lw - clear, max(corner - lw, 2.0) - clear)
    def ring(poly_o, z0, z1):
        from shapely.geometry.polygon import orient
        sec = lambda q: [list(c) for c in np.asarray(orient(q, 1.0).exterior.coords)[:-1]]
        cs = m3d.CrossSection([sec(poly_o)]) - m3d.CrossSection([sec(pocket)])
        return m3d.Manifold.extrude(cs, z1 - z0).translate([0, 0, z0])
    lead = 0.6                                                  # a small lead-in step so the lid finds the neck
    neck_m = ring(n_out, seam - 1.0, top - lead) + ring(n_out.buffer(-lead, join_style=1), top - lead - 0.01, top)
    ti = max(range(len(base)), key=lambda i: base[i][1].bounds[1][2])
    base = [(("neck" if n_ == "graft" else n_), m_, s_, c_) for n_, m_, s_, c_ in extras.graft(base, [neck_m], [], into=ti)]
    assembled = []
    for _, m_, s_, c_ in cparts:                                # flipped: the ceiling (z = F) lands on the neck's rim
        a_ = m_.copy(); a_.apply_transform(flip); a_.apply_translation([0, 0, top + F]); assembled.append(("Lid", a_, s_, c_))
    stats["lid"] = dict(style="gift", clearance=clear, cap="match", cap_h=round(Hc, 1), seam=round(seam, 1), neck=round(neck, 2),
                        lid_wall=round(lw, 2), closed_h=round(top + F, 1), knob="none")
    warnings.append(f"Gift-box lid: {Hc:.1f} mm deep, slides over a {neck:.2f} mm smooth neck with {clear} mm a side; "
                    f"closed it is {W:g} x {D:g} x {top + F:.1f} mm, flush, seam at {seam:.1f} mm.")
    return base, lid_parts, assembled


def _merge_range(ranges, z0, z1, opts, base_lh):
    """Add settings over [z0, z1] to Bambu layer ranges, splitting and merging existing ones (later wins);
    every range keeps a layer_height (the CLI needs it)."""
    cuts = sorted({z0, z1} | {a for a, _, _ in ranges or []} | {b for _, b, _ in ranges or []})
    out = []
    for a, b in zip(cuts, cuts[1:]):
        if b - a < 1e-6:
            continue
        o = {}
        for ra, rb, ro in ranges or []:
            if ra - 1e-6 <= a and b <= rb + 1e-6:
                o.update(ro)
        if z0 - 1e-6 <= a and b <= z1 + 1e-6:
            o.update(opts)
        if not o:
            continue
        o.setdefault("layer_height", f"{base_lh:.2f}")
        if out and out[-1][2] == o and abs(out[-1][1] - a) < 1e-6:
            out[-1] = (out[-1][0], b, o)
        else:
            out.append((a, b, o))
    return out


def _geom_transitions(parts, over, ranges):
    """Colour changes counted from the geometry, layer by layer, the way Bambu orders them: each layer starts
    with the colour already loaded. Used where parts share layers in ways the family's own count can't see."""
    lh = float(over.get("layer_height", "0.2")); h0 = float(over.get("initial_layer_print_height", lh))
    top = max(float(m.bounds[1][2]) for _, m, _, _ in parts)
    mids, z = [], 0.0; first = True
    while z < top - 1e-6:
        step = h0 if first else lh
        for a, b, opt in ranges or []:
            if a - 1e-6 <= z < b - 1e-6 and "layer_height" in opt:
                step = float(opt["layer_height"])
        mids.append(z + step / 2); z += step; first = False
    mids = np.array(mids)
    present = {}
    for _, m, _, col in parts:
        tz = m.vertices[m.faces][:, :, 2]; lo, hi = tz.min(1), tz.max(1)
        a = np.searchsorted(mids, lo, side="left"); b = np.searchsorted(mids, hi, side="right")
        d = np.zeros(len(mids) + 1, int); np.add.at(d, a, 1); np.add.at(d, b, -1)
        on = np.cumsum(d)[:-1] > 0
        present[col] = present.get(col, np.zeros(len(mids), bool)) | on
    cols = list(present); seq = []
    layers_ = [[c for c in cols if present[c][k]] for k in range(len(mids))]
    for k, here in enumerate(layers_):
        here = list(here)
        if seq and seq[-1] in here:                             # start with the colour already loaded
            here.remove(seq[-1]); here.insert(0, seq[-1])
        nxt = next((L for L in layers_[k + 1:] if L), [])       # ...and end on one the next layer needs
        tail = [c for c in here[1:] if c in nxt]
        if tail and len(here) > 2:
            here.remove(tail[0]); here.append(tail[0])
        seq.extend(here)
    return [(x, y) for x, y in zip(seq, seq[1:]) if x != y]


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


def _weave_courses(S, v, nz, region, options):
    """A woven base under a gift-box lid: its courses are the bottom of the whole closed box, so a twist or an ombre
    runs on into the lid (the lid gets the matching map in _gift_box). Explicit weave_courses wins (the lid's own)."""
    if options.get("weave_courses"):
        off, sg, tot = options["weave_courses"]; return (int(off), int(sg), int(tot))
    if options.get("lid") != "gift" or not (options.get("weave_twist") or options.get("weave_ombre")):
        return None
    cp = _gift_lid_params(S, v, options)
    if cp is None:
        return None
    return (0, 1, region.n + S.lattice(cp, nz.rod_h).n)


def _gift_lid_params(S, v, options):
    """The gift-box lid's cap params (same outline, its own wall) -> dict, or None when no lid wall fits."""
    clear = extras.FITS.get(options.get("lid_fit", "slip"), 0.25)
    W, D, wall = float(v["width"]), float(v["depth"]), float(v["wall"])
    try:
        over = (float(options.get("lid_over_w") or 0), float(options.get("lid_over_d") or 0))
    except (TypeError, ValueError):
        over = (0.0, 0.0)
    lw = (min(W - over[0], D - over[1]) / 2 - clear) if min(over) > 0 else min(GIFT_LID_WALL, wall - clear - GIFT_NECK_MIN)
    if lw < 4.0:
        return None
    Hs = float(min(60.0, max(12.0, float(options.get("lid_height") or 30.0))))
    return dict(v, height=Hs, wall=lw, floor=2.5)


def _ombre_stops(options):
    o = options.get("weave_ombre")
    if not o:
        return None
    stops = [int(x) for x in (o.split(",") if isinstance(o, str) else o)]
    return stops if len(stops) >= 2 else None


def _weave_picture(region, options):
    """Image in the weave: (dark(x, y, z), first course) from the picture library, or None. Low pieces carry it
    across the top courses (seen from above); tall ones around the wall (seen from the side)."""
    key = options.get("weave_picture")
    if not key:
        return None
    from . import pictures
    pic = dict(options, picture=key)
    on = options.get("weave_picture_on") or ("top" if region.height < 0.45 * 2 * region.extent else "wall")
    if on == "top":
        g = np.linspace(-region.extent, region.extent, 400); X, Y = np.meshgrid(g, g, indexing="ij")
        ins = region.sdf(region.z(region.n - 1))(X, Y) <= 0
        if not ins.any():
            return None
        x0, x1 = X[ins].min(), X[ins].max(); y0, y1 = Y[ins].min(), Y[ins].max()
        f = pictures.darkness(pic, (x1 - x0) / max(y1 - y0, 1e-6))
        courses = int(options.get("weave_picture_courses") or 3)
        return (lambda x, y, z: f((x - x0) / (x1 - x0), (y - y0) / (y1 - y0)) > 0.5,
                max(region.floor_courses if region.floor_courses < region.n - courses else 0, region.n - courses))
    H = region.height
    f = pictures.darkness(pic, 2 * math.pi * region.extent / max(H, 1e-6))
    return (lambda x, y, z: f(np.mod(np.arctan2(y, x) / (2 * math.pi), 1.0), np.asarray(z) / H) > 0.5,
            region.floor_courses)


def _png_data_url(rgba, max_px=480):
    """Small PNG data URL of the backlit estimate (the studio shows it beside the 3D view)."""
    import base64, io
    from PIL import Image
    im = Image.fromarray(rgba, "RGBA"); im.thumbnail((max_px, max_px), Image.LANCZOS)
    buf = io.BytesIO(); im.save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def make(shape, texture, params=None, nozzle=printer.DEFAULT_NOZZLE, colours=None, options=None, draft=False, _raw=False):
    from . import plugins
    plugins.load_all()                                          # textures written as plugins (cheap when unchanged)
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
    if _raw:                                                    # internal (lid caps): sizes below a shape's minimum
        v.update({k: float(x) for k, x in (params or {}).items()})
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
        from . import plugins as _pl
        rods = lattice.weave(region, nz, texture, group=int(options.get("course_group", 1) or 1),
                             params=_pl.param_values(T.get("params"), options),
                             twist=float(options.get("weave_twist") or 0.0), ombre=_ombre_stops(options),
                             picture=_weave_picture(region, options), face=options.get("weave_face", "top"),
                             courses=_weave_courses(S, v, nz, region, options),
                             ombre_ends=int(round(float(options.get("weave_ombre_ends") or 0) / nz.rod_h)))
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
        if info.get("recount") and len({c for _, _, _, c in parts}) > 1:   # shaped colour edges: 2 colours a layer
            transitions = _geom_transitions(parts, over, ranges); swaps = len(transitions)
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
                                  draft=draft, options=options)
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
        if info.get("backlit") is not None:                    # wall lithophane: the lit-from-inside view (unrolled)
            extra["backlit"] = _png_data_url(info["backlit"], max_px=720)
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
    elif T["family"] == "colourwork":
        chart = options.get("chart")
        if isinstance(chart, str):
            chart = json.loads(chart)
        if not chart:
            chart = colourwork.PRESETS.get(options.get("chart_preset") or colourwork.DEFAULT_PRESET,
                                           colourwork.PRESETS[colourwork.DEFAULT_PRESET])["bands"]
        meshes, info = colourwork.build(S, v, nz, style=texture, chart=chart, size=options.get("stitch_size", "regular"),
                                        band=int(options.get("band", 1) or 1), rim=options.get("rim", "none"),
                                        rim_slot=options.get("rim_slot"), draft=draft, options=options)
        merged, slot_col = {}, {}
        for slot, mesh in sorted(meshes.items()):
            merged.setdefault(colours[slot], []).append(mesh); slot_col[slot] = colours[slot]
        parts = [(f"colour {k}", trimesh.util.concatenate(ms), k, col) for k, (col, ms) in enumerate(merged.items(), 1)]
        seq = [colours[s_] for s_ in info["slot_seq"]]
        transitions = [(a, b) for a, b in zip(seq, seq[1:]) if a != b]
        swaps = len(transitions)
        over = printer.overrides(nz.size, "halftone", slots=len(parts), floor_layers=info["floor_layers"],
                                 layer_h=info["layer_h"], line_w=info["line_w"])
        extra = dict(stitches=info["cols"], stitch_mm=info["stitch_mm"], layers=info["layers"], line=info["line_w"])
        if swaps > 250:
            warnings.append(f"{swaps} colour changes: long print. 'Layers per colour: 2', plain or stripe bands, or a "
                            "smaller piece cut them.")
    elif T["family"] == "halftone":
        meshes, info = halftone.build(S, v, nz, picture_name=options.get("picture", "flames"),
                                      image_path=options.get("image"), band=int(options.get("band", 1)), draft=draft,
                                      area=options.get("area", "full"), silk=options.get("silk") == "silk", pic=options)
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
                                  floor=options.get("floor", "solid"), draft=draft,
                                  mask=options if options.get("mask") in ("in", "out") else None,
                                  params=__import__("text2print.plugins", fromlist=["x"]).param_values(T.get("params"), options))
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
    # ── paneled silhouettes: the wall families built it round; press the panels in (woven clips to them itself) ──
    pw = S.panel(v) if (T["family"] not in ("lattice", "flat") and hasattr(S, "panel")) else None
    if pw is not None:
        seen_p = set(); inf = locals().get("info") or {}
        for m in [m for _, m, _, _ in parts] + [inf.get("draped")] + [m for _, m, _, _ in (locals().get("mix_preview") or [])]:
            if m is not None and id(m) not in seen_p:
                seen_p.add(id(m)); pw(m)
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
        if len({c for _, _, _, c in parts}) > 1:          # the fitting shares layers with the wall: recount
            transitions = _geom_transitions(parts, over, ranges); swaps = len(transitions)
        fit_m = next((m for n_, m, _, _ in parts if n_ == "fitting"), None)
        if fit_m is not None and T["family"] != "spiral":  # wall families print 0 % infill, no top layers: a plinth
            lh_ = float(over.get("layer_height", nz.layer_h))   # or collar would come out a hollow shell
            ranges = _merge_range(ranges, 0.0, float(fit_m.bounds[1][2]) + lh_,
                                  {"sparse_infill_density": "20%", "top_shell_layers": "4"}, lh_)
    if shape in fittings.NOTES:
        warnings.append(fittings.NOTES[shape])
    zmin = min(float(m.bounds[0][2]) for _, m, _, _ in parts)
    for _, m, _, _ in parts:                      # sit exactly on the bed (tilted curved-bead sections can dip µm)
        if abs(zmin) > 1e-9:
            m.apply_translation([0, 0, -zmin])
    # ── words under the base: debossed into the bottom face, mirrored so they read from below ──
    if (options.get("engrave_base") or "").strip():
        if T["family"] in ("lattice", "flat"):
            warnings.append("Words under the base need a solid floor — a woven floor is all rods, and a tile has no "
                            "base. Not engraved.")
        else:
            whole = trimesh.util.concatenate([m for _, m, _, _ in parts])
            sec = whole.section(plane_origin=[0, 0, 0.05], plane_normal=[0, 0, 1])
            if sec is not None:
                (x0, y0), (x1, y1) = sec.bounds[0][:2], sec.bounds[1][:2]
                w_, h_ = x1 - x0, y1 - y0
                cut = extras.engrave_cut(options["engrave_base"].strip(), options.get("engrave_font", "futura"),
                                         0.62 * min(w_, h_), min(12.0, 0.22 * min(w_, h_)), mirror="x",
                                         offset=((x0 + x1) / 2, (y0 + y1) / 2))
                if cut is not None:
                    parts = extras.graft(parts, [], [cut])
                    stats_note = f"“{options['engrave_base'].strip()}” is debossed {extras.ENGRAVE_DEPTH} mm under the base."
                    warnings.append(stats_note)
    for _, m, _, _ in parts:
        if not _wt(m):
            warnings.append("a part is not watertight — report this build")
    all_v = np.vstack([m.vertices for _, m, _, _ in parts])
    lo, hi = all_v.min(0), all_v.max(0)
    vol = sum(_vol(m) for _, m, _, _ in parts) / 1000.0
    if T["family"] == "droop" and info.get("solid"):          # solid body prints as 2 walls + 15 % infill
        m0 = parts[0][1]; skin = m0.area * 2 * nz.line_w / 1000.0
        vol = min(vol, skin + 0.15 * max(vol - skin, 0.0))
    if T["family"] == "spiral":                               # vase mode lays one wall on a solid body + a floor
        m0 = parts[0][1]; ztop = float(m0.bounds[1][2])
        def cap(z):
            sec = m0.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
            return float(sec.to_planar()[0].area) if sec is not None else 0.0
        base, top_cap = cap(0.1), cap(ztop - 0.1)              # a bowl's top cap is far wider than its base
        vol = min(vol, ((m0.area - base - top_cap) * nz.line_w * 1.05 + base * 1.2) / 1000.0)
    for n_, m_, _, _ in parts:                                # fittings print as shells + 20 % infill, not solid
        if n_ == "fitting" and T["family"] != "spiral":
            skin = m_.area * 3 * nz.line_w / 1000.0; fv = _vol(m_) / 1000.0
            vol -= fv - min(fv, skin + 0.2 * max(fv - skin, 0.0))
    # purge: each change flushes the colour pair's volume (x the multiplier) + a sliver of prime tower
    purge_g = sum(bambu.flush_volume(a, b) for a, b in transitions) * flush_mult * 1.26 / 1000 + 0.12 * len(transitions)
    stats = dict(size=[round(float(hi[0] - lo[0]), 1), round(float(hi[1] - lo[1]), 1), round(float(hi[2]), 1)],
                 triangles=int(sum(len(m.faces) for _, m, _, _ in parts)), colours=len({c for _, _, _, c in parts}), swaps=int(swaps),
                 grams_est=int(round(float(vol) * 1.26 + purge_g)),
                 grams_part=int(round(float(vol) * 1.26)), grams_purge=int(round(purge_g)), swap_minutes=round(swaps * SWAP_SECONDS / 60),
                 layer_h=extra.pop("layer_h", None) or (halftone.RECIPE[nz.size][0] if T["family"] in ("halftone", "colourwork") else nz.layer_h),
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
    woven_rect = T["family"] == "lattice" and shape in ("basket", "catchall", "box")
    if style == "gift":
        got = None
        if shape == "box" and T["family"] == "lattice":
            got = _gift_box(shape, S, texture, v, nz, colours, options, parts, stats["size"][2], draft, stats, warnings)
        else:
            warnings.append("Gift-box lids are made for the woven Lidded box — this piece gets a slip lid.")
        if got:
            parts, lid_parts, assembled = got; style = "none"
        else:                                                   # the fallback keeps the gift box's no-knob look
            style = "slip"; options["lid_knob"] = options.get("lid_knob") or "none"
    if (outline is not None or woven_rect) and style in ("slip", "thread", "magnets") and shape in extras.LID_SHAPES:
        if style != "slip":
            warnings.append("Threads and magnets need a round rim — this piece gets a slip lid.")
        ls = (extras.lid_from_region(S.lattice(v, nz.rod_h), options.get("lid_fit", "slip")) if woven_rect
              else extras.lid_outline(parts, options.get("lid_fit", "slip")))
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
            lid_parts, assembled = _cap_or_plain(lid_parts, assembled, shape, S, T, texture, v, nz, colours, options,
                                                 parts, ls, extras.LID_T, "slip", None, top, draft, stats, warnings)
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
            if ls["rim"]:                               # thread ring / magnet land: in the top colour, carved from others
                ti = max(range(len(parts)), key=lambda i: parts[i][1].bounds[1][2])
                parts = [(("rim" if n_ == "graft" else n_), m_, s_, c_) for n_, m_, s_, c_ in
                         extras.graft(parts, [extras._m3d(r_) for r_ in ls["rim"]], [], into=ti)]
            lid_parts = [("Lid", ls["lid"], 1, lc), ("Knob", ls["knob"], 1, lc)]
            a_ = ls["lid"].copy(); a_.apply_transform(trimesh.transformations.rotation_matrix(math.pi, [1, 0, 0]))
            t_plate = 3.6 if style == "magnets" else extras.LID_T     # the flipped plate's underside rests on the rim
            a_.apply_translation([0, 0, top + t_plate - a_.bounds[1][2]])
            kb = ls["knob"].copy(); kb.apply_transform(trimesh.transformations.rotation_matrix(math.pi, [1, 0, 0]))
            kb.apply_translation([0, 0, a_.bounds[1][2] - kb.bounds[0][2] - (extras.LID_T + 0.6)])
            assembled = [("Lid", a_, 1, lc), ("Knob", kb, 1, lc)]
            stats["lid"] = dict(plug=ls["plug_d"], clearance=ls["clearance"], style=style)
            warnings.extend(ls["notes"])
            lid_parts, assembled = _cap_or_plain(lid_parts, assembled, shape, S, T, texture, v, nz, colours, options,
                                                 parts, ls, t_plate, style, open_r, top, draft, stats, warnings)
    lid_plate = "same"
    from . import timing
    stats["minutes_est"] = timing.estimate(T["family"], stats["grams_part"], stats["swaps"], stats["size"][2],
                                           sum(float(m.area) for _, m, _, _ in parts), nz.size)
    if lid_parts:
        stats["colours"] = len({c for _, _, _, c in parts + lid_parts})   # the lid's own filaments count too
        probe = Build(shape, texture, nz.size, v, T["family"], parts, stats, over, extras=lid_parts)
        want = options.get("lid_plate", "auto")
        lid_alone = _geom_transitions(lid_parts, over, None) if len({c for _, _, _, c in lid_parts}) > 1 else []
        if not probe.lid_shares_plate():
            lid_plate = "own"
        elif len({c for _, _, _, c in parts + lid_parts}) > 1:
            shared = _geom_transitions(parts + lid_parts, over, ranges)
            # Auto: print the lid on its own plate when sharing would cost more changes than a second print
            if want == "own" or (want == "auto" and len(shared) > swaps + len(lid_alone)):
                lid_plate = "own"
            else:
                transitions = shared; swaps = len(transitions)
                stats["swaps"] = swaps; stats["swap_minutes"] = round(swaps * SWAP_SECONDS / 60)
                pg = sum(bambu.flush_volume(a, b) for a, b in transitions) * flush_mult * 1.26 / 1000 + 0.12 * swaps
                stats["grams_purge"] = int(round(pg)); stats["grams_est"] = stats["grams_part"] + stats["grams_purge"]
        elif want == "own":
            lid_plate = "own"
        if "lid" in stats:
            stats["lid"].update(plate=lid_plate, swaps=len(lid_alone) if lid_plate == "own" else 0)
    tower = True
    if options.get("tower") == "off":                       # purge goes to the chute only: no tower, no tower sliver
        tower = False; over["enable_prime_tower"] = "0"
        if stats.get("swaps"):
            stats["grams_purge"] = max(0, stats["grams_purge"] - int(round(0.12 * stats["swaps"])))
            stats["grams_est"] = stats["grams_part"] + stats["grams_purge"]
            warnings.append("No prime tower: each change still purges through the chute, but the first line of a new "
                            "colour can carry a little of the old one. Fine on most pieces — try a small one first.")
    if options.get("purge_piece") == "coaster" and len({c for _, _, _, c in parts}) > 1:
        coaster = trimesh.creation.cylinder(radius=45.0, height=6.0, sections=96); coaster.apply_translation([0, 0, 3.0])
        lid_parts = list(lid_parts) + [("Purge coaster", coaster, 1, parts[0][3])]
        warnings.append("The coaster soaks up part of the purge (Bambu's flush-into-object). In a test it took about "
                        "3 g per 40 mm block — a modest saving that turns waste into a coaster.")
    return Build(shape, texture, nz.size, v, T["family"], parts, stats, over, warnings, preview,
                 ranges=ranges, per_filament=per_filament, flush_mult=flush_mult, draft=draft,
                 extras=lid_parts, assembled=assembled, lid_plate=lid_plate, tower=tower)
