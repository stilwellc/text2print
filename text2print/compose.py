"""Mix: stack wall textures as height bands on one vessel — plain, printed fabric, droop and halftone.

A mix is a list of bands, bottom to top, each {texture, share, slot, slot2?, options}. Every band describes each
of its print layers as an outer contour r(theta) and a colour slot; droop bands add strands. Consecutive layers of
one colour become one staircase solid; where a band meets a band of the SAME colour, the upper one reaches a
quarter layer down and the two are unioned (never coplanar — the slicer never samples that quarter layer).
Layer heights: every band prints at the nozzle's standard layer EXCEPT halftone bands, which keep their own recipe
(max layer height, one wide line) through a Bambu layer range — band edges are snapped so every band is a whole
number of its own layers and the slicer's layers land exactly on the geometry's.

Woven rods can't join a mix: they are the whole object, not a wall."""
import math

import numpy as np
import trimesh

from . import droop, halftone
from .fabric_presets import fabric_preset
from .fabric import RELIEFS, relief
from .fabric_wall import tri01

MIXABLE = ["plain", "fuzzy", "zigzag", "domes", "wave", "garland", "drips", "melt", "halftone",
           "fringe", "swag", "curls", "unraveled"]
NAMES = {"plain": "Plain", "fuzzy": "Fuzzy skin", "zigzag": "Zigzag", "domes": "Knit", "wave": "Wave", "garland": "Garland",
         "drips": "Drips", "melt": "Melt", "halftone": "Halftone",
         "fringe": "Fringe", "swag": "Swag", "curls": "Curls", "unraveled": "Unraveled"}
PRESETS = {
    "candle":  dict(name="Coil band", bands=[dict(texture="plain", share=14, slot=0),
                                             dict(texture="curls", share=66, slot=0),
                                             dict(texture="plain", share=20, slot=0)]),
    "skirt":   dict(name="Fringe skirt", bands=[dict(texture="wave", share=34, slot=1),
                                                dict(texture="fringe", share=48, slot=0, options={"density": "dense"}),
                                                dict(texture="plain", share=18, slot=0)]),
    "flame":   dict(name="Flame foot", bands=[dict(texture="halftone", share=46, slot=0, slot2=1),
                                              dict(texture="plain", share=4, slot=1),
                                              dict(texture="zigzag", share=50, slot=1)]),
    "drip":    dict(name="Drip rim", bands=[dict(texture="plain", share=18, slot=0),
                                            dict(texture="garland", share=44, slot=0),
                                            dict(texture="drips", share=38, slot=1)]),
    "stone":   dict(name="Stone & silk", bands=[dict(texture="fuzzy", share=55, slot=0, options={"noise": "voronoi"}),
                                                dict(texture="plain", share=8, slot=1),
                                                dict(texture="wave", share=37, slot=1)]),
    "knit":    dict(name="Knit & wave", bands=[dict(texture="domes", share=30, slot=0),
                                               dict(texture="plain", share=6, slot=1),
                                               dict(texture="wave", share=64, slot=1)]),
}
DEFAULT_PRESET = "flame"


