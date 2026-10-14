"""The shapes you can pick. Each shape knows its size controls and which texture families it can carry:

  lattice — the woven rod family: the shape is a REGION per height (a vectorised signed-distance function in
            the XY plane, <= 0 inside); rods are clipped to it course by course.
  fabric  — the printed-fabric family: the shape is a revolved PROFILE r(z); the wall is a 2-loop shell whose
            print layers zigzag in mid-air.

Laws baked into every lattice shape: a flat, full-size bottom; no course ever reaches past the course below
it (a region may only shrink going up); nothing square — corners, dishes and edges are rounded."""
import math
from dataclasses import dataclass, field

import numpy as np


@dataclass
class Param:
    key: str
    label: str
    lo: float
    hi: float
    step: float
    default: float
    unit: str = "mm"
    family: str = ""          # "" = always shown; "lattice"/"fabric" = only for that texture family


@dataclass
class Shape:
    key: str
    name: str
    blurb: str
    families: tuple                      # ("lattice",), ("fabric",) or both
    params: list = field(default_factory=list)
    round: bool = False                  # circular in plan (polar weave fits)

    def defaults(self):
        return {p.key: p.default for p in self.params}

    def resolve(self, values):
        v = self.defaults()
        for p in self.params:
            if p.key in (values or {}):
                v[p.key] = float(min(max(float(values[p.key]), p.lo), p.hi))
        return v

    # lattice
    def lattice(self, v, rod_h):
        raise NotImplementedError

    # fabric
    def profile(self, v):
        raise NotImplementedError


def _rounded_square(x, y, half, r):
    r = min(r, half); b = half - r
    qx, qy = np.abs(x) - b, np.abs(y) - b
    return np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - r


def _odd_courses(height, rod_h, at_least=3):
    n = max(at_least, int(round(height / rod_h)))
    return n + (1 - n % 2)              # odd count: the top course runs along X, like the floor's first


class Region:
    """Lattice view of a shape at concrete sizes: n courses, an XY sdf per course height, a plan extent."""

    def __init__(self, n_courses, rod_h, sdf_at, extent, round_=False, floor_courses=0):
        self.n, self.rod_h, self._sdf_at, self.extent = n_courses, rod_h, sdf_at, extent
        self.round, self.floor_courses = round_, floor_courses
        self.height = n_courses * rod_h

    def z(self, i):
        return i * self.rod_h + self.rod_h / 2

    def sdf(self, z):
        return self._sdf_at(z)


# ── non-round plans for the wall families ─────────────────────────────────────
# Every wall family (fabric, droop, halftone, vase mode, shell, mix) builds a ROUND vessel from a radius per height.
# A rounded square, rectangle or hexagon reuses all of it: build the round piece with the same circumference as the
# outline (R_eq = perimeter / 2 pi), then map it on — angle -> distance along the outline, (r - R_eq) -> offset
# along the outline's outward normal. Stitch spacing and wall thickness survive; floors scale in from the wall.

