"""Colour zones (up to 4 AMS colours by height on any single-colour texture) and lids.

Zones split a finished mesh with horizontal planes that sit exactly on a layer boundary, so every printed layer is
one colour and the parts only touch on those planes. Lids print top-face down with a plug that drops inside the rim
(PLA slip fit: 0.25 mm a side), and a press-fit knob printed beside them."""
import math

import numpy as np
import trimesh

CLEAR = 0.25            # mm per side, PLA slip fit
LIP_H = 6.0             # plug depth into the rim
LIP_W = 1.6             # plug wall
LID_T = 2.4             # lid plate
KNOB_HOLE = 6.0         # knob peg hole; peg = hole - 0.15 (light press fit)


def _m3d(mesh):
    import manifold3d as m3d
    return m3d.Manifold(m3d.Mesh(vert_properties=np.asarray(mesh.vertices, np.float32),
                                 tri_verts=np.asarray(mesh.faces, np.int32)))


def _tm(man):
    from .meshops import manifold_to_trimesh
    return manifold_to_trimesh(man, min_volume=0.01)


def zone_edges(height, n, grid, style="bands", stripe=None):
    """Zone boundaries (z values on the layer grid) and the zone index of each band between them."""
    snap = lambda z: round(z / grid) * grid
    if style == "stripes":
        stripe = stripe or max(grid * 4, round(6.0 / grid) * grid)
        edges = [0.0]; z = stripe
        while z < height - grid:
            edges.append(snap(z)); z += stripe
        edges.append(height)
        return edges, [i % n for i in range(len(edges) - 1)]
    edges = [0.0] + [snap(height * k / n) for k in range(1, n)] + [height]
    return edges, list(range(n))


def split_by_bodies(meshes, edges):
    """Woven rods: assign whole rods (connected bodies) to the band holding their centre — no cutting."""
    bodies = [b for m in meshes for b in m.split(only_watertight=False)]
    out = [[] for _ in range(len(edges) - 1)]
    for b in bodies:
        zc = (b.bounds[0][2] + b.bounds[1][2]) / 2
        i = max(0, min(len(out) - 1, int(np.searchsorted(edges, zc, side="right") - 1)))
        out[i].append(b)
    return [trimesh.util.concatenate(o) if o else None for o in out]


def split_by_height(mesh, edges, draft=False):
    """-> list of meshes, one per band [edges[i], edges[i+1]]."""
    if draft or not mesh.is_watertight:                              # preview: assign faces by height, no booleans
        zc = mesh.triangles_center[:, 2]
        out = []
        for a, b in zip(edges, edges[1:]):
            sel = np.where((zc >= a) & (zc < b))[0]
            out.append(mesh.submesh([sel], append=True) if len(sel) else None)
        return out
    rest = _m3d(mesh); out = []
    for z in edges[1:-1]:
        above, below = rest.split_by_plane((0.0, 0.0, 1.0), float(z))
        out.append(_tm(below)); rest = above
    out.append(_tm(rest))
    return [m if len(m.faces) else None for m in out]


# ── lids ──────────────────────────────────────────────────────────────────────
LID_SHAPES = {"cup", "vase", "bowl", "dish", "tray", "custom", "cachepot", "sleeve", "lantern", "amphora",
              "basket", "catchall", "platter"}
FITS = {"snug": 0.15, "slip": 0.25, "loose": 0.40}          # per side, PLA (research §4.1)
THREAD = dict(pitch=3.0, starts=2, depth=1.2, clear=0.2, height=9.0, ring=3.0)   # 45 deg flanks, 0.4 diametral
MAGNET = dict(d=6.0, h=2.0, clear_d=0.15, clear_h=0.2, n=3, land=6.5)            # 6x2 N52, press fit


