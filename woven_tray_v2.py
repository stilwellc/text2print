"""Woven rod platter v2 — 2-colour Bambu print. Soft everywhere, nothing square.

A rounded-corner square block of stacked round rods with a round dish dipped in. v2 adds:
  * pillowed top and bottom edges (the outline shrinks over the last courses — soap-bar / river-stone profile;
    the bottom ease doubles as the float: the block stands on a smaller contact patch with a shadow gap)
  * the weave runs at 45 degrees to the block, so rod ends step along all four sides
  * a twill rhythm: on alternate courses of each axis every third rod is skipped, the gap column drifting one
    rod every repeat so a faint diagonal runs across the walls and the dish floor
  * platter proportions: 160 wide, ~25 tall, 130 dish
Every rod is a rounded bead (elliptical section, rounded ends). X rods -> filament 1 (rust), Y -> 2 (cream).
Output: woven_platter_rust.stl, woven_platter_cream.stl (print orientation, Z >= 0), woven_platter_2color.3mf,
        woven_platter_render.png, woven_platter_layers.png.   Run:  .venv/bin/python woven_tray_v2.py
"""
import json
import math
import pathlib
import sys

import numpy as np
import trimesh

sys.path.insert(0, str(pathlib.Path(__file__).with_name("tools")))
import bambu_3mf  # noqa: E402

# ── PARAMETERS (mm) ────────────────────────────────────────────────────────────
size        = 160.0   # block footprint (square, axis-aligned on the bed)
height      = 24.0    # overall height (rounded to whole courses, parity-corrected: top course is rust)
floor_t     = 5.6     # floor under the dish (whole courses; floor top forced to a rust course)
corner_r    = 28.0    # plan corner radius of the block
dip_d       = 130.0   # dish diameter at the rim; spherical, depth = height - floor
ease_top_r  = 6.0     # pillow radius of the top edge (outline shrinks over the top courses, quarter circle)
ease_bot_r  = 0.0     # bottom edge straight: full footprint on the bed, no outward steps (Collin: flat print, no overhangs)
weave_deg   = 0.0     # rod direction relative to the block (0 = straight weave; 45 = diagonal, dropped by Collin)
twill_skip  = 4       # on alternate courses of each axis skip every Nth rod (0 = off); the gap drifts 1 rod per repeat
layer_h     = 0.20    # slicer layer height — must match the Bambu process
rod_layers  = 4       # print layers per course (rod height 0.80; also = colour-swap cadence)
line_w      = 0.42    # slicer line width (0.4 nozzle)
rod_lines   = 4       # extrusion widths per rod -> 1.68 mm wide bead
pitch       = 3.6     # rod centre-to-centre spacing; gap 1.92 mm (bridges are trivial for PLA)
colour_rust = "#8B3A2F"
colour_cream = "#EDE3D1"

rod_w = rod_lines * line_w
rod_h = rod_layers * layer_h
n_floor = max(1, round(floor_t / rod_h))
if (n_floor - 1) % 2 != 0:                       # dish floor (top floor course) must be an X course = rust
    n_floor += 1
n_total = max(n_floor + 2, round(height / rod_h))
if (n_total - 1) % 2 != 0:                       # top course must be an X course (rust cap)
    n_total += 1
height = n_total * rod_h
dip_depth = (n_total - n_floor) * rod_h
dip_R = ((dip_d / 2.0) ** 2 + dip_depth ** 2) / (2.0 * dip_depth)
ext = size * (abs(math.cos(math.radians(weave_deg))) + abs(math.sin(math.radians(weave_deg)))) + 2 * pitch
n_across = int(math.floor(ext / pitch)) + 1
# print orientation: bed at Z=0. Every course is narrower than the one below it at the top ease (no overhang);
# the bottom is flat and full-size, so no course ever reaches past the one beneath it.
# seam: aligned, lands at rod ends.


def ease_inset(z_mid):
    """How far the outline is pulled in at height z: quarter-circle pillows at the bottom and top edges."""
    ins = 0.0
    if ease_bot_r > 0 and z_mid < ease_bot_r:
        ins = max(ins, ease_bot_r - math.sqrt(max(ease_bot_r ** 2 - (ease_bot_r - z_mid) ** 2, 0.0)))
    d = height - z_mid
    if ease_top_r > 0 and d < ease_top_r:
        ins = max(ins, ease_top_r - math.sqrt(max(ease_top_r ** 2 - (ease_top_r - d) ** 2, 0.0)))
    return ins


def block_sdf(px, py, inset):
    """Signed distance to the rounded-square block outline (block frame), shrunk by `inset`."""
    half = size / 2.0 - inset
    r = min(corner_r, half)
    bx = by = half - r
    qx, qy = abs(px) - bx, abs(py) - by
    outside = math.hypot(max(qx, 0.0), max(qy, 0.0))
    inside = min(max(qx, qy), 0.0)
    return outside + inside - r


def dip_radius(z_mid):
    h = z_mid - (height - dip_depth)
    if h <= 0.0:
        return 0.0
    return math.sqrt(max(dip_R ** 2 - (dip_R - h) ** 2, 0.0))


