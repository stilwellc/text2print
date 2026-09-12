import math, sys
import cadquery as cq

# ── PARAMETERS ── all mm ─────────────────────────────────────────────
RUN_IN_W, RUN_IN_D = 48.0, 14.0          # the wall opening, inches
cols, rows  = 6, 2                       # 6 wide × 2 high (203 × 178 mm tiles sit easily on the 256 bed)
tile_w      = RUN_IN_W * 25.4 / cols     # 203.2 mm
tile_d      = RUN_IN_D * 25.4 / rows     # 177.8 mm
SCALE_X     = (RUN_IN_W * 25.4) / 1250.0 # the field is authored at 1250 × 500 and stretched to fit
SCALE_Y     = (RUN_IN_D * 25.4) / 500.0
SCALE       = SCALE_X                    # kept for older references
plate_t     = 4.0     # back plate (4mm so the edge dowel holes keep 1mm walls)
slat_t      = 4.8     # slat TIP thickness: 0.8 nozzle → one 0.8 wall each side + 3.2 core (multiples of the line)
slat_root   = 6.4     # slat ROOT thickness (0.8 multiples)
root_fillet = 2.0     # concave fillet where each slat meets the plate (prints face-up, no overhang)
crest_chamfer = True  # knife-edge crests: 45° flanks both sides, following the wave (prints face-up)
slats_per   = 9
slat_pitch  = tile_w / slats_per   # 9 slats per tile ≈ 22.6 mm pitch (the reference's spacing), continuous across joints
h_min       = 6.0     # trough slat height
h_max       = 50.0    # crest slat height (2 in; peaks add on top)
sample_step = 2.5     # Y sampling of the front edge
crest_power = 1.4     # >1 sharpens crests, widens troughs

# ── Phase 2: mounting + alignment (all in the plate, all hidden between slats) ──
pin_d       = 2.2     # 1.75mm filament dowel + 0.45 (horizontal hole, 0.8-nozzle sag allowance)
pin_depth   = 12.0    # per side → 22mm pins
pin_y       = [tile_d * 0.2, tile_d * 0.8]      # on the left/right edges
pin_x       = [1.5 * tile_w / 9, 7.5 * tile_w / 9]   # on the top/bottom edges, on slat ribs 1 and 7
bed_chamfer = 0.8     # Phase 3: chamfer on the plate's bed edges (one 0.8 line; elephant foot, clean joints)
# lattice back: windows through the plate between slats; ribs stay under every slat
rib_w       = 11.4    # rib under each slat (root 6.4 + fillets 2×2.0 = 10.4, +0.5 each side)
border      = 14.0    # solid border all round (dowel sockets live in it)
cross_y     = [tile_d / 2] # cross ribs (Y) that tie the slat ribs together
cross_w     = 8.0

# print orientation: plate face down on the bed, slats extrude +Z. No overhangs.
# seam: the slicer will pin it on a slat's back vertical edge — hidden in the gap.

RUN_W, RUN_D = tile_w * cols, tile_d * rows          # real run (1219 × 356 mm = 48 × 14 in)
DESIGN_W, DESIGN_D = 1250.0, 500.0                    # the field is authored at full size and scaled

# accents: three deliberate peaks ON the main ridge (thirds of the run, asymmetric heights),
# plus a fine undulation along the crests so the ridge line itself moves.
# a monitor sits in the middle of the run: the flanks are the money areas. The ridges cross on
# the flanks, the peaks live there, and an envelope calms the centre (which also saves filament).
WAVES, PH1, PH2 = 1.75, 0.30, 2.10     # main ridge 1.75 waves; counter ridge runs at W2 so they cross several times
W2, W3, PH3 = 2.25, 2.75, 1.0          # counter-ridge and third (fine) ridge frequencies
peaks       = [(0.10, 16.7, 90.0), (0.22, 23.3, 80.0), (0.78, 21.7, 80.0), (0.91, 15.0, 90.0)]   # (u, extra mm, radius mm)
eddies      = [(0.30, 95.0, 21.7, 105.0), (0.70, 405.0, 18.3, 100.0), (0.36, 380.0, 16.7, 90.0), (0.64, 120.0, 16.7, 90.0)]   # free peaks (u, y, extra mm, radius)
end_taper   = 230.0   # mm: the left and right ends fade toward the wall over this distance
end_floor   = 3.0     # slat height at the very ends (a lip, not a cliff)
seam_dip    = 0.22    # fraction of local height removed at a tile seam (0 = off)
seam_sigma  = 16.0    # mm (design space) half-width of the seam dip
centre_dip  = 0.35    # centre height factor = 1 - centre_dip·exp(-((u-0.5)/0.16)²)  → ~55% behind the monitor
ripple_amp  = 0.08    # ±8% of local height, wavelength ~150mm along the run
ripple_wl   = 150.0