class Outline:
    def __init__(self, sdf, extent, n=4096):
        import skimage.measure as skm
        g = np.linspace(-extent - 3, extent + 3, 700); X, Y = np.meshgrid(g, g, indexing="ij")
        c = max(skm.find_contours(sdf(X, Y), 0.0), key=len)
        P = np.column_stack([np.interp(c[:, 0], np.arange(len(g)), g), np.interp(c[:, 1], np.arange(len(g)), g)])
        if np.cross(P[1] - P[0], P[2] - P[0]) < 0 or _signed_area(P) < 0:
            P = P[::-1]
        if _signed_area(P) < 0:
            P = P[::-1]
        k0 = int(np.argmin(np.abs(np.arctan2(P[:, 1], P[:, 0])) + (P[:, 0] < 0) * 10))   # start on the +x axis
        P = np.roll(P, -k0, axis=0)
        seg = np.hypot(*np.diff(np.vstack([P, P[:1]]), axis=0).T); s_ = np.concatenate([[0], np.cumsum(seg)])
        self.L = float(s_[-1]); t = np.linspace(0, self.L, n, endpoint=False)
        Pc = np.vstack([P, P[:1]])
        C = np.column_stack([np.interp(t, s_, Pc[:, 0]), np.interp(t, s_, Pc[:, 1])])
        T = np.roll(C, -1, axis=0) - np.roll(C, 1, axis=0)
        w = max(1, int(1.5 / (self.L / n)))                              # smooth normals over ~3 mm of outline
        k = np.ones(2 * w + 1) / (2 * w + 1)
        T = np.column_stack([np.convolve(np.r_[T[-w:, 0], T[:, 0], T[:w, 0]], k, "valid"),
                             np.convolve(np.r_[T[-w:, 1], T[:, 1], T[:w, 1]], k, "valid")])
        T /= np.linalg.norm(T, axis=1)[:, None]
        self.C, self.N, self.n = C, np.column_stack([T[:, 1], -T[:, 0]]), n
        self.R = self.L / (2 * math.pi)

    def warp(self, mesh, band=4.0):
        """Map a round piece built at radius R onto this outline (in place)."""
        V = mesh.vertices; r = np.hypot(V[:, 0], V[:, 1])
        th = np.mod(np.arctan2(V[:, 1], V[:, 0]), 2 * math.pi)
        f = th / (2 * math.pi) * self.n; i0 = np.floor(f).astype(int) % self.n; i1 = (i0 + 1) % self.n; a = (f - np.floor(f))[:, None]
        C = self.C[i0] * (1 - a) + self.C[i1] * a; N = self.N[i0] * (1 - a) + self.N[i1] * a
        N /= np.linalg.norm(N, axis=1)[:, None]
        off = r - self.R
        wall = C + off[:, None] * N
        inner = (np.clip(r / max(self.R - band, 1e-6), 0, 1))[:, None] * (C - band * N)
        XY = np.where((off >= -band)[:, None], wall, inner)
        mesh.vertices = np.column_stack([XY, V[:, 2]])
        return mesh


def _signed_area(P):
    return 0.5 * float(np.sum(P[:, 0] * np.roll(P[:, 1], -1) - np.roll(P[:, 0], -1) * P[:, 1]))


class Block(Shape):
    """Rounded-square or round block with a spherical dish dipped in and a pillowed top edge (tray family)."""

    def lattice(self, v, rod_h):
        size = v.get("width", v.get("diameter"))
        nf = max(1, int(round(v["floor"] / rod_h))); nf += 1 - nf % 2          # floor top is an X course
        n = max(nf + 2, _odd_courses(v["height"], rod_h))
        H = n * rod_h; depth = (n - nf) * rod_h
        dish = min(v.get("dish", 0.0), size - 12.0)
        Rs = ((dish / 2) ** 2 + depth ** 2) / (2 * depth) if dish > 0 else 0.0
        pillow = v.get("pillow", 0.0); half = size / 2; corner = v.get("corner", 0.0)

        def sdf_at(z):
            d = H - z
            ins = 0.0 if (pillow <= 0 or d >= pillow) else pillow - math.sqrt(max(pillow ** 2 - (pillow - d) ** 2, 0))
            h = z - (H - depth)
            r = 0.0 if (dish <= 0 or h <= 0) else math.sqrt(max(Rs ** 2 - (Rs - h) ** 2, 0.0))
            def f(x, y):
                outer = np.hypot(x, y) - (half - ins) if self.round else _rounded_square(x, y, half - ins, corner)
                return outer if r <= 0 else np.maximum(outer, r - np.hypot(x, y))
            return f
        return Region(n, rod_h, sdf_at, half, self.round, nf)

    def outline(self, v):
        if self.round:
            return None
        half = v["width"] / 2; corner = max(v.get("corner", 0.0), 6.0)
        return Outline(lambda x, y: _rounded_square(x, y, half, corner), half)

    def profile(self, v):                                 # wall families: a straight-sided low vessel
        o = self.outline(v); R = o.R if o else v["diameter"] / 2
        return (lambda z: R), v["height"], R


