import math
import sys

import cadquery as cq
import manifold3d as m3d
import numpy as np
import trimesh

import megalodon_underside as underside

# Megalodon tooth floating stand — tooth hangs point-down, held only by its two
# side edges in slim V-clips at the ends of a curved "halo" arc that hides behind it.
# Axes: X = left/right, Y = depth (front of display is -Y), Z = up.
# The tooth's mid-plane is Y = 0.

# Usage: python megalodon_stand.py [0.2|0.4]  — nozzle the print is tuned for (default 0.2).
# Outputs carry a _02 / _04 tag. The 0.4 build changes only what the nozzle can feel:
# the joint fit and the underside plate (see megalodon_underside.PROFILES).
NOZZLE = float(sys.argv[1]) if len(sys.argv) > 1 else 0.2
TAG    = f"_{round(NOZZLE * 10):02d}"
underside.use_nozzle(NOZZLE)

# ── PARAMETERS ── all dimensions in mm ─────────────────────────────────
# Tooth — owner's measurements (inches / ounces); these also print on the underside plate
tooth_long_in  = 5.81  # longest edge   (L1)
tooth_short_in = 5.68  # shorter edge   (L2)
tooth_w_in     = 4.43  # widest, across the root (W)
tooth_wt_oz    = 10.55 # weight (WT)
tooth_w      = tooth_w_in * 25.4   # 112.5 mm
crown_h_est  = 115.0   # est. tip to crown base, where width ~ tooth_w

# Edge clips — the only part seen from the front, so kept as small as the grip allows
groove_span  = 100.0   # spacing of the two V-groove bottoms (tooth settles where width = this)
clip_reach   = 6.0     # how far each clip wraps onto the tooth face (= groove depth)
clip_back    = 2.5     # material outboard of the groove bottom
clip_d       = 15.0    # clip front-to-back size
clip_h       = 14.0    # clip height
clip_round   = 3.5     # vertical-edge round (plan view becomes a soft stadium)
clip_soft    = 2.0     # underside round
groove_half  = 40.0    # V half-angle — takes edge thickness up to ~2*reach*tan(40) = 10mm
edge_tilt    = math.degrees(math.atan(tooth_w / 2 / crown_h_est))   # ~26 deg: clips lean with the same crown taper the settle height assumes
clip_cap     = 4.0     # extra height above the top plane, trimmed off so the leaning clip still has a flat print face

# Halo arc — hidden behind the tooth; enters each clip from behind
arc_r        = 5.0     # 10mm tube — same as the rod top, so the junction is seamless
arc_end_x    = 48.5    # arc end, inside the back of each clip
arc_end_y    = 10.0
top_flat     = 1.6     # flat on the halo top; it is the print-bed face (>= r(1 - cos45) keeps the tube under 45 deg)

# Rod
rod_r        = 6.0     # 12mm at the bell throat, tapering to arc_r at the top
post_y       = 32.0    # rod centre behind the tooth plane
tip_z        = 45.0    # tooth tip height above the table — leaves ~12mm under the tip even if the real crown is taller than crown_h_est

# Hidden joint — a D-flat pin on the halo drops into a socket in the rod top; CA glue it (pin + bearing face)
pin_d        = 6.0     # pin diameter; rod top is 10mm, leaving a 1.85mm socket wall
pin_len      = 12.0
pin_flat     = 0.8     # D-flat depth — keys the halo so it can't spin on the rod
pin_tip      = 0.5     # lead-in chamfer on the pin
socket_lead  = 0.4     # lead-in chamfer on the socket mouth (also clears first-layer squish on the halo)
slide_gap    = {0.2: 0.15, 0.4: 0.2}[NOZZLE]   # per side — 0.15 snug on 0.2; 0.2 is the 0.4-nozzle PLA sliding fit. CA glue the joint either way

# Trumpet bell base — centred on the rod; profile r(h) = rod_r + (bell_r - rod_r)(1 - h/bell_h)^flare
bell_r       = 65.0    # mouth radius on the table
bell_h       = 55.0    # flare height, mouth to throat (tangent into the rod)
bell_flare   = 3.5     # higher = sharper trumpet flare at the mouth
bell_lip     = 2.0     # vertical lip at the mouth
bell_chamfer = 0.6     # bed-side edge
bell_soften  = 1.5     # round on the crease where the lip meets the flare

