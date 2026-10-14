"""Mix: stack wall textures as height bands on one vessel — plain, printed fabric, droop and halftone.

A mix is a list of bands, bottom to top, each {texture, share, slot, slot2?, options}. Every band describes each
of its print layers as an outer contour r(theta) and a colour slot; droop bands add strands. Consecutive layers of
one colour become one staircase solid; where a band meets a band of the SAME colour, the upper one reaches a
quarter layer down and the two are unioned (never coplanar — the slicer never samples that quarter layer).
One layer height and one wall for the whole print: the nozzle's standard layer and the fabric shell.

Woven rods can't join a mix: they are the whole object, not a wall."""
import math

import numpy as np
import trimesh

from . import droop, halftone
from .fabric_presets import fabric_preset
from .fabric_wall import tri01

MIXABLE = ["plain", "zigzag", "domes", "wave", "halftone", "fringe", "swag", "curls", "unraveled"]
NAMES = {"plain": "Plain", "zigzag": "Zigzag", "domes": "Knit", "wave": "Wave", "halftone": "Halftone",
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


def build(shape, v, nz, bands):
    prof, height, rmax = shape.profile(v)
    bands = normalise(bands)
    lh = nz.layer_h
    fp = {st: fabric_preset(nz.size, diameter=2 * rmax, stitch=st)["fabric"] for st in ("zigzag", "domes", "wave")}
    shell = fp["zigzag"]["shell_t"]
    floor_t = fp["zigzag"]["floor_t"]
    n_layers = int(round(height / lh)); n_floor = int(math.ceil(floor_t / lh))
    # band layer ranges (the floor belongs to the first band)
    edges = [0]; acc = 0.0
    for b in bands:
        acc += b["share"]; edges.append(int(round(acc * n_layers)))
    edges[-1] = n_layers
    for i in range(1, len(edges)):
        edges[i] = max(edges[i], edges[i - 1] + (n_floor + 2 if i == 1 else 2))
    edges = [min(e, n_layers) for e in edges]
    # one angular sampling for the whole print (fine enough for every band's period)
    need = [fp[b["texture"]]["zigzags_around"] * fp[b["texture"]]["samples_per_zigzag"]
            for b in bands if b["texture"] in fp]
    ribs = max(24, int(round(2 * math.pi * rmax / max(2.6 * shell, 3.2))))
    if any(b["texture"] == "halftone" for b in bands):
        need.append(ribs * 6)
    n_th = max(need + [360])
    th = np.linspace(0, 2 * np.pi, n_th, endpoint=False)

    layers = []          # per layer: (slot, outer r array)
    droop_bands = []
    for bi, b in enumerate(bands):
        k0, k1 = edges[bi], edges[bi + 1]; t = b["texture"]
        for k in range(k0, k1):
            zm = (k + 0.5) * lh; R = prof(zm); p = k - k0
            base = np.full(n_th, R)
            if t in fp and k >= n_floor:
                f = fp[t]; cyc = f["zigzag_layers"] + f["straight_layers"]
                if p % cyc >= f["zigzag_layers"]:
                    layers.append((b["slot"], base)); continue
                band = p // cyc; u = f["zigzags_around"] * th / (2 * np.pi) + 0.5 * (band % 2)
                scale = max(0.35, R / rmax); d = f["zigzag_depth"] * scale
                stand = 0.02 * (1 + band % 2) + 0.001 * (p % cyc)
                if t == "domes":
                    env = math.sin(math.pi * ((p % cyc) + 0.5) / f["zigzag_layers"])
                    disp = d * env * np.sin(np.pi * np.mod(u, 1.0)) ** 2
                elif t == "wave":
                    disp = 0.5 * d * np.sin(2 * np.pi * u)
                else:
                    disp = d * tri01(u)
                layers.append((b["slot"], base + stand + disp))
            elif t == "halftone" and k >= n_floor:
                pic = b["options"].get("picture", "flames")
                colour = p % 2
                g = halftone.picture(pic, th / (2 * np.pi), p / max(k1 - k0, 1), b["options"].get("image"))
                g = g if colour == 0 else 1 - g
                step = max(prof(zm) - prof(zm - lh), 0.0)
                amp = max(0.2 * shell, min(0.5 * shell, 0.6 * shell - step))
                ripple = 0.5 - 0.5 * np.cos(ribs * th)
                layers.append((b["slot"] if colour == 0 else b["slot2"], base + amp * g * ripple))
            else:
                layers.append((b["slot"], base))
        if t in droop.STYLES:
            droop_bands.append((b, k0, k1))

    # runs of one colour -> staircases; same-colour neighbours overlap a quarter layer down and get unioned
    runs = []; k = 0
    while k < n_layers:
        slot = layers[k][0]; k2 = k
        while k2 + 1 < n_layers and layers[k2 + 1][0] == slot and _same_family(bands, edges, k2, k2 + 1):
            k2 += 1
        runs.append((slot, k, k2 + 1)); k = k2 + 1
    solids = {}
    for slot, a, b in runs:
        rings = []
        for kk in range(a, b):
            z0 = kk * lh
            if kk == a and a > 0 and layers[a - 1][0] == slot:
                z0 -= 0.25 * lh
            rings += [(z0, layers[kk][1]), ((kk + 1) * lh, layers[kk][1])]
        solids.setdefault(slot, []).append(_staircase(rings, shell, floor_t if a == 0 else None))

    # droop strands, in their band's colour
    q = lambda z: (math.floor(z / lh) + 0.25) * lh
    flat_strands, hung = {}, {}; reach = 0.0
    for b, k0, k1 in droop_bands:
        st = b["texture"]; o = b["options"]
        spots = droop._rows(st, prof, height, nz, droop.DENSITY.get(o.get("density", "medium"), 1.0),
                            droop.LENGTH.get(o.get("length", "medium"), 1.0), z_range=(k0 * lh, k1 * lh))
        spots = droop._never_touch(spots, prof, q)
        reach = max([reach] + [bu for _, _, bu, _, _, _, _ in spots])
        ribbons = [droop._ribbon(t_, ch, bu, q(z), hh, w, prof, shell * 0.55, droop._SPEC[st]["power"], le)
                   for t_, ch, bu, z, hh, le, w in spots]
        flat_strands.setdefault(b["slot"], []).extend(ribbons)
        dr = droop.drape(trimesh.Trimesh(), spots, prof, q, ribbons, st)
        hung.setdefault(b["slot"], []).append(dr)

    parts, preview = {}, {}
    for slot, ms in solids.items():
        strands = flat_strands.get(slot, [])
        walls = _manifold(ms) if len(ms) > 1 else ms[0]
        parts[slot] = _manifold([walls] + strands) if strands else walls
        if strands and _bodies(parts[slot]) > _bodies(walls):
            raise ValueError("a droop strand isn't attached to the wall")
        preview[slot] = trimesh.util.concatenate([walls] + hung.get(slot, []))
    # colour changes: walk the layers' slot sets
    sets = [{s} for s, _ in layers]
    swaps, last = 0, None
    for S in sets:
        if last is not None and last not in S:
            swaps += 1
        last = next(iter(S))
    info = dict(layers=n_layers, bands=[(b["texture"], edges[i + 1] - edges[i]) for i, b in enumerate(bands)],
                swaps=swaps, floor_layers=n_floor, droop=bool(droop_bands),
                strands=sum(len(v) for v in flat_strands.values()), reach=round(reach, 1))
    return parts, preview, info


def _same_family(bands, edges, k_a, k_b):
    """True when layers k_a and k_b sit in the same band (a run never crosses a band edge)."""
    ba = next(i for i in range(len(bands)) if edges[i] <= k_a < edges[i + 1])
    bb = next(i for i in range(len(bands)) if edges[i] <= k_b < edges[i + 1])
    return ba == bb
