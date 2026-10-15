"""Tools for Claude as the designer (the studio's "Design with Claude" box, or the skill in a chat):

    python -m text2print catalogue                 everything a design can use, as JSON (shapes + sizes, textures,
                                                   options, mix blends, pictures, fonts, plugins, palette, saved designs)
    python -m text2print design check FILE.json    build a design, report stats + warnings, render a preview PNG
    python -m text2print picture prepare PHOTO ... turn a photo into a print-ready picture in the library

A design is exactly what the studio builds: {"shape", "texture", "params", "nozzle", "colours", "options"} —
options holds everything else (picture/text settings, mix "bands" with "blend", lid, engraving, zones…)."""
import json
import pathlib
import urllib.parse

import numpy as np


def catalogue():
    from . import build, compose, pictures, plugins, printer, store
    from .shapes import SHAPES
    plugins.load_all()
    shapes = {k: dict(name=s.name, blurb=s.blurb, round=bool(s.round), families=list(s.families),
                      params={p.key: dict(label=p.label, lo=p.lo, hi=p.hi, default=p.default, unit=p.unit,
                                          only_for=p.family or None) for p in s.params})
              for k, s in SHAPES.items()}
    textures = {k: dict(name=t["name"], family=t["family"], slots=t.get("slots", 1), colour_changes=t.get("swaps"),
                        blurb=t.get("blurb", ""), custom=bool(t.get("custom")),
                        fits=[s for s in SHAPES if build.compatible(s, k)])
                for k, t in build.TEXTURES.items()}
    options = {fam: {k: dict(label=lab, choices=[c[0] for c in (ch or [])] or None, default=d)
                     for k, lab, kind, ch, d in opts} for fam, opts in build.OPTIONS.items()}
    saved = []
    for d in store.designs()[-30:]:
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(d.get("link", "")).query))
        saved.append(dict(name=d.get("name"), link=d.get("link"), shape=q.get("shape"), texture=q.get("texture")))
    return dict(
        design_format={"shape": "shape key", "texture": "texture key", "params": "{size: mm}", "nozzle": 0.4,
                       "colours": "list of hex, one per AMS slot the design uses", "options": "everything else"},
        shapes=shapes, textures=textures, options_by_family=options,
        mix=dict(band_textures={k: compose.NAMES[k] for k in compose.MIXABLE}, blends=compose.BLEND_STYLES,
                 blendable=sorted(compose.BLENDABLE), presets={k: v["bands"] for k, v in compose.PRESETS.items()},
                 band_format={"texture": "key", "share": "relative height", "slot": "AMS slot index (0-3)",
                              "slot2": "second slot (halftone / woven bands)", "options": "{picture, image, density…}",
                              "blend": "{style: one of blends, size: mm} — how this band meets the band BELOW"}),
        pictures=dict(choices=pictures.choices(), fonts=[k for k, _ in pictures.fonts()],
                      layouts=[k for k, _ in pictures.LAYOUTS],
                      controls=["picture_place: wrap|front", "picture_size 0.15-1", "picture_lift 0-1",
                                "picture_contrast 0.3-3", "picture_invert", "text, font, text_layout"],
                      fabric_mask="fabric: mask in|out + picture options -> the stitch only inside/around the picture"),
        lid=dict(styles=["none", "slip", "thread", "magnets"], looks=[t["key"] for t in build.lid_textures()],
                 knobs=[k for k, _ in build.LID_KNOBS], fits=["snug", "slip", "loose"],
                 options=["lid", "lid_texture", "lid_colours", "lid_height", "lid_knob", "lid_fit", "lid_plate",
                          "engrave_lid"]),
        engraving=["engrave_base", "engrave_lid", "engrave_font"],
        woven_modifiers=dict(
            applies_to="any woven (lattice) texture on any shape — options, set them from what the person describes",
            weave_twist="degrees per course (-12..12): the whole lattice rotates as it climbs; 2-4 reads as a spiral, "
                        "8+ as a strong swirl. Same colour changes, rods stay inside the outline",
            weave_ombre="slots bottom->top, e.g. '0,1' or '0,1,2': each course takes a colour, dithered so it fades "
                        "from the first to the last (one change per course; 3 stops need 3 colours)",
            weave_picture="a picture key (text, lib:<name>, a drawn picture plugin): dark parts of the picture switch "
                          "the rods to slot 1 — words, a logo or a motif woven into the rods. Uses text/font/"
                          "picture_contrast/picture_invert like any picture",
            weave_picture_on="top (seen from above: trays, dishes, coasters — carried by weave_picture_courses top "
                             "courses, default 3) | wall (around the side: vessels, baskets). Default: by proportions",
            limits="bold shapes only: one rod (~2.5 mm) is the pixel, so letters >= 14 mm tall, 1-6 short words; "
                   "picture costs colour changes on every course it touches — check colour_changes"),
        cheaper_colour=["course_group 1-4 (woven)", "tower: off", "zones + zone_style courses (droop)"],
        palette=build.PALETTE, nozzles=list(printer.NOZZLES), plugins_dir=str(plugins.DIR),
        pictures_dir=str(pictures.LIB), saved_designs=saved)


