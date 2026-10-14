"""Woven rod lattice ("printed basketry") — print-verified Oct 2026 on a Bambu P2S, 0.4 nozzle, PLA, 2 colours.

The object is a stack of COURSES. A course is a set of parallel rods, `rod_layers` print layers tall; the next
course runs in another direction, so every rod bridges short gaps across the rods beneath it and the whole thing is
an open lattice with no supports. Each rod is a rounded bead (elliptical rw x rh section, rounded ends) — nothing
square anywhere. Colour follows direction by default (X rods -> filament 1, Y rods -> filament 2), which costs one
AMS swap per course; patterns that mix colours inside a course (tartan, over-under) cost one swap per LAYER.

    from textures.rodweave import (ROD, RoundedSquare, Circle, grid_courses, PATTERNS, block,
                                   export_bambu, slice_cli, ROD_OVERRIDES)

    # a) a pattern tile (sampler): list of (mesh, colour_hex) ready for export_bambu
    rods = PATTERNS["selvedge"](RoundedSquare(90, 14), height=12)
    export_bambu("tile.3mf", rods, title="selvedge tile")

    # b) the printed tray/platter family (round dish, pillowed top, flat bottom, twill)
    rust, cream = block(size=117, height=33, floor_t=10.4, corner_r=20, dip_d=94)
    export_bambu("tray.3mf", [(rust, RUST), (cream, CREAM)], title="woven tray")

Laws (all learned the hard way, see docs in SKILL.md "Woven rod lattice"):
  * one OBJECT with one PART per colour — never one object per colour (empty layers -> Bambu refuses to slice)
  * meshes centred on XY=0 (bambu_3mf places by centre); bed 256, prime tower parked at (216,216)
  * a course may never reach past the course below it (Collin: flat bottom, no outward steps); the top pillow is fine
  * rod lattices are all "overhang wall" to the slicer: ROD_OVERRIDES raises overhang/bridge speeds to 50 mm/s
    (stock 10 mm/s doubles the print time for nothing — spans are < 2 mm bridges)
"""
import json
import math
import pathlib
import re
import subprocess
import sys
import zipfile

import numpy as np
import trimesh

_TOOLS = pathlib.Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

RUST, CREAM, GOLD = "#8B3A2F", "#EDE3D1", "#B8862B"
SLOT = {RUST: 1, CREAM: 2, GOLD: 3}
ROD = dict(rw=1.68, rh=0.80, pitch=3.6, layer_h=0.20, rod_layers=4)   # 4 lines x 4 layers, 0.4 nozzle — the proven bead
BAMBU = "/Applications/BambuStudio.app/Contents/MacOS/BambuStudio"


# ── outlines ──────────────────────────────────────────────────────────────────
class RoundedSquare:
    def __init__(self, size, r):
        self.size, self.r, self.half = float(size), float(r), size / 2.0
    def sdf(self, x, y, inset=0.0):
        half = self.half - inset; r = min(self.r, half); b = half - r
        qx, qy = abs(x) - b, abs(y) - b
        return math.hypot(max(qx, 0.0), max(qy, 0.0)) + min(max(qx, qy), 0.0) - r
    @property
    def extent(self):
        return self.size * 1.5


class Circle:
    def __init__(self, d):
        self.size, self.R = float(d), d / 2.0
    def sdf(self, x, y, inset=0.0):
        return math.hypot(x, y) - (self.R - inset)
    @property
    def extent(self):
        return self.size * 1.5