class Vessel(Shape):
    """Cylinder: a lattice wall ring on a lattice floor (cup), or an open ring (shade); fabric: a straight wall."""
    open_top_bottom = False

    def lattice(self, v, rod_h):
        R = v["diameter"] / 2; wall = min(v["wall"], R - 4)
        nf = 0 if self.open_top_bottom else (lambda k: k + 1 - k % 2)(max(1, int(round(v.get("floor", 4) / rod_h))))
        n = max(nf + 2, _odd_courses(v["height"], rod_h)); fz = nf * rod_h

        def sdf_at(z):
            def f(x, y):
                d = np.hypot(x, y)
                return d - R if z < fz else np.maximum(d - R, (R - wall) - d)
            return f
        return Region(n, rod_h, sdf_at, R, True, nf)

    def profile(self, v):
        R = v["diameter"] / 2
        return (lambda z: R), v["height"], R


class Profiled(Shape):
    """Revolved silhouettes: a wall for fabric/droop/halftone/..., or a woven ring that follows the silhouette."""
    kind = "bowl"
    LEAN = 0.8                         # woven: a course may step at most 0.8 mm per mm (~39 deg) in or out of the
                                       # one below — rod ends overhang on BOTH faces, so inward counts too

    def lattice(self, v, rod_h):
        prof, h, _ = self.profile(v)
        fitted = self.kind in ("cachepot", "sleeve")         # inner size is the fit: the weave grows outward
        wall = v.get("wall", 6.0)
        nf = (lambda k: k + 1 - k % 2)(max(1, int(round(v.get("floor", 4) / rod_h))))
        if self.kind == "sleeve":
            nf = 0                                           # open tube: the glass is the floor
        n = max(nf + 2, _odd_courses(h, rod_h)); fz = nf * rod_h
        zc = (np.arange(n) + 0.5) * rod_h
        r_in = np.array([max(prof(min(z, h)) - (SHELL if fitted else wall), 0.0) for z in zc])
        for k in range(1, n):                                # every course rests on the one below
            r_in[k] = min(max(r_in[k], r_in[k - 1] - self.LEAN * rod_h), r_in[k - 1] + self.LEAN * rod_h)
        r_out = r_in + wall

        def sdf_at(z):
            k = min(n - 1, max(0, int(z / rod_h)))
            ro, ri = r_out[k], r_in[k]
            def f(x, y):
                d = np.hypot(x, y)
                if z < fz or ri < 5.0:                       # floor, or a stem too thin to hollow: solid
                    return d - ro
                return np.maximum(d - ro, ri - d)
            return f
        return Region(n, rod_h, sdf_at, float(r_out.max()), True, nf)

    def profile(self, v):
        if self.kind == "custom":
            return custom_profile(v)
        if self.kind in KIND_PROFILES:
            return KIND_PROFILES[self.kind](v)
        top, h = v["diameter"] / 2, v["height"]
        if self.kind == "goblet":
            stem = top * 0.26; foot = top * 0.62
            def f(z):
                t = min(max(z / h, 0), 1)
                if t < 0.22:
                    return stem + (foot - stem) * (0.5 + 0.5 * math.cos(math.pi * t / 0.22))
                return stem + (top - stem) * ((t - 0.22) / 0.78) ** 1.15      # flare <= ~48 deg
            return f, h, top
        if self.kind == "candle":
            base = top; neck = max(top * 0.36, v.get("socket", 22.5) / 2 + 4)
            def f(z):
                t = min(max(z / h, 0), 1)
                if t < 0.84:
                    return neck + (base - neck) * (1 - t / 0.84) ** 1.6 if t > 0.04 else base
                return neck + (t - 0.84) / 0.16 * 3.0                         # a small lip at the top
            return f, h, top
        if self.kind == "bowl":
            base = top * v["base"] / 100.0
            f = lambda z: base + (top - base) * math.sin(0.5 * math.pi * min(max(z / h, 0), 1)) ** 0.85
            return f, h, top
        belly = top                                  # vase: belly = diameter, neck = % of it
        neck = belly * v["neck"] / 100.0; foot = belly * 0.62
        def f(z):
            t = min(max(z / h, 0), 1)
            if t < 0.42:
                return foot + (belly - foot) * math.sin(0.5 * math.pi * t / 0.42)
            return neck + (belly - neck) * (0.5 + 0.5 * math.cos(math.pi * (t - 0.42) / 0.58))
        return f, h, belly


