"""
Monster #4 — the green goblin-bat bust (Sep 26 2026).

Reference = Collin's own four renders in refs/monster4/ (front, back, profile,
three-quarter), used "literally, exactly": a low wide skull on a short folded
column; two frog-dome eye mounds on top of the face; a pink nose blob between
them; one tall forward-leaning horn on the crown; two huge swallow-tail bat
ears swept back off the skull sides; a grinning muzzle with four square teeth
and two corner fangs under a rolled upper lip; one fat rolled lower lip.

Proportions MEASURED off the silhouettes (front 0.1835 mm/px, profile 0.1647,
back 0.1907), scaled to 200 mm to the horn tip.

Sculpt frame: mm, Z up, +Y where the face looks; field() flips Y so the face
looks toward −Y in the WORLD (studio_render yaw −152/180/−95 = hero/front/profile).
Pipeline as kaiju_head.py / monster3.py: SDF on a half-voxel-offset grid,
exact-EDT hollowing, marching cubes, largest body.
"""
import sys, time
import numpy as np
import trimesh
from skimage import measure
from kaiju_head import ellipsoid, ellipsoid_roty, smin, smax, smoothstep

PHASE = int(sys.argv[1]) if len(sys.argv) > 1 else 1
VOXEL = float(sys.argv[2]) if len(sys.argv) > 2 else 0.75
wall  = 2.2

# ── FORM (phase 1) ──────────────────────────────────────────────────────────
# the column: a rounded-rect foot 108 wide × 114 deep, z 0–62, two soft folds
COLUMN = dict(hx=50.0, hy=54.0, yc=-4.0, lean=0.06, r=44.0, z1=62.0, flare=4.0)   # profile: neck front 55 at z 45   # leans forward: back edge −61 at the bed, −52 at z 60 (profile photo)
FOLDS  = [dict(z=22.0, amp=1.0, w=8.0), dict(z=42.0, amp=1.0, w=8.0)]
skull   = dict(c=(0, -6, 104), r=(55, 60, 46))        # deep round skull: back y −66, top z 150        # low skull: x ±54, back y −62 (profile photo), top z 144
occiput = dict(c=(0, -30, 98), r=(48, 32, 36))
muzzle  = dict(c=(0, 46, 106), h=(48, 38, 22), rr=18.0)   # deep rounded block: y 8…84, z 84–128, x ±48   # ROUNDED BOX: broad flat front at y 84, z 86–128, x ±46
jowl_l  = dict(c=(-46, 22, 90), r=(20, 34, 26))       # round cheek masses ±66       # jowls ±62 (front photo z 76: ±58; the ear root gives the width above)
jowl_r  = dict(c=( 46, 22, 90), r=(20, 34, 26))
jaw     = dict(c=(0, 36, 72), r=(58, 34, 12))         # the lower jaw mass behind the lip cushion (front y 70), z 60–84         # the fat rolled lower lip: 120 wide, z 58–86, front y 84
chin    = dict(c=(0, 26, 54), r=(42, 24, 12))         # profile: chin front 50 at z 54
brow    = dict(c=(0, 20, 132), r=(44, 28, 14))        # the shelf the mounds sit on
mound_l = dict(c=(-38, 26, 126), r=(22, 22, 21))      # big round eye mounds: tops z 147, fronts y 48, out to ±60      # frog domes, tops at z 147, bulging past the skull sides
mound_r = dict(c=( 38, 26, 126), r=(22, 22, 21))
HORN    = dict(base=(0, 46, 132), tip=(0, 72, 200), r0=19.0, r1=2.6, n=18, k=2.5, pow=0.55)
horn_boss = dict(c=(0, 40, 140), r=(24, 24, 14))     # the crown mound the horn grows out of, top z 154      # the crown mound the horn grows out of   # profile photo: tip at +72
# swallow-tail ears: a plate in its own (s outward, t up) frame, root on the
# skull side, swept back SWEEP° about Z, thick at the root, thin at the edge.
# Upper tip long and sharp (z 170), notch (z 140), broad rounded lower blade (z 108).
EAR = dict(root=(50.0, -18.0, 116.0), sweep=34.0, rise=0.0,
           # outline TRACED from the front render's silhouette (left ear, pitch-corrected), s = (|x|-50)/cos 34°, t = z-116
           poly=[(-10.0, 26.0), (10.1, -39.7), (59.6, -24.2), (75.0, -14.0), (75.3, -8.9), (58.4, 3.5), (56.0, 12.8), (59.1, 20.3), (76.6, 38.5), (75.8, 43.8), (67.8, 45.4), (56.8, 43.5), (10.0, 26.5), (-10.0, -38.0)],
           t_root=34.0, t_edge=16.0, s_max=77.0, lens=45.0, round=2.5, corner=2.5, cup=-0.0010, scale=1.0)