_cw, _sw = math.cos(math.radians(weave_deg)), math.sin(math.radians(weave_deg))


def to_block(x, y):
    """Lattice frame -> block frame (the block is rotated by weave_deg in the lattice frame)."""
    return _cw * x + _sw * y, -_sw * x + _cw * y


def outline_interval(c, axis, inset):
    """[t0, t1] along a rod (lattice axis `axis`, across-position c) inside the block outline, or None."""
    def f(t):
        x, y = (t, c) if axis == 0 else (c, t)
        return block_sdf(*to_block(x, y), inset)
    # the outline is convex: march out from the centre line until outside, then bisect
    tmax = ext / 2.0
    ts = np.arange(-tmax, tmax + 0.5, 0.5)
    inside = [f(t) <= 0 for t in ts]
    if not any(inside):
        return None
    i0 = inside.index(True); i1 = len(inside) - 1 - inside[::-1].index(True)
    def bisect(ta, tb):              # f(ta) > 0, f(tb) <= 0
        for _ in range(20):
            tm = (ta + tb) / 2.0
            if f(tm) <= 0: tb = tm
            else: ta = tm
        return tb
    t0 = bisect(ts[i0 - 1], ts[i0]) if i0 > 0 else ts[i0]
    t1 = bisect(ts[i1 + 1], ts[i1]) if i1 < len(ts) - 1 else ts[i1]
    return t0, t1


_R_X = np.array([[0, 0, 1, 0], [1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 1]], float)
_R_Y = np.array([[-1, 0, 0, 0], [0, 0, 1, 0], [0, 1, 0, 0], [0, 0, 0, 1]], float)


def rod(a0, a1, c, z0, z1, axis):
    """One rod as a rounded bead: elliptical cross-section with rounded ends, in the lattice frame."""
    length = max(a1 - a0, rod_w)
    m = trimesh.creation.capsule(height=length - rod_w, radius=rod_w / 2.0, count=[12, 8])
    m.apply_translation(-m.bounding_box.centroid)
    m.apply_transform(np.diag([1.0, rod_h / rod_w, 1.0, 1.0]))
    m.apply_transform(_R_X if axis == 0 else _R_Y)
    ca, cz = (a0 + a1) / 2.0, (z0 + z1) / 2.0
    m.apply_translation([ca, c, cz] if axis == 0 else [c, ca, cz])
    return m


