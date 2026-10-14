"""
Live mapping: render the model's SILHOUETTE from the four photo angles with an
orthographic camera, overlay it on the photo's silhouette (scaled so the bed→horn-tip
heights match, centred on the horn tip), score IoU, and print the width error per
height row. Usage: python monster4_map.py monster4_p2.stl out_prefix
"""
import sys, os, numpy as np, trimesh, pyrender
from PIL import Image

stl, out = sys.argv[1], sys.argv[2]
tm = trimesh.load(stl, force="mesh")
VIEWS = {  # name: (camera azimuth from the front (deg, + toward the monster's left/-X side), pitch above horizontal)
    "front": (0, 6), "threequarter": (40, 8), "profile": (90, 4), "back": (180, 6)}
W = H = 1000

def ref_mask(name):
    a = np.asarray(Image.open(f"refs/monster4/{name}.png").convert("RGB")).astype(int)
    return a.sum(-1) < 600

def render_mask(az, pitch):
    az, pt = np.radians(az), np.radians(pitch)
    d = np.array([-np.sin(az) * np.cos(pt), -np.cos(az) * np.cos(pt), np.sin(pt)])   # unit vector from the model to the camera
    up = np.array([0, 0, 1.0]); f = -d; s = np.cross(f, up); s /= np.linalg.norm(s); u = np.cross(s, f)
    ctr = tm.bounding_box.centroid; R = float(np.linalg.norm(tm.extents)) / 2
    M = np.eye(4); M[:3, 0] = s; M[:3, 1] = u; M[:3, 2] = -f; M[:3, 3] = ctr + d * (R * 3)
    scene = pyrender.Scene(bg_color=[0, 0, 0, 0], ambient_light=[1, 1, 1])
    scene.add(pyrender.Mesh.from_trimesh(tm, material=pyrender.MetallicRoughnessMaterial(baseColorFactor=[1, 1, 1, 1])))
    scene.add(pyrender.OrthographicCamera(xmag=R * 1.05, ymag=R * 1.05, znear=0.1, zfar=R * 10), pose=M)
    r = pyrender.OffscreenRenderer(W, H); _, depth = r.render(scene); r.delete()
    return depth > 0, (2 * R * 1.05) / W          # mask, mm per pixel

def bbox(m):
    ys, xs = np.where(m); return xs.min(), xs.max(), ys.min(), ys.max()

def keypoints(m):
    """base centre x (bottom 12 % of rows), bed y, horn tip y (topmost pixel within the central 16 % column band)"""
    x0, x1, y0, y1 = bbox(m); rows = m[int(y1 - 0.12 * (y1 - y0)):y1 + 1]
    cx = np.where(rows)[1].mean(); band = 0.08 * (x1 - x0)
    tip = y0                                            # the horn is the highest point in every photo
    return cx, y1, tip

def align(ref, mod):
    """scale/shift the model mask so bed→horn-tip matches the photo and the base centre lines up"""
    rcx, rbed, rtip = keypoints(ref); mcx, mbed, mtip = keypoints(mod)
    sc = (rbed - rtip) / (mbed - mtip)
    im = Image.fromarray(mod.astype(np.uint8) * 255).resize((int(mod.shape[1] * sc), int(mod.shape[0] * sc)))
    out = np.zeros_like(ref); a = np.asarray(im) > 127
    dx = int(round(rcx - mcx * sc)); dy = int(round(rbed - mbed * sc))
    ys, xs = np.where(a); xs = xs + dx; ys = ys + dy
    ok = (xs >= 0) & (xs < ref.shape[1]) & (ys >= 0) & (ys < ref.shape[0]); out[ys[ok], xs[ok]] = True
    return out, sc

report = []
for name, (az, pitch) in VIEWS.items():
    ref = ref_mask(name); mod, mmpp = render_mask(az, pitch); mod2, sc = align(ref, mod)
    iou = (ref & mod2).sum() / (ref | mod2).sum()
    rgb = np.full(ref.shape + (3,), 255, np.uint8)
    rgb[ref & ~mod2] = (60, 170, 70)      # photo only = green (model is missing this)
    rgb[mod2 & ~ref] = (220, 60, 160)     # model only = magenta (model has extra)
    rgb[ref & mod2] = (150, 150, 150)
    Image.fromarray(rgb).save(f"{out}_{name}.png")
    rcx, ry1, ry0 = keypoints(ref); mm_per_px_ref = 200.0 / (ry1 - ry0); rx0 = rcx   # x measured from the base centre, mm
    lines = [f"== {name}  IoU {iou:.3f}   (green = photo only / missing, magenta = model only / extra)"]
    for fr in np.linspace(0.02, 0.98, 25):
        y = int(ry0 + fr * (ry1 - ry0)); z = 200 * (1 - fr)
        rr = np.where(ref[y])[0]; mm = np.where(mod2[y])[0]
        if len(rr) == 0 and len(mm) == 0: continue
        def ext(v): return (np.nan, np.nan) if len(v) == 0 else ((v.min() - rx0) * mm_per_px_ref, (v.max() - rx0) * mm_per_px_ref)
        (rl, rr_), (ml, mr) = ext(rr), ext(mm)
        lines.append(f"  z {z:5.0f}  photo L {rl:6.1f} R {rr_:6.1f}  model L {ml:6.1f} R {mr:6.1f}   dL {ml-rl:+6.1f} dR {mr-rr_:+6.1f}")
    report += lines
open(f"{out}_report.txt", "w").write("\n".join(report)); print("\n".join(l for l in report if l.startswith("==")))
# contact sheet of the four overlays
tiles = [Image.open(f"{out}_{n}.png").resize((700, 700)) for n in VIEWS]
sheet = Image.new("RGB", (2800, 700), (255, 255, 255))
for i, t in enumerate(tiles): sheet.paste(t, (i * 700, 0))
sheet.save(f"{out}_sheet.jpg", quality=88)