SHAPES = {s.key: s for s in [
    Block("tray", "Tray", "Rounded square with a round dish dipped in", ("lattice", "fabric", "droop", "halftone", "mix", "spiral", "shell"), [
        Param("width", "Width", 60, 200, 1, 117), Param("height", "Height", 12, 60, 0.5, 33),
        Param("dish", "Dish", 0, 184, 1, 94, family="lattice"), Param("floor", "Floor", 2, 20, 0.5, 10.4, family="lattice"),
        Param("corner", "Corner", 0, 50, 1, 20), Param("pillow", "Top edge", 0, 10, 0.5, 6, family="lattice")]),
    Block("platter", "Platter", "Low, wide tray for the table", ("lattice", "fabric", "droop", "halftone", "mix", "spiral", "shell"), [
        Param("width", "Width", 100, 200, 1, 160), Param("height", "Height", 10, 40, 0.5, 24),
        Param("dish", "Dish", 0, 184, 1, 130, family="lattice"), Param("floor", "Floor", 2, 14, 0.5, 5.6, family="lattice"),
        Param("corner", "Corner", 0, 60, 1, 28), Param("pillow", "Top edge", 0, 10, 0.5, 6, family="lattice")]),
    Block("dish", "Round dish", "A round block with a bowl in it", ("lattice", "fabric", "droop", "halftone", "mix", "spiral", "shell"), [
        Param("diameter", "Diameter", 60, 200, 1, 130), Param("height", "Height", 12, 60, 0.5, 28),
        Param("dish", "Dish", 0, 184, 1, 104, family="lattice"), Param("floor", "Floor", 2, 20, 0.5, 6.4, family="lattice"),
        Param("pillow", "Top edge", 0, 10, 0.5, 5, family="lattice")], round=True),
    Block("coaster", "Coaster", "Thin tile with a shallow seat for a glass", ("lattice", "fabric", "halftone", "shell"), [
        Param("width", "Width", 70, 140, 1, 100), Param("height", "Height", 5, 16, 0.5, 8),
        Param("dish", "Seat", 0, 120, 1, 76, family="lattice"), Param("floor", "Floor", 2, 12, 0.5, 5.6, family="lattice"),
        Param("corner", "Corner", 0, 40, 1, 16), Param("pillow", "Top edge", 0, 4, 0.5, 2, family="lattice")]),
    Vessel("cup", "Cup", "Straight-walled vessel with a floor", ("lattice", "fabric", "droop", "halftone", "mix", "spiral", "shell"), [
        Param("diameter", "Diameter", 50, 160, 1, 90), Param("height", "Height", 30, 160, 1, 90),
        Param("wall", "Wall", 4, 16, 0.5, 8, family="lattice"),
        Param("floor", "Floor", 2, 10, 0.5, 4, family="lattice")], round=True),
    Profiled("bowl", "Bowl", "Flared bowl", ("lattice", "fabric", "droop", "halftone", "mix", "spiral", "shell"), [
        Param("diameter", "Diameter", 80, 200, 1, 180), Param("height", "Height", 30, 120, 1, 70),
        Param("base", "Base width", 55, 95, 1, 62, "%"),
        Param("wall", "Wall", 4, 16, 0.5, 6, family="lattice"), Param("floor", "Floor", 2, 10, 0.5, 4, family="lattice")], round=True),
    Profiled("vase", "Vase", "Bellied vase with a narrowing neck", ("lattice", "fabric", "droop", "halftone", "mix", "spiral", "shell"), [
        Param("diameter", "Belly", 70, 180, 1, 120), Param("height", "Height", 80, 240, 1, 180),
        Param("neck", "Neck", 55, 100, 1, 70, "%"),
        Param("wall", "Wall", 4, 16, 0.5, 6, family="lattice"), Param("floor", "Floor", 2, 10, 0.5, 4, family="lattice")], round=True),
]}
SHAPES["vase"].kind = "vase"
_goblet = Profiled("goblet", "Goblet", "A cup on a stem and foot", ("lattice", "fabric", "droop", "halftone", "mix", "spiral", "shell"), [
    Param("diameter", "Diameter", 80, 150, 1, 120), Param("height", "Height", 90, 200, 1, 140),
        Param("wall", "Wall", 4, 16, 0.5, 6, family="lattice"), Param("floor", "Floor", 2, 10, 0.5, 4, family="lattice")], round=True)