def opening(build_, shape, v):
    """(outer rim radius, inner opening radius) at the top of the piece, or None."""
    if build_.shape in ("dish", "tray", "platter") and build_.family == "lattice":
        d = v.get("dish", 0)
        if d <= 8:
            return None
        top = build_.stats["size"][2]
        rim = min(build_.stats["size"][0], build_.stats["size"][1]) / 2
        depth = top - v.get("floor", 4)
        Rs = ((d / 2) ** 2 + depth ** 2) / (2 * depth)
        h = depth - LIP_H                                  # the spherical dish narrows: fit where the plug ends
        r_at = math.sqrt(max(Rs ** 2 - (Rs - h) ** 2, 1.0)) if h > 0 else 4.0
        return rim, r_at
    if build_.family == "lattice" and getattr(shape, "round", False) and hasattr(shape, "lattice"):
        # a woven top course is separate parallel rods: no closed hole to slice; read the ring from the region
        from .printer import nozzle
        reg = shape.lattice(v, nozzle(build_.nozzle).rod_h)
        xs = np.linspace(0, reg.extent + 6, 3000)
        ins = xs[reg.sdf(reg.z(reg.n - 1))(xs, np.zeros_like(xs)) <= 0]
        if not len(ins) or ins.min() < 5:
            return None
        return float(ins.max()), float(ins.min())
    if build_.family == "spiral" and getattr(shape, "round", False):
        # vase mode: the model is a solid body, the print is one wall of one line
        from .printer import nozzle
        prof, h, _ = shape.profile(v)
        return float(prof(h)), float(prof(h) - nozzle(build_.nozzle).line_w)
    mesh = trimesh.util.concatenate([m for _, m, _, _ in build_.parts])
    top = mesh.bounds[1][2]
    best = None
    for dz in (0.6, LIP_H * 0.5, LIP_H - 0.3):
        sec = mesh.section(plane_origin=[0, 0, top - dz], plane_normal=[0, 0, 1])
        if sec is None:
            return None
        pl, _ = sec.to_2D(to_2D=np.eye(4))
        holes = [h for p in pl.polygons_full for h in p.interiors]
        if not holes:
            return None
        r_in = min(math.hypot(x, y) for h in holes for x, y in h.coords)
        best = r_in if best is None else min(best, r_in)
    outer = float(np.hypot(mesh.vertices[:, 0], mesh.vertices[:, 1])[mesh.vertices[:, 2] > top - 1.0].max())
    return outer, best


def _helix_ridge(r_base, depth, pitch, starts, z0, height, outward, n_per_turn=96, embed=0.3):
    """Triangular (45 deg flank) helical ridges on a cylinder of radius r_base, pointing out (+1) or in (-1)."""
    import manifold3d as m3d
    lead = pitch * starts; turns = height / lead + 0.25
    n = max(8, int(n_per_turn * turns)); w = depth                     # half-base = depth -> 45 deg flanks
    ridges = []
    for st in range(starts):
        V, F = [], []
        for i in range(n + 1):
            t = i / n; ang = 2 * math.pi * turns * t + 2 * math.pi * st / starts
            zc = z0 + w + (height - 2 * w) * t
            ca, sa = math.cos(ang), math.sin(ang)
            rb = r_base - outward * embed; rt = r_base + outward * depth
            for rr, zz in ((rb, zc - w - embed), (rt, zc), (rb, zc + w + embed)):
                V.append([rr * ca, rr * sa, zz])
        for i in range(n):
            a, b = 3 * i, 3 * (i + 1)
            for k in range(3):
                k2 = (k + 1) % 3
                F += [[a + k, b + k, b + k2], [a + k, b + k2, a + k2]]
        F += [[0, 2, 1], [3 * n, 3 * n + 1, 3 * n + 2]]
        mesh = trimesh.Trimesh(np.array(V), np.array(F), process=True)
        trimesh.repair.fix_winding(mesh); trimesh.repair.fix_normals(mesh)
        if mesh.volume < 0:
            mesh.invert()
        ridges.append(_m3d(mesh))
    return m3d.Manifold.batch_boolean(ridges, m3d.OpType.Add)


def _plate(rim_r, t, square=None, corner=0.0, n=128):
    import manifold3d as m3d
    if square:
        half = square / 2; r = max(0.5, min(corner, half - 1))
        corners = [m3d.Manifold.cylinder(t, r, r, 48).translate([sx * (half - r), sy * (half - r), 0])
                   for sx in (-1, 1) for sy in (-1, 1)]
        bars = [m3d.Manifold.cube([2 * half, 2 * (half - r), t], True).translate([0, 0, t / 2]),
                m3d.Manifold.cube([2 * (half - r), 2 * half, t], True).translate([0, 0, t / 2])]
        return m3d.Manifold.batch_boolean(corners + bars, m3d.OpType.Add)
    return m3d.Manifold.cylinder(t, rim_r + 0.6, rim_r + 0.6, n)


