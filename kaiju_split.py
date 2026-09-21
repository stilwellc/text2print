"""
The bust in three printable parts, cut from the same field as the one-piece
model so the seams are exact planes:

  base   z < 24                      the collar: prints upright, open bottom — a ring
  neck   24 < z < 42                 the neck and lower jaw: prints INVERTED (top
                                     cut on the bed) so the jaw's flare narrows
                                     as it rises and supports itself
  face   z > 42, world y < 32        prints lying on its BACK (the cut face
                                     down): the brow shelf, muzzle underside
                                     and mouth ceiling all turn vertical; the
                                     splayed fangs point up
  cap    z > 42, world y > 32        the back of the skull — a dome on its cut

Joints carry 6 mm pins in bosses that grow INWARD from the shell wall (the
outside stays clean): three in the neck, four across the head. Every part is
exported already rotated into its print orientation, cut face at z = 0.
"""
import sys, json, numpy as np, trimesh
sys.argv = [sys.argv[0], "2", sys.argv[1] if len(sys.argv) > 1 else "0.5"]
import kaiju_head as K
T = trimesh.transformations

VOXEL   = float(sys.argv[2])
Z_BASE  = 24.0      # base | neck: the collar top, the fur hides it
Z_NECK  = Z_BASE    # no neck ring: the chin's underside only prints cleanly on the face part lying on its back, so face and cap run down to the collar
Y_CUT   = 14.0      # face | cap at the skull's widest line (world y): forward of it every surface faces forward or sideways
PIN_R, HOLE_R, BOSS_R, PIN_L = 3.0, 3.2, 6.5, 18.0
BASE_PINS = [(-50, -20), (50, -20), (0, 50)]              # (x, world y) on the collar wall at z = 24
NECK_PINS = [(-30, -14), (30, -14), (0, 34)]              # (x, world y) on the neck wall at z = 42
HEAD_PINS = [(-40.8, 131.7), (40.8, 131.7), (-40.8, 72.3), (40.8, 72.3)]   # (x, z) on the skull wall at the y cut

def cyl_z(X, Y, Z, x, y, z0, z1, r):
    return np.maximum(np.sqrt((X - x) ** 2 + (Y - y) ** 2) - r, np.maximum(z0 - Z, Z - z1))
def cyl_y(X, Y, Z, x, z, y0, y1, r):
    return np.maximum(np.sqrt((X - x) ** 2 + (Z - z) ** 2) - r, np.maximum(y0 - Y, Y - y1))

TRANSFORMS = {}
def orient(tm, up, name=None):
    """rotate so the world direction `up` becomes +z, then seat on z = 0"""
    up = np.asarray(up, float); up /= np.linalg.norm(up)
    if abs(up[2]) < 0.999: R = T.rotation_matrix(np.arccos(np.clip(np.dot(up, [0, 0, 1]), -1, 1)), np.cross(up, [0, 0, 1]))
    elif up[2] > 0: R = np.eye(4)
    else: R = T.rotation_matrix(np.pi, (1, 0, 0))
    tm.apply_transform(R); dz = -tm.bounds[0][2]; tm.apply_translation((0, 0, dz))
    M = T.translation_matrix((0, 0, dz)) @ R
    if name: TRANSFORMS[name] = M.tolist()
    return tm

def overhang_report(tm):
    n = tm.face_normals; a = tm.area_faces; tot = a.sum(); dz = n[:, 2]
    return {">45": round(100 * a[dz < -np.sin(np.radians(45))].sum() / tot, 1), ">70": round(100 * a[dz < -np.sin(np.radians(70))].sum() / tot, 2)}

xs, ys, zs, X, Y, Z, f, shell, dist = K.fields(VOXEL, with_ears=False)      # the bare head (+ wall depth from the skin)
_, _, _, _, _, _, f_ears, shell_ears, _ = K.fields(VOXEL, with_ears=True)  # the same head wearing its ears