def check_design(design, preview=None, draft=False):
    """Build a design dict; -> summary dict (and a preview PNG when asked)."""
    from . import build
    b = build.make(design["shape"], design["texture"], design.get("params") or {},
                   nozzle=float(design.get("nozzle", 0.4)), colours=design.get("colours") or None,
                   options=design.get("options") or {}, draft=draft)
    s = b.stats
    out = dict(ok=None if draft else all(m.is_watertight for _, m, _, _ in b.parts),   # sketches aren't watertight size_mm=s["size"], colours=s["colours"],
               colour_changes=s["swaps"], grams=s["grams_est"], purge_g=s.get("grams_purge", 0),
               print_minutes=s.get("minutes_est"), lid=s.get("lid"), params=b.params, warnings=b.warnings)
    if preview:
        from .thumbs import render
        view = (b.preview or b.parts) + list(b.assembled)
        tall = s["size"][2] > 0.6 * max(s["size"][:2])
        halftone = b.family == "halftone" or any(bb.get("texture") == "halftone"
                                                  for bb in (design.get("options") or {}).get("bands", []) or [])
        render([(m, c) for _, m, _, c in view], preview, size=720, view=(1.0, -0.9, 0.3 if tall else 0.7), zoom=1.08,
               rake=halftone or len({c for *_, c in view}) == 1)      # raking light: halftone ribs read as they print
        out["preview"] = str(preview)
    return out