BLEND = 7.0

def _n(v): v = np.asarray(v, np.float32); return v / np.linalg.norm(v)

def rbox(P, c, h, rr):
    q = np.abs(P - np.asarray(c, np.float32)) - (np.asarray(h, np.float32) - rr)
    return np.linalg.norm(np.maximum(q, 0), axis=-1) + np.minimum(np.max(q, axis=-1), 0) - rr

def column_sdf(P):
    x, y, z = P[..., 0], P[..., 1], P[..., 2]; B = COLUMN; r = B["r"]
    fl = B.get("flare", 0.0) * np.clip(1 - z / 30.0, 0, 1) ** 2                       # soft flare at the bed
    dx = np.abs(x) - (B["hx"] + fl - r); dy = np.abs(y - (B["yc"] + B["lean"] * np.clip(z, 0, B["z1"]))) - (B["hy"] + fl - r)
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

def ear_frame(sx):
    sw, ri = np.radians(EAR["sweep"]), np.radians(EAR["rise"])
    root = np.array(EAR["root"], np.float32) * np.array([sx, 1, 1], np.float32)
    e_s = _n([sx * np.cos(sw) * np.cos(ri), -np.sin(sw) * np.cos(ri), np.sin(ri)])   # outward, back, and up
    e_t = _n([-sx * np.cos(sw) * np.sin(ri), np.sin(sw) * np.sin(ri), np.cos(ri)])
    e_n = np.cross(e_s, e_t)                                                        # points to the BACK
    return root, e_s, e_t, e_n

_EAR_POLY = None
def ear_poly():
    """the traced outline with every corner filleted (shapely inward/outward buffer)"""
    global _EAR_POLY
    if _EAR_POLY is None:
        from shapely.geometry import Polygon
        r = EAR["corner"]
        sc = EAR.get("scale", 1.0)
        pg = Polygon([(a_ * sc, b_ * sc) for a_, b_ in EAR["poly"]]).buffer(-r, join_style=1, resolution=6).buffer(r, join_style=1, resolution=6)
        _EAR_POLY = [tuple(p) for p in pg.exterior.coords[:-1]]
    return _EAR_POLY

def ear_sdf(P, sx):
    """a fat fin: polygon in (s, t), puffy lens section reaching full thickness
    `lens` mm in from the outline (C1 profile, no crease), thicker at the root,
    cupped forward toward the tips"""
    root, e_s, e_t, e_n = ear_frame(sx)
    q = P - root; s = q @ e_s; t = q @ e_t; n = q @ e_n + EAR["cup"] * np.maximum(s, 0) ** 2
    d2 = poly_sdf(s, t, ear_poly())
    half = 0.5 * (EAR["t_edge"] + (EAR["t_root"] - EAR["t_edge"]) * (1 - np.clip(s / EAR["s_max"], 0, 1)) ** 1.2)
    u = np.clip(-d2 / EAR["lens"], 0, 1); half = half * np.sqrt(1 - (1 - u) ** 2)   # elliptical section: convex to the edge
    dn = np.abs(n) - half
    d = np.sqrt(np.maximum(d2, 0) ** 2 + np.maximum(dn, 0) ** 2) + np.minimum(np.maximum(d2, dn), 0)
    d = np.maximum(d, -s - 24.0)                       # the fin stops well inside the skull
    return d - EAR["round"]

