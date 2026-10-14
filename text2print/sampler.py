"""Test plates: small coupons of every texture, one family per plate so the coupons genuinely share settings.
Print a plate, then record what you see:  python -m text2print verify fringe 0.4 ok --note "..."

    python -m text2print sampler --nozzle 0.4 --out ~/Downloads/text2print/test-plates
"""
import pathlib

import numpy as np

from . import bambu, build, compose, printer

COLOURS = ["#C3302C", "#EDE3D1"]

PLATES = {
    "woven": dict(name="Woven", coupons=[
        ("coaster", "twill", {"width": 70, "height": 8, "dish": 0, "corner": 12, "pillow": 2}, {}),
        ("coaster", "kagome", {"width": 70, "height": 8, "dish": 0, "corner": 12, "pillow": 2}, {}),
        ("coaster", "overunder", {"width": 70, "height": 8, "dish": 0, "corner": 12, "pillow": 2}, {}),
        ("dish", "polar", {"diameter": 70, "height": 10, "dish": 44, "floor": 3, "pillow": 2}, {}),
    ]),
    # every colour coupon has its halftone band in the same place: Bambu's prime tower needs one shared set of
    # layer-height ranges across all objects on the plate
    "colour": dict(name="Colour", coupons=[
        ("cup", "mix", {"diameter": 50, "height": 40}, {"bands": [
            dict(texture="halftone", share=45, slot=0, slot2=1, options={"picture": pic}),
            dict(texture=top, share=55, slot=sl)]})
        for pic, top, sl in (("flames", "zigzag", 1), ("dots", "drips", 0), ("chevron", "wave", 1))]),
    "droop": dict(name="Droop", coupons=[
        ("cup", s, {"diameter": 44, "height": 50, "wall": 6, "floor": 3}, {"length": "short"})
        for s in ("fringe", "swag", "curls", "unraveled")]),
    "fabric": dict(name="Fabric & relief", coupons=[
        ("cup", s, {"diameter": 50, "height": 40}, {}) for s in ("zigzag", "domes", "wave", "garland", "drips", "melt")]),
}


def _layout(halves, bed=printer.BED, tower=printer.TOWER, gap=8.0):
    """Shelf-pack square footprints (half widths) into the bed, keeping clear of the prime tower corner."""
    t0 = tower[0] - tower[2] / 2 - gap
    pos, x, y, row_h = [], gap, gap, 0.0
    for h in halves:
        w = 2 * h
        if x + w > bed - gap:
            x, y = gap, y + row_h + gap; row_h = 0.0
        cx, cy = x + h, y + h
        if cx + h > t0 and cy + h > t0:                       # would sit on the tower: next row
            x, y = gap, y + row_h + gap; row_h = 0.0; cx, cy = x + h, y + h
        if cy + h > bed - gap:
            raise ValueError("coupons don't fit on one plate")
        pos.append((cx, cy)); x += w + gap; row_h = max(row_h, w)
    return pos


def plate(key, nozzle=0.4, colours=None):
    spec = PLATES[key]; colours = colours or COLOURS
    builds = [build.make(s, t, p, nozzle=nozzle, colours=colours, options=o) for s, t, p, o in spec["coupons"]]
    halves = [max(np.abs(m.bounds[:, :2]).max() for _, m, _, _ in b.parts) for b in builds]
    pos = _layout(halves)
    used = []
    for b in builds:
        for _, _, _, c in b.parts:
            if c not in used:
                used.append(c)
    objects = []
    for b, (cx, cy) in zip(builds, pos):
        parts = [(n, m, used.index(c) + 1) for n, m, _, c in b.parts]
        objects.append({"name": b.title(), "position": (cx, cy), "parts": parts, "ranges": b.ranges})
    # one family per plate: the first coupon's settings are the plate's; droop slots keep droop cooling
    over = dict(builds[0].overrides); over["flush_multiplier"] = ["1"]
    kinds = ["droop" if any(bb.family == "droop" or (bb.per_filament and "20" in bb.per_filament.get("fan_max_speed", [])) for bb in builds) else "normal"
             for _ in used]
    per_f = printer.filament_settings(nozzle, kinds) if any(k == "droop" for k in kinds) else None
    return dict(name=spec["name"], objects=objects, colours=used, overrides=over, per_filament=per_f, builds=builds)


def write(key, path, nozzle=0.4, colours=None):
    p = plate(key, nozzle, colours)
    bambu.write_3mf(str(path), p["objects"], title=f"text2print test plate — {p['name']} ({nozzle} mm)",
                    colours=tuple(p["colours"]), overrides=p["overrides"], base=printer.base_config(nozzle),
                    per_filament=p["per_filament"])
    return p


def write_all(out, nozzle=0.4, slice_=False):
    out = pathlib.Path(out).expanduser(); out.mkdir(parents=True, exist_ok=True); report = {}
    for key in PLATES:
        path = out / f"test-plate-{key}-{nozzle:g}mm.3mf"
        p = write(key, path, nozzle)
        report[key] = dict(project=str(path), coupons=[b.texture for b in p["builds"]])
        if slice_:
            report[key]["slice"] = bambu.slice_project(path, out / f".slice-{key}")
    return report
