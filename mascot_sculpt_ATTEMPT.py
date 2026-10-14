"""
Goblin-bat mascot bust — field sculpt (Sep 27, v2).

The scan (Collin's mascot_head_fixed.stl) is used ONLY as the skull massing: smoothed, scaled to
200 mm horn-tip, clipped to the profile photo's back/front envelope, ears and horn cut away. It is
sampled as a signed-distance grid (voxelize → EDT) and everything the photos show that the scan
lacks is added as blended SDF primitives measured off the photos:
  horn (front edge y −78, tip z 197) · swallow-tail ears traced from the front photo, swept back ·
  brow / eye mounds (fronts y −90 at z 126) · muzzle block (front y −88) · jaw / lower lip · chin.
Frame: face toward −Y, ears ±X, bed z = 0. Phase 1 = form. Usage: python mascot.py [voxel] [out]
"""
import sys, json, time, numpy as np, trimesh
from scipy import ndimage
from skimage import measure

VOXEL = float(sys.argv[1]) if len(sys.argv) > 1 else 0.8
OUT = sys.argv[2] if len(sys.argv) > 2 else "mascot_p1.stl"
H_TIP = 200.0
SRC = "mascot_head_ref.stl"

# ── the scan as skull ─────────────────────────────────────────────────────────
SKULL = dict(smooth=12, cheek_slim=0.09, right_slim=0.14, cheek_z0=30.0, cheek_z1=48.0, cheek_z2=60.0, cheek_z3=110.0, right_z1=120.0,   # jowl slimming window z 48–60 (front photo: ±54 at z 52, scan ±63)
             side_clip=56.0, side_z=76.0, side_k=10.0,   # the jowls (front ±60/72 at z 68–84) stay; only the scan's ears go          # cut the scan's ears off: soft clip at |x| = 52 above z 60
             top_clip=146.0, top_k=10.0,           # cut the scan's horn off
             env_k=6.0, env_margin=-4.0,
             neck=dict(a=60.0, b=56.0, yc=-2.0, z1=62.0, k=4.0))   # the scan's neck is a rounded square; the photo's is an oval column (front ±55, profile depth 54)            # clip to the profile photo's back/front envelope
PROFILE = {int(k): v for k, v in json.load(open("refs/mascot/profile_contour.json")).items()}   # z: (back L, front R) screen mm @ az 70
TRACE = json.load(open("refs/mascot/front_trace.json"))

def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1); return t * t * (3 - 2 * t)
def smin(a, b, k):
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0, 1); return b + (a - b) * h - k * h * (1 - h)
def smax(a, b, k): return -smin(-a, -b, k)

def skull_mesh():
    tm = trimesh.load(SRC, force="mesh")
    tm.apply_transform(trimesh.transformations.rotation_matrix(-np.pi / 2, [0, 0, 1]))   # file faces +X → −Y
    tm.apply_translation([0, 0, -tm.bounds[0, 2]]); tm.apply_scale(H_TIP / tm.bounds[1, 2])
    bot = tm.vertices[:, 2] < 8; tm.apply_translation([-tm.vertices[bot, 0].mean(), 0, 0])
    trimesh.smoothing.filter_taubin(tm, lamb=0.5, nu=-0.53, iterations=SKULL["smooth"])
    V = tm.vertices.copy(); x, y, z = V[:, 0], V[:, 1], V[:, 2]
    s = 1 - SKULL["cheek_slim"] * smoothstep(SKULL["cheek_z0"], SKULL["cheek_z1"], z) * (1 - smoothstep(SKULL["cheek_z2"], SKULL["cheek_z3"], z))
    wr = smoothstep(0, 12, x) * (1 - smoothstep(SKULL["right_z1"] - 30, SKULL["right_z1"], z))
    V[:, 0] = x * s * (1 - SKULL["right_slim"] * wr); V[:, 1] = y * s
    tm.vertices = V; tm.apply_translation([0, 0, -tm.bounds[0, 2]])
    return tm

