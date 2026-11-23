"""Bambu Lab P2S, the target printer: per-nozzle machine numbers, the rod bead each nozzle prints, and the
slicer overrides each texture family needs. The resolved Bambu Studio configs live in data/p2s_<nozzle>.json
(built by data/build_profiles.py from Bambu's own P2S + PLA Matte presets)."""
import json
import math
import pathlib
from dataclasses import dataclass

PRINTER = "Bambu Lab P2S"
BED = 256.0                      # mm, square
TOWER = (216.0, 216.0, 30.0)     # prime tower x, y, width — parked back-right, clear of the object
SAFE_HALF = 100.0                # objects are capped at 200 mm so the tower never overlaps them
DATA = pathlib.Path(__file__).parent / "data"
NOZZLES = (0.2, 0.4, 0.6, 0.8)
DEFAULT_NOZZLE = 0.4


@dataclass(frozen=True)
class Nozzle:
    size: float
    layer_h: float
    line_w: float
    rod_lines: int      # extrusion lines per rod (= wall loops)
    rod_layers: int     # print layers per rod course (= colour-swap cadence)
    gap: float          # air between neighbouring rods (each rod bridges this)
    verified: bool      # printed and confirmed on Collin's P2S

    @property
    def rod_w(self):
        return round(self.rod_lines * self.line_w, 3)

    @property
    def rod_h(self):
        return round(self.rod_layers * self.layer_h, 3)

    @property
    def pitch(self):
        return round(self.rod_w + self.gap, 3)


_N = {
    0.2: Nozzle(0.2, 0.10, 0.22, 4, 4, 1.00, False),
    0.4: Nozzle(0.4, 0.20, 0.42, 4, 4, 1.92, True),     # the printed tray: 1.68 x 0.80 beads on a 3.6 pitch
    0.6: Nozzle(0.6, 0.30, 0.62, 3, 4, 2.20, False),
    0.8: Nozzle(0.8, 0.40, 0.82, 3, 4, 2.80, False),
}


def nozzle(size=DEFAULT_NOZZLE, rod_lines=None, rod_layers=None, gap=None) -> Nozzle:
    """The nozzle's standard rod, or with rod_lines / rod_layers / gap a custom one on the same nozzle (never marked
    verified). fine_rod(size) is the half-size rod for small pieces."""
    size = round(float(size), 1)
    if size not in _N:
        raise ValueError(f"no P2S profile for a {size} mm nozzle (have {sorted(_N)})")
    n = _N[size]
    if rod_lines is None and rod_layers is None and gap is None:
        return n
    return Nozzle(n.size, n.layer_h, n.line_w, int(rod_lines or n.rod_lines), int(rod_layers or n.rod_layers),
                  float(n.gap if gap is None else gap), False)


