"""The droop family: single strands that leave the wall and arc into air, then sag under gravity into hanging
loops, fringe, swags and curls (the UNRAVEL technique, print-verified July 2026).

Each strand is a flat ribbon one or two extrusions wide and a few layers tall, anchored INTO the wall at its two
ends only, with open air between strand and wall. The mesh shows the strand before gravity; the printer lays the
unsupported span molten and it drops. Laws (all print-verified):
  * bridges at NORMAL speed (slow freezes each mm as laid and nothing droops); fan <= 20 %, nozzle +5 C
  * strands never intersect in the mesh — they fuse on the print, not in geometry; rows sit a full strand height
    plus a layer apart, strands in a row never overlap
  * directly stacked loops fuse: at most 3 deep, then offset; row phases drift so columns don't stack forever
  * strand height <= 4 layers; bottom loops start high enough that their droop never reaches the bed
  * a loop can't be an r(theta) displacement (single-valued radius welds loops into cliffs) — it is its own ribbon
Jitter is hash-deterministic: a design regenerates identically."""
import hashlib
import math

import numpy as np
import trimesh

STYLES = {
    "fringe":    dict(name="Fringe", blurb="Dense narrow loops that fall into a long hanging fringe"),
    "swag":      dict(name="Swag", blurb="Wide, fat loops that sag into layered festoons"),
    "curls":     dict(name="Curls", blurb="Small loops stacked in drifting columns — they settle into coils"),
    "unraveled": dict(name="Unraveled", blurb="A wild mix of short and long loops, as if the wall is coming apart"),
    "fur":       dict(name="Fur", blurb="Hundreds of bridged hairs out to a cut-away shell — brush them into a mane"),
}
CLEAR = 2.5                 # mm: a hung loop's lowest point stays this far above the bed
FUR_LEN = {"short": 10.0, "medium": 15.0, "long": 22.0}
DENSITY = {"sparse": 0.55, "medium": 1.0, "dense": 1.45}
LENGTH = {"short": 0.7, "medium": 1.0, "long": 1.4}

# per style, in units of the nozzle's line width (lw) and layer height (lh) where it matters
_SPEC = {
    # width 1.15 lw = ONE extrusion (the single overhanging line is the whole idea); swag is 2 lines on purpose
    #            chord mm  bulge mm  width lw  tall lh  row gap lh  keep
    "fringe":    dict(chord=(6, 9),   bulge=(14, 22), width=1.15, tall=2, row=4,  keep=0.62, power=0.55),
    "swag":      dict(chord=(22, 32), bulge=(7, 10),  width=2.1, tall=3, row=14, keep=0.90, power=1.0),
    "curls":     dict(chord=(4, 5.5), bulge=(6, 8),   width=1.15, tall=3, row=5,  keep=1.0, power=0.5),
    "unraveled": dict(chord=(6, 30),  bulge=(5, 24),  width=1.15, tall=2, row=6,  keep=0.55, power=0.7),
}


def panel_windows(n, width_deg, offset_deg=90.0):
    """POILU-style panels (Nov 2026, after bold_designers' POILU 3.0): strands only inside n vertical windows of
    width_deg each, evenly spaced, the first centred at offset_deg (90 = the silhouette edge seen from the front,
    so the front face between panels stays bare)."""
    n = int(n or 0)
    if n <= 0 or width_deg <= 0:
        return None
    return [(math.radians(offset_deg + 360.0 * i / n), math.radians(min(width_deg, 360.0 / n)) / 2) for i in range(n)]


def in_panels(theta, panels, margin=0.0):
    """True when theta (+- margin radians) lies inside one of the panel windows (or there are no panels)."""
    if not panels:
        return True
    for c, hw in panels:
        if abs((theta - c + math.pi) % (2 * math.pi) - math.pi) <= hw - margin:
            return True
    return False


def even_options(o):
    """Options dict -> the even-rows spec (or None). {"rows": "even", "loop_w", "loop_l", "tier", "ruffle", "ruffles"}."""
    if (o or {}).get("rows") != "even":
        return None
    keys = ("loop_w", "loop_l", "tier", "ruffle", "ruffles", "tall", "line") + TIER_KEYS
    return {k: float(o[k]) for k in keys if o.get(k) not in (None, "")}


# Teardrop tiers (Nov 2026, second pass at POILU 3.0): "pinch" switches a row from the open arch to a loop whose two
# legs leave the wall close together and open into a round end — the teardrop / hairpin of the originals.
TIER_KEYS = ("pinch", "gap", "vary", "stray", "collar", "crown_rows", "crown_l", "crown_w", "flounce", "flounce_wave",
             "flounce_waves", "flounce_swirl", "flounce_gain", "l_min", "crown_tier", "crown_step",
             "petal", "petal_sag", "petals", "petal_share", "petal_seed", "bed_reach",
             "arch_spring", "arch_top", "edge_taper", "grow")


def strand_d(width, layer_h):
    """Diameter of the round strand a width x layer_h line becomes when it is laid in air."""
    return 2.0 * math.sqrt(width * layer_h / math.pi)


def petal_field(th, z, P, D, n):
    """(see petal_slot for a petal's colour) Overlapping petals (the frills of POILU's ruffled pieces): rows of n lobes around, every other row half a lobe
    over, each lobe's hem a hanging arc D mm deep, rows P mm apart, all gently warped so no two lobes match.
    -> (u = mm above the hem of the lobe that owns the point, lobe id). numpy-friendly."""
    th = np.asarray(th, float); z = np.asarray(z, float)
    tw = th + 0.10 * np.sin(z / 17.0 + 1.3); zw = z + 0.18 * P * np.sin(3 * th + z / 23.0)
    best_u = np.full(np.broadcast(th, z).shape, np.inf); best_id = np.zeros(best_u.shape, np.int64)
    for par in (0, 1):
        c = tw * n / (2 * math.pi) + 0.5 * par; col = np.floor(c); x = c - col - 0.5
        g = zw + D * (1 - 4 * x * x) - par * P
        k = np.floor(g / (2 * P)); u = g - 2 * P * k
        lid = (par + 2 * (col.astype(np.int64) % n) + 2 * n * (k.astype(np.int64) + 50))
        take = u < best_u
        best_u = np.where(take, u, best_u); best_id = np.where(take, lid, best_id)
    return best_u, best_id


