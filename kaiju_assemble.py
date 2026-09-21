"""Assembled reference: every printed part put back into world space (the
inverse of split_transforms.json), fangs seated on their gum pads. For
looking at, not printing."""
import json, numpy as np, trimesh, kaiju_head as K
T = {k: np.array(v) for k, v in json.load(open("split_transforms.json")).items()}
parts = []
for name in ("base", "face", "cap", "ear_left", "ear_right"):
    m = trimesh.load(f"sofubi_ape_{name}.stl", force="mesh"); m.apply_transform(np.linalg.inv(T[name])); parts.append(m)
for sx in (-1, 1):
    for fg, down in ((K.fang_up, True), (K.fang_lo, False)):
        base = np.array([sx * fg["x"], -fg["y"], fg["z_base"]], float); t = np.radians(fg["splay"])   # sculpt frame → world: the face looks toward −Y
        axis = np.array([0, -np.sin(t), -np.cos(t)]) if down else np.array([0, -np.sin(t), np.cos(t)])
        m = trimesh.load("sofubi_ape_fang_upper.stl" if down else "sofubi_ape_fang_lower.stl", force="mesh")
        # the canine curls toward local +y: back into the mouth and toward the
        # opposing jaw (down for the uppers, up for the lowers)
        curl = np.array([0, np.cos(t), -np.sin(t)]) if down else np.array([0, np.cos(t), np.sin(t)])
        M = np.eye(4); M[:3, 2] = axis; M[:3, 1] = curl; M[:3, 0] = np.cross(curl, axis); M[:3, 3] = base + axis * 6.0   # pad top
        m.apply_transform(M); parts.append(m)
# eye plugs: base on the cup floor, dome forward; the right one turned so its
# catchlight sits upper-outer like the left's
for sx in (-1, 1):
    e = trimesh.load("sofubi_ape_eye.stl", force="mesh")
    if sx > 0: e.apply_transform(trimesh.transformations.rotation_matrix(np.radians(-90), [0, 0, 1]))
    M = np.eye(4); M[:3, 0] = (1, 0, 0); M[:3, 1] = (0, 0, 1); M[:3, 2] = (0, -1, 0); M[:3, 3] = (sx * K.eye_x, -K.EYE_FLOOR_Y, K.eye_z)
    e.apply_transform(M); parts.append(e)
A = trimesh.util.concatenate(parts); A.export("sofubi_ape_assembled.stl")
print(f"assembled {A.extents[0]:.1f} x {A.extents[1]:.1f} x {A.extents[2]:.1f} mm  {len(A.faces):,} faces")