def _knob(rim_r):
    import manifold3d as m3d
    cap_r = max(9.0, min(16.0, rim_r * 0.18))
    cap = m3d.Manifold.cylinder(5.0, cap_r, cap_r * 0.72, 64)
    peg = m3d.Manifold.cylinder(LID_T + 0.6, (KNOB_HOLE - 0.15) / 2, (KNOB_HOLE - 0.15) / 2, 48).translate([0, 0, 4.99])
    return _tm(cap + peg)


def lid_set(style, rim_r, open_r, top_z, fit="slip", square=None, corner=0.0):
    """-> dict(lid, knob, rim: [solids added to the piece], plug_d, clearance, notes). Lids print top-face down."""
    import manifold3d as m3d
    clear = FITS.get(fit, 0.25); n = max(96, int(2 * math.pi * rim_r / 1.2)); notes = []
    hole = m3d.Manifold.cylinder(30, KNOB_HOLE / 2, KNOB_HOLE / 2, 48).translate([0, 0, -1])
    rim_parts = []
    if style == "thread" and open_r > 18 and not square:
        T = THREAD; r_ring = open_r - T["ring"]
        z0 = top_z - T["height"] - 1.0
        ring_prof = np.array([(open_r + 0.6, z0 - T["ring"]), (open_r + 0.6, top_z), (r_ring, top_z),
                              (r_ring, z0), (open_r + 0.6, z0 - T["ring"])])        # 45 deg underside, no overhang
        ring = _m3d(trimesh.creation.revolve(ring_prof, sections=n))
        ring = ring + _helix_ridge(r_ring, T["depth"], T["pitch"], T["starts"], z0 + 0.5, T["height"] - 0.5, -1)
        rim_parts.append(_tm(ring))
        r_p = r_ring - T["depth"] - T["clear"] - 0.0                   # plug core clears the ring's ridges
        plug = (m3d.Manifold.cylinder(T["height"], r_p, r_p, n) - m3d.Manifold.cylinder(T["height"] + 1, r_p - LIP_W, r_p - LIP_W, n).translate([0, 0, -0.5]))
        plug = plug + _helix_ridge(r_p, T["depth"], T["pitch"], T["starts"], 0.6, T["height"] - 0.6, +1)
        # the plug's ridges sit half a pitch from the ring's: rotate by 180/starts so they interleave
        plug = plug.rotate([0, 0, 180.0 / T["starts"]]).translate([0, 0, LID_T - 0.01])
        body = _plate(rim_r, LID_T, square, corner, n) + plug
        notes.append(f"Two-start thread, {T['pitch']} mm pitch: half a turn closes it.")
        plug_d = 2 * r_p
    elif style == "magnets" and open_r > 14:
        M = MAGNET; land_in = open_r - M["land"]; t_plate = 3.6
        z0 = top_z - 5.0
        land_prof = np.array([(open_r + 0.6, z0 - M["land"]), (open_r + 0.6, top_z), (land_in, top_z),
                              (land_in, z0), (open_r + 0.6, z0 - M["land"])])
        land = _m3d(trimesh.creation.revolve(land_prof, sections=n))
        rp = open_r - M["land"] / 2; pd = M["d"] + M["clear_d"]; ph = M["h"] + M["clear_h"]
        pockets = [m3d.Manifold.cylinder(ph + 1, pd / 2, pd / 2, 32).translate([rp, 0, top_z - ph]).rotate([0, 0, 360 * k / M["n"]])
                   for k in range(M["n"])]
        rim_parts.append(_tm(land - m3d.Manifold.batch_boolean(pockets, m3d.OpType.Add)))
        r_plug = land_in - clear
        plug = (m3d.Manifold.cylinder(3.0, r_plug, r_plug, n) - m3d.Manifold.cylinder(4, r_plug - LIP_W, r_plug - LIP_W, n).translate([0, 0, -0.5])).translate([0, 0, t_plate - 0.01])
        lid_pockets = [m3d.Manifold.cylinder(ph + 1, pd / 2, pd / 2, 32).translate([rp, 0, t_plate - ph]).rotate([0, 0, 360 * k / M["n"]])
                       for k in range(M["n"])]
        body = _plate(rim_r, t_plate, square, corner, n) + plug - m3d.Manifold.batch_boolean(lid_pockets, m3d.OpType.Add)
        notes.append(f"Press {2 * M['n']} 6 × 2 mm magnets into the pockets (mind the poles: lid and rim must attract).")
        plug_d = 2 * r_plug
    else:
        r_p = open_r - clear
        ring = (m3d.Manifold.cylinder(LIP_H, r_p, r_p, n) - m3d.Manifold.cylinder(LIP_H + 1, r_p - LIP_W, r_p - LIP_W, n).translate([0, 0, -0.5]))
        lead = m3d.Manifold.cylinder(0.8, r_p + 0.01, r_p - 0.7, n).translate([0, 0, LIP_H - 0.8])   # lead-in chamfer
        ring = (ring - (m3d.Manifold.cylinder(0.8, r_p + 1, r_p + 1, n).translate([0, 0, LIP_H - 0.8]) - lead)).translate([0, 0, LID_T - 0.01])
        body = _plate(rim_r, LID_T, square, corner, n) + ring
        plug_d = 2 * r_p
    lid_m = _tm(body - hole)
    return dict(lid=lid_m, knob=_knob(rim_r), rim=rim_parts, plug_d=round(plug_d, 1), clearance=clear, notes=notes)


