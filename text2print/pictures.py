"""Picture library: one source of pictures for every picture-driven texture (halftone walls, wall lithophanes,
flat lithophane and CMYK tiles, halftone bands in a mix).

A picture is chosen by options:
  image        an uploaded picture's id or a path (wins over everything)
  picture      a built-in key (flames, fade, dots, chevron, waves, moon, sunset), "text", or "lib:<name>"
  text, font, text_layout, text_invert     when picture == "text"

Library pictures live in ~/.text2print/pictures (or $T2P_PICTURES): PNG/JPG files, or small Python programs
that draw a picture from a prompt (see plugins.py — the skill writes these):

    PICTURE = dict(name="Koi pond", colour=False)
    def draw(u, v, aspect):      # u: 0..1 across (around a wall), v: 0..1 up; aspect = width / height in mm
        return grey               # 0..1, 1 = dark / the front colour   (colour=True: an (..., 3) RGB array)

Text is rendered at the real proportions of the wall or tile it goes on, so letters are never stretched."""
import hashlib
import importlib.util
import math
import os
import pathlib

import numpy as np

HOME = pathlib.Path(os.environ.get("T2P_HOME", pathlib.Path.home() / ".text2print"))
LIB = pathlib.Path(os.environ.get("T2P_PICTURES", HOME / "pictures"))
CACHE = HOME / "cache"

_SYS = pathlib.Path("/System/Library/Fonts"); _SUP = _SYS / "Supplemental"
FONTS = {                                     # key: (label, file, face index in a .ttc)
    "helvetica": ("Helvetica Bold", _SYS / "Helvetica.ttc", 1),
    "futura": ("Futura Bold", _SUP / "Futura.ttc", 2),
    "avenir": ("Avenir Next Heavy", _SYS / "Avenir Next.ttc", 8),
    "didot": ("Didot Bold", _SUP / "Didot.ttc", 2),
    "georgia": ("Georgia Bold", _SUP / "Georgia Bold.ttf", 0),
    "rockwell": ("Rockwell Bold", _SUP / "Rockwell.ttc", 2),
    "typewriter": ("American Typewriter", _SUP / "AmericanTypewriter.ttc", 0),
    "impact": ("Impact", _SUP / "Impact.ttf", 0),
    "script": ("Snell Roundhand", _SUP / "SnellRoundhand.ttc", 1),
    "chalk": ("Chalkduster", _SUP / "Chalkduster.ttf", 0),
}
LAYOUTS = [("center", "Centred"), ("repeat", "Repeating"), ("stack", "Stacked")]
BUILTIN = {"flames": "Flames", "fade": "Fade", "dots": "Polka dots", "chevron": "Chevron", "waves": "Waves",
           "moon": "Moon over hills", "sunset": "Sunset (colour)"}


def fonts():
    return [(k, lab) for k, (lab, path, _) in FONTS.items() if path.exists()]


def library():
    """{'lib:<name>': {'name', 'kind': 'image'|'program', 'path', 'colour'}} — scanned fresh each call."""
    out = {}
    if LIB.exists():
        for p in sorted(LIB.iterdir()):
            if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
                out[f"lib:{p.stem}"] = dict(name=p.stem.replace("_", " ").replace("-", " ").title(), kind="image",
                                            path=str(p), colour=True)
            elif p.suffix == ".py" and not p.name.startswith("_"):
                try:
                    mod = _load(p)
                    meta = getattr(mod, "PICTURE", None)
                    if meta and callable(getattr(mod, "draw", None)):
                        out[f"lib:{p.stem}"] = dict(name=meta.get("name", p.stem), kind="program", path=str(p),
                                                    colour=bool(meta.get("colour")))
                except Exception:                                     # a broken file never breaks the studio
                    continue
    from . import plugins                                             # pictures defined in plugin files too
    for k, meta in plugins.pictures().items():
        out.setdefault(k, meta)
    return out


def choices():
    """Picker list: built-ins, text, then the library."""
    out = [dict(key=k, name=n, group="Built-in") for k, n in BUILTIN.items()]
    out.append(dict(key="text", name="Text…", group="Text"))
    out += [dict(key=k, name=m["name"], group="Library", params=m.get("params") or {}) for k, m in library().items()]
    return out


_MODS = {}


def _load(path):
    path = pathlib.Path(path); key = (str(path), path.stat().st_mtime)
    if key not in _MODS:
        spec = importlib.util.spec_from_file_location(f"t2p_pic_{path.stem}", path)
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        _MODS[key] = mod
    return _MODS[key]


