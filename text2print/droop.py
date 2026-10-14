"""The droop family: single strands that leave the wall and arc into air, then sag under gravity into hanging
loops, fringe, swags and curls (the UNRAVEL technique, print-verified July 2026).

Each strand is a flat ribbon one or two extrusions wide and a few layers tall, anchored INTO the wall at its two
ends only, with open air between strand and wall. The mesh shows the strand before gravity; the printer lays the
unsupported span molten and it drops. Laws (all print-verified):
  * bridges at NORMAL speed (slow freezes each mm as laid and nothing droops); fan <= 20 %, nozzle +5 C
  * strands never intersect in the mesh — they fuse on the print, not in geometry; rows sit a full strand height
    plus a layer apart, strands in a row never overlap
  * directly stacked loops fuse: at most 3 deep, then offset; row phases drift so columns don't stack forever
  * strand height <= 4 layers; bottom loops start high enough that their droop never reaches the bed
  * a loop can't be an r(theta) displacement (single-valued radius welds loops into cliffs) — it is its own ribbon
Jitter is hash-deterministic: a design regenerates identically."""
import hashlib
import math

import numpy as np
import trimesh

STYLES = {
    "fringe":    dict(name="Fringe", blurb="Dense narrow loops that fall into a long hanging fringe"),
    "swag":      dict(name="Swag", blurb="Wide, fat loops that sag into layered festoons"),
    "curls":     dict(name="Curls", blurb="Small loops stacked in drifting columns — they settle into coils"),
    "unraveled": dict(name="Unraveled", blurb="A wild mix of short and long loops, as if the wall is coming apart"),
    "fur":       dict(name="Fur", blurb="Hundreds of bridged hairs out to a cut-away shell — brush them into a mane"),
}
CLEAR = 2.5                 # mm: a hung loop's lowest point stays this far above the bed
FUR_LEN = {"short": 10.0, "medium": 15.0, "long": 22.0}
DENSITY = {"sparse": 0.55, "medium": 1.0, "dense": 1.45}
LENGTH = {"short": 0.7, "medium": 1.0, "long": 1.4}

# per style, in units of the nozzle's line width (lw) and layer height (lh) where it matters
_SPEC = {
    # width 1.15 lw = ONE extrusion (the single overhanging line is the whole idea); swag is 2 lines on purpose
    #            chord mm  bulge mm  width lw  tall lh  row gap lh  keep
    "fringe":    dict(chord=(6, 9),   bulge=(14, 22), width=1.15, tall=2, row=4,  keep=0.62, power=0.55),
    "swag":      dict(chord=(22, 32), bulge=(7, 10),  width=2.1, tall=3, row=14, keep=0.90, power=1.0),
    "curls":     dict(chord=(4, 5.5), bulge=(6, 8),   width=1.15, tall=3, row=5,  keep=1.0, power=0.5),
    "unraveled": dict(chord=(6, 30),  bulge=(5, 24),  width=1.15, tall=2, row=6,  keep=0.55, power=0.7),
}


def _h(*key):
    d = hashlib.sha1(":".join(map(str, key)).encode()).digest()
    return int.from_bytes(d[:4], "big") / 2 ** 32


def _ribbon(theta_c, chord, bulge, z0, height, width, r_of_z, embed, power, lean=0.0, n=26):
    """One loop: a strip that starts inside the wall, arcs out `bulge` mm and returns, `chord` mm apart.
    Built straight from arrays (offset polyline -> strip -> extrusion): thousands per piece, so no shapely/trimesh
    processing per strand."""
    r_w = r_of_z(z0 + height / 2)
    dth = chord / max(r_w, 1.0)
    t = np.linspace(0, 1, n)
    s = np.sin(np.pi * t) ** power
    th = theta_c + (t - 0.5) * dth + lean * dth * np.sin(np.pi * t) ** 2
    leg = min(2.0, 0.4 * bulge)                             # each end leaves the wall RADIALLY for `leg` mm, so a
    r = (r_w + leg) + (bulge - leg) * s                     # long shallow strand never grazes the wall surface
    r = np.concatenate([[r_w - embed], r, [r_w - embed]])
    th = np.concatenate([[th[0]], th, [th[-1]]])
    P = np.column_stack([r * np.cos(th), r * np.sin(th)])
    return _strip(P, width, z0, height)


