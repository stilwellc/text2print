"""The woven rod lattice ("printed basketry"), print-verified Oct 2026 on a Bambu P2S (0.4 nozzle, PLA, AMS).

An object is a stack of COURSES. A course is a set of parallel rounded beads, `rod_layers` print layers tall;
the next course runs another way, so each rod bridges short gaps across the rods beneath it. No supports, no
infill, no walls — the rods are the object. Patterns decide which way each course runs, which rods exist, their
paths and their colour slot; the shape decides where rods may be (a Region from shapes.py).

Colour costs: a pattern that keeps one colour per course swaps once per course; one that mixes colours inside a
course (tartan, over-under) swaps about once per print LAYER."""
import math

import numpy as np
import trimesh

# ── beads ─────────────────────────────────────────────────────────────────────
SECTION = 8             # octagon section, vertices at the sides and top: exactly the print-verified tray bead
CAP = 4                 # rings per rounded end cap
PHASE = 0.0


def _section(rw, rh):
    a = np.linspace(0, 2 * np.pi, SECTION, endpoint=False) + PHASE
    return np.stack([np.cos(a) * rw / 2, np.sin(a) * rh / 2], axis=1)          # (S, 2): (lateral, vertical)


def _template(rw, rh):
    """Straight bead along +X of unit-free length: left-cap rings, right-cap rings, two cap poles.
    Returns (offsets (V,3), sign (V,) -1 left / +1 right, faces (F,3))."""
    sec = _section(rw, rh); S = SECTION
    rings, signs = [], []
    caps = [(k / (CAP + 1)) for k in range(CAP, 0, -1)]                         # outermost first
    for a in caps:                                                              # left cap, outer -> inner
        s = math.sqrt(1 - a * a)
        rings.append(np.column_stack([np.full(S, -a * rw / 2), sec[:, 0] * s, sec[:, 1] * s])); signs.append(-1)
    rings.append(np.column_stack([np.zeros(S), sec[:, 0], sec[:, 1]])); signs.append(-1)
    rings.append(np.column_stack([np.zeros(S), sec[:, 0], sec[:, 1]])); signs.append(+1)
    for a in reversed(caps):                                                    # right cap, inner -> outer
        s = math.sqrt(1 - a * a)
        rings.append(np.column_stack([np.full(S, a * rw / 2), sec[:, 0] * s, sec[:, 1] * s])); signs.append(+1)
    V = np.vstack(rings); sign = np.repeat(signs, S).astype(float)
    m = len(rings); F = []
    for i in range(m - 1):
        for j in range(S):
            a, b = i * S + j, i * S + (j + 1) % S
            c, d = (i + 1) * S + j, (i + 1) * S + (j + 1) % S
            F += [[a, b, d], [a, d, c]]
    pl, pr = len(V), len(V) + 1
    V = np.vstack([V, [[-rw / 2, 0, 0], [rw / 2, 0, 0]]]); sign = np.append(sign, [-1, 1])
    for j in range(S):
        F.append([pl, (j + 1) % S, j]); F.append([pr, (m - 1) * S + j, (m - 1) * S + (j + 1) % S])
    F = np.asarray(F)
    # orient outward: check with a test bead
    test = trimesh.Trimesh(V + np.outer(sign, [5, 0, 0]), F, process=False)
    if test.volume < 0:
        F = F[:, ::-1]
    return V, sign, F


_TEMPLATES = {}


def straight_beads(A, B, rw, rh):
    """Many straight beads in one mesh. A, B: (n,3) end points (bead centre line). Fully vectorised."""
    A = np.asarray(A, float); B = np.asarray(B, float)
    if len(A) == 0:
        return None
    key = (round(rw, 4), round(rh, 4))
    if key not in _TEMPLATES:
        _TEMPLATES[key] = _template(rw, rh)
    V, sign, F = _TEMPLATES[key]
    D = B - A; L = np.linalg.norm(D[:, :2], axis=1)
    keep = L > 1e-6; A, B, D, L = A[keep], B[keep], D[keep], L[keep]
    ux = D[:, :2] / L[:, None]                                                   # rods lie in a plane z = const
    mid = (A + B) / 2
    # local (x along rod, y lateral, z up) -> world
    lx = V[None, :, 0] + sign[None, :] * (L[:, None] / 2)                       # (n, V)
    wx = mid[:, None, 0] + lx * ux[:, None, 0] - V[None, :, 1] * ux[:, None, 1]
    wy = mid[:, None, 1] + lx * ux[:, None, 1] + V[None, :, 1] * ux[:, None, 0]
    wz = mid[:, None, 2] + V[None, :, 2]
    verts = np.stack([wx, wy, wz], axis=2).reshape(-1, 3)
    nv = len(V)
    faces = (F[None, :, :] + (np.arange(len(A)) * nv)[:, None, None]).reshape(-1, 3)
    return trimesh.Trimesh(verts, faces, process=False)


def path_bead(points, rw, rh):
    """Bead along a 3D polyline (curved rods: ripples, rings, loops, over-under). Watertight, outward normals."""
    P = np.asarray(points, float)
    if len(P) < 2:
        return None
    sec = _section(rw, rh); S = SECTION
    T = np.gradient(P, axis=0); T /= np.linalg.norm(T, axis=1)[:, None] + 1e-12
    pts, scl = [], []
    caps = [(k / (CAP + 1)) for k in range(CAP, 0, -1)]
    for a in caps:
        pts.append(P[0] - T[0] * (rw / 2) * a); scl.append(math.sqrt(1 - a * a))
    pts += list(P); scl += [1.0] * len(P)
    for a in reversed(caps):
        pts.append(P[-1] + T[-1] * (rw / 2) * a); scl.append(math.sqrt(1 - a * a))
    pts = np.asarray(pts); scl = np.asarray(scl)
    T = np.gradient(pts, axis=0); T /= np.linalg.norm(T, axis=1)[:, None] + 1e-12
    up = np.array([0, 0, 1.0])
    N = np.cross(T, up); nn = np.linalg.norm(N, axis=1)
    N = np.where(nn[:, None] > 1e-9, N / np.maximum(nn, 1e-12)[:, None], np.array([1.0, 0, 0]))
    Bn = np.cross(N, T)
    V = (pts[:, None, :] + N[:, None, :] * (sec[None, :, 0] * scl[:, None])[..., None]
         + Bn[:, None, :] * (sec[None, :, 1] * scl[:, None])[..., None]).reshape(-1, 3)
    m = len(pts); F = []
    for i in range(m - 1):
        for j in range(S):
            a, b = i * S + j, i * S + (j + 1) % S
            c, d = (i + 1) * S + j, (i + 1) * S + (j + 1) % S
            F += [[a, b, d], [a, d, c]]
    c0 = len(V); V = np.vstack([V, P[0] - T[0] * rw / 2, P[-1] + T[-1] * rw / 2])
    for j in range(S):
        F.append([c0, (j + 1) % S, j]); F.append([c0 + 1, (m - 1) * S + j, (m - 1) * S + (j + 1) % S])
    mesh = trimesh.Trimesh(V, np.asarray(F), process=False)
    if mesh.volume < 0:
        mesh.invert()
    return mesh


