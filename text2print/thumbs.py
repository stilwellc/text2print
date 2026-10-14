"""Card thumbnails for the studio: every shape (with a texture that suits it) and every texture (on a small
sample). Written to studio/static/thumbs/. Run: python -m text2print thumbs"""
import pathlib

from . import build
from .render import render
from .shapes import SHAPES

OUT = pathlib.Path(__file__).resolve().parent.parent / "studio" / "static" / "thumbs"
FABRIC_TONE = "#D2B48C"     # fabric relief reads in a light tone under raking light
SHAPE_LOOK = {"tray": "twill", "platter": "grid", "dish": "polar", "coaster": "selvedge", "cup": "grid",
              "shade": "kagome", "bowl": "zigzag", "vase": "wave", "goblet": "swag", "candle": "curls", "custom": "garland",
              "cachepot": "twist", "sleeve": "zigzag", "lantern": "voronoi", "pendant": "fringe", "puck": "voronoi",
              "amphora": "flutes", "basket": "twill", "catchall": "grid", "hextile": "kagome", "tile": "cmyk"}
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
        look = SHAPE_LOOK[key]
        if look in ("cmyk", "flatlitho"):
            _backlit_thumb(look, key, {}, OUT / f"shape_{key}.png"); continue
        fab = fab and look not in ("cmyk",)
        b = build.make(key, look, colours=[FABRIC_TONE] if fab else None)
        tall = key in ("cup", "vase", "shade", "bowl", "goblet", "candle", "custom", "cachepot", "sleeve", "lantern",
                       "pendant", "puck", "amphora", "basket")
        render([(m, c) for _, m, _, c in (b.preview or b.parts)], OUT / f"shape_{key}.png", size=360,
               view=(1.0, -0.95, 0.45 if tall else 0.8), zoom=1.12, rake=s.families == ("fabric",))
        print("shape", key, flush=True)
    for key, t in build.TEXTURES.items():
        if only and f"texture_{key}" not in only:
            continue
        if t["family"] == "spiral":
            b = build.make("vase", key, {"diameter": 90, "height": 120}, colours=[FABRIC_TONE])
            render([(m, c) for _, m, _, c in b.parts], OUT / f"texture_{key}.png", size=360, view=(1.0, -0.9, 0.35), zoom=1.1, rake=True)
        elif t["family"] == "shell":
            b = build.make("cup", key, {"diameter": 70, "height": 80}, colours=[FABRIC_TONE])
            render([(m, c) for _, m, _, c in b.parts], OUT / f"texture_{key}.png", size=360,
                   view=(1.0, -0.9, 0.35) if key != "litho" else (0.2, -0.3, 1.0), zoom=1.1, rake=True)
        elif t["family"] == "flat":
            _backlit_thumb(key, "tile", {"width": 90, "depth": 70}, OUT / f"texture_{key}.png")
        elif t["family"] == "mix":
            from . import compose
            b = build.make("vase", key, {"diameter": 90, "height": 120}, colours=HALFTONE_COLOURS,
                           options={"bands": compose.PRESETS["flame"]["bands"]})
            render([(m, c) for _, m, _, c in (b.preview or b.parts)], OUT / f"texture_{key}.png", size=360,
                   view=(1.0, -0.9, 0.3), zoom=1.1)
        elif t["family"] == "halftone":
            b = build.make("cup", key, {"diameter": 80, "height": 90}, nozzle=0.8, colours=HALFTONE_COLOURS)
            render([(m, c) for _, m, _, c in b.parts], OUT / f"texture_{key}.png", size=360,
                   view=(1.0, -0.9, 0.25), zoom=1.1)
        elif t["family"] == "droop":                         # a small cup wearing the strands, raking light
            b = build.make("cup", key, {"diameter": 60, "height": 90}, colours=[FABRIC_TONE])
            render([(m, c) for _, m, _, c in (b.preview or b.parts)], OUT / f"texture_{key}.png", size=360,
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


def _backlit_thumb(texture, shape_key, dims, path, size=360):
    """Flat pictures only read when lit from behind: show the slicer-honest backlit estimate."""
    from PIL import Image, ImageFilter
    from . import flat, printer, shapes
    sh = shapes.SHAPES[shape_key]; v = sh.resolve(dims)
    _, info = flat.build(sh, v, printer.nozzle(0.4), "cmyk" if texture == "cmyk" else "litho", draft=False)
    im = Image.fromarray(info["backlit"], "RGBA")
    im.thumbnail((int(size * 0.8), int(size * 0.8)), Image.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    shadow = Image.new("RGBA", im.size, (60, 40, 20, 0)); shadow.putalpha(im.getchannel("A").point(lambda a: a * 0.25))
    shadow = shadow.filter(ImageFilter.GaussianBlur(8))
    canvas.alpha_composite(shadow, ((size - im.width) // 2 + 4, (size - im.height) // 2 + 8))
    canvas.alpha_composite(im, ((size - im.width) // 2, (size - im.height) // 2))
    canvas.save(path)


def docs_sheet(path=None, cols=8, cell=230):
    """docs/textures.png: every texture card with its name (README)."""
    from PIL import Image, ImageDraw, ImageFont
    from .build import TEXTURES
    path = path or OUT.parent.parent.parent / "docs" / "textures.png"
    T = [(k, t["name"]) for k, t in TEXTURES.items() if k != "mix" and (OUT / f"texture_{k}.png").exists()]
    lab = 34; rows = (len(T) + cols - 1) // cols
    im = Image.new("RGB", (cols * cell, rows * (cell + lab)), (247, 245, 240)); d = ImageDraw.Draw(im)
    try:
        f = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 19)
    except OSError:
        f = ImageFont.load_default()
    for i, (k, n) in enumerate(T):
        t = Image.open(OUT / f"texture_{k}.png").convert("RGBA").resize((cell - 20, cell - 20), Image.LANCZOS)
        x, y = (i % cols) * cell, (i // cols) * (cell + lab)
        im.paste(t, (x + 10, y + 6), t)
        w = d.textlength(n, font=f); d.text((x + (cell - w) / 2, y + cell - 6), n, fill=(60, 55, 50), font=f)
    im.save(path, optimize=True)
    return path
