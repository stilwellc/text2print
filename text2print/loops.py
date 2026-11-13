"""Loops on colour-knit: ready-made looks for the colourwork textures (jacquard, beads).

A colourwork wall already changes colour layer by layer, so a ONE-layer loop hung from it takes its layer's colour
for free. A look pairs a loop layout (`droop._tier_rows`) with a colour plan for the knit under it:

    tiers    teardrop loops in brick-offset rows, a fringe of long hairpins under the rim
    shag     short scallops, close rows: a shaggy coat
    fringe   two side panels of long, uneven hairpins over a bare knit front and back
    window   the fringe wraps the piece and leaves one arched knit window at the front
("front" is pictures.FRONT_U, 315 degrees: the side the studio camera looks at, where a "front" picture and a
once-only motif also sit)
    petals   scallops that lengthen down overlapping petals, each petal one colour

    plan "rows"    each loop row (and the wall it hangs from) takes one colour, faded up the piece
    plan "salt"    a ground colour with single stitches of a second scattered through it; loops match their stitch
    plan "petals"  the knit under each petal is that petal's colour
    plan "chart"   keep whatever chart was chosen; loops take the colour of the stitch under them

Print: one bead per loop (the project sets min_bead_width 200 %), low fan, overhang slow-down off. Loops are not
print-verified on any nozzle yet: print a small piece first."""
import math
import types

import numpy as np

from . import colourwork, droop
from .halftone import RECIPE

LOOKS = {
    "tiers": dict(name="Teardrop tiers", plan="rows", loops=dict(
        loop_w=4.0, loop_l=9.0, tier=2.24, pinch=0.3, line=1.0, gap=0.5, collar=6.0,
        crown_rows=3, crown_l=14.0, crown_w=2.4, crown_tier=0.56, crown_step=3.0)),
    "shag": dict(name="Shag", plan="rows", loops=dict(
        loop_w=3.2, loop_l=6.0, tier=1.4, pinch=0.9, line=1.0, gap=0.5, collar=6.0, l_min=3.0,
        crown_rows=2, crown_l=6.5, crown_w=2.0, crown_tier=0.56)),
    "fringe": dict(name="Fringe panels", plan="chart", loops=dict(
        loop_w=3.4, loop_l=17.0, tier=0.84, pinch=0.3, line=0.8, gap=0.5, vary=0.45, stray=0.08, collar=8.0,
        panels=2, panel_width=115, panel_offset=45)),          # at the silhouette edges seen from the front (315 deg)
    "window": dict(name="Fringe and a window", plan="salt", loops=dict(
        loop_w=3.4, loop_l=16.0, tier=0.84, pinch=0.3, line=0.8, gap=0.5, vary=0.35, collar=8.0,
        panels=1, panel_width=250, panel_offset=135, edge_taper=4, grow=0.4, crown_rows=3, crown_l=7.0, crown_w=2.4)),
    "petals": dict(name="Petal ruffles", plan="petals", loops=dict(
        loop_w=4.8, loop_l=15.0, tier=1.96, pinch=1.0, line=1.0, gap=0.5, collar=7.0, l_min=4.5,
        petal=13.0, petal_sag=9.0, petals=5, petal_share=0.38, petal_seed=3, flounce_gain=0.62)),
}
SIZES = {"small": 0.8, "regular": 1.0, "large": 1.5}
_SCALED = ("loop_w", "loop_l", "tier", "collar", "l_min", "crown_l", "crown_w", "crown_step", "petal", "petal_sag")


def _wall(S, v, nz, rim="none"):
    """The colourwork wall's layer grid, exactly as colourwork.build lays it out."""
    lh, lw = RECIPE[nz.size]; prof, H, rmax = S.profile(v)
    n_floor = int(math.ceil(max(1.2, 4 * lh) / lh))
    rim_layers = int(round(3.4 / lh)) if rim in ("braid", "rope") else 0
    n_wall = max(4, int(round(H / lh)) - n_floor - rim_layers)
    return lh, lw, prof, H, rmax, n_floor, n_wall


