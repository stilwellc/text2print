"""Underside spec plate for the megalodon stand: rim rings + ring text,
tooth line drawing with L1 / L2 / W dimension lines, and the weight.

Everything is drawn as 2D shapely geometry in *reading* coordinates (as seen with
the stand turned over), then mirrored and extruded into cutters for a mesh-level cut.
"""
import math
import pathlib
import manifold3d as m3d
import numpy as np
from matplotlib.font_manager import FontProperties
from matplotlib.textpath import TextPath
from shapely import affinity
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

# ── PARAMETERS ── all dimensions in mm ─────────────────────────────────
FONT       = "/System/Library/Fonts/HelveticaNeue.ttc"
CAP_EM     = 0.714     # Helvetica Neue cap height / em
EMBOLDEN   = 0.10      # faux-bold offset per side: regular stems (0.095 em) reach the 0.6mm deboss minimum
STROKE     = 0.7       # line weight for rings, drawing and dimension lines
DEPTH      = 1.0       # deboss depth: 10 layers at 0.1, 5 at 0.2 — deep enough to read by shadow
MIN_LAND   = 0.45      # thinnest plastic left between engraved features: 2 line widths on a 0.2mm nozzle

RING_OUT   = 61.0      # outer rim ring radius
RING_IN    = 51.5      # inner rim ring radius
RIM_BASE   = 54.6      # inner edge of the rim-text cap band
RIM_CAP    = 4.0
RIM_TOP    = "LECTR ARCHIVES"      # arcs over the top, reading clockwise
RIM_BOTTOM = "OTODUS MEGALODON"    # reads upright along the bottom
RIM_TRACK  = 1.3
RIM_DOT    = 0.9                   # dots at 3 and 9 o'clock


TOOTH_H    = 58.0      # drawing height, root top to tip (point down, as displayed)
TOOTH_TOP  = 34.0      # y of the root top
DIM_OFF    = 5.0       # dimension line offset from the edge it measures
DIM_TICK   = 2.6
DIM_CAP    = 3.6
SPEC_CAP   = 3.6
SPEC_Y     = -40.0

# tooth outline, normalised: tip at (0,0), root top at y=1; right half, mirrored for the left
_HALF = [(0.00, 0.00), (0.11, 0.21), (0.22, 0.42), (0.31, 0.61), (0.37, 0.72),
         (0.40, 0.78), (0.405, 0.86), (0.385, 0.93), (0.33, 0.985), (0.25, 1.00),
         (0.16, 0.985), (0.07, 0.955), (0.00, 0.94)]
_BOURLETTE = [(-0.37, 0.735), (0.00, 0.665), (0.37, 0.735)]   # chevron band between crown and root
EXT_STROKE = 0.56      # thin extension lines from the part to each dimension line
CHISEL     = False     # True: cut every stroke as a 45-deg V (stone-inscription style) instead of a
                       # flat-floored pocket — the roofs print as 45-deg slopes, so nothing bridges
CHISEL_STEP = 0.05     # height of each terrace in the chisel stack — 0.1 was tried: the STL reloads
                       # non-manifold (inset terraces pinch), so keep 0.05 and accept the bigger file
SMOOTH     = 0         # Chaikin passes on the tooth outline (0 = the original faceted polygon)

# ── NOZZLE PROFILES ── the defaults above are the 0.2mm profile; use_nozzle(0.4) swaps in a
# set sized in 0.45mm line widths: Medium weight instead of faux-bold Regular, 2-line strokes and
# 2-line lands so every gap and every letter counter gets a real perimeter loop
PROFILES = {
    0.2: {},
    # 0.4: chisel-cut, ~3-line (1.2mm) strokes so each V is ~0.6mm deep, bigger type so the
    # fattened letters keep open counters, and a smoothed tooth outline
    0.4: dict(FONT_FACE="HelveticaNeue-Medium", EMBOLDEN=0.15, STROKE=1.2, EXT_STROKE=1.0,
              MIN_LAND=0.9, RIM_CAP=5.4, RIM_BASE=53.8, RIM_TRACK=1.8, RIM_DOT=1.3,
              DIM_CAP=5.2, DIM_TICK=3.4, DIM_OFF=6.5, SPEC_CAP=5.0, SPEC_Y=-38.5,
              CHISEL=True, SMOOTH=3),
}
_TTC_FACES = {"HelveticaNeue-Medium": 10}   # face index inside HelveticaNeue.ttc