# ── text ──────────────────────────────────────────────────────────────────────
def render_text(text, font="futura", layout="center", aspect=3.0, height_px=600, invert=False):
    """Words -> greyscale PIL image (black text on white) at width/height = aspect."""
    from PIL import Image, ImageDraw, ImageFont
    text = (text or "").strip() or "TEXT"
    W = max(64, int(round(height_px * max(0.2, min(aspect, 30.0))))); H = height_px
    im = Image.new("L", (W, H), 255); d = ImageDraw.Draw(im)
    lab, path, idx = FONTS.get(font, FONTS["helvetica"])
    face = lambda size: (ImageFont.truetype(str(path), size, index=idx) if path.exists() else ImageFont.load_default())

    def fit(lines, box_w, box_h, spacing=0.15):
        lo, hi = 8, 2000
        while hi - lo > 2:                                            # largest size whose block fits the box
            mid = (lo + hi) // 2; f = face(mid)
            bw = max(d.textlength(L, font=f) for L in lines); lh = mid * (1 + spacing)
            if bw <= box_w and lh * len(lines) <= box_h:
                lo = mid
            else:
                hi = mid
        return face(lo), lo

    if layout == "repeat":
        rows = 3 if H >= 200 else 2
        f, size = fit([text + "   "], W * 0.6, H / rows * 0.82, 0)
        step = d.textlength(text + "   ", font=f)
        n = max(1, int(W // step))                                     # whole repeats: no word cut at the seam
        for _ in range(3):
            size = max(8, int(size * (W / n) / step)); f = face(size); step = d.textlength(text + "   ", font=f)
        if size * 1.15 > H / rows:                                     # too tall now: one more repeat, smaller
            n += 1; size = max(8, int(size * (W / n) / step)); f = face(size); step = W / n
        for r in range(rows):
            y = (r + 0.5) * H / rows - size * 0.55
            x = -(r % 2) * step / 2                                     # offset rows: a woven wallpaper
            while x < W:
                d.text((x, y), text, font=f, fill=0); x += step
    else:
        lines = text.split() if layout == "stack" else [text]
        f, size = fit(lines, W * 0.86, H * 0.8)
        lh = size * 1.15; y0 = (H - lh * len(lines)) / 2
        for i, L in enumerate(lines):
            w = d.textlength(L, font=f)
            d.text(((W - w) / 2, y0 + i * lh), L, font=f, fill=0)
    if invert:
        from PIL import ImageOps
        im = ImageOps.invert(im)
    return im


# ── one sampler for every texture ─────────────────────────────────────────────
def _image_path(options):
    img = options.get("image")
    if not img:
        return None
    if pathlib.Path(str(img)).exists():
        return str(img)
    from . import store
    p = store.image_path(img)
    return str(p) if p and pathlib.Path(p).exists() else None


def image_for(options, aspect, colour=False):
    """The picture as a PIL image (RGB if colour) at the target aspect, or None for procedural built-ins."""
    from PIL import Image
    path = _image_path(options)
    pic = options.get("picture") or ""
    if path:
        im = Image.open(path)
    elif pic == "text":
        key = hashlib.sha1(repr((options.get("text"), options.get("font"), options.get("text_layout"),
                                 bool(options.get("text_invert")), round(aspect, 2))).encode()).hexdigest()[:16]
        CACHE.mkdir(parents=True, exist_ok=True); cp = CACHE / f"text_{key}.png"
        if not cp.exists():
            render_text(options.get("text"), options.get("font", "futura"), options.get("text_layout", "center"),
                        aspect, invert=bool(options.get("text_invert"))).save(cp)
        im = Image.open(cp)
    elif pic.startswith("lib:"):
        meta = library().get(pic)
        if not meta:
            return None
        if meta["kind"] == "image":
            im = Image.open(meta["path"])
        else:
            H = 600; W = max(64, int(round(H * max(0.2, min(aspect, 30.0)))))
            u, v = np.meshgrid((np.arange(W) + 0.5) / W, 1 - (np.arange(H) + 0.5) / H)
            mod = None if meta.get("draw") else _load(meta["path"])
            draw = meta.get("draw") or mod.draw
            pmeta = meta.get("params") or (getattr(mod, "PARAMS", None) if mod else None) or {}
            from . import plugins
            g = np.asarray(plugins.call(draw, u, v, aspect, p=plugins.param_values(pmeta, options)), float)
            if g.ndim == 3:                                            # a colour program: RGB 0..1
                im = Image.fromarray((np.clip(g, 0, 1) * 255).astype(np.uint8), "RGB")
            else:                                                      # grey: 1 = dark
                im = Image.fromarray(((1 - np.clip(g, 0, 1)) * 255).astype(np.uint8), "L")
    else:
        return None
    return im.convert("RGB" if colour else "L")


FRONT_U = 0.875          # "front" = the side the studio camera looks at


def natural_aspect(options):
    """Width/height a picture wants when it isn't wrapped: an image's own shape, text's measured shape."""
    from PIL import Image
    path = _image_path(options); pic = options.get("picture") or ""
    if path:
        w, h = Image.open(path).size; return w / max(h, 1)
    if pic == "text":
        im = render_text(options.get("text"), options.get("font", "futura"), options.get("text_layout", "center"), 8.0,
                         height_px=200)
        a = np.asarray(im) < 128
        if not a.any():
            return 3.0
        ys, xs = np.where(a); bw = xs.max() - xs.min() + 1; bh = ys.max() - ys.min() + 1
        return float((bw * 1.12) / (bh * 1.3))
    if pic.startswith("lib:"):
        meta = library().get(pic) or {}
        if meta.get("kind") == "image":
            w, h = Image.open(meta["path"]).size; return w / max(h, 1)
        return 1.5
    return 1.0


def _base(options, aspect):
    """The picture itself, as darkness f(u, v) over its own 0..1 square, drawn for width/height = aspect."""
    im = image_for(options, aspect)
    if im is None:
        from . import halftone
        name = options.get("picture") or "flames"
        if name == "moon":
            def f(u, v):
                u = np.asarray(u, float) % 1.0; v = np.asarray(v, float)
                d = np.hypot((u * 6 % 1.0) - 0.5, (v - 0.68) * 1.6)
                moon = np.clip(1 - d / 0.22, 0, 1) ** 0.6
                hills = (v < 0.3 + 0.08 * np.sin(2 * np.pi * u * 5) + 0.05 * np.sin(2 * np.pi * u * 13)).astype(float)
                return 1 - np.clip(0.15 + 0.85 * moon - 0.6 * hills, 0, 1)
            return f
        if name == "sunset":
            im = _sunset().convert("L")
        else:
            name = name if name in halftone.PICTURES else "flames"
            return lambda u, v: halftone.picture(name, u, v)
    a = 1.0 - np.asarray(im, float) / 255.0
    h, w = a.shape

    def f(u, v):
        u = np.asarray(u, float) % 1.0; v = np.clip(np.asarray(v, float), 0, 1)
        return a[np.clip(((1 - v) * (h - 1)).round().astype(int), 0, h - 1), np.clip((u * (w - 1)).round().astype(int), 0, w - 1)]
    return f


def _num(options, key, default, lo, hi):
    try:
        return float(min(hi, max(lo, float(options.get(key, default)))))
    except (TypeError, ValueError):
        return default


def darkness(options, aspect):
    """-> f(u, v) giving 0..1, 1 = dark (the halftone's front colour; the lithophane's thick part), over a wall
    whose picture zone is `aspect` wide per unit tall. Picture controls:
      picture_place  wrap (all the way round) | front (the picture at its own proportions, on the front)
      picture_size   share of the height it spans (0.15-1), picture_lift: where its centre sits (0 bottom - 1 top)
      picture_contrast (0.3-3), picture_invert"""
    place = options.get("picture_place", "wrap")
    size = _num(options, "picture_size", 1.0, 0.15, 1.0)
    lift = _num(options, "picture_lift", 0.5, 0.0, 1.0)
    con = _num(options, "picture_contrast", 1.0, 0.3, 3.0)
    inv = str(options.get("picture_invert", "")).lower() in ("1", "true", "yes")
    if place == "front":
        za = natural_aspect(options); base = _base(options, za)
        uspan = min(1.0, za * size / max(aspect, 1e-6))
    else:
        za = aspect / size; base = _base(options, za); uspan = 1.0
    v0 = size / 2 + (1 - size) * lift                        # the zone stays on the wall

    def f(u, v):
        u = np.asarray(u, float); v = np.asarray(v, float)
        if place == "front":
            uu = (((u - FRONT_U + 0.5) % 1.0) - 0.5) / uspan + 0.5
        else:
            uu = u % 1.0
        vv = (v - v0) / size + 0.5
        inside = (uu >= 0) & (uu <= 1) & (vv >= 0) & (vv <= 1)
        g = np.where(inside, base(np.clip(uu, 0, 1), np.clip(vv, 0, 1)), 0.0)
        if con != 1.0:
            g = np.where(inside, np.clip((g - 0.5) * con + 0.5, 0, 1), g)
        if inv:
            g = np.where(inside, 1.0 - g, g)
        return g
    return f


def colour_image(options, aspect):
    """RGB PIL image for colour textures (CMYK tiles); built-ins fall back to the sunset."""
    im = image_for(options, aspect, colour=True)
    return im if im is not None else _sunset()


def _sunset():
    from PIL import Image
    W, H = 400, 300
    y, x = np.mgrid[0:H, 0:W].astype(float); y /= H; x /= W
    sky = np.stack([0.98 - 0.2 * y, 0.55 + 0.3 * y, 0.35 + 0.55 * y], -1)
    sun = np.hypot(x - 0.62, (y - 0.55) * 0.75) < 0.13
    sky[sun] = [1.0, 0.86, 0.35]
    hills = y > 0.62 + 0.08 * np.sin(x * 9) + 0.04 * np.sin(x * 23)
    sky[hills] = np.stack([0.15 + 0.1 * x, 0.32 + 0.2 * (1 - y), 0.22 + 0.05 * x], -1)[hills]
    return Image.fromarray((np.clip(sky, 0, 1) * 255).astype(np.uint8))


def wall_aspect(prof, height):
    """Width/height of an unrolled wall: circumference at its widest over the height."""
    zs = np.linspace(0, height, 32)
    return 2 * math.pi * max(prof(z) for z in zs) / max(height, 1e-6)
