"""Render the README's motion GIFs from real builds.  .venv/bin/python docs/make_motion.py [print-build] [droop]

print-build  a woven piece growing course by course, as the printer lays it, under a slow orbit.
droop        strands leaving the wall flat (as the printer lays them), then swinging down as gravity hangs them.
             The motion is the same per-strand swing the studio's "After droop" preview applies (droop.drape),
             run from 0 to its final angle."""
import math
import pathlib
import sys

import numpy as np
import trimesh
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from text2print import design as D, droop, printer          # noqa: E402
from text2print.render import GROUND, render                  # noqa: E402
from text2print.shapes import SHAPES                          # noqa: E402

OUT = pathlib.Path(__file__).resolve().parent / "media"
FONT = "/System/Library/Fonts/HelveticaNeue.ttc"
INK = (110, 100, 85)


def _ease(t):
    return 0.5 - 0.5 * math.cos(math.pi * min(max(t, 0.0), 1.0))


def _clean(im):
    """Snap near-ground pixels to the exact ground so frames never flicker or show a tile edge."""
    a = np.asarray(im.convert("RGB")).astype(np.int16)
    a[np.abs(a - np.array(GROUND)).max(-1) <= 6] = GROUND
    return Image.fromarray(a.astype(np.uint8))


def _save_gif(frames, durations, path, colours=128):
    """One shared palette built from a strip of sample frames, no dithering (keeps the ground flat)."""
    k = min(6, len(frames)); idx = np.linspace(0, len(frames) - 1, k).astype(int)
    w, h = frames[0].size
    strip = Image.new("RGB", (w * k, h + 24), GROUND)
    for j, i in enumerate(idx):
        strip.paste(frames[i], (w * j, 0))
    strip.paste(Image.new("RGB", (w * k, 24), INK), (0, h))          # keep the caption ink exact in the palette
    pal = strip.quantize(colors=colours, method=Image.Quantize.MEDIANCUT)
    q = [f.quantize(palette=pal, dither=Image.Dither.NONE) for f in frames]
    q[0].save(path, save_all=True, append_images=q[1:], duration=durations, loop=0, optimize=True, disposal=1)
    print(f"{path.name}: {path.stat().st_size // 1024} KB, {len(frames)} frames, {sum(durations) / 1000:.1f}s", flush=True)


def _rod_floor(m):
    """Per face: the lowest z of the rod (connected piece) it belongs to, so a course appears whole as it is laid."""
    lab = trimesh.graph.connected_component_labels(m.face_adjacency, node_count=len(m.faces))
    fz = m.vertices[m.faces][:, :, 2].min(1)
    floor = np.full(lab.max() + 1, np.inf); np.minimum.at(floor, lab, fz)
    return floor[lab]


def _clip(m, floor, z):
    keep = floor < z
    if not keep.any():
        return None
    return trimesh.Trimesh(m.vertices, m.faces[keep], process=False)


CUP = {"shape": "cup", "texture": "grid", "nozzle": 0.8, "params": {"diameter": 80, "height": 80},
       "colours": ["#2E4E7E", "#EDE3D1"]}


def print_build(d=CUP, size=520, ss=3, build_frames=48, hold_ms=1600, elev=0.55, zoom=1.12):
    _, b = D.build_design(d)
    parts = D.view_of(b, hung=False)
    allv = np.vstack([m.vertices for m, _ in parts]); lo, hi = allv.min(0), allv.max(0)
    centre = (lo + hi) / 2; radius = float(np.linalg.norm(hi - lo)) / 2
    lh = printer.nozzle(d["nozzle"]).layer_h
    floors = [_rod_floor(m) for m, _ in parts]
    frames, durs = [], []
    n = build_frames
    for i in range(n + 1):
        t = i / n
        z = lo[2] + lh * 0.5 + (hi[2] - lo[2]) * t + (lh if i == n else 0)
        a = math.radians(-60 + 75 * _ease(t))                    # slow quarter orbit across the build
        shown = [(c, col) for c, col in ((_clip(m, f, z), col) for (m, col), f in zip(parts, floors)) if c is not None]
        im = render(shown, size=size * ss, view=(math.cos(a), math.sin(a), elev), zoom=zoom, target=centre,
                    radius=radius)
        frames.append(_clean(im.resize((size, size), Image.LANCZOS)))
        durs.append(hold_ms if i == n else (260 if i == 0 else 70))
    _save_gif(frames, durs, OUT / "print-build.gif")
    return frames