def _face_path(face):
    """matplotlib can only read face 0 of a .ttc — extract the wanted face to a cached .ttf."""
    out = pathlib.Path(__file__).with_name(".fonts") / f"{face}.ttf"
    if not out.exists():
        from fontTools.ttLib import TTCollection
        out.parent.mkdir(exist_ok=True)
        TTCollection(FONT).fonts[_TTC_FACES[face]].save(out)
    return str(out)


def use_nozzle(nozzle):
    """Switch every plate parameter to the profile for this nozzle diameter."""
    global _fp
    g = globals()
    g.update(_DEFAULTS)
    prof = dict(PROFILES[nozzle])
    face = prof.pop("FONT_FACE", None)
    g.update(prof)
    _fp = FontProperties(fname=_face_path(face) if face else FONT)


_DEFAULTS = {k: v for k, v in globals().items() if k.isupper() and not k.startswith("_")
             and k not in ("PROFILES",)}

# ── TEXT ─────────────────────────────────────────────────────────────
_fp = FontProperties(fname=FONT)


INCH = "\u2033"   # double prime — drawn by inch_mark(), not the font


def inch_mark(cap):
    """Inch mark as two slanted bars sized for the nozzle: the font's tiny double-prime fuses
    into one blob once emboldened, so bar width and the land between them follow the profile."""
    bar = max(0.7, STROKE * 0.75)
    gap = MIN_LAND + 2 * EMBOLDEN
    h = 0.38 * cap
    lean = 0.25 * h
    bars = [Polygon([(x, cap - h), (x + bar, cap - h), (x + bar + lean, cap), (x + lean, cap)])
            for x in (0.0, bar + gap)]
    return unary_union(bars).buffer(-EMBOLDEN)   # plate() emboldens everything; pre-shrink to keep the gap


def glyph(ch, cap):
    """One character as shapely geometry, baseline at y=0, left edge at x=0."""
    size = cap / CAP_EM
    geom = Polygon()
    if ch == INCH:
        return inch_mark(cap)
    if ch.isspace():                       # TextPath chokes on a bare space; advance() spaces it
        return geom
    for ring in TextPath((0, 0), ch, size=size, prop=_fp).to_polygons(closed_only=True):
        if len(ring) >= 3:
            geom = geom.symmetric_difference(Polygon(ring).buffer(0))   # even-odd fill = holes in o, e, a
    return geom


def advance(ch, cap):
    if ch == " ":
        return 0.28 * cap / CAP_EM
    g = glyph(ch, cap)
    return g.bounds[2] - g.bounds[0] if not g.is_empty else 0.0


def text_line(s, cap, track=0.4, cx=0.0, y=0.0, angle=0.0):
    """Tracked single line centred at (cx, y), rotated by angle (deg) about that centre.
    `track` is the visible gap after emboldening, floored at MIN_LAND (advance() is the
    tight glyph box, so without this a bold pass closes letter gaps to ~0.15mm)."""
    track = max(track, MIN_LAND) + 2 * EMBOLDEN
    parts, x = [], 0.0
    for ch in s:
        g = glyph(ch, cap)
        if not g.is_empty:
            parts.append(affinity.translate(g, x - g.bounds[0], 0))
        x += advance(ch, cap) + track
    line = affinity.translate(unary_union(parts), -(x - track) / 2, -cap / 2)
    return affinity.translate(affinity.rotate(line, angle, origin=(0, 0)), cx, y)


