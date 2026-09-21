"""
Sofubi ape-beast head — a shelf bust in the vintage Bullmark / Marusan language.

Sculpted as a signed-distance field rather than CAD primitives: soft masses
smooth-unioned into one form, features cut and added in the field, meshed
with marching cubes. Hollowed in the field itself (a 2 mm shell) and left open
at the neck so it prints upright as a cup with no supports on the outside.

Coordinates: mm, Z up, +Y is the direction the face looks, X is left/right.
The neck base sits on Z = 0 (the print bed).
"""
import sys, time, json, pathlib
import numpy as np
import trimesh
from skimage import measure

# ── PARAMETERS ── all mm ─────────────────────────────────────────────────────
PHASE       = int(sys.argv[1]) if len(sys.argv) > 1 else 1   # 1 base · 2 features · 3 finish
VOXEL       = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0   # 1.0 preview · 0.5 final
wall        = 2.0      # shell thickness (5 perimeters at 0.4 mm)
blend       = 8.0      # smooth-union radius — soft, but the features must READ

# the masses (centre xyz, radii xyz, optional tilt about X in degrees — +tilt
# pitches the front of the mass DOWN). Ape anatomy: a low wide skull, two brow
# ridges with a dip between, eyes sunk beneath them, a nose bridge running
# down to a broad flat nose, and a muzzle that drops forward and DOWN.
shoulders   = dict(c=(0, -6, 4),    r=(74, 56, 36))
neck        = dict(c=(0, -10, 40),  r=(36, 34, 46))
skull       = dict(c=(0, -14, 102), r=(60, 58, 44))              # low and wide, not a ball
brow_l      = dict(c=(-28, 47, 111), r=(35, 22, 17), tilt=-4)   # two heavy ridges, low — the eyes live in their shadow
brow_r      = dict(c=( 28, 47, 111), r=(35, 22, 17), tilt=-4)
scowl_l     = dict(c=(-13, 56, 106), r=(15, 11, 9))              # the inner brows pinch down hard: the scowl
scowl_r     = dict(c=( 13, 56, 106), r=(15, 11, 9))
bridge      = dict(c=(0, 54, 100),  r=(12, 20, 22))              # the nose bridge, glabella down to the nose
nose        = dict(c=(0, 79, 89),   r=(17, 10, 7.5))             # the nose leather: a DISTINCT mass, its front 5 mm proud of the muzzle, added crisp after the main blend
nose_wing_l = dict(c=(-11, 83, 85), r=(8, 6.5, 6))                 # flared alar wings, fronts level with the leather
nose_wing_r = dict(c=( 11, 83, 85), r=(8, 6.5, 6))
nose_fill   = dict(c=(0, 79, 88),   r=(22, 15, 12))                # region where the wall is thickened to 5 mm so the nostrils can be deep
nostril     = dict(r=(6.0, 4.6, 3.6), tilt=32)                   # oblique ovals, outer end higher, real cavities 3.8 mm deep into the 5 mm nose wall
muzzle      = dict(c=(0, 46, 70),   r=(50, 44, 30), tilt=10)     # prognathic: forward and down
upper_lip   = dict(c=(0, 78, 78),   r=(42, 10, 8))               # the curled lip over the mouth, peeled up off the fangs
lip_corner_l = dict(c=(-40, 70, 84), r=(9, 9, 7))               # the corners pull up and back: the sneer
lip_corner_r = dict(c=( 40, 70, 84), r=(9, 9, 7))
jaw         = dict(c=(0, 30, 44),   r=(44, 36, 20))
cheek_l     = dict(c=(-50, 22, 82), r=(18, 30, 34))
cheek_r     = dict(c=( 50, 22, 82), r=(18, 30, 34))
ear_l       = dict(c=(-57, -16, 102), r=(16, 20, 25))            # ears: cupped plugs — the equator sits ON the root plane |x| = 57, so beyond it the ear is a half-egg with no undercut
ear_r       = dict(c=( 57, -16, 102), r=(16, 20, 25))
ear_scoop   = dict(dx=79, y=-6, z=102, r=15)   # dishes the outer face ≈ 9 mm deep, 7 mm of solid left at the centre   # centred OUTSIDE the ear: dishes the outer face 7 mm deep, opening outward — up, when the ear prints on its root                      # the cup, scooped from the outside
crest       = dict(c=(0, 12, 140),  r=(22, 54, 6), tilt=22)
# the oni horns: two in a row down the centreline, rooted on the forehead
# and higher on the skull, both thrust FORWARD 55° off vertical (with the
# face on its back that is 35° off print-vertical and the taper takes the
# underside to ~22°: no overhang), curling up toward the tip, ring grooves
# on the print-up side. Solid-filled. A horn along the forehead normal (24°
# off vertical) would print horizontal — never. Both roots sit well forward
# of the face|cap cut (sculpt y −14).
HORNS = [dict(base=(0, 41.0, 132.5), lean=55.0, L=20.0, r0=6.5, r1=1.5, curl=3.0, grooves=(6.0, 10.0, 14.0)),
         dict(base=(0, 15.9, 143.6), lean=55.0, L=20.0, r0=6.5, r1=1.5, curl=3.0, grooves=(6.0, 10.0, 14.0))]