def petal_slot(lid, share=0.38, seed=3):
    """Colour slot of a petal: 1 for `share` of them (hash of the lobe id), else 0."""
    return (((np.sin((np.asarray(lid) + seed) * 12.9898) * 43758.5453) % 1.0) < share).astype(int)


def _teardrop(L, W, a, n_arc=13):
    """Centreline of one loop in its own frame: u = mm out from the wall, s = mm sideways. Legs start at s = +-a,
    run straight to the tangent points of a round end (radius W/2) whose far side sits L out. a = W/2 gives a
    straight-sided scallop, a small a the pinched teardrop. A loop too short for a round end is a half ellipse."""
    rho = W / 2.0; c = L - rho; a = min(a, rho)
    if c <= 0.25 * rho:
        t = np.linspace(0.0, math.pi, n_arc + 4)
        return L * np.sin(t), rho * np.cos(t) * (a + (rho - a) * np.sin(t)) / rho
    d = math.hypot(c, a)
    beta = math.atan2(a, -c) - math.acos(min(1.0, rho / d))
    ang = np.linspace(beta, -beta, n_arc)
    au, as_ = c + rho * np.cos(ang), rho * np.sin(ang)
    k = np.array([0.0, 0.5])                                  # the leg: root and one mid point (a straight line)
    lu, ls = k * au[0], a + k * (as_[0] - a)
    return np.concatenate([lu, au, lu[::-1]]), np.concatenate([ls, as_, -ls[::-1]])


def _loop_ribbon(theta, W, L, z0, height, width, r_of_z, embed, pinch):
    """One teardrop loop as a printable flat ribbon: straight in its own plane (not wrapped round the wall), both
    roots sunk `embed` into the wall."""
    r_w = r_of_z(z0 + height / 2)
    a = max(pinch * W / 2.0, (width + 0.4) / 2.0)             # the legs keep 0.4 mm of air between them at the root
    u, s_ = _teardrop(L, W, a)
    u = np.concatenate([[-embed], u, [-embed]]); s_ = np.concatenate([[s_[0]], s_, [s_[-1]]])
    c, sn = math.cos(theta), math.sin(theta)
    P = np.column_stack([(r_w + u) * c - s_ * sn, (r_w + u) * sn + s_ * c])
    return _strip(P, width, z0, height)


