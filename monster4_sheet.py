"""Review sheet: front / three-quarter / profile / back of an STL above Collin's four renders (refs/monster4)."""
import sys, os
from PIL import Image
sys.path.insert(0, "tools"); from studio_render import render
stl, out = sys.argv[1], sys.argv[2]
tmp = "/private/tmp/claude-501/-Users-collin/6a2fc169-fe21-45af-9912-2bd0b7ac69ed/scratchpad"; os.makedirs(tmp, exist_ok=True)
views = [(180, -4), (-145, -8), (-95, -4), (0, -8)]                  # front, three-quarter, profile, back
refs  = ["front", "threequarter", "profile", "back"]
T = 700
sheet = Image.new("RGB", (4 * T, T + 520), (28, 24, 22))
for i, ((yaw, pitch), rn) in enumerate(zip(views, refs)):
    p = f"{tmp}/m4s{i}.jpg"; render(stl, p, T, T, yaw, pitch); sheet.paste(Image.open(p), (i * T, 0))
    r = Image.open(f"refs/monster4/{rn}.png").convert("RGB"); r = r.resize((int(r.width * 500 / r.height), 500))
    sheet.paste(r, (i * T + (T - r.width) // 2, T + 10))
sheet.save(out, quality=88); print("wrote", out)