# ── pin bosses ──────────────────────────────────────────────────────────────
# A boss floating in the hollow starts in mid-air and the print fails there
# (the first split did exactly that — three bosses in the void). So every boss
# is placed ON the inner wall, found by probing the smooth field at the cut
# height, overlapping the wall by 40%, and the ring parts' bosses run the full
# height of the ring so they start on the bed.
shell0 = shell.copy()   # the hollow shell BEFORE bosses — the wall is where this goes negative

def wall_point(zc, ang):
    """inner-wall point at height zc in direction `ang` (radians, from +x), by
    marching outward from the centreline until the smooth solid is entered"""
    iz = int(np.argmin(np.abs(zs - zc)))
    cx, cy = 0.0, -8.0
    for r in np.arange(0, 90, 0.5):
        x, y = cx + r * np.cos(ang), cy + r * np.sin(ang)
        ix, iy = int(np.argmin(np.abs(xs - x))), int(np.argmin(np.abs(ys - y)))
        if shell0[ix, iy, iz] < 0: return x, y     # first WALL voxel = the inner skin (f is solid everywhere inside — wrong field to probe)
    return cx + 40 * np.cos(ang), cy + 40 * np.sin(ang)

def z_boss(zc, ang, z0, z1):
    global shell
    wx, wy = wall_point(zc, ang)
    # the boss centre sits inside the wall line by 40 % of its radius, so 60 % hangs inward, attached
    bx, by = wx - 0.4 * BOSS_R * np.cos(ang), wy - 0.4 * BOSS_R * np.sin(ang)
    shell = np.minimum(shell, np.maximum(cyl_z(X, Y, Z, bx, by, z0, z1, BOSS_R), f))
    shell = np.maximum(shell, -cyl_z(X, Y, Z, bx, by, zc - 10, zc + 10, HOLE_R))
    return bx, by

# base | neck at z = 24: three bosses, full ring height on both sides
BASE_PIN_ANGLES = [np.radians(a) for a in (200, 340, 90)]
NECK_PIN_ANGLES = [np.radians(a) for a in (215, 325, 90)]
placed = {}
for ang in BASE_PIN_ANGLES:
    bx, by = z_boss(Z_BASE, ang, 0.0, Z_BASE + 14)
    placed.setdefault("base", []).append((bx, by))
    # head-side foot: a slab from the boss to the face|cap cut plane, inside the wall, so the
    # receiver stands on that part's bed instead of hanging 1–2 mm above it
    y0, y1 = (min(by, Y_CUT), max(by, Y_CUT))
    foot = np.maximum.reduce([np.abs(X - bx) - BOSS_R, y0 - Y, Y - y1, Z_BASE - Z, Z - (Z_BASE + 14)])
    shell = np.minimum(shell, np.maximum(foot, f))
    shell = np.maximum(shell, -cyl_z(X, Y, Z, bx, by, Z_BASE - 10, Z_BASE + 10, HOLE_R))

# face | cap at y = 32: bosses start on the bed of each part (the cut face) —
# placed on the skull wall the same way, probing in the x/z plane
def y_boss(xc, zc):
    global shell
    iy = int(np.argmin(np.abs(ys - Y_CUT)))
    ang = np.arctan2(zc - 100.0, xc)
    for r in np.arange(0, 90, 0.5):
        x, z = r * np.cos(ang), 100.0 + r * np.sin(ang)
        ix, iz = int(np.argmin(np.abs(xs - x))), int(np.argmin(np.abs(zs - z)))
        if shell0[ix, iy, iz] < 0: break
    bx, bz = x - 0.4 * BOSS_R * np.cos(ang), z - 0.4 * BOSS_R * np.sin(ang)
    shell = np.minimum(shell, np.maximum(cyl_y(X, Y, Z, bx, bz, Y_CUT - 14, Y_CUT + 14, BOSS_R), f))
    shell = np.maximum(shell, -cyl_y(X, Y, Z, bx, bz, Y_CUT - 10, Y_CUT + 10, HOLE_R))
    return bx, bz
for xc, zc in HEAD_PINS: placed.setdefault("head", []).append(y_boss(xc, zc))
print("bosses placed on the wall:", {k: [(round(a, 1), round(b, 1)) for a, b in v] for k, v in placed.items()})

