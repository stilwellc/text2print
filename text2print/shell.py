"""Shell family: a plain wall that carries the texture another way.

  voronoi   a 1.6 mm wall perforated with Voronoi cells (each cell's top is clamped to a <= 45 deg roof so nothing
            bridges far) — an open organic lattice for shades and planters
  litho     a lithophane band: the wall's thickness follows a picture (0.8 mm light, 3 mm dark) so it shows when lit
            from inside — LED shades, puck lamps, lanterns
  fuzzy     Bambu Studio's structured fuzzy skin (Perlin "orange peel", Billow, Ridged "marble", Voronoi "stone")
            switched on in height bands through layer ranges (verified on the CLI), smooth bands between"""
import math

import numpy as np
import trimesh

from . import halftone

STYLES = {
    "voronoi": dict(name="Voronoi", blurb="An organic lattice of cells cut through the wall"),
    "litho":   dict(name="Lithophane", blurb="The picture appears when it's lit from inside"),
    "fuzzy":   dict(name="Fuzzy skin", blurb="Slicer-made noise: orange peel, marble ridges or stone cells, in bands"),
}
NOISE = {"perlin": "Orange peel", "billow": "Billow", "ridgedmulti": "Marble", "voronoi": "Stone"}
LITHO = dict(t_min=0.8, t_max=3.0)


def _tube(zs, r_out, r_in, floor_t):
    """Closed solid between an outer and an inner surface (rings per z), floor up to floor_t."""
    n = len(r_out[0]); th = np.linspace(0, 2 * np.pi, n, endpoint=False); c, s = np.cos(th), np.sin(th)
    rings = [(z, r) for z, r in zip(zs, r_out)] + [(z, r) for z, r in zip(zs[::-1], r_in[::-1]) if z >= floor_t - 1e-9]
    if abs(rings[-1][0] - floor_t) > 1e-9:
        rings.append((floor_t, rings[-1][1]))
    V = np.vstack([np.column_stack([r * c, r * s, np.full(n, z)]) for z, r in rings])
    m = len(rings); j = np.arange(n); jn = (j + 1) % n; F = []
    for i in range(m - 1):
        a, b = i * n, (i + 1) * n
        F += [np.column_stack([a + j, a + jn, b + j]), np.column_stack([a + jn, b + jn, b + j])]
    cb, ct = len(V), len(V) + 1
    V = np.vstack([V, [[0, 0, zs[0]], [0, 0, floor_t]]])
    F += [np.column_stack([jn, j, np.full(n, cb)]), np.column_stack([(m - 1) * n + j, (m - 1) * n + jn, np.full(n, ct)])]
    mesh = trimesh.Trimesh(V, np.vstack(F), process=True)
    trimesh.repair.fix_normals(mesh)
    if mesh.volume < 0:
        mesh.invert()
    return mesh


def _plain(prof, height, rmax, wall, floor_t, n=None, dz=0.5):
    n = n or max(180, int(2 * math.pi * rmax / 1.0))
    zs = np.append(np.arange(0, height, dz), height)
    r_out = [np.full(n, prof(z)) for z in zs]; r_in = [np.full(n, max(prof(z) - wall, 1.0)) for z in zs]
    return _tube(zs, r_out, r_in, floor_t)


def _lum(image_path, picture, u, v):
    if image_path:
        from PIL import Image
        im = np.asarray(Image.open(image_path).convert("L"), float) / 255.0
        h, w = im.shape
        return im[np.clip(((1 - v) * (h - 1)).astype(int), 0, h - 1), np.clip((u * (w - 1)).astype(int), 0, w - 1)]
    if picture == "moon":                                         # soft built-in: a moon over hills
        d = np.hypot((u * 6 % 1.0) - 0.5, (v - 0.68) * 1.6)
        moon = np.clip(1 - d / 0.22, 0, 1) ** 0.6
        hills = (v < 0.3 + 0.08 * np.sin(2 * np.pi * u * 5) + 0.05 * np.sin(2 * np.pi * u * 13)).astype(float)
        return np.clip(0.15 + 0.85 * moon - 0.6 * hills, 0, 1)
    return 1.0 - halftone.picture(picture, u, v)


