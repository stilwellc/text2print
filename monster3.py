"""
Monster #3 — v5, from scratch (Sep 26, "starting from scratch with fable").

A vintage-Japanese-vinyl monster head bust. FORM is measured from the three
views of the same wooden head in refs/monster3 (ref4 three-quarter, ref5 side,
ref6 back), scaled to 190 mm tall; refs 2/3/8 are secondary. DETAIL (eyes,
teeth, skin) is the Bullmark toy language, not the wood grain.

Measured (mm, z from the bed):
  block     flat open base 110 wide × 105 deep, sides swelling to 142 wide at
            z≈89 (the cheeks), top at z≈120 saddling between the lobes
  lobes     two thick fans, ~34 across, centred x ±48, 115 long front→back,
            rising from the brow (z 120) back and up to tips at z≈190
  crest     a horn at the top front centre, tip z≈176, broad front-to-back
  snout     overhangs the base front by ~55 mm; upper jaw z 84–128
  grin      rolled upper lip, blunt teeth under it, mouth ~26 open,
            two big upward fangs + beads on the lower jaw, chin pad
  eyes      Bullmark googly eyes high on the brow either side of the crest
  back      three teardrop mounds up the centre line (ref6)

Sculpt frame: mm, Z up, +Y where the face looks; field() flips Y so the face
looks toward −Y in the WORLD (studio_render yaw −152/180/−95 = hero/front/profile).
"""
import sys, time
import numpy as np
import trimesh
from skimage import measure
from kaiju_head import ellipsoid, smin, smax, smoothstep

PHASE = int(sys.argv[1]) if len(sys.argv) > 1 else 2
VOXEL = float(sys.argv[2]) if len(sys.argv) > 2 else 0.75
wall  = 2.0

# ── FORM — big soft masses, no box (v5b) ──────────────────────────────────
base_col = dict(hx=60.0, hy=54.0, yc=-14.0, r=30.0, z1=90.0)   # as wide as the cheeks: near-vertical sides (ref6)        # the flat-bottomed foot, 110 × 100
head     = dict(c=(0, -12, 92), r=(70, 62, 56))                     # the skull: top of the saddle ≈ z 148
# THE FACE (refs 4 + 2, re-read Sep 26): a broad shovel muzzle with a fat
# rolled rim, teeth hanging under it; two GIANT eyeballs sitting on top of
# the muzzle at the front; a lower jaw with two huge upturned fangs and a
# flat oval chin pad; the mouth a wide gape between.
upper_jaw = dict(c=(0, 36, 90), r=(56, 66, 26))                     # y −30 … 102, z 64 … 116
eye_seat_l = dict(c=(-27, 56, 108), r=(24, 28, 16))                  # the mounds the eyeballs sit in
eye_seat_r = dict(c=( 27, 56, 108), r=(24, 28, 16))
lower_jaw = dict(c=(0, 30, 42), r=(50, 64, 22))                     # y −34 … 94, z 20 … 64
chin     = dict(c=(0, 64, 38), r=(32, 28, 16))
chin_pad = dict(c=(0, 86, 40), r=(20, 7, 13))                       # the flat oval pad on the chin front (ref4)
jowl_l   = dict(c=(-56, 6, 70), r=(22, 38, 34))
jowl_r   = dict(c=( 56, 6, 70), r=(22, 38, 34))
MOUTH    = dict(c=(0, 70, 70), r=(48, 58, 18))                      # the gape: z 54 … 86, open at the front
# the lobes: fat thumbs, broad front-to-back, rising from behind the eyes back and up
LOBE  = dict(p=((46, 28, 112), (52, -6, 146), (55, -34, 176), (56, -48, 190)),
             r=((20, 40, 20), (18, 34, 18), (15, 22, 14), (11, 12, 10)))   # a broad fan covering the skull side (ref5)
CREST = dict(base=(0, 4, 118), tip=(0, -2, 180), r0=(15.0, 19.0, 15.0), r1=(6.5, 8.5, 6.5), n=12)   # a thumb between the lobes (ref6)
BLEND = 12.0