def _rows(lh, row_mm, band, colours=2):
    unit = colours * band
    return unit * max(1, int(round(row_mm / (unit * lh))))


def _cols(rmax, lw, size, style="jacquard"):
    """Stitches around and the row height, as colourwork.build computes them (bead rows are square, ribs 5 % short)."""
    col_mm = max(colourwork.SIZES.get(size, 3.2) * lw, 2.6 * lw)
    cols = max(24, int(round(2 * math.pi * rmax / col_mm)))
    return cols, (1.0 if style == "beads" else 0.95) * 2 * math.pi * rmax / cols


def dealer(weights):
    """Deal rows to colours by error diffusion: the mix follows weights(u) exactly, with no long runs."""
    acc = []

    def zone_of(u):
        w = weights(u); sw = sum(w) or 1.0
        if not acc:
            acc.extend([0.0] * len(w))
        for j, x in enumerate(w):
            acc[j] += x / sw
        k = max(range(len(w)), key=lambda j: acc[j]); acc[k] -= 1.0
        return k
    return zone_of


def fade(n, blend=0.4):
    """Weights for n colours faded up the piece: the first owns the foot, the last the top, any between are a
    thinner accent through the middle."""
    def w(u):
        return [(1.0 if i in (0, n - 1) else 0.62) * math.exp(-((u - i / max(n - 1, 1)) / blend) ** 2) for i in range(n)]
    return w