def build(shape, v, nz, style, options, draft=False):
    prof, height, rmax = shape.profile(v)
    floor_t = 1.6; info = {}
    if style == "litho":
        t0, t1 = LITHO["t_min"], LITHO["t_max"]
        n = max(240, int(2 * math.pi * rmax / (1.2 if draft else 0.4)))
        dz = 1.0 if draft else 0.3
        zs = np.append(np.arange(0, height, dz), height)
        u = np.linspace(0, 1, n, endpoint=False)
        band0, band1 = floor_t + 2.0, height - 2.0
        r_out, r_in = [], []
        for z in zs:
            R = prof(z)
            if band0 <= z <= band1:
                lum = _lum(options.get("image"), options.get("picture", "moon"), u, np.full(n, (z - band0) / (band1 - band0)))
                t = t1 - (t1 - t0) * lum                                 # bright -> thin
            else:
                t = np.full(n, t1)
            r_out.append(np.full(n, R)); r_in.append(np.maximum(R - t, 1.0))
        # overhang: going up, the inner surface may step inward (the wall thickening) at most 0.9 mm per mm;
        # thinning going up is free. Dark-above-light edges soften a little — normal for upright lithophanes.
        for k in range(1, len(r_in)):
            r_in[k] = np.maximum(r_in[k], r_in[k - 1] - 0.9 * (zs[k] - zs[k - 1]))
        mesh = _tube(zs, r_out, r_in, floor_t)
        info["note"] = "Lithophane: print in white or natural PLA and light it from inside with an LED."
        return mesh, [], info
    if style == "fuzzy":
        mesh = _plain(prof, height, rmax, 1.0, floor_t)
        noise = options.get("noise", "perlin"); layout = options.get("fuzzy_bands", "all")
        lh = nz.layer_h; snap = lambda z: round(z / lh) * lh
        if layout == "all":
            spans = [(floor_t + 2, height)]
        else:                                                      # alternate fuzzy / smooth bands
            k = 3 if layout == "thirds" else 6
            edges = [snap(floor_t + (height - floor_t) * i / k) for i in range(k + 1)]
            spans = [(edges[i], edges[i + 1]) for i in range(0, k, 2)]
        ranges = [(snap(a), snap(b), {"layer_height": f"{lh:.2f}", "fuzzy_skin": "external",
                                      "fuzzy_skin_noise_type": noise, "fuzzy_skin_thickness": "0.4",
                                      "fuzzy_skin_point_distance": "0.6"}) for a, b in spans]
        return mesh, ranges, info
    # voronoi
    import manifold3d as m3d
    from scipy.spatial import Voronoi
    from shapely.geometry import Polygon
    from .meshops import manifold_to_trimesh
    wall = 1.6
    base = _plain(prof, height, rmax, wall, floor_t, n=max(240, int(2 * math.pi * rmax / 0.8)))
    circ = 2 * math.pi * rmax; cell = {"small": 9.0, "medium": 13.0, "large": 18.0}.get(options.get("cell", "medium"), 13.0)
    z0, z1 = floor_t + 6.0, height - 6.0
    rng = np.random.default_rng(7)
    nx, ny = max(6, int(circ / cell)), max(2, int((z1 - z0) / cell))
    pts = np.array([[(i + 0.5 + 0.35 * rng.uniform(-1, 1)) * circ / nx, z0 + (j + 0.5 + 0.35 * rng.uniform(-1, 1)) * (z1 - z0) / ny]
                    for i in range(nx) for j in range(ny)])
    tiled = np.vstack([pts + [dx, 0] for dx in (-circ, 0, circ)])     # wrap around the cylinder
    vor = Voronoi(tiled); web = 1.6 if not draft else 2.5
    cutters = []
    for idx in range(len(pts), 2 * len(pts)):                        # cells of the middle copy only
        reg = vor.regions[vor.point_region[idx]]
        if -1 in reg or not reg:
            continue
        poly = Polygon(vor.vertices[reg]).intersection(Polygon([(-circ, z0), (2 * circ, z0), (2 * circ, z1), (-circ, z1)]))
        zc_ = float(np.mean(np.array(poly.exterior.coords)[:, 1])) if not poly.is_empty else z0
        poly = poly.buffer(-web / 2 * rmax / max(prof(zc_), 1.0), join_style=2)   # webs keep their width where the wall narrows
        if poly.is_empty or poly.area < 6 or poly.geom_type != "Polygon":
            continue
        # pointed roof: clip the hole's top to a 45 deg gable, so nothing above it has to bridge
        xs, ys = np.array(poly.exterior.coords).T
        xc, top, H = float(xs.mean()), float(ys.max()), 1000.0
        gable = Polygon([(xc - H, top - H), (xc, top), (xc + H, top - H)])            # the cell sits inside this triangle
        poly = poly.intersection(gable)
        if poly.is_empty or poly.area < 6 or poly.geom_type != "Polygon":
            continue
        from shapely.geometry.polygon import orient
        c_ = _radial_prism(orient(poly, 1.0), prof, wall, rmax)    # counter-clockwise, or manifold reads it empty
        if c_ is not None:
            cutters.append(c_)
    if cutters:
        cut = m3d.Manifold.batch_boolean(cutters, m3d.OpType.Add)
        body = m3d.Manifold(m3d.Mesh(vert_properties=np.asarray(base.vertices, np.float32), tri_verts=np.asarray(base.faces, np.int32)))
        base = manifold_to_trimesh(body - cut)
        bodies = base.split(only_watertight=False)
        if len(bodies) > 1:                                        # never ship a piece that falls out on the bed
            base = max(bodies, key=lambda b_: abs(b_.volume))
            info["islands_removed"] = len(bodies) - 1
    info["cells"] = len(cutters)
    return base, [], info


def _radial_prism(poly, prof, wall, rref, steps=24):
    """A hole cutter: the (arc-length, z) polygon pushed radially through the wall."""
    import manifold3d as m3d
    xs, zs = np.array(poly.exterior.coords[:-1]).T
    cs = m3d.CrossSection([np.column_stack([xs, zs]).tolist()])
    if cs.area() <= 0:
        return None
    # build as extruded 2D polygon in a local frame, then bend: sample radially as a lofted solid
    depth = wall + 3.0
    ext = m3d.Manifold.extrude(cs, depth).translate([0, 0, -depth / 2])     # x = arc, y = z, z = radial
    def warp(p):
        a, zz, rr = p[0], p[1], p[2]
        r = prof(float(zz)) - wall / 2 + rr
        th = a / rref                                              # cells are laid out by angle
        return [r * math.cos(th), r * math.sin(th), zz]
    return ext.refine_to_length(2.0).warp(warp)