# ── DETAIL (Bullmark) ───────────────────────────────────────────────────────
LIP_UP  = dict(z=86.0, r=9.5, x_half=50.0, flare=3.0)      # a fat rolled rim round the muzzle front, flaring out
LIP_LO  = dict(z=56.0, r=8.5, x_half=44.0, flare=1.5)
TEETH_UP = dict(xs=(-24.0, -12.0, 0.0, 12.0, 24.0), top=84.0, h=14.0, w=10.0, d=12.0)
FANGS_UP = dict(x=38.0, top=84.0, L=22.0, r0=6.5, r1=1.6, lean=(0.10, 0.12, -1.0))     # upper corner fangs (ref2)
FANGS_LO = dict(x=30.0, y=74.0, z=50.0, L=32.0, r0=8.0, r1=1.8, lean=(0.06, 0.12, 1.0))   # the two big upturned fangs (ref4)
BEADS   = dict(xs=(-16.0, -8.0, 0.0, 8.0, 16.0), y=76.0, z=56.0, r=4.6)
TONGUE  = dict(c=(0, 50, 58), r=(22, 24, 6.5))
EYE     = dict(x=27.0, z=120.0, dir=(0.22, 1.0, 0.18), r=19.0, proud=15.0, lid_r=20.4, lid_line=7.0, pupil=8.0, pupil_depth=3.0)   # GIANT frog eyes on the muzzle top
NOSTRILS = dict(x=9.0, y=100.0, z=104.0, r=4.5)             # two small nubs at the front top of the muzzle (ref4's bead)
TEARS   = [dict(z=12.0, w=10.0, h=34.0), dict(z=52.0, w=7.5, h=26.0), dict(z=84.0, w=5.0, h=18.0)]

def _n(v): v = np.asarray(v, np.float32); return v / np.linalg.norm(v)

def base_col_sdf(P):
    x, y, z = P[..., 0], P[..., 1], P[..., 2]; B = base_col; r = B["r"]
    dx = np.abs(x) - (B["hx"] - r); dy = np.abs(y - B["yc"]) - (B["hy"] - r)
    d2 = np.sqrt(np.maximum(dx, 0) ** 2 + np.maximum(dy, 0) ** 2) + np.minimum(np.maximum(dx, dy), 0) - r
    return np.maximum(d2, z - B["z1"])

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

def lobe_sdf(P, sx):
    """a fat thumb: ellipsoids along a curve, broad front-to-back, slimmer across"""
    pts = [np.array(q, np.float32) * np.array([sx, 1, 1], np.float32) for q in LOBE["p"]]
    d = None
    for i in range(len(pts) - 1):
        for k in np.linspace(0, 1, 6, endpoint=(i == len(pts) - 2)):
            c = pts[i] + (pts[i + 1] - pts[i]) * k
            r = tuple(a + (b - a) * k for a, b in zip(LOBE["r"][i], LOBE["r"][i + 1]))
            e = ellipsoid(P, c, r); d = e if d is None else smin(d, e, 6.0)
    return d

def crest_sdf(P):
    b, t = np.array(CREST["base"], np.float32), np.array(CREST["tip"], np.float32); d = None
    for k in np.linspace(0, 1, CREST["n"]):
        c = b + (t - b) * k; r = tuple(a + (bb - a) * k ** 1.1 for a, bb in zip(CREST["r0"], CREST["r1"]))
        e = ellipsoid(P, c, r); d = e if d is None else smin(d, e, 3.0)
    return d

def cone(P, b, a, L, r0, r1, n=12, k=1.8):
    b = np.asarray(b, np.float32); a = _n(a); d = None
    for t in np.linspace(0, 1, n):
        c = b + a * L * t; r = r1 + (r0 - r1) * (1 - t) ** 0.9
        s = np.linalg.norm(P - c, axis=-1) - r; d = s if d is None else smin(d, s, k)
    return d

