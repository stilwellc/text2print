"""
Sofubi kaiju #2 — v3, in the TOY language.

v1 (archive/kaiju2_head_v1_cartoon.py) read as a cartoon/bug; v2
(archive/kaiju2_head_v2_realistic.py) read as a realistic creature. Collin:
"doesn't look like an oversized Japanese toy head — realistic, not playful and
a tad goofy like the references". So v3 copies the vintage vinyl language
directly — above all the 1970s Bullmark Baragon sofubi (the toy version of
refs/kaiju2/3.png), plus Bullmark's Miclas:

  - a round, wide, face-forward head — the toy caricature, not an animal skull
  - BIG googly eyes facing forward, a hard lid band across their tops
  - a short bulbous nose knob with two round nostril holes
  - a HUGE U-grin across the whole face: thick smooth lip rim, a row of little
    square teeth all round it, a fat tongue in the bottom
  - one small silver horn on the forehead, three little spikes behind it
  - big cupped bat ears (ref 3) with a scalloped outer edge and a thick rim
  - smooth face; the square-tile hide of the toy's body on the neck and nape
  - ref 2's long neck with heavy sagging folds down the throat, and its stubby
    cheek spikes

Pipeline as the ape (kaiju_head.py). Sculpt frame: mm, Z up, +Y where the face
looks; field() flips Y so in the WORLD the face looks toward −Y.
"""
import sys, time
import numpy as np
import trimesh
from skimage import measure
from kaiju_head import ellipsoid, ellipsoid_roty, smin, smax, smoothstep

# ── PARAMETERS ── all mm ─────────────────────────────────────────────────────
PHASE = int(sys.argv[1]) if len(sys.argv) > 1 else 2
VOXEL = float(sys.argv[2]) if len(sys.argv) > 2 else 0.75
wall  = 2.0
blend = 8.0

# ── masses: a round toy head on a long neck ──
collar  = dict(c=(0, -4, 6), r=(52, 46, 15))
NECK    = dict(z0=6.0, z1=128.0, rx0=34.0, ry0=32.0, rx1=31.0, ry1=29.0, yc0=-8.0, yc1=2.0)   # slimmer: the head reads oversized
cranium = dict(c=(0, -2, 152), r=(48, 42, 40))
face    = dict(c=(0, 22, 128), r=(40, 30, 28))       # the big round lower face the grin lives in
jaw     = dict(c=(0, 24, 106), r=(34, 26, 14))
cheek_l = dict(c=(-34, 18, 128), r=(14, 20, 18))
cheek_r = dict(c=( 34, 18, 128), r=(14, 20, 18))
eye_mound_l = dict(c=(-22, 30, 162), r=(15, 12, 14))
eye_mound_r = dict(c=( 22, 30, 162), r=(15, 12, 14))
brow    = dict(c=(0, 24, 171), r=(36, 16, 10))
muzzle_up = dict(c=(0, 40, 141), r=(30, 16, 12))    # the snout pushes the grin forward
muzzle_lo = dict(c=(0, 34, 108), r=(32, 20, 12))
nose    = dict(c=(0, 56, 148), r=(11, 9, 8))         # the knob — added crisp (k 3)
# ref 1's angry brows: a heavy ridge over each eye, inner end low
brow_ridge_l = dict(c=(-19, 38, 177), r=(16, 9, 6), deg=-18)
brow_ridge_r = dict(c=( 19, 38, 177), r=(16, 9, 6), deg=18)

# ── the grin: a U in the face. Open between z_bot(x) and z_top(x); the corners
# are where they meet (|x| ≈ 34) ──
def z_top(x): return 138.0 - 0.004 * x * x
def z_bot(x): return 102.0 + 0.028 * x * x
MOUTH_BACK = 16.0                      # the cavity's back wall (sculpt y)
LIP_R      = 3.4                       # the thick smooth lip rim
TOOTH      = dict(w=4.4, h=8.0, taper=0.40, pitch=5.0, top_half=30.0, bot_half=27.0)
tongue     = dict(c=(0, 36, 106), r=(20, 20, 9.0))
NOSTRIL    = dict(x=4.6, r=2.4, depth=3.0)
# ── eyes: googly balls, a lid band over the top, a ring round the socket ──
EYE = dict(x=19.0, z=163.0, dir=(0.18, 1.0, 0.06), r=10.5, proud=7.5, lid_r=12.0, lid_line=5.8,
           ring_R=12.6, ring_r=2.0)