_goblet.kind = "goblet"
_candle = Profiled("candle", "Candle holder", "A bell that narrows to a socket for a taper candle", ("droop",), [
    Param("diameter", "Base", 80, 160, 1, 120), Param("height", "Height", 80, 180, 1, 130),
    Param("socket", "Socket", 18, 26, 0.5, 23)], round=True)
_candle.kind = "candle"; _candle.solid = True
SHAPES["goblet"] = _goblet; SHAPES["candle"] = _candle
_custom = Profiled("custom", "Your shape", "Draw the silhouette — five points from foot to rim", ("lattice", "fabric", "droop", "halftone", "mix", "spiral", "shell"), [
    Param("diameter", "Widest", 60, 200, 1, 120), Param("height", "Height", 40, 220, 1, 150),
    Param("c0", "Foot", 20, 100, 1, 62, "%"), Param("c1", "Lower", 20, 100, 1, 92, "%"),
    Param("c2", "Middle", 20, 100, 1, 100, "%"), Param("c3", "Upper", 20, 100, 1, 74, "%"),
    Param("c4", "Rim", 20, 100, 1, 80, "%"),
        Param("wall", "Wall", 4, 16, 0.5, 6, family="lattice"), Param("floor", "Floor", 2, 10, 0.5, 4, family="lattice")], round=True)
_custom.kind = "custom"
SHAPES["custom"] = _custom


def custom_profile(v):
    """Monotone cubic (Fritsch-Carlson) through five radii at 0/25/50/75/100 % height, then clamped so the wall
    never leans outward faster than ~42 deg (printable without supports) and never thinner than 12 mm radius."""
    R = v["diameter"] / 2; h = v["height"]
    xs = np.array([0, 0.25, 0.5, 0.75, 1.0]) * h
    ys = np.array([max(12.0, R * v[f"c{i}"] / 100.0) for i in range(5)])
    d = np.diff(ys) / np.diff(xs)
    m = np.zeros(5); m[0], m[-1] = d[0], d[-1]
    for i in range(1, 4):
        m[i] = 0.0 if d[i - 1] * d[i] <= 0 else 2 / (1 / d[i - 1] + 1 / d[i])
    zf = np.linspace(0, h, int(h / 0.25) + 1); rf = np.empty_like(zf)
    for k, z in enumerate(zf):
        i = min(3, int(z / (h / 4))); t = (z - xs[i]) / (xs[i + 1] - xs[i]); hh = xs[i + 1] - xs[i]
        rf[k] = ((2 * t ** 3 - 3 * t ** 2 + 1) * ys[i] + (t ** 3 - 2 * t ** 2 + t) * hh * m[i]
                 + (-2 * t ** 3 + 3 * t ** 2) * ys[i + 1] + (t ** 3 - t ** 2) * hh * m[i + 1])
    for k in range(1, len(rf)):                                   # overhang law: outward lean <= 0.9 mm per mm
        rf[k] = min(rf[k], rf[k - 1] + 0.9 * (zf[k] - zf[k - 1]))
    rf = np.maximum(rf, 12.0)
    rmax = float(rf.max())
    return (lambda z: float(np.interp(z, zf, rf))), h, rmax
