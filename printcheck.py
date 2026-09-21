"""
A slicer's-eye printability check, per part, in its export orientation.
Slices the mesh into layers and asks the two questions that decide whether
an FDM print survives:
  ISLANDS   a region on layer N with NO material under it on layer N-1 —
            it starts in mid-air and is extruded onto nothing. Fatal unless
            supported.
  OVERHANG  the part of a region that hangs past the layer below by more
            than a 50° slope allows — droops, curls, may fail.
Also flags first-layer contact and the thinnest cross-section features.
"""
import sys, numpy as np, trimesh
from shapely.geometry import Polygon, MultiPolygon
from shapely.ops import unary_union

STEP = 0.4              # analysis layer (mm); overhang tolerance scales with it
MAX_SLOPE = 50.0        # degrees from vertical the printer holds unsupported
ISLAND_MIN = 2.0        # mm² — below this a start-in-air is a fur tip that fuses next layer, a warning not a failure

def layer_polys(tm, z):
    s = tm.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
    if s is None: return None
    # project with the print frame's own axes so 2D x/y ARE print x/y
    p2, _ = s.to_planar(to_2D=np.array([[1,0,0,0],[0,1,0,0],[0,0,1,-z],[0,0,0,1]], float))
    return unary_union([p for p in p2.polygons_full if p.is_valid and p.area > 0]) if p2.polygons_full else None

def to_world(name, pt):
    import json, os
    if not os.path.exists("split_transforms.json"): return pt
    M = np.array(json.load(open("split_transforms.json")).get(name, np.eye(4)))
    w = np.linalg.inv(M) @ np.array([pt[0], pt[1], pt[2], 1.0])
    return tuple(round(float(v), 1) for v in w[:3])

def check(path, name=""):
    tm = trimesh.load(path, force="mesh")
    zmin, zmax = tm.bounds[0][2], tm.bounds[1][2]
    grow = STEP * np.tan(np.radians(MAX_SLOPE))
    zs = np.arange(zmin + STEP * 0.5, zmax, STEP)
    prev = None; islands = []; warns = 0; oh_area = 0.0; oh_layers = 0; first = None; thin = []; worst = (0.0, 0.0)
    for i, z in enumerate(zs):
        cur = layer_polys(tm, z)
        if cur is None or cur.is_empty: prev = None; continue
        if first is None: first = cur.area
        geoms = list(cur.geoms) if isinstance(cur, MultiPolygon) else [cur]
        if prev is not None and not prev.is_empty:
            supp = prev.buffer(grow)
            for g in geoms:
                if not g.intersects(prev):                 # nothing under it at all
                    if g.area < ISLAND_MIN: warns += 1
                    else:
                        c = g.centroid.coords[0]
                        islands.append((round(z - zmin, 1), round(g.area, 1), to_world(name, (c[0], c[1], z))))
                else:
                    hang = g.difference(supp)
                    if hang.area > 0.5:
                        oh_area += hang.area; oh_layers += 1
                        # how far past the layer below does it reach → the true slope
                        reach = hang.hausdorff_distance(prev) if not prev.is_empty else 0.0
                        ang = np.degrees(np.arctan(reach / STEP))
                        if ang > worst[0]: worst = (round(float(ang), 0), round(z - zmin, 1))
        # thin features: any region narrower than ~2 perimeters
        for g in geoms:
            if 0.3 < g.area < 3.0 and g.length > 0:
                w = 4 * g.area / g.length   # rough min width
                if w < 0.9: thin.append((round(z - zmin, 1), round(w, 2)))
        prev = cur
    return dict(height=round(zmax - zmin, 1), layers=len(zs), first_layer_mm2=round(first or 0, 0),
                islands=islands, tip_warnings=warns, overhang_mm2=round(oh_area, 0), overhang_layers=oh_layers,
                worst_slope_deg=worst[0], worst_slope_z=worst[1], thin=thin[:6])

if __name__ == "__main__":
    import json
    out = {}
    for name in sys.argv[1:]:
        r = check(f"sofubi_ape_{name}.stl", name); out[name] = r
        v = "PASS" if not r["islands"] else f"FAIL — {len(r['islands'])} island(s)"
        print(f"{name:5} h {r['height']:6.1f}  first layer {r['first_layer_mm2']:6.0f} mm²  overhang {r['overhang_mm2']:6.0f} mm² on {r['overhang_layers']:3d} layers, worst {r['worst_slope_deg']:.0f}° at z+{r['worst_slope_z']}  tips {r['tip_warnings']}  → {v}")
        for z, a, c in r["islands"][:12]: print(f"        island {a:5.1f} mm² at print z+{z:5.1f} — world (x {c[0]}, y {c[1]}, z {c[2]})")
    json.dump(out, open("printcheck.json", "w"), indent=1)
