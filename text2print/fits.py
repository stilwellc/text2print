"""Things functional parts keep needing, built once (each was first written by hand inside a one-off, Nov 2026):

    coupon         a small print that tests a clearance before the real part is printed
    split_keyed    cut a part in two with dovetail keys that slide together
    crush_ribs     ribs inside a bore that grip whatever is pushed in
    bump           a click bump on a wall
    sheet_slot     a slot that holds a sheet (acrylic, card), with a lead-in
    grille         a field of holes that will actually print on the plate
    trace / inlay  a picture or words as a second colour set flush in a face, thin features removed
    artwork_check  does the sliced first layer print that artwork? (a clean render is not proof)

Geometry is manifold3d (solids) and shapely (flat art), in mm. Pass the results to part.deliver()."""
import math

import numpy as np

FITS = {"press": 0.05, "snug": 0.15, "slip": 0.25, "loose": 0.40}     # a side, PLA on the 0.4 nozzle; PETG wants ~0.05 more
STEPS = (0.10, 0.15, 0.20, 0.25, 0.30, 0.40)
MIN_HOLE, MIN_LAND = 3.0, 2.5                                         # holes in a face on the plate (1.8 mm holes lost 10 %)
DOVETAIL = dict(neck=1.8, head=3.0, depth=2.0, height=4.0, clear=0.12)


def _m3():
    import manifold3d as m3
    return m3


def _mesh(man):
    from .meshops import manifold_to_trimesh
    return manifold_to_trimesh(man, split=False)


def _notches(n, x, y, z, size=1.2):
    """n small square notches in a row from (x, y), cut through z: how a coupon says which step is which."""
    m3 = _m3(); out = m3.Manifold()
    for k in range(n):
        out += m3.Manifold.cube([size, size * 2, z + 2], True).translate([x + k * size * 2, y, z / 2])
    return out


def coupon(kind, nominal, steps=STEPS, thickness=4.0, depth=8.0):
    """A test piece for one fit, at each clearance in `steps` (mm a side), smallest first; notches count the step
    (one notch = the first). Print it, try the real thing in it, and use the step that feels right.

    "hole"      a bar of round holes for a pin, pipe or peg of diameter `nominal` (up to 40 mm)
    "slot"      a comb of slots for a sheet of thickness `nominal`, `depth` deep
    "dovetail"  a bar of dovetail slots and one key (split_keyed's key); nominal is ignored, and the bar's cut
                corner marks the tightest slot
    -> {"parts": [(name, mesh)], "steps": steps, "size": (x, y, z)}"""
    m3 = _m3(); steps = tuple(float(s) for s in steps); n = len(steps)
    if kind == "hole":
        if not 1.0 <= nominal <= 40.0:
            raise ValueError("a hole coupon tests diameters from 1 to 40 mm; for a larger one print a ring of the real part")
        land = max(2.5, nominal * 0.18); pitch = nominal + 2 * steps[-1] + land; L, W = n * pitch + land, nominal + 2 * steps[-1] + 2 * land + 3
        bar = m3.Manifold.cube([L, W, thickness]).translate([-L / 2, -W / 2, 0])
        for i, c in enumerate(steps):
            x = -L / 2 + land + pitch * i + (pitch - land) / 2
            r = nominal / 2 + c
            bar -= m3.Manifold.cylinder(thickness + 2, r, r, 96).translate([x, -1.5, -1])
            bar -= _notches(i + 1, x - (i * 1.2), W / 2 - 1.2, thickness)
        return {"parts": [("coupon", _mesh(bar))], "steps": steps, "size": (round(L, 2), round(W, 2), thickness)}
    if kind == "slot":
        if not 0.4 <= nominal <= 12.0:
            raise ValueError("a slot coupon tests sheets from 0.4 to 12 mm thick")
        land = 3.0; pitch = nominal + 2 * steps[-1] + land; L, H = n * pitch + land, depth + 3.0; W = 12.0
        bar = m3.Manifold.cube([L, W, H]).translate([-L / 2, -W / 2, 0])
        for i, c in enumerate(steps):
            x = -L / 2 + land + pitch * i + (pitch - land) / 2
            bar -= sheet_slot(nominal, W + 2, depth, c).translate([x, 0, H])
            bar -= m3.Manifold.cube([1.2, 1.2 * (i + 1) * 2, 1.2], True).translate([x - (nominal / 2 + c + 1.5), -W / 2, H])
        return {"parts": [("coupon", _mesh(bar))], "steps": steps, "size": (round(L, 2), W, H)}
    if kind == "dovetail":
        d = DOVETAIL; land = 4.0; pitch = d["head"] + 2 * steps[-1] + land; L = n * pitch + land; W = d["depth"] + 5.0; H = d["height"] + 1.5
        bar = m3.Manifold.cube([L, W, H]).translate([-L / 2, 0, 0])
        for i, c in enumerate(steps):
            x = -L / 2 + land + pitch * i + (pitch - land) / 2
            bar -= _dovetail(d["neck"], d["head"], d["depth"], c).extrude(H + 2).translate([x, W, -1])
        bar -= m3.Manifold.cube([3.0, 3.0, H + 2], True).rotate([0, 0, 45]).translate([-L / 2, 0, H / 2])    # the cut corner is the tight end
        key = _dovetail(d["neck"], d["head"], d["depth"], 0).extrude(d["height"]) + m3.Manifold.cube([8.0, 6.0, d["height"]]).translate([-4.0, 0.3 - 0.01, 0])
        return {"parts": [("coupon", _mesh(bar)), ("key", _mesh(key))], "steps": steps, "size": (round(L, 2), W, H)}
    raise ValueError(f"unknown coupon '{kind}': hole, slot or dovetail")