# ── bead primitives ───────────────────────────────────────────────────────────
def bead(points, widths=None, rw=ROD["rw"], rh=ROD["rh"], n=12):
    """Rounded bead along a 3D polyline: elliptical rw x rh section, rounded caps. Returns a watertight Trimesh
    with outward normals (positive volume). `widths` = per-point scale of the section."""
    P = np.asarray(points, float)
    if len(P) < 2:
        return None
    widths = np.ones(len(P)) if widths is None else np.asarray(widths, float)
    T = np.gradient(P, axis=0); T /= np.linalg.norm(T, axis=1)[:, None] + 1e-12
    cap = 4
    pts, scl = [], []
    for k in range(cap, 0, -1):
        a = k / (cap + 1)
        pts.append(P[0] - T[0] * (rw / 2) * widths[0] * a); scl.append(widths[0] * math.sqrt(max(1 - a * a, 0)))
    pts += list(P); scl += list(widths)
    for k in range(1, cap + 1):
        a = k / (cap + 1)
        pts.append(P[-1] + T[-1] * (rw / 2) * widths[-1] * a); scl.append(widths[-1] * math.sqrt(max(1 - a * a, 0)))
    pts = np.asarray(pts); scl = np.asarray(scl)
    T = np.gradient(pts, axis=0); T /= np.linalg.norm(T, axis=1)[:, None] + 1e-12
    up = np.array([0, 0, 1.0]); ang = np.linspace(0, 2 * np.pi, n, endpoint=False)
    V = []
    for p, t, s in zip(pts, T, scl):
        nrm = np.cross(t, up); nn = np.linalg.norm(nrm)
        nrm = nrm / nn if nn > 1e-9 else np.array([1.0, 0, 0])
        bin_ = np.cross(nrm, t)
        for a in ang:
            V.append(p + nrm * (rw / 2) * s * math.cos(a) + bin_ * (rh / 2) * s * math.sin(a))
    V = np.asarray(V); F = []; m = len(pts)
    for i in range(m - 1):
        for j in range(n):
            a, b = i * n + j, i * n + (j + 1) % n
            c, d = (i + 1) * n + j, (i + 1) * n + (j + 1) % n
            F += [[a, d, b], [a, c, d]]
    c0 = len(V); V = np.vstack([V, pts[0][None], pts[-1][None]])
    for j in range(n):
        F.append([c0, j, (j + 1) % n]); F.append([c0 + 1, (m - 1) * n + (j + 1) % n, (m - 1) * n + j])
    mesh = trimesh.Trimesh(V, np.asarray(F), process=False)
    if mesh.volume < 0:
        mesh.invert()
    return mesh


def straight(a, b, rw=ROD["rw"], rh=ROD["rh"]):
    return bead(np.asarray([a, b], float), rw=rw, rh=rh)


# ── course machinery ──────────────────────────────────────────────────────────
def clip_runs(xy, sdf, min_len=ROD["rw"]):
    runs, cur = [], []
    for p in xy:
        if sdf(p[0], p[1]) <= 0:
            cur.append(p)
        elif cur:
            runs.append(cur); cur = []
    if cur:
        runs.append(cur)
    out = []
    for r in runs:
        r = np.asarray(r)
        if len(r) >= 2 and np.linalg.norm(r[-1] - r[0]) >= min_len:
            out.append(r)
    return out


def course(z, theta, outline, pitch=ROD["pitch"], inset=0.0, shape=None, step=1.0, keep=None):
    """Straight (or shaped) rods along direction theta at spacing pitch, clipped to the outline.
    Returns [(j, pts[N,3])]. shape(ts, j) -> lateral offset array for rippled rods. keep(j) -> bool to skip rods."""
    rods = []
    ext = outline.extent; n = int(math.ceil(ext / pitch)) + 1
    ts = np.arange(-ext / 2, ext / 2 + step, step)
    ct, st = math.cos(theta), math.sin(theta)
    sdf = lambda x, y: outline.sdf(x, y, inset)
    for j in range(-n, n + 1):
        if keep and not keep(j):
            continue
        c = j * pitch
        off = shape(ts, j) if shape else np.zeros_like(ts)
        xy = np.stack([ts * ct - (c + off) * st, ts * st + (c + off) * ct], axis=1)
        for run in clip_runs(xy, sdf):
            rods.append((j, np.column_stack([run, np.full(len(run), z)])))
    return rods


def zc(i, rh=ROD["rh"]):
    """Centre height of course i."""
    return i * rh + rh / 2.0


def n_courses(height, rh=ROD["rh"]):
    return int(round(height / rh))


# ── the pattern catalogue: f(outline, height) -> [(mesh, colour)] ─────────────
def _add(out, m, col):
    if m is not None and len(m.faces):
        out.append((m, col))


