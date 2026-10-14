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

from . import bambu, compose, droop, fabric, halftone, lattice, printer
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

# options each family offers in the picker: key -> (label, kind, choices, default)
OPTIONS = {
    "fabric": [("rim_loops", "Loop edge at the rim", "toggle", None, False),
               ("floor", "Floor", "seg", [("solid", "Solid"), ("diamonds", "Diamonds"), ("lens", "Eyes")], "solid")],
    "droop": [("density", "Density", "seg", [("sparse", "Sparse"), ("medium", "Medium"), ("dense", "Dense")], "medium"),
              ("length", "Loop length", "seg", [("short", "Short"), ("medium", "Medium"), ("long", "Long")], "medium")],
    "lattice": [],
    "mix": [],
    "halftone": [("picture", "Picture", "seg", [(k, v["name"]) for k, v in halftone.PICTURES.items()], "flames"),
                 ("band", "Layers per colour", "seg", [("1", "1 — sharpest"), ("2", "2 — half the changes")], "1")],
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

    @property
    def colours(self):
        return [c for _, _, _, c in self.parts]

    def title(self):
        return f"{SHAPES[self.shape].name} — {TEXTURES[self.texture]['name']}"

    def write_3mf(self, path):
        half = max(np.abs(m.bounds[:, :2]).max() for _, m, _, _ in self.parts)
        cx = min(printer.BED / 2, printer.TOWER[0] - printer.TOWER[2] / 2 - 8 - half)
        objects = [{"name": self.title(), "position": (cx, cx), "parts": [(n, m, s) for n, m, s, _ in self.parts]}]
        bambu.write_3mf(str(path), objects, title=self.title(), colours=tuple(self.colours),
                        overrides=self.overrides, base=printer.base_config(self.nozzle))
        return pathlib.Path(path)

    def write_stls(self, folder, stem):
        folder = pathlib.Path(folder); folder.mkdir(parents=True, exist_ok=True); out = []
        for name, m, s, _ in self.parts:
            p = folder / f"{stem}_{s}_{name.split()[0].lower()}.stl"; m.export(p); out.append(p)
        return out


def make(shape, texture, params=None, nozzle=printer.DEFAULT_NOZZLE, colours=None, options=None):
    if shape not in SHAPES:
        raise ValueError(f"unknown shape {shape!r}")
    if texture not in TEXTURES:
        raise ValueError(f"unknown texture {texture!r}")
    if not compatible(shape, texture):
        raise ValueError(f"{TEXTURES[texture]['name']} doesn't fit a {SHAPES[shape].name.lower()}")
    S = SHAPES[shape]; T = TEXTURES[texture]; nz = printer.nozzle(nozzle); options = options or {}
    v = S.resolve(params or {}); warnings = []
    colours = list(colours or []) + DEFAULT_COLOURS[len(colours or []):]
    if T["family"] == "halftone" and nz.size in (0.4, 0.8):
        warnings.append(f"{nz.size} mm uses the published halftone recipe; not yet printed on your P2S")
    elif not nz.verified:
        warnings.append(f"{nz.size} mm nozzle settings are computed from the proven 0.4 recipe, not yet print-tested")

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
        over = printer.overrides(nz.size, "lattice", slots=len(parts))
        extra = dict(rods=rods.count(), courses=region.n, rod=f"{nz.rod_w:.2f} × {nz.rod_h:.2f} mm",
                     pitch=nz.pitch)
    elif T["family"] == "mix":
        meshes, prev, info = compose.build(S, v, nz, options.get("bands") or compose.PRESETS[compose.DEFAULT_PRESET]["bands"])
        merged, mprev = {}, {}
        for slot in sorted(meshes):
            merged.setdefault(colours[slot], []).append(meshes[slot]); mprev.setdefault(colours[slot], []).append(prev[slot])
        parts = [(f"colour {k}", trimesh.util.concatenate(ms), k, col) for k, (col, ms) in enumerate(merged.items(), 1)]
        mix_preview = [(f"colour {k}", trimesh.util.concatenate(mprev[col]), k, col) for k, col in enumerate(merged, 1)]
        swaps = info["swaps"] if len(parts) > 1 else 0
        over = printer.overrides(nz.size, "droop" if info["droop"] else "fabric", slots=len(parts),
                                 floor_layers=info["floor_layers"])
        extra = dict(layers=info["layers"], bands=len(info["bands"]))
        if info["strands"]:
            extra.update(strands=info["strands"], reach=info["reach"])
            warnings.append("The mix has droop strands, so the whole print runs at the droop fan (20 %) — fabric bands "
                            "bridge a little softer than on their own.")
    elif T["family"] == "halftone":
        meshes, info = halftone.build(S, v, nz, picture_name=options.get("picture", "flames"),
                                      image_path=options.get("image"), band=int(options.get("band", 1)))
        merged = {}
        for slot, mesh in sorted(meshes.items()):
            merged.setdefault(colours[slot], []).append(mesh)
        parts = [(f"colour {k}", trimesh.util.concatenate(ms), k, col) for k, (col, ms) in enumerate(merged.items(), 1)]
        swaps = info["swaps"] if len(parts) > 1 else 0
        over = printer.overrides(nz.size, "halftone", slots=len(parts), floor_layers=info["floor_layers"],
                                 layer_h=info["layer_h"], line_w=info["line_w"])
        extra = dict(ribs=info["ribs"], layers=info["layers"], line=info["line_w"])
        if len(parts) == 1:
            warnings.append("Both colours are the same — the picture only shows as rib texture.")
    elif T["family"] == "droop":
        mesh, info = droop.build(S, v, nz, style=texture, density=options.get("density", "medium"),
                                 length=options.get("length", "medium"), preview=True)
        parts = [("colour 1", mesh, 1, colours[0])]; swaps = 0
        over = printer.overrides(nz.size, "droop", slots=1, floor_layers=info["floor_layers"], solid=info["solid"])
        extra = dict(strands=info["strands"], reach=info["reach"])
        warnings.append("Strands droop under gravity — the preview shows them before they fall. Keep the fan low; "
                        "the project already does.")
    else:
        mesh, info = fabric.build(S, v, nz.size, stitch=texture, rim_loops=bool(options.get("rim_loops")),
                                  floor=options.get("floor", "solid"))
        parts = [("colour 1", mesh, 1, colours[0])]; swaps = 0
        over = printer.overrides(nz.size, "fabric", slots=1, floor_layers=info["floor_layers"],
                                 wall_speed=info["wall_speed"])
        extra = dict(stitches=info["stitches"], swing_ratio=info["swing_ratio"])

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
    stats = dict(size=[round(float(hi[0] - lo[0]), 1), round(float(hi[1] - lo[1]), 1), round(float(hi[2]), 1)],
                 triangles=int(sum(len(m.faces) for _, m, _, _ in parts)), colours=len(parts), swaps=int(swaps),
                 grams_est=int(round(float(vol) * 1.26 + swaps * SWAP_GRAMS)),
                 grams_part=int(round(float(vol) * 1.26)), grams_purge=int(round(swaps * SWAP_GRAMS)), swap_minutes=round(swaps * SWAP_SECONDS / 60),
                 layer_h=extra.pop("layer_h", None) or (halftone.RECIPE[nz.size][0] if T["family"] == "halftone" else nz.layer_h),
                 nozzle=nz.size, **extra)
    if max(hi[0] - lo[0], hi[1] - lo[1]) > 2 * printer.SAFE_HALF + 1:
        warnings.append("wider than 200 mm — the prime tower may not fit beside it")
    preview = None
    if T["family"] == "mix" and info["strands"]:            # the drape switch only matters when strands exist
        preview = mix_preview
        for _, m, _, _ in preview:
            m.apply_translation([0, 0, -zmin])
    if T["family"] == "droop":
        dm = info["draped"]; dm.apply_translation([0, 0, -zmin])
        preview = [("colour 1", dm, 1, colours[0])]
    return Build(shape, texture, nz.size, v, T["family"], parts, stats, over, warnings, preview)
