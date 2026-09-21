"""Maker's mark: text debossed 0.6 mm into the underside of the base (the
bed face — the classic place for a sofubi stamp; the letters are holes in
the first four layers, which print perfectly). Run after kaiju_split.py."""
import sys, numpy as np, trimesh
from matplotlib.textpath import TextPath
from matplotlib.font_manager import FontProperties
from shapely.geometry import Polygon
TEXT = sys.argv[1] if len(sys.argv) > 1 else "co.stil  2026"
H, DEPTH = 7.0, 0.6
tp = TextPath((0, 0), TEXT, size=H, prop=FontProperties(family="DejaVu Sans", weight="bold"))
rings = [Polygon(r) for r in tp.to_polygons() if len(r) > 3]
rings.sort(key=lambda p: -p.area)
outers = []
for r in rings:
    holder = next((o for o in outers if o["poly"].contains(r.representative_point())), None)
    if holder: holder["holes"].append(r.exterior.coords)
    else: outers.append({"poly": r, "holes": []})
letters = [trimesh.creation.extrude_polygon(Polygon(o["poly"].exterior.coords, o["holes"]), DEPTH + 0.6) for o in outers]
text = trimesh.util.concatenate(letters)
b = text.bounds; text.apply_translation((-(b[0][0] + b[1][0]) / 2, -(b[0][1] + b[1][1]) / 2, -0.6))
# mirror so it reads correctly looking AT the underside, place at the back of the footprint
text.apply_transform(np.diag([-1, 1, 1, 1])); text.apply_translation((0, 38.0, 0))
base = trimesh.load("sofubi_ape_base.stl", force="mesh")
out = base
for l in letters:
    pass
out = base.difference(text, engine="manifold")
import manifold3d as m3d
mm = m3d.Manifold(m3d.Mesh(np.asarray(out.vertices, np.float32), np.asarray(out.faces, np.uint32)))
print(f"mark '{TEXT}' {text.extents[0]:.1f} x {text.extents[1]:.1f} mm on the underside · base manifold3d={mm.status()} · {len(out.faces):,} faces")
out.export("sofubi_ape_base.stl")