_SK = {}
def skull_sdf(P):
    """signed distance of the (clipped) scan at points P, from a voxel EDT grid"""
    if "g" not in _SK:
        tm = skull_mesh(); pitch = max(VOXEL, 0.6)
        vg = tm.voxelized(pitch=pitch).fill(); occ = vg.matrix
        sdf = (ndimage.distance_transform_edt(~occ) - ndimage.distance_transform_edt(occ)) * pitch
        _SK["g"] = (sdf.astype(np.float32), vg.translation.astype(np.float32), pitch)
    g, o, pitch = _SK["g"]
    idx = [(P[..., i] - o[i]) / pitch for i in range(3)]
    d = ndimage.map_coordinates(g, [i.ravel() for i in idx], order=1, mode="nearest").reshape(P.shape[:-1]).astype(np.float32)
    outside = (P[..., 0] < o[0]) | (P[..., 0] > o[0] + pitch * g.shape[0]) | (P[..., 1] < o[1]) | (P[..., 1] > o[1] + pitch * g.shape[1]) | (P[..., 2] < o[2]) | (P[..., 2] > o[2] + pitch * g.shape[2])
    d = np.where(outside, 30.0, d)
    x, y, z = P[..., 0], P[..., 1], P[..., 2]
    # cut the scan's ears (soft side clip above the jowls) and its horn (top clip)
    d = smax(d, np.minimum(np.abs(x) - SKULL["side_clip"], z - SKULL["side_z"]), SKULL["side_k"])   # active only above z 60 (the jowls keep their width)
    d = smax(d, z - SKULL["top_clip"], SKULL["top_k"])
    N = SKULL["neck"]; d_col = (np.hypot(x / N["a"], (y - N["yc"]) / N["b"]) - 1.0) * min(N["a"], N["b"])
    d = smax(d, np.minimum(d_col, N["z1"] - z), N["k"])          # oval column below z1, fading into the scan above
    # clip to the profile photo's envelope: back contour (L) and front contour (R), y = −screen / 0.94
    zz = np.array(sorted(PROFILE)); back = np.array([PROFILE[k][0] if PROFILE[k][0] is not None else np.nan for k in zz]); front = np.array([PROFILE[k][1] for k in zz])
    zb = zz[~np.isnan(back)]; yb = -back[~np.isnan(back)] / 0.94 + SKULL["env_margin"]      # +y
    yf = -front / 0.94 - SKULL["env_margin"]                                                   # −y
    y_back = np.interp(z, zb, yb); y_front = np.interp(z, zz, yf)
    env = np.maximum(y - y_back, y_front - y)      # positive outside the envelope
    d = smax(d, env, SKULL["env_k"])
    return d

# ── primitives (front = −Y) ───────────────────────────────────────────────────
FACE_X = 7.0                                            # the face sits 7 mm right of the base centre (front photo: nose +6.8, eyes −31 / +45)
def ell(P, c, r):
    q = (P - np.asarray(c, np.float32)) / np.asarray(r, np.float32)
    return (np.linalg.norm(q, axis=-1) - 1.0) * float(min(r))
def rbox(P, c, h, rr):
    q = np.abs(P - np.asarray(c, np.float32)) - (np.asarray(h, np.float32) - rr)
    return np.linalg.norm(np.maximum(q, 0), axis=-1) + np.minimum(np.max(q, axis=-1), 0) - rr
def cone(P, b, t, r0, r1, n=18, k=2.5, pw=0.6):
    b, t = np.asarray(b, np.float32), np.asarray(t, np.float32); d = None
    for u in np.linspace(0, 1, n):
        c = b + (t - b) * u; r = r1 + (r0 - r1) * (1 - u) ** pw
        s = np.linalg.norm(P - c, axis=-1) - r; d = s if d is None else smin(d, s, k)
    return d

