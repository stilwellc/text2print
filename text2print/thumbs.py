"""Card thumbnails for the studio: every shape (with a texture that suits it) and every texture (on a small
sample). Written to studio/static/thumbs/. Run: python -m text2print thumbs"""
import pathlib

from . import build
from .render import render
from .shapes import SHAPES

OUT = pathlib.Path(__file__).resolve().parent.parent / "studio" / "static" / "thumbs"
FABRIC_TONE = "#D2B48C"     # fabric relief reads in a light tone under raking light
SHAPE_LOOK = {"tray": "twill", "platter": "grid", "dish": "polar", "coaster": "selvedge", "cup": "grid",
              "shade": "kagome", "bowl": "zigzag", "vase": "wave", "goblet": "swag", "candle": "curls"}
HALFTONE_COLOURS = ["#F3D34A", "#C3302C"]
SAMPLE = {"lattice": ("coaster", {"width": 70, "height": 8, "dish": 0, "corner": 12, "pillow": 0}),
          "lattice_round": ("dish", {"diameter": 70, "height": 9, "dish": 0, "pillow": 0}),
          "fabric": ("cup", {"diameter": 60, "height": 46})}


def render_all(only=None):
    OUT.mkdir(parents=True, exist_ok=True)
    for key, s in SHAPES.items():
        if only and f"shape_{key}" not in only:
            continue
        fab = "lattice" not in s.families
        b = build.make(key, SHAPE_LOOK[key], colours=[FABRIC_TONE] if fab else None)
        tall = key in ("cup", "vase", "shade", "bowl", "goblet", "candle")
        render([(m, c) for _, m, _, c in (b.preview or b.parts)], OUT / f"shape_{key}.png", size=360,
               view=(1.0, -0.95, 0.45 if tall else 0.8), zoom=1.12, rake=s.families == ("fabric",))
        print("shape", key, flush=True)
    for key, t in build.TEXTURES.items():
        if only and f"texture_{key}" not in only:
            continue
        if t["family"] == "halftone":
            b = build.make("cup", key, {"diameter": 80, "height": 90}, nozzle=0.8, colours=HALFTONE_COLOURS)
            render([(m, c) for _, m, _, c in b.parts], OUT / f"texture_{key}.png", size=360,
                   view=(1.0, -0.9, 0.25), zoom=1.1)
        elif t["family"] == "droop":                         # a small cup wearing the strands, raking light
            b = build.make("cup", key, {"diameter": 60, "height": 90}, colours=[FABRIC_TONE])
            render([(m, c) for _, m, _, c in b.preview], OUT / f"texture_{key}.png", size=360,
                   view=(1.0, -0.9, 0.3), zoom=1.15, rake=True)
        elif t["family"] == "fabric":                      # close on the wall, raking light: show the stitch
            shp, v = SAMPLE["fabric"]; b = build.make(shp, key, v, colours=[FABRIC_TONE])
            render([(m, c) for _, m, _, c in b.parts], OUT / f"texture_{key}.png", size=360,
                   view=(1.0, -0.6, 0.12), zoom=2.6, target=(26, -16, 30), rake=True)
        else:
            shp, v = SAMPLE["lattice_round" if t.get("round_only") else "lattice"]; b = build.make(shp, key, v)
            low = key == "overunder"
            render([(m, c) for _, m, _, c in b.parts], OUT / f"texture_{key}.png", size=360,
                   view=(1.0, -0.9, 0.42 if low else 0.9), zoom=1.9 if low else 1.15,
                   target=(10, -10, 4) if low else None)
        print("texture", key, flush=True)
    return 0