# features
eye_x, eye_y, eye_z = 26, 56, 104                                # small, set wide and high, sunk beneath the ridges
socket_r, eye_r     = 13.0, 10.5
lid_t               = 2.0
iris_r, pupil_r     = 4.6, 2.5
nostril_r           = 4.5
nostril_x, nostril_y, nostril_z = 10, 85.8, 84.0   # centre 0.8 mm proud of the probed skin (y 85.0 at x 10, z 84)
NOSTRIL_DEPTH = 3.8
mouth       = dict(c=(0, 74, 62),   r=(46, 28, 16))              # the cavity under the lip — a wide snarl
fang_up     = dict(x=28, y=76, z_base=75.5, h=17, r=5.4, tip=1.6, splay=52)   # seat ON the mouth ceiling (cavity top ≈ z 75 at x 28)   # splay = degrees the fang leans forward out of the mouth  # upper fangs: integral, hang from the lip, blunt
fang_lo     = dict(x=23, y=62, z_base=49.5, h=15, r=5.2, tip=1.6, splay=45)   # seat ON the mouth floor (cavity bottom ≈ z 50 at x 23)
FANG_BOSS_R, FANG_BOSS_L = 5.0, 12.0   # seat boss: radius, depth inward along the fang axis
FANG_HOLE_R, FANG_HOLE_D = 1.7, 9.0    # 3.4 mm hole for a 3.0 mm pin
# tooth rows: tapered rounded incisors (not spheres), rooted 2 mm inside the
# lip / jaw and leaning forward like the fangs so that with the face printed on
# its back they climb instead of cantilevering. w×d at the root, h exposed.
teeth_up    = dict(y=84.0, z=77.0, w=6.5, d=4.5, h=8.0, taper=0.42, splay=55, xs=(-16, -8, 0, 8, 16))     # rooted in the lip 1.5 mm above the mouth ceiling (76.9 at y 84), tips hang 6 mm under the lip edge and 2 mm proud of it
teeth_lo    = dict(y=63.0, z=48.5, w=6.0, d=4.2, h=7.5, taper=0.42, splay=55, xs=(-13.5, -4.5, 4.5, 13.5))   # standing on the jaw shelf (floor 48.5 at y 63), the shelf's front edge is y≈67
neck_base_z = 0.0

# the fur: raked strokes running down and back around the head; over the crown
# they run front-to-back instead, so nothing converges into a starburst
fur_amp     = 1.6
fur_pitch   = 4.2
fur_ref_r   = 70.0
face_zone   = dict(c=(0, 66, 92), r=(46, 38, 48))

# print orientation: neck base on the bed, face forward; open bottom
# seam: nowhere to hide it on an organic form — random seam in the slicer

# ── FIELD ────────────────────────────────────────────────────────────────────
def ellipsoid(P, c, r, tilt=0.0):
    """approximate SDF of an ellipsoid, optionally pitched about the X axis"""
    q = P - np.asarray(c, np.float32)
    if tilt:
        t = np.radians(tilt); cs, sn = np.cos(t), np.sin(t)
        y, z = q[..., 1], q[..., 2]
        q = np.stack([q[..., 0], cs * y - sn * z, sn * y + cs * z], axis=-1)
    q = q / np.asarray(r, np.float32)
    k0 = np.linalg.norm(q, axis=-1)
    k1 = np.linalg.norm(q / np.asarray(r, np.float32), axis=-1)
    return k0 * (k0 - 1.0) / np.maximum(k1, 1e-6)