def _tier_rows(r_of_z, height, nz, even, seed=11, z_range=None, panels=None):
    """Teardrop tiers: rows of identical loops packed until neighbours nearly touch, each row half a loop off the
    one below, the top row landing exactly under the bare collar. even = {
      loop_w: the loop's width (centreline, mm), loop_l: its reach, tier: row spacing, pinch: root spacing as a
      fraction of the width (0.3 teardrop .. 1 scallop), gap: air between neighbours (0.5), line: strand width,
      collar: bare band under the rim (mm), crown_rows / crown_l / crown_w: the top rows as a ruff of long narrow
      hairpins (crown_tier: their spacing, crown_step: mm shorter per row going up), vary: 0..1 random shortening (lofty fringe), stray: share of loops a third longer,
      flounce: period (mm) of flounces — loops lengthen up each flounce (flounce_gain mm per mm), so the pile swells
      to a hem and steps back under it; flounce_wave / flounce_waves / flounce_swirl: the hem's rise and fall around the piece,
      petal / petal_sag / petals: petal-shaped frills instead (petal_field), l_min: the shortest loop}.
    -> [(theta, width, reach, z, strand_h, 0, line)]"""
    lh, lw = nz.layer_h, nz.line_w
    tall = int(min(4, even.get("tall", 2))); strand_h = tall * lh
    width = float(even.get("line", 1.15 * lw)); gap = float(even.get("gap", 0.5))
    W0 = float(even.get("loop_w", 4.5)); L0 = float(even.get("loop_l", 9.0))
    tier = round(max(float(even.get("tier", 2.8)), (tall + 1) * lh) / lh) * lh
    vary = float(even.get("vary", 0.0)); stray = float(even.get("stray", 0.0))
    crown = int(even.get("crown_rows", 0)); cl = float(even.get("crown_l", 1.8 * L0)); cw = float(even.get("crown_w", 0.62 * W0))
    P = float(even.get("flounce", 0.0)); A = float(even.get("flounce_wave", 0.0)); nw = int(even.get("flounce_waves", 3))
    gain = float(even.get("flounce_gain", 1.12))            # 1.12: every loop ends at the hem; less: rows peek out as scallops
    swirl = float(even.get("flounce_swirl", 0.0)); l_min = float(even.get("l_min", max(3.0, 0.8 * W0)))
    a_spring = float(even.get("arch_spring", 0.0)); a_top = float(even.get("arch_top", 0.0))
    taper = int(even.get("edge_taper", 0)); grow = float(even.get("grow", 0.0))
    pet = float(even.get("petal", 0.0)); pet_sag = float(even.get("petal_sag", 0.7 * pet)); pet_n = int(even.get("petals", 5))
    if z_range is None:
        z_range = (0.0, height - 1.0)
    z_hi = z_range[1] - strand_h - float(even.get("collar", 0.0))
    # bed_reach: rows start at the very first wall layers and a loop may be this much LONGER than its height above
    # the bed, so the lowest rows come to rest on the plate and flare (default: every loop stops CLEAR short of it)
    reach_bed = even.get("bed_reach")
    z_lo = z_range[0] if reach_bed is not None else max(z_range[0], CLEAR + l_min)
    n_rows = int((z_hi - z_lo) / tier) + 1
    out = []
    # crown_tier: the crown rows sit this close together (a fringe of several colours on consecutive layers, as
    # on POILU's rims); crown_step: each crown row above the lowest is this much shorter, so every colour shows
    ct = round(max(float(even.get("crown_tier", tier)), (tall + 1) * lh) / lh) * lh; cstep = float(even.get("crown_step", 0.0))
    drop = max(0, crown - 1) * (tier - ct)                     # the regular rows move up by what the crown saves
    n_rows = int((z_hi - z_lo + drop) / tier) + 1
    for k in range(n_rows):                                    # k = 0 is the TOP row: the collar line stays crisp
        z = z_hi - k * ct if k < crown else z_hi - k * tier + drop
        row = n_rows - 1 - k; r = r_of_z(z)
        W, L = (cw, max(l_min, cl - (crown - 1 - k) * cstep)) if k < crown else (W0, L0)
        pitch = W + width + gap
        # arch: the bare window between panels keeps its width up to arch_spring (mm), then closes in a round arch at
        # arch_top; above it (and in the crown rows) the loops run right round. edge_taper: the first loops beside
        # the window are short and lengthen over that many loops, so the fringe swells away from a crisp edge.
        # grow: loops at the top are this fraction shorter than at the foot.
        row_panels = panels
        if panels and (k < crown or (a_top > a_spring and z >= a_top)):
            row_panels = None
        elif panels and a_top > a_spring and z > a_spring:
            shut = 1.0 - math.sqrt(max(0.0, 1.0 - ((z - a_spring) / (a_top - a_spring)) ** 2))
            row_panels = [(c0_, hw_ + (math.pi / len(panels) - hw_) * shut) for c0_, hw_ in panels]
        for c0, hw in (row_panels or [(0.0, math.pi)]):
            arc = 2 * hw * r
            n = max(1, int(arc / pitch)) if row_panels else max(3, int(arc / pitch))
            step = (2 * hw / n) if not row_panels else pitch / r
            start = c0 - hw + (0.5 * step if not row_panels else (hw - (n - 1) * step / 2))
            odd = row % 2
            n_here = n - (1 if (row_panels and odd) else 0)
            for i in range(n_here):
                th = start + (i + 0.5 * odd) * step
                Lk = L
                if k >= crown and grow:
                    Lk *= 1.0 - grow * (z - z_lo) / max(z_hi - z_lo, 1e-6)
                if k >= crown and row_panels and taper:
                    e = min(i, n_here - 1 - i)
                    if e < taper:
                        Lk *= 0.35 + 0.65 * e / taper
                if k >= crown:
                    if pet > 0:
                        Lk = min(L, l_min + gain * float(petal_field(th, z, pet, pet_sag, pet_n)[0]))
                    elif P > 0:
                        u = (z - A * math.sin(nw * th + swirl * z)) % P
                        Lk = min(L, l_min + gain * u)
                    if vary:
                        Lk *= 1.0 - vary * _h(seed, "v", row, round(th, 4))
                    if stray and _h(seed, "s", row, round(th, 4)) < stray:
                        Lk *= 1.35
                Lk = min(Lk, z + float(reach_bed)) if reach_bed is not None else min(Lk, z - CLEAR)
                if Lk < max(2.2, 0.6 * W):
                    continue
                out.append((th % (2 * math.pi), W, Lk, z, strand_h, 0.0, width))
    return out[::-1]                                           # bottom row first: print order


def _h(*key):
    d = hashlib.sha1(":".join(map(str, key)).encode()).digest()
    return int.from_bytes(d[:4], "big") / 2 ** 32


def _ribbon(theta_c, chord, bulge, z0, height, width, r_of_z, embed, power, lean=0.0, n=26):
    """One loop: a strip that starts inside the wall, arcs out `bulge` mm and returns, `chord` mm apart.
    Built straight from arrays (offset polyline -> strip -> extrusion): thousands per piece, so no shapely/trimesh
    processing per strand."""
    r_w = r_of_z(z0 + height / 2)
    dth = chord / max(r_w, 1.0)
    t = np.linspace(0, 1, n)
    s = np.sin(np.pi * t) ** power
    th = theta_c + (t - 0.5) * dth + lean * dth * np.sin(np.pi * t) ** 2
    leg = min(2.0, 0.4 * bulge)                             # each end leaves the wall RADIALLY for `leg` mm, so a
    r = (r_w + leg) + (bulge - leg) * s                     # long shallow strand never grazes the wall surface
    r = np.concatenate([[r_w - embed], r, [r_w - embed]])
    th = np.concatenate([[th[0]], th, [th[-1]]])
    P = np.column_stack([r * np.cos(th), r * np.sin(th)])
    return _strip(P, width, z0, height)


