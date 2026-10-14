"""Review sheet: front / three-quarter / profile / back of an STL above refs 4, 5, 6 (+ 8)."""
import sys, os
from PIL import Image
sys.path.insert(0, "tools"); from studio_render import render
stl, out = sys.argv[1], sys.argv[2]
tmp = "/private/tmp/claude-501/-Users-collin/2a7497c0-8c01-463a-9292-f8e064ab5a84/scratchpad"; os.makedirs(tmp, exist_ok=True)
tiles = []
for i, (yaw, pitch) in enumerate([(180, -4), (-145, -8), (-95, -4), (0, -8)]):
    p = f"{tmp}/m3s{i}.jpg"; render(stl, p, 700, 700, yaw, pitch); tiles.append(Image.open(p))
refs = [Image.open(f"refs/monster3/ref{n}.png").convert("RGB") for n in (4, 5, 6, 8)]
sheet = Image.new("RGB", (2800, 700 + 420), (28, 24, 22))
for i, t in enumerate(tiles): sheet.paste(t, (i * 700, 0))
x = 10
for r in refs:
    r = r.resize((int(r.width * 400 / r.height), 400)); sheet.paste(r, (x, 710)); x += r.width + 20
sheet.save(out, quality=88); sheet.save(out.replace(".jpg", ".png")); print("wrote", out)
