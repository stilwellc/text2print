"""
Phase 2 — details on Collin's mesh (mascot_p1.stl, 200 mm). Nothing else changes.
  EYES  ape construction: at each ring centre, probe the skin along the mound normal; cut a spherical cup
        (r SOCK_R, sunk SINK) + a bore for the plug's seat; the eye is a separate PLUG (ball r EYE_R with its
        centre on the cup floor, so it stands EYE_R − SINK proud) printed dome-up.
  TEETH four incisors + two fangs hung from the upper lip at the scan's slit (z ≈ 60), union'd — paint white.
  NOSE  the scan's own oval (x −10…20, z 92–120) — paint pink.
Usage: python mascot_p2.py  → mascot_p2.stl, mascot_eye.stl
"""
import numpy as np, trimesh
T = trimesh.transformations

EYES = [(-27.0, 112.0), (44.0, 110.0)]     # ring centres read off the gridded front render (x, z)
SOCK_R, SINK, EYE_R, CLR = 12.0, 5.0, 9.5, 0.25    # rim Ø19.5 sits inside the scan's Ø22 ring; ball stands 4.5 proud
LID_T = 1.8                                       # lid rim torus tube radius (clean edge round the cup — the ape lesson)
SEAT_D = 10.0                              # bore depth behind the cup floor
PIN_R, PIN_D = 1.7, 6.0                    # plug pin socket (3.4 mm bamboo pin / filament)
MOUTH_Z, FACE_X = 60.0, 6.0
INCISORS = [(-10.5, 6.5, 8.0), (-3.5, 6.5, 9.0), (3.5, 6.5, 9.0), (10.5, 6.5, 8.0)]   # (x offset, width, drop below the slit) — middle pair longer
FANGS = [(-18.5, 3.4, 8.0), (18.5, 3.4, 8.0)]                                         # (x offset, base r, drop) — short blunt canines
TOOTH_FRONT, TOOTH_BACK, TOOTH_IN = -75.5, -64.0, 6.0   # tooth TOP face flush with the upper lip pad (y −76); the row leans out LEAN° so the tips clear the lower lip
PROUD = 1.5                                             # mm the tooth face stands off the scan's own lump
LIP_POCKET = dict(hx=24.0, y_back=-72.0, z0=46.0, z1=61.0, rr=3.0)   # shallow recess in the lower lip roll under the row: the lip tucks BEHIND the teeth (photo overbite)

head = trimesh.load("mascot_p1.stl", force="mesh")
def probe(x, z, d=(0, 1.0, 0), y0=-200.0):
    loc, _, fi = head.ray.intersects_location([[x, y0, z]], [list(d)], multiple_hits=False)
    return loc[0], head.face_normals[fi[0]]

from skimage import measure
def _mc(sdf, lo, hi, res=0.3):
    """mesh an SDF over the box lo..hi (marching cubes at res mm)"""
    ax = [np.arange(lo[i] - 4, hi[i] + 4 + res, res, dtype=np.float32) for i in range(3)]   # margin clears the rounded tip/cap so the surface closes
    X, Y, Z = np.meshgrid(*ax, indexing="ij"); f = sdf(np.stack([X, Y, Z], -1))
    v, fc, _, _ = measure.marching_cubes(f.astype(np.float32), level=0.0, spacing=(res, res, res))
    v += np.array([ax[0][0], ax[1][0], ax[2][0]], np.float32); m = trimesh.Trimesh(v, fc, process=True); m.fix_normals()
    assert m.is_watertight and m.is_volume, "tooth mesh not a volume"; return m
def rounded_box(c, h, rr):
    """box centred c with half-extents h, all edges rounded rr (exact SDF, meshed)"""
    c = np.asarray(c, np.float32); h = np.asarray(h, np.float32)
    def sdf(P):
        q = np.abs(P - c) - (h - rr); return np.linalg.norm(np.maximum(q, 0), axis=-1) + np.minimum(np.max(q, axis=-1), 0) - rr
    return _mc(sdf, c - h, c + h)
def rounded_cone(base, r, drop, tip_r=1.2):
    """downward canine: exact round-cone SDF (Quilez) between a sphere r at the base and a sphere tip_r `drop` below"""
    a = np.asarray(base, np.float32); b = a - np.array([0, 0, drop], np.float32); r1, r2 = float(r), float(tip_r)
    def sdf(P):
        ba = b - a; l2 = float(ba @ ba); rr = r1 - r2; a2 = l2 - rr * rr; il2 = 1.0 / l2
        pa = P - a; y = pa @ ba; z = y - l2; x2 = np.sum((pa * l2 - ba * y[..., None]) ** 2, axis=-1); y2 = y * y * l2; z2 = z * z * l2
        k = np.sign(rr) * rr * rr * x2
        d_tip = np.sqrt(x2 + z2) * il2 - r2; d_base = np.sqrt(x2 + y2) * il2 - r1; d_side = (np.sqrt(x2 * a2 * il2) + y * rr) * il2 - r1
        return np.where(np.sign(z) * a2 * z2 > k, d_tip, np.where(np.sign(y) * a2 * y2 < k, d_base, d_side))
    return _mc(sdf, b - [r, r, 0], a + [r, r, 0])