def grid(outline, height, colours=(RUST, CREAM), twill_skip=0):
    """The base weave: alternating X/Y courses, optional twill (alternate courses of each axis skip every Nth rod,
    gap drifting one rod per repeat; never the top course)."""
    out = []; N = n_courses(height)
    for i in range(N):
        axis = i % 2; same = i // 2
        tw = twill_skip and same % 2 == 1 and i != N - 1
        phase = (same // 2) % twill_skip if twill_skip else 0
        keep = (lambda j, ph=phase: (j + ph) % twill_skip != 0) if tw else None
        for _, pts in course(zc(i), axis * math.pi / 2, outline, keep=keep):
            _add(out, straight(pts[0], pts[-1]), colours[axis])
    return out


def kagome(outline, height, colours=(RUST, CREAM, GOLD), pitch_scale=1.15):
    """Three directions (0/60/120) cycling course by course — triangular/hexagonal openings. 3 colours, or map two
    directions to one spool. One swap per course."""
    out = []
    for i in range(n_courses(height)):
        for _, pts in course(zc(i), (i % 3) * math.pi / 3, outline, pitch=ROD["pitch"] * pitch_scale):
            _add(out, straight(pts[0], pts[-1]), colours[i % 3])
    return out


def helix(outline, height, colours=(RUST, CREAM), deg_per_course=6.0):
    """Each course rotated a few degrees from the one below: moiré walls, spiralling rod ends. Free."""
    out = []
    for i in range(n_courses(height)):
        th = (i % 2) * math.pi / 2 + math.radians(deg_per_course * i)
        for _, pts in course(zc(i), th, outline):
            _add(out, straight(pts[0], pts[-1]), colours[i % 2])
    return out


def polar(outline, height, colours=(RUST, CREAM), n_spokes=64):
    """Concentric ring courses alternating with radial spokes that halve toward the centre (rose window).
    Wants a Circle outline. Ring bridges stay <= 2 pitches because spokes double every octave."""
    out = []; R = outline.size / 2.0; p = ROD["pitch"]; rw = ROD["rw"]
    for i in range(n_courses(height)):
        z = zc(i)
        if i % 2 == 0:
            k = 1
            while k * p < R - rw / 2:
                r = k * p
                a = np.linspace(0, 2 * np.pi, max(24, int(2 * np.pi * r / 1.5)), endpoint=True)
                _add(out, bead(np.column_stack([r * np.cos(a), r * np.sin(a), np.full(len(a), z)])), colours[0]); k += 1
        else:
            for n in range(n_spokes):
                lvl = 0
                while lvl < 5 and n % (2 ** (lvl + 1)) == 0:
                    lvl += 1
                r0 = max((n_spokes / 2 ** lvl) * p / (2 * np.pi), p)
                if r0 >= R - rw:
                    continue
                th = 2 * np.pi * n / n_spokes
                _add(out, straight([r0 * math.cos(th), r0 * math.sin(th), z],
                                   [(R - rw / 2) * math.cos(th), (R - rw / 2) * math.sin(th), z]), colours[1])
    return out


def ripple(outline, height, colours=(RUST, CREAM), amp=0.8, period=18.0):
    """X courses as sine rods (adjacent rods in antiphase -> honeycomb against the straight Y rods).
    amp <= (pitch - rw)/2 - 0.15 keeps neighbouring rods from touching (0.8 at the default bead)."""
    out = []
    shape = lambda ts, j: amp * np.sin(2 * np.pi * ts / period + (0 if j % 2 == 0 else np.pi))
    for i in range(n_courses(height)):
        if i % 2 == 0:
            for _, pts in course(zc(i), 0.0, outline, shape=shape, step=0.75):
                _add(out, bead(pts), colours[0])
        else:
            for _, pts in course(zc(i), math.pi / 2, outline):
                _add(out, straight(pts[0], pts[-1]), colours[1])
    return out


def selvedge(outline, height, colours=(RUST, CREAM)):
    """Base grid + U-turn loops joining neighbouring rod pairs at the outline (a woven hem instead of cut ends).
    Rod ends are pulled in by the loop radius so every loop stays inside the outline (no outward step)."""
    out = []; p = ROD["pitch"]; pull = p / 2.0     # loop radius: ends pulled in so loop apexes land ON the outline
    for i in range(n_courses(height)):
        th = (i % 2) * math.pi / 2; col = colours[i % 2]
        ct, st = math.cos(th), math.sin(th); u = np.array([ct, st, 0.0])
        byj = {}
        for j, pts in course(zc(i), th, outline):
            a, b = pts[0] + u * pull, pts[-1] - u * pull
            if np.dot(b - a, u) >= ROD["rw"]:
                byj[j] = np.array([a, b])
        for j, pts in byj.items():
            _add(out, straight(pts[0], pts[-1]), col)
        for j in byj:
            k = j + 1
            if k not in byj:
                continue
            end = 1 if j % 2 == 0 else 0
            a = byj[j][-1 if end else 0]; b = byj[k][-1 if end else 0]
            mid = (a + b) / 2; rad = np.linalg.norm(b - a) / 2
            if rad < 0.5:
                continue
            dirn = np.array([ct, st, 0.0]) * (1 if end else -1); side = (b - a) / (2 * rad)
            arc = np.array([mid - side * rad * math.cos(t) + dirn * rad * math.sin(t) for t in np.linspace(0, np.pi, 10)])
            _add(out, bead(arc), col)
    return out


def beat(outline, height, colours=(RUST, CREAM), ratio=1.18):
    """X courses at the base pitch, Y courses at pitch*ratio: large-scale moiré bands from spacing alone."""
    out = []
    for i in range(n_courses(height)):
        pitch = ROD["pitch"] * (1 if i % 2 == 0 else ratio)
        for _, pts in course(zc(i), (i % 2) * math.pi / 2, outline, pitch=pitch):
            _add(out, straight(pts[0], pts[-1]), colours[i % 2])
    return out


def ombre(outline, height, colours=(RUST, CREAM)):
    """Rods thin out going up on a FIXED grid (every rod, every 2nd, every 4th + slimmer bead). Free-pitch
    versions lose alignment and read as noise — keep the grid nested so every rod sits on supports."""
    out = []; N = n_courses(height)
    for i in range(N):
        f = i / max(N - 1, 1); level = 0 if f < 0.34 else (1 if f < 0.67 else 2)
        for _, pts in course(zc(i), (i % 2) * math.pi / 2, outline, keep=lambda j, L=level: j % (2 ** L) == 0):
            _add(out, straight(pts[0], pts[-1], rw=ROD["rw"] * (1 - 0.25 * level)), colours[i % 2])
    return out


def overunder(outline, height, colours=(RUST, CREAM)):
    """TRUE over-under weave: X and Y rods share a 2-course band and undulate in Z so each passes over then under
    the other. Supported at every crossing (one of the two is always 'over' at the band top). Costs a swap per
    LAYER in two colours — use one colour, or colour by zone, for sane swap counts."""
    out = []; rh = ROD["rh"]; p = ROD["pitch"]; A = rh / 2; rw = ROD["rw"]
    ext = outline.extent; n = int(math.ceil(ext / 2 / p)) + 1
    for b in range(n_courses(height) // 2):
        zb = b * 2 * rh + rh
        for j in range(-n, n + 1):
            c = j * p; s = 1 if j % 2 == 0 else -1
            xs = np.arange(-ext / 2, ext / 2 + 0.6, 0.6)
            for run in clip_runs(np.stack([xs, np.full_like(xs, c)], axis=1), outline.sdf):
                _add(out, bead(np.column_stack([run, zb + A * s * np.cos(np.pi * run[:, 0] / p)])), colours[0])
        for k in range(-n, n + 1):
            c = k * p; t = 1 if k % 2 == 0 else -1
            ys = np.arange(-ext / 2, ext / 2 + 0.6, 0.6)
            for run in clip_runs(np.stack([np.full_like(ys, c), ys], axis=1), outline.sdf):
                _add(out, bead(np.column_stack([run, zb - A * t * np.cos(np.pi * run[:, 1] / p)])), colours[1])
    return out


def tartan(outline, height, colours=(RUST, CREAM), seq_x=(3, 1), seq_y=(2, 2)):
    """Colour runs along both axes (seq = (n_colour0, n_colour1)) -> plaid on every face. Colours mix inside a
    course, so it costs a swap per layer; thicker courses (rod_layers 8) halve that."""
    out = []
    for i in range(n_courses(height)):
        seq = seq_x if i % 2 == 0 else seq_y; period = sum(seq)
        for j, pts in course(zc(i), (i % 2) * math.pi / 2, outline):
            _add(out, straight(pts[0], pts[-1]), colours[0] if (j % period) < seq[0] else colours[1])
    return out


PATTERNS = {"grid": grid, "kagome": kagome, "helix": helix, "polar": polar, "ripple": ripple,
            "selvedge": selvedge, "beat": beat, "ombre": ombre, "overunder": overunder, "tartan": tartan}
# Collin's keepers after the Oct 2026 render review: kagome, polar, ripple, selvedge, beat, overunder, tartan.
SWAP_COST = {"grid": "per course", "kagome": "per course", "helix": "per course", "polar": "per course",
             "ripple": "per course", "selvedge": "per course", "beat": "per course", "ombre": "per course",
             "overunder": "per LAYER (2 colours)", "tartan": "per LAYER (2 colours)"}


# ── the tray / platter family (woven_tray_v1.py / v2.py distilled) ────────────
def block(size=117.0, height=33.0, floor_t=10.4, corner_r=20.0, dip_d=94.0, ease_top_r=6.0, twill_skip=4,
          colours=(RUST, CREAM)):
    """Rounded-square block of straight-weave beads with a spherical dish dipped in, a pillowed top edge and a flat
    full-size bottom. Floor-top and top course are forced to colour 0. Returns (mesh_colour0, mesh_colour1)."""
    rh = ROD["rh"]; rw = ROD["rw"]
    n_floor = max(1, round(floor_t / rh)); n_floor += (n_floor - 1) % 2
    N = max(n_floor + 2, round(height / rh)); N += (N - 1) % 2
    H = N * rh; depth = (N - n_floor) * rh
    Rs = ((dip_d / 2) ** 2 + depth ** 2) / (2 * depth)
    outline = RoundedSquare(size, corner_r)
    def dip_r(z):
        h = z - (H - depth)
        return 0.0 if h <= 0 else math.sqrt(max(Rs ** 2 - (Rs - h) ** 2, 0.0))
    def inset(z):
        d = H - z
        return 0.0 if (ease_top_r <= 0 or d >= ease_top_r) else ease_top_r - math.sqrt(max(ease_top_r ** 2 - (ease_top_r - d) ** 2, 0.0))
    parts = {0: [], 1: []}
    for i in range(N):
        axis = i % 2; z = zc(i); r = dip_r(z); same = i // 2
        tw = twill_skip and same % 2 == 1 and i != N - 1
        phase = (same // 2) % twill_skip if twill_skip else 0
        keep = (lambda j, ph=phase: (j + ph) % twill_skip != 0) if tw else None
        for j, pts in course(z, axis * math.pi / 2, outline, inset=inset(z), keep=keep):
            c = j * ROD["pitch"]
            half = math.sqrt(r * r - c * c) if abs(c) < r else 0.0
            a0, a1 = (pts[0][0], pts[-1][0]) if axis == 0 else (pts[0][1], pts[-1][1])
            pieces = [(a0, a1)] if half <= 0 else [(a0, -half), (half, a1)]
            for p0, p1 in pieces:
                if p1 - p0 >= rw:
                    A = [p0, c, z] if axis == 0 else [c, p0, z]; B = [p1, c, z] if axis == 0 else [c, p1, z]
                    m = straight(A, B)
                    if m is not None:
                        parts[axis].append(m)
    return trimesh.util.concatenate(parts[0]), trimesh.util.concatenate(parts[1])


# ── Bambu export + CLI slice ──────────────────────────────────────────────────
def rod_overrides():
    import bambu_3mf
    o = dict(bambu_3mf.DEFAULT_OVERRIDES)
    o.update({"layer_height": f"{ROD['layer_h']:.2f}", "initial_layer_print_height": f"{ROD['layer_h']:.2f}",
              "line_width": "0.42", "outer_wall_line_width": "0.42", "inner_wall_line_width": "0.42",
              "initial_layer_line_width": "0.42", "wall_loops": "4", "sparse_infill_density": "0%",
              "top_shell_layers": "0", "bottom_shell_layers": "0", "detect_thin_wall": "1", "enable_prime_tower": "1",
              "seam_position": "aligned", "elefant_foot_compensation": "0", "detect_overhang_wall": "1",
              "brim_type": "no_brim", "printable_area": ["0x0", "256x0", "256x256", "0x256"],
              "wipe_tower_x": ["216"], "wipe_tower_y": ["216"], "prime_tower_width": "30"})
    base = json.loads(bambu_3mf.BASE_SETTINGS.read_text())
    for k, v in {"overhang_3_4_speed": "60", "overhang_4_4_speed": "50", "overhang_totally_speed": "50",
                 "bridge_speed": "50", "outer_wall_speed": "100", "inner_wall_speed": "150", "initial_layer_speed": "35"}.items():
        o[k] = [v] * len(base[k]) if isinstance(base.get(k), list) else v
    return o


ROD_OVERRIDES = rod_overrides


def group_by_colour(rods):
    """[(mesh, colour)] -> [(part_name, mesh, slot)] with one watertight concatenated part per colour."""
    groups = {}
    for m, c in rods:
        groups.setdefault(c, []).append(m)
    parts = []
    for c, ms in groups.items():
        mesh = trimesh.util.concatenate(ms)
        parts.append((f"{ {1: 'rust', 2: 'cream', 3: 'gold'}[SLOT[c]] } rods", mesh, SLOT[c]))
    parts.sort(key=lambda p: p[2])
    return parts


def export_bambu(path, rods_or_parts, title="woven", position=(128, 128), colours=(RUST, CREAM, GOLD), stl=True):
    """One object, one part per colour, bambu_3mf project with the rod overrides. rods_or_parts = [(mesh, colour)]
    (grouped here) or [(name, mesh, slot)]. Also writes <stem>_<part>.stl beside the 3MF when stl=True."""
    import bambu_3mf
    parts = rods_or_parts if (rods_or_parts and len(rods_or_parts[0]) == 3) else group_by_colour(rods_or_parts)
    zmin = min(p[1].bounds[0][2] for p in parts)
    for _, m, _ in parts:
        if zmin < 0:
            m.apply_translation([0, 0, -zmin])
    n = max(p[2] for p in parts)
    path = pathlib.Path(path)
    if stl:
        for name, m, _ in parts:
            m.export(path.with_name(f"{path.stem}_{name.split()[0]}.stl"))
    bambu_3mf.write_3mf(str(path), [{"name": title, "position": position, "parts": parts}], title=title,
                        colours=tuple(colours[:n]), overrides=rod_overrides())
    return path


def slice_cli(p3mf, workdir):
    """Slice a project 3MF with the Bambu Studio CLI; returns {'time','grams','layers'} or {'error'}.
    The CLI ignores part->filament assignment (single-colour numbers); swaps are not counted."""
    workdir = pathlib.Path(workdir); workdir.mkdir(parents=True, exist_ok=True)
    out = workdir / "sliced.3mf"
    with open(workdir / "cli.log", "w") as log:
        subprocess.run([BAMBU, "--slice", "0", "--export-3mf", str(out.resolve()), str(pathlib.Path(p3mf).resolve())],
                       cwd=workdir, stdout=log, stderr=subprocess.STDOUT)
    res = json.loads((workdir / "result.json").read_text())
    if res.get("return_code") != 0:
        return {"error": res.get("error_string"), "warning": str(res.get("sliced_plates", [{}])[0].get("warning_message", ""))[:200]}
    g = zipfile.ZipFile(out).read("Metadata/plate_1.gcode").decode(errors="ignore")
    return {"time": re.search(r"; model printing time: ([^;]+);", g).group(1).strip(),
            "grams": float(re.search(r"; total filament weight \[g\] : ([\d.]+)", g).group(1)),
            "layers": int(re.search(r"; total layer number: (\d+)", g).group(1))}