def _strip(P, width, z0, height):
    """Polyline P (k, 2) -> watertight extruded ribbon of `width` (flat caps, mitred joins clamped to 2x)."""
    T = np.empty_like(P)
    T[1:-1] = P[2:] - P[:-2]; T[0] = P[1] - P[0]; T[-1] = P[-1] - P[-2]
    T /= np.maximum(np.linalg.norm(T, axis=1), 1e-9)[:, None]
    N = np.column_stack([-T[:, 1], T[:, 0]])
    seg = P[1:] - P[:-1]; seg /= np.maximum(np.linalg.norm(seg, axis=1), 1e-9)[:, None]
    scale = np.ones(len(P))
    if len(P) > 2:                                          # mitre: 1/cos(half the turn), clamped
        cosh = np.clip(np.einsum("ij,ij->i", N[1:-1], np.column_stack([-seg[:-1, 1], seg[:-1, 0]])), 0.5, 1.0)
        scale[1:-1] = 1.0 / cosh
    L = P + N * (width / 2 * scale)[:, None]; R = P - N * (width / 2 * scale)[:, None]
    k = len(P)
    ring = np.vstack([L, R[::-1]])                          # closed outline, 2k points
    V = np.vstack([np.column_stack([ring, np.full(2 * k, z0)]), np.column_stack([ring, np.full(2 * k, z0 + height)])])
    m2 = 2 * k; i = np.arange(m2); i2 = (i + 1) % m2
    side = np.vstack([np.column_stack([i, i2, m2 + i2]), np.column_stack([i, m2 + i2, m2 + i])])
    a = np.arange(k - 1); l0, l1 = a, a + 1; r0, r1 = m2 - 1 - a, m2 - 2 - a      # strip quads between L and R
    bot = np.vstack([np.column_stack([l0, r1, l1]), np.column_stack([l0, r0, r1])])
    top = np.vstack([np.column_stack([m2 + l0, m2 + l1, m2 + r1]), np.column_stack([m2 + l0, m2 + r1, m2 + r0])])
    F = np.vstack([side, bot, top])
    m = trimesh.Trimesh(V, F, process=False)
    if (V[F][:, 0] * np.cross(V[F][:, 1], V[F][:, 2])).sum() < 0:   # signed volume < 0: flip every face
        m.faces = F[:, ::-1]
    return m


def _even_rows(r_of_z, height, nz, even, seed=11, z_range=None, panels=None):
    """EVEN rows (after POILU 3.0): every row a regular ring of identical teardrop loops, rows a fixed tier apart,
    each row offset half a loop from the one below (brick), no random gaps, sizes or lean. even = {
      loop_w: anchor spacing (chord) mm, loop_l: reach (bulge) mm, tier: row spacing mm,
      ruffle: row wave amplitude mm (0 = flat rows), ruffles: waves around, tall: strand layers (2)}.
    Ruffled rows rise and fall around the piece, so tiers pile into ruffles (no cut-safe colour courses then)."""
    lh, lw = nz.layer_h, nz.line_w
    tall = int(min(4, even.get("tall", 2))); strand_h = tall * lh
    width = float(even.get("line", 1.15 * lw))                    # a fatter single line (with a strand modifier) hangs rounder
    chord = float(even.get("loop_w", 5.0)); reach = float(even.get("loop_l", 10.0))
    tier = max(float(even.get("tier", 3.2)), (tall + 1) * lh)
    tier = round(tier / lh) * lh                                   # rows on the layer grid
    amp = float(even.get("ruffle", 0.0)); waves = int(even.get("ruffles", 5))
    rim = 0.0
    if z_range is None:
        z_range = (0.0, height); rim = 1.0
    min_reach = max(2.5, 0.35 * reach)
    z_lo = max(z_range[0], CLEAR + min_reach) + amp
    z_hi = z_range[1] - strand_h - rim - amp
    out, row, z = [], 0, z_lo
    while z <= z_hi:
        r = r_of_z(z); slot = chord + width * 3.3                 # _never_touch keeps 1.5 widths of air each side
        n = max(3, int(2 * math.pi * r / slot))
        for k in range(n):
            th = 2 * math.pi * (k + 0.5 * (row % 2)) / n
            zk = z + (amp * math.sin(waves * th + 0.9 * row) if amp else 0.0)
            zk = z_lo - amp + round((zk - (z_lo - amp)) / lh) * lh if amp else zk
            b = min(reach, zk - CLEAR)
            if b < min_reach or not in_panels(th, panels, chord / 2 / r):
                continue
            out.append((th, min(chord, slot - width * 2.0), b, zk, strand_h, 0.0, width))
        row += 1; z += tier
    return out