# Underside spec plate (rim seal, tooth drawing with L1/L2/W, weight) — see megalodon_underside.py

# Magnet pockets — two 5mm disc magnets in the bed face, one each side of the tooth drawing.
# Placed on the 3/9 o'clock axis (in line with the rim dots), midway between the dimension
# labels (~21-23mm out) and the inner rim ring (~51mm): ~11mm of plain plastic either side.
# At r=37 the bell is ~11mm tall, so 2.8mm of pocket leaves a 6mm+ roof over the magnet.
mag_d        = 5.0     # magnet diameter
mag_depth    = 2.8     # pocket depth (magnet face flush with the bed face)
mag_x        = 37.0    # pocket centres at (+-mag_x, mag_y) in the plate's reading coordinates
mag_y        = 0.0
mag_fit      = {0.2: 0.15, 0.4: 0.2}[NOZZLE]   # diametral clearance — snug press fit, drop of CA
mag_lead     = 0.3     # lead-in chamfer at the pocket mouth

# ── DERIVED ──────────────────────────────────────────────────────────
settle_h  = crown_h_est * groove_span / tooth_w     # tooth settles here, above its tip
cradle_z  = tip_z + settle_h                         # groove centre height
z_top     = cradle_z + clip_h / 2                    # top of the halo (print bed when flipped)
arc_z     = z_top - (arc_r - top_flat)               # arc centre height = rod top / ball centre

# arc: circle through the rod (0, post_y) and both arc ends
arc_cy = (post_y**2 - arc_end_x**2 - arc_end_y**2) / (2 * (post_y - arc_end_y))
arc_R  = post_y - arc_cy
a0     = math.degrees(math.atan2(arc_end_y - arc_cy, arc_end_x))

# tip clearance over the bell, directly under the tooth tip (post_y from the bell axis)
_u        = ((post_y - rod_r) / (bell_r - rod_r)) ** (1 / bell_flare)
bell_z_at_tip = bell_lip + bell_h * (1 - _u)
tip_gap   = tip_z - bell_z_at_tip

# two printed parts, split where the halo sits on the rod top (z = arc_z):
#   stem  = bell + rod   — prints upright on the bell mouth (a flaring bell never overhangs)
#   halo  = arc + ball + clips + pin — prints upside-down on its top flat (pin points up)
# seam: pinned to the rear (+Y) on both parts

# ── MODEL ────────────────────────────────────────────────────────────
# stem profile in (radius, z), revolved about the rod axis
n_pts   = 24
flare   = [(rod_r + (bell_r - rod_r) * (1 - i / n_pts) ** bell_flare,
            bell_lip + bell_h * i / n_pts) for i in range(n_pts + 1)]
stem = (cq.Workplane("XZ")
        .moveTo(0, 0).lineTo(bell_r, 0).lineTo(bell_r, bell_lip)
        .spline(flare[1:], includeCurrent=True)
        .lineTo(arc_r, arc_z).lineTo(0, arc_z).close()
        .revolve(360, (0, 0, 0), (0, 1, 0))
        .faces("<Z").edges().chamfer(bell_chamfer)
        .edges(cq.selectors.BoxSelector((-bell_r - 1, -bell_r - 1, bell_lip - 0.01),
                                        (bell_r + 1, bell_r + 1, bell_lip + 0.01)))
        .fillet(bell_soften)
        .translate((0, post_y, 0)))


def d_pin(d, length, z0, flat):
    """D-profile cylinder on the rod axis, flat facing -Y (toward the tooth)."""
    r = d / 2
    return (cq.Workplane("XY", origin=(0, post_y, z0))
            .circle(r).extrude(length)
            .cut(cq.Workplane("XY", origin=(0, post_y - r - 5 + flat, z0 - 1))
                 .rect(2 * r + 2, 10).extrude(length + 2)))