def _strip(P, width, z0, height):
    """Polyline P (k, 2) -> watertight extruded ribbon of `width` (flat caps, mitred joins clamped to 2x)."""
    T = np.empty_like(P)
    T[1:-1] = P[2:] - P[:-2]; T[0] = P[1] - P[0]; T[-1] = P[-1] - P[-2]
    T /= np.maximum(np.linalg.norm(T, axis=1), 1e-9)[:, None]
    N = np.column_stack([-T[:, 1], T[:, 0]])
    seg = P[1:] - P[:-1]; seg /= np.maximum(np.linalg.norm(seg, axis=1), 1e-9)[:, None]
    scale = np.ones(len(P))
    if len(P) > 2:                                          # mitre: 1/cos(half the turn), clamped
        cosh = np.clip(np.einsum("ij,ij->i", N[1:-1], np.column_stack([-seg[:-1, 1], seg[:-1, 0]])), 0.5, 1.0)
        scale[1:-1] = 1.0 / cosh
    L = P + N * (width / 2 * scale)[:, None]; R = P - N * (width / 2 * scale)[:, None]
    k = len(P)
    ring = np.vstack([L, R[::-1]])                          # closed outline, 2k points
    V = np.vstack([np.column_stack([ring, np.full(2 * k, z0)]), np.column_stack([ring, np.full(2 * k, z0 + height)])])
    m2 = 2 * k; i = np.arange(m2); i2 = (i + 1) % m2
    side = np.vstack([np.column_stack([i, i2, m2 + i2]), np.column_stack([i, m2 + i2, m2 + i])])
    a = np.arange(k - 1); l0, l1 = a, a + 1; r0, r1 = m2 - 1 - a, m2 - 2 - a      # strip quads between L and R
    bot = np.vstack([np.column_stack([l0, r1, l1]), np.column_stack([l0, r0, r1])])
    top = np.vstack([np.column_stack([m2 + l0, m2 + l1, m2 + r1]), np.column_stack([m2 + l0, m2 + r1, m2 + r0])])
    F = np.vstack([side, bot, top])
    m = trimesh.Trimesh(V, F, process=False)
    if (V[F][:, 0] * np.cross(V[F][:, 1], V[F][:, 2])).sum() < 0:   # signed volume < 0: flip every face
        m.faces = F[:, ::-1]
    return m


