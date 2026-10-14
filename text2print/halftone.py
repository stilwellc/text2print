"""The halftone family: a picture made from two colours that alternate EVERY print layer.

Each layer is one wavy extrusion around the wall. Where the picture wants colour A, A's layers wave outward and
B's layers stay flat behind them; where it wants B, the reverse. From outside you see whichever colour bulges,
and the depth of its wave is the grey level — vertical ribs that read as a halftone image.
(Technique from kowafatcompany's "Fire Flame Vase", inspired by m_editat, medium_things, nozzleboss, wontek.)

Print: one wall, 0 % infill, layers at the nozzle's maximum height (0.7 x nozzle), one wide line per layer
(the 0.8 recipe is 0.56 mm layers / 1.4 mm lines; the 0.4 recipe 0.28 / 1.0). The AMS changes every layer.
Overhang law: a bulging layer sits on a flat one below, so its swing is capped at half a line width."""
import math

import numpy as np
import trimesh

PICTURES = {
    "flames":  dict(name="Flames"),
    "fade":    dict(name="Fade"),
    "dots":    dict(name="Polka dots"),
    "chevron": dict(name="Chevron"),
    "waves":   dict(name="Waves"),
}
RECIPE = {   # nozzle -> (layer height, line width)
    0.2: (0.14, 0.50), 0.4: (0.28, 1.00), 0.6: (0.42, 1.20), 0.8: (0.56, 1.40),
}


def _hash(i):
    return (np.sin(np.asarray(i, float) * 12.9898 + 78.233) * 43758.5453) % 1.0


def picture(name, u, v, path=None):
    """Grey level 0..1 (1 = colour A in front) at u = angle 0..1 around, v = height 0..1."""
    u = np.asarray(u, float) % 1.0; v = np.asarray(v, float)
    if path:
        from PIL import Image
        im = np.asarray(Image.open(path).convert("L"), float) / 255.0
        h, w = im.shape
        return 1.0 - im[np.clip(((1 - v) * (h - 1)).astype(int), 0, h - 1), np.clip((u * (w - 1)).astype(int), 0, w - 1)]
    if name == "fade":
        return np.clip(1.2 - 1.4 * v, 0, 1)
    if name == "dots":
        n = 9; cu, cv = u * n, v * n * 0.9
        row = np.floor(cv); cu = cu + 0.5 * (row % 2)
        d = np.hypot(cu - np.floor(cu) - 0.5, (cv - row - 0.5) * 1.1)
        return (d < 0.30).astype(float)
    if name == "chevron":
        n = 6; x = (u * n) % 1.0
        return (((v * 5 + np.abs(x - 0.5)) % 1.0) < 0.5).astype(float)
    if name == "waves":
        return (np.sin(2 * np.pi * (v * 4 + 0.18 * np.sin(2 * np.pi * u * 3))) > 0).astype(float)
    # flames: tongues rising from the bottom, each with its own height, width and sway
    n = 7; k = np.floor(u * n); x = u * n - k                       # x: 0..1 across a tongue
    h = 0.55 + 0.35 * _hash(k)
    sway = 0.12 * np.sin(2 * np.pi * (v * 1.6 + _hash(k + 3)))
    half = 0.42 * np.clip(1 - v / h, 0, None) ** 0.6 * (1 + 0.25 * np.sin(2 * np.pi * v * 3 + k))
    body = (np.abs(x - 0.5 - sway) < np.where(v < h, half, 0)).astype(float)
    k2 = np.floor(u * n + 0.5); x2 = u * n + 0.5 - k2; h2 = 0.3 + 0.25 * _hash(k2 + 7)   # small tongues between
    half2 = 0.3 * np.clip(1 - v / h2, 0, 1) ** 0.7
    small = (np.abs(x2 - 0.5) < half2).astype(float)
    return np.clip(np.maximum(body, small) + (v < 0.12), 0, 1)


AREAS = {"full": 1.0, "half": 0.5, "third": 1 / 3}