def base_field(P):
    f = ellipsoid(P, **head)
    f = smin(f, base_col_sdf(P), 30.0)                 # a bell: the foot flows up into the cheeks
    for m in (upper_jaw, lower_jaw, jowl_l, jowl_r, chin):
        f = smin(f, ellipsoid(P, **m), BLEND)
    for m in (eye_seat_l, eye_seat_r):
        f = smin(f, ellipsoid(P, **m), 8.0)
    f = smin(f, ellipsoid(P, **chin_pad), 3.0)
    for sx in (-1, 1):
        f = smin(f, lobe_sdf(P, sx), 12.0)
    f = smin(f, crest_sdf(P), 8.0)
    return f

_G = {}
def _front(x, z):
    """the base skin's front y at (x, z)"""
    ys = np.arange(120, -20, -0.25, dtype=np.float32)
    Q = np.stack([np.full_like(ys, x), ys, np.full_like(ys, z)], -1)
    fq = base_field(Q); i = int(np.argmax(fq < 0)); return float(ys[i])

def teardrop2d(x, z, w, h):
    zc = w
    circ = np.sqrt(x * x + (z - zc) ** 2) - w
    k = np.clip((z - zc) / max(h - zc, 1e-3), 0, 1)
    top = np.where(z > zc, np.maximum(np.abs(x) - w * (1 - k) ** 1.2, z - h), circ)
    return np.minimum(circ, top)

def features(f, P):
    x, y, z = P[..., 0], P[..., 1], P[..., 2]
    if "lip" not in _G:
        _G["lip"] = {tx: _front(tx, LIP_UP["z"]) for tx in np.arange(-52, 52.1, 4.0)}
        _G["lip_lo"] = {tx: _front(tx, LIP_LO["z"]) for tx in np.arange(-46, 46.1, 4.0)}
        _G["eye"] = _front(EYE["x"], EYE["z"])
        print(f"    eye front y {_G['eye']:.1f}")
    # the gape, then the rolled lips laid along the skin (flaring out), teeth, fangs, beads, tongue
    f = smax(f, -ellipsoid(P, **MOUTH), 3.0)
    for L, key in ((LIP_UP, "lip"), (LIP_LO, "lip_lo")):
        d = None
        for tx, fy in _G[key].items():
            if abs(tx) > L["x_half"]: continue
            s_ = np.sqrt((x - tx) ** 2 + (y - (fy - L["r"] + L["flare"])) ** 2 + (z - L["z"]) ** 2) - L["r"]
            d = s_ if d is None else smin(d, s_, 3.0)
        f = smin(f, d, 3.0)
    for tx in TEETH_UP["xs"]:
        fy = _G["lip"][min(_G["lip"], key=lambda k: abs(k - tx))] - 2.0
        box = np.maximum.reduce([np.abs(x - tx) - TEETH_UP["w"] / 2, (TEETH_UP["top"] - TEETH_UP["h"]) - z, z - (TEETH_UP["top"] + 5), (fy - TEETH_UP["d"]) - y, y - fy])
        f = smin(f, box - 0.8, 0.8)
    for sx in (-1, 1):
        fy = _G["lip"][min(_G["lip"], key=lambda k: abs(k - sx * FANGS_UP["x"]))] - 6.0
        f = smin(f, cone(P, (sx * FANGS_UP["x"], fy, FANGS_UP["top"]), np.array(FANGS_UP["lean"]) * [sx, 1, 1], FANGS_UP["L"], FANGS_UP["r0"], FANGS_UP["r1"]), 1.6)
        f = smin(f, cone(P, (sx * FANGS_LO["x"], FANGS_LO["y"], FANGS_LO["z"]), np.array(FANGS_LO["lean"]) * [sx, 1, 1], FANGS_LO["L"], FANGS_LO["r0"], FANGS_LO["r1"]), 1.6)
    for bx in BEADS["xs"]:
        f = smin(f, np.linalg.norm(P - np.array([bx, BEADS["y"], BEADS["z"]], np.float32), axis=-1) - BEADS["r"], 1.2)
    f = smin(f, ellipsoid(P, **TONGUE), 2.5)
    # nostril nubs
    for sx in (-1, 1):
        f = smin(f, np.linalg.norm(P - np.array([sx * NOSTRILS["x"], NOSTRILS["y"], NOSTRILS["z"]], np.float32), axis=-1) - NOSTRILS["r"], 2.0)
    # the giant eyes: a ball standing proud of its seat, a lid hood over the top-back, a pupil hole
    for sx in (-1, 1):
        e = _n(np.array(EYE["dir"], np.float32) * np.array([sx, 1, 1], np.float32))
        srf = np.array([sx * EYE["x"], _G["eye"], EYE["z"]], np.float32)
        c = srf - e * (EYE["r"] - EYE["proud"])
        q = P - c; along = q @ e
        rr = np.linalg.norm(q, axis=-1)
        f = smin(f, rr - EYE["r"], 3.0)
        lid = smax(rr - EYE["lid_r"], EYE["lid_line"] - q[..., 2], 1.5)
        lid = np.maximum(lid, -6.0 - along)
        f = smin(f, lid, 1.2)
        tip = c + e * EYE["r"]
        hole = np.linalg.norm(P - tip, axis=-1) - EYE["pupil"]
        f = np.maximum(f, np.minimum(-hole, f + EYE["pupil_depth"]))
    # teardrop mounds up the back (ref6)
    bk = y < -40.0
    for T in TEARS:
        d2 = teardrop2d(x, z - T["z"], T["w"], T["h"])
        f = np.where(bk, f - 4.5 * np.sqrt(np.clip(-d2 / 6.0, 0, 1)), f)
    return f