HORN = dict(base=(FACE_X, -60.0, 134.0), tip=(FACE_X, -78.0, 197.0), r0=13.5, r1=2.2, k=8.0)    # profile: front edge y −78 from z 140 to the tip
HORN_BOSS = dict(c=(FACE_X, -52.0, 134.0), r=(24.0, 22.0, 14.0), k=10.0)                          # the crown mound the horn grows from
MOUND = dict(x=38.0, c=(-57.0, 124.0), r=(21.0, 21.0, 19.0), k=12.0)   # profile: brow front y −81 at z 132                                # eye mounds: fronts y −91, tops z 143, out to ±66
MUZZLE = dict(c=(FACE_X, -56.0, 92.0), r=(46.0, 30.0, 28.0), k=11.0)                       # rounded block, front y −88, z 66–118
JAW = dict(c=(FACE_X, -54.0, 65.0), r=(46.0, 26.0, 12.0), k=9.0)                          # lower lip/jaw mass, front y −84, z 52–76
CHIN = dict(c=(FACE_X, -52.0, 52.0), r=(42.0, 22.0, 10.0), k=6.0)   # profile: chin front −57 at z 36, −76 at z 52
# ears: symmetric about the FACE centre (photo tips −115/+127 about the base = ±121 about x 7); root_z = pivot; rise 0 (front photo is the master);
# cup_t bows both tips forward (profile: ear back edge vertical at y +70); lens > any half-width → pure elliptical section
EAR = dict(root_x=50.0, root_y=-12.0, root_z=120.0, sweep=30.0, rise=0.0, cup_t=0.005, cup_b=0.02,
           t_root=26.0, t_edge=8.0, lens=60.0, round=2.5, corner=1.0, k=9.0, inset=26.0, z_floor=76.0)

def ear_sdf(P, sx, poly_xz):
    """fat swallow-tail fin: outline traced from the front photo (x, z in mm), mapped to the plate frame
    (s outward along the swept plate, t up) with s = (|x| − root_x) / cos(sweep); thick at the root, thin at the edge"""
    sw, ri = np.radians(EAR["sweep"]), np.radians(EAR["rise"]); root = np.array([FACE_X + sx * EAR["root_x"], EAR["root_y"], EAR["root_z"]], np.float32)
    e_s = np.array([sx * np.cos(sw) * np.cos(ri), np.sin(sw) * np.cos(ri), np.sin(ri)], np.float32)      # outward, back, and up
    e_t = np.array([-sx * np.cos(sw) * np.sin(ri), -np.sin(sw) * np.sin(ri), np.cos(ri)], np.float32); e_n = np.cross(e_s, e_t)
    q = P - root; s = q @ e_s; t = q @ e_t; n = q @ e_n + np.where(t > 0, EAR["cup_t"], EAR["cup_b"]) * t * t * np.clip(s / 40.0, 0, 1)   # n points BACK: +cup pulls the tips forward
    from shapely.geometry import Polygon, box
    pts = [((abs(px - FACE_X) - EAR["root_x"]) / np.cos(sw), pz - EAR["root_z"]) for px, pz in poly_xz]
    pg = Polygon(pts).buffer(0).intersection(box(-EAR["inset"], EAR["z_floor"] - EAR["root_z"], 200, 200))   # the trace runs down the jowl: keep the ear proper
    pg = pg.buffer(-EAR["corner"], join_style=1).buffer(EAR["corner"], join_style=1)
    poly = [tuple(p) for p in pg.exterior.coords[:-1]]
    d2 = poly_sdf(s, t, poly)
    s_max = max(p[0] for p in poly)
    half = 0.5 * (EAR["t_edge"] + (EAR["t_root"] - EAR["t_edge"]) * (1 - np.clip(s / s_max, 0, 1)) ** 1.2)
    u = np.clip(-d2 / EAR["lens"], 0, 1); half = half * np.sqrt(1 - (1 - u) ** 2)
    dn = np.abs(n) - half
    d = np.sqrt(np.maximum(d2, 0) ** 2 + np.maximum(dn, 0) ** 2) + np.minimum(np.maximum(d2, dn), 0)
    d = np.maximum(d, -s - EAR["inset"])
    return d - EAR["round"]