# ── horn + spikes + cheek spikes (base probed onto the skin) ──
def _n(v): v = np.asarray(v, np.float32); return v / np.linalg.norm(v)
def _horn(b, a, u, L, r0, r1, curl):
    a = _n(a); u = np.asarray(u, np.float32); u = _n(u - a * (u @ a))
    return dict(b=np.asarray(b, np.float32), a=a, u=u, L=L, r0=r0, r1=r1, curl=curl)
HORN   = dict(y=30.0, a=(0, 0.45, 0.9), u=(0, -1.0, 0.3), L=16.0, r0=5.5, r1=1.6, curl=2.0)
SPIKES = [dict(y=y, L=L) for y, L in ((12.0, 8.0), (-4.0, 9.0), (-20.0, 7.0))]
CHEEK_SPIKE = dict(y=20.0, z=124.0, a=(1.0, 0.3, 0.15), u=(0, 0, 1), L=12.0, r0=6.0, r1=2.6, curl=2.0)
# ── ears (ref 3 / the Bullmark Baragon): a cupped fan, pointed top tip,
# scalloped outer edge, thick rim. Polygon in (s along, t across/up) ──
EAR = dict(root=(42, 0, 172), a=(0.7, 0.0, 0.72), n=(0.2, 1.0, 0.0),
           poly=((-4, 14), (14, 26), (44, 36), (50, 20), (54, 8), (48, -4), (40, -12), (20, -15), (-4, -14)),
           scallops=(((58, 24), 8.5), ((56, 1), 5.5)),
           half_t=2.0, rim_t=1.6, root_t=4.5, cup_t=0.04, cup_s=0.010,
           ribs=((44, 30), (50, 7)), rib_r=2.0, rib_w=0.6)
# ── skin ──
FOLDS = dict(z0=52.0, pitch=14.0, amp=3.0, droop=8.0, zlo=52.0, zhi=102.0)      # ref 2: a few heavy folds high on the throat
TILES = dict(cell=6.5, ref_r=38.0, depth=0.7, groove=0.9, zlo=12.0, zhi=150.0)  # the toy's square-tile hide

# print orientation: collar on the bed (the print is split in phase 3)

# ── helpers ─────────────────────────────────────────────────────────────────
def neck_column(P):
    z = P[..., 2]
    t = np.clip((z - NECK["z0"]) / (NECK["z1"] - NECK["z0"]), 0, 1)
    rx = NECK["rx0"] + (NECK["rx1"] - NECK["rx0"]) * t
    ry = NECK["ry0"] + (NECK["ry1"] - NECK["ry0"]) * t
    yc = NECK["yc0"] + (NECK["yc1"] - NECK["yc0"]) * t
    d = (np.sqrt((P[..., 0] / rx) ** 2 + ((P[..., 1] - yc) / ry) ** 2) - 1.0) * np.minimum(rx, ry)
    return np.maximum(d, np.maximum(NECK["z0"] - z, z - NECK["z1"]))

def chain(P, pts, radii, k):
    d = None
    for c, r in zip(pts, radii):
        s = np.linalg.norm(P - np.asarray(c, np.float32), axis=-1) - r
        d = s if d is None else smin(d, s, k)
    return d

def horn_sdf(P, H, n=14, k=2.0):
    ts = np.linspace(0, 1, n)
    pts = [H["b"] + H["a"] * H["L"] * t + H["u"] * H["curl"] * t * t for t in ts]
    rad = [H["r1"] + (H["r0"] - H["r1"]) * (1 - t) ** 0.85 for t in ts]
    return chain(P, pts, rad, k)

def torus_axis(P, c, e, R, r):
    q = P - c; along = q @ e
    radial = np.linalg.norm(q - along[..., None] * e, axis=-1)
    return np.sqrt((radial - R) ** 2 + along ** 2) - r

def base_field(P):
    f = ellipsoid(P, **cranium)
    f = smin(f, neck_column(P), 14.0)
    f = smin(f, ellipsoid(P, **collar), 10.0)
    for m in (face, jaw, cheek_l, cheek_r, eye_mound_l, eye_mound_r, brow, muzzle_up, muzzle_lo):
        f = smin(f, ellipsoid(P, **m), blend)
    f = smin(f, ellipsoid(P, **nose), 3.0)
    for m in (brow_ridge_l, brow_ridge_r):
        f = smin(f, ellipsoid_roty(P, m["c"], m["r"], m["deg"]), 4.0)
    return f

