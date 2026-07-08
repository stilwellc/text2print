"""floor_cuts.py — decorative through-cuts for solid floors.

Helpers for perforating the flat floor of a part (bowl, tray, lid)
with manifold3d booleans:

  diamond_cutters()  concentric rings of diamond cutouts, alternate
                     rings rotated half a step so they crisscross
  text_cutters()     a word cut clean through, with thin stencil
                     bridges through enclosed counters (o, e, p...)
                     so no letter interior falls out of the print
  cut_floor()        applies cutters and REFUSES to return geometry
                     with loose islands (extra bodies = pieces that
                     detach on the print bed)

Reference pairing: zigzag_fabric.fabric_solid() for the walls, these
helpers for the floor. Tests: tests/test_floor_cuts.py.
"""
import numpy as np
import trimesh


def _to_manifold(tm):
    import manifold3d as m3d
    return m3d.Manifold(m3d.Mesh(
        vert_properties=np.array(tm.vertices, dtype=np.float32),
        tri_verts=np.array(tm.faces, dtype=np.int32)))


def diamond_cutters(rings, diag=5.0, depth=5.0, z0=-1.0):
    """Diamond-prism cutters in concentric rings.

    rings  list of (radius mm, hole count); alternate rings are rotated
           half a step so the pattern crisscrosses.
    diag   point-to-point diamond size, mm.
    depth  cutter height, mm — must exceed the floor thickness.
    z0     cutter bottom, mm — start below the floor underside.

    Keep the outermost radius + diag/2 clear of the inner wall, and
    webs between holes >= ~3mm for a rigid floor.
    """
    import manifold3d as m3d
    side = diag / np.sqrt(2)
    cutters = []
    for ring_i, (ring_r, count) in enumerate(rings):
        offset = (np.pi / count) * (ring_i % 2)
        for h in range(count):
            a = 2 * np.pi * h / count + offset
            cut = m3d.Manifold.cube([side, side, depth], center=True)
            cut = cut.rotate([0, 0, 45 + np.degrees(a)])
            cutters.append(cut.translate(
                [ring_r * np.cos(a), ring_r * np.sin(a), z0 + depth / 2]))
    return cutters


def lens_cutters(rings, length=12.0, width=4.5, depth=5.0, z0=-1.0):
    """Eye/lens-shaped cutters (vesica of two circles) in concentric
    rings, long axis tangential, alternate rings offset half a step.

    The lens is the negative shape of the wave stitch's eye windows —
    use it for floors that speak the same language as a wave wall.
    rings is a list of (radius mm, hole count), like diamond_cutters.
    """
    from shapely.geometry import Point

    a, b = length / 2, width / 2
    R = (a * a + b * b) / (2 * b)          # vesica circle radius
    d = R - b                              # circle center offset
    lens = Point(0, -d).buffer(R, quad_segs=48).intersection(
        Point(0, d).buffer(R, quad_segs=48))

    cutters = []
    for ring_i, (ring_r, count) in enumerate(rings):
        offset = (np.pi / count) * (ring_i % 2)
        for h in range(count):
            ang = 2 * np.pi * h / count + offset
            prism = trimesh.creation.extrude_polygon(lens, height=depth)
            prism.apply_translation([0, 0, z0])
            # long axis (x) -> tangential at ring position
            prism.apply_transform(trimesh.transformations.rotation_matrix(
                ang + np.pi / 2, [0, 0, 1]))
            prism.apply_translation(
                [ring_r * np.cos(ang), ring_r * np.sin(ang), 0])
            cutters.append(_to_manifold(prism))
    return cutters


def text_region(text, width, font="Arial Rounded MT Bold", bridge_w=1.0):
    """A word as 2D cut polygons (shapely), stencil-bridged.

    Letters with enclosed counters get a thin vertical tab of kept
    material through each counter so the interior stays attached.
    Returns a list of shapely Polygons centered on the origin, `width`
    mm wide, reading correctly from +Z (from inside the part).
    """
    from matplotlib.textpath import TextPath
    from matplotlib.font_manager import FontProperties
    from shapely.geometry import Polygon, MultiPolygon, box
    from shapely.ops import unary_union
    from shapely import affinity

    path = TextPath((0, 0), text, size=20, prop=FontProperties(family=font))
    rings = [r for r in path.to_polygons() if len(r) > 2]
    # even-odd containment: a ring inside an odd number of rings is a hole
    polys = [Polygon(r) for r in rings]
    letters = []
    for i, p in enumerate(polys):
        depth_in = sum(1 for j, q in enumerate(polys)
                       if i != j and q.contains(p))
        if depth_in % 2 == 0:
            holes = [r for j, r in enumerate(rings) if j != i
                     and polys[j].within(p)]
            letters.append(Polygon(rings[i], holes))

    word = unary_union(letters)
    minx, _, maxx, _ = word.bounds
    s = width / (maxx - minx)
    word = affinity.scale(word, xfact=s, yfact=s, origin=(0, 0))
    word = affinity.translate(
        word,
        xoff=-(word.bounds[0] + word.bounds[2]) / 2,
        yoff=-(word.bounds[1] + word.bounds[3]) / 2)

    bridges = []
    for letter in getattr(word, "geoms", [word]):
        for hole in letter.interiors:
            hx = hole.centroid.x
            b = letter.bounds
            bridges.append(box(hx - bridge_w / 2, b[1] - 1,
                               hx + bridge_w / 2, b[3] + 1))
    cut = word.difference(unary_union(bridges)) if bridges else word
    return list(cut.geoms) if isinstance(cut, MultiPolygon) else [cut]


def text_cutters(text, width, font="Arial Rounded MT Bold",
                 bridge_w=1.0, depth=5.0, z0=-1.0):
    """Extruded manifold cutters for a stencil-bridged word."""
    cutters = []
    for poly in text_region(text, width, font=font, bridge_w=bridge_w):
        prism = trimesh.creation.extrude_polygon(poly, height=depth)
        prism.apply_translation([0, 0, z0])
        cutters.append(_to_manifold(prism))
    return cutters


def cut_floor(tm, cutters):
    """Subtract cutters from a solid; refuse results with loose islands.

    Returns a new trimesh.Trimesh. Raises ValueError if the cut
    disconnects any region (it would fall out of the print) — usually a
    missing stencil bridge or cutouts overlapping into a closed ring.
    """
    import manifold3d as m3d
    cutter_m = m3d.Manifold.batch_boolean(cutters, m3d.OpType.Add)
    result_m = _to_manifold(tm) - cutter_m
    out = result_m.to_mesh()
    result = trimesh.Trimesh(
        vertices=np.array(out.vert_properties, dtype=np.float64),
        faces=np.array(out.tri_verts, dtype=np.int64), process=True)
    n_bodies = len(result.split(only_watertight=False))
    if n_bodies != 1:
        raise ValueError(
            f"floor cut produced {n_bodies} bodies — loose island(s) "
            "would fall out of the print; add stencil bridges or "
            "separate the cutouts")
    return result