def lid(rim_r, plug_r, square=None, corner=0.0):
    """Back-compat: a slip lid whose plug is plug_r (clearance already taken off)."""
    d = lid_set("slip", rim_r, plug_r + FITS["slip"], 0.0, "slip", square, corner)
    return d["lid"], d["knob"]


def fit_test(nozzle=0.4):
    """Rim rings and lids at 0.15 / 0.20 / 0.25 / 0.30 / 0.40 mm a side; notches on each lid count the step."""
    import manifold3d as m3d
    out = []
    for i, c in enumerate((0.15, 0.20, 0.25, 0.30, 0.40), 1):
        ro, ri = 25.0, 23.0
        rim = m3d.Manifold.cylinder(10, ro, ro, 128) - m3d.Manifold.cylinder(12, ri, ri, 128).translate([0, 0, -1])
        d = lid_set("slip", ro, ri, 10.0, "slip")
        r_p = ri - c
        ring = (m3d.Manifold.cylinder(LIP_H, r_p, r_p, 128) - m3d.Manifold.cylinder(LIP_H + 1, r_p - LIP_W, r_p - LIP_W, 128).translate([0, 0, -0.5])).translate([0, 0, LID_T - 0.01])
        lid_m = m3d.Manifold.cylinder(LID_T, ro + 0.6, ro + 0.6, 128) + ring
        for k in range(i):                                            # i notches on the rim edge = step i
            lid_m = lid_m - m3d.Manifold.cube([3, 3, LID_T + 2], True).translate([ro + 0.6, 0, LID_T / 2]).rotate([0, 0, 12 * k])
        out.append((f"fit {c:.2f} rim", _tm(rim)))
        out.append((f"fit {c:.2f} lid", _tm(lid_m)))
    return out


def lid_outline(parts, fit="slip"):
    """Slip lid for any opening (square, rectangle, hex, textured): the plug follows the opening found by slicing
    the piece just under its rim; the plate follows the piece's outline. -> lid_set-style dict, or None."""
    import manifold3d as m3d
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    clear = FITS.get(fit, 0.25)
    mesh = trimesh.util.concatenate([m for _, m, _, _ in parts])
    top = mesh.bounds[1][2]; hole = None; outer = None
    for dz in (0.6, LIP_H * 0.5, LIP_H - 0.3):
        sec = mesh.section(plane_origin=[0, 0, top - dz], plane_normal=[0, 0, 1])
        if sec is None:
            return None
        pl, _ = sec.to_2D(to_2D=np.eye(4))
        polys = sorted(pl.polygons_full, key=lambda q: -q.area)
        if not polys or not polys[0].interiors:
            return None
        h = max((Polygon(i) for i in polys[0].interiors), key=lambda q: q.area)
        hole = h if hole is None else hole.intersection(h)
        ext = unary_union([Polygon(q.exterior) for q in polys]).convex_hull
        outer = ext if outer is None else outer.union(ext)
    hole = hole.buffer(-0.4).buffer(0.4)                       # drop texture specks from the opening's edge
    return _lid_from_polys(hole, outer, clear)