# ── clipping lines and curves to a region ─────────────────────────────────────
def runs(point, sdf, t_lo, t_hi, step, min_len):
    """Runs of the parametric curve point(t) -> (x, y) arrays that lie inside sdf (<= 0), ends refined by
    bisection. Returns [(t0, t1)]."""
    ts = np.arange(t_lo, t_hi + step, step)
    x, y = point(ts)
    inside = sdf(x, y) <= 0
    if not inside.any():
        return []
    edges = np.diff(inside.astype(np.int8))
    starts = list(np.where(edges == 1)[0] + 1); ends = list(np.where(edges == -1)[0])
    if inside[0]:
        starts = [0] + starts
    if inside[-1]:
        ends = ends + [len(ts) - 1]
    lo_in = np.array([ts[s] for s in starts]); lo_out = np.array([ts[s - 1] if s > 0 else ts[s] for s in starts])
    hi_in = np.array([ts[e] for e in ends]); hi_out = np.array([ts[e + 1] if e < len(ts) - 1 else ts[e] for e in ends])
    for _ in range(14):                                       # vectorised bisection of every boundary crossing
        m = (lo_in + lo_out) / 2; ins = sdf(*point(m)) <= 0
        lo_in = np.where(ins, m, lo_in); lo_out = np.where(ins, lo_out, m)
        m = (hi_in + hi_out) / 2; ins = sdf(*point(m)) <= 0
        hi_in = np.where(ins, m, hi_in); hi_out = np.where(ins, hi_out, m)
    return [(a, b) for a, b in zip(lo_in, hi_in) if b - a >= min_len]


class Course:
    """Helpers a pattern uses to lay rods in course i of a region."""

    def __init__(self, region, nz, i):
        self.region, self.nz, self.i = region, nz, i
        self.z = region.z(i)
        f = region.sdf(self.z); h = nz.rod_w / 2
        self.sdf = lambda x, y: f(x, y) + h       # clip bead CENTRE lines to the region shrunk by half a bead:
                                                  # the bead's skin then stays inside the outline everywhere
        self.E = region.extent + nz.pitch

    def lines(self, theta, pitch=None, keep=None, offset=None, step=None):
        """Parallel rods along theta at `pitch`; keep(j) filters rods; offset(t, j) -> lateral wiggle (ripples).
        Returns [(j, t0, t1, point_fn)] where point_fn(t) -> (x, y)."""
        pitch = pitch or self.nz.pitch; step = step or min(1.0, pitch / 3)
        ct, st = math.cos(theta), math.sin(theta)
        n = int(math.ceil(self.E / pitch)) + 1; out = []
        for j in range(-n, n + 1):
            if keep is not None and not keep(j):
                continue
            c = j * pitch
            if offset is None:
                pf = lambda t, c=c: (t * ct - c * st, t * st + c * ct)
            else:
                pf = lambda t, c=c, j=j: (t * ct - (c + offset(t, j)) * st, t * st + (c + offset(t, j)) * ct)
            for t0, t1 in runs(pf, self.sdf, -self.E, self.E, step, 0.25 * self.nz.rod_w):
                out.append((j, t0, t1, pf))
        return out

    def curve(self, point, t_lo, t_hi, step=1.0):
        return [(t0, t1) for t0, t1 in runs(point, self.sdf, t_lo, t_hi, step, 0.25 * self.nz.rod_w)]


class Rods:
    """Accumulates rods per colour slot; straight ones are batched."""

    def __init__(self, nz):
        self.nz = nz; self.lines = {}; self.paths = {}; self.layers = {}

    def _span(self, slot, z0, z1):
        self.layers.setdefault(slot, []).append((z0, z1))

    def line(self, a, b, slot):
        self.lines.setdefault(slot, []).append((a, b)); h = self.nz.rod_h / 2
        self._span(slot, a[2] - h, a[2] + h)

    def path(self, pts, slot):
        pts = np.asarray(pts, float)
        if len(pts) >= 2:
            self.paths.setdefault(slot, []).append(pts); h = self.nz.rod_h / 2
            self._span(slot, pts[:, 2].min() - h, pts[:, 2].max() + h)

    def count(self):
        return sum(len(v) for v in self.lines.values()) + sum(len(v) for v in self.paths.values())

    def meshes(self):
        rw, rh = self.nz.rod_w, self.nz.rod_h; out = {}
        for slot in sorted(set(self.lines) | set(self.paths)):
            parts = []
            if self.lines.get(slot):
                A = np.array([a for a, _ in self.lines[slot]]); B = np.array([b for _, b in self.lines[slot]])
                parts.append(straight_beads(A, B, rw, rh))
            parts += [path_bead(p, rw, rh) for p in self.paths.get(slot, [])]
            parts = [p for p in parts if p is not None]
            if parts:
                out[slot] = trimesh.util.concatenate(parts)
        return out

    def swap_estimate(self, layer_h):
        """AMS swaps if Bambu orders colours greedily per layer (one swap per course for course-coloured
        patterns, about one per layer when colours mix inside a course)."""
        if len(self.layers) <= 1:
            return 0
        top = max(z1 for v in self.layers.values() for _, z1 in v)
        nl = int(math.ceil(top / layer_h)); present = {}
        for slot, spans in self.layers.items():
            mark = np.zeros(nl, bool)
            for z0, z1 in spans:
                mark[max(0, int(z0 / layer_h + 0.01)):min(nl, int(math.ceil(z1 / layer_h - 0.01)))] = True
            present[slot] = mark
        swaps, last = 0, None
        for k in range(nl):
            S = [s for s in present if present[s][k]]
            if not S:
                continue
            if last in S:
                swaps += len(S) - 1; last = [s for s in S if s != last][-1] if len(S) > 1 else last
            else:
                swaps += len(S) if last is not None else len(S) - 1; last = S[-1]
        return swaps