_shade = Vessel("shade", "Lamp shade", "Open cylinder — light through the weave", ("lattice",), [
    Param("diameter", "Diameter", 80, 200, 1, 140), Param("height", "Height", 60, 180, 1, 120),
    Param("wall", "Wall", 4, 14, 0.5, 6)], round=True)
_shade.open_top_bottom = True
SHAPES["shade"] = _shade



# ── fitted shapes (see fittings.py) ───────────────────────────────────────────
def _clamped(fn, h, rmin=12.0, lean=0.9):
    """Sample fn on 0.25 mm steps and clamp so the wall never leans out faster than `lean` mm per mm."""
    zf = np.linspace(0, h, int(h / 0.25) + 1); rf = np.array([max(rmin, fn(z)) for z in zf])
    for k in range(1, len(rf)):
        rf[k] = min(rf[k], rf[k - 1] + lean * (zf[k] - zf[k - 1]))
    return (lambda z: float(np.interp(z, zf, rf))), h, float(rf.max())


SHELL = 1.0     # the fabric shell at 0.4; fitted sizes are inner sizes, so the wall goes outside them


def _cachepot(v):
    rid = (v["pot"] * 25.4 + 5.0) / 2; h = v["pot"] * 25.4 * 0.92 + v["extra"]
    R0 = rid + SHELL
    return _clamped(lambda z: R0 + 0.06 * z, h)                     # a slight flare (~3.5 deg)


def _sleeve(v):
    R = v["liner"] / 2 + 1.0 + SHELL
    return (lambda z: R), v["height"], R


def _lantern(v):
    R = v["diameter"] / 2; h = v["height"]
    return _clamped(lambda z: R * (0.86 + 0.14 * math.sin(math.pi * min(z / h, 1.0))), h)


def _pendant(v):
    R = v["diameter"] / 2; h = v["height"]; r0 = 38.0
    return _clamped(lambda z: r0 + (R - r0) * math.sin(0.5 * math.pi * min(z / h, 1.0)) ** 0.9, h, lean=0.85)


def _puck(v):
    R = v["diameter"] / 2; h = v["height"]; foot = 29.85 + 3.0
    def f(z):
        t = min(z / h, 1.0)
        if z < 20:
            return foot
        return foot + (R - foot) * math.sin(math.pi * min((z - 20) / (h * 0.75), 1.0) * 0.5) ** 0.8 - (R - foot) * 0.35 * max(0, t - 0.75) / 0.25
    return _clamped(f, h)


def _amphora(v):
    belly = v["diameter"] / 2; h = v["height"]; neck = belly * v["neck"] / 100.0; foot = belly * 0.5
    def f(z):
        t = min(max(z / h, 0), 1)
        if t < 0.38:
            return foot + (belly - foot) * math.sin(0.5 * math.pi * t / 0.38) ** 0.8
        if t < 0.86:
            return neck + (belly - neck) * (0.5 + 0.5 * math.cos(math.pi * (t - 0.38) / 0.48))
        return neck + (belly - neck) * 0.25 * ((t - 0.86) / 0.14) ** 1.5         # flared lip
    return _clamped(f, h)


_WOVEN_PARAMS = [Param("wall", "Wall", 4, 16, 0.5, 6, family="lattice"), Param("floor", "Floor", 2, 10, 0.5, 4, family="lattice")]
KIND_PROFILES = {"cachepot": _cachepot, "sleeve": _sleeve, "lantern": _lantern, "pendant": _pendant,
                 "puck": _puck, "amphora": _amphora}
