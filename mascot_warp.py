"""
Goblin-bat mascot bust — Phase 1 base body.
Source: Collin's mascot_head_fixed.stl (generated mesh, face +X, ears ±Y, 97 mm tall).
Canonical frame here: face toward −Y, ears ±X, bed at z = 0, horn tip at z = H_TIP.
Pipeline: rotate → scale → Taubin smooth → silhouette warps (row-table driven) → export.
Usage: python mascot.py [out.stl]
"""
import sys, numpy as np, trimesh

SRC = "mascot_head_ref.stl"
H_TIP = 200.0          # mm, bed → horn tip (mapping-tool convention)
SMOOTH_IT = 12         # Taubin iterations (12 = clean clay, −2 % volume)

# ── silhouette warps (all zero = raw file; tuned off mascot_map row tables) ──
WARP = dict(
    cheek_slim   = 0.10,   # fraction to slim x/y radius below the ears (0.10 = −10 %)
    cheek_z0     = 40.0,  # slimming full below this z, fades to 0 by cheek_z1
    cheek_z1     = 110.0,
    ear_lift_deg = 8.0,   # rotate each ear up about its root (+ = tips rise)
    ear_root_x   = 45.0,  # |x| beyond which (above ear_z0) a vertex belongs to the ear incl. its lower fold; the jowls below ear_z0 stay body
    ear_z0       = 60.0,  # ears live above this z; below it wide vertices are jowl, not ear
    ear_scale    = 0.94,   # scale both ears about their root pivot (file ears run ~13 mm longer than the photo)
    ear_r_scale  = 0.86,   # extra scale on the +x ear (photo: ears symmetric; file: +x ear bigger)
    right_slim   = 0.06,   # slim the +x half of the body (file: right jowl/cheek 5–19 mm wider than the photo), fades out above right_z1
    right_z1     = 120.0,
    head_tilt_deg = 0.0,  # nose-up pitch of the whole head about the x-axis (profile photo: muzzle further forward, horn leaning forward, skull back lower)
    tilt_z0      = 30.0,  # weight ramps 0→1 between tilt_z0 and tilt_z1 (neck stays put)
    tilt_z1      = 80.0,
    tilt_pivot_y = 0.0,   # pivot line y (0 = column centre); z pivot = tilt_z0
    ear_sweep_deg = 0.0,  # rotate the ears BACK about a vertical axis through the root (+ = tips move toward +y)
    lobe_lift_l  = 8.0,   # mm: raise the −x ear's lower lobe (front table: lobe 10 mm too wide/low at z 68–84)
    lobe_lift_r  = 17.0,  # mm: raise the +x ear's lower lobe (18–19 mm too wide/low at z 68–84)
    lobe_z0      = 95.0,  # lobe weight 1 below this z, 0 above lobe_z1
    lobe_z1      = 125.0,
)

def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1); return t * t * (3 - 2 * t)

def load_canonical():
    tm = trimesh.load(SRC, force="mesh")
    tm.apply_transform(trimesh.transformations.rotation_matrix(-np.pi / 2, [0, 0, 1]))  # +X face → −Y
    tm.apply_translation([0, 0, -tm.bounds[0, 2]])
    tm.apply_scale(H_TIP / tm.bounds[1, 2])
    xs = tm.vertices[:, 0]; bot = tm.vertices[:, 2] < 8
    tm.apply_translation([-xs[bot].mean(), 0, 0])          # base centred on x = 0
    return tm

def warp(tm, W):
    V = tm.vertices.copy(); x, y, z = V[:, 0], V[:, 1], V[:, 2]
    # cheek / base slimming: radial scale about the column axis, fading out upward
    w = 1 - smoothstep(W["cheek_z0"], W["cheek_z1"], z)
    s = 1 - W["cheek_slim"] * w
    inear = (np.abs(x) > W["ear_root_x"]) & (z > W["ear_z0"])
    s = np.where(inear, 1.0, s)
    # right-half slimming: x scale only, weighted by how far past the centreline, fading upward
    wr = smoothstep(0, 12, x) * (1 - smoothstep(W["right_z1"] - 30, W["right_z1"], z))
    s_r = np.where(inear, 1.0, 1 - W["right_slim"] * wr)
    V[:, 0] = x * s * s_r; V[:, 1] = y * s
    x = V[:, 0]
    # ear lift: rotate about the y-axis line through (±ear_root_x, z_root), weight grows outward
    for sgn in (-1, 1):
        sel = ((sgn * V[:, 0]) > W["ear_root_x"]) & (V[:, 2] > W["ear_z0"])
        if not sel.any(): continue
        zr = V[sel, 2].mean()
        wt = smoothstep(W["ear_root_x"], W["ear_root_x"] + 30, sgn * V[sel, 0])
        ang = np.radians(W["ear_lift_deg"]) * wt * sgn
        dx = V[sel, 0] - sgn * W["ear_root_x"]; dz = V[sel, 2] - zr
        V[sel, 0] = sgn * W["ear_root_x"] + dx * np.cos(ang) - dz * np.sin(ang)
        V[sel, 2] = zr + dx * np.sin(ang) + dz * np.cos(ang)
        ks = W["ear_scale"] * (W["ear_r_scale"] if sgn > 0 else 1.0)
        if ks != 1.0:
            k = 1 + (ks - 1) * wt
            V[sel, 0] = W["ear_root_x"] + (V[sel, 0] - W["ear_root_x"]) * k
            V[sel, 2] = zr + (V[sel, 2] - zr) * k
        if W["ear_sweep_deg"]:
            a2 = np.radians(W["ear_sweep_deg"]) * wt * sgn
            dx = V[sel, 0] - sgn * W["ear_root_x"]; dy = V[sel, 1]
            V[sel, 0] = sgn * W["ear_root_x"] + dx * np.cos(a2) - dy * np.sin(a2)
            V[sel, 1] = dx * np.sin(a2) + dy * np.cos(a2)
    # lower-lobe lift: z-shear of the ear's lower half, growing outward from the root
    for sgn, key in ((-1, "lobe_lift_l"), (1, "lobe_lift_r")):
        sel = ((sgn * V[:, 0]) > W["ear_root_x"]) & (V[:, 2] > W["ear_z0"])
        wt = smoothstep(W["ear_root_x"], W["ear_root_x"] + 30, sgn * V[sel, 0]) * (1 - smoothstep(W["lobe_z0"], W["lobe_z1"], V[sel, 2]))
        V[sel, 2] = V[sel, 2] + W[key] * wt
    # head tilt: nose-up rotation about the x-axis, weighted so the neck/base stay put
    if W["head_tilt_deg"]:
        wt = smoothstep(W["tilt_z0"], W["tilt_z1"], V[:, 2])
        a = -np.radians(W["head_tilt_deg"]) * wt          # negative about +x lifts −y (the face)
        dy = V[:, 1] - W["tilt_pivot_y"]; dz = V[:, 2] - W["tilt_z0"]
        V[:, 1] = W["tilt_pivot_y"] + dy * np.cos(a) - dz * np.sin(a)
        V[:, 2] = W["tilt_z0"] + dy * np.sin(a) + dz * np.cos(a)
    tm.vertices = V
    return tm