# ── internal ribs for the face part ──────────────────────────────────────────
# Lying on its back, the face part has three inverted bowls inside the hollow
# whose apexes start in mid-air: the back wall of the mouth (60 mm², 34 mm
# from anything) and one beside each eye socket. A 2 mm rib from each apex
# straight back to the cut plane (that part's bed) gives every layer
# something to build on. The ribs are clipped to the inside of the solid so
# nothing shows outside, and they cost about 4 g between them.
RIB_T = 2.0
FACE_RIBS = [  # (x, z0, z1) — each rib spans world y from -Y_REACH to the y = 32 cut
    (0.0, 54.0, 71.0),      # under the mouth's back wall
    (-39.4, 88.0, 97.0),    # beside the left eye socket (the pocket moved outboard with the eyes)
    (39.4, 88.0, 97.0),     # beside the right eye socket
    (-26.0, 100.0, 108.0),  # behind the left eyeball — its back is an inverted bowl to the hollow
    (26.0, 100.0, 108.0),   # behind the right eyeball
]
for rx, rz0, rz1 in FACE_RIBS:
    rib = np.maximum.reduce([np.abs(X - rx) - RIB_T / 2, -48.0 - Y, Y - Y_CUT, rz0 - Z, Z - rz1])
    shell = np.minimum(shell, np.maximum(rib, f + 0.5))   # inside the smooth solid only, half a mm shy of its skin

# ── the ears: PLUGS with a flat root. Each ear is the with-ears solid beyond
#    the plane |x| = X_ROOT (3 mm inside the skull at the ear's centre), within
#    the ear's own footprint; it carries the patch of skull skin it displaces,
#    so its outer surface runs into the head's without a step. The head gets
#    the matching opening — a real sofubi ear-plug joint — and a 6 mm pin boss
#    inside. Flat root = full first layer on the bed, no mid-air start.
def cyl_x(X, Y, Z, x0, x1, y, z, r):
    return np.maximum(np.sqrt((Y - y) ** 2 + (Z - z) ** 2) - r, np.maximum(x0 - X, X - x1))
X_ROOT = 57.0
EAR_PIN_Y, EAR_PIN_Z = 16.0, 102.0   # world y, z (the ear centre)
Pw = np.stack([X, -Y, Z], axis=-1)   # face frame for the footprint ellipsoids
foot_l = K.ellipsoid(Pw, K.ear_l["c"], tuple(r + 2.5 for r in K.ear_l["r"]))
foot_r = K.ellipsoid(Pw, K.ear_r["c"], tuple(r + 2.5 for r in K.ear_r["r"]))
del Pw
def ear_field(sx):
    foot = foot_l if sx < 0 else foot_r
    return np.maximum.reduce([shell_ears, X_ROOT - sx * X, foot])
# the seam lives INSIDE the ear: the head keeps the inner part of each ear
# as a solid stump ending in a flat top on the root plane, and the plug sits
# on that. The ear skin runs continuously across a planar part line — a
# real sofubi seam — instead of a flat-backed plug hovering 8 mm over the
# curved skull at the ear's top and bottom edges. The stump is only the ear
# material OUTSIDE the bare skull (f > −0.5), so it adds ~4 g a side, not
# the 21 g half-ellipsoid buried in the hollow. Its faces are vertical in
# both head prints (the plane is |x| = const, the skin faces ±x).
head_minus_ears = shell.copy()
for sx, foot in ((-1, foot_l), (1, foot_r)):
    stump = np.maximum.reduce([shell_ears, foot, sx * X - X_ROOT, -f - 0.5])
    head_minus_ears = np.minimum(head_minus_ears, stump)
    opening = np.maximum(X_ROOT - sx * X, foot)                                  # beyond the root plane, inside the footprint
    head_minus_ears = np.maximum(head_minus_ears, -opening)                      # the opening in the skull
    x0, x1 = (40.0, X_ROOT + 0.5) if sx > 0 else (-(X_ROOT + 0.5), -40.0)
    boss = cyl_x(X, Y, Z, x0, x1, EAR_PIN_Y, EAR_PIN_Z, BOSS_R)
    head_minus_ears = np.minimum(head_minus_ears, np.maximum(boss, np.maximum(f, -opening)))   # inside the bare head, not in the opening
    hx0, hx1 = (44.0, X_ROOT + 2) if sx > 0 else (-(X_ROOT + 2), -44.0)
    head_minus_ears = np.maximum(head_minus_ears, -cyl_x(X, Y, Z, hx0, hx1, EAR_PIN_Y, EAR_PIN_Z, HOLE_R))