def _rows(style, r_of_z, height, nz, density, length, seed=11, z_range=None, aligned=False):
    """Strand placements (theta, chord, bulge, z0, tall, lean, width) honouring the laws above."""
    sp = _SPEC[style]; lh, lw = nz.layer_h, nz.line_w
    tall = min(4, sp["tall"]); strand_h = tall * lh; width = sp["width"] * lw
    gap = max(sp["row"], tall + 1) * lh                      # rows a full strand + a layer apart: never intersect
    # plain bands as small as possible (Collin): strands run from just above the bed to just under the rim. A loop
    # hangs about its bulge below its anchor, so near the bed loops are SHORTENED to clear it instead of the whole
    # bottom being left plain — the fringe tapers into the foot.
    rim = 0.0
    if z_range is None:
        z_range = (0.0, height); rim = 1.0
    min_bulge = max(2.5, 0.35 * sp["bulge"][0] * length)
    z_lo = max(z_range[0], CLEAR + min_bulge)
    z_hi = z_range[1] - strand_h - rim
    fit = lambda b, z: min(b, z - CLEAR)                    # the hung loop stops CLEAR mm above the bed
    out = []
    if style == "curls":
        # tiers of coil columns; each next loop drifts 40 % of a chord sideways (partial overlap -> a coil)
        run_n = 16; tier_h = run_n * gap * 0.75; tier = 0; z_t = z_lo
        while z_t <= z_hi:
            r_t = r_of_z(z_t)
            n_cols = max(6, int(2 * math.pi * r_t / 10.0 * min(density, 1.4)))
            for c in range(n_cols):
                th = 2 * math.pi * (c + 0.5 * (tier % 2) + 0.3 * _h(seed, "c", tier, c)) / n_cols
                z = z_t + _h(seed, "z", tier, c) * tier_h * 0.5
                if aligned:                                    # courses: every loop on one row grid, so colour
                    z = z_lo + round((z - z_lo) / gap) * gap   # can change between rows without cutting a loop
                run = int(run_n * (0.6 + 0.6 * _h(seed, "n", tier, c))); d = 1 if (c + tier) % 2 else -1
                for k in range(run):
                    if z > z_hi:
                        break
                    chord = sp["chord"][0] + (sp["chord"][1] - sp["chord"][0]) * _h(seed, "ch", tier, c, k)
                    th_k = th + d * 0.4 * chord / r_of_z(z) * (k % 4 - 1.5)
                    bulge = fit((sp["bulge"][0] + (sp["bulge"][1] - sp["bulge"][0]) * _h(seed, "b", tier, c, k)) * length, z)
                    if bulge >= min_bulge:
                        out.append((th_k, chord, bulge, z, strand_h, 0.0, width))
                    z += gap
            tier += 1; z_t += tier_h
        return out
    row = 0; z = z_lo
    phi = (math.sqrt(5) - 1) / 2
    while z <= z_hi:
        r = r_of_z(z); circ = 2 * math.pi * r
        chord_avg = sum(sp["chord"]) / 2
        slot = chord_avg + width * 2.2
        n = max(3, int(circ / slot))
        phase = (row * phi) % 1.0                              # drift: no column stacks more than ~3 deep
        for k in range(n):
            if _h(seed, "keep", row, k) > min(0.98, sp["keep"] * density):
                continue
            chord = sp["chord"][0] + (sp["chord"][1] - sp["chord"][0]) * _h(seed, "ch", row, k)
            chord = min(chord, slot - width * 2.0)            # strands in a row never touch
            bulge = fit((sp["bulge"][0] + (sp["bulge"][1] - sp["bulge"][0]) * _h(seed, "b", row, k)) * length, z)
            lean = (_h(seed, "l", row, k) - 0.5) * (0.8 if style == "unraveled" else 0.25)
            th = 2 * math.pi * (k + phase) / n
            out.append((th, chord, bulge, z, strand_h, lean, width))
        row += 1; z += gap
    return out


def _never_touch(spots, prof, q):
    """Law: strands never intersect in the mesh. Strands that share layers must keep a full strip width of air
    between their footprints (angular extent incl. lean); later ones that don't are dropped."""
    kept, by_z = [], {}
    for sp in spots:
        th, ch, bu, z, hh, lean, w = sp
        zq = round(q(z), 4); r = prof(zq)
        half = (ch / 2 + w * 1.5) / r * (1 + abs(lean))
        lo, hi = th - half, th + half
        clash = False
        for zz, items in by_z.items():
            if abs(zz - zq) >= hh + 1e-6:
                continue
            for a, b in items:
                for off in (-2 * math.pi, 0.0, 2 * math.pi):
                    if lo < b + off and a + off < hi:
                        clash = True; break
                if clash:
                    break
            if clash:
                break
        if not clash:
            by_z.setdefault(zq, []).append((lo, hi)); kept.append(sp)
    return kept


def body(shape, v, nz):
    """The wall: a plain 2-loop revolved shell (vessels) or a solid revolved body with a candle socket."""
    prof, height, rmax = shape.profile(v)
    shell = 2 * nz.line_w + 0.15; floor_t = max(1.6, 8 * nz.layer_h)
    lh = nz.layer_h; step = lh * max(1, round(0.6 / lh))
    # wall rings on the 3/4-layer grid, strand faces on the 1/4-layer grid: every strand face sits half a layer
    # from every ring, so the union never meets near-coplanar faces (they leave slivers)
    zs = np.concatenate([[0.0], np.arange(0.75 * lh, height, step), [height]])
    if getattr(shape, "solid", False):
        sock_r, sock_d = v.get("socket", 22.5) / 2, 22.0
        pts = [(0, 0)] + [(prof(z), z) for z in zs] + [(sock_r, height), (sock_r, height - sock_d), (0, height - sock_d)]
    else:
        outer = [(prof(z), z) for z in zs]
        inner = [(max(prof(z) - shell, 1.0), z) for z in zs[::-1] if z >= floor_t]
        pts = [(0, 0)] + outer + inner + [(max(prof(floor_t) - shell, 1.0), floor_t), (0, floor_t)]
    pts = np.array(pts, float)
    m = trimesh.creation.revolve(pts, sections=max(96, int(2 * math.pi * rmax / 1.2)))
    if m.volume < 0:
        m.invert()
    return m, prof, height, rmax, shell


