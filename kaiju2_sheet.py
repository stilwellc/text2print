"""Review sheet: three studio renders of an STL (3/4, front, profile) above the three references."""
import sys, os, tempfile
from PIL import Image
sys.path.insert(0, "tools")
from studio_render import render
stl, out = sys.argv[1], sys.argv[2]
views = [(-152, -8), (180, -4), (-95, -4)] if len(sys.argv) < 4 else [tuple(map(float, v.split(","))) for v in sys.argv[3:]]
tiles = []
for i, (yaw, pitch) in enumerate(views):
    p = os.path.join(tempfile.gettempdir(), f"k2v{i}.jpg"); render(stl, p, 800, 800, yaw, pitch); tiles.append(Image.open(p))
refs = [Image.open(f"refs/kaiju2/{n}").convert("RGB") for n in ("1.png", "2.jpg", "3.png")]
W = 800 * len(tiles); sheet = Image.new("RGB", (W, 800 + 420), (28, 24, 22))
for i, t in enumerate(tiles): sheet.paste(t, (i * 800, 0))
x = 0
for r in refs:
    r = r.resize((int(r.width * 400 / r.height), 400)); sheet.paste(r, (x + 10, 810)); x += r.width + 20
sheet.save(out, quality=88); print("wrote", out)
