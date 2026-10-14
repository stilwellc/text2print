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
    """Revolved silhouettes for the fabric family."""
    kind = "bowl"

    def profile(self, v):
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
    Block("tray", "Tray", "Rounded square with a round dish dipped in", ("lattice",), [
        Param("width", "Width", 60, 200, 1, 117), Param("height", "Height", 12, 60, 0.5, 33),
        Param("dish", "Dish", 0, 184, 1, 94), Param("floor", "Floor", 2, 20, 0.5, 10.4),
        Param("corner", "Corner", 0, 50, 1, 20), Param("pillow", "Top edge", 0, 10, 0.5, 6)]),
    Block("platter", "Platter", "Low, wide tray for the table", ("lattice",), [
        Param("width", "Width", 100, 200, 1, 160), Param("height", "Height", 10, 40, 0.5, 24),
        Param("dish", "Dish", 0, 184, 1, 130), Param("floor", "Floor", 2, 14, 0.5, 5.6),
        Param("corner", "Corner", 0, 60, 1, 28), Param("pillow", "Top edge", 0, 10, 0.5, 6)]),
    Block("dish", "Round dish", "A round block with a bowl in it", ("lattice",), [
        Param("diameter", "Diameter", 60, 200, 1, 130), Param("height", "Height", 12, 60, 0.5, 28),
        Param("dish", "Dish", 0, 184, 1, 104), Param("floor", "Floor", 2, 20, 0.5, 6.4),
        Param("pillow", "Top edge", 0, 10, 0.5, 5)], round=True),
    Block("coaster", "Coaster", "Thin tile with a shallow seat for a glass", ("lattice",), [
        Param("width", "Width", 70, 140, 1, 100), Param("height", "Height", 5, 16, 0.5, 8),
        Param("dish", "Seat", 0, 120, 1, 76), Param("floor", "Floor", 2, 12, 0.5, 5.6),
        Param("corner", "Corner", 0, 40, 1, 16), Param("pillow", "Top edge", 0, 4, 0.5, 2)]),
    Vessel("cup", "Cup", "Straight-walled vessel with a floor", ("lattice", "fabric", "droop", "halftone"), [
        Param("diameter", "Diameter", 50, 160, 1, 90), Param("height", "Height", 30, 160, 1, 90),
        Param("wall", "Wall", 4, 16, 0.5, 8, family="lattice"),
        Param("floor", "Floor", 2, 10, 0.5, 4, family="lattice")], round=True),
    Profiled("bowl", "Bowl", "Flared bowl", ("fabric", "droop", "halftone"), [
        Param("diameter", "Diameter", 80, 200, 1, 180), Param("height", "Height", 30, 120, 1, 70),
        Param("base", "Base width", 55, 95, 1, 62, "%")], round=True),
    Profiled("vase", "Vase", "Bellied vase with a narrowing neck", ("fabric", "droop", "halftone"), [
        Param("diameter", "Belly", 70, 180, 1, 120), Param("height", "Height", 80, 240, 1, 180),
        Param("neck", "Neck", 55, 100, 1, 70, "%")], round=True),
]}
SHAPES["vase"].kind = "vase"
_goblet = Profiled("goblet", "Goblet", "A cup on a stem and foot", ("fabric", "droop", "halftone"), [
    Param("diameter", "Diameter", 80, 150, 1, 120), Param("height", "Height", 90, 200, 1, 140)], round=True)
_goblet.kind = "goblet"
_candle = Profiled("candle", "Candle holder", "A bell that narrows to a socket for a taper candle", ("droop",), [
    Param("diameter", "Base", 80, 160, 1, 120), Param("height", "Height", 80, 180, 1, 130),
    Param("socket", "Socket", 18, 26, 0.5, 22.5)], round=True)
_candle.kind = "candle"; _candle.solid = True
SHAPES["goblet"] = _goblet; SHAPES["candle"] = _candle
_shade = Vessel("shade", "Lamp shade", "Open cylinder — light through the weave", ("lattice",), [
    Param("diameter", "Diameter", 80, 200, 1, 140), Param("height", "Height", 60, 180, 1, 120),
    Param("wall", "Wall", 4, 14, 0.5, 6)], round=True)
_shade.open_top_bottom = True
SHAPES["shade"] = _shade
