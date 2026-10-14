import math
import cadquery as cq

# ── PARAMETERS ── all dimensions in mm ──────────────────────────────
# Base (red, reeded ripple texture) — chunky block, wider across than along
base_w      = 78.0   # block width along the tray (X)
base_d      = 86.0   # block depth (Y) — spreads out perpendicular to the box
base_h      = 78.0   # block height
base_edge_r = 8.0    # vertical-edge fillet — chunky-block silhouette

# Tray (white, smooth) — thick chunky box, the dominant mass
tray_l      = 250.0  # tray length (X)
tray_w      = 50.0   # tray width (Y)
tray_h      = 52.8   # tray thickness (48 +10%; the extra sinks into the plinth)
tray_edge_r = 4.0    # vertical-edge fillet — crisp sculptural cube edges

# Pocket — open-top channel through the base; box half-sunk, centered
pocket_gap    = 0.2   # per-side sliding-fit clearance, PLA (fit table)
nest_depth    = 28.8  # box sinks into the base — the +10% height went here,
                      # so the proud height and 102mm total are unchanged
back_overhang = 70.0  # tray beyond the base's -X face (front gets 102mm)

# Die pocket — a real die (dice) is the stick holder; it nests in a square
# recess at the bar's back end, sunk 25% of its height
die_s          = 16.0   # standard board die side (19.0 for casino, 12.0 mini)
die_gap        = 0.2    # per-side nesting clearance, PLA (fit table)
die_sink_pct   = 0.25   # fraction of the die's height sunk into the bar
die_back_inset = 10.0   # pocket's back wall in from the bar's back end

# Ash trough — crisp rectangular recess in the box top, catches the ash trail
trough_w         = 30.0  # recess width
trough_depth     = 7.0   # recess depth below the top face
trough_start_gap = 12.0  # recess starts this far ahead of the socket cube
trough_end_marg  = 14.0  # recess ends this far in from the front end
trough_corner_r  = 2.0   # plan corner radius — keeps corners cleanable

# Magnet pockets — 8×3mm N35 discs, press-fit in the base underside
mag_d      = 8.2    # pocket ⌀  (nominal +0.2, hardware table)
mag_depth  = 3.1    # pocket depth (nominal +0.1)
mag_inset  = 16.0   # pocket center inset from each bottom edge

# derived
tray_z0  = base_h - nest_depth                   # box underside height
tray_cy  = 0.0                                   # centered on the base in Y
tray_x0  = -base_w / 2 - back_overhang           # box back end past the -X face

# print orientation: both parts flat on the bed at Z=0, upright — open-top
# channel means no bridges, no supports on either part
# seam: pin to rear-left vertical edge on both parts — intentional

# ── MODEL ───────────────────────────────────────────────────────────
base = (
    cq.Workplane("XY")
    .box(base_w, base_d, base_h, centered=(True, True, False))
    .edges("|Z").fillet(base_edge_r)
)

# open-top channel through both X faces (overshoots faces and top — no skins)
channel = (
    cq.Workplane("XY", origin=(0, tray_cy, tray_z0 - pocket_gap))
    .box(base_w + 6.0,
         tray_w + 2 * pocket_gap,
         nest_depth + pocket_gap + 1.0,
         centered=(True, True, False))
)
base = base.cut(channel)

# ── magnet pockets, base underside ──────────────────────────────────
mag_pts = [(sx_, sy_) for sx_ in (-(base_w / 2 - mag_inset), base_w / 2 - mag_inset)
           for sy_ in (-(base_d / 2 - mag_inset), base_d / 2 - mag_inset)]
mag_cut = (cq.Workplane("XY", origin=(0, 0, -1.0))
           .pushPoints(mag_pts).circle(mag_d / 2).extrude(mag_depth + 1.0))
base = base.cut(mag_cut)

# ── tray (white bar) — pure box, crisp edges ────────────────────────
tray = (
    cq.Workplane("XY", origin=(tray_x0 + tray_l / 2, tray_cy, 0))
    .box(tray_l, tray_w, tray_h, centered=(True, True, False))
    .edges("|Z").fillet(tray_edge_r)
    .edges(">Z").chamfer(1.0)              # crisp light-catching top edge
)

# die pocket — square recess the die drops into, sunk 25% of its height
pocket_s   = die_s + 2 * die_gap           # pocket side
sink_depth = die_s * die_sink_pct          # 4.0mm for a 16mm die
pocket_x0  = tray_x0 + die_back_inset      # pocket back wall
die_cx     = pocket_x0 + pocket_s / 2      # pocket center
die_pocket = (
    cq.Workplane("XY", origin=(die_cx, 0, tray_h - sink_depth))
    .box(pocket_s, pocket_s, sink_depth + 1.0, centered=(True, True, False))
    .edges("|Z").fillet(1.0)               # dice edges are rounded ≥1mm — fits
)
tray = tray.cut(die_pocket)

# ash trough: crisp rectangular recess in the top face — vertical walls and a
# solid floor, prints upright with no supports
trough_x0 = pocket_x0 + pocket_s + trough_start_gap
trough_x1 = tray_x0 + tray_l - trough_end_marg
trough_cut = (
    cq.Workplane("XY", origin=((trough_x0 + trough_x1) / 2, 0,
                               tray_h - trough_depth))
    .box(trough_x1 - trough_x0, trough_w, trough_depth + 1.0,
         centered=(True, True, False))
    .edges("|Z").fillet(trough_corner_r)
)
tray = tray.cut(trough_cut)

# elephant-foot relief on the bed edge
tray = tray.edges("<Z").chamfer(0.5)

# ── EXPORT ── two separate prints + a visual-only assembly ──────────
cq.exporters.export(base, "incense_plinth_red.stl", tolerance=0.01, angularTolerance=0.1)
cq.exporters.export(tray, "incense_bar_white.stl", tolerance=0.01, angularTolerance=0.1)
cq.exporters.export(base, "incense_plinth_red.step")
cq.exporters.export(tray, "incense_bar_white.step")

assembly = base.union(tray.translate((0, 0, tray_z0)))
cq.exporters.export(assembly, "assembly.stl", tolerance=0.01, angularTolerance=0.1)
print(f"base {base_w}x{base_d}x{base_h}  tray {tray_l}x{tray_w}x{tray_h}  "
      f"die pocket {pocket_s:.1f}sq x{sink_depth:.1f}  "
      f"magnets {len(mag_pts)}x⌀{mag_d}x{mag_depth}")
