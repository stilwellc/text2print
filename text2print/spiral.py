"""Spiral-vase family: the cross-section is the texture and the piece prints as one continuous spiral (Bambu's
spiral vase mode) — fast, seamless, and single-filament (Bambu can't change filament in spiral mode, BambuStudio
issue #1713), so these suit dual/tri-colour silk.

    pleats   sharp folds            flutes   rounded scallops cut inward      twist   pleats that turn with height
    lowpoly  a faceted polygon that turns    pinch   the round mouth squeezes into a lens at the top
    ribs     zero-width slits make the single wall fold in and back: hidden ribs that stiffen a thin translucent
             wall and show as lines against light (needs slice_closing_radius 0)

The mesh is a solid body; the slicer keeps only its outer contour. Folds and twist are clamped so no surface
leans out past ~42 degrees."""
import math

import numpy as np
import trimesh

STYLES = {
    "pleats":  dict(name="Pleats", blurb="Sharp vertical folds — paper-lantern crisp"),
    "flutes":  dict(name="Flutes", blurb="Rounded scallops running up the wall, like a column"),
    "twist":   dict(name="Twist", blurb="Folds that turn as they rise"),
    "lowpoly": dict(name="Low-poly", blurb="A faceted polygon that twists up the piece"),
    "pinch":   dict(name="Pinch", blurb="The round foot squeezes into a lens-shaped mouth"),
    "ribs":    dict(name="Rib slits", blurb="Hidden internal ribs: a thin glowing wall with lines in the light"),
}


def _section(style, th, z, h, R, v):
    t = z / max(h, 1e-6)
    if style == "pleats":
        n = int(v.get("folds", 24)); return R * (1 + 0.07 * (1 - np.abs(np.cos(n * th / 2))) )
    if style == "flutes":
        n = int(v.get("folds", 24)); return R * (1 - 0.05 * (1 - np.abs(np.sin(n * th / 2))) ** 0.5)
    if style == "twist":
        n = int(v.get("folds", 16)); turn = math.radians(v.get("turn", 120)) * t
        return R * (1 + 0.07 * (1 - np.abs(np.cos(n * (th - turn) / 2))))
    if style == "lowpoly":
        n = int(v.get("folds", 7)); turn = math.radians(v.get("turn", 90)) * t
        a = np.mod(th - turn, 2 * np.pi / n) - np.pi / n
        return R * math.cos(math.pi / n) / np.cos(a)
    if style == "pinch":
        p = 0.55 * max(0.0, (t - 0.35) / 0.65) ** 1.4
        return R * (1 - p * np.sin(th) ** 2)
    return np.full_like(th, R)                                            # ribs: round, slits are cut later


def build(shape, v, nz, style="pleats", draft=False):
    prof, height, rmax = shape.profile(v)
    n_th = (360 if draft else 960) if style != "lowpoly" else int(v.get("folds", 7)) * (16 if draft else 48)
    th = np.linspace(0, 2 * np.pi, n_th, endpoint=False)
    dz = 1.0 if draft else 0.4
    zs = np.append(np.arange(0, height, dz), height)
    rings = [np.maximum(_section(style, th, z, height, prof(z), v), 5.0) for z in zs]
    # overhang law: going up, no point moves outward faster than 0.9 mm per mm
    for k in range(1, len(rings)):
        rings[k] = np.minimum(rings[k], rings[k - 1] + 0.9 * (zs[k] - zs[k - 1]))
    c, s = np.cos(th), np.sin(th)
    V = np.vstack([np.column_stack([r * c, r * s, np.full(n_th, z)]) for z, r in zip(zs, rings)])
    m = len(zs); j = np.arange(n_th); jn = (j + 1) % n_th; F = []
    for i in range(m - 1):
        a, b = i * n_th, (i + 1) * n_th
        F += [np.column_stack([a + j, a + jn, b + j]), np.column_stack([a + jn, b + jn, b + j])]
    cb, ct = len(V), len(V) + 1
    V = np.vstack([V, [[0, 0, 0], [0, 0, height]]])
    F += [np.column_stack([jn, j, np.full(n_th, cb)]), np.column_stack([(m - 1) * n_th + j, (m - 1) * n_th + jn, np.full(n_th, ct)])]
    mesh = trimesh.Trimesh(V, np.vstack(F), process=True)
    if mesh.volume < 0:
        mesh.invert()
    if style == "ribs" and not draft:
        mesh = _slits(mesh, prof, height, int(v.get("folds", 24)))
    return mesh, dict(sections=n_th, slits=style == "ribs")


def _slits(mesh, prof, h, n, depth=3.0, width=0.02, floor=2.0):
    """Radial zero-width slits from the outside in: with slice_closing_radius 0 the spiral wall folds in along each
    slit and back out — a hidden rib."""
    import manifold3d as m3d
    from .meshops import manifold_to_trimesh
    body = m3d.Manifold(m3d.Mesh(vert_properties=np.asarray(mesh.vertices, np.float32), tri_verts=np.asarray(mesh.faces, np.int32)))
    rmax = max(prof(z) for z in np.linspace(0, h, 60))
    cuts = []
    for k in range(n):
        a = 360.0 * k / n
        slab = m3d.Manifold.cube([rmax + 5, width, h - floor + 1], False).translate([0, -width / 2, floor])
        keep = m3d.Manifold.cylinder(h + 2, 1.0, 1.0, 32)                    # leave a core so slits stop short
        cuts.append(slab.rotate([0, 0, a]))
    inner = m3d.Manifold(m3d.Mesh(vert_properties=np.asarray(mesh.vertices * [1, 1, 1], np.float32), tri_verts=np.asarray(mesh.faces, np.int32)))
    # slits only reach `depth` in from the outer surface: intersect each slab with (body minus an inset body)
    inset = mesh.copy(); vv = inset.vertices.copy(); r = np.hypot(vv[:, 0], vv[:, 1]); sc = np.maximum(r - depth, 0.5) / np.maximum(r, 1e-6)
    vv[:, 0] *= sc; vv[:, 1] *= sc; inset.vertices = vv
    core = m3d.Manifold(m3d.Mesh(vert_properties=np.asarray(inset.vertices, np.float32), tri_verts=np.asarray(inset.faces, np.int32)))
    cutter = m3d.Manifold.batch_boolean(cuts, m3d.OpType.Add) - core
    return manifold_to_trimesh(body - cutter, min_volume=0.0)