def fine_rod(size=DEFAULT_NOZZLE) -> Nozzle:
    """Half the standard rod in every direction (0.4 nozzle: 0.84 x 0.4 mm on a 1.8 pitch): a weave that still reads on
    a piece with only 10-20 mm between its openings. Two lines by two layers; not print-verified."""
    n = nozzle(size)
    return nozzle(size, rod_lines=max(1, n.rod_lines // 2), rod_layers=max(1, n.rod_layers // 2), gap=round(n.gap / 2, 3))


def base_config(size) -> dict:
    return json.loads((DATA / f"p2s_{nozzle(size).size}.json").read_text())


def _per_extruder(base, key, value):
    cur = base.get(key)
    return [value] * len(cur) if isinstance(cur, list) else value


def overrides(size, family, slots=1, floor_layers=0, wall_speed=None, solid=False, layer_h=None, line_w=None,
              material=None) -> dict:
    """Slicer settings for a texture family on this nozzle. family = 'lattice' | 'fabric' | 'litho' | 'spiral' |
    'halftone' | 'droop'. The speeds here are PLA's; pass material ("petg", or a list, one per colour) and they are
    held to that material's pace (process_for). build.make does this itself; a script that builds its own project
    passes it here."""
    o = _family_overrides(size, family, slots, floor_layers, wall_speed, solid, layer_h, line_w)
    mats = [material] if isinstance(material, str) else list(material or [])
    if any(str(m).strip().lower() not in ("pla", "") for m in mats) and family != "droop":
        o.update(process_for(size, mats, o))
    return o


def _family_overrides(size, family, slots, floor_layers, wall_speed, solid, layer_h, line_w) -> dict:
    n = nozzle(size); base = base_config(size)
    lw = f"{n.line_w:.2f}"
    o = {
        "layer_height": f"{n.layer_h:.2f}", "initial_layer_print_height": f"{n.layer_h:.2f}",
        "line_width": lw, "outer_wall_line_width": lw, "inner_wall_line_width": lw, "initial_layer_line_width": lw,
        "sparse_infill_density": "0%", "top_shell_layers": "0", "seam_position": "aligned",
        "elefant_foot_compensation": "0", "brim_type": "no_brim", "timelapse_type": "0",
        "enable_prime_tower": "1" if slots > 1 else "0",
        "wipe_tower_x": [f"{TOWER[0]:g}"], "wipe_tower_y": [f"{TOWER[1]:g}"], "prime_tower_width": f"{TOWER[2]:g}",
        "printable_area": ["0x0", f"{BED:g}x0", f"{BED:g}x{BED:g}", f"0x{BED:g}"],
    }
    if family == "lattice":
        # the rods ARE the object: n loops side by side make one bead; every span is a short bridge the slicer
        # calls "overhang wall" — stock 10 mm/s doubles the print for nothing
        o.update({"wall_loops": str(n.rod_lines), "bottom_shell_layers": "0", "detect_thin_wall": "1",
                  "wall_generator": "arachne", "detect_overhang_wall": "1"})
        for k, v in {"overhang_3_4_speed": "60", "overhang_4_4_speed": "50", "overhang_totally_speed": "50",
                     "bridge_speed": "50", "outer_wall_speed": "100", "inner_wall_speed": "150",
                     "initial_layer_speed": "35"}.items():
            o[k] = _per_extruder(base, k, v)
    elif family == "litho":
        # solid wall: enough loops to fill 3 mm, fine layers for smooth tones
        o.update({"wall_loops": str(max(6, int(math.ceil(3.2 / n.line_w)))), "bottom_shell_layers": str(max(floor_layers, 4)),
                  "top_shell_layers": "0", "sparse_infill_density": "0%", "detect_thin_wall": "1", "wall_generator": "arachne",
                  "seam_position": "back"})
    elif family == "spiral":
        # one continuous spiral: Bambu's spiral vase mode, 1 wall a touch wider than the nozzle, solid floor
        w = f"{max(n.line_w, round(n.size * 1.25, 2)):.2f}"
        o.update({"spiral_mode": "1", "wall_loops": "1", "bottom_shell_layers": str(max(floor_layers, 4)),
                  "top_shell_layers": "0", "sparse_infill_density": "0%", "outer_wall_line_width": w,
                  "outer_wall_speed": _per_extruder(base, "outer_wall_speed", "60"), "detect_thin_wall": "0",
                  "slice_closing_radius": "0" if solid else base.get("slice_closing_radius", "0.049")})
    elif family == "halftone":
        # one wide line per layer at the nozzle's max layer height (the published 0.4/0.8 recipe)
        w = f"{line_w:.2f}"
        o.update({"layer_height": f"{layer_h:.2f}", "initial_layer_print_height": f"{layer_h:.2f}",
                  "line_width": w, "outer_wall_line_width": w, "inner_wall_line_width": w,
                  "initial_layer_line_width": w, "top_surface_line_width": w, "internal_solid_infill_line_width": w,
                  "wall_loops": "1", "bottom_shell_layers": str(max(floor_layers, 3)), "detect_thin_wall": "1",
                  "wall_generator": "arachne", "spiral_mode": "0"})
    elif family == "droop":
        # a plain 2-loop wall + single-line strands into air. The strands only droop if laid FAST and molten, so the
        # overhang slow-down is off (process level); fan and temperature are per filament (filament_settings)
        o.update({"wall_loops": "2", "bottom_shell_layers": str(max(floor_layers, 3)), "detect_thin_wall": "1",
                  "wall_generator": "arachne", "top_shell_layers": "5" if solid else "0",
                  "sparse_infill_density": "15%" if solid else "0%", "sparse_infill_pattern": "gyroid",
                  "enable_overhang_speed": _per_extruder(base, "enable_overhang_speed", "0")})
    else:
        # printed fabric: a 2-loop shell, solid floor, mid-air zigzag layers — slow outer wall, full fan
        o.update({"wall_loops": "2", "bottom_shell_layers": str(max(floor_layers, 3)), "detect_thin_wall": "0",
                  "spiral_mode": "0"})
        if wall_speed:
            o["outer_wall_speed"] = _per_extruder(base, "outer_wall_speed", str(wall_speed))
    return o


DROOP_FILAMENT = {"fan_max_speed": "20", "fan_min_speed": "10", "overhang_fan_speed": "20",
                  "additional_cooling_fan_speed": "0", "slow_down_for_layer_cooling": "0"}


FUR_FILAMENT = {"fan_max_speed": "100", "fan_min_speed": "100", "overhang_fan_speed": "100",
                "additional_cooling_fan_speed": "70", "slow_down_for_layer_cooling": "1"}


def filament_settings(size, kinds):
    """Per-filament settings, one entry per AMS slot used. kinds: "droop" | "normal" per slot. Droop slots run a
    low fan and +5 C so their strands stay molten long enough to fall; the other slots keep the stock cooling."""
    base = base_config(size)
    first = lambda k: (base[k][0] if isinstance(base.get(k), list) else base.get(k))
    out = {}
    for key in list(DROOP_FILAMENT) + ["nozzle_temperature"]:
        vals = []
        for kind in kinds:
            if key == "nozzle_temperature":
                t = int(first("nozzle_temperature")); vals.append(str(t + 5 if kind == "droop" else t - 5 if kind == "fur" else t))
            elif kind == "fur":
                vals.append(FUR_FILAMENT[key])
            else:
                vals.append(DROOP_FILAMENT[key] if kind == "droop" else str(first(key)))
        out[key] = vals
    return out


# ── materials other than the base PLA Matte ───────────────────────────────────────────────────────────────────────
MATERIALS = {   # short name -> Bambu Studio system filament preset (the 0.4 name; other nozzles add their suffix)
    "petg": "Generic PETG",        # regular PETG of any brand, solid or clear
    "petg-hf": "Bambu PETG HF", "petg-basic": "Bambu PETG Basic",
    "petg-clear": "Bambu PETG Translucent", "petg-translucent": "Bambu PETG Translucent",
}
_FIL_DIRS = (pathlib.Path.home() / "Library/Application Support/BambuStudio/system/BBL/filament",
             pathlib.Path("/Applications/BambuStudio.app/Contents/Resources/profiles/BBL/filament"),
             DATA / "filament")      # last: the presets as shipped with Bambu Studio 2.9, flattened, for a machine without it
_KEEP_BED = ("textured_plate_temp", "hot_plate_temp", "eng_plate_temp")      # the P2S textured plate runs 60 C, always


def _filament_chain(name):
    out = {}
    while name:
        f = next((d / f"{name}.json" for d in _FIL_DIRS if (d / f"{name}.json").exists()), None)
        if f is None:
            raise FileNotFoundError(f"Bambu Studio has no filament preset {name!r}")
        d = json.loads(f.read_text())
        for k, v in d.items():
            out.setdefault(k, v)
        name = d.get("inherits")
    return out


def material_settings(size, materials):
    """Per-filament settings for other materials: one entry per AMS slot, each a MATERIALS key or a Bambu Studio
    system preset family name ("Bambu PETG HF"). Every filament-preset value is taken from Bambu's own P2S preset
    (first extruder variant), except the bed temperatures. -> {key: [value per slot], "_preset": the same, untouched}
    ("_preset" lets the writer flag only what a texture family changes on top, e.g. the droop fan)."""
    n = nozzle(size); base = base_config(size)
    out = {"filament_settings_id": [], "filament_ids": [], "filament_type": []}
    chains, stock = [], []                                    # stock: slots left on the base PLA preset
    for m in materials:
        if str(m).strip().lower() in ("pla", ""):               # this slot stays on the base PLA Matte preset
            chains.append(dict(base, filament_id=(base.get("filament_ids") or ["GFA00"])[0])); stock.append(len(chains) - 1)
            out["filament_settings_id"].append((base.get("filament_settings_id") or [""])[0])
            out["filament_ids"].append((base.get("filament_ids") or ["GFA00"])[0]); out["filament_type"].append("PLA")
            continue
        fam = MATERIALS.get(str(m).strip().lower(), m)
        name = f"{fam} @BBL P2S {n.size} nozzle"
        if not any((d / f"{name}.json").exists() for d in _FIL_DIRS):       # generic presets: one file for 0.4-0.8
            name = f"{fam} @BBL P2S"
        c = _filament_chain(name); chains.append(c)
        out["filament_settings_id"].append(name); out["filament_ids"].append(c.get("filament_id", "GFG99"))
        out["filament_type"].append((c.get("filament_type") or ["PETG"])[0])
    # only what a FILAMENT preset sets. A PLA slot's chain is the whole project config: taking its keys too wrote the
    # process speeds as per-filament lists (wrong length, and they overrode the project's own speeds)
    presets = [c for i, c in enumerate(chains) if i not in stock]
    for key in sorted(set().union(*presets)) if presets else []:
        if key in out or key not in base or not isinstance(base[key], list) or key.startswith(_KEEP_BED) \
                or key in ("compatible_printers", "filament_extruder_variant", "filament_self_index"):
            continue
        vals = []
        for c in chains:
            v = c.get(key, base[key])
            vals.append(str(v[0] if isinstance(v, list) and v else v))
        out[key] = vals
    out["_preset"] = {k: list(v) for k, v in out.items()}
    return out


# ── process speeds per material ───────────────────────────────────────────────────────────────────────────────────
# The process preset (and each family's speed overrides) is Bambu's for PLA. A PETG filament preset changes
# temperature, fan and the flow limit, not the speeds — so PETG ran at PLA speeds pinned at its flow limit: rough walls,
# leathery tops, and a first layer of fine rods laid at 35 mm/s between 600 mm/s travels (two prints, Nov 21-22 2026).
# These are CEILINGS: a family that already runs slower keeps its own number.
PETG_PROCESS = {
    "outer_wall_speed": 60, "inner_wall_speed": 100, "sparse_infill_speed": 100, "internal_solid_infill_speed": 100,
    "top_surface_speed": 60, "gap_infill_speed": 50, "support_speed": 80, "support_interface_speed": 50,
    "bridge_speed": 30, "overhang_2_4_speed": 40, "overhang_3_4_speed": 30, "overhang_4_4_speed": 30,
    "overhang_totally_speed": 30,
    "default_acceleration": 4000, "outer_wall_acceleration": 2000, "top_surface_acceleration": 1000,
    "initial_layer_speed": 20, "initial_layer_infill_speed": 30, "initial_layer_acceleration": 300,
    "initial_layer_travel_acceleration": 1000,
}
PROCESS = {"petg": PETG_PROCESS}                      # by filament type, lower case; PLA is the stock preset


def solid_part(size=DEFAULT_NOZZLE, layer_h=None, walls=3, infill="20%", colours=1, material=None, first_layer=None, **more) -> dict:
    """Overrides for a plain functional part (a bracket, a sleeve, a stand): 3 walls and 20 % gyroid, never a hollow
    shell (a shadowbox printed at 5 % lightning broke); variable-width walls, seam at the back, no brim, no support,
    a prime tower only with two or more colours. material holds the speeds to that material's pace. first_layer
    (mm/s) slows layer one further for small or fine features. Anything in `more` is set on top."""
    n = nozzle(size); base = base_config(size)
    lh = float(layer_h or n.layer_h)
    o = {"layer_height": f"{lh:g}", "initial_layer_print_height": f"{max(lh, float(base['initial_layer_print_height'])):g}",
         "wall_generator": "arachne", "wall_loops": str(int(walls)), "sparse_infill_density": str(infill),
         "sparse_infill_pattern": "gyroid", "top_shell_layers": str(max(5, math.ceil(1.0 / lh))),
         "bottom_shell_layers": str(max(4, math.ceil(0.8 / lh))), "seam_position": "back",
         "elefant_foot_compensation": "0.15", "enable_support": "0", "brim_type": "no_brim", "timelapse_type": "0",
         "enable_prime_tower": "1" if colours > 1 else "0"}
    if colours > 1:                                   # parked front-right, clear of a piece placed left of centre
        o.update({"wipe_tower_x": [f"{BED - 50:g}"], "wipe_tower_y": ["20"], "prime_tower_width": f"{TOWER[2]:g}"})
    o.update({k: (str(v) if not isinstance(v, (list, tuple, dict)) else v) for k, v in more.items()})
    mats = [material] if isinstance(material, str) else list(material or [])
    if any(str(m).strip().lower() not in ("pla", "") for m in mats):
        o.update(process_for(size, mats, o))
    if first_layer:
        o.update(slow_first_layer(size, first_layer, o))
    return o


def slow_first_layer(size, mm_s, over=None) -> dict:
    """Layer one at mm_s (fill at 1.5 x), acceleration 300, moves between pieces at acceleration 1000 and at most
    300 mm/s — for small or fine features on the textured plate. Never raises a value the project already has lower.
    (Bambu Studio has no first-layer travel speed, so the 300 mm/s ceiling on moves holds for the whole print.)"""
    base = base_config(size); over = over or {}; out = {}
    for k, v in {"initial_layer_speed": mm_s, "initial_layer_infill_speed": round(mm_s * 1.5), "initial_layer_acceleration": 300,
                 "initial_layer_travel_acceleration": 1000, "travel_speed": 300}.items():
        cur = over.get(k, base.get(k)); cur0 = float(cur[0] if isinstance(cur, list) else cur)
        out[k] = _per_extruder(base, k, f"{min(cur0, v):g}")
    return out


def process_for(size, filament_types, over=None, skip=()):
    """Process settings for the materials on the plate, as an update for `over` (the project's overrides so far).
    The process is one for the whole plate, so with PLA and PETG together the slower material sets the pace.
    Each value is min(what the project has, the material's ceiling), in the config's own list shape; settings that
    are not plain numbers (percentages), and keys in `skip`, are left alone. PLA alone returns {}."""
    caps = {}
    for t in filament_types:
        for k, v in PROCESS.get(str(t).strip().lower().split("-")[0], {}).items():
            caps[k] = min(v, caps.get(k, v))
    base = base_config(size); over = over or {}; out = {}
    for k, cap in caps.items():
        if k in skip or k not in base:
            continue
        cur = over.get(k, base[k]); vals = list(cur) if isinstance(cur, list) else [cur]
        try:
            new = [f"{min(float(v), cap):g}" for v in vals]
        except (TypeError, ValueError):
            continue
        shape = base[k]
        out[k] = (new if len(new) == len(shape) else [new[0]] * len(shape)) if isinstance(shape, list) else new[0]
    return out