def sphere(c, r): s = trimesh.creation.icosphere(subdivisions=4, radius=r); s.apply_translation(c); return s
def cyl_along(p0, n, r, length):
    c = trimesh.creation.cylinder(radius=r, height=length, sections=64)
    M = trimesh.geometry.align_vectors([0, 0, 1], n); c.apply_transform(M); c.apply_translation(np.asarray(p0) + np.asarray(n) * length / 2); return c

cuts, lids, log = [], [], []
for ex, ez in EYES:
    p, n = probe(ex, ez); n = n / np.linalg.norm(n)
    # use a smoothed normal: average over a 6 mm patch so a facet doesn't tilt the eye
    ns = [probe(ex + dx, ez + dz)[1] for dx in (-4, 0, 4) for dz in (-4, 0, 4)]; n = np.mean(ns, 0); n /= np.linalg.norm(n)
    floor = p - n * SINK
    cuts.append(sphere(p + n * (SOCK_R - SINK), SOCK_R))                    # the cup
    cuts.append(cyl_along(floor - n * SEAT_D, n, EYE_R + CLR, SEAT_D + 0.5))  # the seat bore, from SEAT_D behind the floor up to the floor
    rim_r = float(np.sqrt(SOCK_R ** 2 - (SOCK_R - SINK) ** 2))
    lid = trimesh.creation.torus(major_radius=rim_r + 0.3, minor_radius=LID_T, major_sections=96, minor_sections=24)
    lid.apply_transform(trimesh.geometry.align_vectors([0, 0, 1], n)); lid.apply_translation(p - n * 0.4); lids.append(lid)
    log.append(f"eye at x {ex:+.0f}: skin ({p[0]:.1f}, {p[1]:.1f}, {p[2]:.1f}) normal {np.round(n, 2)}  cup floor y {floor[1]:.1f}")
out = head
for l in lids: out = out.union(l, engine="manifold")
for c in cuts: out = out.difference(c, engine="manifold")
out = sorted(out.split(only_watertight=False), key=lambda m: -abs(m.volume))[0]   # the cup cut can isolate a sliver of the scan's crater ridge

# teeth: hang from the lip, faces flush with the lip skin at the slit
adds = []
for xo, w, drop in INCISORS:
    x = FACE_X + xo; p, n = probe(x, MOUTH_Z + 2)
    front = probe(x, MOUTH_Z + 4)[0][1] - PROUD                  # face just proud of the scan's own tooth lump at that x
    adds.append(rounded_box((x, (front + TOOTH_BACK) / 2, MOUTH_Z + TOOTH_IN - (drop + TOOTH_IN) / 2), ((w - 0.8) / 2, (TOOTH_BACK - front) / 2, (drop + TOOTH_IN) / 2), 1.6))
for xo, r, drop in FANGS:
    x = FACE_X + xo; p, n = probe(x, MOUTH_Z + 2)
    front = probe(x, MOUTH_Z + 4)[0][1] - PROUD
    adds.append(rounded_cone((x, front + r, MOUTH_Z + TOOTH_IN), r, drop + TOOTH_IN))
for a in adds: out = out.union(a, engine="manifold")
out.export("mascot_p2.stl")
print("\n".join(log)); print(f"mascot_p2.stl: {out.extents.round(1)} · {len(out.faces):,} faces · watertight={out.is_watertight} · bodies={len(out.split(only_watertight=False))}")

# the eye plug: ball r EYE_R on a seat cylinder (r EYE_R, SEAT_D long) with a pin socket; z axis = eye axis, base at z 0
ball = sphere((0, 0, SEAT_D), EYE_R)
seat = trimesh.creation.cylinder(radius=EYE_R, height=SEAT_D, sections=96); seat.apply_translation((0, 0, SEAT_D / 2))
plug = seat.union(ball, engine="manifold")
pin = trimesh.creation.cylinder(radius=PIN_R, height=PIN_D * 2, sections=48)   # centred at z 0 → 6 mm socket into the base
plug = plug.difference(pin, engine="manifold")
plug.export("mascot_eye.stl"); print(f"mascot_eye.stl: {plug.extents.round(1)} · watertight={plug.is_watertight} · print 2, dome up")