def smin(a, b, k):
    """polynomial smooth minimum — the soft blend between masses"""
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return b + (a - b) * h - k * h * (1.0 - h)

def smax(a, b, k):
    return -smin(-a, -b, k)

def _hash(i, seed):
    v = i[..., 0] * 127.1 + i[..., 1] * 311.7 + i[..., 2] * 74.7 + seed * 17.13
    return np.modf(np.sin(v) * 43758.5453)[0]

def vnoise(P, scale, seed=0.0):
    """value noise on a lattice, trilinear + smoothstep — vectorised, no deps"""
    q = P / scale
    i = np.floor(q); t = q - i; t = t * t * (3 - 2 * t)
    i = i.astype(np.float32)
    def c(dx, dy, dz): return _hash(i + np.array([dx, dy, dz], np.float32), seed)
    x0 = c(0,0,0)*(1-t[...,0]) + c(1,0,0)*t[...,0]; x1 = c(0,1,0)*(1-t[...,0]) + c(1,1,0)*t[...,0]
    x2 = c(0,0,1)*(1-t[...,0]) + c(1,0,1)*t[...,0]; x3 = c(0,1,1)*(1-t[...,0]) + c(1,1,1)*t[...,0]
    y0 = x0*(1-t[...,1]) + x1*t[...,1]; y1 = x2*(1-t[...,1]) + x3*t[...,1]
    return (y0*(1-t[...,2]) + y1*t[...,2]).astype(np.float32)

def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1); return t * t * (3 - 2 * t)

def fur_relief(P):
    """Raked fur: continuous strokes down and back around the head (front-to-
    back over the crown), wobbled so no two run parallel, and gated by a
    coarse noise into long tufts with soft ends. Fades to smooth skin over the
    face. Returns the relief (mm) to push the surface OUT."""
    theta = np.abs(np.arctan2(P[..., 1], P[..., 0]) - np.pi / 2)
    u_side = theta * fur_ref_r - 0.55 * P[..., 2]
    u_top = P[..., 0] * 1.0 + 0.25 * P[..., 1]
    w = smoothstep(118.0, 140.0, P[..., 2])
    u = u_side + (u_top - u_side) * w + 12.0 * vnoise(P, 30.0, 1.0) + 3.0 * vnoise(P, 9.0, 4.0)
    phase = 6.0 * vnoise(P, 17.0, 2.0)
    # SHINGLE profile: with the face part printed on its back, the flank of a
    # stroke that faces the back of the head faces DOWN. A symmetric ridge
    # puts that flank at ~55°; a shingle rises steeply on the front and ramps
    # off the back over most of the pitch, so the downward flank stays under
    # 40° and needs nothing under it.
    # three coats: the crown wears short dense tufts, the sides long raked
    # strokes, the collar a heavy shag — the pitch and relief drift with height
    crown = smoothstep(118.0, 136.0, P[..., 2]); collar = smoothstep(44.0, 26.0, P[..., 2])
    pitch = fur_pitch - 1.4 * crown + 1.4 * collar
    amp = fur_amp - 0.6 * crown + 0.7 * collar
    t = np.modf(u / pitch + phase / (2 * np.pi))[0]              # 0..1 across one stroke, increasing toward the back
    t = np.where(t < 0, t + 1, t)
    # the face|cap seam is at face-y −14. The face part prints on its back
    # (its down is toward the seam), the cap prints back-up (its down is also
    # toward the seam) — so on BOTH sides the shingle must ramp AWAY from the
    # seam: comb the coat forward on the cap, back on the face
    t = np.where(P[..., 1] < -14.0, 1.0 - t, t)
    rise = smoothstep(0.0, 0.18, t)                                 # the front face: up in 18 % of the pitch
    ramp = 1 - smoothstep(0.18, 1.0, t)                             # the back: down over the remaining 82 %
    ridge = rise * ramp
    tuft = smoothstep(0.28, 0.70, vnoise(P, 16.0, 3.0)) * 0.75 + 0.25   # long tufts, soft ends
    mask = smoothstep(0.0, 10.0, ellipsoid(P, **face_zone))
    return amp * ridge * tuft * mask

