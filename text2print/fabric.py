"""The printed-fabric family: a revolved wall whose print layers zigzag in mid-air (fabric_wall.py), with
nozzle-matched stitch presets (fabric_presets.py) and optional floor cut-outs (floors.py).

The swing of every stitch is scaled to the LOCAL radius, so the swing / wavelength ratio — the strength
invariant, print-verified at 0.53-0.73 — holds through a bowl's narrow foot or a vase's neck."""
import math

import numpy as np

from .fabric_presets import fabric_preset
from .fabric_wall import fabric_solid, tri01
from . import floors

RELIEFS = {
    "garland": dict(name="Garland", blurb="Rows of festoon scallops that hang across the wall"),
    "drips":   dict(name="Drips", blurb="Teardrops running down the wall like glue-gun drips"),
    "melt":    dict(name="Melt", blurb="Sagging coil beads with broken arcs, as if the wall softened"),
}

STITCHES = {
    "zigzag": dict(name="Zigzag", blurb="Crisscrossing fins that open into diamonds — light and airy"),
    "domes":  dict(name="Knit", blurb="Rounded stitch domes in offset rows, like stockinette"),
    "wave":   dict(name="Wave", blurb="Mirrored sine strands that open eye-shaped windows"),
}
STITCHES.update(RELIEFS)
FLOORS = {"solid": "Solid", "diamonds": "Diamonds", "lens": "Eyes"}


def _h(i, salt=0.0):
    return (np.sin(np.asarray(i, float) * 12.9898 + salt * 78.233 + 1.7) * 43758.5453) % 1.0


def _ridge(dz, depth, up=0.9, down=None):
    """Raised bead profile across height offset dz (mm, + above the bead centre). The underside ramps over at least
    `depth` mm (<= 45 deg overhang); the top can be steeper — it faces up."""
    down = max(depth * 1.6, 1.2) if down is None else down       # cosine flank: max slope = depth*pi/(2*down) <= 45 deg
    a = np.where(dz >= 0, dz / up, -dz / down)
    return depth * np.where(a < 1, 0.5 + 0.5 * np.cos(np.pi * np.clip(a, 0, 1)), 0.0)


def relief(kind, th, z, R, z0, z1, depth):
    """Outward displacement (mm, >= 0) at angles th for the print layer centred at z, band [z0, z1]."""
    circ = 2 * np.pi * max(R, 1.0); x = th / (2 * np.pi)
    if kind == "garland":
        row_h = 13.0; n = max(4, int(round(circ / 26.0)))
        out = np.zeros_like(th)
        r0 = int(np.floor((z - z0) / row_h)) - 1
        for r in range(r0, r0 + 3):
            base = z0 + r * row_h
            u = (x * n + 0.5 * (r % 2)) % 1.0
            yc = base + row_h * (0.92 - 0.62 * np.sin(np.pi * u))           # attached high, sagging between
            out = np.maximum(out, _ridge(z - yc, depth, up=0.7))
        return out
    if kind == "drips":
        # a glue-gun bead along the top of the band with drips of varied length running down from it
        span = z1 - z0; top = z1 - min(6.0, 0.08 * span)
        out = _ridge(z - top, depth * 1.1, up=0.8) * np.ones_like(th)
        n = max(10, int(round(circ / 6.5)))
        for i in range(n):
            L = span * (0.12 + 0.55 * _h(i, 1) ** 1.4)
            t = (top - z) / L                                                 # 0 at the bead, 1 at the drip's tip
            ramp = max(depth * 1.9, 1.4)                                      # under the bulb: <= 45 deg
            if not -0.02 <= t <= 1 + ramp / L:
                continue
            ang = (i + 0.35 * _h(i, 3)) / n
            bulb = np.clip(t, 0, 1) ** 2.2
            w = (1.3 + 2.4 * bulb) / circ
            d = depth * (0.75 + 0.55 * bulb)
            if t > 1:                                                         # under the bulb: ramp out gently
                d *= max(0.0, 1 - (t - 1) * L / ramp)
            dx = np.abs(((x - ang + 0.5) % 1.0) - 0.5)
            out = np.maximum(out, d * np.sqrt(np.clip(1 - (dx / w) ** 2, 0, 1)))
        return out
    # melt: horizontal beads whose height droops between pins, with gaps
    row_h = 6.5; n = max(5, int(round(circ / 30.0))); out = np.zeros_like(th)
    r0 = int(np.floor((z - z0) / row_h)) - 1
    for r in range(r0, r0 + 3):
        base = z0 + (r + 1) * row_h
        u = x * n + 0.37 * r; seg = np.floor(u); f = u - seg
        sag = 1.8 + 2.4 * _h(seg + 31 * r, 4)
        yc = base - sag * np.sin(np.pi * f)
        keep = _h(seg + 17 * r, 5) > 0.18                                  # broken arcs
        out = np.maximum(out, np.where(keep, _ridge(z - yc, depth * 0.85, up=0.6), 0.0))
    return out