_WALL = ("fabric", "droop", "halftone", "mix", "spiral", "shell")
for key, name, blurb, params in [
    ("cachepot", "Cachepot", "Covers a 3–8 in nursery pot; no water, so any texture works", [
        Param("pot", "Nursery pot", 3, 7, 1, 6, "in"), Param("extra", "Extra height", 0, 40, 1, 8)]),
    ("sleeve", "Glass sleeve", "Slips over a jar, bottle or test tube — the glass holds the water", [
        Param("liner", "Glass diameter", 15, 120, 0.5, 70), Param("height", "Height", 30, 240, 1, 110)]),
    ("lantern", "Tealight lantern", "A tealight pocket in a weighted plinth", [
        Param("diameter", "Diameter", 60, 140, 1, 84), Param("height", "Height", 50, 160, 1, 96)]),
    ("pendant", "Pendant shade", "Hangs from an E27 cord set — the collar has a 40 mm hole", [
        Param("diameter", "Mouth", 120, 200, 1, 180), Param("height", "Height", 90, 220, 1, 150)]),
    ("puck", "LED puck lamp", "Sits over Bambu's LED Lamp Kit puck — no mains wiring", [
        Param("diameter", "Widest", 90, 190, 1, 130), Param("height", "Height", 90, 220, 1, 160)]),
    ("amphora", "Amphora", "Narrow foot, full belly, slim neck and a flared lip", [
        Param("diameter", "Belly", 80, 180, 1, 120), Param("height", "Height", 110, 240, 1, 200),
        Param("neck", "Neck", 30, 70, 1, 42, "%")]),
]:
    woven = key in ("cachepot", "sleeve", "amphora")
    _s = Profiled(key, name, blurb, (("lattice",) if woven else ()) + _WALL, params + (_WOVEN_PARAMS if woven else []), round=True)
    _s.kind = key
    SHAPES[key] = _s



# ── non-round footprints (woven) and flat tiles ───────────────────────────────
def sd_round_rect(x, y, hx, hy, r):
    r = min(r, hx, hy); qx, qy = np.abs(x) - (hx - r), np.abs(y) - (hy - r)
    return np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - r


def sd_hex(x, y, flat, r=0.0):
    """Hexagon with flat-to-flat `flat` (flat sides top and bottom), corners rounded by r (iq's sdHexagon)."""
    k = (-0.8660254, 0.5, 0.57735027)
    R = flat / 2 - r
    px, py = np.abs(x), np.abs(y)
    px, py = py, px                                         # rotate 90 deg: flat sides on +/-y
    d = np.minimum(k[0] * px + k[1] * py, 0.0)
    px = px - 2 * d * k[0]; py = py - 2 * d * k[1]
    cx = np.clip(px, -k[2] * R, k[2] * R)
    return np.hypot(px - cx, py - R) * np.sign(py - R) - r


