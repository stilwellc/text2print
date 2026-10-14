"""Woven rod tray — 2-colour Bambu print.

A rounded-corner square block with a round dish dipped into it. Every print "course" is a set of parallel rods (one extrusion wide, `rod_layers` print layers tall);
consecutive courses run at 90 degrees, so the tray is a stacked cross-hatch lattice with open gaps
(the reference photo: rust rods along one axis, cream rods along the other, a brush fringe at the rim).
Each rod bridges `pitch` between the perpendicular rods beneath it — no supports anywhere.

Colour law: X-direction rods -> filament 1 (rust), Y-direction rods -> filament 2 (cream).
Output: woven_tray_rust.stl, woven_tray_cream.stl (print orientation, bed at Z=0), woven_tray_2color.3mf,
        woven_tray_render.png (coloured 4-view), woven_tray_layers.png (course map).
Run:  .venv/bin/python woven_tray.py
"""
import hashlib
import json
import math
import pathlib
import sys

import numpy as np
import trimesh

sys.path.insert(0, str(pathlib.Path(__file__).with_name("tools")))
import bambu_3mf  # noqa: E402

# ── PARAMETERS (mm) ────────────────────────────────────────────────────────────
size        = 120.0   # outer footprint of the walls (square); fringe adds beyond this
height      = 33.0    # overall height to the top course (rounded to whole courses, parity-corrected)
floor_t     = 10.0    # floor thickness (rounded to whole courses)
corner_r    = 20.0    # plan-view corner radius of the square block (rounded square, like the photo; 0 = sharp)
dip_d       = 94.0    # diameter of the round dip at the rim (walls at the thinnest = (size - dip_d)/2)
dip_shape   = "sphere"  # spherical-cap bowl: chord dip_d at the rim, depth = height - floor; shallow curve, flat-ish middle
layer_h     = 0.20    # slicer layer height — must match the Bambu process
rod_layers  = 4       # print layers per course (rod height = 0.80 mm; also = colour-swap cadence)
line_w      = 0.42    # slicer line width (0.4 nozzle)
rod_lines   = 4       # extrusion lines per rod (4 -> 1.68 mm wide rod, 4 wall loops side by side)
pitch       = 3.6     # rod centre-to-centre spacing; gap = pitch - rod_w = 1.92 mm bridges (trivial for PLA)
fringe_len  = 8.0     # how far the rim courses reach past the wall (brush fringe)
fringe_rows = 0       # top courses that carry the fringe
fringe_step = 1       # pitches the fringe grows per course (1 pitch = 2 mm cantilever per course, print-safe)
jitter      = 1.5     # random shortening of fringe rod ends, 0..jitter mm (hash-deterministic)
colour_rust = "#8B3A2F"
colour_cream = "#EDE3D1"
seed        = 7

rod_w = rod_lines * line_w
rod_h = rod_layers * layer_h
n_floor = max(1, round(floor_t / rod_h))
if (n_floor - 1) % 2 != 0:                           # the dish floor (top floor course) must be an X course = rust
    n_floor += 1
n_total = max(n_floor + 2, round(height / rod_h))
if (n_total - 1) % 2 != 0:                           # top course must be an X course (rust cap, as in the photo)
    n_total += 1
height = n_total * rod_h
n_across = int(math.floor((size - rod_w) / pitch)) + 1   # rods per full course
span = (n_across - 1) * pitch + rod_w                     # actual footprint
margin = (size - span) / 2.0
# print orientation: bed at Z=0, floor courses first; the fringe grows outward one pitch per course.
# seam: every rod is one closed loop; seam lands at a rod end (edge-on, invisible).

def _jit(*key):
    h = hashlib.sha1(("%d:" % seed + ":".join(map(str, key))).encode()).digest()
    return int.from_bytes(h[:4], "big") / 2**32


_R_X = np.array([[0, 0, 1, 0], [1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 1]], float)   # capsule Z -> world X, Y -> Z
_R_Y = np.array([[-1, 0, 0, 0], [0, 0, 1, 0], [0, 1, 0, 0], [0, 0, 0, 1]], float)  # capsule Z -> world Y, Y -> Z


def rod(a0, a1, b0, b1, z0, z1, axis):
    """One rod as a rounded bead: elliptical cross-section (rod_w wide, rod_h tall) with rounded ends.
    No right angles anywhere — the slicer follows the curve, so every course prints as soft beads."""
    length = max(a1 - a0, rod_w)
    m = trimesh.creation.capsule(height=length - rod_w, radius=rod_w / 2.0, count=[12, 8])
    m.apply_translation(-m.bounding_box.centroid)                       # centre the capsule on its axis
    m.apply_transform(np.diag([1.0, rod_h / rod_w, 1.0, 1.0]))          # squash the vertical to rod_h
    m.apply_transform(_R_X if axis == 0 else _R_Y)
    ca, cb, cz = (a0 + a1) / 2.0, (b0 + b1) / 2.0, (z0 + z1) / 2.0
    m.apply_translation([ca, cb, cz] if axis == 0 else [cb, ca, cz])
    return m


