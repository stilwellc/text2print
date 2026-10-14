"""Review sheet: model front / three-quarter / profile / back (studio render) above Collin's four photos, plus the silhouette overlays.
Usage: python mascot_sheet.py model.stl map_prefix out.jpg   (map_prefix = output prefix of a mascot_map.py run)"""
import sys, subprocess, numpy as np
from PIL import Image, ImageDraw
stl, mp, out = sys.argv[1], sys.argv[2], sys.argv[3]
S = "/private/tmp/claude-501/-Users-collin/ef956a5a-39a6-4219-99f0-1df75b8b70a5/scratchpad"
subprocess.run([sys.executable, "mascot_views.py", stl, f"{S}/sheet_views.png"], check=True, capture_output=True)
views = Image.open(f"{S}/sheet_views.png")               # 2800×700: front / 3q / profile / back
T = 700
tiles = [views.crop((i * T, 0, (i + 1) * T, T)) for i in range(4)]
def fit(p):
    im = Image.open(p).convert("RGB"); im.thumbnail((T, T)); bg = Image.new("RGB", (T, T), (255, 255, 255)); bg.paste(im, ((T - im.width) // 2, (T - im.height) // 2)); return bg
photos = [fit(f"refs/mascot/{n}.png") for n in ("front", "threequarter", "profile", "back")]
overlays = [fit(f"{mp}_{n}.png") for n in ("front", "threequarter", "profile", "back")]
sheet = Image.new("RGB", (T * 4, T * 3 + 40), (255, 255, 255)); d = ImageDraw.Draw(sheet)
for r, (row, label) in enumerate([(tiles, "model"), (photos, "photo"), (overlays, "silhouette: green = photo only, magenta = model only")]):
    for c, im in enumerate(row): sheet.paste(im, (c * T, r * T + 40))
d.text((10, 10), f"{stl}   rows: model / photo / overlay", fill=(0, 0, 0))
sheet.save(out, quality=88); print("wrote", out)