def _droop_scene(shape_key, style, params=None, nozzle=0.4, density="medium", length="medium"):
    """The wall, and each strand as laid with the swing that hangs it: (ribbon, axis, pivot, final angle)."""
    S = SHAPES[shape_key]; nz = printer.nozzle(nozzle); v = S.resolve(params or {})
    wall, prof, height, rmax, shell = droop.body(S, v, nz)
    spots = droop._rows(style, prof, height, nz, droop.DENSITY[density], droop.LENGTH[length])
    lh = nz.layer_h
    q = lambda z: (math.floor(z / lh) + 0.25) * lh
    spots = droop._never_touch(spots, prof, q)
    ribbons = [droop._ribbon(th, ch, bu, q(z), hh, w, prof, shell * 0.55, droop._SPEC[style]["power"], lean)
               for th, ch, bu, z, hh, lean, w in spots]
    lo_, hi_ = droop.HANG[style]; swings = []
    for k, ((th, ch, bu, z, hh, lean, w), rib) in enumerate(zip(spots, ribbons)):      # as droop.drape
        r_w = prof(q(z) + hh / 2)
        axis = np.array([-math.sin(th), math.cos(th), 0.0])
        pivot = np.array([r_w * math.cos(th), r_w * math.sin(th), q(z) + hh / 2])
        ang = math.radians(lo_ + (hi_ - lo_) * droop._h(11, "hang", k))
        z_a = q(z) + hh / 2; s_ = prof(max(z_a - 2.0, 0.0)) - prof(z_a)
        if s_ > 0:
            ang = min(ang, math.atan2(2.0, s_) - math.radians(4))
        R = trimesh.transformations.rotation_matrix(ang, axis, pivot)
        probe = trimesh.transform_points([pivot + [math.cos(th) * 5, math.sin(th) * 5, 0]], R)[0]
        if probe[2] > pivot[2]:
            ang = -ang
        swings.append((rib, axis, pivot, ang, z))
    return wall, swings, height


def _posed(wall, swings, t, height):
    """Strands swung t of the way down; higher rows lag a little so the sag ripples down the piece."""
    out = [wall]
    for rib, axis, pivot, ang, z in swings:
        lag = 0.25 * (z / max(height, 1.0))
        f = _ease((t - lag * 0.6) / (1 - 0.25 * 0.6)) if t < 1 else 1.0
        m = rib.copy(); m.apply_transform(trimesh.transformations.rotation_matrix(ang * f, axis, pivot)); out.append(m)
    return trimesh.util.concatenate(out)


def droop_motion(size=520, ss=3, colour="#2E4E7E", style="fringe", shape_key="cup", params=None,
                 length="medium", elev=0.3, zoom=1.25):
    wall, swings, height = _droop_scene(shape_key, style, params, length=length)
    flat = _posed(wall, swings, 0.0, height)
    lo, hi = flat.bounds; centre = (lo + hi) / 2; radius = float(np.linalg.norm(hi - lo)) / 2
    font = ImageFont.truetype(FONT, 22)
    view = (1.0, -0.9, elev)

    def frame(t, label):
        m = _posed(wall, swings, t, height)
        im = render([(m, colour)], size=size * ss, view=view, zoom=zoom, target=centre, radius=radius, rake=True)
        im = _clean(im.resize((size, size), Image.LANCZOS))
        if label:
            dr = ImageDraw.Draw(im); w = dr.textlength(label, font=font)
            dr.text(((size - w) / 2, size - 40), label, font=font, fill=INK)
        return im

    seq = [(0.0, "as printed", 1100)]
    n = 14
    seq += [(i / n, None, 55) for i in range(1, n)]
    seq += [(1.0, "after droop", 1500)]
    seq += [(1 - i / n, None, 40) for i in range(1, n)]
    frames = [frame(t, lab) for t, lab, _ in seq]
    _save_gif(frames, [ms for _, _, ms in seq], OUT / "droop.gif")
    return frames


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    jobs = sys.argv[1:] or ["print-build", "droop"]
    if "print-build" in jobs:
        print_build()
    if "droop" in jobs:
        droop_motion()
