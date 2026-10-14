"""Quick look at the one-piece ape (with ears) — hero / front / profile sheet, before any split."""
import sys, os, tempfile
sys.argv = [sys.argv[0], "2", sys.argv[1] if len(sys.argv) > 1 else "0.75", *sys.argv[2:]]
import kaiju_head as K
from PIL import Image
sys.path.insert(0, "tools"); from studio_render import render
out = sys.argv[3] if len(sys.argv) > 3 else "sofubi_ape_preview.jpg"
xs, ys, zs, X, Y, Z, f, shell, dist = K.fields(float(sys.argv[2]), with_ears=True)
tm = K.mesh_from(shell, xs, ys, zs, float(sys.argv[2])); stl = os.path.join(tempfile.gettempdir(), "ape_preview.stl"); tm.export(stl)
print("extents", tm.extents.round(1))
tiles = []
for i, (yaw, pitch) in enumerate([(-152, -8), (180, -4), (-95, -4)]):
    p = os.path.join(tempfile.gettempdir(), f"apev{i}.jpg"); render(stl, p, 800, 800, yaw, pitch); tiles.append(Image.open(p))
sheet = Image.new("RGB", (2400, 800)); [sheet.paste(t, (i * 800, 0)) for i, t in enumerate(tiles)]; sheet.save(out, quality=88); print("wrote", out)
