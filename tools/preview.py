"""Headless STL -> PNG preview renderer for text2print.

Usage:
    python3 tools/preview.py model.stl [out.png] [--views iso|multi]
                             [--title T] [--subtitle S]
                             [--resolution N] [--strict]

Renders offscreen via pyrender (no display server needed) and composes
a labelled multi-view sheet with PIL. With --strict, a non-watertight
mesh exits with code 2 so callers can gate on it.
"""
import argparse
import os
import platform
import sys

# On headless Linux, pyrender needs EGL before it is imported.
if platform.system() == "Linux" and not os.environ.get("DISPLAY"):
    os.environ.setdefault("PYOPENGL_PLATFORM", "egl")

import numpy as np
import trimesh
import pyrender
from PIL import Image, ImageDraw, ImageFont

BG = (245, 242, 238)
INK = (60, 56, 50)
FAINT = (150, 144, 136)


def _look_at(eye, target, up=(0.0, 0.0, 1.0)):
    """Camera pose matrix looking from *eye* toward *target* (Z-up world)."""
    eye = np.asarray(eye, dtype=float)
    target = np.asarray(target, dtype=float)
    up = np.asarray(up, dtype=float)
    fwd = target - eye
    fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, up)
    if np.linalg.norm(right) < 1e-9:          # looking straight up/down
        right = np.cross(fwd, np.array([0.0, 1.0, 0.0]))
    right /= np.linalg.norm(right)
    true_up = np.cross(right, fwd)
    pose = np.eye(4)
    pose[:3, 0], pose[:3, 1], pose[:3, 2], pose[:3, 3] = right, true_up, -fwd, eye
    return pose


# view name -> unit eye direction (before distance scaling)
_VIEWS = {
    "Isometric":  (1.0, -1.0, 0.75),
    "Front":      (0.0, -1.0, 0.12),
    "Right":      (1.0, 0.0, 0.12),
    "Rear iso":   (-1.0, 1.0, 0.75),
    "Top":        (0.012, -0.012, 1.0),
    "Bottom":     (0.012, -0.012, -1.0),
}


def _render_view(tm, direction, resolution):
    """One framed render of *tm* from *direction*; returns a PIL image."""
    scene = pyrender.Scene(bg_color=[*BG, 255], ambient_light=[0.35] * 3)
    scene.add(pyrender.Mesh.from_trimesh(tm, smooth=False))

    center = tm.bounding_box.centroid
    radius = float(np.linalg.norm(tm.extents)) / 2.0
    fov = np.radians(38.0)
    dist = max(radius / np.tan(fov / 2) * 1.25, radius * 2.2)
    eye = center + np.asarray(direction, dtype=float) / \
        np.linalg.norm(direction) * dist

    cam_pose = _look_at(eye, center)
    scene.add(pyrender.PerspectiveCamera(yfov=fov), pose=cam_pose)
    scene.add(pyrender.DirectionalLight(color=np.ones(3), intensity=4.0),
              pose=cam_pose)

    renderer = pyrender.OffscreenRenderer(resolution, resolution)
    try:
        color, _ = renderer.render(scene)
    finally:
        renderer.delete()
    return Image.fromarray(color)


def _font(size):
    for name in ("Helvetica.ttc", "Arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _stats_line(tm, path):
    e = tm.extents
    wt = "watertight" if tm.is_watertight else "NOT WATERTIGHT"
    return (f"{os.path.basename(path)}   ·   "
            f"{e[0]:.1f} × {e[1]:.1f} × {e[2]:.1f} mm   ·   "
            f"{len(tm.faces):,} triangles   ·   {wt}")


def render_multi_view(tm, out_path, resolution=600, title=None, subtitle=None,
                      src_path=""):
    """Six labelled views on one sheet. Returns out_path."""
    names = list(_VIEWS)
    tiles = {n: _render_view(tm, _VIEWS[n], resolution) for n in names}

    pad, header, footer, label_h = 14, (64 if title or subtitle else 20), 44, 26
    cols, rows = 3, 2
    w = cols * resolution + (cols + 1) * pad
    h = header + rows * (resolution + label_h) + (rows + 1) * pad + footer
    sheet = Image.new("RGB", (w, h), BG)
    draw = ImageDraw.Draw(sheet)

    if title:
        draw.text((w // 2, 18), title, fill=INK, font=_font(22), anchor="mm")
    if subtitle:
        draw.text((w // 2, 44), subtitle, fill=FAINT, font=_font(14), anchor="mm")

    for i, name in enumerate(names):
        cx = pad + (i % cols) * (resolution + pad)
        cy = header + pad + (i // cols) * (resolution + label_h + pad)
        draw.text((cx + resolution // 2, cy + 8), name,
                  fill=FAINT, font=_font(13), anchor="mm")
        sheet.paste(tiles[name], (cx, cy + label_h - 8))

    draw.text((w // 2, h - footer // 2), _stats_line(tm, src_path),
              fill=FAINT, font=_font(13), anchor="mm")
    sheet.save(out_path)
    return out_path


def render_single(tm, out_path, resolution=900, src_path=""):
    """One isometric view with a stats footer. Returns out_path."""
    tile = _render_view(tm, _VIEWS["Isometric"], resolution)
    footer = 40
    sheet = Image.new("RGB", (resolution, resolution + footer), BG)
    sheet.paste(tile, (0, 0))
    draw = ImageDraw.Draw(sheet)
    draw.text((resolution // 2, resolution + footer // 2),
              _stats_line(tm, src_path), fill=FAINT, font=_font(13), anchor="mm")
    sheet.save(out_path)
    return out_path


def main(argv=None):
    parser = argparse.ArgumentParser(description="Render an STL preview sheet.")
    parser.add_argument("stl", help="input .stl file")
    parser.add_argument("out", nargs="?", default=None,
                        help="output .png (default: <stl>_preview.png)")
    parser.add_argument("--views", choices=("iso", "multi"), default="multi")
    parser.add_argument("--title", default=None)
    parser.add_argument("--subtitle", default=None)
    parser.add_argument("--resolution", type=int, default=600,
                        help="pixels per view tile (default 600)")
    parser.add_argument("--strict", action="store_true",
                        help="exit 2 if the mesh is not watertight")
    args = parser.parse_args(argv)

    tm = trimesh.load(args.stl, force="mesh")
    if not isinstance(tm, trimesh.Trimesh) or len(tm.faces) == 0:
        print(f"error: no triangles in {args.stl}", file=sys.stderr)
        return 1

    out = args.out or os.path.splitext(args.stl)[0] + "_preview.png"
    if args.views == "multi":
        render_multi_view(tm, out, resolution=args.resolution,
                          title=args.title, subtitle=args.subtitle,
                          src_path=args.stl)
    else:
        render_single(tm, out, resolution=max(args.resolution, 700),
                      src_path=args.stl)

    e = tm.extents
    print(f"model      : {args.stl}")
    print(f"bounds     : {e[0]:.1f} x {e[1]:.1f} x {e[2]:.1f} mm")
    print(f"triangles  : {len(tm.faces):,}")
    print(f"watertight : {tm.is_watertight}")
    print(f"preview    : {out} ({os.path.getsize(out):,} bytes)")

    if args.strict and not tm.is_watertight:
        print("STRICT: mesh is not watertight", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