def _march(fn, p0, d, lo=-40.0, hi=60.0, step=0.25):
    ts = np.arange(hi, lo, -step, dtype=np.float32)
    pts = np.asarray(p0, np.float32) + ts[:, None] * np.asarray(d, np.float32)
    f = fn(pts); i = int(np.argmax(f < 0))
    if not f[i] < 0: raise RuntimeError(f"probe from {p0} along {d} found no surface")
    return pts[i]

_G = {}
def geometry():
    if _G: return _G
    def front(x, z): return float(_march(base_field, (x, 0, z), (0, 1, 0), 0, 100)[1])
    def top(x, y): return float(_march(base_field, (x, y, 100), (0, 0, 1), 0, 130)[2])
    # the lip rim: along the top edge and the U, sitting on the face
    rim = []
    for x in np.linspace(-34, 34, 35):
        rim.append((x, front(x, z_top(x)) - 1.0, z_top(x)))
    for x in np.linspace(-33, 33, 34):
        rim.append((x, front(x, z_bot(x)) - 1.0, z_bot(x)))
    _G["rim"] = rim
    # teeth: along the top edge pointing down, along the U pointing inward
    teeth = []
    for x in np.arange(-TOOTH["top_half"], TOOTH["top_half"] + 0.01, TOOTH["pitch"]):
        teeth.append((x, z_top(x), 0.0, -1.0, front(x, z_top(x))))
    for x in np.arange(-TOOTH["bot_half"], TOOTH["bot_half"] + 0.01, TOOTH["pitch"]):
        dz = 0.056 * x; nx, nz = -dz, 1.0; L = np.hypot(nx, nz)
        teeth.append((x, z_bot(x), nx / L, nz / L, front(x, z_bot(x))))
    _G["teeth"] = teeth
    eyes = []
    for sx in (-1, 1):
        e = _n(np.array(EYE["dir"]) * [sx, 1, 1])
        s = _march(base_field, (sx * EYE["x"], 0, EYE["z"]), e, 0, 80)
        eyes.append((s - e * (EYE["r"] - EYE["proud"]), e, s))
    _G["eyes"] = eyes
    _G["nostrils"] = [np.array([sx * NOSTRIL["x"], front(sx * NOSTRIL["x"], 145.0), 145.0], np.float32) for sx in (-1, 1)]
    _G["horn"] = _horn((0, HORN["y"], top(0, HORN["y"]) - 2.5), HORN["a"], HORN["u"], HORN["L"], HORN["r0"], HORN["r1"], HORN["curl"])
    _G["spikes"] = [_horn((0, s["y"], top(0, s["y"]) - 1.5), (0, -0.3, 1.0), (0, -1, 0), s["L"], 4.0, 1.0, 1.0) for s in SPIKES]
    sp = []
    for sx in (-1, 1):
        side = _march(base_field, (0, CHEEK_SPIKE["y"], CHEEK_SPIKE["z"]), (sx, 0, 0), 0, 90)
        sp.append(_horn(side - np.array([sx * 2.5, 0, 0], np.float32), np.array(CHEEK_SPIKE["a"]) * [sx, 1, 1],
                        CHEEK_SPIKE["u"], CHEEK_SPIKE["L"], CHEEK_SPIKE["r0"], CHEEK_SPIKE["r1"], CHEEK_SPIKE["curl"]))
    _G["cheek_spikes"] = sp
    print(f"    eyes {[tuple(np.round(c, 1)) for c, _, _ in eyes]} · horn base {tuple(np.round(_G['horn']['b'], 1))} · lip front y {front(0, z_top(0)):.1f}/{front(0, z_bot(0)):.1f}")
    return _G

def mouth2d(x, z):
    """< 0 inside the grin's outline (x-z plane)"""
    return np.maximum(z_bot(x) - z, z - z_top(x))

