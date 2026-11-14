"""The README's hero banner: every piece from make_media.PIECES on one shelf, at true relative size, spinning in sync.
  .venv/bin/python docs/make_hero.py"""
import pathlib
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from text2print import design as D          # noqa: E402
from text2print.render import render, GROUND  # noqa: E402
import make_media as M                       # noqa: E402

OUT = pathlib.Path(__file__).resolve().parent / "media" / "hero.gif"
ORDER = ["woven-cup", "halftone-cup", "loop-vase", "twist-vase", "fringe-cup", "woven-dish"]
HERO_PARAMS = {"woven-dish": {"diameter": 170}}   # bigger than the gallery dish so its rings read at banner scale
TILE, SS, FRAMES, MS = 420, 3, 36, 75
W, H, PAD, MIN_GAP = 1280, 380, 28, 34
ELEV = 0.32                                    # one camera height for the whole shelf


def frames_for(name):
    d, _, _ = M.PIECES[name]
    d = {**d, "params": {**d.get("params", {}), **HERO_PARAMS.get(name, {})}}
    _, b = D.build_design(d)
    parts = D.view_of(b, hung=True)
    v = np.vstack([m.vertices for m, _ in parts]); lo, hi = v.min(0), v.max(0)
    rake = len({c for _, c in parts}) == 1
    out = []
    for i in range(FRAMES):
        a = -np.pi / 4 + 2 * np.pi * i / FRAMES
        out.append(render(parts, size=TILE * SS, view=(np.cos(a), np.sin(a), ELEV), zoom=1.0, target=(lo + hi) / 2, rake=rake))
    return out, float(np.linalg.norm(hi - lo))


def bbox(im):
    a = np.asarray(im).astype(int); m = np.abs(a - np.array(GROUND)).max(-1) > 6
    ys, xs = np.nonzero(m); return xs.min(), ys.min(), xs.max() + 1, ys.max() + 1


if __name__ == "__main__":
    pieces = {n: frames_for(n) for n in ORDER}
    big = max(r for _, r in pieces.values())
    # every tile renders its piece at the same apparent size; scale each by its true size so the shelf is to scale
    crops = {}
    for n, (fr, r) in pieces.items():
        boxes = np.array([bbox(f) for f in fr]); x0, y0 = boxes[:, :2].min(0); x1, y1 = boxes[:, 2:].max(0)
        s = r / big
        crops[n] = [f.crop((x0, y0, x1, y1)).resize((max(1, int((x1 - x0) * s)), max(1, int((y1 - y0) * s))), Image.LANCZOS)
                    for f in fr]
    widths = [crops[n][0].width for n in ORDER]; tallest = max(crops[n][0].height for n in ORDER)
    # the tallest piece fills the banner height, unless that would close the gaps between pieces
    k = min((H - 2 * PAD) * SS / tallest, (W - 2 * PAD - 5 * MIN_GAP) * SS / sum(widths))
    widths = [int(w * k) for w in widths]
    gap = (W * SS - 2 * PAD * SS - sum(widths)) / (len(ORDER) - 1)
    frames = []
    for i in range(FRAMES):
        c = Image.new("RGB", (W * SS, H * SS), GROUND); x = PAD * SS
        floor = H * SS - PAD * SS
        for n, w in zip(ORDER, widths):
            im = crops[n][i]
            if k != 1: im = im.resize((int(im.width * k), int(im.height * k)), Image.LANCZOS)
            c.paste(im, (int(x + (w - im.width) / 2), floor - im.height)); x += w + gap
        frames.append(c.resize((W, H), Image.LANCZOS))
    pal = frames[0].quantize(colors=96, method=Image.Quantize.MEDIANCUT)
    q = []
    for f in frames:
        a = np.asarray(f).astype(int); a[np.abs(a - np.array(GROUND)).max(-1) <= 8] = GROUND
        q.append(Image.fromarray(a.astype("uint8")).quantize(palette=pal, dither=Image.Dither.NONE))
    q[0].save(OUT, save_all=True, append_images=q[1:], duration=MS, loop=0, optimize=True, disposal=1)
    frames[0].save(pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else OUT.with_suffix(".first.png"))
    print(OUT, OUT.stat().st_size // 1024, "KB")