def horn_sdf(P):
    b, t = np.array(HORN["base"], np.float32), np.array(HORN["tip"], np.float32); d = None
    for k in np.linspace(0, 1, HORN["n"]):
        c = b + (t - b) * k; r = HORN["r1"] + (HORN["r0"] - HORN["r1"]) * (1 - k) ** HORN["pow"]
        s = np.linalg.norm(P - c, axis=-1) - r; d = s if d is None else smin(d, s, HORN["k"])
    return d

_HULL = None
def hull_at(P):
    """signed distance of the visual hull (hull_sdf.npy, WORLD frame) at sculpt-frame points P (y flipped)"""
    global _HULL
    if _HULL is None:
        import json as _j; from scipy import ndimage as _nd
        meta = _j.load(open("hull_meta.json")); _HULL = (np.load("hull_sdf.npy"), meta["grid"], meta["vox"], _nd)
    H, g, v, _nd = _HULL
    Pw = P * np.array([1, -1, 1], np.float32)
    ix = (Pw[..., 0] - (g["x"][0] + 0.5 * v)) / v; iy = (Pw[..., 1] - (g["y"][0] + 0.5 * v)) / v; iz = (Pw[..., 2] - (g["z"][0] + 0.5 * v)) / v
    hv = _nd.map_coordinates(H, [ix.ravel(), iy.ravel(), iz.ravel()], order=1, mode="nearest").reshape(P.shape[:-1]).astype(np.float32)
    return np.where(P[..., 2] < 6.0, -50.0, hv)                 # never let the hull touch the bed (a floor would seal the hollow)

HULL_CARVE = dict(on=False, inset=0.0, k=6.0)   # visual-hull carve tried Sep 27: squashed crown, stub ears, bed ledge — OFF     # the sculpt is built slightly oversize; the hull carves it to the renders' outlines

def base_field(P):
    z = P[..., 2]
    f = ellipsoid(P, **skull)
    f = smin(f, ellipsoid(P, **occiput), BLEND)
    f = smin(f, column_sdf(P), 20.0)                   # the head overhangs the neck with a soft undercut
    f = smin(f, rbox(P, **muzzle), BLEND)
    for m in (jowl_l, jowl_r, chin, brow):
        f = smin(f, ellipsoid(P, **m), BLEND)
    f = smin(f, ellipsoid(P, **jaw), 9.0)
    for m in (mound_l, mound_r):
        f = smin(f, ellipsoid(P, **m), 5.0)
    for sx in (-1, 1):
        f = smin(f, ear_sdf(P, sx), 14.0)
    f = smin(f, ellipsoid(P, **horn_boss), 8.0)
    f = smin(f, horn_sdf(P), 8.0)
    if HULL_CARVE["on"]:
        f = smax(f, hull_at(P) - HULL_CARVE["inset"], HULL_CARVE["k"])
    for F in FOLDS:                                    # the column's soft rolls
        f = f - F["amp"] * np.exp(-((z - F["z"]) / F["w"]) ** 2) * (z < COLUMN["z1"] + 6)
    return f

