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

from . import bambu, compose, droop, extras, fabric, halftone, lattice, printer, verify
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
            "mix": dict(family="mix", slots=4, swaps="band", name="Mix",
                        blurb="Stack textures in bands up the wall — fabric, droop, halftone and plain")}

ZONES = [("zones", "Colours", "seg", [("1", "1"), ("2", "2"), ("3", "3"), ("4", "4")], "1"),
         ("zone_style", "Colour layout", "seg", [("bands", "Bands"), ("stripes", "Stripes")], "bands")]
LID = [("lid", "Lid", "seg", [("none", "None"), ("lid", "Lid with knob")], "none")]

# options each family offers in the picker: key -> (label, kind, choices, default)
OPTIONS = {
    "fabric": [("rim_loops", "Loop edge at the rim", "toggle", None, False),
               ("floor", "Floor", "seg", [("solid", "Solid"), ("diamonds", "Diamonds"), ("lens", "Eyes")], "solid")] + ZONES,
    "droop": [("density", "Density", "seg", [("sparse", "Sparse"), ("medium", "Medium"), ("dense", "Dense")], "medium"),
              ("length", "Loop length", "seg", [("short", "Short"), ("medium", "Medium"), ("long", "Long")], "medium")] + ZONES,
    "lattice": [("colour_by", "Colour by", "seg", [("direction", "Rod direction"), ("height", "Height")], "direction")] + ZONES,
    "mix": [("purge", "Purge", "seg", [("standard", "Standard"), ("lean", "Lean — less waste, slight tint")], "standard")],
    "halftone": [("picture", "Picture", "seg", [(k, v["name"]) for k, v in halftone.PICTURES.items()], "flames"),
                 ("band", "Layers per colour", "seg", [("1", "1 — sharpest"), ("2", "2 — half the changes")], "1"),
                 ("purge", "Purge", "seg", [("standard", "Standard"), ("lean", "Lean — less waste, slight tint")], "standard")],
}

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
        return [c for _, _, _, c in self.parts]

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
                objects.append({"name": n, "position": (x + h, min(printer.BED / 2, safe - h)), "parts": [(n, m, idx(c))]})
                x += 2 * h + 8
        else:
            cx = min(printer.BED / 2, safe - half); objects[0]["position"] = (cx, cx)
            if self.extras:                                        # too big to share a plate: their own project
                lid_objects, x = [], 8
                for (n, m, _, c), h in zip(self.extras, extra_halves):
                    lid_objects.append({"name": n, "position": (x + h, printer.BED / 2), "parts": [(n, m, 1)]}); x += 2 * h + 8
                over = dict(self.overrides); over["enable_prime_tower"] = "0"; over["wall_loops"] = "3"
                over["sparse_infill_density"] = "15%"; over["top_shell_layers"] = "4"; over["bottom_shell_layers"] = "4"
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

    def write_stls(self, folder, stem):
        folder = pathlib.Path(folder); folder.mkdir(parents=True, exist_ok=True); out = []
        for name, m, s, _ in self.parts:
            p = folder / f"{stem}_{s}_{name.split()[0].lower()}.stl"; m.export(p); out.append(p)
        return out


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
    elif T["family"] == "halftone":
        meshes, info = halftone.build(S, v, nz, picture_name=options.get("picture", "flames"),
                                      image_path=options.get("image"), band=int(options.get("band", 1)), draft=draft)
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
        if len(parts) == 1:
            warnings.append("Both colours are the same — the picture only shows as rib texture.")
    elif T["family"] == "droop":
        mesh, info = droop.build(S, v, nz, style=texture, density=options.get("density", "medium"),
                                 length=options.get("length", "medium"), preview=True, draft=draft)
        parts = [("colour 1", mesh, 1, colours[0])]; swaps = 0
        over = printer.overrides(nz.size, "droop", slots=1, floor_layers=info["floor_layers"], solid=info["solid"])
        per_filament = printer.filament_settings(nz.size, ["droop"])
        extra = dict(strands=info["strands"], reach=info["reach"])
        warnings.append("Strands droop under gravity — the preview shows them hung. The project already runs the fan "
                        "low and the nozzle 5 °C hotter.")
    else:
        mesh, info = fabric.build(S, v, nz.size, stitch=texture, rim_loops=bool(options.get("rim_loops")),
                                  floor=options.get("floor", "solid"), draft=draft)
        parts = [("colour 1", mesh, 1, colours[0])]; swaps = 0
        over = printer.overrides(nz.size, "fabric", slots=1, floor_layers=info["floor_layers"],
                                 wall_speed=info["wall_speed"])
        extra = dict(stitches=info["stitches"], swing_ratio=info["swing_ratio"])

    # ── colour zones: up to 4 colours by height (fabric, droop, and woven when coloured by height) ──
    zones = int(options.get("zones", 1) or 1)
    zoned = zones > 1 and (T["family"] in ("fabric", "droop") or
                           (T["family"] == "lattice" and options.get("colour_by") == "height"))
    if T["family"] == "lattice" and options.get("colour_by") == "height" and zones == 1:
        zoned, zones = True, 1
    if zoned:
        whole = trimesh.util.concatenate([m for _, m, _, _ in parts])
        top = float(whole.bounds[1][2])
        grid = nz.rod_h if T["family"] == "lattice" else (fabric.fabric_preset(nz.size, diameter=100)["fabric"]["layer_h"]
                                                           if T["family"] == "fabric" else nz.layer_h)
        edges, zone_of = extras.zone_edges(top, zones, grid, options.get("zone_style", "bands"))
        pieces = (extras.split_by_bodies([m for _, m, _, _ in parts], edges) if T["family"] == "lattice"
                  else extras.split_by_height(whole, edges, draft=draft))
        by_col = {}
        for piece, zi in zip(pieces, zone_of):
            if piece is not None:
                by_col.setdefault(colours[zi], []).append(piece)
        parts = [(f"colour {k}", trimesh.util.concatenate(ms), k, col) for k, (col, ms) in enumerate(by_col.items(), 1)]
        seq = [colours[z] for z in zone_of]
        transitions = [(a, b) for a, b in zip(seq, seq[1:]) if a != b]; swaps = len(transitions)
        if len(parts) > 1:
            over["enable_prime_tower"] = "1"
            if per_filament:
                per_filament = printer.filament_settings(nz.size, ["droop"] * len(parts))
        extra["zones"] = zones
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
    # purge: each change flushes the colour pair's volume (x the multiplier) + a sliver of prime tower
    purge_g = sum(bambu.flush_volume(a, b) for a, b in transitions) * flush_mult * 1.26 / 1000 + 0.12 * len(transitions)
    stats = dict(size=[round(float(hi[0] - lo[0]), 1), round(float(hi[1] - lo[1]), 1), round(float(hi[2]), 1)],
                 triangles=int(sum(len(m.faces) for _, m, _, _ in parts)), colours=len(parts), swaps=int(swaps),
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
    if T["family"] == "droop":
        dm = info["draped"]; dm.apply_translation([0, 0, -zmin])
        if zoned and len(parts) > 1:
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
    if options.get("lid") == "lid" and shape in extras.LID_SHAPES:
        tmp = Build(shape, texture, nz.size, v, T["family"], parts, stats, over)
        op = extras.opening(tmp, S, v)
        if op is None:
            warnings.append("This piece has no opening at the top to fit a lid into.")
        else:
            rim, plug = op
            sq = v.get("width") if shape == "tray" else None
            lid_m, knob_m = extras.lid(rim, plug, square=sq, corner=v.get("corner", 0.0))
            lc = colours[int(options.get("lid_colour", 1)) - 1] if options.get("lid_colour") else parts[0][3]
            lid_parts = [("Lid", lid_m, 1, lc), ("Knob", knob_m, 1, lc)]
            top = stats["size"][2]
            a = lid_m.copy(); a.apply_transform(trimesh.transformations.rotation_matrix(math.pi, [1, 0, 0]))
            a.apply_translation([0, 0, top + extras.LID_T - a.bounds[0][2] - extras.LID_T])
            kb = knob_m.copy(); kb.apply_transform(trimesh.transformations.rotation_matrix(math.pi, [1, 0, 0]))
            kb.apply_translation([0, 0, a.bounds[1][2] - kb.bounds[0][2] - (extras.LID_T + 0.6)])
            assembled = [("Lid", a, 1, lc), ("Knob", kb, 1, lc)]
            stats["lid"] = dict(plug=round(2 * plug, 1), clearance=extras.CLEAR)
    return Build(shape, texture, nz.size, v, T["family"], parts, stats, over, warnings, preview,
                 ranges=ranges, per_filament=per_filament, flush_mult=flush_mult, draft=draft,
                 extras=lid_parts, assembled=assembled)