def tooth_sdf2(P, t):
    """a little square tooth: a rounded block along the inner lip, running from
    just behind the rim all the way back to the cavity's back wall — in the
    face-on-its-back print it is a vertical rib, never a cantilever"""
    x0, z0, nx, nz, yf = t
    q_x = P[..., 0] - x0; q_z = P[..., 2] - z0
    n_ = q_x * nx + q_z * nz                      # into the mouth
    a_ = q_x * nz - q_z * nx                      # along the lip
    # the tooth is 9 mm deep and sinks back into the lip at 45° over its last
    # 5 mm (no grille of long ribs; with the face on its back, no flat underside)
    h = TOOTH["h"] * np.clip((P[..., 1] - (yf - 9.0)) / 5.0, 0.0, 1.0)
    u = np.clip(n_ / np.maximum(h, 1e-3), 0, 1)
    da = np.abs(a_) - (TOOTH["w"] / 2) * (1 - TOOTH["taper"] * u) + 0.5
    dn = np.maximum(-n_ - 2.0, n_ - h) + 0.5
    d2 = np.sqrt(np.maximum(da, 0) ** 2 + np.maximum(dn, 0) ** 2) + np.minimum(np.maximum(da, dn), 0) - 0.5
    dy = np.maximum(yf - 9.5 - P[..., 1], P[..., 1] - (yf - 0.6))
    return np.maximum(d2, dy)

def features(f, P):
    g = geometry()
    x, y, z = P[..., 0], P[..., 1], P[..., 2]
    # ── the grin ──
    cav = np.maximum(mouth2d(x, z), MOUTH_BACK - y)
    f = smax(f, -cav, 2.0)
    f = smin(f, chain(P, g["rim"], [LIP_R] * len(g["rim"]), 2.0), 2.5)
    f = smin(f, ellipsoid(P, **tongue), 2.5)
    for t in g["teeth"]:
        f = smin(f, tooth_sdf2(P, t), 0.6)
    # ── nose knob's nostrils: round holes, depth-capped ──
    for c in g["nostrils"]:
        hole = np.linalg.norm((P - c) * np.array([1, 0.6, 1], np.float32), axis=-1) - NOSTRIL["r"]
        f = np.maximum(f, np.minimum(-hole, f + NOSTRIL["depth"]))
    # ── googly eyes ──
    for c, e, s in g["eyes"]:
        f = smin(f, torus_axis(P, s - e * 1.5, e, EYE["ring_R"], EYE["ring_r"]), 2.0)
        rr = np.linalg.norm(P - c, axis=-1)
        f = np.minimum(f, rr - EYE["r"])
        q = P - c
        lid = smax(rr - EYE["lid_r"], EYE["lid_line"] - q[..., 2], 1.4)
        lid = np.maximum(lid, -3.0 - (q @ e))
        f = smin(f, lid, 1.0)
    # ── horn, spikes, cheek spikes, ears ──
    for H in [g["horn"]] + g["spikes"] + g["cheek_spikes"]:
        f = smin(f, horn_sdf(P, H), 2.5)
    for sx in (-1, 1):
        f = smin(f, ear_sdf(P, sx), 4.0)
    return f

def ear_frame(sx):
    root = np.array(EAR["root"], np.float32) * np.array([sx, 1, 1], np.float32)
    a = _n(np.array(EAR["a"]) * np.array([sx, 1, 1]))
    n = np.array(EAR["n"]) * np.array([sx, 1, 1]); n = _n(n - a * (n @ a))
    b = np.cross(n, a); b = b if b[2] > 0 else -b
    return root, a, b.astype(np.float32), n

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

def ear_sdf(P, sx):
    root, a, b, n = ear_frame(sx)
    q = P - root; s = q @ a; t = q @ b
    w = q @ n - EAR["cup_t"] * (t - 8) ** 2 - EAR["cup_s"] * (s - 20) ** 2 * (s > 20)   # a deep cup
    d2 = poly_sdf(s, t, EAR["poly"])
    for (ps, pt), r in EAR["scallops"]:
        d2 = np.maximum(d2, r - np.sqrt((s - ps) ** 2 + (t - pt) ** 2))
    d2 = d2 + 1.2
    th = EAR["half_t"] + (EAR["root_t"] - EAR["half_t"]) * (1 - smoothstep(0.0, 16.0, s)) \
         + EAR["rim_t"] * (1 - smoothstep(0.0, 3.5, -d2))
    plate = smax(d2, np.abs(w) - th, 1.2)
    ribs = None
    for ts, tt_ in EAR["ribs"]:
        L = np.hypot(ts - 2.0, tt_ - 4.0); ds, dt = (ts - 2.0) / L, (tt_ - 4.0) / L
        h = np.clip(((s - 2.0) * ds + (t - 4.0) * dt) / L, 0, 0.85)
        r = np.sqrt((s - 2.0 - ds * L * h) ** 2 + (t - 4.0 - dt * L * h) ** 2 + (w - EAR["rib_w"]) ** 2) - EAR["rib_r"] * (1 - 0.5 * h)
        ribs = r if ribs is None else np.minimum(ribs, r)
    return smin(plate, ribs, 1.0)

