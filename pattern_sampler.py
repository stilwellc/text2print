"""Render sampler for the woven-rod patterns in textures/rodweave.py: one 90 mm tile per pattern on one sheet.
Run: .venv/bin/python pattern_sampler.py [pattern ...]   ->  pattern_<name>.png + pattern_sampler_sheet.png"""
import sys
import numpy as np, trimesh
sys.path.insert(0, "."); sys.path.insert(0, "tools")
from textures import rodweave as rw

KEEP = ["kagome", "polar", "ripple", "selvedge", "beat", "overunder", "tartan"]   # Collin's keepers (Oct 2026)
TITLES = {"grid": "Base grid", "kagome": "Kagome (3 directions)", "helix": "Helical twist (6° per course)",
          "polar": "Polar: rings + rose-window spokes", "ripple": "Rippled courses", "selvedge": "Selvedge loops at the edge",
          "beat": "Beat frequency (3.6 vs 4.25 pitch)", "ombre": "Structural ombre (thins toward the rim)",
          "overunder": "True over-under weave", "tartan": "Tartan (3/1 x 2/2)"}
TILE, TH, CORNER = 90.0, 12.0, 14.0


def render_tile(rods, title, path, res=1000):
    import pyrender
    from PIL import Image, ImageDraw
    import preview as pv
    scene = pyrender.Scene(bg_color=[245, 242, 238, 255], ambient_light=[0.45] * 3)
    groups = {}
    for m, c in rods:
        groups.setdefault(c, []).append(m)
    for c, ms in groups.items():
        rgb = [(int(c[k:k + 2], 16) / 255) ** 2.2 for k in (1, 3, 5)]
        mat = pyrender.MetallicRoughnessMaterial(baseColorFactor=rgb + [1.0], metallicFactor=0.0, roughnessFactor=0.8)
        scene.add(pyrender.Mesh.from_trimesh(trimesh.util.concatenate(ms), material=mat, smooth=False))
    tgt = np.array([0, 0, TH / 2]); d = np.array([1.0, -0.9, 0.8]); d /= np.linalg.norm(d)
    pose = pv._look_at(tgt + d * 150, tgt)
    scene.add(pyrender.PerspectiveCamera(yfov=np.radians(42)), pose=pose)
    scene.add(pyrender.DirectionalLight(color=np.ones(3), intensity=3.5), pose=pose)
    r = pyrender.OffscreenRenderer(res, res)
    try:
        colr, _ = r.render(scene)
    finally:
        r.delete()
    im = Image.fromarray(colr); ImageDraw.Draw(im).text((18, 14), title, fill=(60, 56, 50), font=pv._font(26))
    im.save(path); return im


if __name__ == "__main__":
    from PIL import Image
    names = sys.argv[1:] or KEEP
    tiles = []
    for name in names:
        outline = rw.Circle(TILE) if name == "polar" else rw.RoundedSquare(TILE, CORNER)
        rods = rw.PATTERNS[name](outline, TH)
        print(f"{name}: {len(rods)} rods", flush=True)
        tiles.append(render_tile(rods, TITLES[name], f"pattern_{name}.png"))
    cols = 2; rows = (len(tiles) + 1) // 2; s = 1000
    sheet = Image.new("RGB", (cols * s, rows * s), (245, 242, 238))
    for k, t in enumerate(tiles):
        sheet.paste(t, ((k % cols) * s, (k // cols) * s))
    sheet.save("pattern_sampler_sheet.png"); print("sheet done")