def course_rods(i):
    """(a0, a1, c, z0, z1, axis) for course i in the lattice frame; axis 0 = rods along lattice X."""
    axis = i % 2
    z0, z1 = i * rod_h, (i + 1) * rod_h
    zm = (z0 + z1) / 2.0
    inset = ease_inset(zm)
    r = dip_radius(zm)
    same_axis_idx = i // 2                      # 0,1,2,... counting courses of this axis
    twill_course = twill_skip and (same_axis_idx % 2 == 1) and i != n_total - 1   # never the visible top course
    phase = (same_axis_idx // 2) % twill_skip if twill_skip else 0
    rods = []
    for j in range(n_across):
        if twill_course and (j + phase) % twill_skip == 0:
            continue
        c = (j - (n_across - 1) / 2.0) * pitch
        iv = outline_interval(c, axis, inset)
        if iv is None:
            continue
        t0, t1 = iv
        half = math.sqrt(r * r - c * c) if abs(c) < r else 0.0     # dish is centred, rotation-invariant
        pieces = [(t0, t1)] if half <= 0.0 else [(t0, -half), (half, t1)]
        for a0, a1 in pieces:
            if a1 - a0 >= rod_w:
                rods.append((a0, a1, c, z0, z1, axis))
    return rods


def build():
    parts = {0: [], 1: []}
    n = 0
    for i in range(n_total):
        for a0, a1, c, z0, z1, axis in course_rods(i):
            parts[axis].append(rod(a0, a1, c, z0, z1, axis)); n += 1
    rust = trimesh.util.concatenate(parts[0]); cream = trimesh.util.concatenate(parts[1])
    rot = trimesh.transformations.rotation_matrix(math.radians(-weave_deg), [0, 0, 1])   # block axis-aligned on bed
    for m in (rust, cream):
        m.apply_transform(rot)
    return rust, cream, n


def render(rust, cream, path):
    import pyrender
    from PIL import Image, ImageDraw
    import preview as pv
    views = [("Isometric", (1.0, -1.0, 0.75)), ("Front", (0.0, -1.0, 0.18)),
             ("Top", (0.012, -0.012, 1.0)), ("Edge close-up", (1.0, -0.6, 0.45))]
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
        tgt = center
        if name == "Edge close-up":
            dist *= 0.45; tgt = center + np.array([size * 0.3, -size * 0.3, 0])
        eye = tgt + np.asarray(d) / np.linalg.norm(d) * dist
        pose = pv._look_at(eye, tgt)
        scene.add(pyrender.PerspectiveCamera(yfov=fov), pose=pose)
        scene.add(pyrender.DirectionalLight(color=np.ones(3), intensity=3.5), pose=pose)
        rr = pyrender.OffscreenRenderer(900, 900)
        try:
            colr, _ = rr.render(scene)
        finally:
            rr.delete()
        im = Image.fromarray(colr); ImageDraw.Draw(im).text((16, 12), name, fill=(60, 56, 50)); tiles.append(im)
    sheet = Image.new("RGB", (1800, 1800), (245, 242, 238))
    for k, t in enumerate(tiles):
        sheet.paste(t, ((k % 2) * 900, (k // 2) * 900))
    sheet.save(path)


def course_map(path):
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon
    fig, axs = plt.subplots(1, 4, figsize=(20, 5))
    picks = (0, 3, n_floor + 3, n_total - 1)
    labels = ("course 0 (bottom ease)", "course 3", f"course {n_floor + 3} (dish)", f"top course {n_total - 1} (top ease)")
    rot = np.array([[_cw, _sw], [-_sw, _cw]]).T   # lattice -> bed (rotate by -weave)
    rot = np.array([[math.cos(math.radians(-weave_deg)), -math.sin(math.radians(-weave_deg))],
                    [math.sin(math.radians(-weave_deg)), math.cos(math.radians(-weave_deg))]])
    for ax, i, lab in zip(axs, picks, labels):
        for a0, a1, c, _, _, axis in course_rods(i):
            if axis == 0:
                quad = np.array([[a0, c - rod_w / 2], [a1, c - rod_w / 2], [a1, c + rod_w / 2], [a0, c + rod_w / 2]])
            else:
                quad = np.array([[c - rod_w / 2, a0], [c + rod_w / 2, a0], [c + rod_w / 2, a1], [c - rod_w / 2, a1]])
            ax.add_patch(Polygon(quad @ rot.T, closed=True, color=colour_rust if axis == 0 else colour_cream))
        ax.set_xlim(-size / 2 - 5, size / 2 + 5); ax.set_ylim(-size / 2 - 5, size / 2 + 5)
        ax.set_aspect("equal"); ax.set_title(lab); ax.set_facecolor("#555")
    fig.savefig(path, dpi=100, bbox_inches="tight")


if __name__ == "__main__":
    rust, cream, n_rods = build()
    for m, nm in ((rust, "rust"), (cream, "cream")):
        assert m.is_watertight, nm
        m.export(f"woven_platter_{nm}.stl")
    both = trimesh.util.concatenate([rust, cream])
    print(f"courses {n_total} (floor {n_floor}), rods {n_rods}, faces {len(both.faces)}, bbox {both.extents.round(2)}, "
          f"rod {rod_w:.2f}x{rod_h:.2f}, pitch {pitch}, dip {dip_d} deep {dip_depth:.1f} R {dip_R:.1f}, "
          f"contact patch ~{size - 2 * ease_inset(rod_h / 2):.0f}")
    render(rust, cream, "woven_platter_render.png")
    course_map("woven_platter_layers.png")
    overrides = dict(bambu_3mf.DEFAULT_OVERRIDES)
    overrides.update({
        "layer_height": f"{layer_h:.2f}", "initial_layer_print_height": f"{layer_h:.2f}",
        "line_width": f"{line_w:.2f}", "outer_wall_line_width": f"{line_w:.2f}", "inner_wall_line_width": f"{line_w:.2f}",
        "initial_layer_line_width": f"{line_w:.2f}",
        "wall_loops": str(rod_lines), "sparse_infill_density": "0%", "top_shell_layers": "0", "bottom_shell_layers": "0",
        "detect_thin_wall": "1", "enable_prime_tower": "1", "seam_position": "aligned",
        "elefant_foot_compensation": "0", "detect_overhang_wall": "1", "brim_type": "no_brim",
        # the base config carries a 200x200 printable area and a prime tower at plate centre; a 160 mm platter
        # needs the real P2S bed and the tower parked in the back-right corner
        "printable_area": ["0x0", "256x0", "256x256", "0x256"], "wipe_tower_x": ["216"], "wipe_tower_y": ["216"],
        "prime_tower_width": "30",
    })
    base = json.loads(bambu_3mf.BASE_SETTINGS.read_text())
    for k, v in {"overhang_3_4_speed": "60", "overhang_4_4_speed": "50", "overhang_totally_speed": "50",
                 "bridge_speed": "50", "outer_wall_speed": "100", "inner_wall_speed": "150",
                 "initial_layer_speed": "35"}.items():
        overrides[k] = [v] * len(base[k]) if isinstance(base.get(k), list) else v
    bambu_3mf.write_3mf("woven_platter_2color.3mf", [
        {"name": "woven platter", "position": (118, 118),
         "parts": [("rust rods", rust, 1), ("cream rods", cream, 2)]},
    ], title="woven platter", colours=(colour_rust, colour_cream), overrides=overrides)
    json.dump({"courses": n_total, "floor_courses": n_floor, "rods": n_rods, "height": height, "size": size,
               "dip_d": dip_d, "dip_depth": dip_depth, "weave_deg": weave_deg, "twill_skip": twill_skip,
               "ease_top_r": ease_top_r, "ease_bot_r": ease_bot_r}, open("woven_platter_meta.json", "w"), indent=1)
    print("wrote woven_platter_2color.3mf")
