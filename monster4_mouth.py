"""Mouth precheck: build ONLY the mouth region of monster4 on a fine grid (no hollowing), render
front / three-quarter / profile close-ups beside the reference crops. Seconds per iteration."""
import sys, os, numpy as np, trimesh
sys.argv = [sys.argv[0], "2"]
import monster4 as M
from skimage import measure
sys.path.insert(0, "tools"); from studio_render import render
from PIL import Image
VOX = 0.4
xs = np.arange(-78 + VOX/2, 78, VOX, np.float32); ys = np.arange(-98 + VOX/2, -25, VOX, np.float32); zs = np.arange(48 + VOX/2, 124, VOX, np.float32)
X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")
f = M.field(np.stack([X, Y, Z], -1))
f = np.maximum(f, Y + 26.0)             # keep world y < -26 (the face front); closed slab
tm = M.mesh_from(f, xs, ys, zs, VOX, keep_largest=True)
SM = int(os.environ.get("M4_SMOOTH", "0"))
if SM: trimesh.smoothing.filter_taubin(tm, lamb=0.5, nu=-0.53, iterations=SM)
tm.export("monster4_mouth.stl")
T = "/private/tmp/claude-501/-Users-collin/6a2fc169-fe21-45af-9912-2bd0b7ac69ed/scratchpad"
render("monster4_mouth.stl", f"{T}/mf.jpg", 900, 600, 180, -4); render("monster4_mouth.stl", f"{T}/mq.jpg", 900, 600, -140, -10); render("monster4_mouth.stl", f"{T}/mp.jpg", 600, 700, -92, -4)
pf = Image.open(f"{T}/ref_mouth_front.png").resize((900, 492)); pq = Image.open(f"{T}/ref_mouth_3q.png").resize((900, 548)); pp = Image.open(f"{T}/ref_mouth_profile.png").resize((420, 552))
s = Image.new("RGB", (1800, 600 + 600 + 700 + 40), (28, 24, 22))
s.paste(pf, (0, 54)); s.paste(Image.open(f"{T}/mf.jpg"), (900, 0)); s.paste(pq, (0, 620 + 26)); s.paste(Image.open(f"{T}/mq.jpg"), (900, 620)); s.paste(pp, (0, 1240 + 74)); s.paste(Image.open(f"{T}/mp.jpg"), (900, 1240))
s.save("monster4_mouth_pair.jpg", quality=90); print(f"mouth precheck: {len(tm.faces):,} faces")