def cyl_x(P, x0, x1, y, z, r):
    """cylinder along X from x0 to x1"""
    d = np.sqrt((P[..., 1] - y) ** 2 + (P[..., 2] - z) ** 2) - r
    return np.maximum(d, np.maximum(x0 - P[..., 0], P[..., 0] - x1))

def cyl_z(P, x, y, z0, z1, r):
    d = np.sqrt((P[..., 0] - x) ** 2 + (P[..., 1] - y) ** 2) - r
    return np.maximum(d, np.maximum(z0 - P[..., 2], P[..., 2] - z1))

def cone_up(P, x, y, z0, h, r):
    """cone standing on z0, tip at z0 + h"""
    zz = P[..., 2] - z0
    rr = np.sqrt((P[..., 0] - x) ** 2 + (P[..., 1] - y) ** 2)
    return np.maximum(rr - r * (1 - zz / h), np.maximum(-zz, zz - h))

def torus_y(P, c, R, r):
    """torus with its axis along Y (a ring you look into from the front)"""
    q = P - np.asarray(c, np.float32)
    return np.sqrt((np.sqrt(q[..., 0] ** 2 + q[..., 2] ** 2) - R) ** 2 + q[..., 1] ** 2) - r

def tooth_sdf(P, tx, y, z, w, d, h, taper, splay, down, xs=None, rr=1.0):
    """an incisor: a rounded box w×d at the root, shrinking by `taper` toward a
    rounded tip h along its axis; the root runs 1.5 mm back into the gum. Axis =
    down (uppers) or up (lowers), leaning `splay` degrees forward (+y)."""
    q = P - np.array([tx, y, z], np.float32)
    t = np.radians(splay); cs, sn = np.cos(t), np.sin(t)
    if down:
        axis = np.array([0, sn, -cs], np.float32); fwd = np.array([0, cs, sn], np.float32)
    else:
        axis = np.array([0, sn, cs], np.float32); fwd = np.array([0, cs, -sn], np.float32)
    along = q @ axis; fw = q @ fwd; lat = q[..., 0]
    u = np.clip(along / h, 0, 1)
    hx = (w / 2) * (1 - taper * u) - rr; hy = (d / 2) * (1 - taper * u) - rr
    dx = np.abs(lat) - hx; dy = np.abs(fw) - hy; dz = np.maximum(-along - 1.5, along - h) - rr * 0.6 + rr   # root 1.5 mm into a 2.25 mm wall
    dpos = np.sqrt(np.maximum(dx, 0) ** 2 + np.maximum(dy, 0) ** 2 + np.maximum(dz, 0) ** 2)
    return dpos + np.minimum(np.maximum(dx, np.maximum(dy, dz)), 0) - rr

def _cone(q, h, r, tip):
    """cone along local +z from the origin: base radius r at z=0, pad radius `tip` at z=h"""
    zz = q[..., 2]
    rr = np.sqrt(q[..., 0] ** 2 + q[..., 1] ** 2)
    return np.maximum(rr - np.maximum(r * (1 - zz / h), tip), np.maximum(-zz, zz - h))

def cone_down(P, x, y, z_base, h, r, tip, splay=0.0):
    """a fang hanging from (x, y, z_base), leaning `splay` degrees forward (+y)"""
    q = P - np.array([x, y, z_base], np.float32)
    t = np.radians(splay); cs, sn = np.cos(t), np.sin(t)
    # local +z = world direction (0, sin, -cos): down, tilted forward
    ql = np.stack([q[..., 0], cs * q[..., 1] + sn * q[..., 2], sn * q[..., 1] - cs * q[..., 2]], axis=-1)
    return _cone(ql, h, r, tip)

def cone_up_b(P, x, y, z_base, h, r, tip, splay=0.0):
    """a fang standing on (x, y, z_base), leaning `splay` degrees forward (+y)"""
    q = P - np.array([x, y, z_base], np.float32)
    t = np.radians(splay); cs, sn = np.cos(t), np.sin(t)
    ql = np.stack([q[..., 0], cs * q[..., 1] - sn * q[..., 2], sn * q[..., 1] + cs * q[..., 2]], axis=-1)
    return _cone(ql, h, r, tip)

WITH_EARS = True

