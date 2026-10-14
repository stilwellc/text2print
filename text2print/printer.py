"""Bambu Lab P2S, the target printer: per-nozzle machine numbers, the rod bead each nozzle prints, and the
slicer overrides each texture family needs. The resolved Bambu Studio configs live in data/p2s_<nozzle>.json
(built by data/build_profiles.py from Bambu's own P2S + PLA Matte presets)."""
import json
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


def nozzle(size=DEFAULT_NOZZLE) -> Nozzle:
    size = round(float(size), 1)
    if size not in _N:
        raise ValueError(f"no P2S profile for a {size} mm nozzle (have {sorted(_N)})")
    return _N[size]


def base_config(size) -> dict:
    return json.loads((DATA / f"p2s_{nozzle(size).size}.json").read_text())


def _per_extruder(base, key, value):
    cur = base.get(key)
    return [value] * len(cur) if isinstance(cur, list) else value


def overrides(size, family, slots=1, floor_layers=0, wall_speed=None, solid=False, layer_h=None, line_w=None) -> dict:
    """Slicer settings for a texture family on this nozzle. family = 'lattice' | 'fabric'."""
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
                t = int(first("nozzle_temperature")); vals.append(str(t + 5 if kind == "droop" else t))
            else:
                vals.append(DROOP_FILAMENT[key] if kind == "droop" else str(first(key)))
        out[key] = vals
    return out
