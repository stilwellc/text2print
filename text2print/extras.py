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
    out = man.to_mesh()
    m = trimesh.Trimesh(np.asarray(out.vert_properties)[:, :3], np.asarray(out.tri_verts), process=True)
    if len(m.faces) and m.volume < 0:
        m.invert()
    return m


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
LID_SHAPES = {"cup", "vase", "bowl", "dish", "tray", "custom"}


def opening(build_, shape, v):
    """(outer radius of the rim, plug radius) for the piece's top opening, or None."""
    if build_.shape in ("dish", "tray"):
        d = v.get("dish", 0)
        if d <= 8:
            return None
        top = build_.stats["size"][2]
        rim = min(build_.stats["size"][0], build_.stats["size"][1]) / 2
        # the dish is spherical: the plug must fit the dish where the plug ends, LIP_H down
        depth = top - v.get("floor", 4)
        Rs = ((d / 2) ** 2 + depth ** 2) / (2 * depth)
        h = depth - LIP_H
        r_at = math.sqrt(max(Rs ** 2 - (Rs - h) ** 2, 1.0)) if h > 0 else 4.0
        return rim, r_at - CLEAR
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
    return outer, best - CLEAR


def lid(rim_r, plug_r, square=None, corner=0.0):
    """Lid in print orientation (top face on the bed): plate, plug ring rising above it, knob hole in the middle.
    Returns (lid mesh, knob mesh)."""
    import manifold3d as m3d
    n = max(96, int(2 * math.pi * rim_r / 1.2))
    if square:                                                     # rounded square plate matching a tray
        half = square / 2; r = min(corner, half - 1)
        plate = m3d.Manifold.cube([2 * (half - r), 2 * (half - r), LID_T], True).translate([0, 0, LID_T / 2])
        if r > 0:
            plate = m3d.Manifold.cylinder(LID_T, r, r, n // 4).translate([0, 0, 0])
            corners = [m3d.Manifold.cylinder(LID_T, r, r, max(24, n // 8)).translate([sx * (half - r), sy * (half - r), 0])
                       for sx in (-1, 1) for sy in (-1, 1)]
            bars = [m3d.Manifold.cube([2 * half, 2 * (half - r), LID_T], True).translate([0, 0, LID_T / 2]),
                    m3d.Manifold.cube([2 * (half - r), 2 * half, LID_T], True).translate([0, 0, LID_T / 2])]
            plate = m3d.Manifold.batch_boolean(corners + bars, m3d.OpType.Add)
    else:
        plate = m3d.Manifold.cylinder(LID_T, rim_r + 0.6, rim_r + 0.6, n)
    ring = (m3d.Manifold.cylinder(LIP_H, plug_r, plug_r, n) - m3d.Manifold.cylinder(LIP_H + 1, plug_r - LIP_W, plug_r - LIP_W, n).translate([0, 0, -0.5]))
    ring = ring.translate([0, 0, LID_T - 0.01])
    body = plate + ring
    # chamfer-free: the knob hole goes through the plate (the top face is the bed face, so it prints clean)
    hole = m3d.Manifold.cylinder(LID_T + 2, KNOB_HOLE / 2, KNOB_HOLE / 2, 48).translate([0, 0, -1])
    lid_m = _tm(body - hole)
    # knob: a mushroom printed flat-side down, with a peg on top that presses into the lid from below
    cap_r = max(9.0, min(16.0, rim_r * 0.18))
    cap = m3d.Manifold.cylinder(5.0, cap_r, cap_r * 0.72, 64)
    peg = m3d.Manifold.cylinder(LID_T + 0.6, (KNOB_HOLE - 0.15) / 2, (KNOB_HOLE - 0.15) / 2, 48).translate([0, 0, 4.99])
    knob = _tm(cap + peg)
    return lid_m, knob