class Box(Shape):
    """Rounded-rectangle woven box: a basket (deep, optional handle slots with 45 deg arched tops) or a catch-all."""

    def lattice(self, v, rod_h):
        W, D, H, wall, corner = v["width"], v["depth"], v["height"], v["wall"], v.get("corner", 12)
        nf = max(1, int(round(v["floor"] / rod_h))); nf += 1 - nf % 2
        n = max(nf + 2, _odd_courses(H, rod_h)); top = n * rod_h; fz = nf * rod_h
        handles = v.get("handles", 0) > 0
        hw = min(32.0, D / 2 - wall - 6)                           # hand slot: 14 mm straight, then a 45 deg pointed arch
        hz1 = top - 6.0; hz0 = hz1 - (14.0 + hw)
        if hz0 < fz + 10:
            handles = False

        def sdf_at(z):
            def f(x, y):
                outer = sd_round_rect(x, y, W / 2, D / 2, corner)
                if z < fz:
                    return outer
                pocket = sd_round_rect(x, y, W / 2 - wall, D / 2 - wall, max(corner - wall, 2.0))
                d = np.maximum(outer, -pocket)
                if handles and hz0 <= z <= hz1:
                    half = min(hw, hz1 - z)                     # straight below, 45 deg arch closing on top
                    if half > 2.0:
                        slot = np.maximum(np.abs(y) - half, (W / 2 - wall - 1.0) - np.abs(x))
                        d = np.maximum(d, -slot)
                return d
            return f
        return Region(n, rod_h, sdf_at, max(W, D) / 2, False, nf)

    def outline(self, v):
        W, D = v["width"], v["depth"]; corner = max(v.get("corner", 12.0), 6.0)
        return Outline(lambda x, y: sd_round_rect(x, y, W / 2, D / 2, corner), max(W, D) / 2)

    def profile(self, v):
        R = self.outline(v).R
        return (lambda z: R), v["height"], R


class HexTile(Shape):
    """Hexagonal tile: woven (a hex coaster / wall tile) or a flat lithophane panel."""

    def lattice(self, v, rod_h):
        F, H = v["width"], v["height"]
        n = _odd_courses(H, rod_h)
        return Region(n, rod_h, lambda z: (lambda x, y: sd_hex(x, y, F, 4.0)), F / 2 * 1.16, False, n)

    def footprint(self, v):
        return lambda x, y: sd_hex(x, y, v["width"], 3.0)

    def outline(self, v):
        return Outline(lambda x, y: sd_hex(x, y, v["width"], 6.0), v["width"] / 2 * 1.16)

    def profile(self, v):
        R = self.outline(v).R
        return (lambda z: R), v["height"], R


class Tile(Shape):
    """Flat rectangular panel (lithophane photo tile)."""

    def footprint(self, v):
        return lambda x, y: sd_round_rect(x, y, v["width"] / 2, v["depth"] / 2, 4.0)


SHAPES["basket"] = Box("basket", "Basket", "A rounded-rectangle basket, with handle slots if you like", ("lattice", "fabric", "droop", "halftone", "mix", "spiral", "shell"), [
    Param("width", "Width", 100, 200, 1, 180), Param("depth", "Depth", 70, 160, 1, 120), Param("height", "Height", 40, 140, 1, 90),
    Param("wall", "Wall", 6, 16, 0.5, 9, family="lattice"), Param("floor", "Floor", 2, 10, 0.5, 4, family="lattice"), Param("corner", "Corner", 4, 40, 1, 18),
    Param("handles", "Handle slots", 0, 1, 1, 1, "")])
SHAPES["catchall"] = Box("catchall", "Catch-all", "A low rounded-rectangle valet tray", ("lattice", "fabric", "droop", "halftone", "mix", "spiral", "shell"), [
    Param("width", "Width", 100, 200, 1, 170), Param("depth", "Depth", 60, 150, 1, 110), Param("height", "Height", 14, 50, 0.5, 28),
    Param("wall", "Wall", 6, 16, 0.5, 9, family="lattice"), Param("floor", "Floor", 2, 10, 0.5, 4, family="lattice"), Param("corner", "Corner", 4, 40, 1, 20)])
SHAPES["hextile"] = HexTile("hextile", "Hex tile", "A hexagonal tile — textured, woven, or a lithophane for the wall", ("lattice", "flat", "fabric", "halftone", "shell"), [
    Param("width", "Flat to flat", 60, 200, 1, 120), Param("height", "Thickness", 4, 20, 0.5, 8, family="!flat")])
SHAPES["tile"] = Tile("tile", "Photo tile", "A flat lithophane panel — one colour or full-colour CMYK", ("flat",), [
    Param("width", "Width", 60, 200, 1, 150), Param("depth", "Height", 60, 200, 1, 100)])
