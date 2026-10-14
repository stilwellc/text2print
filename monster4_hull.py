"""Visual hull from Collin's four renders: each photo's silhouette is back-projected along its calibrated
(near-orthographic) camera and intersected on the sculpt voxel grid; profile and three-quarter are also
mirrored (symmetry) → 6 view cones. Output: hull_sdf.npy (signed distance, mm; − inside) + hull_meta.json."""
import sys, json, numpy as np
from PIL import Image
from scipy import ndimage
VOX = float(sys.argv[1]) if len(sys.argv) > 1 else 0.6
AZ3 = float(sys.argv[2]) if len(sys.argv) > 2 else 40.0      # three-quarter camera azimuth (deg from the front toward the monster's -X side)
GRID = dict(x=(-142, 142), y=(-100, 92), z=(-2, 206))
h = 0.5 * VOX
xs = np.arange(GRID["x"][0] + h, GRID["x"][1], VOX, np.float32); ys = np.arange(GRID["y"][0] + h, GRID["y"][1], VOX, np.float32); zs = np.arange(GRID["z"][0] + h, GRID["z"][1], VOX, np.float32)
X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")            # WORLD frame (face looks toward -Y)
BASE_C = np.array([0.0, 4.0, 0.0])                            # the column centre in world (sculpt yc = -4)
def mask_of(name, mirror):
    a = np.asarray(Image.open(f"refs/monster4/{name}.png").convert("RGB")).astype(int); m = ndimage.binary_fill_holes(a.sum(-1) < 600)
    return m[:, ::-1] if mirror else m
def keypoints(m):
    ys_, xs_ = np.where(m); x0, x1, y0, y1 = xs_.min(), xs_.max(), ys_.min(), ys_.max()
    rows = m[int(y1 - 0.12 * (y1 - y0)):y1 + 1]; cx = np.where(rows)[1].mean(); return cx, y1, y0
VIEWS = [("front", 0, 6, False), ("profile", 90, 4, False), ("profile", -90, 4, True), ("threequarter", AZ3, 8, False), ("threequarter", -AZ3, 8, True)]   # back render dropped: it contradicts the front on the ear tips
solid = np.ones(X.shape, bool)
report = {}
for name, az, pitch, mirror in VIEWS:
    m = mask_of(name, mirror); pcx, pbed, ptip = keypoints(m); mmpx = 200.0 / (pbed - ptip)
    a, p = np.radians(az), np.radians(pitch)
    d = np.array([-np.sin(a) * np.cos(p), -np.cos(a) * np.cos(p), np.sin(p)])       # model → camera
    f = -d; s = np.cross(f, np.array([0, 0, 1.0])); s /= np.linalg.norm(s); u = np.cross(s, f)
    # image offset: the base bottom rim projects to the photo's bed row (lowest point) and base-centre column
    th = np.linspace(0, 2 * np.pi, 360); rim = np.stack([BASE_C[0] + 50 * np.cos(th), BASE_C[1] + 54 * np.sin(th), np.zeros_like(th)], 1)
    X0 = float((rim @ s).mean()); Y0 = float((rim @ u).min())
    Ximg = X * s[0] + Y * s[1] + Z * s[2]; Yimg = X * u[0] + Y * u[1] + Z * u[2]
    px = np.rint(pcx + (Ximg - X0) / mmpx).astype(np.int32); py = np.rint(pbed - (Yimg - Y0) / mmpx).astype(np.int32)
    inb = (px >= 0) & (px < m.shape[1]) & (py >= 0) & (py < m.shape[0])
    inside = np.zeros(X.shape, bool); inside[inb] = m[py[inb], px[inb]]
    solid &= inside
    report[f"{name}{'_mirror' if mirror else ''}"] = dict(mmpx=round(mmpx, 4), az=az, pitch=pitch)
    print(f"  {name:13s} az {az:6.1f} mirror={mirror}  kept {inside.mean()*100:5.1f}% of grid  → hull {solid.mean()*100:5.2f}%")
solid &= Z >= 0
# signed distance (mm), lightly smoothed so the view-cone creases round off
dist_out = ndimage.distance_transform_edt(~solid) * VOX; dist_in = ndimage.distance_transform_edt(solid) * VOX
sdf = (dist_out - dist_in).astype(np.float32)
sdf = ndimage.gaussian_filter(sdf, sigma=float(sys.argv[3]) if len(sys.argv) > 3 else 5.0)   # rounds the view-cone ridges; ~3 mm outline tolerance
np.save("hull_sdf.npy", sdf); json.dump(dict(grid=GRID, vox=VOX, views=report), open("hull_meta.json", "w"), indent=1)
print("hull volume", round(float(solid.sum()) * VOX**3 / 1000, 1), "cm³ · saved hull_sdf.npy", sdf.shape)