def _rows(style, r_of_z, height, nz, density, length, seed=11, z_range=None, aligned=False, panels=None, even=None):
    """Strand placements (theta, chord, bulge, z0, tall, lean, width) honouring the laws above.
    panels: optional windows from panel_windows() — strands only inside them (whole strand, chord included).
    even: optional dict -> regular POILU-style rows instead of the style's jittered ones (see _even_rows)."""
    if even:
        return _even_rows(r_of_z, height, nz, even, seed, z_range, panels)
    sp = _SPEC[style]; lh, lw = nz.layer_h, nz.line_w
    tall = min(4, sp["tall"]); strand_h = tall * lh; width = sp["width"] * lw
    gap = max(sp["row"], tall + 1) * lh                      # rows a full strand + a layer apart: never intersect
    # plain bands as small as possible (Collin): strands run from just above the bed to just under the rim. A loop
    # hangs about its bulge below its anchor, so near the bed loops are SHORTENED to clear it instead of the whole
    # bottom being left plain — the fringe tapers into the foot.
    rim = 0.0
    if z_range is None:
        z_range = (0.0, height); rim = 1.0
    min_bulge = max(2.5, 0.35 * sp["bulge"][0] * length)
    z_lo = max(z_range[0], CLEAR + min_bulge)
    z_hi = z_range[1] - strand_h - rim
    fit = lambda b, z: min(b, z - CLEAR)                    # the hung loop stops CLEAR mm above the bed
    out = []
    if style == "curls":
        # tiers of coil columns; each next loop drifts 40 % of a chord sideways (partial overlap -> a coil)
        run_n = 16; tier_h = run_n * gap * 0.75; tier = 0; z_t = z_lo
        while z_t <= z_hi:
            r_t = r_of_z(z_t)
            n_cols = max(6, int(2 * math.pi * r_t / 10.0 * min(density, 1.4)))
            for c in range(n_cols):
                th = 2 * math.pi * (c + 0.5 * (tier % 2) + 0.3 * _h(seed, "c", tier, c)) / n_cols
                z = z_t + _h(seed, "z", tier, c) * tier_h * 0.5
                if aligned:                                    # courses: every loop on one row grid, so colour
                    z = z_lo + round((z - z_lo) / gap) * gap   # can change between rows without cutting a loop
                run = int(run_n * (0.6 + 0.6 * _h(seed, "n", tier, c))); d = 1 if (c + tier) % 2 else -1
                for k in range(run):
                    if z > z_hi:
                        break
                    chord = sp["chord"][0] + (sp["chord"][1] - sp["chord"][0]) * _h(seed, "ch", tier, c, k)
                    th_k = th + d * 0.4 * chord / r_of_z(z) * (k % 4 - 1.5)
                    bulge = fit((sp["bulge"][0] + (sp["bulge"][1] - sp["bulge"][0]) * _h(seed, "b", tier, c, k)) * length, z)
                    if bulge >= min_bulge and in_panels(th_k, panels, chord / 2 / r_of_z(z)):
                        out.append((th_k, chord, bulge, z, strand_h, 0.0, width))
                    z += gap
            tier += 1; z_t += tier_h
        return out
    row = 0; z = z_lo
    phi = (math.sqrt(5) - 1) / 2
    while z <= z_hi:
        r = r_of_z(z); circ = 2 * math.pi * r
        chord_avg = sum(sp["chord"]) / 2
        slot = chord_avg + width * 2.2
        n = max(3, int(circ / slot))
        phase = (row * phi) % 1.0                              # drift: no column stacks more than ~3 deep
        for k in range(n):
            if _h(seed, "keep", row, k) > min(0.98, sp["keep"] * density):
                continue
            chord = sp["chord"][0] + (sp["chord"][1] - sp["chord"][0]) * _h(seed, "ch", row, k)
            chord = min(chord, slot - width * 2.0)            # strands in a row never touch
            bulge = fit((sp["bulge"][0] + (sp["bulge"][1] - sp["bulge"][0]) * _h(seed, "b", row, k)) * length, z)
            lean = (_h(seed, "l", row, k) - 0.5) * (0.8 if style == "unraveled" else 0.25)
            th = 2 * math.pi * (k + phase) / n
            if not in_panels(th, panels, (chord / 2) / r * (1 + abs(lean))):
                continue
            out.append((th, chord, bulge, z, strand_h, lean, width))
        row += 1; z += gap
    return out


def _never_touch(spots, prof, q):
    """Law: strands never intersect in the mesh. Strands that share layers must keep a full strip width of air
    between their footprints (angular extent incl. lean); later ones that don't are dropped."""
    kept, by_z = [], {}
    for sp in spots:
        th, ch, bu, z, hh, lean, w = sp
        zq = round(q(z), 4); r = prof(zq)
        half = (ch / 2 + w * 1.5) / r * (1 + abs(lean))
        lo, hi = th - half, th + half
        clash = False
        for zz, items in by_z.items():
            if abs(zz - zq) >= hh + 1e-6:
                continue
            for a, b in items:
                for off in (-2 * math.pi, 0.0, 2 * math.pi):
                    if lo < b + off and a + off < hi:
                        clash = True; break
                if clash:
                    break
            if clash:
                break
        if not clash:
            by_z.setdefault(zq, []).append((lo, hi)); kept.append(sp)
    return kept


def body(shape, v, nz):
    """The wall: a plain 2-loop revolved shell (vessels) or a solid revolved body with a candle socket."""
    prof, height, rmax = shape.profile(v)
    shell = 2 * nz.line_w + 0.15; floor_t = max(1.6, 8 * nz.layer_h)
    lh = nz.layer_h; step = lh * max(1, round(0.6 / lh))
    # wall rings on the 3/4-layer grid, strand faces on the 1/4-layer grid: every strand face sits half a layer
    # from every ring, so the union never meets near-coplanar faces (they leave slivers)
    zs = np.concatenate([[0.0], np.arange(0.75 * lh, height, step), [height]])
    if getattr(shape, "solid", False):
        sock_r, sock_d = v.get("socket", 22.5) / 2, 22.0
        pts = [(0, 0)] + [(prof(z), z) for z in zs] + [(sock_r, height), (sock_r, height - sock_d), (0, height - sock_d)]
    else:
        outer = [(prof(z), z) for z in zs]
        inner = [(max(prof(z) - shell, 1.0), z) for z in zs[::-1] if z >= floor_t]
        pts = [(0, 0)] + outer + inner + [(max(prof(floor_t) - shell, 1.0), floor_t), (0, floor_t)]
    pts = np.array(pts, float)
    m = trimesh.creation.revolve(pts, sections=max(96, int(2 * math.pi * rmax / 1.2)))
    if m.volume < 0:
        m.invert()
    return m, prof, height, rmax, shell


HANG = {"fringe": (78, 88), "swag": (55, 72), "curls": (45, 80), "unraveled": (35, 88)}   # degrees below horizontal


def courses(spots, lh):
    """Layer boundaries (z) where a colour can change without cutting a strand: each strand row's first layer,
    kept only if no other strand spans it. Like woven courses — colour follows the row, one change per row."""
    occ = [(int(math.floor(z / lh + 1e-9)), int(math.floor(z / lh + 1e-9)) + int(round(hh / lh))) for _, _, _, z, hh, _, _ in spots]
    starts = sorted({a for a, _ in occ})
    return [k * lh for k in starts if not any(a < k <= b for a, b in occ)]