def _pt(pf, t, z):
    x, y = pf(np.array([t])); return [float(x[0]), float(y[0]), z]


# ── patterns ──────────────────────────────────────────────────────────────────
def p_grid(region, nz, rods, twill=0, cross_pitch=1.0, tartan=None):
    for i in range(region.n):
        c = Course(region, nz, i); axis = i % 2; same = i // 2
        tw = twill and same % 2 == 1 and i != region.n - 1
        ph = (same // 2) % twill if twill else 0
        pitch = nz.pitch * (cross_pitch if axis == 1 else 1.0)
        keep = None
        if tw:
            # never skip a rod that is the only one in its wall band: the cross rods of the next course rest on it
            # and would print in mid-air (a 6 mm wall holds one lengthwise rod on some sides, Oct 25 2026)
            lens = {}
            for j, t0, t1, _ in c.lines(axis * math.pi / 2, pitch=pitch):
                lens[j] = max(lens.get(j, 0.0), t1 - t0)
            lmax = max(lens.values()) if lens else 0.0
            band = sorted(j for j, ln in lens.items() if ln > 0.6 * lmax)
            groups, cur = [], []
            for j in band:
                if cur and j != cur[-1] + 1:
                    groups.append(cur); cur = []
                cur.append(j)
            if cur:
                groups.append(cur)
            protect = {g[0] for g in groups if len(g) == 1}
            fc = int(getattr(region, "floor_courses", 0) or 0)
            if lens and fc and fc - 2 <= i < fc:          # the last floor courses: the first wall course stands on
                protect |= {min(lens), max(lens), min(lens) + 1, max(lens) - 1} & set(band)   # their outermost rods
            keep = lambda j, ph=ph, protect=protect: j in protect or (j + ph) % twill != 0
        for j, t0, t1, pf in c.lines(axis * math.pi / 2, pitch=pitch, keep=keep):
            slot = axis
            if tartan:
                seq = tartan[axis]; slot = 0 if (j % sum(seq)) < seq[0] else 1
            rods.line(_pt(pf, t0, c.z), _pt(pf, t1, c.z), slot)


def p_kagome(region, nz, rods):
    for i in range(region.n):
        c = Course(region, nz, i); k = i % 3
        for j, t0, t1, pf in c.lines(k * math.pi / 3, pitch=nz.pitch * 1.15):
            rods.line(_pt(pf, t0, c.z), _pt(pf, t1, c.z), k)


def p_polar(region, nz, rods):
    p = nz.pitch; R = region.extent
    for i in range(region.n):
        c = Course(region, nz, i)
        if i % 2 == 0:                                                           # rings
            k = 1
            while k * p < R:
                r = k * p
                pf = lambda t, r=r: (r * np.cos(t), r * np.sin(t))
                spans = c.curve(pf, 0, 2 * math.pi - 1e-6, step=min(0.2, 1.0 / r))
                full = len(spans) == 1 and spans[0][1] - spans[0][0] > 2 * math.pi - 0.05
                for t0, t1 in spans:
                    if full:
                        t1 = t0 + 2 * math.pi
                    ts = np.linspace(t0, t1, max(8, int((t1 - t0) * r / 1.2)))
                    rods.path(np.column_stack([*pf(ts), np.full(len(ts), c.z)]), 0)
                k += 1
        else:                                                                    # spokes, halving inward
            N = max(16, int(2 ** round(math.log2(2 * math.pi * R / p))))
            for s in range(N):
                lvl = 0
                while lvl < 6 and s % (2 ** (lvl + 1)) == 0:
                    lvl += 1
                r0 = max((N / 2 ** lvl) * p / (2 * math.pi), p * 0.8)
                th = 2 * math.pi * s / N
                pf = lambda t, th=th: (t * math.cos(th) + 0 * t, t * math.sin(th) + 0 * t)
                for t0, t1 in c.curve(pf, r0, R + p, step=0.5):
                    rods.line(_pt(pf, t0, c.z), _pt(pf, t1, c.z), 1)


def p_ripple(region, nz, rods, period=18.0):
    amp = max(0.2, (nz.pitch - nz.rod_w) / 2 - 0.15)
    off = lambda t, j: amp * np.sin(2 * np.pi * np.asarray(t) / period + (0 if j % 2 == 0 else np.pi))
    for i in range(region.n):
        c = Course(region, nz, i)
        if i % 2 == 0:
            for j, t0, t1, pf in c.lines(0.0, offset=off, step=0.75):
                ts = np.linspace(t0, t1, max(2, int((t1 - t0) / (period / 14))))
                rods.path(np.column_stack([*pf(ts), np.full(len(ts), c.z)]), 0)
        else:
            for j, t0, t1, pf in c.lines(math.pi / 2):
                rods.line(_pt(pf, t0, c.z), _pt(pf, t1, c.z), 1)


def p_selvedge(region, nz, rods):
    """Grid + U-turn loops joining neighbouring rod ends wherever a rod meets an edge (outline or dish). Ends are
    pulled in by the loop radius so loops never reach past the region."""
    p = nz.pitch; pull = p / 2
    for i in range(region.n):
        c = Course(region, nz, i); axis = i % 2; th = axis * math.pi / 2
        u = np.array([math.cos(th), math.sin(th), 0.0])
        lines = c.lines(th)
        ends = []                                       # (j, side, point, rod index)
        segs = []
        for k, (j, t0, t1, pf) in enumerate(lines):
            a = np.array(_pt(pf, t0, c.z)); b = np.array(_pt(pf, t1, c.z))
            segs.append([a, b]); ends.append((j, 0, k)); ends.append((j, 1, k))
        paired = set(); loops = []
        by = {}
        for j, side, k in ends:
            by.setdefault((j, side), []).append(k)
        for (j, side), ks in sorted(by.items()):
            for k in ks:
                if (k, side) in paired:
                    continue
                for k2 in by.get((j + 1, side), []):
                    if (k2, side) in paired:
                        continue
                    if np.linalg.norm(segs[k][side] - segs[k2][side]) < 1.6 * p:
                        paired.add((k, side)); paired.add((k2, side)); loops.append((k, k2, side)); break
        dirs = {0: -u, 1: u}
        for k, side in paired:
            segs[k][side] = segs[k][side] - dirs[side] * pull
        for k, (a, b) in enumerate(segs):
            if np.dot(b - a, u) >= nz.rod_w * 0.5:
                rods.line(a.tolist(), b.tolist(), axis)
        for k, k2, side in loops:
            A, B = segs[k][side], segs[k2][side]; d = dirs[side] * (2 * pull / 0.75 * 0.5)
            P0, P1, P2, P3 = A, A + d, B + d, B
            ts = np.linspace(0, 1, 12)[:, None]
            curve = (1 - ts) ** 3 * P0 + 3 * (1 - ts) ** 2 * ts * P1 + 3 * (1 - ts) * ts ** 2 * P2 + ts ** 3 * P3
            rods.path(curve, axis)


def p_overunder(region, nz, rods):
    """True over-under: X and Y rods share a 2-course band and undulate so each passes over then under."""
    p = nz.pitch; A = nz.rod_h / 2
    for b in range(region.n // 2):
        zb = (2 * b + 1) * nz.rod_h
        c = Course(region, nz, 2 * b + 1)
        for axis in (0, 1):
            th = axis * math.pi / 2
            for j, t0, t1, pf in c.lines(th, step=0.6):
                s = 1 if j % 2 == 0 else -1
                ts = np.linspace(t0, t1, max(4, int((t1 - t0) / (p / 5))))
                x, y = pf(ts)
                along = x if axis == 0 else y
                z = zb + (A * s * np.cos(np.pi * along / p) if axis == 0 else -A * s * np.cos(np.pi * along / p))
                rods.path(np.column_stack([x, y, z]), axis)
    if region.n % 2 == 1:                                                         # finishing course on top
        c = Course(region, nz, region.n - 1)
        for j, t0, t1, pf in c.lines(0.0):
            rods.line(_pt(pf, t0, c.z), _pt(pf, t1, c.z), 0)


# ── more weaves (Oct 2026): curved rods, broken rods, outline rods ─────────────────────────────────────────
def _tri(x):
    """Triangle wave, period 1, -1..1."""
    x = np.mod(x, 1.0)
    return 4 * np.abs(x - 0.5) - 1


def _curved(c, rods, theta, pitch, offset, slot, keep=None):
    """Parallel curved rods (offset(t, j) sideways from straight), clipped and laid as paths."""
    for j, t0, t1, pf in c.lines(theta, pitch=pitch, keep=keep, offset=offset, step=0.6):
        ts = np.linspace(t0, t1, max(3, int((t1 - t0) / 0.9)))
        rods.path(np.column_stack([*pf(ts), np.full(len(ts), c.z)]), slot)


def p_chevron(region, nz, rods, period=4.0, rise=0.42):
    """Parallel zigzag rods (V after V) crossed by straight ones: chevron stripes."""
    P = nz.pitch * period; A = P * rise / 2
    for i in range(region.n):
        c = Course(region, nz, i)
        if i % 2 == 0:
            _curved(c, rods, 0.0, nz.pitch * 1.1, lambda t, j: A * _tri(np.asarray(t) / P), 0)
        else:
            for j, t0, t1, pf in c.lines(math.pi / 2):
                rods.line(_pt(pf, t0, c.z), _pt(pf, t1, c.z), 1)


def p_herringbone(region, nz, rods, period=4.0, rise=0.42):
    """Zigzag rods in both directions: the woven herringbone of tweed."""
    P = nz.pitch * period; A = P * rise / 2
    for i in range(region.n):
        c = Course(region, nz, i)
        _curved(c, rods, (i % 2) * math.pi / 2, nz.pitch * 1.1,
                lambda t, j: A * _tri(np.asarray(t) / P + (0.5 if (j // 3) % 2 else 0.0)), i % 2)


def p_ogee(region, nz, rods, period=7.0):
    """Wavy rods mirrored pairwise: neighbours swell apart and pinch together into onion-shaped lenses."""
    pitch = nz.pitch * 1.6; A = max(0.4, (pitch - nz.rod_w - 0.5) / 2); P = nz.pitch * period
    for i in range(region.n):
        c = Course(region, nz, i)
        _curved(c, rods, (i % 2) * math.pi / 2, pitch,
                lambda t, j: A * np.sin(2 * math.pi * np.asarray(t) / P) * (1 if j % 2 == 0 else -1), i % 2)


def _segments(c, rods, theta, pitch, slot, present, min_len):
    """Straight rods broken where present(x, y, j) is False; a piece must cross >= 2 rods below (min_len)."""
    for j, t0, t1, pf in c.lines(theta, pitch=pitch):
        ts = np.arange(t0, t1, 0.4); x, y = pf(ts)
        on = present(x, y, j)
        k = 0
        while k < len(ts):
            if not on[k]:
                k += 1; continue
            k2 = k
            while k2 + 1 < len(ts) and on[k2 + 1]:
                k2 += 1
            a, b = ts[k], min(ts[k2] + 0.4, t1)
            if b - a >= min_len:
                rods.line(_pt(pf, a, c.z), _pt(pf, b, c.z), slot)
            k = k2 + 1


def p_basket(region, nz, rods, cells=3):
    """Basketweave: checkerboard blocks where the across rods drop away and the course beneath shows through."""
    S = nz.pitch * cells
    for i in range(region.n):
        c = Course(region, nz, i)
        if i % 2 == 1 or i < 2:                                # full: the first floor courses and every Y course
            for j, t0, t1, pf in c.lines((i % 2) * math.pi / 2):
                rods.line(_pt(pf, t0, c.z), _pt(pf, t1, c.z), i % 2)
        else:
            _segments(c, rods, 0.0, nz.pitch, 0,
                      lambda x, y, j: ((np.floor(x / S) + np.floor(y / S)) % 2) == 0, 2 * nz.pitch)


def p_brick(region, nz, rods, length=4.0):
    """Brick bond: rods broken into bricks, every other row offset by half a brick."""
    L = nz.pitch * length; g = nz.pitch * 0.9
    for i in range(region.n):
        c = Course(region, nz, i)
        if i % 2 == 1 or i < 2:
            for j, t0, t1, pf in c.lines((i % 2) * math.pi / 2):
                rods.line(_pt(pf, t0, c.z), _pt(pf, t1, c.z), i % 2)
        else:
            _segments(c, rods, 0.0, nz.pitch, 0,
                      lambda x, y, j: np.mod(x + (L + g) / 2 * (j % 2), L + g) < L, 2 * nz.pitch)


def p_trellis(region, nz, rods):
    """Rods at +45 and -45 degrees: an open diamond trellis."""
    for i in range(region.n):
        c = Course(region, nz, i)
        for j, t0, t1, pf in c.lines(math.pi / 4 if i % 2 == 0 else -math.pi / 4, pitch=nz.pitch * 1.35):
            rods.line(_pt(pf, t0, c.z), _pt(pf, t1, c.z), i % 2)


def p_frame(region, nz, rods):
    """Picture frame: rods that follow the piece's own outline in concentric rings, crossed by straight rods."""
    import skimage.measure as skm
    E = region.extent + nz.pitch; n = int(2 * E / 0.5)
    g = np.linspace(-E, E, n); X, Y = np.meshgrid(g, g, indexing="ij")
    for i in range(region.n):
        c = Course(region, nz, i)
        if i % 2 == 1:
            for j, t0, t1, pf in c.lines(math.pi / 2 if (i // 2) % 2 else 0.0, pitch=nz.pitch * 1.25):
                rods.line(_pt(pf, t0, c.z), _pt(pf, t1, c.z), 1)
            continue
        F = c.sdf(X, Y); k = 0
        while True:
            level = -k * nz.pitch
            if F.min() > level:
                break
            for cont in skm.find_contours(F, level):
                pts = np.column_stack([np.interp(cont[:, 0], np.arange(n), g), np.interp(cont[:, 1], np.arange(n), g)])
                seg = np.hypot(*np.diff(pts, axis=0).T)                 # resample to ~0.9 mm spacing
                pts = pts[np.r_[0, np.where(np.diff(np.floor(np.concatenate([[0], np.cumsum(seg)]) / 0.9)) > 0)[0], len(pts) - 1]]
                if len(pts) < 4 or np.hypot(*(pts.max(0) - pts.min(0))) < 2 * nz.rod_w:
                    continue
                rods.path(np.column_stack([pts, np.full(len(pts), c.z)]), 0)
            k += 1
            if k > 400:
                break


def _contour_rings(F, g, level, min_size):
    import skimage.measure as skm
    n = len(g); out = []
    for cont in skm.find_contours(F, level):
        pts = np.column_stack([np.interp(cont[:, 0], np.arange(n), g), np.interp(cont[:, 1], np.arange(n), g)])
        if len(pts) < 8 or np.hypot(*(pts.max(0) - pts.min(0))) < min_size:
            continue
        seg = np.hypot(*np.diff(pts, axis=0).T)
        keep = np.r_[0, np.where(np.diff(np.floor(np.concatenate([[0], np.cumsum(seg)]) / 0.9)) > 0)[0], len(pts) - 1]
        out.append(pts[keep])
    return out


def p_labyrinth(region, nz, rods, rings=2, spacing=2.6):
    """Labyrinth: rods follow the outline in concentric rings with a gap in each (alternating sides) and short
    bridges between neighbours — one meandering path, like a classical labyrinth — raised over a two-colour weave.
    The ring courses go on the piece's top face; a lid (printed upside down) gets them on its bed face, so they end
    up on top once it's flipped on (region.face = "bottom"). A clear centre is kept for a knob."""
    face = getattr(region, "face", "top")
    ring_i = set(range(rings)) if face == "bottom" else set(range(region.n - rings, region.n))
    E = region.extent + nz.pitch; n = int(2 * E / 0.5)
    g = np.linspace(-E, E, n); X, Y = np.meshgrid(g, g, indexing="ij")
    sp = spacing * nz.pitch; gap = 1.6 * nz.pitch; centre = 11.0
    for i in range(region.n):
        c = Course(region, nz, i)
        if i not in ring_i:
            for j, t0, t1, pf in c.lines((i % 2) * math.pi / 2, pitch=nz.pitch * 1.15):
                rods.line(_pt(pf, t0, c.z), _pt(pf, t1, c.z), i % 2)
            continue
        F = c.sdf(X, Y); k = 0; levels = []
        while F.min() < -k * sp and k < 200:
            rs = _contour_rings(F, g, -k * sp, 2 * nz.rod_w)
            rs = [r for r in rs if np.hypot(r[:, 0], r[:, 1]).max() > centre + sp]
            if not rs:
                break
            levels.append(rs); k += 1
        for k, rs in enumerate(levels):
            for r in rs:
                if k == 0:                                             # the frame: unbroken
                    rods.path(np.column_stack([r, np.full(len(r), c.z)]), 2); continue
                ang = np.arctan2(r[:, 1], r[:, 0]); rad = np.hypot(r[:, 0], r[:, 1])
                at = 0.0 if k % 2 else math.pi                         # the gap alternates sides ring to ring
                d = np.abs((ang - at + math.pi) % (2 * math.pi) - math.pi) * rad
                keep = d > gap / 2
                if keep.all():
                    rods.path(np.column_stack([r, np.full(len(r), c.z)]), 2); continue
                cut = np.where(~keep)[0]                               # roll so the gap sits at the ends
                r2 = np.roll(r[:-1] if np.allclose(r[0], r[-1]) else r, -int(cut[-1]) - 1, axis=0)
                k2 = np.roll(keep[:-1] if np.allclose(r[0], r[-1]) else keep, -int(cut[-1]) - 1)
                seg = r2[k2]
                if len(seg) >= 2:
                    rods.path(np.column_stack([seg, np.full(len(seg), c.z)]), 2)
                if k + 1 < len(levels) and k % 2 == 1 and i == min(ring_i):   # a bridge inward beside the gap
                    for end in (seg[0], seg[-1])[:1]:
                        inner = np.vstack(levels[k + 1]); dd = np.hypot(*(inner - end).T)
                        q = inner[int(np.argmin(dd))]
                        if dd.min() < 1.6 * sp:
                            rods.line([float(end[0]), float(end[1]), c.z], [float(q[0]), float(q[1]), c.z], 2)


PATTERNS = {
    "grid":      dict(name="Weave", blurb="The classic: rods cross at right angles, colour by direction", slots=2, fn=p_grid, swaps="course"),
    "twill":     dict(name="Twill", blurb="Every 4th rod skipped on alternate courses — a drifting diagonal", slots=2, fn=lambda r, n, o: p_grid(r, n, o, twill=4), swaps="course"),
    "kagome":    dict(name="Kagome", blurb="Three directions at 60° — triangles and hexagons", slots=3, fn=p_kagome, swaps="course"),
    "polar":     dict(name="Rose window", blurb="Rings and spokes that halve toward the centre", slots=2, fn=p_polar, swaps="course", round_only=True),
    "ripple":    dict(name="Ripple", blurb="Wavy rods against straight ones — reed and honeycomb", slots=2, fn=p_ripple, swaps="course"),
    "selvedge":  dict(name="Selvedge", blurb="Rod ends join in loops — a woven hem on every edge", slots=2, fn=p_selvedge, swaps="course"),
    "beat":      dict(name="Moiré", blurb="Two rod spacings that beat into large bands", slots=2, fn=lambda r, n, o: p_grid(r, n, o, cross_pitch=1.18), swaps="course"),
    "overunder": dict(name="Over-under", blurb="A true weave — rods pass over and under each other", slots=2, fn=p_overunder, swaps="layer"),
    "chevron":   dict(name="Chevron", blurb="Parallel zigzag rods crossed by straight ones — stacked Vs", slots=2, fn=p_chevron, swaps="course"),
    "herringbone": dict(name="Herringbone", blurb="Zigzag rods both ways, flipping in blocks — woven tweed", slots=2, fn=p_herringbone, swaps="course"),
    "ogee":      dict(name="Ogee", blurb="Wavy rods mirrored in pairs, pinching into onion-shaped lenses", slots=2, fn=p_ogee, swaps="course"),
    "basket":    dict(name="Basketweave", blurb="Checkerboard blocks where one direction drops away to show the other", slots=2, fn=p_basket, swaps="course"),
    "brick":     dict(name="Brick bond", blurb="Rods broken into staggered bricks over a full cross course", slots=2, fn=p_brick, swaps="course"),
    "trellis":   dict(name="Trellis", blurb="Rods at ±45° — an open diamond trellis", slots=2, fn=p_trellis, swaps="course"),
    "frame":     dict(name="Picture frame", blurb="Rods follow the piece's own outline in concentric rings", slots=2, fn=p_frame, swaps="course"),
    "tartan":    dict(name="Tartan", blurb="Colour runs along both directions — plaid", slots=2, fn=lambda r, n, o: p_grid(r, n, o, tartan=((3, 1), (2, 2))), swaps="layer"),
}


PATTERNS["labyrinth"] = dict(name="Labyrinth", blurb="Raised rings that follow the outline, broken into a maze, over a "
                             "two-colour weave — made for lids (3 colours)", slots=3, fn=p_labyrinth, swaps="course")
GROUPABLE = {"grid", "twill", "kagome", "polar", "ripple", "selvedge", "beat", "chevron", "herringbone", "ogee",
             "basket", "brick", "trellis", "frame"}                                    # colour follows the course


def weave(region, nz, pattern, group=1, params=None, twist=0.0, ombre=None, picture=None, face="top", courses=None, ombre_ends=0, sett=None, face_lines=None):
    """group > 1: colour changes every `group` courses instead of every course (bands, not colour by
    direction) — a half, a third or a quarter of the AMS changes.
    Modifiers Claude sets from a description (any weave):
      twist   degrees each course turns about the centre — the weave spirals up the piece
      ombre   slots bottom -> top, e.g. [0, 1] or [0, 2, 1]: course colours fade through them (ordered dither)
      picture (dark(x, y, z) -> bool, first_course): rods split and coloured by a picture — dark parts in slot 1
    face: "top" or "bottom" — which face shows (a lid prints upside down); patterns like labyrinth read it
    courses: (offset, sign, total) — this piece's courses inside a taller whole (a base and its flipped lid):
      course c is course offset + sign * c of total, so the twist and the ombre carry on across the seam
    ombre_ends: courses held solid at each end of the ombre
    face_lines: {"kind": "waves", "pitch", "amp", "wave", "slot"} — continuous rods laid along curves on the face
      course (a lid's top), like the picture frame's rings: the face course's straight rods turn the other colour
      and the curves run over them in `slot`, so solid lines sit on a woven field
    sett: ((a, b), (c, d)) — a colour sett for grid and twill: along each direction, a rods in one colour then b in
      the other (a tartan's stripe order); twill woven with a sett is how tartans and houndstooth are made"""
    rods = Rods(nz)
    region.face = face
    reg = _Twisted(region, twist, courses) if twist else region
    if sett and pattern in ("grid", "twill"):
        p_grid(reg, nz, rods, twill=4 if pattern == "twill" else 0, tartan=sett)
    elif PATTERNS[pattern].get("custom"):                    # a plugin weave: its sliders' values
        from .plugins import call
        call(PATTERNS[pattern]["fn"], reg, nz, rods, p=params)
    else:
        PATTERNS[pattern]["fn"](reg, nz, rods)
    if twist:
        _untwist(rods, reg)
    if face_lines:
        _face_lines(region, nz, rods, face_lines)
    if ombre and len(ombre) >= 2:
        recolour_ombre(rods, list(ombre), region.n, courses, ombre_ends)
    elif group > 1 and pattern in GROUPABLE:
        regroup(rods, group, PATTERNS[pattern]["slots"])
    if picture is not None:
        recolour_picture(rods, *picture)          # (dark, first course[, last course])
    return rods


def _face_lines(region, nz, rods, spec):
    """Curves as rods on the face course: two families of waves half a wave apart (interlocking lenses)."""
    ci = 0 if getattr(region, "face", "top") == "bottom" else region.n - 1
    slot = int(spec.get("slot", 0)); ground = 1 - slot if slot in (0, 1) else 1
    pitch = float(spec.get("pitch", 15.0)); amp = float(spec.get("amp", 5.0)); k = 2 * math.pi / float(spec.get("wave", 90.0))
    rw = nz.rod_w; fc = max(1, int(getattr(region, "floor_courses", 0) or 0))
    paths = spec.get("paths")                                # a drawn line set (mm, as seen on the closed lid)
    if paths is not None:
        from shapely.geometry import LineString
        from shapely import vectorized
        flip = -1.0 if getattr(region, "face", "top") == "bottom" else 1.0   # the lid flips about x to close
        paths = [np.column_stack([np.asarray(q, float)[:, 0], flip * np.asarray(q, float)[:, 1]]) for q in paths]
        zone = None
        for q in paths:
            g = LineString(q).buffer(rw + 0.1)
            zone = g if zone is None else zone.union(g)

        def near(x, y):
            return vectorized.contains(zone, np.asarray(x, float), np.asarray(y, float))
    else:
        near = None

    def _near_waves(x, y):                                   # touching a wave rod of either family: perpendicular
        out = np.zeros(np.shape(x), bool)                   # distance ~ vertical distance / sqrt(1 + slope^2)
        for ph, off in ((0.0, 0.0), (math.pi, pitch / 2)):
            dv = np.abs(((y - amp * np.sin(k * x + ph) - off) / pitch + 0.5) % 1.0 - 0.5) * pitch
            sl = amp * k * np.cos(k * x + ph)
            out |= dv / np.sqrt(1 + sl * sl) < 0.5 * rw + 0.5 * rw + 0.1      # the two beads' half-widths + a hair
        return out
    if near is None:
        near = _near_waves

    items = []
    for kind, g, sl in _all(rods):                          # the face course's straight rods: the ground colour, cut
        z = g[0][2] if kind == "line" else float(np.mean(np.asarray(g)[:, 2]))   # back where a wave rod crosses
        cc = _course(rods, z)
        if cc != ci:                                         # the rest of the top (the floor courses) goes to the ground
            top_floor = (cc < fc) if ci == 0 else (cc >= region.n - fc)    # colour too: nothing else peeks through
            items.append((kind, g, ground if top_floor else sl)); continue
        P = np.array([g[0], g[1]], float) if kind == "line" else np.asarray(g, float)
        if kind != "line":
            items.append((kind, g, ground)); continue
        L = float(np.hypot(*(P[1, :2] - P[0, :2])))
        ts = np.linspace(0, 1, max(2, int(L / 0.25)))
        pts = P[0] + (P[1] - P[0]) * ts[:, None]
        free = ~near(pts[:, 0], pts[:, 1])
        k0 = 0
        while k0 < len(ts):
            if not free[k0]:
                k0 += 1; continue
            k1 = k0
            while k1 + 1 < len(ts) and free[k1 + 1]:
                k1 += 1
            a_, b_ = pts[k0].copy(), pts[k1].copy()
            if np.hypot(*(b_[:2] - a_[:2])) >= rw:
                items.append(("line", (tuple(a_), tuple(b_)), ground))
            k0 = k1 + 1
    _rebuild(rods, items)
    c = Course(region, nz, ci)
    if paths is not None:                                    # each drawn line: one continuous rod, clipped to the outline
        for q in paths:
            seg = np.asarray(q, float)
            L = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(seg, axis=0).T))])
            if L[-1] < 2 * rw:
                continue
            pf = lambda t, seg=seg, L=L: (np.interp(t, L, seg[:, 0]), np.interp(t, L, seg[:, 1]))
            for t0, t1 in c.curve(pf, 0.0, float(L[-1]), step=0.5):
                ts = np.linspace(t0, t1, max(2, int((t1 - t0) / 0.5)))
                x_, y_ = pf(ts)
                rods.path(np.column_stack([x_, y_, np.full(len(ts), c.z)]), slot)
        return
    E = region.extent + pitch
    for phase in (0.0, math.pi):
        off = 0.0 if phase == 0.0 else pitch / 2
        y0 = -math.ceil(E / pitch) * pitch + off
        while y0 <= E:
            pf = lambda t, y0=y0, phase=phase: (t, y0 + amp * np.sin(k * np.asarray(t) + phase))
            for t0, t1 in c.curve(pf, -E, E, step=0.6):
                ts = np.linspace(t0, t1, max(2, int((t1 - t0) / 0.6)))
                rods.path(np.column_stack([ts, y0 + amp * np.sin(k * ts + phase), np.full(len(ts), c.z)]), slot)
            y0 += pitch


class _Twisted:
    """A region seen in each course's own rotated frame: patterns lay rods as usual, then _untwist turns course i
    by i x twist degrees. Clipping happens in the rotated frame, so every rod still ends inside the outline."""

    def __init__(self, region, twist_deg, courses=None):
        self.r = region; self.tw = math.radians(twist_deg); self.courses = courses
        self.n, self.rod_h, self.extent = region.n, region.rod_h, region.extent
        self.round, self.floor_courses, self.height = region.round, region.floor_courses, region.height
        self.face = getattr(region, "face", "top")

    def z(self, i):
        return self.r.z(i)

    def angle(self, z):
        c = round((z - self.rod_h / 2) / self.rod_h)
        if self.courses:                                    # a flipped lid: its course c is course off - c of the
            off, sg, _ = self.courses                       # whole, and the flip mirrors the turn
            return self.tw * sg * (off + sg * c)
        return self.tw * c

    def sdf(self, z):
        f = self.r.sdf(z); a = self.angle(z); c, s_ = math.cos(a), math.sin(a)
        return lambda x, y: f(x * c - y * s_, x * s_ + y * c)


def _untwist(rods, reg):
    def rot(pt, z):
        a = reg.angle(z); c, s_ = math.cos(a), math.sin(a)
        return [pt[0] * c - pt[1] * s_, pt[0] * s_ + pt[1] * c, pt[2]]
    rods.lines = {k: [(rot(a, a[2]), rot(b, b[2])) for a, b in v] for k, v in rods.lines.items()}
    out = {}
    for k, v in rods.paths.items():
        out[k] = []
        for P in v:
            P = np.array(P, float); a = np.array([reg.angle(z) for z in P[:, 2]])
            c, s_ = np.cos(a), np.sin(a)
            out[k].append(np.column_stack([P[:, 0] * c - P[:, 1] * s_, P[:, 0] * s_ + P[:, 1] * c, P[:, 2]]))
    rods.paths = out


def _course(rods, z):
    h = rods.nz.rod_h
    return int(round((z - h / 2) / h))


def _rebuild(rods, items):
    """items: [(kind 'line'|'path', geometry, slot)] -> rods.lines / paths / layers."""
    h = rods.nz.rod_h / 2
    rods.lines, rods.paths, rods.layers = {}, {}, {}
    for kind, g, sl in items:
        if kind == "line":
            rods.lines.setdefault(sl, []).append(g); z = g[0][2]
            rods.layers.setdefault(sl, []).append((z - h, z + h))
        else:
            rods.paths.setdefault(sl, []).append(g)
            rods.layers.setdefault(sl, []).append((g[:, 2].min() - h, g[:, 2].max() + h))


def _all(rods):
    return [("line", g, sl) for sl, v in rods.lines.items() for g in v] + \
           [("path", np.asarray(g, float), sl) for sl, v in rods.paths.items() for g in v]


def recolour_ombre(rods, stops, n_courses, courses=None, ends=0):
    """Course colours fade bottom -> top through the stops: within each step a course takes the upper colour
    when its height passes an ordered-dither threshold, so the mix ramps smoothly — one change per alternation.
    ends: courses held in the first / last colour at the bottom and the top, so both edges finish clean (no stray
    rods of the other colour fraying the rim or the base)."""
    def slot_of(c):
        if courses:                                         # this piece's course c is course off + sign * c of a whole
            off, sg, n_courses_ = courses; c = off + sg * c
        else:
            n_courses_ = n_courses
        span = max(n_courses_ - 1 - 2 * ends, 1)
        t = min(max((c - ends) / span, 0.0), 1.0) * (len(stops) - 1)
        k = min(int(t), len(stops) - 2); tt = t - k
        thr = (c * 0.6180339887 + 0.31) % 1.0
        return stops[k + 1] if tt > thr else stops[k]
    items = []
    for kind, g, _ in _all(rods):
        z = g[0][2] if kind == "line" else float(np.mean(g[:, 2]))
        items.append((kind, g, slot_of(_course(rods, z))))
    _rebuild(rods, items)


def recolour_picture(rods, dark, first_course, last_course=None, step=0.4):
    """Rods from first_course up are split where the picture changes; dark parts go to slot 1, light to slot 0.
    Pieces end half a bead short of a colour change so neighbouring colours touch instead of overlapping;
    specks shorter than a bead width take their neighbours' colour."""
    rw = rods.nz.rod_w; items = []
    for kind, g, sl in _all(rods):
        P = np.array([g[0], g[1]], float) if kind == "line" else g
        cc = _course(rods, float(P[0][2]))
        if cc < first_course or (last_course is not None and cc > last_course):
            items.append((kind, g, sl)); continue
        seg = np.hypot(*np.diff(P[:, :2], axis=0).T); cum = np.concatenate([[0], np.cumsum(seg)]); L = cum[-1]
        if L < 1e-6:
            items.append((kind, g, sl)); continue
        ts = np.append(np.arange(0, L, step), L)
        pts = np.column_stack([np.interp(ts, cum, P[:, k]) for k in range(3)])
        d = np.asarray(dark(pts[:, 0], pts[:, 1], pts[:, 2]), bool)
        runs, k = [], 0                                            # runs of one colour along the rod
        while k < len(ts):
            k2 = k
            while k2 + 1 < len(ts) and d[k2 + 1] == d[k]:
                k2 += 1
            runs.append([ts[k], ts[k2] if k2 + 1 >= len(ts) else (ts[k2] + ts[k2 + 1]) / 2, d[k]])
            if k2 + 1 < len(ts):
                runs[-1][1] = (ts[k2] + ts[k2 + 1]) / 2
            k = k2 + 1
        for i_ in range(1, len(runs)):                              # starts meet the previous end
            runs[i_][0] = runs[i_ - 1][1]
        changed = True                                              # absorb specks
        while changed and len(runs) > 1:
            changed = False
            for i_, r in enumerate(runs):
                if r[1] - r[0] < rw:
                    j = i_ - 1 if i_ > 0 else i_ + 1
                    a, b = sorted((i_, j)); runs[a] = [runs[a][0], runs[b][1], runs[j][2]]; del runs[b]
                    changed = True; break
            merged = []
            for r in runs:                                          # neighbours of one colour join
                if merged and merged[-1][2] == r[2]:
                    merged[-1][1] = r[1]
                else:
                    merged.append(r)
            runs = merged
        for i_, (a, b, dk) in enumerate(runs):
            a2 = a + (rw / 2 if i_ > 0 else 0.0); b2 = b - (rw / 2 if i_ < len(runs) - 1 else 0.0)
            if b2 - a2 < rw * 0.5:
                continue
            if kind == "line" and len(runs) == 1:
                items.append(("line", g, 1 if dk else 0)); continue
            sub = np.append(np.arange(a2, b2, 0.9), b2)
            Q = np.column_stack([np.interp(sub, cum, P[:, k]) for k in range(3)])
            if kind == "line":
                items.append(("line", (list(Q[0]), list(Q[-1])), 1 if dk else 0))
            else:
                items.append(("path", Q, 1 if dk else 0))
    _rebuild(rods, items)


def regroup(rods, group, n_slots):
    """Reassign every rod's colour by its course: slot = (course // group) % n_slots."""
    h = rods.nz.rod_h
    course = lambda z: int(round((z - h / 2) / h))
    lines, paths, layers = {}, {}, {}
    for _, ls in rods.lines.items():
        for a, b in ls:
            s = (course(a[2]) // group) % n_slots
            lines.setdefault(s, []).append((a, b)); layers.setdefault(s, []).append((a[2] - h / 2, a[2] + h / 2))
    for _, ps in rods.paths.items():
        for pts in ps:
            s = (course(float(np.mean(pts[:, 2]))) // group) % n_slots
            paths.setdefault(s, []).append(pts)
            layers.setdefault(s, []).append((pts[:, 2].min() - h / 2, pts[:, 2].max() + h / 2))
    rods.lines, rods.paths, rods.layers = lines, paths, layers