def field(P):
    P = P * np.array([1, -1, 1], np.float32)
    f = base_field(P)
    if PHASE >= 2:
        f = features(f, P)
    return f

def skin_relief(P):
    """ref 2's heavy folds down the throat; the toy's square tiles on the sides
    and back of the neck and the nape. The face and crown stay smooth."""
    x, y, z = P[..., 0], P[..., 1], P[..., 2]
    ang = np.arctan2(x, y); front = np.cos(ang)
    band = smoothstep(FOLDS["zlo"], FOLDS["zlo"] + 6, z) * (1 - smoothstep(FOLDS["zhi"] - 10, FOLDS["zhi"], z))
    ze = z + FOLDS["droop"] * np.clip(front, 0, 1) ** 2
    t = np.mod((ze - FOLDS["z0"]) / FOLDS["pitch"], 1.0)
    fold = smoothstep(0.0, 0.72, t) * (1 - smoothstep(0.72, 1.0, t))
    fold = fold * (0.6 + 0.4 * np.sin(1.7 * np.floor((ze - FOLDS["z0"]) / FOLDS["pitch"]) + 0.8))   # each fold its own weight
    wf = smoothstep(0.15, 0.6, front)                          # folds on the throat
    c = TILES["cell"]; u = ang * TILES["ref_r"]
    du = np.abs(np.mod(u, c) - c / 2); dv = np.abs(np.mod(z, c) - c / 2)
    dline = np.minimum(c / 2 - du, c / 2 - dv)
    groove = 1 - smoothstep(0.0, TILES["groove"], dline)
    tz = smoothstep(TILES["zlo"], TILES["zlo"] + 4, z) * (1 - smoothstep(TILES["zhi"] - 8, TILES["zhi"], z))
    wt = (1 - wf) * tz * (1 - smoothstep(-0.2, 0.3, front) * smoothstep(96.0, 104.0, z))   # never on the face
    return FOLDS["amp"] * fold * band * wf - TILES["depth"] * groove * wt

def fields(voxel):
    from scipy import ndimage
    h = 0.5 * voxel
    xs = np.arange(-112 + h, 112, voxel, dtype=np.float32)
    ys = np.arange(-80 + h, 80, voxel, dtype=np.float32)
    zs = np.arange(-2 + h, 236, voxel, dtype=np.float32)
    X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")
    P = np.stack([X, Y, Z], axis=-1)
    f = field(P)
    dist = ndimage.distance_transform_edt(f < 0) * voxel
    f_tex = f
    if PHASE >= 2:
        band = np.abs(f) < 3.0
        f_tex = f.copy()
        f_tex[band] -= skin_relief(P[band] * np.array([1, -1, 1], np.float32))
    del P
    shell = np.maximum(f_tex, dist - (wall + 0.5 * voxel))
    shell = np.maximum(shell, -Z)
    return xs, ys, zs, X, Y, Z, f, shell, dist

def mesh_from(shellfield, xs, ys, zs, voxel, keep_largest=True):
    verts, faces, _, _ = measure.marching_cubes(shellfield, level=0.0, spacing=(voxel, voxel, voxel))
    verts += np.array([xs[0], ys[0], zs[0]], np.float32)
    tm = trimesh.Trimesh(verts, faces, process=False)
    if keep_largest:
        parts = tm.split(only_watertight=False)
        if len(parts) > 1:
            tm = sorted(parts, key=lambda m: abs(m.volume), reverse=True)[0]
    tm.fix_normals()
    return tm

if __name__ == "__main__":
    t0 = time.time()
    xs, ys, zs, X, Y, Z, f, shell, dist = fields(VOXEL)
    tm = mesh_from(shell, xs, ys, zs, VOXEL)
    out = f"kaiju2_p{PHASE}.stl"
    tm.export(out)
    e = tm.extents
    print(f"exported {out}: {e[0]:.1f} x {e[1]:.1f} x {e[2]:.1f} mm · {len(tm.faces):,} faces · "
          f"watertight={tm.is_watertight} · {time.time()-t0:.1f}s · PLA ≈ {abs(tm.volume)/1000*1.24:.0f} g shell")