def arc_text(s, cap, r_band, track, bottom=False):
    """Text on an arc centred at 12 o'clock (or 6 o'clock with bottom=True, kept upright).
    The cap band always spans r_band .. r_band + cap."""
    r_base = r_band + cap if bottom else r_band     # bottom text hangs its caps inward
    widths = [advance(ch, cap) for ch in s]
    # gaps are measured at the baseline; on the bottom arc the caps converge toward the centre,
    # so pad by the shrink at cap height to keep MIN_LAND there too
    shrink = (sum(widths) / len(s)) * cap / r_base if bottom else 0.0
    track = max(track, MIN_LAND) + 2 * EMBOLDEN + shrink
    total = sum(widths) + track * (len(s) - 1)
    parts, arc = [], -total / 2
    for ch, w in zip(s, widths):
        mid = arc + w / 2
        if bottom:
            theta = -math.pi / 2 + mid / r_base     # left-to-right = counter-clockwise along the bottom
            rot = math.degrees(theta) + 90
        else:
            theta = math.pi / 2 - mid / r_base      # left-to-right = clockwise along the top
            rot = math.degrees(theta) - 90
        g = glyph(ch, cap)
        if not g.is_empty:
            g = affinity.translate(g, -(g.bounds[0] + g.bounds[2]) / 2, 0)
            g = affinity.rotate(g, rot, origin=(0, 0))
            parts.append(affinity.translate(g, r_base * math.cos(theta), r_base * math.sin(theta)))
        arc += w + track
    return unary_union(parts)


def rim():
    mid_r = RIM_BASE + RIM_CAP / 2
    dots = [Point(x * mid_r, 0).buffer(RIM_DOT, 32) for x in (-1, 1)]
    return unary_union([ring(RING_OUT), ring(RING_IN),
                        arc_text(RIM_TOP, RIM_CAP, RIM_BASE, RIM_TRACK),
                        arc_text(RIM_BOTTOM, RIM_CAP, RIM_BASE, RIM_TRACK, bottom=True), *dots])


# ── DRAWING ──────────────────────────────────────────────────────────
def stroke(coords, w=STROKE):
    return LineString(coords).buffer(w / 2, cap_style="flat", join_style="mitre")


def ring(r, w=STROKE):
    return Point(0, 0).buffer(r + w / 2, 256).difference(Point(0, 0).buffer(r - w / 2, 256))


def dimension(p0, p1, label, side, avoid=None):
    """Dimension line parallel to p0->p1, offset to `side` (+1 left of travel, -1 right),
    end ticks, and a centred label set in a gap in the line."""
    p0, p1 = np.array(p0, float), np.array(p1, float)
    d = (p1 - p0) / np.linalg.norm(p1 - p0)
    n = np.array([-d[1], d[0]]) * side
    a, b = p0 + n * DIM_OFF, p1 + n * DIM_OFF
    ang = math.degrees(math.atan2(d[1], d[0]))
    if ang > 90 or ang < -90:                                   # keep labels upright
        ang += 180
    mid = (a + b) / 2
    txt = text_line(label, DIM_CAP, track=0.5, cx=mid[0], y=mid[1], angle=ang)
    # gap around the label: after both get emboldened, leave MIN_LAND between text and line end
    gap = txt.buffer(max(1.2, MIN_LAND + 2 * EMBOLDEN + STROKE / 2)).convex_hull
    line = stroke([a, b]).difference(gap)
    ticks = [stroke([q - n * DIM_TICK / 2, q + n * DIM_TICK / 2]) for q in (a, b)]
    # thin extension lines from the part to the dimension line
    def ext_start(p):
        """first offset along n that leaves a MIN_LAND of plastic between this line and `avoid`"""
        t = 0.5
        while avoid is not None and Point(p + n * t).distance(avoid) < MIN_LAND + EXT_STROKE / 2:
            t += 0.1
        return t
    ext = [stroke([p + n * ext_start(p), p + n * (DIM_OFF + DIM_TICK / 2)], EXT_STROKE) for p in (p0, p1)]
    return unary_union([line, txt, *ticks, *ext])