def _staircase(rings, shell, floor_t=None):
    """rings: [(z, r_outer array)] bottom-up, one per layer boundary pair. Inner wall = outer - shell.
    With floor_t: a solid floor up to floor_t (centre caps). Returns a watertight Trimesh."""
    out = []

    def add(z, r):
        if out and abs(out[-1][0] - z) < 1e-9 and np.allclose(out[-1][1], r):
            return
        if len(out) >= 2 and np.allclose(out[-1][1], r) and np.allclose(out[-2][1], r):
            out[-1] = (z, out[-1][1]); return
        out.append((z, r))
    for z, r in rings:
        add(z, r)
    up = list(out); out.clear()
    for z, r in reversed(rings):
        if floor_t is not None and z < floor_t - 1e-9:
            break
        add(z, np.maximum(r - shell, 0.5))
    if floor_t is not None and abs(out[-1][0] - floor_t) > 1e-9:
        add(floor_t, out[-1][1])
    allr = up + out
    n = len(allr[0][1]); th = np.linspace(0, 2 * np.pi, n, endpoint=False)
    c, s = np.cos(th), np.sin(th)
    V = np.vstack([np.column_stack([r * c, r * s, np.full(n, z)]) for z, r in allr])
    m = len(allr); j = np.arange(n); jn = (j + 1) % n; F = []
    for i in range(m - 1):
        a, b = i * n, (i + 1) * n
        F += [np.column_stack([a + j, a + jn, b + j]), np.column_stack([a + jn, b + jn, b + j])]
    if floor_t is None:                                        # close: inner bottom ring -> outer bottom ring
        a, b = (m - 1) * n, 0
        F += [np.column_stack([a + j, a + jn, b + j]), np.column_stack([a + jn, b + jn, b + j])]
    else:
        cb, ct = len(V), len(V) + 1
        V = np.vstack([V, [[0, 0, allr[0][0]], [0, 0, floor_t]]])
        F += [np.column_stack([jn, j, np.full(n, cb)]),
              np.column_stack([(m - 1) * n + j, (m - 1) * n + jn, np.full(n, ct)])]
    mesh = trimesh.Trimesh(V, np.vstack(F), process=True)
    trimesh.repair.fix_normals(mesh)
    if mesh.volume < 0:
        mesh.invert()
    return mesh


def _manifold(meshes):
    import manifold3d as m3d
    ms = [m3d.Manifold(m3d.Mesh(vert_properties=np.asarray(t.vertices, np.float32),
                                tri_verts=np.asarray(t.faces, np.int32))) for t in meshes]
    out = m3d.Manifold.batch_boolean(ms, m3d.OpType.Add).to_mesh()
    mesh = trimesh.Trimesh(np.asarray(out.vert_properties)[:, :3], np.asarray(out.tri_verts), process=True)
    parts = mesh.split(only_watertight=False)
    solid = [b for b in parts if abs(b.volume) > 0.5]          # drop zero-volume flaps from grazing cuts
    if len(solid) != len(parts):
        mesh = trimesh.util.concatenate(solid)
    if mesh.volume < 0:
        mesh.invert()
    return mesh


def _bodies(mesh):
    return len(mesh.split(only_watertight=False))


def normalise(bands):
    bands = [dict(b) for b in bands if b.get("texture") in MIXABLE]
    if not bands:
        bands = [dict(b) for b in PRESETS[DEFAULT_PRESET]["bands"]]
    tot = sum(max(float(b.get("share", 1)), 1.0) for b in bands)
    for b in bands:
        b["share"] = max(float(b.get("share", 1)), 1.0) / tot
        b["slot"] = int(b.get("slot", 0)); b["slot2"] = int(b.get("slot2", 1 if b["slot"] == 0 else 0))
        b["options"] = dict(b.get("options") or {})
    return bands