# ── multi-scale detail (the reference's per-slat S-curves and creases) ──────────
def _hash(ix, iy, seed=7):
    n = (ix * 374761393 + iy * 668265263 + seed * 1442695041) & 0xFFFFFFFF
    n = (n ^ (n >> 13)) * 1274126177 & 0xFFFFFFFF
    return ((n ^ (n >> 16)) & 0xFFFF) / 65535.0
def _smooth(t): return t * t * (3.0 - 2.0 * t)
def vnoise(x, y, seed=7):
    """Value noise in [-1, 1], smooth, deterministic."""
    ix, iy = math.floor(x), math.floor(y); fx, fy = _smooth(x - ix), _smooth(y - iy)
    a, b = _hash(ix, iy, seed), _hash(ix + 1, iy, seed); c, d = _hash(ix, iy + 1, seed), _hash(ix + 1, iy + 1, seed)
    return 2.0 * ((a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy) - 1.0
octaves     = [(420.0, 0.50), (210.0, 0.28), (105.0, 0.14), (52.0, 0.07)]   # (wavelength mm, weight)
def fbm(x, y):
    return sum(w * vnoise(x / lam + 3.7 * k, y / lam + 1.3 * k, seed=11 + k) for k, (lam, w) in enumerate(octaves)) / sum(w for _, w in octaves)
fold_wl     = 260.0   # spacing of the sharp creases along the run
fold_amp    = 0.22    # weight of the crease term (thin knife ridges)
warp_x      = 90.0    # mm of domain warp along the run
warp_y      = 110.0   # mm of domain warp up the wall (this is what gives each slat its own S)

# ── complementary wave languages (all smooth sinusoids; weights drift across the run) ──
long_wl, long_w   = 640.0, 0.20   # broad swell along the run
short_wl, short_w = 150.0, 0.12   # short wave, strongest where the ridges are quiet
diag_wl, diag_w   = 260.0, 0.10   # diagonal wave crossing the ridges
vrip_wl, vrip_w   = 85.0,  0.06   # fine ripple up each slat (varies along y)

def field_design(x, y):
    """Foundation: two snaking ridges that cross (the field approved at Phase 1).
    Complements: long swell, short wave, diagonal wave, vertical ripple — all smooth,
    weighted so each has a home region. Then the centre envelope, flank peaks, crest ripple."""
    u, v = x / DESIGN_W, y / DESIGN_D
    yc1 = DESIGN_D * 0.5 + 160.0 * math.sin(2*math.pi*1.25*u + 0.3)        # main ridge centreline
    yc2 = DESIGN_D * 0.5 - 170.0 * math.sin(2*math.pi*1.25*u + 1.2)        # counter ridge
    r1 = math.exp(-((y - yc1) / 95.0) ** 2)
    r2 = 0.72 * math.exp(-((y - yc2) / 62.0) ** 2)
    g = 1.0 - (1.0 - r1) * (1.0 - r2)                                    # foundation 0..1
    quiet = 1.0 - g                                                      # where the ridges are not
    long_ = 0.5 + 0.5 * math.sin(2*math.pi * (x / long_wl + 0.25 * v) + 0.4)
    short = 0.5 + 0.5 * math.sin(2*math.pi * (x / short_wl + 0.35 * v) + 1.0)
    diag  = 0.5 + 0.5 * math.sin(2*math.pi * ((x + 0.7 * y) / diag_wl) + 2.0)
    vrip  = 0.5 + 0.5 * math.sin(2*math.pi * y / vrip_wl + 0.8 * math.sin(2*math.pi * x / 400.0))
    # weights drift along the run so the languages trade places instead of stacking
    w_short = short_w * (0.4 + 0.6 * quiet) * (0.5 + 0.5 * math.sin(2*math.pi * u * 0.9 + 1.0))
    w_diag  = diag_w  * (0.5 + 0.5 * math.cos(2*math.pi * u * 0.7 + 0.3))
    total = 0.70 * g + long_w * long_ + w_short * short + w_diag * diag + vrip_w * vrip * g
    gt = min(1.0, max(0.0, total))
    env = 1.0 - centre_dip * math.exp(-((u - 0.5) / 0.14) ** 2)
    h = h_min + (h_max - h_min) * (gt ** crest_power) * env
    for (uk, amp, rad) in peaks:
        xk = uk * DESIGN_W; yk = DESIGN_D * 0.5 + 160.0 * math.sin(2*math.pi*1.25*uk + 0.3)
        h += amp * math.exp(-((x - xk) ** 2 + (y - yk) ** 2) / rad ** 2) * (0.5 + 0.5 * min(1.0, 1.3 * g))
    for (ue, ye, amp, rad) in eddies:
        h += amp * math.exp(-((x - ue * DESIGN_W) ** 2 + (y - ye) ** 2) / rad ** 2)
    h *= 1.0 + ripple_amp * g * math.sin(2*math.pi * x / ripple_wl + 1.1 * math.sin(2*math.pi * y / DESIGN_D))
    # seams in the troughs: a soft, shallow dip where tile boundaries fall along the run
    for k in range(1, cols):
        xs = k * (DESIGN_W / cols)
        h -= seam_dip * (h - h_min) * math.exp(-((x - xs) / seam_sigma) ** 2)
    # ends emerge from the wall: smooth taper to a low lip at x = 0 and x = DESIGN_W
    def _ss(t): t = min(1.0, max(0.0, t)); return t * t * (3.0 - 2.0 * t)
    f = _ss(x / end_taper) * _ss((DESIGN_W - x) / end_taper)
    return end_floor + (h - end_floor) * f

def field(x, y):
    """Real-space height: the full-size design evaluated at (x, y)/SCALE. Only the footprint
    is scaled — heights stay at full size (the 3in crest was the brief)."""
    return field_design(x / SCALE_X, y / SCALE_Y)

def slat(x_local, x_global, y0_global):
    """A slat = (wave prism, YZ profile extruded along X) ∩ (tapered blade, XZ profile
    extruded along Y). The blade is slat_root wide at the plate with a quarter-round
    fillet each side, narrowing to slat_t at the top."""
    ys = [i * sample_step for i in range(int(tile_d / sample_step) + 1)]
    pts = [(0.0, 0.0)] + [(y, field(x_global, y0_global + y)) for y in ys] + [(tile_d, 0.0)]
    wave = (cq.Workplane("YZ", origin=(x_local - slat_root - root_fillet, 0, 0))
            .polyline(pts).close().extrude(2 * (slat_root + root_fillet)))
    H = h_max + 30.0      # blade taller than any peak + ripple; the wave prism trims it
    f, hr, ht = root_fillet, slat_root / 2, slat_t / 2
    arc = [(-(hr + f) + f * math.sin(a), f - f * math.cos(a)) for a in (math.pi * k / 8 for k in range(0, 5))]
    left = [(-(hr + f), 0.0)] + arc[1:]                       # ends exactly at (-hr, f)
    right = [(-xx, zz) for (xx, zz) in reversed(arc[1:])] + [(hr + f, 0.0)]
    prof = left + [(-ht, H), (ht, H)] + right
    blade = (cq.Workplane("XZ", origin=(x_local, 0, 0)).polyline(prof).close()
             .extrude(-tile_d))          # XZ normal is -Y; extrude toward +Y
    slat_solid = wave.intersect(blade)
    if crest_chamfer:
        # 45° flanks that follow the crest: extrude the (lowered) wave profile along (±1, 0, 1)
        L = slat_root + 8.0
        for side in (+1, -1):
            x0 = x_local - side * (slat_root / 2 + 1.0)
            lowered = [(0.0, 0.0)] + [(y, max(0.0, field(x_global, y0_global + y) - slat_root / 2 - 1.0)) for y in ys] + [(tile_d, 0.0)]
            lowered = [pt for i, pt in enumerate(lowered) if i == 0 or (abs(pt[0] - lowered[i-1][0]) > 1e-6 or abs(pt[1] - lowered[i-1][1]) > 1e-6)]
            if len(lowered) < 3 or max(z for _, z in lowered) <= 0.0:
                continue                     # crest lower than the chamfer depth here: nothing to cut
            wire = cq.Workplane("YZ", origin=(x0, 0, 0)).polyline(lowered).close().val()
            roof = cq.Solid.extrudeLinear(cq.Face.makeFromWires(wire), cq.Vector(side * L, 0, L))
            slat_solid = slat_solid.intersect(cq.Workplane().add(roof))
    return slat_solid

def tile(r, c):
    x0, y0 = c * tile_w, r * tile_d
    plate = (cq.Workplane("XY").box(tile_w, tile_d, plate_t, centered=(False, False, False))
             .edges("<Z").chamfer(bed_chamfer))     # elephant-foot relief on the bed perimeter
    # lattice back: cut windows between the slat ribs (glue lands on ribs + border)
    n = slats_per
    xcs = [(i + 0.5) * slat_pitch for i in range(n)]
    ybands, y_edges = [], [border] + sorted(cross_y) + [tile_d - border]
    for k in range(0, len(y_edges) - 1):
        ya = y_edges[k] + (cross_w / 2 if k > 0 else 0); yb = y_edges[k + 1] - (cross_w / 2 if k + 1 < len(y_edges) - 1 else 0)
        ybands.append((ya, yb))
    xr = [border] + [v for xc in xcs for v in (xc - rib_w / 2, xc + rib_w / 2)] + [tile_w - border]
    for j in range(0, len(xr) - 1, 2):
        xa, xb = xr[j], xr[j + 1]
        if xb - xa < 3.0: continue
        for (ya, yb) in ybands:
            win = cq.Workplane("XY", origin=(xa, ya, -1.0)).box(xb - xa, yb - ya, plate_t + 2.0, centered=(False, False, False))
            plate = plate.cut(win)
    # no screw holes: the tiles are glued to the wall (adhesive or mounting tape); dowels align them
    # filament dowel sockets in the plate edges: left/right (along X), bottom/top (along Y)
    zc = plate_t / 2
    # dowel sockets only on SHARED edges — the outer edges of the run stay clean
    for y in pin_y:
        if c > 0:        plate = plate.cut(cq.Workplane().add(cq.Solid.makeCylinder(pin_d / 2, pin_depth + 0.01, cq.Vector(-0.01, y, zc), cq.Vector(1, 0, 0))))
        if c < cols - 1: plate = plate.cut(cq.Workplane().add(cq.Solid.makeCylinder(pin_d / 2, pin_depth + 0.01, cq.Vector(tile_w + 0.01, y, zc), cq.Vector(-1, 0, 0))))
    for x in pin_x:
        if r > 0:        plate = plate.cut(cq.Workplane().add(cq.Solid.makeCylinder(pin_d / 2, pin_depth + 0.01, cq.Vector(x, -0.01, zc), cq.Vector(0, 1, 0))))
        if r < rows - 1: plate = plate.cut(cq.Workplane().add(cq.Solid.makeCylinder(pin_d / 2, pin_depth + 0.01, cq.Vector(x, tile_d + 0.01, zc), cq.Vector(0, -1, 0))))
    body = plate
    n = slats_per
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