# ── DETAIL (phase 2) ────────────────────────────────────────────────────────
EYE   = dict(x=37.0, z=122.0, dir=(-0.12, 1.0, -0.12), r=8.0, socket_r=10.0, cup_depth=4.0, lid_t=1.8, iris=(5.0, 4.4, 0.5), pupil=(2.4, 0.8))   # the APE construction: socket + lid rim + eyeball plug on the cup floor
NOSE  = dict(c=(0, 73, 120), r=(16, 15, 10.5))                   # measured: 32 wide, 20 tall, centre z 120, front y 85 (2–3 mm proud)                    # the pink blob, front y 83
# ── THE MOUTH — measured off the front photo crop and the profile edge (Sep 27, "1:1") ──
# smile line: nearly flat at z 84 corner to corner (front photo), teeth hang from it
def slit_h(x): return MOUTH["half_h"] + MOUTH["open_mid"] * np.exp(-(x / MOUTH["open_w"]) ** 2)   # opens in the middle where the teeth show
def z_mouth(x): return 81.5 - 0.0006 * x * x          # slit centre; edge = 85, cushion top = 78 in the middle
MOUTH  = dict(x_half=58.0, half_h=1.5, open_mid=2.0, open_w=30.0, back=60.0, pocket=dict(c=(0, 60, 79), r=(34, 18, 8)))   # the rounded pocket the teeth hang in                    # a thin dark line; the cavity behind the teeth
PADS   = dict(c=(32, 62, 102), r=(34, 22, 15), tilt=8.0, k=10.0)     # pads z 92–118, front 82; the roll below them is the lip      # the pads: flush with the muzzle front (82), z 82–114, soft
PHILTRUM = dict(w=6.0, depth=2.4, z0=86.0, z1=112.0)                # a broad soft dip
LIP_EDGE  = dict(r=3.5, r_end=2.5, proud=-1.0, x_end=58.0, k=10.0, on=True)   # profile: the lip curls IN — roll centre y 75 z 90, front 80, bottom 85     # the pad bottoms round over onto the line
# lower lip cushion (profile edge): top tucked behind the teeth (y ~70 at z 78), bulge front y 80 at z 66, crease z 58; ends rise to z 78 at x ±60
LOWER_LIP = dict(r_mid=11.0, r_end=3.5, z_mid=66.0, z_end=79.0, proud=6.0, x_end=62.0, k=6.0)   # profile: bulge front 80 at z 60–70, crease z 52
CORNER   = dict(x=58.0, z=82.0, r=7.0, depth=2.5)                     # the soft dimple where the lips tuck in at the corner
# incisors: a 30 mm row of four 7.4 mm teeth, faces 7 mm behind the lip plane, middle pair to z 74, outer to z 75.7
TEETH  = dict(xs=(-11.1, -3.7, 3.7, 11.1), bottom=(76.5, 75.0, 75.0, 76.5), w=6.8, d=5.0, setback=9.0, embed=3.0, round=2.3)   # chiclets, visible: faces 4 mm behind the lip, hanging over the cushion
FANGS  = dict(x=18.5, tip_z=72.0, r0=2.9, r1=0.5, lean=(0.10, 0.06, -1.0), embed=2.0, setback=8.0)   # canines just outboard of the row
# ── THE LINES OF THE MOUTH along the cheek (profile + three-quarter photos): polylines in (y, z), x probed on the side skin
CHEEK = dict(   # soft folds (Gaussian valleys, r = half-width) on curved paths read off the profile overlay grid
    mouth_line = dict(pts=((72, 84), (60, 84), (48, 83), (36, 82), (24, 80.5), (12, 79), (4, 78)), r=2.2, depth=2.6),
    pad_crease = dict(pts=((62, 104), (52, 100), (42, 95), (32, 90), (22, 85.5), (12, 81.5), (5, 79)), r=4.0, depth=1.6),
    lip_roll   = dict(pts=((62, 72), (50, 71.5), (38, 72), (26, 72.5), (14, 72.5), (6, 72)), r=(6.0, 5.5, 5.0, 4.5, 4.0, 3.5), proud=2.5),
    lip_crease = dict(pts=((66, 56), (54, 58), (42, 61), (30, 63.5), (18, 65), (8, 66)), r=3.0, depth=2.2),
)
CHIN_FOLD = dict(z=55.0, amp=2.0, w=4.0)   # the crease under the overhanging lower lip (profile: z 52–58)