def field(P):
    P = P * np.array([1, -1, 1], np.float32)      # the face looks toward -Y in the world
    f = ellipsoid(P, **skull)
    for m in (shoulders, neck, brow_l, brow_r, scowl_l, scowl_r, bridge, muzzle, jaw, cheek_l, cheek_r, crest):
        f = smin(f, ellipsoid(P, **m), blend)
    # ears: grown from the skull, then dished from the outside. Built only when
    # WITH_EARS — the head is built without them and the ears are what the
    # with-ears solid has that the bare head does not.
    if WITH_EARS:
        for m in (ear_l, ear_r):
            f = smin(f, ellipsoid(P, **m), 6.0)
        for sx in (-1, 1):
            c = np.array([sx * ear_scoop["dx"], ear_scoop["y"], ear_scoop["z"]], np.float32)
            scoop = np.linalg.norm(P - c, axis=-1) - ear_scoop["r"]
            f = smax(f, -scoop, 3.0)
            # antihelix: a crisp 0.9 mm ridge ringing the cup floor — a band of
            # the scoop sphere's inner shell, 31° ± 3° off the scoop axis
            rr = np.linalg.norm(P - c, axis=-1); axial = -sx * (P[..., 0] - c[0])
            ridge = np.maximum.reduce([rr - ear_scoop["r"], ear_scoop["r"] - 0.9 - rr, np.abs(axial - ear_scoop["r"] * np.cos(np.radians(31))) - 0.75])
            f = np.minimum(f, ridge)
    # the upper lip goes on before the mouth is cut, so the cut shapes its underside
    f = smin(f, ellipsoid(P, **upper_lip), 5.0)
    for m in (lip_corner_l, lip_corner_r):
        f = smin(f, ellipsoid(P, **m), 5.0)
    # eyes: sockets under the ridges, the lid rim, the ball set deep
    for sx in (-1, 1):
        sock = np.linalg.norm(P - np.array([sx * eye_x, eye_y + 5, eye_z], np.float32), axis=-1) - socket_r
        f = smax(f, -sock, 4.0)
        lid = torus_y(P, (sx * eye_x, eye_y - 1, eye_z), socket_r + 0.5, lid_t)
        lid = np.maximum(lid, f - 3.0)
        f = smin(f, lid, 2.5)
        # the eyeball is a PLUG (sofubi_ape_eye.stl, printed dome-up at fine
        # layers for a crisp iris). The head carries its seat: a solid boss
        # behind the socket with a flat cup floor, a 0.25 mm-clearance bore
        # for the plug's skirt and a 3.4 mm pin hole. The boss tapers back at
        # 40° to an apex ON the eye-back rib, so with the face on its back
        # every layer of it sits on the one below.
        f = np.minimum(f, eye_seat(P, sx))
        f = np.maximum(f, -cyl_y_sdf(P, sx * eye_x, eye_z, EYE_FLOOR_Y, EYE_FLOOR_Y + 30.0, eye_r + 0.25))
        f = np.maximum(f, -cyl_y_sdf(P, sx * eye_x, eye_z, EYE_FLOOR_Y - 9.5, EYE_FLOOR_Y + 0.5, 1.7))
    # the nose: leather pad + two alar wings, unioned CRISP so it reads as a
    # nose sitting on the muzzle, then a crease under it to part it from the
    # lip, then two oblique oval nostrils (no rims — rimmed round dimples read
    # as buttons)
    f = smin(f, ellipsoid(P, **nose), 2.5)
    for m in (nose_wing_l, nose_wing_r):
        f = smin(f, ellipsoid(P, **m), 2.5)
    # the horns, each with its ring grooves
    for H in HORNS:
        h = horn_sdf(P, H); f = smin(f, h, 2.5); f = horn_grooves(f, P, h, H)
    # the mouth cavity
    f = smax(f, -ellipsoid(P, **mouth), 5.0)
    # nostrils
    # depth-capped: the oval is cut at most NOSTRIL_DEPTH into the skin
    # wherever it lies (a free ellipsoid + rounded smax went through the
    # 2.25 mm wall and its far rim was a 14 mm² island in the hollow)
    for sx in (-1, 1):
        cut = ellipsoid_roty(P, (sx * nostril_x, nostril_y, nostril_z), nostril["r"], sx * nostril["tilt"])
        f = np.maximum(f, np.minimum(-cut, f + NOSTRIL_DEPTH))
    # teeth — all integral now. Upper fangs hang from the lip with a blunt pad
    # tip and lean against the lip wall, so every layer has something under it.
    # the four fangs are separate plugs (Collin: "teeth make more sense to be
    # their own plugs") — the head carries their seats: a shallow pad where
    # each fang's base lands, so the glue line is a flat ring, not fur
    for tx in teeth_up["xs"]:
        f = smin(f, tooth_sdf(P, tx, down=True, **teeth_up), 1.2)
    for tx in teeth_lo["xs"]:
        f = smin(f, tooth_sdf(P, tx, down=False, **teeth_lo), 1.2)
    # ── crisp toy detailing (designer-sofubi: stamped, not organic) ──────
    # gum lines: a bead along the upper lip edge over the incisor roots, and
    # one along the jaw shelf. Both are embedded a hair into the wall so their
    # lowest print layer touches material (a bead floating 0.3 mm off the
    # ceiling is a two-layer island).
    f = smin(f, capsule_x(P, -19.5, 19.5, 86.5, 76.8, 1.3), 0.8)
    f = smin(f, capsule_x(P, -17.0, 17.0, 66.0, 48.3, 1.2), 0.8)
    return f

