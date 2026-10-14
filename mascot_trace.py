"""Trace the ears off refs/mascot/front.png (200 mm bed→horn-tip, base centre x = 0) → refs/mascot/front_trace.json"""
import numpy as np, json
from PIL import Image
from skimage import measure
from shapely.geometry import Polygon
a = np.asarray(Image.open("refs/mascot/front.png").convert("RGB")).astype(int)
mask = a.sum(-1) < 720
ys, xs = np.where(mask); x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
rows = mask[int(y1 - 0.12 * (y1 - y0)):y1 + 1]; cx = np.where(rows)[1].mean()
mmpp = 200.0 / (y1 - y0)
def to_mm(px, py): return ((px - cx) * mmpp, (y1 - py) * mmpp)
xmm = (np.arange(mask.shape[1]) - cx) * mmpp
out = {"mmpp": mmpp}
for name, sel in (("left", xmm < -50), ("right", xmm > 56)):
    ear = mask & sel[None, :]
    lab = measure.label(ear); reg = sorted(measure.regionprops(lab), key=lambda p: -p.area)[0]
    c = max(measure.find_contours((lab == reg.label).astype(float), 0.5), key=len)
    pg = Polygon([to_mm(p[1], p[0]) for p in c]).simplify(1.2)
    poly = [(round(px, 1), round(pz, 1)) for px, pz in pg.exterior.coords[:-1]]
    out[f"ear_{name}_xz"] = poly
    print(f"{name} ear: {len(poly)} pts, x {min(p[0] for p in poly):.1f}..{max(p[0] for p in poly):.1f}, z {min(p[1] for p in poly):.1f}..{max(p[1] for p in poly):.1f}")
    print(poly)
json.dump(out, open("refs/mascot/front_trace.json", "w"))