def field(P):
    P = P * np.array([1, -1, 1], np.float32)
    f = base_field(P)
    if PHASE >= 2:
        f = features(f, P)
    return f

def fields(voxel):
    from scipy import ndimage
    h = 0.5 * voxel
    xs = np.arange(-96 + h, 96, voxel, dtype=np.float32)
    ys = np.arange(-118 + h, 116, voxel, dtype=np.float32)
    zs = np.arange(-2 + h, 206, voxel, dtype=np.float32)
    X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")
    f = field(np.stack([X, Y, Z], axis=-1))
    dist = ndimage.distance_transform_edt(f < 0) * voxel
    shell = np.maximum(f, dist - (wall + 0.5 * voxel))
    shell = np.maximum(shell, -Z)                      # open bottom on the bed
    return xs, ys, zs, X, Y, Z, f, shell, dist

def mesh_from(fld, xs, ys, zs, voxel, keep_largest=True):
    eps = 1e-3
    fld = np.where(np.abs(fld) < eps, np.where(fld < 0, -eps, eps), fld).astype(np.float32)
    v, fc, _, _ = measure.marching_cubes(fld, level=0.0, spacing=(voxel, voxel, voxel))
    v += np.array([xs[0], ys[0], zs[0]], np.float32)
    tm = trimesh.Trimesh(v, fc, process=False)
    if keep_largest:
        parts = tm.split(only_watertight=False)
        if len(parts) > 1: tm = sorted(parts, key=lambda m: abs(m.volume), reverse=True)[0]
    tm.fix_normals()
    return tm

if __name__ == "__main__":
    t0 = time.time()
    xs, ys, zs, X, Y, Z, f, shell, dist = fields(VOXEL)
    tm = mesh_from(shell, xs, ys, zs, VOXEL)
    out = f"monster3_p{PHASE}.stl"; tm.export(out)
    e = tm.extents
    print(f"exported {out}: {e[0]:.1f} x {e[1]:.1f} x {e[2]:.1f} mm · {len(tm.faces):,} faces · watertight={tm.is_watertight} · {time.time()-t0:.1f}s · PLA ≈ {abs(tm.volume)/1000*1.24:.0f} g shell")