def build(shape, v, nz, bands, draft=False):
    prof, height, rmax = shape.profile(v)
    bands = normalise(bands)
    base_lh = nz.layer_h
    ht_lh, ht_lw = halftone.RECIPE[nz.size]
    fp = {st: fabric_preset(nz.size, diameter=2 * rmax, stitch=st)["fabric"] for st in ("zigzag", "domes", "wave")}
    shell = fp["zigzag"]["shell_t"]; floor_t = fp["zigzag"]["floor_t"]

    # band edges: each band a whole number of its own layers; the floor belongs to band 0
    lhs = [ht_lh if b["texture"] == "halftone" else base_lh for b in bands]
    n_floor = int(math.ceil(floor_t / lhs[0])); floor_z = n_floor * lhs[0]
    zs = [0.0]; acc = 0.0
    for i, b in enumerate(bands):
        acc += b["share"]; want = acc * height - zs[-1]
        n = max(int(round(want / lhs[i])), (n_floor + 3) if i == 0 else 3)
        zs.append(zs[-1] + n * lhs[i])
    total_h = zs[-1]

    def n_theta(t):
        circ = 2 * math.pi * rmax
        if t in fp:
            n = fp[t]["zigzags_around"] * fp[t]["samples_per_zigzag"]
        elif t in RELIEFS:
            n = int(circ / 0.6)
        elif t == "halftone":
            n = _ribs(rmax, ht_lw) * 6
        else:
            n = max(180, int(circ / 1.2))
        return max(120, n // (3 if draft else 1))

    layers = []          # dicts: z0, z1, slot, r (array) or None (smooth), band, lh
    ranges, droop_bands = [], []
    for bi, b in enumerate(bands):
        t = b["texture"]; lh = lhs[bi]; za, zb = zs[bi], zs[bi + 1]; n = n_theta(t)
        th = np.linspace(0, 2 * np.pi, n, endpoint=False)
        if t == "fuzzy":                                           # slicer-made texture through a layer range
            ranges.append((za, zb, {"layer_height": f"{lh:.2f}", "fuzzy_skin": "external",
                                    "fuzzy_skin_noise_type": b["options"].get("noise", "perlin"),
                                    "fuzzy_skin_thickness": "0.4", "fuzzy_skin_point_distance": "0.6"}))
        if t == "halftone":
            # only the layer height: line widths in a range make Bambu 2.8 drop layers of multi-part objects
            ranges.append((za, zb, {"layer_height": f"{ht_lh:.2f}"}))
        if t in droop.STYLES:
            droop_bands.append((b, za, zb))
        k = 0
        while za + (k + 1) * lh <= zb + 1e-6:
            z0, z1 = za + k * lh, za + (k + 1) * lh; zm = (z0 + z1) / 2; R = prof(zm)
            floor_layer = z1 <= floor_z + 1e-6
            entry = dict(z0=z0, z1=z1, slot=b["slot"], band=bi, lh=lh, n=n, r=None)
            if floor_layer or t in ("plain", "fuzzy") or t in droop.STYLES:
                pass                                                   # smooth wall
            elif t in fp:
                f = fp[t]; cyc = f["zigzag_layers"] + f["straight_layers"]; p = k
                if p % cyc < f["zigzag_layers"]:
                    band = p // cyc; u = f["zigzags_around"] * th / (2 * np.pi) + 0.5 * (band % 2)
                    d = f["zigzag_depth"] * max(0.35, R / rmax)
                    stand = 0.02 * (1 + band % 2) + 0.001 * (p % cyc)
                    if t == "domes":
                        env = math.sin(math.pi * ((p % cyc) + 0.5) / f["zigzag_layers"])
                        disp = d * env * np.sin(np.pi * np.mod(u, 1.0)) ** 2
                    elif t == "wave":
                        disp = 0.5 * d * np.sin(2 * np.pi * u)
                    else:
                        disp = d * tri01(u)
                    entry["r"] = R + stand + disp
                else:
                    entry["r"] = np.full(n, R)
            elif t in RELIEFS:
                entry["r"] = R + 0.02 * (k % 2) + relief(t, th, zm, R, za, zb, fp["zigzag"]["zigzag_depth"] * max(0.35, R / rmax))
            elif t == "halftone":
                colour = k % 2; ribs = _ribs(rmax, ht_lw)
                g = halftone.picture(b["options"].get("picture", "flames"), th / (2 * np.pi), (zm - za) / max(zb - za, 1e-6),
                                     b["options"].get("image"))
                g = g if colour == 0 else 1 - g
                step = max(prof(zm) - prof(zm - lh), 0.0)
                amp = max(0.2 * ht_lw, min(0.5 * ht_lw, 0.6 * ht_lw - step))
                entry["r"] = R + amp * g * (0.5 - 0.5 * np.cos(ribs * th))
                entry["slot"] = b["slot"] if colour == 0 else b["slot2"]
            layers.append(entry); k += 1

    # runs: consecutive layers of one band and one colour
    runs = []; i = 0
    while i < len(layers):
        j = i
        while j + 1 < len(layers) and layers[j + 1]["slot"] == layers[i]["slot"] and layers[j + 1]["band"] == layers[i]["band"]:
            j += 1
        runs.append((i, j)); i = j + 1
    solids = {}
    for a, b_ in runs:
        L0 = layers[a]; slot = L0["slot"]; n = L0["n"]
        bi = L0["band"]; sh = ht_lw if bands[bi]["texture"] == "halftone" else shell
        rings = []
        reach_down = a > 0 and layers[a - 1]["slot"] == slot
        for kk in range(a, b_ + 1):
            L = layers[kk]; z0 = L["z0"] - (0.25 * layers[a - 1]["lh"] if kk == a and reach_down else 0.0)
            if L["r"] is None:                                         # smooth: one ring per layer boundary
                rings.append((z0, np.full(n, prof(max(z0, 0.0)))))
                if kk == b_:
                    rings.append((L["z1"], np.full(n, prof(L["z1"]))))
            else:
                rings += [(z0, L["r"]), (L["z1"], L["r"])]
        solids.setdefault(slot, []).append(_staircase(rings, sh, floor_z if a == 0 else None))

    # droop strands, in their band's colour, on that band's layer grid
    flat, hung = {}, {}; reach = 0.0
    for b, za, zb in droop_bands:
        st = b["texture"]; o = b["options"]
        q = lambda z, za=za: za + (math.floor((z - za) / base_lh) + 0.25) * base_lh
        spots = droop._rows(st, prof, total_h, nz, droop.DENSITY.get(o.get("density", "medium"), 1.0),
                            droop.LENGTH.get(o.get("length", "medium"), 1.0), z_range=(za, zb))
        spots = droop._never_touch(spots, prof, q)
        reach = max([reach] + [bu for _, _, bu, _, _, _, _ in spots])
        ribbons = [droop._ribbon(t_, ch, bu, q(z), hh, w, prof, shell * 0.55, droop._SPEC[st]["power"], le)
                   for t_, ch, bu, z, hh, le, w in spots]
        flat.setdefault(b["slot"], []).extend(ribbons)
        hung.setdefault(b["slot"], []).append(droop.drape(trimesh.Trimesh(), spots, prof, q, ribbons, st))

    parts, preview = {}, {}
    for slot, ms in solids.items():
        strands = flat.get(slot, [])
        if draft:
            walls = trimesh.util.concatenate(ms)
            parts[slot] = trimesh.util.concatenate([walls] + strands)
        else:
            walls = _manifold(ms) if len(ms) > 1 else ms[0]
            parts[slot] = _manifold([walls] + strands) if strands else walls
            if strands and _bodies(parts[slot]) > _bodies(walls):
                raise ValueError("a droop strand isn't attached to the wall")
        preview[slot] = trimesh.util.concatenate([walls] + hung.get(slot, []))

    seq = [L["slot"] for L in layers]
    swaps = sum(1 for x, y in zip(seq, seq[1:]) if x != y)
    kinds = {}
    for b in bands:
        for s_ in ([b["slot"], b["slot2"]] if b["texture"] == "halftone" else [b["slot"]]):
            if b["texture"] in droop.STYLES:
                kinds[s_] = "droop"
            else:
                kinds.setdefault(s_, "normal")
    info = dict(layers=len(layers), bands=[(b["texture"], round(zs[i + 1] - zs[i], 2)) for i, b in enumerate(bands)],
                swaps=swaps, floor_layers=n_floor, droop=bool(droop_bands), height=round(total_h, 2),
                strands=sum(len(x) for x in flat.values()), reach=round(reach, 1), ranges=ranges, kinds=kinds,
                layer_slots=[(round(L["z0"], 4), round(L["z1"], 4), L["slot"]) for L in layers])
    return parts, preview, info


def _ribs(rmax, lw):
    return max(24, int(round(2 * math.pi * rmax / max(2.6 * lw, 3.2))))
