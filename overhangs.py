"""Steep-face area per part in its print orientation, by feature region (world coords)."""
import sys, json, numpy as np, trimesh
M_ALL = json.load(open('split_transforms.json'))
sys.argv, _argv = ['x', '2', '1.0'], sys.argv
import kaiju_head as K
VOX = 1.0; XS, YS, ZS, _, _, _, F, _, _ = K.fields(VOX, with_ears=True); sys.argv = _argv
def run(name):
    tm = trimesh.load(f'sofubi_ape_{name}.stl', force='mesh', process=False)
    n = tm.face_normals; a = tm.area_faces; c = tm.triangles_center
    Mi = np.linalg.inv(np.array(M_ALL[name])); w = (Mi @ np.c_[c, np.ones(len(c))].T).T[:, :3]
    ang = np.degrees(np.arcsin(np.clip(-n[:, 2], -1, 1)))
    # EXTERIOR faces only: step 1.5 mm along the face normal (in world) and ask the
    # smooth solid whether that point is inside. Inner-skin normals point into
    # the cavity (inside the solid); outer-skin normals point out. The flat bed
    # face of the part is excluded too (it sits on the plate).
    nw = (Mi[:3, :3] @ n.T).T
    probe = w + 1.5 * nw
    ix = np.clip(np.round((probe[:, 0] - XS[0]) / VOX).astype(int), 0, len(XS) - 1)
    iy = np.clip(np.round((probe[:, 1] - YS[0]) / VOX).astype(int), 0, len(YS) - 1)
    iz = np.clip(np.round((probe[:, 2] - ZS[0]) / VOX).astype(int), 0, len(ZS) - 1)
    exterior = F[ix, iy, iz] > 0
    bed = c[:, 2] < 0.6
    keep = exterior & ~bed
    a = np.where(keep, a, 0.0)
    s45 = (ang > 45) & keep; s65 = (ang > 65) & keep
    fy = -w[:, 1]; x = w[:, 0]; z = w[:, 2]
    tot = a.sum(); print(f"{name}: exterior {tot:.0f} mm² · {a[s45].sum():.0f} mm² >45° ({100*a[s45].sum()/tot:.1f}%) · {a[s65].sum():.0f} mm² >65° ({100*a[s65].sum()/tot:.1f}%)")
    R = {'ears': np.abs(x) > 60, 'crest/top (z>128)': z > 128, 'fur sides (|x| 30-60, behind the eyes)': (np.abs(x) > 30) & (fy < 40) & (z > 45),
         'brow/eyes': (np.abs(x) <= 52) & (z > 88) & (fy > 40), 'muzzle/mouth/lip': (np.abs(x) <= 52) & (z > 45) & (z <= 88) & (fy > 40),
         'cheeks/jaw sides': (np.abs(x) > 30) & (z < 60), 'below z 45': z <= 45}
    seen = np.zeros(len(a), bool)
    for k, m in R.items():
        m = m & ~seen; seen |= m
        if a[s45 & m].sum() > 30: print(f"   {k:44} >45° {a[s45 & m].sum():6.0f}   >65° {a[s65 & m].sum():6.0f}")
    if a[s45 & ~seen].sum() > 30: print(f"   {'other':44} >45° {a[s45 & ~seen].sum():6.0f}   >65° {a[s65 & ~seen].sum():6.0f}")
for n in sys.argv[1:]: run(n)
