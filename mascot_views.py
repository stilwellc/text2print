"""Studio views of a canonical (face −Y) STL: front / three-quarter / profile / back on one strip. Usage: python mascot_views.py in.stl out.png"""
import sys, numpy as np, trimesh, pyrender
from PIL import Image
tm = trimesh.load(sys.argv[1], force="mesh")
def render(yaw_deg, pitch_deg=6, size=(1400, 1400), zoom=0.62):
    scene = pyrender.Scene(bg_color=[0.96, 0.95, 0.93, 1], ambient_light=[0.35] * 3)
    scene.add(pyrender.Mesh.from_trimesh(tm, smooth=False, material=pyrender.MetallicRoughnessMaterial(baseColorFactor=[0.8, 0.78, 0.72, 1], roughnessFactor=0.8)))
    c = tm.bounds.mean(axis=0); R = np.linalg.norm(tm.extents) / 2
    yaw, pitch = np.radians(yaw_deg), np.radians(pitch_deg)
    d = np.array([-np.sin(yaw) * np.cos(pitch), -np.cos(yaw) * np.cos(pitch), np.sin(pitch)])   # yaw 0 = camera in front (−Y)
    z = d; x = np.cross([0, 0, 1], z); x /= np.linalg.norm(x); y = np.cross(z, x)
    pose = np.eye(4); pose[:3, 0] = x; pose[:3, 1] = y; pose[:3, 2] = z; pose[:3, 3] = c + d * R * 4
    scene.add(pyrender.OrthographicCamera(xmag=R * zoom, ymag=R * zoom, znear=1.0, zfar=2000.0), pose=pose)
    scene.add(pyrender.DirectionalLight(intensity=2.6), pose=pose)
    lp = np.eye(4); lp[:3, :3] = trimesh.transformations.rotation_matrix(np.radians(-50), [0, 0, 1])[:3, :3] @ pose[:3, :3]; lp[:3, 3] = pose[:3, 3]
    scene.add(pyrender.DirectionalLight(intensity=1.8), pose=lp)
    r = pyrender.OffscreenRenderer(*size); col, _ = r.render(scene); r.delete()
    return Image.fromarray(col)
tiles = [render(0), render(42), render(90), render(180)]
sheet = Image.new("RGB", (1400 * 4, 1400), (245, 242, 237))
for i, t in enumerate(tiles): sheet.paste(t, (i * 1400, 0))
sheet.resize((2800, 700)).save(sys.argv[2]); print("wrote", sys.argv[2])