# ── cap ribs: the inside of the skull dome is a wide, flat-ish ceiling when the
#    cap prints back-up. Two 2 mm ribs from the cut plane to the inner apex
#    turn it into four short bridges. Hidden inside.
for rib in (np.maximum.reduce([np.abs(X) - 0.6, Y_CUT - Y, 88.0 - Z, Z - 150.0]),
            np.maximum.reduce([np.abs(Z - 108.0) - 0.6, Y_CUT - Y, np.abs(X) - 48.0])):   # 1.2 mm = 3 perimeters, enough to anchor bridges
    shell_ribbed = np.maximum(rib, f + 0.5)
    head_minus_ears = np.minimum(head_minus_ears, shell_ribbed)

# ── the seams: flat butt joints, pinned, with a chamfered V at the visible line
# A tongue-and-groove was tried and rejected: both big parts print standing
# on their cut faces, so whichever part carries the tongue stands on the
# tongue alone (the face's bed contact fell from 1,332 to 254 mm²) and every
# internal rib on the groove part starts 2 mm in the air. The three pins per
# seam already register the parts and are not rotationally symmetric. Both
# outer edges get a 0.7 mm chamfer, so the skins meet in a small V: a seam
# that reads as a seam, the way vinyl ones do, and a home for the elephant's
# foot instead of a step to fill.
TONGUE, CLEAR_AX, CHAMF = 0.0, 0.0, 0.7
y_face = Y_CUT; y_cap = Y_CUT; z_base = Z_BASE; z_head = Z_BASE
ch_face = CHAMF - dist - (Y_CUT - Y)
ch_cap  = CHAMF - dist - (Y - Y_CUT)
ch_base = CHAMF - dist - (Z_BASE - Z)
ch_head = CHAMF - dist - (Z - Z_BASE)
def chamfer(fld, term): return np.maximum(fld, term)

# ── the base is a cup: a 2 mm solid floor on the bed. A full first layer for
#    adhesion, and a pocket for a steel bar or a bag of sand before the head
#    goes on — 160 g of face wants ballast under it.
FLOOR = 1.6
base_fld = np.maximum(head_minus_ears, Z - z_base)
base_fld = np.minimum(base_fld, np.maximum.reduce([f, Z - FLOOR, -Z]))   # clipped at the bed, or the floor runs off the grid's bottom and the mesh is open

parts = {
    "base": (chamfer(base_fld, ch_base), (0, 0, 1)),
    "face": (chamfer(chamfer(np.maximum(np.maximum(head_minus_ears, z_head - Z), Y - y_face), ch_face), ch_head), (0, -1, 0)),
    "cap":  (chamfer(chamfer(np.maximum(np.maximum(head_minus_ears, z_head - Z), y_cap - Y), ch_cap), ch_head), (0, 1, 0)),
    "ear_left":  (np.maximum(ear_field(-1), -cyl_x(X, Y, Z, -(X_ROOT + 9), -(X_ROOT - 1), EAR_PIN_Y, EAR_PIN_Z, HOLE_R)), (-1, 0, 0)),
    "ear_right": (np.maximum(ear_field( 1), -cyl_x(X, Y, Z, X_ROOT - 1, X_ROOT + 9, EAR_PIN_Y, EAR_PIN_Z, HOLE_R)), (1, 0, 0)),
}
report = {}
for name, (fld, up) in parts.items():
    tm = K.mesh_from(fld, xs, ys, zs, VOXEL)
    tm = orient(tm, up, name)
    tm.export(f"sofubi_ape_{name}.stl")
    oh = overhang_report(tm)
    g = abs(tm.volume) / 1000 * 1.24
    import manifold3d as m3d
    mm = trimesh.Trimesh(tm.vertices, tm.faces, process=True)
    st = m3d.Manifold(m3d.Mesh(vert_properties=np.asarray(mm.vertices, np.float32), tri_verts=np.asarray(mm.faces, np.int32))).status()
    report[name] = {"manifold3d": str(st), "mm": [round(float(v), 1) for v in tm.extents], "g": round(g), "faces": len(tm.faces), "watertight": bool(tm.is_watertight), "overhang": oh}
    print(f"{name:5} {tm.extents[0]:6.1f} x {tm.extents[1]:6.1f} x {tm.extents[2]:6.1f} mm  {g:4.0f} g  {len(tm.faces):>9,} faces  manifold3d={st}  overhang >45° {oh['>45']}%  >70° {oh['>70']}%")