EYE_FLOOR_Y = eye_y - 4 - 2.0     # cup floor: 2 mm behind the ball's equator
EYE_SEAT_R  = eye_r + 0.25 + 1.5  # bore + a 1.5 mm wall

def horn_axes(H):
    t = np.radians(H["lean"])
    return np.array(H["base"], np.float32), np.array([0, np.sin(t), np.cos(t)], np.float32), np.array([0, -np.cos(t), np.sin(t)], np.float32)

def horn_sdf(P, H):
    """a chain of 16 spheres along a quadratic curve, radius r0 → r1, smooth-unioned"""
    b, a, u = horn_axes(H); d = None
    for tt in np.linspace(0.0, 1.0, 16):
        c = b + a * H["L"] * tt + u * H["curl"] * tt ** 2
        r = H["r1"] + (H["r0"] - H["r1"]) * (1 - tt) ** 0.85
        sph = np.linalg.norm(P - c, axis=-1) - r
        d = sph if d is None else smin(d, sph, 2.0)
    return d

def horn_grooves(f, P, h, H):
    """ring grooves 0.9 wide × 0.6 deep. The tip-side wall of each faces DOWN in
    the print, so it is a 45° ramp (0.6 → 0 over 0.6 mm), and the grooves stop
    short of the horn's world-top (which faces print-down). Verified on a horn
    alone: 0 mm² steeper than 45°."""
    b, a, u = horn_axes(H); s_along = (P - b) @ a
    q_u = (P - b - a * s_along[..., None]) @ u
    for si in H["grooves"]:
        depth = 0.6 * np.clip((si + 0.75 - s_along) / 0.6, 0.0, 1.0)
        band = np.maximum.reduce([si - 0.45 - s_along, s_along - (si + 0.75), h - 1.0, q_u - 1.0])
        f = np.maximum(f, np.minimum(-band, f + depth))
    return f

def ellipsoid_roty(P, c, r, deg):
    """ellipsoid rotated about its own y axis by `deg` (in the x-z plane)"""
    q = P - np.asarray(c, np.float32)
    t = np.radians(deg); cs, sn = np.cos(t), np.sin(t)
    x, z = q[..., 0], q[..., 2]
    q = np.stack([cs * x + sn * z, q[..., 1], -sn * x + cs * z], axis=-1)
    return ellipsoid(q, (0, 0, 0), r)

def cyl_y_sdf(P, xc, zc, y0, y1, r):
    """cylinder along +y from y0 to y1"""
    rad = np.sqrt((P[..., 0] - xc) ** 2 + (P[..., 2] - zc) ** 2) - r
    return np.maximum(rad, np.maximum(y0 - P[..., 1], P[..., 1] - y1))

def capsule_x(P, x0, x1, y, z, r):
    qx = np.clip(P[..., 0], x0, x1)
    return np.sqrt((P[..., 0] - qx) ** 2 + (P[..., 1] - y) ** 2 + (P[..., 2] - z) ** 2) - r