# ── profile fit: the photo's side contour (profile view at az 70°, screen mm from the base centre, 200 mm scale) ──
# screen x ≈ 0.34·x + 0.94·(−y); front-most / back-most points sit near x = 0, so y ≈ −screen / 0.94
PROFILE_PHOTO = {  # z: (back L, front R)  — from refs/mascot/profile.png via mascot_map
    196: (None, 76.3), 188: (None, 77.8), 180: (None, 78.0), 172: (None, 77.0), 164: (None, 75.7), 156: (None, 73.6),
    148: (None, 71.5), 140: (None, 69.4), 132: (None, 81.4), 124: (None, 85.0), 116: (None, 83.6), 108: (None, 84.2),
    100: (-60.9, 84.4), 92: (-56.9, 82.7), 84: (-55.8, 77.2), 76: (-54.1, 79.9), 68: (-50.7, 82.5), 60: (-47.5, 82.5),
    52: (-46.2, 71.5), 44: (-47.1, 57.0), 36: (-50.3, 53.9), 28: (-53.2, 57.0), 20: (-54.7, 59.2), 12: (-53.4, 53.9)}
PROFILE_FIT = dict(on=True, gain_front=1.0, gain_back=1.15, sigma=8.0)   # gains scale the displacement; sigma = z smoothing (mm)

def profile_fit(V, P=PROFILE_FIT):
    """Displace the front surface (y < 0) and the back surface (y > 0) per height so the model's side contour
    matches PROFILE_PHOTO. Above z 145 (horn only) the whole section shifts rigidly."""
    from scipy.ndimage import gaussian_filter1d
    x, y, z = V[:, 0], V[:, 1], V[:, 2]
    zs = np.arange(0, 201, 2.0); cur_f = np.full(len(zs), np.nan); cur_b = np.full(len(zs), np.nan)
    body = np.abs(x) < 45
    for i, zc in enumerate(zs):
        sel = body & (np.abs(z - zc) < 2)
        if sel.sum() > 5: cur_f[i] = y[sel].min(); cur_b[i] = y[sel].max()
    def interp_photo(col):
        pts = sorted((zz, v[col]) for zz, v in PROFILE_PHOTO.items() if v[col] is not None)
        zz = np.array([p[0] for p in pts]); vv = -np.array([p[1] for p in pts]) / 0.94   # screen → model y
        return zz, vv
    zf, tf = interp_photo(1); zb, tb = interp_photo(0)
    tgt_f = np.interp(zs, zf, tf); tgt_b = np.interp(zs, zb, tb)
    d_f = np.where(np.isnan(cur_f), 0, tgt_f - cur_f); d_b = np.where(np.isnan(cur_b), 0, tgt_b - cur_b)
    d_f[(zs < zf.min() - 4) | (zs > zf.max() + 4)] = 0; d_b[(zs < zb.min() - 4) | (zs > zb.max() + 4)] = 0
    d_f = gaussian_filter1d(d_f, P["sigma"] / 2) * P["gain_front"]; d_b = gaussian_filter1d(d_b, P["sigma"] / 2) * P["gain_back"]
    df = np.interp(z, zs, d_f); db = np.interp(z, zs, d_b)
    wf = np.maximum(smoothstep(15, -25, y), smoothstep(140, 150, z)); wb = smoothstep(-15, 25, y) * (1 - smoothstep(140, 150, z))
    V[:, 1] = y + wf * df + wb * db
    return V, list(zip(zs[::8], np.round(d_f[::8], 1), np.round(d_b[::8], 1)))

def build(W=WARP):
    tm = load_canonical()
    trimesh.smoothing.filter_taubin(tm, lamb=0.5, nu=-0.53, iterations=SMOOTH_IT)
    tm = warp(tm, W)
    if PROFILE_FIT["on"]:
        V, table = profile_fit(tm.vertices.copy()); tm.vertices = V
        build.profile_table = table
    tm.apply_translation([0, 0, -tm.bounds[0, 2]])
    return tm

if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "mascot_p1.stl"
    tm = build()
    print("extents", np.round(tm.extents, 1), "watertight", tm.is_watertight)
    tm.export(out); print("wrote", out)