pin = trimesh.creation.cylinder(radius=PIN_R, height=PIN_L, sections=48); pin.apply_translation((0, 0, PIN_L / 2))
pin.export("sofubi_ape_pin.stl"); print(f"pin   {PIN_R*2:.0f} x {PIN_L:.0f} mm  · print 9")

# ── the fangs: blunt cones that print BASE DOWN, tip up — a cone narrowing
#    upward has no overhang anywhere. A 3.4 mm socket in the base takes a
#    3 mm pin; the matching socket is bored into the lip / jaw seat.
def fang(h, r, tip, curl=3.2, squash=0.88):
    """a sabre canine, printed base-down tip-up. Profile: a 1.2 mm gum collar
    wider than the seat pad (hides the glue line), a convex body that stays fat
    through the lower half, then a point with a rounded end. The body then bends
    `curl` mm toward local +y above the pin socket (quadratic, so the bend is
    gentlest where the socket is) and is squashed to 0.88 across x so the
    section is an oval, not a circle. Every face still tilts upward: the taper
    (≥13°) outruns the lean (≤27°), so nothing overhangs even on the inside of
    the curve."""
    from scipy.interpolate import PchipInterpolator
    us = np.array([0.0, 0.18, 0.40, 0.60, 0.78, 0.90, 0.97, 1.0])
    rs = np.array([1.00, 0.96, 0.84, 0.64, 0.40, 0.21, 0.08, 0.0]) * r
    body = PchipInterpolator(us, rs)
    prof = [(0, 0), (r + 0.8, 0), (r + 0.8, 0.8), (r + 0.3, 1.4)]
    for u in np.linspace(0.08, 1.0, 46):
        prof.append((float(max(body(u), 0.0)), float(1.4 + u * (h - 1.4))))
    prof[-1] = (0.0, float(h))
    cone = trimesh.creation.revolve(prof, sections=96)
    sock = trimesh.creation.cylinder(radius=K.FANG_HOLE_R, height=5.0, sections=48); sock.apply_translation((0, 0, 2.0))
    m = cone.difference(sock, engine="manifold")
    v = m.vertices.copy(); z0 = 4.8
    s = np.clip((v[:, 2] - z0) / (h - z0), 0, 1)
    v[:, 1] += curl * s ** 2; v[:, 0] *= squash
    m.vertices = v; return m
for name, fg in (("fang_upper", K.fang_up), ("fang_lower", K.fang_lo)):
    m = fang(fg["h"], fg["r"], fg["tip"]); m.export(f"sofubi_ape_{name}.stl")
    n = m.face_normals; down = n[:, 2] < -np.sin(np.radians(45)); bed = m.triangles_center[:, 2] < 0.3
    print(f"{name:11} {m.extents[0]:5.1f} x {m.extents[1]:5.1f} x {m.extents[2]:5.1f} mm  · print 2 · base down, tip up · curl toward +y · faces >45° overhang: {m.area_faces[down & ~bed].sum():.1f} mm²")
tp = trimesh.creation.cylinder(radius=1.5, height=11.0, sections=48); tp.apply_translation((0, 0, 5.5)); tp.export("sofubi_ape_pin_tooth.stl")
print("pin_tooth   3 x 11 mm  · print 4")
json.dump(report, open("split_report.json", "w"), indent=1)
json.dump(TRANSFORMS, open("split_transforms.json", "w"))