HANG = {"fringe": (78, 88), "swag": (55, 72), "curls": (45, 80), "unraveled": (35, 88)}   # degrees below horizontal


def courses(spots, lh):
    """Layer boundaries (z) where a colour can change without cutting a strand: each strand row's first layer,
    kept only if no other strand spans it. Like woven courses — colour follows the row, one change per row."""
    occ = [(int(math.floor(z / lh + 1e-9)), int(math.floor(z / lh + 1e-9)) + int(round(hh / lh))) for _, _, _, z, hh, _, _ in spots]
    starts = sorted({a for a, _ in occ})
    return [k * lh for k in starts if not any(a < k <= b for a, b in occ)]


def drape(wall, spots, prof, q, ribbons, style, seed=11, pieces=False):
    """Preview only: each strand swung down about the line joining its anchors, as gravity will do it.
    Not printable (strands pass through each other) — the print files always carry the flat strands."""
    lo, hi = HANG[style]; out = [wall]
    for k, ((th, ch, bu, z, hh, lean, w), rib) in enumerate(zip(spots, ribbons)):
        r_w = prof(q(z) + hh / 2)
        axis = np.array([-math.sin(th), math.cos(th), 0.0])
        pivot = np.array([r_w * math.cos(th), r_w * math.sin(th), q(z) + hh / 2])
        ang = math.radians(lo + (hi - lo) * _h(seed, "hang", k))
        R = trimesh.transformations.rotation_matrix(ang, axis, pivot)
        probe = trimesh.transform_points([pivot + [math.cos(th) * 5, math.sin(th) * 5, 0]], R)[0]
        if probe[2] > pivot[2]:
            R = trimesh.transformations.rotation_matrix(-ang, axis, pivot)
        d = rib.copy(); d.apply_transform(R); out.append((z, d) if pieces else d)
    if pieces:                                       # wall + [(anchor z, hung strand)]: colour follows the anchor
        return out[0], out[1:]
    return trimesh.util.concatenate(out)