# ── photos -> print-ready pictures ────────────────────────────────────────────
def prepare(src, out, crop=None, mode="halftone", contrast=1.0, gamma=1.0, equalize=False, posterize=0, edges=False,
            threshold=None, blur=0.0, invert=False, subject=False, max_px=1600):
    """Photo -> greyscale (halftone/litho) or colour (CMYK) picture. Dark = the front colour / thick lithophane.
    crop: (x0, y0, x1, y1) as fractions. subject: lift the subject off a plain background (border flood fill)."""
    from PIL import Image, ImageFilter, ImageOps
    im = Image.open(src); im = ImageOps.exif_transpose(im).convert("RGB")
    if crop:
        W, H = im.size; x0, y0, x1, y1 = crop
        im = im.crop((int(x0 * W), int(y0 * H), int(x1 * W), int(y1 * H)))
    im.thumbnail((max_px, max_px), Image.LANCZOS)
    if subject:                                    # background = colours connected to the border and close to it
        a = np.asarray(im, float)
        border = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
        bg = np.median(border, axis=0); dist = np.linalg.norm(a - bg, axis=2)
        import skimage.segmentation as seg
        near = dist < max(28.0, np.percentile(dist, 30))
        filled = seg.flood(near.astype(np.uint8), (0, 0)) | seg.flood(near.astype(np.uint8), (a.shape[0] - 1, a.shape[1] - 1))
        a[filled] = 255.0
        im = Image.fromarray(a.astype(np.uint8))
    if mode == "colour":
        if contrast != 1.0:
            from PIL import ImageEnhance
            im = ImageEnhance.Contrast(im).enhance(contrast)
        im.save(out); return str(out)
    g = np.asarray(im.convert("L"), float) / 255.0
    if blur:
        g = np.asarray(Image.fromarray((g * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(blur)), float) / 255.0
    if equalize:
        import skimage.exposure as ex
        g = ex.equalize_adapthist(g, clip_limit=0.02)
    if gamma != 1.0:
        g = g ** gamma
    if contrast != 1.0:
        g = np.clip((g - 0.5) * contrast + 0.5, 0, 1)
    if edges:                                      # line art: dark outlines on white
        import skimage.feature as feat
        e = feat.canny(g, sigma=2.0)
        import scipy.ndimage as ndi
        g = 1.0 - ndi.binary_dilation(e, iterations=2).astype(float)
    if (posterize and posterize > 1) or threshold is not None:   # flat tones: drop sensor grain first
        import scipy.ndimage as ndi
        g = ndi.median_filter(g, size=5)
    if posterize and posterize > 1:
        g = np.round(g * (posterize - 1)) / (posterize - 1)
    if threshold is not None:
        g = (g > threshold).astype(float)
    if invert:
        g = 1.0 - g
    Image.fromarray((np.clip(g, 0, 1) * 255).astype(np.uint8), "L").save(out)
    return str(out)


def slice_design(design, work):
    """Real Bambu Studio numbers for a design + a sliced-layer preview (what the printer lays down)."""
    import re
    import zipfile
    from . import bambu, build
    work = pathlib.Path(work); work.mkdir(parents=True, exist_ok=True)
    b = build.make(design["shape"], design["texture"], design.get("params") or {},
                   nozzle=float(design.get("nozzle", 0.4)), colours=design.get("colours") or None,
                   options=design.get("options") or {})
    proj = b.write_3mf(work / "design.3mf")
    r = bambu.slice_project(proj, work / "sliced")
    if "error" in r:
        return dict(error=r["error"])
    sl = work / "sliced" / "sliced.3mf"
    g = zipfile.ZipFile(sl).read("Metadata/plate_1.gcode").decode(errors="ignore")
    out = dict(print_minutes=r["minutes"], print_time=r["time"], grams=r["grams"], layers=r["layers"],
               colour_changes=len(re.findall(r"^M620 S\dA", g, re.M)), app_estimate_minutes=b.stats.get("minutes_est"))
    try:
        out["sliced_preview"] = bambu.gcode_preview(sl, work / "sliced_preview.png", list(b.colours) + [c for *_, c in b.extras])
    except Exception as e:
        out["sliced_preview_error"] = str(e)
    if (work / "design-lid.3mf").exists():
        rl = bambu.slice_project(work / "design-lid.3mf", work / "sliced_lid")
        out["lid_print"] = rl
    return out


def palette_match(photo, k=4):
    """Dominant colours of a photo -> the nearest filaments in the palette (k-means on a small copy)."""
    from PIL import Image
    from . import build
    im = Image.open(photo).convert("RGB"); im.thumbnail((160, 160))
    a = np.asarray(im, float).reshape(-1, 3)
    rng = np.random.default_rng(1); c = a[rng.choice(len(a), k, replace=False)]
    for _ in range(12):
        lab = np.argmin(((a[:, None, :] - c[None]) ** 2).sum(-1), axis=1)
        c = np.array([a[lab == i].mean(0) if (lab == i).any() else c[i] for i in range(k)])
    share = np.bincount(lab, minlength=k) / len(lab)
    from skimage.color import rgb2lab                      # perceptual distance: beige is near Bone White, not pink
    lab_of = lambda rgb: rgb2lab(np.asarray(rgb, float).reshape(1, 1, 3) / 255.0)[0, 0]
    pal = {n: lab_of([int(h[i:i + 2], 16) for i in (1, 3, 5)]) for n, h in build.PALETTE.items()}
    out = []
    for ci, sh in sorted(zip(c, share), key=lambda t: -t[1]):
        lc = lab_of(ci)
        name = min(pal, key=lambda n: ((pal[n] - lc) ** 2).sum())
        out.append(dict(seen="#%02X%02X%02X" % tuple(int(v) for v in ci), share=round(float(sh), 2),
                        filament=name, hex=build.PALETTE[name]))
    return out