def colourwork_loops(prof, lh, lw, even, info, panels=None, mode="chart", seed=11):
    """Droop loops on a COLOURWORK wall (POILU 3.0: loops over colour-knit). The colourwork's colours already take
    turns layer by layer, so a one-layer loop is whatever colour its layer is — free per-LOOP colour. mode:
      "chart": each loop goes on the nearest layer where ITS stitch bulges, so the loops continue the knit's picture
      "layer": each loop keeps its row's layer (rows mix the band's colours)
      "petal": each loop on the nearest layer of its petal's colour (petal_field / petal_slot)
      int slot: every loop on the nearest layer of that colour.
    A loop whose layer is already taken at its place moves to the next layer that suits it (never dropped while one
    is free within 5 layers). -> ({slot: [ribbons]}, spots, reach). Loops never add AMS changes."""
    import types
    seq, n_floor, cols, slot_seq = info["seq"], info["floor_layers"], info["cols"], info["slot_seq"]
    nz = types.SimpleNamespace(layer_h=lh, line_w=lw)
    ev = dict(even, tall=1, line=float(even.get("line", lw)))
    tiers = "pinch" in ev
    z_lo, z_hi = (n_floor + 2) * lh, info["wall_top"] - 2 * lh
    spots = (_tier_rows if tiers else _even_rows)(prof, info["wall_top"], nz, ev, seed, (z_lo, z_hi), panels)
    air = (ev["line"] + float(ev.get("gap", 0.5))) / 2 - 1e-3 if tiers else 1.5 * ev["line"]
    taken, by_slot, out_spots = {}, {}, []
    two_pi = 2 * math.pi

    def free(L, lo, hi):
        for a_, b_ in taken.get(L, ()):
            for off in (-two_pi, 0.0, two_pi):
                if lo < b_ + off and a_ + off < hi:
                    return False
        return True

    for th, ch, bu, z, hh, lean, w in spots:
        L0 = int(round(z / lh)); col = int(th / two_pi * cols) % cols
        half = (ch / 2 + air) / prof(z); lo, hi = th - half, th + half
        pick = None; want = mode
        if mode == "petal":                                        # the loop takes its OWN petal's colour, whatever
            lid = petal_field(th, z, float(ev["petal"]), float(ev.get("petal_sag", 0.7 * ev["petal"])), int(ev.get("petals", 5)))[1]
            want = int(petal_slot(lid, float(ev.get("petal_share", 0.38)), int(ev.get("petal_seed", 3))))
            if want not in slot_seq[max(0, L0 - 5):L0 + 6]:        # the knit cell under it says: no such layer near
                want = "layer"
        for d in (0, 1, -1, 2, -2, 3, -3, 4, -4, 5, -5):
            Lc = L0 + d; k = Lc - n_floor
            if not (0 <= k < len(seq)) or Lc >= len(slot_seq):
                continue
            if isinstance(want, int) or str(want).isdigit():
                ok = slot_seq[Lc] == int(want)
            elif want == "layer":
                ok = True
            else:
                kind, slot, data = seq[k]
                ok = kind == "plain" or data is None or bool(np.asarray(data[0])[col])
            if ok and free(Lc, lo, hi):
                pick = Lc; break
        if pick is None:
            continue
        z0 = (pick + 0.25) * lh                                    # inside its layer only: the slicer samples mid-layer
        bu = min(bu, z0 + float(ev["bed_reach"])) if ev.get("bed_reach") is not None else min(bu, z0 - CLEAR)
        if bu < 2.2:
            continue
        taken.setdefault(pick, []).append((lo, hi))
        if tiers:
            rib = _loop_ribbon(th, ch, bu, z0, 0.5 * lh, w, prof, 0.55 * lw, float(ev["pinch"]))
        else:
            rib = _ribbon(th, ch, bu, z0, 0.5 * lh, w, prof, 0.55 * lw, 0.55, 0.0)
        slot = slot_seq[pick]
        by_slot.setdefault(slot, []).append(rib); out_spots.append(((th, ch, bu, z0, 0.5 * lh, 0.0, w), slot, rib))
    return by_slot, out_spots, max([s_[0][2] for s_ in out_spots] or [0.0])


def _tube(P, r, sides=5):
    """Polyline P (k, 3) -> a closed tube of radius r (preview strands)."""
    T = np.empty_like(P); T[1:-1] = P[2:] - P[:-2]; T[0] = P[1] - P[0]; T[-1] = P[-1] - P[-2]
    T /= np.maximum(np.linalg.norm(T, axis=1), 1e-9)[:, None]
    ref = np.array([0.0, 0.0, 1.0]); N = np.cross(T, ref)
    bad = np.linalg.norm(N, axis=1) < 1e-6
    N[bad] = np.cross(T[bad], [1.0, 0.0, 0.0])
    N /= np.linalg.norm(N, axis=1)[:, None]; B = np.cross(T, N)
    a = np.linspace(0, 2 * math.pi, sides, endpoint=False)
    V = (P[:, None, :] + r * (np.cos(a)[None, :, None] * N[:, None, :] + np.sin(a)[None, :, None] * B[:, None, :])).reshape(-1, 3)
    k = len(P); i = np.arange(k - 1)[:, None] * sides; j = np.arange(sides)[None, :]; jn = (j + 1) % sides
    F = np.vstack([np.column_stack([(i + j).ravel(), (i + jn).ravel(), (i + sides + jn).ravel()]),
                   np.column_stack([(i + j).ravel(), (i + sides + jn).ravel(), (i + sides + j).ravel()])])
    return V, F


