"""Mix: stack wall textures as height bands on one vessel — plain, printed fabric, droop and halftone.

A mix is a list of bands, bottom to top, each {texture, share, slot, slot2?, options}. Every band describes each
of its print layers as an outer contour r(theta) and a colour slot; droop bands add strands. Consecutive layers of
one colour become one staircase solid; where a band meets a band of the SAME colour, the upper one reaches a
quarter layer down and the two are unioned (never coplanar — the slicer never samples that quarter layer).
Layer heights: every band prints at the nozzle's standard layer EXCEPT halftone bands, which keep their own recipe
(max layer height, one wide line) through a Bambu layer range — band edges are snapped so every band is a whole
number of its own layers and the slicer's layers land exactly on the geometry's.

Woven bands (Weave, Twill, Ripple, Moiré, Rose window): a ring of rods centred on the wall, coloured by course
(even courses `slot`, odd `slot2`) like any woven piece — one AMS change per course. A thin wall can't carry a
rod ring, so a woven band starts with a solid collar that widens from the wall below at <= 45 deg (or a solid
floor disc if it is the bottom band), and ends with a cap that narrows back to the wall for the band above.
The band has an odd number of courses so its first and last courses share the collar's and cap's colour."""
import math

import numpy as np
import trimesh

from . import droop, halftone, lattice
from .fabric_presets import fabric_preset
from .fabric import RELIEFS, relief
from .fabric_wall import tri01

WOVEN = ["grid", "twill", "ripple", "beat", "polar"]        # course-coloured patterns: one colour per course
MIXABLE = ["plain", "fuzzy", "zigzag", "domes", "wave", "garland", "drips", "melt", "halftone",
           "fringe", "swag", "curls", "unraveled"] + WOVEN
TWO_SLOT = {"halftone"} | set(WOVEN)
NAMES = {"plain": "Plain", "fuzzy": "Fuzzy skin", "zigzag": "Zigzag", "domes": "Knit", "wave": "Wave", "garland": "Garland",
         "drips": "Drips", "melt": "Melt", "halftone": "Halftone",
         "fringe": "Fringe", "swag": "Swag", "curls": "Curls", "unraveled": "Unraveled",
         **{k: lattice.PATTERNS[k]["name"] for k in WOVEN}}
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
    "basket":  dict(name="Basket band", bands=[dict(texture="plain", share=16, slot=0),
                                               dict(texture="twill", share=58, slot=0, slot2=1),
                                               dict(texture="plain", share=26, slot=1)]),
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
    mesh = trimesh.Trimesh(V, np.vstack(F), process=False)   # rings dedup'd above: no merge pass needed
    from .meshops import volume
    if volume(mesh) < 0:                                      # consistent winding by construction; fix the sign only
        mesh.invert()
    return mesh


def _manifold(meshes):
    import manifold3d as m3d
    from .meshops import manifold_to_trimesh
    ms = [m3d.Manifold(m3d.Mesh(vert_properties=np.asarray(t.vertices, np.float32),
                                tri_verts=np.asarray(t.faces, np.int32))) for t in meshes]
    from .meshops import drop_flaps
    return drop_flaps(manifold_to_trimesh(m3d.Manifold.batch_boolean(ms, m3d.OpType.Add), split=False))


