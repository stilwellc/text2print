"""Offscreen renders: card thumbnails for the studio and preview sheets for sessions."""
import os
import platform

if platform.system() == "Linux" and not os.environ.get("DISPLAY"):
    os.environ.setdefault("PYOPENGL_PLATFORM", "egl")

import numpy as np

GROUND = (251, 249, 245)


def _look_at(eye, target, up=(0.0, 0.0, 1.0)):
    eye, target, up = (np.asarray(a, float) for a in (eye, target, up))
    f = target - eye; f /= np.linalg.norm(f)
    r = np.cross(f, up); r = r / np.linalg.norm(r) if np.linalg.norm(r) > 1e-9 else np.array([1.0, 0, 0])
    u = np.cross(r, f)
    m = np.eye(4); m[:3, 0], m[:3, 1], m[:3, 2], m[:3, 3] = r, u, -f, eye
    return m


def render(parts, path=None, size=640, view=(1.0, -0.95, 0.85), zoom=1.0, ground=GROUND, target=None, rake=False):
    """parts: [(mesh, '#hex')]. Returns a PIL image (and saves it when path is given)."""
    import pyrender
    import trimesh
    from PIL import Image
    scene = pyrender.Scene(bg_color=[*ground, 255], ambient_light=[0.42] * 3)
    allv = np.vstack([m.vertices for m, _ in parts])
    lo, hi = allv.min(0), allv.max(0); centre = (lo + hi) / 2 if target is None else np.asarray(target, float)
    radius = float(np.linalg.norm(hi - lo)) / 2
    for m, col in parts:
        rgb = [(int(col[k:k + 2], 16) / 255) ** 2.2 for k in (1, 3, 5)]
        mat = pyrender.MetallicRoughnessMaterial(baseColorFactor=rgb + [1.0], metallicFactor=0.0, roughnessFactor=0.85)
        scene.add(pyrender.Mesh.from_trimesh(m, material=mat, smooth=False))
    fov = np.radians(30.0); d = np.asarray(view, float); d /= np.linalg.norm(d)
    dist = radius / np.tan(fov / 2) * 1.08 / zoom
    pose = _look_at(centre + d * dist, centre)
    scene.add(pyrender.PerspectiveCamera(yfov=fov), pose=pose)
    scene.add(pyrender.DirectionalLight(color=np.ones(3), intensity=3.2), pose=pose)
    key_dir = np.array([-1.0, -0.4, 0.25]) if rake else np.array([-0.6, -1.0, 1.4])   # rake: grazing light shows relief
    key = _look_at(centre + key_dir * dist, centre)
    scene.add(pyrender.DirectionalLight(color=np.ones(3), intensity=2.4 if rake else 1.6), pose=key)
    r = pyrender.OffscreenRenderer(size, size)
    try:
        colour, _ = r.render(scene)
    finally:
        r.delete()
    im = Image.fromarray(colour)
    if path:
        im.save(path)
    return im