def _dovetail(neck, head, depth, clear):
    """The key's plan: neck on y = 0, head at y = -depth (it grows toward -y), with a 0.3 root above y = 0."""
    m3 = _m3(); n, h = neck / 2, head / 2
    cs = m3.CrossSection([[(-h, -depth), (h, -depth), (n, 0), (n, 0.3), (-n, 0.3), (-n, 0)]])
    return cs.offset(clear, m3.JoinType.Miter) if clear else cs


def split_keyed(body, key_x, neck=1.8, head=3.0, depth=2.0, height=4.0, clear=0.12, z0=0.0):
    """Cut `body` (a Manifold) in two on the plane y = 0 and join the halves with dovetail keys that slide together
    along z: keys stand on half A (y > 0) at each x in key_x and reach `depth` into half B, from z0 up `height`,
    with a 45 deg roof so they print without support; half B gets the slots, `clear` larger a side. Both halves
    print as they sit. Turn the body first if the cut belongs elsewhere. Raises if a key or slot would break
    through the body's skin or the halves would collide. clear 0.12 is a snug slide in PETG — not print-tested;
    print coupon("dovetail") first. -> (A, B)"""
    m3 = _m3()
    dove = _dovetail(neck, head, depth, 0)
    roof = min(0.8, height / 2)
    key = dove.extrude(height - roof) + dove.translate((0, depth / 2)).extrude(roof, 0, 0, (0.8, 0.8)).translate((0, -depth / 2, height - roof))
    slot = _dovetail(neck, head, depth, clear).extrude(height + 0.5)
    keys, slots = m3.Manifold(), m3.Manifold()
    for x in key_x:
        keys += key.translate((float(x), 0, z0)); slots += slot.translate((float(x), 0, z0 - (0.01 if z0 > 0 else 0)))
    if (keys - body).volume() > 1e-6 or (slots - body).volume() > 1e-6:
        raise ValueError("a key or its slot leaves the body: move key_x into thicker material, or make the key smaller")
    top, bot = body.split_by_plane((0, 1, 0), 0)
    A, B = top + (keys ^ body), bot - slots
    if (A ^ B).volume() > 1e-6:
        raise ValueError("the halves collide")
    return A, B