def build(shape, v, nz, picture_name="flames", image_path=None, band=1, draft=False, area="full", silk=False):
    """Economy levers (research §5.5): `band` layers per colour (fewer changes), `area` keeps the picture to the
    lower part of the piece (plain background above, no changes there), `silk` prints one dual-colour silk
    filament — the ribs flip its sheen, the picture shows with zero AMS changes."""
    lh, lw = RECIPE[nz.size]
    prof, height, rmax = shape.profile(v)
    floor_t = max(1.2, 4 * lh)
    n_layers = int(round(height / lh)); n_floor = int(math.ceil(floor_t / lh))
    period = max(2.6 * lw, 3.2)                                   # rib spacing around the wall
    n_ribs = max(24, int(round(2 * math.pi * rmax / period)))
    n_th = n_ribs * (3 if draft else 6)                           # 6 points per rib: the slicer sees the wave
    th = np.linspace(0, 2 * np.pi, n_th, endpoint=False)
    wave = 0.5 - 0.5 * np.cos(n_ribs * th)                        # 0 at the flat ring, 1 at a rib peak
    parts = {0: [], 1: []}
    # floor: a solid disc in colour A
    disc = trimesh.creation.cylinder(radius=prof(floor_t / 2), height=n_floor * lh, sections=n_th)
    disc.apply_translation([0, 0, n_floor * lh / 2]); parts[0].append(disc)
    pic_top = floor_t + (height - floor_t) * AREAS.get(area, 1.0)
    swaps = 0; prev = 0
    for k in range(n_floor, n_layers):
        z0, z1 = k * lh, (k + 1) * lh; zm = (z0 + z1) / 2
        in_pic = zm <= pic_top
        if silk:
            colour = 0
        elif in_pic:
            colour = ((k - n_floor) // band) % 2                  # colour B first above the floor
        else:
            colour = 1                                            # plain background above the picture
        swaps += colour != prev; prev = colour
        R = prof(zm)
        step = max(prof(zm) - prof(zm - lh), 0.0)               # the wall's own outward lean this layer
        amp = max(0.2 * lw, min(0.5 * lw, 0.6 * lw - step))      # overhang law: lean + swing <= 0.6 line
        if in_pic:
            g = picture(picture_name, th / (2 * np.pi), (zm - floor_t) / max(pic_top - floor_t, 1e-6), image_path)
            g = g if (colour == 0 or silk) else 1.0 - g
        else:
            g = np.zeros_like(th)
        outer = R + amp * g * wave
        inner = outer - lw
        parts[colour].append(_ring(th, inner, outer, z0, z1))
    return {c: trimesh.util.concatenate(ms) for c, ms in parts.items() if ms}, dict(
        layers=n_layers, ribs=n_ribs, layer_h=lh, line_w=lw, floor_layers=n_floor, swaps=swaps)


def _ring(th, r_in, r_out, z0, z1):
    """Closed annular prism with per-angle inner/outer radii — watertight, outward normals."""
    n = len(th); c, s = np.cos(th), np.sin(th)
    V = np.vstack([np.column_stack([r_out * c, r_out * s, np.full(n, z)]) for z in (z0, z1)] +
                  [np.column_stack([r_in * c, r_in * s, np.full(n, z)]) for z in (z0, z1)])
    o0, o1, i0, i1 = 0, n, 2 * n, 3 * n
    j = np.arange(n); jn = (j + 1) % n
    F = np.vstack([
        np.column_stack([o0 + j, o0 + jn, o1 + jn]), np.column_stack([o0 + j, o1 + jn, o1 + j]),      # outer
        np.column_stack([i0 + j, i1 + jn, i0 + jn]), np.column_stack([i0 + j, i1 + j, i1 + jn]),      # inner
        np.column_stack([o1 + j, o1 + jn, i1 + jn]), np.column_stack([o1 + j, i1 + jn, i1 + j]),      # top
        np.column_stack([o0 + j, i0 + jn, o0 + jn]), np.column_stack([o0 + j, i0 + j, i0 + jn]),      # bottom
    ])
    m = trimesh.Trimesh(V, F, process=False)
    if m.volume < 0:
        m.invert()
    return m