_G = {}
def _front(x, z):
    """the base skin's front y at (x, z)"""
    ys = np.arange(120, -20, -0.25, dtype=np.float32)
    Q = np.stack([np.full_like(ys, x), ys, np.full_like(ys, z)], -1)
    fq = base_field(Q); i = int(np.argmax(fq < 0)); return float(ys[i])

def tube(P, pts, radii, k=3.0):
    d = None
    for i in range(len(pts) - 1):
        for u in np.linspace(0, 1, 5, endpoint=(i == len(pts) - 2)):
            c = pts[i] + (pts[i + 1] - pts[i]) * u; r = radii[i] + (radii[i + 1] - radii[i]) * u
            s_ = np.linalg.norm(P - c, axis=-1) - r; d = s_ if d is None else smin(d, s_, k)
    return d

def features(f, P):
    x, y, z = P[..., 0], P[..., 1], P[..., 2]
    if "teeth" not in _G:
        _G["teeth"] = {tx: _front(tx, 90.0) for tx in TEETH["xs"] + (-FANGS["x"], FANGS["x"])}
        xs_ = np.arange(-LOWER_LIP["x_end"], LOWER_LIP["x_end"] + 0.1, 3.0)
        _G["lip_lo"] = []
        for tx in xs_:
            u = min(1.0, (tx / LOWER_LIP["x_end"]) ** 2)
            r = LOWER_LIP["r_mid"] + (LOWER_LIP["r_end"] - LOWER_LIP["r_mid"]) * u
            zc_ = LOWER_LIP["z_mid"] + (LOWER_LIP["z_end"] - LOWER_LIP["z_mid"]) * u
            fy = _front(tx, zc_)
            _G["lip_lo"].append((tx, fy - r + LOWER_LIP["proud"], zc_, r))
        _G["lip_edge"] = [(tx, _front(tx, z_mouth(tx) + 6.0)) for tx in np.arange(-LIP_EDGE["x_end"], LIP_EDGE["x_end"] + 0.1, 3.0)]
        print(f"    tooth front y {_G['teeth'][3.7]:.1f} · lip cushion centre y {_G['lip_lo'][len(xs_)//2][1]:.1f} z {_G['lip_lo'][len(xs_)//2][2]:.1f}")
    # the muzzle pads, soft, flush with the muzzle
    for sx in (-1, 1):
        f = smin(f, ellipsoid_roty(P, (sx * PADS["c"][0], PADS["c"][1], PADS["c"][2]), PADS["r"], sx * PADS["tilt"]), PADS["k"])
    # the philtrum: a soft cleft between the pads
    zw = smoothstep(PHILTRUM["z0"] - 4, PHILTRUM["z0"] + 4, z) * (1 - smoothstep(PHILTRUM["z1"] - 6, PHILTRUM["z1"] + 6, z))
    f = f + PHILTRUM["depth"] * np.exp(-(x / PHILTRUM["w"]) ** 2) * zw * (y > 60)
    # the lower lip cushion (a tube along the measured curve)
    d = None
    for tx, cy, cz, r in _G["lip_lo"]:
        s_ = np.sqrt((x - tx) ** 2 + (y - cy) ** 2 + (z - cz) ** 2) - r
        d = s_ if d is None else smin(d, s_, 3.0)
    f = smin(f, d, LOWER_LIP["k"])
    # the slit: a thin dark line the full width, plus the cavity behind the teeth
    zc = z_mouth(x); hh = slit_h(x)
    line = np.maximum.reduce([np.abs(z - zc) - hh, np.abs(x) - MOUTH["x_half"], MOUTH["back"] - y])
    f = smax(f, -(line - 0.8), 0.9)
    f = smax(f, -ellipsoid(P, **MOUTH["pocket"]), 2.0)                  # the dark pocket behind the lips
    # (corner dimples tried and removed — read as holes)
    # (corner dimples tried and removed — read as holes)
    # the upper lip's rounded edge along the line
    d = None
    for tx, fy in _G["lip_edge"]:
        rr = LIP_EDGE["r_end"] + (LIP_EDGE["r"] - LIP_EDGE["r_end"]) * max(0.0, 1 - (tx / LIP_EDGE["x_end"]) ** 2)
        s_ = np.sqrt((x - tx) ** 2 + (y - (fy - rr + LIP_EDGE["proud"])) ** 2 + (z - (z_mouth(tx) + slit_h(tx) + rr - 0.5)) ** 2) - rr
        d = s_ if d is None else smin(d, s_, 3.0)
    if LIP_EDGE.get("on", False): f = smin(f, d, LIP_EDGE["k"])
    # incisors: rounded slabs from inside the lip down to their measured bottoms, faces set back
    for tx, tb in zip(TEETH["xs"], TEETH["bottom"]):
        fy = _G["teeth"][tx] - TEETH["setback"]
        top = z_mouth(tx) + slit_h(tx) + TEETH["embed"]
        rd = TEETH["round"]
        box = np.maximum.reduce([np.abs(x - tx) - (TEETH["w"] / 2 - rd), np.abs(y - (fy - TEETH["d"] / 2)) - (TEETH["d"] / 2 - rd),
                                 (tb + rd) - z, z - top])
        f = np.minimum(f, box - rd)
    # canines just outboard of the row
    for sx in (-1, 1):
        fy = _G["teeth"][sx * FANGS["x"]] - FANGS["setback"]
        top = z_mouth(sx * FANGS["x"]) + slit_h(sx * FANGS["x"]) + FANGS["embed"]
        f = np.minimum(f, cone(P, (sx * FANGS["x"], fy, top), np.array(FANGS["lean"]) * [sx, 1, 1], top - FANGS["tip_z"], FANGS["r0"], FANGS["r1"]))
    # (cheek fold grooves + jaw roll tried Sep 27 and REMOVED: they read as ridges/scratches on the side)
    # the nose, crisp
    f = smin(f, ellipsoid(P, **NOSE), 4.0)
    # eyes: a shallow socket in the mound's front face, a ball standing proud, a pupil dimple
    for sx in (-1, 1):
        e = _n(np.array(EYE["dir"], np.float32) * np.array([sx, 1, 1], np.float32))
        key = f"eye{sx}"
        if key not in _G:                                  # the skin at the eye position, probed from the front
            _G[key] = _front(sx * EYE["x"], EYE["z"]); print(f"    eye {sx:+d} skin y {_G[key]:.1f}")
        S = np.array([sx * EYE["x"], _G[key], EYE["z"]], np.float32)
        # the socket: a spherical cup sunk cup_depth into the mound
        sock = np.linalg.norm(P - (S + e * (EYE["socket_r"] - EYE["cup_depth"])), axis=-1) - EYE["socket_r"]
        f0 = f
        f = smax(f, -sock, 3.0)
        # the lid rim: a torus round the socket mouth, kept to the skin
        lid = torus_axis(P, S - e * 0.5, e, EYE["socket_r"] + 0.3, EYE["lid_t"])
        lid = smax(lid, f0 - 3.0, 2.0)
        f = smin(f, lid, 2.5)
        # the eyeball (a plug at print time): a ball whose centre sits on the cup floor
        ce = S - e * EYE["cup_depth"] + e * 0.5
        ball = np.linalg.norm(P - ce, axis=-1) - EYE["r"]
        f = np.minimum(f, ball)
        # iris ring groove + flat-floored pupil on the dome, along the axis
        q = P - ce; along = q @ e; radial = np.linalg.norm(q - along[..., None] * e, axis=-1)
        R1, R2, dep = EYE["iris"]
        band = np.maximum(radial - R1, R2 - radial); band = np.maximum(band, -along)
        f = np.maximum(f, np.minimum(-band, f + dep))
        pr, pd = EYE["pupil"]
        band = np.maximum(radial - pr, -along)
        f = np.maximum(f, np.minimum(-band, f + pd))
    # a soft fold under the chin
    f = f - CHIN_FOLD["amp"] * np.exp(-((z - CHIN_FOLD["z"]) / CHIN_FOLD["w"]) ** 2) * (y > 0)
    return f