def hang_pile(loops, prof, lh, pinch, seed=11, rest=0.8, bend=2.2):
    """Preview only: the loops as round strands, laid in print order onto the pile. A loop leaves the wall almost
    level, then falls as steeply as its stiffness (bend radius `bend` mm) and whatever is already under it allow:
    the wall where it widens, and the loops of the rows below, which it comes to rest ON (it adds `rest` strand
    diameters to the pile for the rows above). Dense tiers therefore stand off like scales and long fringe builds a
    lofty curtain, as on the printed pieces. loops: [((theta, W, L, z, hh, lean, line), key)] bottom row first.
    -> {key: mesh}. An estimate, not a simulation; the print files always carry the flat loops."""
    nb = 360; dz = 0.25; ds = 0.4
    z_top = max((sp[3] for sp, _ in loops), default=1.0) + 2.0
    zg = np.arange(0.0, z_top + dz, dz)
    env = np.tile(np.array([prof(z) for z in zg]), (nb, 1))            # outermost matter per (angle bin, height)
    cands = np.radians([88.0, 76.0, 62.0, 48.0, 34.0, 20.0, 8.0, 0.0])
    out = {}
    for n_, ((th, W, L, z, hh, lean, w), key) in enumerate(loops):
        d = strand_d(w, lh if hh < lh else hh); r_a = prof(z)
        hwid = (W / 2) / max(r_a, 1.0)
        b0 = int(math.floor((th - hwid) / (2 * math.pi) * nb)); b1 = int(math.floor((th + hwid) / (2 * math.pi) * nb))
        bins = np.arange(b0, b1 + 1) % nb
        col = env[bins].max(0)
        steps = max(2, int(math.ceil(L / ds))); h_ = L / steps
        dphi = h_ / bend * (0.85 + 0.3 * _h(seed, "stiff", n_))
        phi = math.radians(6.0 + 10.0 * _h(seed, "exit", n_))
        rr, zz = [r_a], [z]
        for _ in range(steps):
            r0, z0 = rr[-1], zz[-1]; done = False
            for c in cands:
                c = min(c, phi + dphi)                                    # never bend tighter than its stiffness
                r1, z1 = r0 + h_ * math.cos(c), z0 - h_ * math.sin(c)
                if z1 < d / 2:
                    continue
                if r1 >= col[min(len(zg) - 1, max(0, int(round(z1 / dz))))] + 0.5 * d:
                    phi = c; done = True; break
            if not done:
                r1, z1 = r0 + h_, z0; phi = 0.0
            rr.append(r1); zz.append(z1)
        rr, zz = np.array(rr), np.array(zz)
        order = np.argsort(zz)
        zi = np.arange(max(0, int(math.ceil(zz.min() / dz))), min(len(zg), int(math.floor(z / dz)) + 1))
        if len(zi):
            add = np.interp(zg[zi], zz[order], rr[order]) + rest * d
            env[np.ix_(bins, zi)] = np.maximum(env[np.ix_(bins, zi)], add[None, :])
        aa = max(pinch * W / 2.0, (w + 0.4) / 2.0)
        u, s_ = _teardrop(L, W, aa, n_arc=11)
        u = np.clip(u, 0.0, L)
        sway = 0.10 * (_h(seed, "sway", n_) - 0.5) * (1.0 + L / 8.0)
        s_ = s_ + sway * u                                               # a little sideways lean, more on long loops
        sg = np.linspace(0.0, L, steps + 1)
        ru, zu = np.interp(u, sg, rr), np.interp(u, sg, zz)
        c, sn = math.cos(th), math.sin(th)
        P = np.column_stack([ru * c - s_ * sn, ru * sn + s_ * c, zu])
        V, F = _tube(P, d / 2)
        acc = out.setdefault(key, [[], [], 0])
        acc[0].append(V); acc[1].append(F + acc[2]); acc[2] += len(V)
    return {k: trimesh.Trimesh(np.vstack(v[0]), np.vstack(v[1]), process=False) for k, v in out.items()}


def even_hang(even):
    """Even rows: a short single-line loop stays stiff and stands off the wall like a scale; a long one hangs."""
    if not even:
        return None
    base = min(85.0, max(40.0, 35.0 + 2.2 * float(even.get("loop_l", 10.0))))
    return (base - 5.0, base + 5.0)


def drape(wall, spots, prof, q, ribbons, style, seed=11, pieces=False, hang=None):
    """Preview only: each strand swung down about the line joining its anchors, as gravity will do it — but never
    into the wall: where the wall widens below the anchor the strand comes to rest on it. Not printable (strands
    pass through each other) — the print files always carry the flat strands."""
    lo, hi = hang or HANG[style]; out = [wall]
    for k, ((th, ch, bu, z, hh, lean, w), rib) in enumerate(zip(spots, ribbons)):
        r_w = prof(q(z) + hh / 2)
        axis = np.array([-math.sin(th), math.cos(th), 0.0])
        pivot = np.array([r_w * math.cos(th), r_w * math.sin(th), q(z) + hh / 2])
        ang = math.radians(lo + (hi - lo) * _h(seed, "hang", k))
        z_a = q(z) + hh / 2; s_ = prof(max(z_a - 2.0, 0.0)) - prof(z_a)          # wall widening per 2 mm down
        if s_ > 0:
            ang = min(ang, math.atan2(2.0, s_) - math.radians(4))              # rest on the wall, a hair off it
        R = trimesh.transformations.rotation_matrix(ang, axis, pivot)
        probe = trimesh.transform_points([pivot + [math.cos(th) * 5, math.sin(th) * 5, 0]], R)[0]
        if probe[2] > pivot[2]:
            R = trimesh.transformations.rotation_matrix(-ang, axis, pivot)
        d = rib.copy(); d.apply_transform(R); out.append((z, d) if pieces else d)
    if pieces:                                       # wall + [(anchor z, hung strand)]: colour follows the anchor
        return out[0], out[1:]
    return trimesh.util.concatenate(out)


