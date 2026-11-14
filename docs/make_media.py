"""Render the README's turntable GIFs from real builds.  .venv/bin/python docs/make_media.py [name ...]

Each GIF is the actual design built by the same code that writes the Bambu project, spun once around
its axis with the studio's renderer (loops and strands shown hung, as they fall)."""
import pathlib
import sys
import time

import numpy as np
from PIL import Image

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from text2print import design as D          # noqa: E402
from text2print.render import render        # noqa: E402

OUT = pathlib.Path(__file__).resolve().parent / "media"
SIZE, FRAMES, MS, SS = 400, 36, 70, 3   # px, frames per turn, ms per frame, supersample

PIECES = {   # name: (design, camera elevation or None for auto, zoom)
    "woven-dish": ({"shape": "dish", "texture": "polar", "nozzle": 0.4, "params": {"diameter": 100},
                    "colours": ["#8B3A2F", "#EDE3D1"]}, 1.1, 1.15),
    "woven-cup": ({"shape": "cup", "texture": "grid", "nozzle": 0.8, "params": {"diameter": 80, "height": 80},
                   "colours": ["#2E4E7E", "#EDE3D1"]}, 0.45, 1.1),
    "loop-vase": ({"shape": "vase", "texture": "jacquard", "nozzle": 0.4, "colours": ["#2E4E7E", "#E8752F", "#F3D34A"],
                   "options": {"loops": "tiers", "band": 2}}, None, 1.08),
    "halftone-cup": ({"shape": "cup", "texture": "halftone", "nozzle": 0.8, "colours": ["#F3D34A", "#C3302C"]}, None, 1.08),
    "twist-vase": ({"shape": "vase", "texture": "twist", "nozzle": 0.4, "colours": ["#3F6B5A"]}, None, 1.08),
    "fringe-cup": ({"shape": "cup", "texture": "fringe", "nozzle": 0.4, "colours": ["#D2B48C"]}, 0.3, 1.1),
}


def spin(name, d, elev=None, zoom=1.08):
    t = time.time()
    _, b = D.build_design(d)
    parts = D.view_of(b, hung=True)
    s = b.stats["size"]
    elev = elev if elev is not None else (0.3 if s[2] > 0.6 * max(s[:2]) else 0.7)
    allv = np.vstack([m.vertices for m, _ in parts]); centre = (allv.min(0) + allv.max(0)) / 2
    rake = len({c for _, c in parts}) == 1
    frames = []
    for i in range(FRAMES):
        a = -np.pi / 4 + 2 * np.pi * i / FRAMES
        im = render(parts, size=SIZE * SS, view=(np.cos(a), np.sin(a), elev), zoom=zoom, target=centre, rake=rake)
        frames.append(im.resize((SIZE, SIZE), Image.LANCZOS))
    pal = frames[0].quantize(colors=96, method=Image.Quantize.MEDIANCUT)
    q = [f.quantize(palette=pal, dither=Image.Dither.NONE) for f in frames]
    path = OUT / f"{name}.gif"
    q[0].save(path, save_all=True, append_images=q[1:], duration=MS, loop=0, optimize=True, disposal=1)
    print(f"{name}: {path.stat().st_size // 1024} KB, {time.time() - t:.0f}s", flush=True)
    return frames


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for n in (sys.argv[1:] or PIECES):
        spin(n, *PIECES[n])