def fur(shape, v, nz, density="medium", length="medium", draft=False, preview=False):
    """Bridge-strand fur (Cepin's "Furry Lion" method): each hair is a one-layer slab two lines wide (out and back)
    bridged from the wall to a thin sacrificial shell. After printing, cut the hairs at the shell, pull it away and
    brush/heat-style the fur. Hairs never touch: one per angle slot per layer, staggered layer to layer."""
    import manifold3d as m3d
    from .meshops import manifold_to_trimesh
    wall, prof, height, rmax, shell = body(shape, v, nz)
    lh = nz.layer_h; L = FUR_LEN.get(length, 15.0); w = 2 * nz.line_w
    z_lo, z_hi = max(1.6, 8 * lh) + lh, height - 1.5          # hair from just above the floor to just under the rim
    every = {"sparse": 3, "medium": 2, "dense": 1}.get(density, 2)
    shell_t = 2 * nz.line_w + 0.05
    # shell: follows the wall at +L from the bed to the top of the fur band
    zs = np.append(np.arange(0, z_hi + lh, 0.6), z_hi + lh)
    outer = [(prof(z) + L + shell_t, z) for z in zs]; inner = [(prof(z) + L, z) for z in zs[::-1]]
    sh = trimesh.creation.revolve(np.array(outer + inner + [outer[0]]), sections=max(120, int(2 * math.pi * (rmax + L) / 1.2)))
    if sh.volume < 0:
        sh.invert()
    # one extruded 2D cross-section per hair layer (hairs in a layer never touch): ~100 solids to union, not ~27k
    layers = []; k = int(z_lo / lh); n_hairs = 0
    while (k + 1) * lh <= z_hi:
        if (k % every) == 0:
            z0 = k * lh + 0.03; z1 = (k + 1) * lh - 0.03; zm = (z0 + z1) / 2; R = prof(zm)
            n = max(12, int(2 * math.pi * R / (w + 1.4)))
            off = 0.5 * ((k // every) % 2)
            r0, r1 = R - shell * 0.6, R + L + shell_t * 0.6
            polys = []
            for i in range(n):
                a = 2 * math.pi * (i + off) / n; c, s_ = math.cos(a), math.sin(a)
                rect = [(r0, -w / 2), (r1, -w / 2), (r1, w / 2), (r0, w / 2)]
                polys.append([(x * c - y * s_, x * s_ + y * c) for x, y in rect])
            layers.append(m3d.Manifold.extrude(m3d.CrossSection(polys), z1 - z0).translate([0, 0, z0]))
            n_hairs += n
        k += 1
    if draft:
        hairs_m = [manifold_to_trimesh(L_) for L_ in layers[:: max(1, len(layers) // 40)]]
        return trimesh.util.concatenate([wall, sh] + hairs_m), dict(strands=n_hairs, reach=round(L, 1), draped=None,
                                                                   floor_layers=int(round(max(1.6, 8 * lh) / lh)), solid=False)
    to_m = lambda t: m3d.Manifold(m3d.Mesh(vert_properties=np.asarray(t.vertices, np.float32), tri_verts=np.asarray(t.faces, np.int32)))
    merged = m3d.Manifold.batch_boolean([to_m(wall), to_m(sh)] + layers, m3d.OpType.Add)
    mesh = manifold_to_trimesh(merged)
    trimmed = None
    if preview:                                     # what you hold after cutting the hairs free of the shell
        cut = [(prof(z) + L - 0.4, z) for z in zs] + [(prof(z) + L + shell_t + 2, z) for z in zs[::-1]]
        tube = trimesh.creation.revolve(np.array(cut + [cut[0]]), sections=max(120, int(2 * math.pi * (rmax + L) / 1.2)))
        if tube.volume < 0:
            tube.invert()
        trimmed = manifold_to_trimesh(merged - to_m(tube))
    return mesh, dict(strands=n_hairs, reach=round(L, 1), draped=trimmed, floor_layers=int(round(max(1.6, 8 * lh) / lh)),
                      solid=False)


def build(shape, v, nz, style="fringe", density="medium", length="medium", preview=False, draft=False, aligned=False):
    import manifold3d as m3d
    if style == "fur":
        return fur(shape, v, nz, density, length, draft, preview)
    wall, prof, height, rmax, shell = body(shape, v, nz)
    spots = _rows(style, prof, height, nz, DENSITY.get(density, 1.0), LENGTH.get(length, 1.0), aligned=aligned)
    embed = shell * 0.55
    lh = nz.layer_h
    q = lambda z: (math.floor(z / lh) + 0.25) * lh           # quarter-layer shift: no strand face is coplanar with
                                                             # the wall's rings (coplanar unions leave slivers)
    spots = _never_touch(spots, prof, q)
    ribbons = [_ribbon(th, ch, bu, q(z), hh, w, prof, embed, _SPEC[style]["power"], lean)
               for th, ch, bu, z, hh, lean, w in spots]
    if draft:                                                   # preview only: skip the (slow) union
        mesh = trimesh.util.concatenate([wall] + ribbons)
    else:
        to_m = lambda t: m3d.Manifold(m3d.Mesh(vert_properties=np.asarray(t.vertices, np.float32),
                                                tri_verts=np.asarray(t.faces, np.int32)))
        from .meshops import manifold_to_trimesh
        merged = m3d.Manifold.batch_boolean([to_m(wall)] + [to_m(r) for r in ribbons], m3d.OpType.Add)
        solid = [c for c in merged.decompose() if abs(c.volume()) > 0.5]
        if len(solid) != 1:
            raise ValueError(f"droop build produced {len(solid)} solid bodies — a strand is detached")
        mesh = manifold_to_trimesh(solid[0])
    reach = max((bu for _, _, bu, _, _, _, _ in spots), default=0.0)
    drape_pieces = drape(wall, spots, prof, q, ribbons, style, pieces=True) if preview else None
    draped = (trimesh.util.concatenate([drape_pieces[0]] + [r_ for _, r_ in drape_pieces[1]])
              if preview else None)                             # hung once, per strand; the whole is their sum
    info = dict(strands=len(spots), reach=round(reach, 1), draped=draped, drape_pieces=drape_pieces,
                courses=courses(spots, lh), course_gap=max(_SPEC[style]["row"], _SPEC[style]["tall"] + 1) * lh,
                floor_layers=int(round(max(1.6, 8 * nz.layer_h) / nz.layer_h)), solid=bool(getattr(shape, "solid", False)))
    return mesh, info