# socket: slide_gap all round — the oversize radius alone already moves the flat out by slide_gap
socket = d_pin(pin_d + 2 * slide_gap, pin_len + 0.5, arc_z - pin_len - 0.5, pin_flat)
stem = stem.cut(socket)
# pick the socket-mouth edges by their farthest point from the axis — a box selector tests a circle's
# centre (on the axis), so it would also grab the rod's outer top edge and notch the visible seam
_sr = pin_d / 2 + slide_gap + 0.3
def _mouth_edge(e):
    pts = [e.positionAt(t) for t in (0, 0.25, 0.5, 0.75, 1)]
    return (all(abs(p.z - arc_z) < 0.01 for p in pts)
            and max(math.hypot(p.x, p.y - post_y) for p in pts) < _sr)
stem = stem.newObject([e for e in stem.edges().vals() if _mouth_edge(e)]).chamfer(socket_lead)
pin = (d_pin(pin_d, pin_len + 1, arc_z - pin_len, pin_flat)
       .faces("<Z").edges().chamfer(pin_tip))

ball = cq.Workplane("XY").sphere(arc_r).translate((0, post_y, arc_z))

# arc tube = a revolved circle (torus segment) about the vertical axis at (0, arc_cy)
arc = (cq.Workplane("XZ", origin=(arc_R, 0, 0))
       .circle(arc_r)
       .revolve(180 - 2 * a0, (-arc_R, 0, 0), (-arc_R, 1, 0))
       .rotate((0, 0, 0), (0, 0, 1), a0)
       .translate((0, arc_cy, arc_z)))
for side in (-1, 1):   # rounded tips where the arc tucks into the back of each clip
    # poles turned to face along Y — a pole on the underside tessellates into a pinch
    arc = arc.union(cq.Workplane("XY").sphere(arc_r)
                    .rotate((0, 0, 0), (1, 0, 0), 90)
                    .translate((side * arc_end_x, arc_end_y, arc_z)))

# right-hand clip, built with the groove apex at the origin, opening toward -X
w = math.tan(math.radians(groove_half))
clip = (cq.Workplane("XY")
        .box(clip_reach + clip_back, clip_d, clip_h + clip_cap)
        .edges("|Z").fillet(clip_round)
        .faces("<Z").edges().fillet(clip_soft)
        .translate(((clip_back - clip_reach) / 2, 0, clip_cap / 2)))
v_cut = (cq.Workplane("XY", origin=(0, 0, -clip_h))
         .polyline([(0, 0), (-2 * clip_reach, 2 * clip_reach * w),
                    (-2 * clip_reach, -2 * clip_reach * w)]).close()
         .extrude(2 * clip_h))
clip = (clip.cut(v_cut)
        .rotate((0, 0, 0), (0, 1, 0), edge_tilt)        # lean out at the top, like the edge
        .translate((groove_span / 2, 0, cradle_z)))
clips = clip.union(clip.mirror("YZ"))

# saddle: the halo's underside clears the rod top; the rod's flat top end is the bearing face.
# A round saddle grazes the tube's sides at a shallow angle and leaves feather-thin slivers,
# so it's a square-walled notch through the tube's lower half instead: every cut wall meets
# the tube square-on. Clearance to the rod is slide_gap (+0.1 for the rod taper).
saddle_r = arc_r + 0.1 + slide_gap
saddle = (cq.Workplane("XY", origin=(0, post_y, arc_z - 2 * arc_r))
          .rect(2 * saddle_r, 2 * arc_r + 2).extrude(2 * arc_r))
halo = ball.union(arc).union(clips).cut(stem).cut(saddle).union(pin)
# flat top: trims the arc, ball and clips to one plane for printing upside-down
halo = halo.cut(cq.Workplane("XY").box(400, 400, 50, centered=(True, True, False))
                .translate((0, 0, z_top)))

# ── EXPORT ───────────────────────────────────────────────────────────
def to_manifold(tm):
    m = m3d.Manifold(m3d.Mesh(vert_properties=np.array(tm.vertices, np.float32),
                              tri_verts=np.array(tm.faces, np.int32)))
    assert m.num_tri() > 0, f"manifold conversion failed: {m.status()}"
    return m