def eye_seat(P, sx):
    """the eye plug's seat: cylinder r EYE_SEAT_R for 6 mm behind the cup
    floor, then a 40° cone back to an apex on the eye-back rib"""
    rad = np.sqrt((P[..., 0] - sx * eye_x) ** 2 + (P[..., 2] - eye_z) ** 2)
    y = P[..., 1]
    cyl = np.maximum(rad - EYE_SEAT_R, np.maximum(EYE_FLOOR_Y - 6.0 - y, y - EYE_FLOOR_Y))
    h = EYE_SEAT_R / np.tan(np.radians(40.0))
    yc = EYE_FLOOR_Y - 6.0
    cone = np.maximum(rad - EYE_SEAT_R * np.clip((y - (yc - h)) / h, 0, 1), np.maximum(yc - h - y, y - yc))
    return np.minimum(cyl, cone)

def fields(voxel, with_ears=True):
    global WITH_EARS
    WITH_EARS = with_ears
    """the grid, the smooth solid field f, and the hollow shell field — every
    part is cut from `shell` with half-spaces, so the cut faces are exact"""
    from scipy import ndimage
    h = 0.5 * voxel
    xs = np.arange(-86 + h, 86, voxel, dtype=np.float32)
    ys = np.arange(-106 + h, 92, voxel, dtype=np.float32)
    zs = np.arange(-2 + h, 190, voxel, dtype=np.float32)
    X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")
    P = np.stack([X, Y, Z], axis=-1)
    f = field(P)
    inside = f < 0
    dist = ndimage.distance_transform_edt(inside) * voxel
    if PHASE >= 2:
        # the eyeballs are filled solid — but only FORWARD of the socket-floor
        # wall (y > 45.5 sits inside that 2 mm wall), so the fill adds no new
        # surface facing the hollow: no closing dome, no flat bridge, no island
        Pl = P * np.array([1, -1, 1], np.float32)
        # the horn is solid, but only forward of its base plane (the skin):
        # the root sphere's inner half would otherwise be a blob in the hollow
        for H in HORNS:
            b, a, u = horn_axes(H)
            dist = np.where((horn_sdf(Pl, H) < 0.5) & (((Pl - b) @ a) > 1.5), 0.0, dist)
        # the nose wall is 5 mm instead of 2.25 so the nostrils can be real
        # cavities: the step in the inner skin is a 2.75 mm ledge, connected
        # in-plane to the wall, not an island
        dist = np.where(ellipsoid(Pl, **nose_fill) < 0, dist - 2.75, dist)
        for sx in (-1, 1):
            # the eye plug's seat stays solid (the pin hole needs meat around it)
            dist = np.where(eye_seat(Pl, sx) < 0.5, 0.0, dist)
        # the ears are SOLID (3 g each): as parts on a flat root they print as
        # domes; hollow, each was a cup whose inner ceiling closed in mid-air
        if WITH_EARS:
            for m in (ear_l, ear_r):
                dist = np.where(ellipsoid(Pl, m["c"], tuple(r + 1.0 for r in m["r"])) < 0, 0.0, dist)
        f_tex = f - fur_relief(Pl)
        del Pl
    else:
        f_tex = f
    del P
    shell = np.maximum(f_tex, dist - (wall + 0.5 * voxel))
    shell = np.maximum(shell, neck_base_z - Z)
    if PHASE >= 2:
        # fang seats: a boss along each fang's axis grows INWARD from the lip
        # or jaw wall (clipped to the solid, so nothing shows outside), then a
        # 3.4 mm pin hole is bored along the same axis. A 2 mm wall cannot
        # hold a pin; the boss can.
        Pl = np.stack([X, -Y, Z], axis=-1)
        shell0 = shell.copy()
        def wall_along(base, axis):
            """march inward along -axis until the hollow shell's far wall is met"""
            left_wall = False
            for L in np.arange(1.0, 80.0, 0.5):
                q = base - axis * L
                ix, iy, iz = int(np.argmin(np.abs(xs - q[0]))), int(np.argmin(np.abs(ys + q[1]))), int(np.argmin(np.abs(zs - q[2])))
                in_wall = shell0[ix, iy, iz] < 0
                if not left_wall:
                    if not in_wall: left_wall = True      # out of the seat's own wall, into the hollow
                elif in_wall:
                    print(f"    fang boss reaches the far wall at {L:.1f} mm"); return L + 2.5
            print("    fang boss: no far wall found — falling back to the stub"); return FANG_BOSS_L
        for sx in (-1, 1):
            for fg, down in ((fang_up, True), (fang_lo, False)):
                base = np.array([sx * fg["x"], fg["y"], fg["z_base"]], np.float32)
                t = np.radians(fg["splay"])
                axis = np.array([0, np.sin(t), -np.cos(t)], np.float32) if down else np.array([0, np.sin(t), np.cos(t)], np.float32)
                q = Pl - base; along = q @ axis; rad = np.linalg.norm(q - along[..., None] * axis, axis=-1)
                # the boss runs from 1 mm proud of the seat all the way to the far
                # inner wall, so its inner end sits ON that wall instead of
                # floating in the hollow (a stub's tip is a mid-air start when
                # the face prints on its back)
                if True:
                    # both seats are GUM PADS: a post 6 mm long standing on the
                    # cavity wall (ceiling for the uppers, floor for the lowers)
                    # along the fang axis. With the face on its back the axis is
                    # 28° from vertical, so every layer sits on the one below and
                    # the base sits on the wall. The pin socket lives in the pad.
                    # A stub hanging INTO the hollow was a mid-air start every time.
                    # the pad runs 6 mm BACK along its axis too, clipped 0.4 mm
                    # short of the inner skin: a post whose embedded end was a
                    # tilted disc left its lower-rear rim hanging in the mouth
                    # air 2 mm under the ceiling (a 3 mm² island with the face
                    # on its back). Running it back to the wall makes every
                    # print layer of the pad touch wall material.
                    boss = np.maximum(rad - FANG_BOSS_R, np.maximum(-along - 6.0, along - 6.0))
                    boss = np.maximum(boss, dist - (wall - 0.4))
                    shell = np.minimum(shell, np.maximum(boss, 0.0 * f - 1.0))
                    hole = np.maximum(rad - FANG_HOLE_R, np.maximum(-along - 0.5, along - 7.0))
                if False:
                    # the jaw hollow under a lower seat runs straight down into the
                    # neck — nothing for a stub to land on. So the seat is a GUM
                    # PAD rising 6 mm from the mouth floor into the cavity (with
                    # the face on its back that is a post standing on a wall), and
                    # the pin socket lives in the pad.
                    boss = np.maximum(rad - FANG_BOSS_R, np.maximum(-along - 1.5, along - 6.0))   # 1.5 mm into a 2.25 mm wall: never out the other side
                    shell = np.minimum(shell, np.maximum(boss, 0.0 * f - 1.0))          # not clipped: it rises into the cavity on purpose
                    hole = np.maximum(rad - FANG_HOLE_R, np.maximum(-along - 0.5, along - 7.0))
                shell = np.maximum(shell, -hole)
        del Pl
    return xs, ys, zs, X, Y, Z, f, shell, dist