def fur(shape, v, nz, density="medium", length="medium", draft=False, preview=False):
    """Bridge-strand fur (Cepin's "Furry Lion" method): each hair is a one-layer slab two lines wide (out and back)
    bridged from the wall to a thin sacrificial shell. After printing, cut the hairs at the shell, pull it away and
    brush/heat-style the fur. Hairs never touch: one per angle slot per layer, staggered layer to layer."""
    import manifold3d as m3d
    from .meshops import manifold_to_trimesh
    wall, prof, height, rmax, shell = body(shape, v, nz)
    lh = nz.layer_h; L = FUR_LEN.get(length, 15.0); w = 2 * nz.line_w
    z_lo, z_hi = max(1.6, 8 * lh) + lh, height - 1.5          # hair from just above the floor to just under the rim
    every = {"sparse": 3, "medium": 2, "dense": 1}.get(density, 2)
    shell_t = 2 * nz.line_w + 0.05
    # shell: follows the wall at +L from the bed to the top of the fur band
    zs = np.append(np.arange(0, z_hi + lh, 0.6), z_hi + lh)
    outer = [(prof(z) + L + shell_t, z) for z in zs]; inner = [(prof(z) + L, z) for z in zs[::-1]]
    sh = trimesh.creation.revolve(np.array(outer + inner + [outer[0]]), sections=max(120, int(2 * math.pi * (rmax + L) / 1.2)))
    if sh.volume < 0:
        sh.invert()
    # one extruded 2D cross-section per hair layer (hairs in a layer never touch): ~100 solids to union, not ~27k
    layers = []; k = int(z_lo / lh); n_hairs = 0
    while (k + 1) * lh <= z_hi:
        if (k % every) == 0:
            z0 = k * lh + 0.03; z1 = (k + 1) * lh - 0.03; zm = (z0 + z1) / 2; R = prof(zm)
            n = max(12, int(2 * math.pi * R / (w + 1.4)))
            off = 0.5 * ((k // every) % 2)
            r0, r1 = R - shell * 0.6, R + L + shell_t * 0.6
            polys = []
            for i in range(n):
                a = 2 * math.pi * (i + off) / n; c, s_ = math.cos(a), math.sin(a)
                rect = [(r0, -w / 2), (r1, -w / 2), (r1, w / 2), (r0, w / 2)]
                polys.append([(x * c - y * s_, x * s_ + y * c) for x, y in rect])
            layers.append(m3d.Manifold.extrude(m3d.CrossSection(polys), z1 - z0).translate([0, 0, z0]))
            n_hairs += n
        k += 1
    if draft:
        hairs_m = [manifold_to_trimesh(L_) for L_ in layers[:: max(1, len(layers) // 40)]]
        return trimesh.util.concatenate([wall, sh] + hairs_m), dict(strands=n_hairs, reach=round(L, 1), draped=None,
                                                                   floor_layers=int(round(max(1.6, 8 * lh) / lh)), solid=False)
    to_m = lambda t: m3d.Manifold(m3d.Mesh(vert_properties=np.asarray(t.vertices, np.float32), tri_verts=np.asarray(t.faces, np.int32)))
    merged = m3d.Manifold.batch_boolean([to_m(wall), to_m(sh)] + layers, m3d.OpType.Add)
    mesh = manifold_to_trimesh(merged)
    trimmed = None
    if preview:                                     # what you hold after cutting the hairs free of the shell
        cut = [(prof(z) + L - 0.4, z) for z in zs] + [(prof(z) + L + shell_t + 2, z) for z in zs[::-1]]
        tube = trimesh.creation.revolve(np.array(cut + [cut[0]]), sections=max(120, int(2 * math.pi * (rmax + L) / 1.2)))
        if tube.volume < 0:
            tube.invert()
        trimmed = manifold_to_trimesh(merged - to_m(tube))
    return mesh, dict(strands=n_hairs, reach=round(L, 1), draped=trimmed, floor_layers=int(round(max(1.6, 8 * lh) / lh)),
                      solid=False)


def build(shape, v, nz, style="fringe", density="medium", length="medium", preview=False, draft=False, aligned=False,
          panels=None, even=None):
    import manifold3d as m3d
    if style == "fur":
        return fur(shape, v, nz, density, length, draft, preview)
    wall, prof, height, rmax, shell = body(shape, v, nz)
    spots = _rows(style, prof, height, nz, DENSITY.get(density, 1.0), LENGTH.get(length, 1.0), aligned=aligned,
                  panels=panels, even=even)
    embed = shell * 0.55
    lh = nz.layer_h
    q = lambda z: (math.floor(z / lh) + 0.25) * lh           # quarter-layer shift: no strand face is coplanar with
                                                             # the wall's rings (coplanar unions leave slivers)
    spots = _never_touch(spots, prof, q)
    ribbons = [_ribbon(th, ch, bu, q(z), hh, w, prof, embed, _SPEC[style]["power"], lean)
               for th, ch, bu, z, hh, lean, w in spots]
    if draft:                                                   # preview only: skip the (slow) union
        mesh = trimesh.util.concatenate([wall] + ribbons)
    else:
        to_m = lambda t: m3d.Manifold(m3d.Mesh(vert_properties=np.asarray(t.vertices, np.float32),
                                                tri_verts=np.asarray(t.faces, np.int32)))
        from .meshops import manifold_to_trimesh
        merged = m3d.Manifold.batch_boolean([to_m(wall)] + [to_m(r) for r in ribbons], m3d.OpType.Add)
        solid = [c for c in merged.decompose() if abs(c.volume()) > 0.5]
        if len(solid) != 1:
            raise ValueError(f"droop build produced {len(solid)} solid bodies — a strand is detached")
        mesh = manifold_to_trimesh(solid[0])
    reach = max((bu for _, _, bu, _, _, _, _ in spots), default=0.0)
    drape_pieces = drape(wall, spots, prof, q, ribbons, style, pieces=True, hang=even_hang(even)) if preview else None
    draped = (trimesh.util.concatenate([drape_pieces[0]] + [r_ for _, r_ in drape_pieces[1]])
              if preview else None)                             # hung once, per strand; the whole is their sum
    info = dict(strands=len(spots), reach=round(reach, 1), draped=draped, drape_pieces=drape_pieces,
                courses=courses(spots, lh), course_gap=max(_SPEC[style]["row"], _SPEC[style]["tall"] + 1) * lh,
                floor_layers=int(round(max(1.6, 8 * nz.layer_h) / nz.layer_h)), solid=bool(getattr(shape, "solid", False)))
    return mesh, info