def _side_pts(pts, step=2.0):
    """densify a (y, z) polyline and probe the side skin x at each point (from x = 95 inward)"""
    out = []
    for (y0, z0), (y1, z1) in zip(pts[:-1], pts[1:]):
        n = max(2, int(abs(y1 - y0) / step) + 1)
        for u in np.linspace(0, 1, n, endpoint=False):
            out.append((y0 + (y1 - y0) * u, z0 + (z1 - z0) * u))
    out.append(pts[-1])
    xs = np.arange(95, 0, -0.25, dtype=np.float32)
    res = []
    for (y, z) in out:
        Q = np.stack([xs, np.full_like(xs, y), np.full_like(xs, z)], -1)
        fq = base_field(Q); i = int(np.argmax(fq < 0)); res.append((float(xs[i]), float(y), float(z)))
    return res

def polyline_dist(P, pts):
    d = None
    for (a, b) in zip(pts[:-1], pts[1:]):
        a = np.asarray(a, np.float32); b = np.asarray(b, np.float32); ab = b - a; L2 = float(ab @ ab)
        t = np.clip(((P - a) @ ab) / L2, 0, 1)
        dd = np.linalg.norm(P - (a + t[..., None] * ab), axis=-1); d = dd if d is None else np.minimum(d, dd)
    return d