def mesh_from(shellfield, xs, ys, zs, voxel, keep_largest=True):
    verts, faces, _, _ = measure.marching_cubes(shellfield, level=0.0, spacing=(voxel, voxel, voxel))
    verts += np.array([xs[0], ys[0], zs[0]], np.float32)
    tm = trimesh.Trimesh(verts, faces, process=False)
    if keep_largest:
        parts = tm.split(only_watertight=False)
        if len(parts) > 1:
            parts = sorted(parts, key=lambda m: abs(m.volume), reverse=True)
            tm = parts[0]
    tm.fix_normals()
    return tm

def build(voxel):
    xs, ys, zs, X, Y, Z, f, shell = fields(voxel)
    return mesh_from(shell, xs, ys, zs, voxel)

if __name__ == "__main__":
    t0 = time.time()
    tm = build(VOXEL)
    ext = tm.extents
    out = f"kaiju_head_p{PHASE}.stl"
    tm.export(out)
    print(f"exported {out}: {ext[0]:.1f} x {ext[1]:.1f} x {ext[2]:.1f} mm · {len(tm.faces):,} faces · watertight={tm.is_watertight} · {time.time()-t0:.1f}s")
    print(f"volume {abs(tm.volume)/1000:.0f} cm³ · PLA ≈ {abs(tm.volume)/1000*1.24:.0f} g at 100% (shell only, before infill)")