def build(shape, v, nozzle, stitch="zigzag", rim_loops=False, floor="solid", draft=False, mask=None, params=None):
    """-> (mesh, info). shape must support the fabric family (has .profile)."""
    prof, height, rmax = shape.profile(v)
    from . import plugins
    custom = plugins.STITCHES.get(stitch)                    # a stitch written as a plugin: domes' proportions
    base = "domes" if custom else (stitch if stitch in ("zigzag", "domes", "wave") else "zigzag")
    preset = fabric_preset(nozzle, diameter=2 * rmax, stitch=base, rim_loops=rim_loops)
    kw = dict(preset["fabric"]); depth = kw["zigzag_depth"]

    def local(z_frac):
        return max(0.35, prof(z_frac * height) / rmax)

    if stitch in RELIEFS:
        n_around = kw["zigzags_around"]
        def scaled(u, layer_in_band, band_layers, band, z_frac):
            th = 2 * np.pi * (np.asarray(u) - 0.5 * (band % 2)) / n_around
            z = z_frac * height
            return relief(stitch, th, z, prof(z), kw["solid_base_z"], height, depth * local(z_frac))
        kw["zigzag_layers"], kw["straight_layers"] = 1, 0
        kw["zigzags_around"] = max(60, int(round(2 * math.pi * rmax / (6.0 if draft else 4.0))))   # 1 mm samples: features are 10 mm+
        kw["samples_per_zigzag"] = 4; n_around = kw["zigzags_around"]
        kw["stitch"] = scaled
        tm = fabric_solid(prof, height, **kw)
        if floor != "solid":
            tm = _cut_floor(tm, prof, kw, floor)
        info = dict(stitches=0, card=preset["print"], floor_layers=int(round(kw["floor_t"] / kw["layer_h"])),
                    swing_ratio=0.0, wall_speed=int(preset["print"]["outer_wall_speed"].split("mm")[0].strip("<=")))
        return tm, info

    def scaled(u, layer_in_band, band_layers, band, z_frac):
        s = local(z_frac)
        if custom:
            d = np.asarray(plugins.call(custom, np.asarray(u, float), layer_in_band, band_layers, band, z_frac, p=params), float)
            return depth * s * np.clip(np.broadcast_to(d, np.shape(u)), 0.0, 1.0)
        if stitch == "domes":
            env = math.sin(math.pi * (layer_in_band + 0.5) / band_layers)
            return depth * s * env * np.sin(np.pi * np.mod(u, 1.0)) ** 2
        if stitch == "wave":
            return 0.5 * depth * s * np.sin(2 * np.pi * u)
        return depth * s * tri01(u)

    if mask is not None:                                     # the texture only inside (or around) a picture / words
        from . import pictures
        n_ar = kw["zigzags_around"]; h0 = kw["solid_base_z"]
        dark = pictures.darkness(mask, 2 * math.pi * rmax / max(height - h0, 1e-6))
        keep_in = mask.get("mask") != "out"
        plain = scaled

        def scaled(u, layer_in_band, band_layers, band, z_frac):
            d = plain(u, layer_in_band, band_layers, band, z_frac)
            th = (np.asarray(u, float) - 0.5 * (band % 2)) / n_ar             # back to 0..1 around
            vv = (z_frac * height - h0) / max(height - h0, 1e-6)
            m = dark(th, np.full(np.shape(th), vv)) > 0.5
            return np.where(m if keep_in else ~m, d, 0.0)
    kw["stitch"] = scaled
    if draft:
        kw["samples_per_zigzag"] = max(2, kw["samples_per_zigzag"] // 2)
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