def torus_axis(P, c, e, R, r):
    q = P - c; along = q @ e
    radial = np.linalg.norm(q - along[..., None] * e, axis=-1)
    return np.sqrt((radial - R) ** 2 + along ** 2) - r

def cone(P, b, a, L, r0, r1, n=12, k=1.8):
    b = np.asarray(b, np.float32); a = _n(a); d = None
    for t in np.linspace(0, 1, n):
        c = b + a * L * t; r = r1 + (r0 - r1) * (1 - t) ** 0.9
        s = np.linalg.norm(P - c, axis=-1) - r; d = s if d is None else smin(d, s, k)
    return d

def field(P):
    P = P * np.array([1, -1, 1], np.float32)
    f = base_field(P)
    if PHASE >= 2:
        f = features(f, P)
    return f

GRID = dict(x=(-142, 142), y=(-100, 92), z=(-2, 206))

def fields(voxel):
    from scipy import ndimage
    h = 0.5 * voxel
    xs = np.arange(GRID["x"][0] + h, GRID["x"][1], voxel, dtype=np.float32)
    ys = np.arange(GRID["y"][0] + h, GRID["y"][1], voxel, dtype=np.float32)
    zs = np.arange(GRID["z"][0] + h, GRID["z"][1], voxel, dtype=np.float32)
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
    # grid must clear the model on every side but the bed
    m = f < 0
    edge = [m[0].any(), m[-1].any(), m[:, 0].any(), m[:, -1].any(), m[:, :, -1].any()]
    if any(edge): print("WARNING: solid touches the grid edge", edge)
    tm = mesh_from(shell, xs, ys, zs, VOXEL)
    SMOOTH = int(__import__("os").environ.get("M4_SMOOTH", "3"))
    if SMOOTH:
        trimesh.smoothing.filter_taubin(tm, lamb=0.5, nu=-0.53, iterations=SMOOTH)   # volume-preserving; kills marching-cubes facets
    out = f"monster4_p{PHASE}.stl"; tm.export(out)
    e = tm.extents
    print(f"exported {out}: {e[0]:.1f} x {e[1]:.1f} x {e[2]:.1f} mm · {len(tm.faces):,} faces · watertight={tm.is_watertight} · {time.time()-t0:.1f}s · PLA ≈ {abs(tm.volume)/1000*1.24:.0f} g shell")
