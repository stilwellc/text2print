"""Studio plate render: dark warm ground, beige matte object, three lights, 16:10. Matches the prints-library plates."""
import sys, numpy as np, trimesh, pyrender
from PIL import Image, ImageFilter
def render(stl, out, w=1200, h=750, yaw_deg=-32, pitch_deg=28):
    tm = trimesh.load(stl, force="mesh"); tm.apply_translation(-tm.bounding_box.centroid)
    ext = tm.extents; R = float(np.linalg.norm(ext)) / 2
    mat = pyrender.MetallicRoughnessMaterial(baseColorFactor=[0.86, 0.82, 0.74, 1.0], metallicFactor=0.0, roughnessFactor=0.75)
    scene = pyrender.Scene(bg_color=[0.11, 0.095, 0.085, 1.0], ambient_light=[0.10, 0.09, 0.08])
    scene.add(pyrender.Mesh.from_trimesh(tm, material=mat, smooth=False))
    yaw, pitch = np.radians(yaw_deg), np.radians(pitch_deg)
    dirv = np.array([np.sin(yaw) * np.cos(pitch), -np.cos(yaw) * np.cos(pitch), np.sin(pitch)])
    # fit: iterate the camera distance until the projected bounding box fills ~84% of the frame
    corners = np.array([[sx * ext[0] / 2, sy * ext[1] / 2, sz * ext[2] / 2] for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)])
    d = R * 3.0; ty = np.tan(np.radians(18)); tx = ty * (w / h)
    for _ in range(4):
        eye = dirv * d; f = -dirv; s_ = np.cross(f, np.array([0, 0, 1.0])); s_ /= np.linalg.norm(s_); u_ = np.cross(s_, f)
        rel = corners - eye; cx = rel @ s_; cy = rel @ u_; cz = -(rel @ f)
        nx = np.max(np.abs(cx) / (cz * tx)); ny = np.max(np.abs(cy) / (cz * ty)); d *= max(nx, ny) / 0.84
    cam_pos = dirv * d
    def look_at(eye, target, up=np.array([0, 0, 1.0])):
        f = target - eye; f /= np.linalg.norm(f); s = np.cross(f, up); s /= np.linalg.norm(s); u = np.cross(s, f)
        M = np.eye(4); M[:3, 0] = s; M[:3, 1] = u; M[:3, 2] = -f; M[:3, 3] = eye; return M
    cam = pyrender.PerspectiveCamera(yfov=np.radians(36), aspectRatio=w / h)
    scene.add(cam, pose=look_at(cam_pos, np.zeros(3)))
    key = pyrender.DirectionalLight(color=[1.0, 0.96, 0.90], intensity=4.6)
    fill = pyrender.DirectionalLight(color=[0.9, 0.92, 1.0], intensity=1.6)
    rim = pyrender.DirectionalLight(color=[1.0, 0.95, 0.85], intensity=1.6)
    scene.add(key, pose=look_at(np.array([-1.2, -1.0, 1.6]) * d, np.zeros(3)))
    scene.add(fill, pose=look_at(np.array([1.4, -0.6, 0.8]) * d, np.zeros(3)))
    scene.add(rim, pose=look_at(np.array([0.3, 1.4, 1.0]) * d, np.zeros(3)))
    r = pyrender.OffscreenRenderer(w, h); color, _ = r.render(scene); r.delete()
    img = Image.fromarray(color)
    # soft vignette like the plates
    vig = Image.new("L", (w, h), 0); yy, xx = np.mgrid[0:h, 0:w]; rr = np.sqrt(((xx - w/2) / (w/2))**2 + ((yy - h/2) / (h/2))**2)
    v = np.clip(1.0 - 0.35 * np.clip(rr - 0.55, 0, 1) / 0.6, 0.65, 1.0); arr = np.asarray(img).astype(np.float32) * v[..., None]
    Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).save(out, quality=82)
if __name__ == "__main__":
    render(sys.argv[1], sys.argv[2])