def poly_sdf(px, py, poly):
    V = np.asarray(poly, np.float32); n = len(V)
    d = (px - V[0, 0]) ** 2 + (py - V[0, 1]) ** 2; sgn = np.ones_like(px)
    for i in range(n):
        a, b = V[i - 1], V[i]
        ex, ey = a[0] - b[0], a[1] - b[1]; wx, wy = px - b[0], py - b[1]
        h = np.clip((wx * ex + wy * ey) / (ex * ex + ey * ey), 0, 1)
        d = np.minimum(d, (wx - ex * h) ** 2 + (wy - ey * h) ** 2)
        c1 = py >= b[1]; c2 = py < a[1]; c3 = ex * wy > ey * wx
        sgn = np.where((c1 & c2 & c3) | (~c1 & ~c2 & ~c3), -sgn, sgn)
    return sgn * np.sqrt(d)

def base_field(P):
    f = skull_sdf(P)
    f = smin(f, ell(P, HORN_BOSS["c"], HORN_BOSS["r"]), HORN_BOSS["k"])
    f = smin(f, cone(P, HORN["base"], HORN["tip"], HORN["r0"], HORN["r1"]), HORN["k"])
    for sx in (-1, 1):
        f = smin(f, ell(P, (FACE_X + sx * MOUND["x"], MOUND["c"][0], MOUND["c"][1]), MOUND["r"]), MOUND["k"])
    f = smin(f, ell(P, MUZZLE["c"], MUZZLE["r"]), MUZZLE["k"])
    f = smin(f, ell(P, JAW["c"], JAW["r"]), JAW["k"])
    f = smin(f, ell(P, CHIN["c"], CHIN["r"]), CHIN["k"])
    for sx in (-1, 1): f = smin(f, ear_sdf(P, sx, TRACE["ear_right_xz"]), EAR["k"])   # the right trace (cleaner, larger) mirrored for both
    return np.maximum(f, -P[..., 2])                     # bed

GRID = dict(x=(-152, 152), y=(-100, 90), z=(-1, 204))
def fields(voxel):
    h = 0.5 * voxel
    xs = np.arange(GRID["x"][0] + h, GRID["x"][1], voxel, dtype=np.float32)
    ys = np.arange(GRID["y"][0] + h, GRID["y"][1], voxel, dtype=np.float32)
    zs = np.arange(GRID["z"][0] + h, GRID["z"][1], voxel, dtype=np.float32)
    X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")
    f = base_field(np.stack([X, Y, Z], axis=-1))
    return xs, ys, zs, f

def mesh_from(fld, xs, ys, zs, voxel):
    eps = 1e-3
    fld = np.where(np.abs(fld) < eps, np.where(fld < 0, -eps, eps), fld).astype(np.float32)
    v, fc, _, _ = measure.marching_cubes(fld, level=0.0, spacing=(voxel, voxel, voxel))
    v += np.array([xs[0], ys[0], zs[0]], np.float32)
    tm = trimesh.Trimesh(v, fc, process=False)
    parts = tm.split(only_watertight=False)
    if len(parts) > 1: tm = sorted(parts, key=lambda m: abs(m.volume), reverse=True)[0]
    tm.fix_normals(); return tm

if __name__ == "__main__":
    t0 = time.time()
    xs, ys, zs, f = fields(VOXEL)
    m = f < 0; edge = [m[0].any(), m[-1].any(), m[:, 0].any(), m[:, -1].any(), m[:, :, -1].any()]
    if any(edge): print("WARNING: solid touches the grid edge", edge)
    tm = mesh_from(f, xs, ys, zs, VOXEL)
    trimesh.smoothing.filter_taubin(tm, lamb=0.5, nu=-0.53, iterations=3)
    tm.export(OUT); e = tm.extents
    print(f"exported {OUT}: {e[0]:.1f} x {e[1]:.1f} x {e[2]:.1f} mm · {len(tm.faces):,} faces · watertight={tm.is_watertight} · {time.time()-t0:.1f}s")
