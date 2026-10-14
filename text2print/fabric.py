"""The printed-fabric family: a revolved wall whose print layers zigzag in mid-air (fabric_wall.py), with
nozzle-matched stitch presets (fabric_presets.py) and optional floor cut-outs (floors.py).

The swing of every stitch is scaled to the LOCAL radius, so the swing / wavelength ratio — the strength
invariant, print-verified at 0.53-0.73 — holds through a bowl's narrow foot or a vase's neck."""
import math

import numpy as np

from .fabric_presets import fabric_preset
from .fabric_wall import fabric_solid, tri01
from . import floors

STITCHES = {
    "zigzag": dict(name="Zigzag", blurb="Crisscrossing fins that open into diamonds — light and airy"),
    "domes":  dict(name="Knit", blurb="Rounded stitch domes in offset rows, like stockinette"),
    "wave":   dict(name="Wave", blurb="Mirrored sine strands that open eye-shaped windows"),
}
FLOORS = {"solid": "Solid", "diamonds": "Diamonds", "lens": "Eyes"}


def build(shape, v, nozzle, stitch="zigzag", rim_loops=False, floor="solid"):
    """-> (mesh, info). shape must support the fabric family (has .profile)."""
    prof, height, rmax = shape.profile(v)
    preset = fabric_preset(nozzle, diameter=2 * rmax, stitch=stitch, rim_loops=rim_loops)
    kw = dict(preset["fabric"]); depth = kw["zigzag_depth"]

    def local(z_frac):
        return max(0.35, prof(z_frac * height) / rmax)

    def scaled(u, layer_in_band, band_layers, band, z_frac):
        s = local(z_frac)
        if stitch == "domes":
            env = math.sin(math.pi * (layer_in_band + 0.5) / band_layers)
            return depth * s * env * np.sin(np.pi * np.mod(u, 1.0)) ** 2
        if stitch == "wave":
            return 0.5 * depth * s * np.sin(2 * np.pi * u)
        return depth * s * tri01(u)

    kw["stitch"] = scaled
    tm = fabric_solid(prof, height, **kw)
    if floor != "solid":
        tm = _cut_floor(tm, prof, kw, floor)
    stitches = kw["zigzags_around"]
    narrow = min(prof(z) for z in np.linspace(kw["solid_base_z"], height, 40))
    ratio = depth * (narrow / rmax) / (2 * math.pi * narrow / stitches)
    info = dict(stitches=stitches, card=preset["print"], floor_layers=int(round(kw["floor_t"] / kw["layer_h"])),
                swing_ratio=round(ratio, 2), wall_speed=int(preset["print"]["outer_wall_speed"].split("mm")[0].strip("<=")))
    return tm, info


def _cut_floor(tm, prof, kw, kind):
    r_in = prof(kw["floor_t"]) - kw["shell_t"] - 2.0
    size = 5.0 if kind == "diamonds" else 9.0
    rings, r = [], 8.0
    while r + size / 2 + 3.0 < r_in:
        rings.append((r, max(6, int(2 * math.pi * r / (size + 3.0)))))
        r += size + 3.0
    if not rings:
        return tm
    depth = kw["floor_t"] + 2
    cutters = (floors.diamond_cutters(rings, diag=size, depth=depth) if kind == "diamonds"
               else floors.lens_cutters(rings, length=size, width=size * 0.42, depth=depth))
    return floors.cut_floor(tm, cutters)
