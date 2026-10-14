"""mobi labs wordmark as 2D geometry, traced from the supplied artwork.

trace_logo() returns a shapely (Multi)Polygon in mm, logo width = `width`, centred on (0,0),
y up — ready to be extruded as a lid inlay (two-colour) or an emboss. Counters (the holes in
o, b, a) are preserved as polygon interiors."""
import pathlib
import numpy as np
from PIL import Image
from shapely import affinity
from shapely.geometry import Polygon
from shapely.ops import unary_union
from skimage import measure

SOURCE = pathlib.Path("/private/tmp/claude-501/-Users-collin/775f6561-0ebb-4666-a7a2-8c36f08c71d8/scratchpad/mobi_logo.png")
LOCAL  = pathlib.Path(__file__).with_name("mobi_logo_src.png")   # kept beside the script


def trace_logo(width=60.0, simplify_px=0.6, min_area_px=30.0):
    src = LOCAL if LOCAL.exists() else SOURCE
    a = np.array(Image.open(src).convert("L")).astype(float)
    ink = (a < 128).astype(float)
    # pad so contours on the border close; find_contours on the 0.5 level gives sub-pixel outlines
    ink = np.pad(ink, 2)
    rings = []
    for c in measure.find_contours(ink, 0.5):
        poly = Polygon([(x, -y) for y, x in c])      # image y down -> y up
        if poly.is_valid and poly.area >= min_area_px:
            rings.append(poly.simplify(simplify_px))
    # even-odd assembly: outer rings minus the rings inside them (the counters)
    rings.sort(key=lambda p: -p.area)
    shapes = []
    for p in rings:
        parent = next((s for s in shapes if s.contains(p.representative_point())), None)
        if parent is None:
            shapes.append(p)
        else:
            shapes[shapes.index(parent)] = parent.difference(p)
    geom = unary_union(shapes).buffer(0)
    minx, miny, maxx, maxy = geom.bounds
    s = width / (maxx - minx)
    geom = affinity.scale(geom, s, s, origin=(0, 0))
    minx, miny, maxx, maxy = geom.bounds
    return affinity.translate(geom, -(minx + maxx) / 2, -(miny + maxy) / 2)


if __name__ == "__main__":
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    g = trace_logo(60.0)
    polys = list(g.geoms) if hasattr(g, "geoms") else [g]
    print(f"{len(polys)} shapes, {sum(len(p.interiors) for p in polys)} counters, bounds {tuple(round(b,2) for b in g.bounds)} mm")
    # thinnest stroke: largest inward buffer that still leaves something, per shape
    for p in polys:
        d = 0.0
        while not p.buffer(-(d + 0.05)).is_empty:
            d += 0.05
        print(f"  shape area {p.area:7.1f} mm2  min stroke ~{2*d:.2f} mm  bounds x {p.bounds[0]:6.1f}..{p.bounds[2]:6.1f}")
    fig, ax = plt.subplots(figsize=(8, 5))
    for p in polys:
        ax.fill(*p.exterior.xy, color="#222"); [ax.fill(*h.xy, color="white") for h in p.interiors]
    ax.set_aspect("equal"); ax.grid(True, alpha=.3); ax.set_title("mobi labs trace @ 60 mm wide")
    fig.savefig("mobi_logo_trace.png", dpi=120, bbox_inches="tight")
