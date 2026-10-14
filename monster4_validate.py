"""Validation overlay: render the model with a calibrated ORTHOGRAPHIC camera at the photo's angle, align to the
photo (base centre x, bed y, horn tip = 200 mm), then crop the mouth/face region of both at the same scale, draw
mm gridlines (z from the bed, x from the base centre) on both, and a 50 % blend. Usage: monster4_validate.py STL out.jpg"""
import sys, numpy as np, trimesh, pyrender
from PIL import Image, ImageDraw, ImageFont
stl, out = sys.argv[1], sys.argv[2]
VIEW = sys.argv[3] if len(sys.argv) > 3 else "front"
AZ, PITCH = {"front": (0, 6), "threequarter": (40, 8), "profile": (90, 4), "back": (180, 6)}[VIEW]
FULL = "--full" in sys.argv
CROP = {"front": ((-130, 130), (0, 205)), "threequarter": ((-150, 120), (0, 205)), "profile": ((-100, 100), (0, 205)), "back": ((-130, 130), (0, 205))}[VIEW] if FULL else {"front": ((-70, 70), (45, 115)), "threequarter": ((-70, 70), (50, 140)), "profile": ((-40, 100), (40, 140)), "back": ((-130, 130), (0, 205))}[VIEW]   # (x0,x1),(z0,z1) mm
tm = trimesh.load(stl, force="mesh")
W = H = 1600
def render(shaded):
    """near-orthographic: perspective camera 40 R away with a matching narrow fov; studio-style 3-light rig"""
    az, pt = np.radians(AZ), np.radians(PITCH)
    d = np.array([-np.sin(az) * np.cos(pt), -np.cos(az) * np.cos(pt), np.sin(pt)])
    ctr = tm.bounding_box.centroid; R = float(np.linalg.norm(tm.extents)) / 2
    dist = 40.0 * R; half = R * 1.05; yfov = 2 * np.arctan(half / dist)
    def look_at(eye, target, up=np.array([0, 0, 1.0])):
        f = target - eye; f /= np.linalg.norm(f); s = np.cross(f, up); s /= np.linalg.norm(s); u = np.cross(s, f)
        M = np.eye(4); M[:3, 0] = s; M[:3, 1] = u; M[:3, 2] = -f; M[:3, 3] = eye; return M
    scene = pyrender.Scene(bg_color=[1, 1, 1, 1], ambient_light=[0.12, 0.12, 0.12])
    mat = pyrender.MetallicRoughnessMaterial(baseColorFactor=[0.84, 0.81, 0.74, 1], metallicFactor=0, roughnessFactor=0.8)
    scene.add(pyrender.Mesh.from_trimesh(tm, material=mat, smooth=False))
    scene.add(pyrender.PerspectiveCamera(yfov=yfov, aspectRatio=1.0, znear=dist - 3 * R, zfar=dist + 3 * R), pose=look_at(ctr + d * dist, ctr))
    if shaded:
        s_ = np.cross(-d, np.array([0, 0, 1.0])); s_ /= np.linalg.norm(s_); u_ = np.array([0, 0, 1.0])
        scene.add(pyrender.DirectionalLight(color=[1, 0.97, 0.92], intensity=4.2), pose=look_at(ctr + (d * 1.0 - s_ * 0.9 + u_ * 1.2) * R * 5, ctr))
        scene.add(pyrender.DirectionalLight(color=[0.92, 0.94, 1.0], intensity=1.8), pose=look_at(ctr + (d * 1.0 + s_ * 1.1 + u_ * 0.5) * R * 5, ctr))
        scene.add(pyrender.DirectionalLight(color=[1, 1, 1], intensity=1.2), pose=look_at(ctr + (d * 1.0 + u_ * 0.1) * R * 5, ctr))
    r = pyrender.OffscreenRenderer(W, H); color, depth = r.render(scene); r.delete()
    return color, depth > 0, (2 * half) / W
color, mask, mmpx_m = render(True)
# ---- alignment keypoints (same as monster4_map): base centre x, bed y, tip y
def keypoints(m):
    ys, xs = np.where(m); x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    rows = m[int(y1 - 0.12 * (y1 - y0)):y1 + 1]; cx = np.where(rows)[1].mean(); return cx, y1, y0
ph = np.asarray(Image.open(f"refs/monster4/{VIEW}.png").convert("RGB")).astype(int); pm = ph.sum(-1) < 600
pcx, pbed, ptip = keypoints(pm); mcx, mbed, mtip = keypoints(mask)
mm_p = 200.0 / (pbed - ptip); mm_m = 200.0 / (mbed - mtip)
def crop_mm(img, cx, bed, mmpx, box, size):
    (x0, x1), (z0, z1) = box
    px0, px1 = cx + x0 / mmpx, cx + x1 / mmpx; py0, py1 = bed - z1 / mmpx, bed - z0 / mmpx
    return Image.fromarray(np.asarray(img).astype(np.uint8)).crop((int(px0), int(py0), int(px1), int(py1))).resize(size, Image.LANCZOS)
(x0, x1), (z0, z1) = CROP; S = 4 if FULL else 8; size = (int((x1 - x0) * S), int((z1 - z0) * S))
A = crop_mm(ph, pcx, pbed, mm_p, CROP, size); B = crop_mm(color, mcx, mbed, mm_m, CROP, size)
def grid(im, label):
    d = ImageDraw.Draw(im)
    for z in range(z0, z1 + 1, 10):
        y = (z1 - z) * S; d.line([(0, y), (im.width, y)], fill=(255, 40, 40) if z % 20 == 0 else (255, 150, 150), width=2 if z % 20 == 0 else 1)
        d.text((4, y - 12), f"z{z}", fill=(255, 40, 40))
    for x in range(x0, x1 + 1, 10):
        xx = (x - x0) * S; d.line([(xx, 0), (xx, im.height)], fill=(60, 120, 255) if x % 20 == 0 else (160, 190, 255), width=2 if x % 20 == 0 else 1)
        if x % 20 == 0: d.text((xx + 3, 4), f"x{x:+d}", fill=(60, 120, 255))
    d.text((im.width - 160, im.height - 20), label, fill=(0, 0, 0))
    return im
blend = Image.blend(A.convert("RGB"), B.convert("RGB"), 0.5)
A = grid(A.convert("RGB"), "PHOTO"); B = grid(B.convert("RGB"), "MODEL"); blend = grid(blend, "50/50 BLEND")
sheet = Image.new("RGB", (size[0] * 3 + 40, size[1]), (30, 30, 30))
sheet.paste(A, (0, 0)); sheet.paste(B, (size[0] + 20, 0)); sheet.paste(blend, (size[0] * 2 + 40, 0)); sheet.save(out, quality=90)
print(f"validation {VIEW}: photo {mm_p:.3f} mm/px, model {mm_m:.3f} mm/px → {out}")