def lid_from_region(region, fit="slip"):
    """Woven rectangles (basket, catch-all): the top course is separate rods, so the opening comes from the
    region's own outline at the top course instead of a slice."""
    import skimage.measure as skm
    from shapely.geometry import Polygon, Point
    clear = FITS.get(fit, 0.25); E = region.extent + 4
    g = np.linspace(-E, E, 900); X, Y = np.meshgrid(g, g, indexing="ij")
    d = region.sdf(region.z(region.n - 1))(X, Y)
    to_poly = lambda c: Polygon(np.column_stack([np.interp(c[:, 0], np.arange(len(g)), g), np.interp(c[:, 1], np.arange(len(g)), g)])).buffer(0)
    polys = [to_poly(c) for c in skm.find_contours(d, 0.0) if len(c) > 20]
    polys = [q for q in polys if q.area > 50]
    if len(polys) < 2:
        return None
    outer = max(polys, key=lambda q: q.area)
    holes = [q for q in polys if q is not outer and q.contains(Point(0, 0))]
    if not holes:
        return None
    return _lid_from_polys(max(holes, key=lambda q: q.area), outer.convex_hull, clear)


def _lid_from_polys(hole, outer, clear):
    import manifold3d as m3d
    plug_o = hole.buffer(-clear, join_style=1); plug_i = plug_o.buffer(-LIP_W, join_style=1)
    if plug_i.is_empty or plug_i.area < 100:
        return None
    plate = outer.buffer(0.6, join_style=1).simplify(0.05)
    ring = plug_o.difference(plug_i)
    def ext(poly, h, z0):
        polys = list(poly.geoms) if hasattr(poly, "geoms") else [poly]
        ms = [trimesh.creation.extrude_polygon(q.simplify(0.05), h) for q in polys]
        m = trimesh.util.concatenate(ms); m.apply_translation([0, 0, z0]); return _m3d(m)
    body = ext(plate, LID_T, 0.0) + ext(ring, LIP_H, LID_T - 0.01)
    hole_c = m3d.Manifold.cylinder(30, KNOB_HOLE / 2, KNOB_HOLE / 2, 48).translate([0, 0, -1])
    rim_r = float(np.sqrt(plate.area / math.pi))
    b = plug_o.bounds
    return dict(lid=_tm(body - hole_c), knob=_knob(rim_r), rim=[], plug_d=round(min(b[2] - b[0], b[3] - b[1]), 1),
                clearance=clear, notes=[f"The lid's plug follows the opening with {clear} mm a side."])


def graft(parts, adds, cuts, into=None):
    """Add solids to a multi-colour piece without unioning into its walls: the adds become their own part in the
    colour of the lowest part (the lid's top face, printed on the bed) and are carved out of the other colours;
    cuts are booleans on everything. Same rule as the fittings."""
    import manifold3d as m3d
    low = into if into is not None else min(range(len(parts)), key=lambda i: parts[i][1].bounds[0][2])
    added = m3d.Manifold.batch_boolean(adds, m3d.OpType.Add) if adds else None
    cut = m3d.Manifold.batch_boolean(cuts, m3d.OpType.Add) if cuts else None
    out = []
    for i, (n, mesh, s, c) in enumerate(parts):
        man = _m3d(mesh)
        if added is not None and c != parts[low][3]:
            man = man - added
        if cut is not None:
            man = man - cut
        if added is not None or cut is not None:
            mesh = _tm(man)
        if len(mesh.faces):
            out.append((n, mesh, s, c))
    if added is not None:
        if cut is not None:
            added = added - cut
        out.append(("graft", _tm(added), parts[low][2], parts[low][3]))
    return out


def plug_of(lid_mesh, t_plate):
    """Split a plain lid (plate 0..t_plate, plug above) -> (plug manifold, its footprint polygons just above the plate)."""
    import manifold3d as m3d
    from shapely.geometry import Polygon
    man = _m3d(lid_mesh)
    top = float(lid_mesh.bounds[1][2])
    plug = man ^ m3d.Manifold.cube([1000, 1000, top - t_plate + 1.0], False).translate([-500, -500, t_plate + 0.02])
    sec = lid_mesh.section(plane_origin=[0, 0, t_plate + 0.15], plane_normal=[0, 0, 1])
    pl, _ = sec.to_2D(to_2D=np.eye(4))
    return plug, list(pl.polygons_full)


def prism(polys, z0, z1):
    """shapely polygons -> one extruded manifold from z0 to z1."""
    ms = [trimesh.creation.extrude_polygon(p, z1 - z0) for p in polys]
    m = trimesh.util.concatenate(ms); m.apply_translation([0, 0, z0])
    return _m3d(m)
