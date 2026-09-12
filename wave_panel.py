import math, sys
import cadquery as cq

# ── PARAMETERS ── all mm ─────────────────────────────────────────────
tile_w      = 250.0   # tile width  (X, along the run)
tile_d      = 250.0   # tile depth  (Y, up the wall)
cols, rows  = 5, 2    # 5 wide × 2 high → 1250 × 500 run
plate_t     = 4.0     # back plate (4mm so the edge dowel holes keep 1mm walls)
slat_t      = 2.4     # slat thickness at the TIP (X) — the fine edge you see
slat_root   = 3.6     # slat thickness at the ROOT — tapers up to slat_t
root_fillet = 1.5     # concave fillet where each slat meets the plate (prints face-up, no overhang)
slat_pitch  = 12.5    # 20 slats per tile, pitch continuous across joints
h_min       = 8.0     # trough slat height
h_max       = 76.0    # crest slat height (≈3 in)
sample_step = 2.5     # Y sampling of the front edge
crest_power = 1.35    # >1 sharpens crests, widens troughs

# ── Phase 2: mounting + alignment (all in the plate, all hidden between slats) ──
pin_d       = 2.0     # 1.75mm filament dowel + 0.25 (horizontal hole, sag allowance)
pin_depth   = 12.0    # per side → 22mm pins
pin_y       = [40.0, 210.0]      # on the left/right edges
pin_x       = [62.5, 187.5]      # on the top/bottom edges (gap centres)
bed_chamfer = 0.6     # Phase 3: chamfer on the plate's bed edges (elephant foot, clean tile joints)

# print orientation: plate face down on the bed, slats extrude +Z. No overhangs.
# seam: the slicer will pin it on a slat's back vertical edge — hidden in the gap.

RUN_W, RUN_D = tile_w * cols, tile_d * rows

def field(x, y):
    """Height field over the whole run. Two snaking ridges (the reference's curling
    crests) on a floor at h_min, plus a faint swell so the troughs are not dead flat."""
    u = x / RUN_W
    yc1 = RUN_D * 0.5 + 160.0 * math.sin(2*math.pi*1.25*u + 0.3)        # main ridge centreline
    yc2 = RUN_D * 0.5 - 170.0 * math.sin(2*math.pi*1.25*u + 1.2)        # counter ridge
    r1 = math.exp(-((y - yc1) / 95.0) ** 2)
    r2 = 0.72 * math.exp(-((y - yc2) / 62.0) ** 2)
    swell = 0.10 * (0.5 + 0.5 * math.sin(2*math.pi*2.4*u + 0.8))
    g = 1.0 - (1.0 - r1) * (1.0 - r2)                                    # soft max of the ridges
    g = min(1.0, max(0.0, g * (0.90 + 0.10 * math.sin(2*math.pi*0.6*u)) + swell))
    return h_min + (h_max - h_min) * g ** crest_power

def slat(x_local, x_global, y0_global):
    """A slat = (wave prism, YZ profile extruded along X) ∩ (tapered blade, XZ profile
    extruded along Y). The blade is slat_root wide at the plate with a quarter-round
    fillet each side, narrowing to slat_t at the top."""
    ys = [i * sample_step for i in range(int(tile_d / sample_step) + 1)]
    pts = [(0.0, 0.0)] + [(y, field(x_global, y0_global + y)) for y in ys] + [(tile_d, 0.0)]
    wave = (cq.Workplane("YZ", origin=(x_local - slat_root - root_fillet, 0, 0))
            .polyline(pts).close().extrude(2 * (slat_root + root_fillet)))
    H = h_max + 1.0
    f, hr, ht = root_fillet, slat_root / 2, slat_t / 2
    arc = [(-(hr + f) + f * math.sin(a), f - f * math.cos(a)) for a in (math.pi * k / 8 for k in range(0, 5))]
    left = [(-(hr + f), 0.0)] + arc[1:]                       # ends exactly at (-hr, f)
    right = [(-xx, zz) for (xx, zz) in reversed(arc[1:])] + [(hr + f, 0.0)]
    prof = left + [(-ht, H), (ht, H)] + right
    blade = (cq.Workplane("XZ", origin=(x_local, 0, 0)).polyline(prof).close()
             .extrude(-tile_d))          # XZ normal is -Y; extrude toward +Y
    return wave.intersect(blade)

def tile(r, c):
    x0, y0 = c * tile_w, r * tile_d
    plate = (cq.Workplane("XY").box(tile_w, tile_d, plate_t, centered=(False, False, False))
             .edges("<Z").chamfer(bed_chamfer))     # elephant-foot relief on the bed perimeter
    # no screw holes: the tiles are glued to the wall (adhesive or mounting tape); dowels align them
    # filament dowel sockets in the plate edges: left/right (along X), bottom/top (along Y)
    zc = plate_t / 2
    for y in pin_y:
        plate = plate.cut(cq.Workplane().add(cq.Solid.makeCylinder(pin_d / 2, pin_depth + 0.01, cq.Vector(-0.01, y, zc), cq.Vector(1, 0, 0))))
        plate = plate.cut(cq.Workplane().add(cq.Solid.makeCylinder(pin_d / 2, pin_depth + 0.01, cq.Vector(tile_w + 0.01, y, zc), cq.Vector(-1, 0, 0))))
    for x in pin_x:
        plate = plate.cut(cq.Workplane().add(cq.Solid.makeCylinder(pin_d / 2, pin_depth + 0.01, cq.Vector(x, -0.01, zc), cq.Vector(0, 1, 0))))
        plate = plate.cut(cq.Workplane().add(cq.Solid.makeCylinder(pin_d / 2, pin_depth + 0.01, cq.Vector(x, tile_d + 0.01, zc), cq.Vector(0, -1, 0))))
    body = plate
    n = int(round(tile_w / slat_pitch))
    for i in range(n):
        xl = (i + 0.5) * slat_pitch
        body = body.union(slat(xl, x0 + xl, y0).translate((0, 0, plate_t - 0.01)))
    return body

if __name__ == "__main__":
    which = sys.argv[1:] or ["0,0"]
    for w in which:
        r, c = (int(v) for v in w.split(","))
        part = tile(r, c)
        name = f"wave_tile_r{r}_c{c}.stl"
        cq.exporters.export(part, name, tolerance=0.05, angularTolerance=0.2)
        print(f"exported {name}  ({tile_w} x {tile_d} x {plate_t + h_max} mm max)")