def chaikin(pts, passes):
    """Corner-cutting smoothing of an open polyline; both end points stay fixed."""
    pts = np.asarray(pts, float)
    for _ in range(passes):
        q = [pts[0]]
        for a, b in zip(pts[:-1], pts[1:]):
            q += [0.75 * a + 0.25 * b, 0.25 * a + 0.75 * b]
        q.append(pts[-1])
        pts = np.array(q)
    return [tuple(p) for p in pts]


def tooth_drawing(labels):
    s = TOOTH_H
    tip_y = TOOTH_TOP - s
    def P(x, y):
        return (x * s, tip_y + y * s)
    # tip and root notch are the half-outline's end points, so smoothing keeps them sharp
    half = chaikin(_HALF, SMOOTH) if SMOOTH else _HALF
    right = [P(x, y) for x, y in half]
    left = [P(-x, y) for x, y in reversed(half[1:-1])]
    outline = Polygon(right + left)
    art = outline.buffer(STROKE / 2).difference(outline.buffer(-STROKE / 2))
    art = art.union(stroke([P(x, y) for x, y in _BOURLETTE], EXT_STROKE))
    tip, sh_r, sh_l = P(0, 0), P(0.405, 0.86), P(-0.405, 0.86)
    root_r, root_l = P(0.405, 1.0), P(-0.405, 1.0)
    dims = [dimension(tip, sh_l, labels["L1"], side=+1, avoid=art),     # +1/-1 = outward for these travel directions
            dimension(tip, sh_r, labels["L2"], side=-1, avoid=art),
            dimension(root_l, root_r, labels["W"], side=+1, avoid=art)]
    return unary_union([art, *dims])


def plate(labels):
    """The whole underside artwork in reading coordinates, centred on the bell axis."""
    spec = text_line(labels["WT"], SPEC_CAP, track=0.55, y=SPEC_Y)
    art = unary_union([rim(), tooth_drawing(labels), spec])
    return art.buffer(EMBOLDEN, join_style="round").buffer(0)


def cutter(center_xy, labels, mirror_x=True):
    """manifold3d cutter: the plate extruded from z=-1 up to DEPTH, mirrored so it reads
    correctly from below. Built as a CrossSection (even-odd fill) — extruding letters with
    holes through trimesh gave non-manifold meshes."""
    art = plate(labels)
    if mirror_x:
        art = affinity.scale(art, xfact=-1, yfact=1, origin=(0, 0))
    art = affinity.translate(art, *center_xy)
    def section(geom):
        rings = []
        for g in (geom.geoms if hasattr(geom, "geoms") else [geom]):
            for r in [g.exterior, *g.interiors]:
                rings.append(np.asarray(r.coords)[:-1])
        return m3d.CrossSection(rings, m3d.FillRule.EvenOdd)

    if not CHISEL:
        return m3d.Manifold.extrude(section(art), DEPTH + 1).translate([0, 0, -1]), art
    # chisel: a terrace stack — at height z the cut is the art inset by z (45 deg walls), until
    # the strokes close up or DEPTH is reached; plus a 1mm lead-in below the bed face
    slabs = [m3d.Manifold.extrude(section(art), 1.0).translate([0, 0, -1])]
    z = 0.0
    while z < DEPTH - 1e-9:
        inset = art.buffer(-(z + CHISEL_STEP / 2), join_style="round")
        if inset.is_empty:
            break
        slabs.append(m3d.Manifold.extrude(section(inset), CHISEL_STEP).translate([0, 0, z]))
        z += CHISEL_STEP
    return m3d.Manifold.batch_boolean(slabs, m3d.OpType.Add), art
