"""Plain things people ask for first, as functional parts (solid walls, 3 lines thick; not the one-line textured
shells of the catalogue): a can or box with a lid that fits, and a plaque with words or a mark set flush in it.
Each returns what part.deliver() takes:

    from text2print import basics, part
    part.deliver("can", **basics.can(70, 40, lid="thread"), colours=["#FFFFFF"], material="petg", slice=True)
"""
import math

import numpy as np

from . import extras, fits
from .meshops import manifold_to_trimesh

WALL, FLOOR = 2.4, 2.0


def _tm(man):
    return manifold_to_trimesh(man, split=False)


def can(diameter, height, wall=WALL, floor=FLOOR, lid="thread", fit="slip"):
    """A round can `diameter` across and `height` tall (outside, lid off) with a lid: "thread" (two-start, about one
    turn; needs an opening of 37 mm or more), "slip" (a plug with a lead-in) or "none". The lid sits flush with the
    wall and prints top-face down. -> {"parts": {"Base": [...], "Lid": [...]}, "check": {...}, "notes": [...]}"""
    import manifold3d as m3
    R = diameter / 2; r = R - wall
    if r < 8 or height < floor + 8:
        raise ValueError("too small: the can needs an opening of 16 mm and 8 mm of depth")
    if lid == "thread" and r <= 18.5:
        raise ValueError("a screw lid needs a can 42 mm or more across; use lid='slip'")
    n = max(96, int(2 * math.pi * R / 1.0))
    base = m3.Manifold.cylinder(height, R, R, n) - m3.Manifold.cylinder(height, r, r, n).translate([0, 0, floor])
    out = {"parts": {"Base": [("Base", None, 1)]}, "check": {"can height": (float(height), "z", None, "Base"),
                                                          "can diameter": (float(diameter), "x", None, "Base")}, "notes": []}
    if lid != "none":
        ls = extras.lid_set(lid, R - 0.6, r, height, fit, knob=False)      # the plate is rim_r + 0.6: flush with the wall
        for ring in ls["rim"]:
            base += extras._m3d(ring) ^ m3.Manifold.cylinder(height, R, R, n)
        out["parts"]["Lid"] = [("Lid", ls["lid"], 1)]; out["notes"] = ls["notes"] + [f"Lid clearance {ls['clearance']} mm a side ({fit})."]
        out["check"]["lid diameter"] = (float(diameter), "x", None, "Lid")
    out["parts"]["Base"] = [("Base", _tm(base), 1)]
    return out


def _rounded(w, d, c):
    from shapely.geometry import box as _box
    c = max(0.5, min(c, min(w, d) / 2 - 0.01))
    return _box(-w / 2 + c, -d / 2 + c, w / 2 - c, d / 2 - c).buffer(c, quad_segs=24)


def box(width, depth, height, corner=8.0, wall=WALL, floor=FLOOR, lid="slip", fit="slip"):
    """A rounded box (outside sizes, lid off) with a slip lid whose plug follows the opening, or lid="none".
    -> {"parts": {"Base": [...], "Lid": [...]}, "check": {...}, "notes": [...]}"""
    outer = _rounded(width, depth, corner); inner = outer.buffer(-wall, join_style=1)
    if inner.is_empty or inner.area < 150 or height < floor + 8:
        raise ValueError("too small: the box needs an opening and 8 mm of depth")
    base = extras.prism([outer], 0, height) - extras.prism([inner], floor, height + 1)
    out = {"parts": {"Base": [("Base", _tm(base), 1)]}, "notes": [],
           "check": {"box width": (float(width), "x", None, "Base"), "box depth": (float(depth), "y", None, "Base"),
                     "box height": (float(height), "z", None, "Base"),
                     "opening": (float(width - 2 * wall), "x", (0.0, 0.0, floor + 4.0), "Base")}}
    if lid != "none":
        ls = extras._lid_from_polys(inner, outer.buffer(-0.6, join_style=1), extras.FITS.get(fit, 0.25), knob=False)
        if ls is None:
            raise ValueError("the opening is too small for a lid's plug")
        out["parts"]["Lid"] = [("Lid", ls["lid"], 1)]; out["notes"] = ls["notes"]
    return out


def plaque(width, height, text=None, image=None, thickness=3.0, corner=4.0, text_height=None, margin=6.0, hole=0.0, face="bottom",
           depth=0.6, min_feature=0.4):
    """A rounded plate with words and/or a traced picture set flush in it as a second colour. face "bottom" puts the
    art on the plate side (the crispest face; it is mirrored so it reads right) — "top" on the top face. With both,
    the picture sits above the words. hole > 0 adds a hanging hole that size in the top-left corner. Art that will
    not print (under min_feature) is removed and reported.
    -> {"parts": [("Plate", mesh, 1), ("Art", mesh, 2)], "check", "art" (the flat art, for fits.artwork_check),
        "notes", "mirror"}"""
    import manifold3d as m3
    from shapely import affinity
    from shapely.ops import unary_union
    if not text and not image:
        raise ValueError("a plaque wants text, an image, or both")
    room_w, room_h = width - 2 * margin, height - 2 * margin; arts, notes = [], []
    if image:
        pic, info = fits.trace(image, room_w, min_feature)
        ph = room_h * (0.6 if text else 1.0); k = min(1.0, ph / max(1e-6, pic.bounds[3] - pic.bounds[1]))
        pic = affinity.scale(pic, k, k, origin=(0, 0)); pic, info = fits.printable(pic, min_feature)
        pic = affinity.translate(pic, 0, (room_h / 2 - (pic.bounds[3] - pic.bounds[1]) / 2 - pic.bounds[1] - (pic.bounds[3] - pic.bounds[1]) / 2) if text else 0)
        arts.append(pic); notes.append(f"picture: {info['pieces']} pieces, {info['kept'] * 100:.0f} % of the drawn area prints")
    if text:
        th = float(text_height or (room_h * (0.28 if image else 0.5)))
        w_, _ = fits.words(text, th, min_feature=min_feature)
        bw = w_.bounds[2] - w_.bounds[0]
        if bw > room_w:
            w_ = affinity.scale(w_, room_w / bw, room_w / bw, origin=(0, 0))
        w_, info = fits.printable(w_, min_feature)
        cy = (w_.bounds[1] + w_.bounds[3]) / 2
        w_ = affinity.translate(w_, -(w_.bounds[0] + w_.bounds[2]) / 2, (-room_h / 2 + (w_.bounds[3] - w_.bounds[1]) / 2 - cy) if image else -cy)
        arts.append(w_); notes.append(f"words: {info['kept'] * 100:.0f} % of the drawn area prints")
        if info["kept"] < 0.9:
            notes.append("the words lose detail at this size: make them taller or the plaque wider")
    art = unary_union(arts)
    plate = extras.prism([_rounded(width, height, corner)], 0, thickness)
    if hole > 0:
        plate -= m3.Manifold.cylinder(thickness + 2, hole / 2, hole / 2, 48).translate([-width / 2 + margin, height / 2 - margin, -1])
    body, plug = fits.inlay(plate, art, depth=depth, face=face)
    return {"parts": [("Plate", _tm(body), 1), ("Art", _tm(plug), 2)], "art": art, "mirror": face == "bottom", "notes": notes,
            "check": {"plaque width": (float(width), "x"), "plaque height": (float(height), "y"), "plaque thickness": (float(thickness), "z")}}