def _attach(walls, strands, check=True):
    """Union strands into their walls; with check, a strand that adds a body (detached) raises. Bodies are
    counted by Manifold (C++) — trimesh splits of a multi-million-triangle wall cost seconds. Skipped when a
    woven band shares the part (thousands of rods are separate bodies by design)."""
    import manifold3d as m3d
    from .meshops import drop_flaps, manifold_to_trimesh
    to_m = lambda t: m3d.Manifold(m3d.Mesh(vert_properties=np.asarray(t.vertices, np.float32),
                                           tri_verts=np.asarray(t.faces, np.int32)))
    w = to_m(walls)
    u = m3d.Manifold.batch_boolean([w] + [to_m(s) for s in strands], m3d.OpType.Add)
    if check:
        nw = len([c for c in w.decompose() if abs(c.volume()) > 0.5])
        nu = len([c for c in u.decompose() if abs(c.volume()) > 0.5])
        if nu > nw:
            raise ValueError("a droop strand isn't attached to the wall")
    return drop_flaps(manifold_to_trimesh(u, split=False))


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
    rod_h, rl = nz.rod_h, nz.rod_layers
    wplan = {}                                                   # woven band -> (lower courses, rod courses, cap courses)
    for i, b in enumerate(bands):
        if b["texture"] in WOVEN:
            w = float(b["options"].get("wall", 6.0))
            ramp = int(math.ceil(((w - shell) / 2 + 0.5) / rod_h))   # courses to widen/narrow at <= 45 deg
            low = int(math.ceil(floor_t / rod_h)) if i == 0 else ramp
            wplan[i] = [low, 0, ramp if i < len(bands) - 1 else 0, w]
    if 0 in wplan:
        n_floor = wplan[0][0] * rl; floor_z = n_floor * lhs[0]
    zs = [0.0]; acc = 0.0
    for i, b in enumerate(bands):
        acc += b["share"]; want = acc * height - zs[-1]
        if i in wplan:
            low, _, cap, _ = wplan[i]
            k = max(3, int(round(want / rod_h)) - low - cap); k += 1 - k % 2   # odd: first and last course = slot
            wplan[i][1] = k
            n = (low + k + cap) * rl
        else:
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
        if t in WOVEN:                     # a rod is rod_lines loops side by side; the collar and cap fill solid too
            ranges.append((za, zb, {"layer_height": f"{lh:.2f}", "wall_loops": str(nz.rod_lines)}))
        k = 0
        while za + (k + 1) * lh <= zb + 1e-6:
            z0, z1 = za + k * lh, za + (k + 1) * lh; zm = (z0 + z1) / 2; R = prof(zm)
            floor_layer = z1 <= floor_z + 1e-6
            entry = dict(z0=z0, z1=z1, slot=b["slot"], band=bi, lh=lh, n=n, r=None)
            if t in WOVEN:                                             # rods, collar and cap: no wall rings
                low, nc, cap, _ = wplan[bi]; course = k // rl - low
                entry["woven"] = True
                if 0 <= course < nc and course % 2 == 1:
                    entry["slot"] = b["slot2"]
            elif floor_layer or t in ("plain", "fuzzy") or t in droop.STYLES:
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
                if "_dark" not in b:                                      # the picture library, once per band
                    from . import pictures
                    b["_dark"] = pictures.darkness(b["options"], 2 * math.pi * rmax / max(zb - za, 1e-6))
                g = b["_dark"](th / (2 * np.pi), np.full(len(th), (zm - za) / max(zb - za, 1e-6)))
                g = g if colour == 0 else 1 - g
                step = max(prof(zm) - prof(zm - lh), 0.0)
                amp = max(0.2 * ht_lw, min(0.5 * ht_lw, 0.6 * ht_lw - step))
                entry["r"] = R + amp * g * (0.5 - 0.5 * np.cos(ribs * th))
                entry["slot"] = b["slot"] if colour == 0 else b["slot2"]
            layers.append(entry); k += 1

    # runs: consecutive layers of one band and one colour
    # runs: consecutive layers of one colour. A run may cross into the next band when the wall is the same
    # thickness and the contours share a sampling (or one side is smooth): one staircase, no boolean union —
    # the unions of same-colour neighbours were most of a mix's build time.
    def _shell(L):
        return ht_lw if bands[L["band"]]["texture"] == "halftone" else shell
    def _joins(A, B):
        if A.get("woven") or B.get("woven") or A["slot"] != B["slot"]:
            return False
        if A["band"] == B["band"]:
            return True
        return _shell(A) == _shell(B) and (A["r"] is None or B["r"] is None or len(A["r"]) == len(B["r"]))
    runs = []; i = 0
    while i < len(layers):
        j = i; rn = len(layers[i]["r"]) if layers[i]["r"] is not None else None   # the run's contour sampling
        while j + 1 < len(layers) and _joins(layers[j], layers[j + 1]):
            nb = layers[j + 1]["r"]
            if nb is not None and rn is not None and len(nb) != rn:
                break
            rn = rn if rn is not None else (len(nb) if nb is not None else None)
            j += 1
        runs.append((i, j)); i = j + 1
    solids = {}
    for bi, b in enumerate(bands):
        if bi in wplan:
            za = zs[bi]; prev_slot = next((L["slot"] for L in reversed(layers) if L["z1"] <= za + 1e-6), None)
            for slot, m in _woven_band(b, wplan[bi], za, prof, shell, nz, bi == 0, prev_slot, draft).items():
                solids.setdefault(slot, []).append(m)
    for a, b_ in runs:
        L0 = layers[a]; slot = L0["slot"]
        n = next((len(layers[k]["r"]) for k in range(a, b_ + 1) if layers[k]["r"] is not None), L0["n"])
        if L0.get("woven"):
            continue
        bi = L0["band"]; sh = ht_lw if bands[bi]["texture"] == "halftone" else shell
        rings = []
        reach_down = a > 0 and layers[a - 1]["slot"] == slot
        for kk in range(a, b_ + 1):
            L = layers[kk]; z0 = L["z0"] - (0.25 * layers[a - 1]["lh"] if kk == a and reach_down else 0.0)
            if L["r"] is None:                                         # smooth: one ring per layer boundary
                rings.append((z0, np.full(n, prof(max(z0, 0.0)))))
                if kk == b_ or layers[kk + 1]["r"] is not None:          # close before a textured layer: a step,
                    rings.append((L["z1"], np.full(n, prof(L["z1"]))))   # not a ramp across this layer
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
            if strands:
                parts[slot] = _attach(walls, strands, check=not wplan)
            else:
                parts[slot] = walls
        preview[slot] = trimesh.util.concatenate([walls] + hung.get(slot, []))

    seq = [L["slot"] for L in layers]
    swaps = sum(1 for x, y in zip(seq, seq[1:]) if x != y)
    kinds = {}
    for b in bands:
        for s_ in ([b["slot"], b["slot2"]] if b["texture"] in TWO_SLOT else [b["slot"]]):
            if b["texture"] in droop.STYLES:
                kinds[s_] = "droop"
            else:
                kinds.setdefault(s_, "normal")
    info = dict(layers=len(layers), bands=[(b["texture"], round(zs[i + 1] - zs[i], 2)) for i, b in enumerate(bands)],
                swaps=swaps, floor_layers=n_floor, droop=bool(droop_bands), height=round(total_h, 2), woven=bool(wplan),
                strands=sum(len(x) for x in flat.values()), reach=round(reach, 1), ranges=ranges, kinds=kinds,
                layer_slots=[(round(L["z0"], 4), round(L["z1"], 4), L["slot"]) for L in layers])
    return parts, preview, info