# round-trip the stem through the STL exporter (verified watertight); OCC's raw tessellate()
# leaves seams that manifold3d rejects. The plate is cut at mesh level — an OCC boolean of
# text against the spline-revolved bell takes minutes and can fail outright.
cq.exporters.export(stem, f"megalodon_stem{TAG}.stl", tolerance=0.01, angularTolerance=0.1)
inch = underside.INCH if NOZZLE >= 0.4 else " IN"     # 0.4: compact inch mark keeps the dimension lines visible
plate_cut, _ = underside.cutter((0, post_y), labels={
    "L1": f"L1  {tooth_long_in:.2f}{inch}", "L2": f"L2  {tooth_short_in:.2f}{inch}",
    "W": f"W  {tooth_w_in:.2f}{inch}", "WT": f"WT  {tooth_wt_oz:.2f} OZ"})
stem_full = to_manifold(trimesh.load(f"megalodon_stem{TAG}.stl", force="mesh"))
stem_m = stem_full - plate_cut
# magnet pockets: straight bore + a short cone at the mouth, from 1mm below the bed face
_mr = (mag_d + mag_fit) / 2
pockets = [(m3d.Manifold.cylinder(mag_depth + 1, _mr, circular_segments=96).translate([0, 0, -1])
            + m3d.Manifold.cylinder(mag_lead + 1, _mr + mag_lead + 1, _mr, circular_segments=96).translate([0, 0, -1])
            ).translate([side * mag_x, post_y + mag_y, 0]) for side in (-1, 1)]
inlay_m = stem_full ^ plate_cut          # seal body for a two-colour print: exactly what the cut removes
stem_m = stem_m - m3d.Manifold.batch_boolean(pockets, m3d.OpType.Add)
mesh = stem_m.to_mesh()
trimesh.Trimesh(np.array(mesh.vert_properties)[:, :3], np.array(mesh.tri_verts)).export(f"megalodon_stem{TAG}.stl")
mesh = inlay_m.to_mesh()
trimesh.Trimesh(np.array(mesh.vert_properties)[:, :3], np.array(mesh.tri_verts)).export(f"megalodon_stem_inlay{TAG}.stl")
cq.exporters.export(halo, f"megalodon_halo{TAG}.stl", tolerance=0.01, angularTolerance=0.1)
# preview only: two bodies side by side (they share the saddle surface, so no boolean union)
cq.exporters.export(cq.Compound.makeCompound([stem.val(), halo.val()]),
                    f"megalodon_stand_assembled{TAG}.stl",
                    tolerance=0.01, angularTolerance=0.1)
# print-oriented copies: stem centred on its bell mouth; halo flipped onto its top flat
stem_p = trimesh.load(f"megalodon_stem{TAG}.stl", force="mesh")
stem_shift = [-stem_p.bounds.mean(0)[0], -stem_p.bounds.mean(0)[1], -stem_p.bounds[0][2]]
stem_p.apply_translation(stem_shift)
stem_p.export(f"megalodon_stem_print{TAG}.stl")
inlay_p = trimesh.load(f"megalodon_stem_inlay{TAG}.stl", force="mesh")
inlay_p.apply_translation(stem_shift)          # same frame as the body, so the two load as one object
inlay_p.export(f"megalodon_stem_inlay_print{TAG}.stl")
import megalodon_bambu
megalodon_bambu.write_3mf(f"megalodon_stem_2color{TAG}.3mf",
                          [("stem body", stem_p, 1), ("seal inlay", inlay_p, 2)],
                          title="Megalodon stand — stem (2 colour)")
halo_p = trimesh.load(f"megalodon_halo{TAG}.stl", force="mesh")
halo_p.apply_transform(trimesh.transformations.rotation_matrix(math.pi, [1, 0, 0]))
halo_p.apply_translation([-halo_p.bounds.mean(0)[0], -halo_p.bounds.mean(0)[1], -halo_p.bounds[0][2]])
halo_p.export(f"megalodon_halo_print{TAG}.stl")

print(f"tip gap over bell={tip_gap:.1f}  cradle z={cradle_z:.1f}  top z={z_top:.1f}  "
      f"arc R={arc_R:.1f} cy={arc_cy:.1f} span={180 - 2 * a0:.1f}deg  "
      f"max edge thickness={2 * clip_reach * w:.1f}")