def crush_ribs(bore_d, height, n=6, bite=0.3, width=1.2, z0=0.0, lead=1.0):
    """n ribs standing `bite` into a bore of diameter bore_d (make the bore `bite` larger than the thing, a side, and
    the ribs take up the difference): they crush a little and hold a part whose size varies. A `lead` mm chamfer at
    the top lets it start. Add the result to the body. -> Manifold"""
    m3 = _m3(); r = bore_d / 2; out = m3.Manifold()
    rib = m3.Manifold.cube([bite + 0.6, width, height]).translate([r - bite, -width / 2, z0])
    if lead > 0:                                         # cut the top inner corner at 45 deg
        wedge = m3.Manifold.cube([bite * 2, width + 1, bite * 2], True).rotate([0, 45, 0]).translate([r - bite, 0, z0 + height])
        rib -= wedge
    for k in range(int(n)):
        out += rib.rotate([0, 0, 360.0 * k / n])
    return out


def bump(at, normal, proud=1.2, width=12.0, length=None):
    """A click bump on a wall: a ridge `proud` high with 45 deg flanks both ways, `width` long, centred at `at` and
    standing out along `normal` (an axis: "+x", "-x", "+y", "-y"). The flanks run along z, so something pushed along
    z rides over it and clicks behind. Put it on a thin wall that can flex (2 mm), not a solid block. -> Manifold"""
    m3 = _m3(); length = 2 * proud if length is None else length
    tri = m3.CrossSection([[(0, -length / 2), (proud, 0), (0, length / 2), (-0.3, length / 2), (-0.3, -length / 2)]])
    b = tri.extrude(width).translate((0, 0, -width / 2)).rotate([90, 0, 0])            # proud along +x, flanks along z, long along y
    rot = {"+x": 0, "+y": 90, "-x": 180, "-y": 270}[normal]
    return b.rotate([0, 0, rot]).translate([float(c) for c in at])


def sheet_slot(thickness, length, depth, clear=FITS["slip"], lead=0.6):
    """A cutter for a slot that holds a sheet `thickness` thick: open at z = 0 and running `depth` down, `length`
    along y, `clear` a side, with a `lead` chamfer at the mouth. Translate it to the face and subtract. -> Manifold"""
    m3 = _m3(); w = thickness / 2 + clear
    sec = m3.CrossSection([[(-w, -depth), (w, -depth), (w, -lead), (w + lead, 0), (w + lead, 0.5), (-w - lead, 0.5), (-w - lead, 0), (-w, -lead)]])
    return sec.extrude(length).translate((0, 0, -length / 2)).rotate([90, 0, 0])