def _ribs(rmax, lw):
    return max(24, int(round(2 * math.pi * rmax / max(2.6 * lw, 3.2))))


LEAN = 0.8          # a woven course steps at most this many mm per mm in or out of the one below


def _revolve(pts, n=192):
    m = trimesh.creation.revolve(np.array(pts + [pts[0]], float), sections=n)
    if m.volume < 0:
        m.invert()
    return m


def _woven_band(b, plan, za, prof, shell, nz, bottom, prev_slot, draft=False):
    """-> {slot: mesh}: collar (or floor disc), rods, cap. The ring is centred on the wall (r = prof - shell/2)."""
    low, nc, cap, w = plan; rh, lh = nz.rod_h, nz.layer_h; q = 0.25 * lh
    z_r0 = za + low * rh; z_r1 = z_r0 + nc * rh
    mids = np.empty(nc)
    for i in range(nc):
        mids[i] = prof(z_r0 + (i + 0.5) * rh) - shell / 2
        if i:
            mids[i] = min(max(mids[i], mids[i - 1] - LEAN * rh), mids[i - 1] + LEAN * rh)
    rmax = float(mids.max() + w / 2); n = max(96, int(2 * math.pi * rmax / 1.2))
    out = {}
    slot, slot2 = b["slot"], b["slot2"]
    ro0, ri0 = mids[0] + w / 2, max(mids[0] - w / 2, 0.0)
    if bottom:                                                     # solid floor disc the ring stands on
        lower = _revolve([(0.0, 0.0), (ro0, 0.0), (ro0, z_r0 + q), (0.0, z_r0 + q)], n)
    else:                                                          # collar: wall below -> full ring at <= 45 deg
        zb = za - (q if prev_slot == slot else 0.0); Rw = prof(za)
        lower = _revolve([(Rw - shell, zb), (Rw, zb), (ro0, z_r0 + q), (ri0, z_r0 + q)], n)
    out.setdefault(slot, []).append(lower)
    if cap:                                                        # ring -> wall for the band above
        roN, riN = mids[-1] + w / 2, max(mids[-1] - w / 2, 0.0); zt = z_r1 + cap * rh; Rt = prof(zt)
        out[slot].append(_revolve([(riN, z_r1 - q), (roN, z_r1 - q), (Rt, zt), (Rt - shell, zt)], n))

    from .shapes import Region                                     # the ring as a lattice region, local z

    def sdf_at(z):
        k = min(nc - 1, max(0, int(z / rh)))
        ro, ri = mids[k] + w / 2, mids[k] - w / 2
        return lambda x, y: np.maximum(np.hypot(x, y) - ro, ri - np.hypot(x, y))
    rods = lattice.weave(Region(nc, rh, sdf_at, rmax, True, 0), nz, b["texture"])
    for s_, m in rods.meshes().items():
        m = m.copy(); m.apply_translation([0, 0, z_r0])
        out.setdefault(slot if s_ == 0 else slot2, []).append(m)
    return {s_: trimesh.util.concatenate(ms) for s_, ms in out.items()}