dip_depth = (n_total - n_floor) * rod_h
dip_R = ((dip_d / 2.0) ** 2 + dip_depth ** 2) / (2.0 * dip_depth)   # sphere radius through rim chord + bottom


def dip_radius(z_mid):
    """Radius of the spherical dip at height z (centre of a course); the dip only widens going up => no overhangs."""
    h = z_mid - (height - dip_depth)                 # height above the bottom of the dip
    if h <= 0.0:
        return 0.0
    return math.sqrt(max(dip_R ** 2 - (dip_R - h) ** 2, 0.0))


def outline_half(c, cx):
    """Half-length of a rod at across-position c for the rounded-square outline (centre cx)."""
    half = span / 2.0
    u = abs(c - cx)
    if corner_r <= 0 or u <= half - corner_r:
        return half
    du = u - (half - corner_r)
    return half - corner_r + math.sqrt(max(corner_r ** 2 - du ** 2, 0.0))


def course_rods(i):
    """Return list of (a0, a1, b0, b1, z0, z1, axis) for course i; axis 0 = rods run along X."""
    axis = i % 2
    z0, z1 = i * rod_h, (i + 1) * rod_h
    ext = 0.0
    if i >= n_total - fringe_rows:
        k = i - (n_total - fringe_rows) + 1
        ext = min(fringe_len, k * fringe_step * pitch)
    lo = margin                      # inner bound of the lattice footprint
    hi = margin + span
    rods = []
    pos = [lo + rod_w / 2 + j * pitch for j in range(n_across)]   # rod centrelines (across)
    r = dip_radius((z0 + z1) / 2.0)
    cx = lo + span / 2.0
    for c in pos:
        e0 = ext * (1.0 - jitter / max(fringe_len, 1e-9) * _jit(i, c, 0)) if ext else 0.0
        e1 = ext * (1.0 - jitter / max(fringe_len, 1e-9) * _jit(i, c, 1)) if ext else 0.0
        oh = outline_half(c, cx)                             # rounded-square outline clips the rod ends
        lo_c, hi_c = cx - oh, cx + oh
        half = math.sqrt(r * r - (c - cx) ** 2) if abs(c - cx) < r else 0.0
        if half <= 0.0:                                      # rod clears the dip: full length
            rods.append((lo_c - e0, hi_c + e1, c - rod_w / 2, c + rod_w / 2, z0, z1, axis))
        else:                                                # rod split by the round dip, stepped ends
            for a0, a1 in ((lo_c - e0, cx - half), (cx + half, hi_c + e1)):
                if a1 - a0 >= rod_w:                          # drop sub-rod-width stubs
                    rods.append((a0, a1, c - rod_w / 2, c + rod_w / 2, z0, z1, axis))
    # courses above the floor also need the fringe to extend sideways (perpendicular to the rods):
    if ext:
        extra = []
        # rods beyond the wall footprint in the "across" direction (so the fringe ring is a full lattice)
        n_ext = int(ext // pitch)
        for j in range(1, n_ext + 1):
            for side in (-1, 1):
                c = (lo + rod_w / 2 - j * pitch) if side < 0 else (hi - rod_w / 2 + j * pitch)
                e0 = ext * (1.0 - jitter / max(fringe_len, 1e-9) * _jit(i, c, 0))
                e1 = ext * (1.0 - jitter / max(fringe_len, 1e-9) * _jit(i, c, 1))
                extra.append((lo - e0, hi + e1, c - rod_w / 2, c + rod_w / 2, z0, z1, axis))
        rods += extra
    return rods


def build():
    parts = {0: [], 1: []}
    n_rods = 0
    for i in range(n_total):
        for a0, a1, b0, b1, z0, z1, axis in course_rods(i):
            parts[axis].append(rod(a0, a1, b0, b1, z0, z1, axis))
            n_rods += 1
    rust = trimesh.util.concatenate(parts[0]); cream = trimesh.util.concatenate(parts[1])
    c = margin + span / 2.0                      # centre the lattice on XY=0 (bambu_3mf places by centre)
    for m in (rust, cream):
        m.apply_translation([-c, -c, 0.0])
    return rust, cream, n_rods


def render(rust, cream, path):
    import pyrender
    from PIL import Image, ImageDraw
    sys.path.insert(0, "tools"); import preview as pv
    views = [("Isometric", (1.0, -1.0, 0.75)), ("Front", (0.0, -1.0, 0.18)),
             ("Top", (0.012, -0.012, 1.0)), ("Rim close-up", (1.0, -0.6, 0.45))]
    both = trimesh.util.concatenate([rust, cream])
    center = both.bounding_box.centroid; radius = float(np.linalg.norm(both.extents)) / 2
    tiles = []
    for name, d in views:
        scene = pyrender.Scene(bg_color=[245, 242, 238, 255], ambient_light=[0.45] * 3)
        for m, col in ((rust, colour_rust), (cream, colour_cream)):
            rgb = [(int(col[k:k + 2], 16) / 255) ** 2.2 for k in (1, 3, 5)]
            mat = pyrender.MetallicRoughnessMaterial(baseColorFactor=rgb + [1.0], metallicFactor=0.0, roughnessFactor=0.8)
            scene.add(pyrender.Mesh.from_trimesh(m, material=mat, smooth=False))
        fov = np.radians(38.0)
        dist = max(radius / np.tan(fov / 2) * 1.25, radius * 2.2)
        if name == "Rim close-up":
            dist *= 0.45; tgt = center + np.array([span * 0.3, -span * 0.3, 0])
        else:
            tgt = center
        eye = tgt + np.asarray(d) / np.linalg.norm(d) * dist
        pose = pv._look_at(eye, tgt)
        scene.add(pyrender.PerspectiveCamera(yfov=fov), pose=pose)
        scene.add(pyrender.DirectionalLight(color=np.ones(3), intensity=3.5), pose=pose)
        r = pyrender.OffscreenRenderer(900, 900)
        try:
            colr, _ = r.render(scene)
        finally:
            r.delete()
        im = Image.fromarray(colr); ImageDraw.Draw(im).text((16, 12), name, fill=(60, 56, 50))
        tiles.append(im)
    sheet = Image.new("RGB", (1800, 1800), (245, 242, 238))
    for k, t in enumerate(tiles):
        sheet.paste(t, ((k % 2) * 900, (k // 2) * 900))
    sheet.save(path)


def course_map(path):
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axs = plt.subplots(1, 3, figsize=(15, 5))
    for ax, i, label in zip(axs, (0, n_floor + 2, n_total - 1), ("floor course 0", f"dip course {n_floor + 2}", f"top course {n_total-1} (fringe)")):
        for a0, a1, b0, b1, _, _, axis in course_rods(i):
            col = colour_rust if axis == 0 else colour_cream
            if axis == 0:
                ax.add_patch(plt.Rectangle((a0, b0), a1 - a0, b1 - b0, color=col))
            else:
                ax.add_patch(plt.Rectangle((b0, a0), b1 - b0, a1 - a0, color=col))
        ax.set_xlim(-10, size + 10); ax.set_ylim(-10, size + 10); ax.set_aspect("equal"); ax.set_title(label)
        ax.set_facecolor("#555")
    fig.savefig(path, dpi=110, bbox_inches="tight")


if __name__ == "__main__":
    rust, cream, n_rods = build()
    for m, nm in ((rust, "rust"), (cream, "cream")):
        assert m.is_watertight, nm
        m.export(f"woven_tray_{nm}.stl")
    both = trimesh.util.concatenate([rust, cream])
    print(f"courses {n_total} (floor {n_floor}), rods {n_rods}, faces {len(both.faces)}, "
          f"bbox {both.extents.round(2)}, rod {rod_w:.2f}x{rod_h:.2f}, pitch {pitch}, dip {dip_d} deep {dip_depth:.1f} R {dip_R:.1f}")
    render(rust, cream, "woven_tray_render.png")
    course_map("woven_tray_layers.png")
    overrides = dict(bambu_3mf.DEFAULT_OVERRIDES)
    overrides.update({
        "layer_height": f"{layer_h:.2f}", "initial_layer_print_height": f"{layer_h:.2f}",
        "line_width": f"{line_w:.2f}", "outer_wall_line_width": f"{line_w:.2f}", "inner_wall_line_width": f"{line_w:.2f}",
        "initial_layer_line_width": f"{line_w:.2f}",
        "wall_loops": str(rod_lines), "sparse_infill_density": "0%", "top_shell_layers": "0", "bottom_shell_layers": "0",
        "detect_thin_wall": "1", "enable_prime_tower": "1", "seam_position": "aligned",
        "elefant_foot_compensation": "0", "detect_overhang_wall": "1", "brim_type": "no_brim",
    })
    # speeds: every rod span is a 1.74 mm bridge between crossings, so the stock 10 mm/s overhang crawl is
    # pointless (it was 9h25 single-colour); 50 mm/s (Bambu's own bridge default) bridges that trivially. Keys are per-extruder lists in the
    # base config, so write lists of the same length.
    import json as _json
    base = _json.loads(bambu_3mf.BASE_SETTINGS.read_text())
    for k, v in {"overhang_3_4_speed": "60", "overhang_4_4_speed": "50", "overhang_totally_speed": "50",
                 "bridge_speed": "50", "outer_wall_speed": "100", "inner_wall_speed": "150",
                 "initial_layer_speed": "35"}.items():
        overrides[k] = [v] * len(base[k]) if isinstance(base.get(k), list) else v
    bambu_3mf.write_3mf("woven_tray_2color.3mf", [
        {"name": "woven tray", "position": (128, 128),
         "parts": [("rust rods (X)", rust, 1), ("cream rods (Y)", cream, 2)]},
    ], title="woven tray", colours=(colour_rust, colour_cream), overrides=overrides)
    json.dump({"courses": n_total, "floor_courses": n_floor, "rods": n_rods, "height": height,
               "span": span, "dip_d": dip_d, "fringe": fringe_len, "rod_w": rod_w, "rod_h": rod_h}, open("woven_tray_meta.json", "w"), indent=1)
    print("wrote woven_tray_2color.3mf")