def grille(width, height, thickness, hole=MIN_HOLE, land=MIN_LAND, margin=None, corner=0.0, pattern="square", on_plate=True, blind=0.0):
    """A cutter of round holes over a width x height field centred on the origin (z from 0 to thickness; blind > 0
    leaves a floor that thick at z = 0). pattern "square" or "hex". On a face that prints on the plate, holes under
    3 mm or lands under 2.5 mm are refused: 1,033 holes of 1.8 mm lost about one in ten on layer one. The grid is
    stretched to fill the field evenly, a column on the centre line. corner rounds the field's corners.
    Slice with bambu.PERFORATED_WALLS + SMALL_LOOPS_FIRST_LAYER. -> (Manifold, hole count)"""
    m3 = _m3()
    if on_plate and (hole < MIN_HOLE or land < MIN_LAND):
        raise ValueError(f"holes of {hole:g} mm with {land:g} mm lands will not all print on the plate: "
                         f"use holes of {MIN_HOLE:g} or more and lands of {MIN_LAND:g} or more (or on_plate=False for a face printed upright)")
    margin = land if margin is None else margin; r = hole / 2
    fw, fh = width - 2 * margin - hole, height - 2 * margin - hole
    if fw < 0 or fh < 0:
        raise ValueError("the field is too small for one hole inside its margin")
    p = hole + land; rows_p = p * (math.sqrt(3) / 2 if pattern == "hex" else 1.0)
    nx = int(fw // p); nx -= nx % 2                      # an even number of gaps: one column on the centre line
    ny = int(fh // rows_p)
    px = fw / nx if nx else 0.0; py = fh / ny if ny else 0.0
    cr = max(0.0, corner - margin)

    def inside(x, y):
        dx, dy = abs(x) - (width / 2 - margin - cr), abs(y) - (height / 2 - margin - cr)
        return (dx <= 0 or dy <= 0 or math.hypot(dx, dy) <= cr - r + 1e-9) if cr > 0 else True
    cyl = m3.Manifold.cylinder(thickness - blind + 1, r, r, 48).translate([0, 0, blind])
    holes = []
    for j in range(ny + 1):
        y = -fh / 2 + j * py
        shift = (px / 2) if (pattern == "hex" and j % 2) else 0.0
        for i in range(nx + 1 - (1 if shift else 0)):
            x = -fw / 2 + i * px + shift
            if inside(x, y):
                holes.append(cyl.translate([x, y, 0]))
    return (m3.Manifold.compose(holes) if holes else m3.Manifold()), len(holes)


# ── two-colour art set flush in a face ─────────────────────────────────────────────────────────────────────────────
def printable(geom, min_feature=0.4, min_area=0.12):
    """Flat art with everything a nozzle cannot draw removed: gaps narrower than min_feature are closed, slivers
    thinner than it are dropped, specks under min_area mm2 go. -> (geometry, {"kept": the share of the drawing that
    survives unchanged (1 = all of it), "pieces"})"""
    from shapely.ops import unary_union
    h = min_feature / 2; g = geom.buffer(0)
    out = g.buffer(h, join_style=1).buffer(-h, join_style=1).buffer(-h, join_style=1).buffer(h, join_style=1)
    ps = [p for p in (out.geoms if hasattr(out, "geoms") else [out]) if p.area > min_area]
    out = unary_union(ps).simplify(0.02) if ps else out
    changed = out.symmetric_difference(g).area / g.area if g.area else 1.0     # filled gaps count as loss too
    return out, {"kept": round(max(0.0, 1.0 - changed), 3), "pieces": len(ps)}


def trace(image, width_mm, min_feature=0.4, dark=True, threshold=128):
    """A picture -> flat art in mm, centred on the origin, `width_mm` wide: the dark pixels (or the light ones with
    dark=False), traced, then made printable(). White shapes inside black ones stay white.
    -> (shapely geometry, info)"""
    import skimage.measure as skm
    from PIL import Image, ImageFilter
    from shapely.geometry import Polygon
    im = (Image.open(image) if not hasattr(image, "convert") else image).convert("L")
    k = max(1, int(round(1600 / max(im.size))))
    im = im.resize((im.width * k, im.height * k), Image.LANCZOS).filter(ImageFilter.GaussianBlur(0.6 * k))
    a = np.asarray(im, float); on = np.pad(((a < threshold) if dark else (a >= threshold)).astype(float), 4)
    ys, xs = np.nonzero(on)
    if not len(xs):
        raise ValueError("nothing to trace: the picture has no " + ("dark" if dark else "light") + " pixels")
    cx, cy = (xs.min() + xs.max()) / 2, (ys.min() + ys.max()) / 2; s = width_mm / max(1, xs.max() - xs.min())
    geom = None
    for c in skm.find_contours(on, 0.5):
        if len(c) < 12:
            continue
        q = Polygon(np.column_stack([(c[:, 1] - cx) * s, -(c[:, 0] - cy) * s])).buffer(0)
        if q.is_empty or q.area < 0.03:
            continue
        geom = q if geom is None else geom.symmetric_difference(q)
    if geom is None:
        raise ValueError("nothing to trace")
    out, info = printable(geom.simplify(0.02), min_feature)
    info["size"] = (round(out.bounds[2] - out.bounds[0], 2), round(out.bounds[3] - out.bounds[1], 2))
    return out, info


def words(text, height_mm=8.0, font="futura", min_feature=0.4):
    """Words -> printable flat art, centred, `height_mm` tall. -> (geometry, info)"""
    from .extras import text_polygons
    return printable(text_polygons(text, font, height_mm), min_feature)


def inlay(body, art, depth=0.6, face="bottom", at=(0.0, 0.0)):
    """Set flat art into a face of `body` (a Manifold) as a second colour, flush: -> (body with the pocket, the inlay).
    face "bottom" = the face on the plate (the crispest: the art is mirrored for you so it reads right from below);
    "top" = the top face. depth 0.6 = three 0.2 layers. Deliver the two as parts of one piece, slots 1 and 2, and
    check the sliced file with artwork_check()."""
    from shapely import affinity
    from .extras import prism
    lo = body.bounding_box()[:3]; hi = body.bounding_box()[3:]
    g = affinity.scale(art, xfact=-1, origin=(0, 0)) if face == "bottom" else art
    g = affinity.translate(g, at[0], at[1])
    polys = [p for p in (g.geoms if hasattr(g, "geoms") else [g]) if p.area > 0]
    z0, z1 = (lo[2], lo[2] + depth) if face == "bottom" else (hi[2] - depth, hi[2])
    plug = prism(polys, z0 - 0.5, z1 + 0.5) ^ body
    m3 = _m3(); slab = m3.Manifold.cube([hi[0] - lo[0] + 2, hi[1] - lo[1] + 2, depth]).translate([lo[0] - 1, lo[1] - 1, z0])
    plug = plug ^ slab
    if plug.volume() < 1e-6:
        raise ValueError("the art misses the body's face")
    return body - plug, plug


def artwork_check(sliced, want, centre, z=None, half=None, mirror=False, out_png=None, px=0.05):
    """Does the sliced layer print the art? Rasterises every extrusion of one layer at its real width, by filament,
    and compares it with what was drawn. want: {filament number: shapely geometry} in the piece's own coordinates
    (as modelled, y up), centre: the piece's (x, y) on the plate, z: the layer's height (default: the first layer),
    mirror=True when the art was mirrored into the bottom face by inlay(). -> {filament: {"area", "printed" (share
    of the art laid in its own colour), "wrong_colour", "bare"}}; out_png saves a picture: red = art printed in
    another colour, amber = art not printed at all. A share under about 0.9 means features too fine for the nozzle."""
    import re
    from PIL import Image, ImageDraw
    from shapely import affinity
    from . import bambu
    g = bambu.load_gcode(sliced)
    flow = float(str(bambu.gcode_setting(g, "filament_flow_ratio") or "1").split(",")[0])
    lh = None
    bounds = [w.bounds for w in want.values()]
    half = half or max(max(abs(v) for v in b) for b in bounds) + 2.0
    N = int(2 * half / px)
    to_px = lambda x, y: ((x - centre[0] + half) / px, (half - (y - centre[1])) / px)
    segs = {}; tool = None; cur_z = None; prev = None; first = None
    for l in g:
        if tool is None and l.startswith(";VT"):
            mv = re.match(r";VT(\d+)", l); tool = int(mv.group(1)) + 1 if mv else None
        mt = re.match(r"^T(\d+)\b", l)
        if mt and int(mt.group(1)) <= 15:
            tool = int(mt.group(1)) + 1
        if l.startswith("; Z_HEIGHT:"):
            cur_z = float(l.split(":")[1]); continue
        if l.startswith("; LAYER_HEIGHT:"):
            lh = float(l.split(":")[1]); continue
        if not re.match(r"^G[0-3] ", l):
            continue
        mx, my, me = re.search(r"X([-\d.]+)", l), re.search(r"Y([-\d.]+)", l), re.search(r"E([-\d.]+)", l)
        if mx is None and my is None:
            continue
        x = float(mx.group(1)) if mx else (prev[0] if prev else 0.0); y = float(my.group(1)) if my else (prev[1] if prev else 0.0)
        near = lambda q: abs(q[0] - centre[0]) < half and abs(q[1] - centre[1]) < half
        if me and float(me.group(1)) > 0 and prev is not None and cur_z is not None and (near((x, y)) or near(prev)):
            if first is None:
                first = cur_z
            if abs(cur_z - (first if z is None else z)) < 0.02:
                if l[1] in "23":
                    mi, mj = re.search(r"I([-\d.]+)", l), re.search(r"J([-\d.]+)", l)
                    i, j = float(mi.group(1)) if mi else 0.0, float(mj.group(1)) if mj else 0.0
                    c = (prev[0] + i, prev[1] + j); r = math.hypot(i, j)
                    a0, a1 = math.atan2(prev[1] - c[1], prev[0] - c[0]), math.atan2(y - c[1], x - c[0])
                    if l[1] == "2" and a1 >= a0: a1 -= 2 * math.pi
                    if l[1] == "3" and a1 <= a0: a1 += 2 * math.pi
                    n = max(2, int(abs(a1 - a0) * r / 0.25) + 1)
                    pts = [(c[0] + r * math.cos(t), c[1] + r * math.sin(t)) for t in np.linspace(a0, a1, n)]; L = abs(a1 - a0) * r
                else:
                    pts, L = [prev, (x, y)], math.hypot(x - prev[0], y - prev[1])
                h = lh or 0.2
                if L > 1e-4:
                    w = float(me.group(1)) * math.pi * 0.875 ** 2 / flow / (L * h) + h * (1 - math.pi / 4)
                    if 0.15 < w < 1.6:
                        segs.setdefault(tool, []).extend((a, b, w) for a, b in zip(pts[:-1], pts[1:]))
        prev = (x, y)
    got = {}
    for t, ss in segs.items():
        im = Image.new("1", (N, N), 0); d = ImageDraw.Draw(im)
        for a, b, w in ss:
            pa, pb = to_px(*a), to_px(*b); d.line([pa, pb], fill=1, width=max(1, int(round(w / px))))
            r = w / px / 2; d.ellipse([pb[0] - r, pb[1] - r, pb[0] + r, pb[1] + r], fill=1)
        got[t] = np.asarray(im)
    none = np.zeros((N, N), bool); anyc = none.copy()
    for m in got.values():
        anyc = anyc | m
    res = {}; rgb = np.full((N, N, 3), 244, np.uint8)
    shade = {1: (236, 236, 230), 2: (24, 24, 24), 3: (150, 150, 150), 4: (90, 90, 90)}
    for t, m in got.items():
        rgb[m] = shade.get(t, (120, 120, 120))
    for t, geom in want.items():
        gg = affinity.scale(geom, xfact=-1, origin=(0, 0)) if mirror else geom
        im = Image.new("1", (N, N), 0); d = ImageDraw.Draw(im)
        for q in (gg.geoms if hasattr(gg, "geoms") else [gg]):
            if q.is_empty or not hasattr(q, "exterior"):
                continue
            f = lambda cs: [to_px(centre[0] + x, centre[1] + y) for x, y in cs]
            d.polygon(f(q.exterior.coords), fill=1)
            for hole in q.interiors:
                d.polygon(f(hole.coords), fill=0)
        wm = np.asarray(im); mine = got.get(int(t), none); A = max(1, int(wm.sum()))
        others = anyc & ~mine
        res[int(t)] = {"area": round(float(wm.sum()) * px * px, 1), "printed": round(float((wm & mine).sum()) / A, 3),
                       "wrong_colour": round(float((wm & others).sum()) / A, 3), "bare": round(float((wm & ~anyc).sum()) / A, 3)}
        rgb[wm & others] = (230, 60, 60); rgb[wm & ~anyc] = (250, 190, 40)
    if out_png:
        Image.fromarray(rgb).resize((1000, 1000), Image.LANCZOS).save(out_png)
    return res