def row_chart(S, v, nz, loops, n_colours=3, rim="none"):
    """Colour by ROW: each loop row and the wall under it take one colour (`{"course": [...]}` band); the bare neck
    above the top row is colour 0; the fringe rows under the rim cycle through the colours so each one shows."""
    lh, lw, prof, H, rmax, n_floor, n_wall = _wall(S, v, nz, rim); wall_top = (n_floor + n_wall) * lh
    ns = types.SimpleNamespace(layer_h=lh, line_w=lw)
    ev = dict(droop.even_options(dict(loops, rows="even")), tall=1, line=float(loops.get("line", lw)))
    spots = droop._tier_rows(prof, wall_top, ns, ev, 11, ((n_floor + 2) * lh, wall_top - 2 * lh))
    rows = sorted({int(round(s[3] / lh)) for s in spots})
    if not rows:
        return [{"plain": 0, "mm": H}]
    deal = dealer(fade(n_colours))
    zone = [deal((i + 0.5) / len(rows)) for i in range(len(rows))]
    crown = int(loops.get("crown_rows", 0))
    for i in range(min(crown, len(rows))):                      # top row first
        zone[len(rows) - 1 - i] = (n_colours - 1 - i) % n_colours
    course, r = [], 0
    for k in range(n_wall):
        L = n_floor + k
        while r + 1 < len(rows) and L >= rows[r + 1] - min(3, (rows[r + 1] - rows[r]) // 2):
            r += 1
        course.append(zone[r])
    top = rows[-1] + 4 - n_floor
    course[top:] = [0] * (len(course) - top)
    return [{"course": course}]


def salt_chart(S, v, nz, size="regular", band=2, share=0.16, rows=0.5, settle=0.6, neck_mm=None, line_mm=5.0,
               top_motif=("X...", ".X.X", "..X."), seed=7, rim="none", style="jacquard"):
    """Salt on pepper: colour 0 with single colour-1 stitches scattered through it, a thin colour-1 line at the foot
    and under the rim, and a small motif round the neck. Salt sits in only `rows` of the stitch rows (a row of one
    colour costs no filament changes), denser there so the total stays `share`, and settles toward the foot."""
    lh, lw, prof, H, rmax, n_floor, n_wall = _wall(S, v, nz, rim)
    cols, row_mm = _cols(rmax, lw, size, style); R = _rows(lh, row_mm, band)
    top = n_wall - 2 - int(round(line_mm / lh))
    motif = [(m * (cols // len(m) + 1))[:cols] for m in (top_motif or [])]
    body = top - len(motif) * R
    rng = np.random.default_rng(seed); art, used, last, run = [], 0, None, 0
    while used + R <= body:
        u = used / max(body, 1)
        want = rng.random() < rows * (1 + settle * (1 - 2 * u))
        if last is not None and run >= 2 and want == last:
            want = not want
        run = run + 1 if want == last else 1; last = want
        dens = min(0.6, share / max(rows, 0.05) * (1 + settle * (1 - 2 * u)))
        on = (rng.random(cols) < dens) if want else np.zeros(cols, bool)
        if want and not on.any():
            on[rng.integers(cols)] = True
        art.append("".join("X" if o else "." for o in on)); used += R
    bands = [{"plain": 1, "mm": 2 * lh}]
    if art:
        bands.append({"art": art[::-1], "colours": [0, 1], "gap": 0})
    if body - used > 0:
        bands.append({"plain": 0, "mm": (body - used) * lh})
    if motif:
        bands.append({"art": motif, "colours": [0, 1], "gap": 0})
    return bands + [{"plain": 1, "mm": 2 * lh}, {"plain": 0, "mm": H}]


def petal_chart(S, v, nz, loops, size="regular", band=2, rim="none", style="jacquard"):
    """The knit under petal ruffles: every stitch takes its petal's colour (droop.petal_field / petal_slot)."""
    lh, lw, prof, H, rmax, n_floor, n_wall = _wall(S, v, nz, rim)
    cols, row_mm = _cols(rmax, lw, size, style); R = _rows(lh, row_mm, band)
    n_rows = max(1, int((n_wall - float(loops.get("collar", 7.0)) / lh) / R))
    th = (np.arange(cols) + 0.5) / cols * 2 * math.pi
    art = []
    for r in range(n_rows):
        z = (n_floor + R * r + R / 2) * lh
        _, lid = droop.petal_field(th, np.full(cols, z), float(loops["petal"]), float(loops.get("petal_sag", 0.7 * loops["petal"])),
                                   int(loops.get("petals", 5)))
        on = droop.petal_slot(lid, float(loops.get("petal_share", 0.38)), int(loops.get("petal_seed", 3))) == 1
        art.append("".join("X" if o else "." for o in on))
    return [{"art": art[::-1], "colours": [0, 1], "gap": 0}, {"plain": 0, "mm": H}]


def resolve(look, options, S, v, nz, n_colours=3, style="jacquard"):
    """A look name + the picker's options -> (chart or None, loops spec for droop.colourwork_loops).
    options: loop_size small|regular|large, loop_colour auto|rows|salt|petals|chart, stitch_size, band, rim."""
    if look not in LOOKS:
        raise ValueError(f"no loop look called {look!r} (have {', '.join(LOOKS)})")
    L = LOOKS[look]; k = SIZES.get(options.get("loop_size", "regular"), 1.0)
    spec = {key: (val * k if key in _SCALED else val) for key, val in L["loops"].items()}
    kn = RECIPE[nz.size][1] / RECIPE[0.4][1]                     # strand and gap follow the nozzle's line, as the wall does
    spec["line"] *= kn; spec["gap"] *= kn
    H = S.profile(v)[1]
    if look == "window":                                        # the window closes in an arch under the shoulder
        spec.update(arch_spring=0.6 * H, arch_top=0.85 * H, bed_reach=0.35 * spec["loop_l"])
    plan = options.get("loop_colour") or "auto"
    plan = L["plan"] if plan == "auto" else plan
    if plan == "petals" and "petal" not in spec:
        plan = "salt"
    size, band, rim = options.get("stitch_size", "regular"), max(1, int(options.get("band", 1) or 1)), options.get("rim", "none")
    if plan == "rows":
        return row_chart(S, v, nz, spec, max(2, min(3, int(n_colours))), rim), dict(spec, colour="layer")
    if plan == "salt":
        return salt_chart(S, v, nz, size, band, rim=rim, style=style), dict(spec, colour="chart")
    if plan == "petals":
        return petal_chart(S, v, nz, spec, size, band, rim, style), dict(spec, colour="petal")
    return None, dict(spec, colour="chart")
