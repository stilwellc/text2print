"""Standard interfaces built once and reused by shapes (values from the Oct 2026 research, docs/research-2026-10.md):

  E26/E27 shade collar  40 mm hole in a ~3-4 mm solid collar plate
  Bambu LED Lamp Kit 001 puck  59 x 18 mm  -> pocket 59.7 x 18.3 with a USB-C cable notch
  Tealight 38 x 16 (LED 37.2 x 36.6)  -> pocket 41 x 17 in a solid plinth
  Taper candle ~22 mm  -> 23 mm bore with crush ribs down to ~22
  Nursery pots 4/6/8 in  -> cachepot inner diameter pot + 5 mm, a raised foot ring so the pot drains
  Glass liner  -> inner bore = liner + 1 mm a side
A fitting is applied to the finished piece: solids are unioned into the part that holds the floor, cuts go through
every part. All values are mm."""
import math

import numpy as np
import trimesh

E27_HOLE = 40.0
PUCK = (59.0, 18.0)                 # diameter, height of the Bambu LED Lamp Kit 001 puck
PUCK_CLEAR = 0.35                   # per side
TEALIGHT_POCKET = (41.0, 17.0)
TAPER_BORE, TAPER_RIB = 23.0, 0.5
POT_CLEAR = 5.0
LINER_GAP = 1.0
# Glass mason jars (regular 70 mm and wide 86 mm mouths): one continuous right-hand thread at 4 per inch. The lid's
# inside wall clears the glass thread crests; its own ridge reaches in under them. NOT print-verified: the pitch is
# the published figure, the depths are set from typical jars. Print one and check before making several.
MASON = dict(pitch=6.35, turns=1.1, depth=1.4, clear=0.3, liner=2.4, top=3.0, start=4.5)


def _m(mesh):
    import manifold3d as m3d
    return m3d.Manifold(m3d.Mesh(vert_properties=np.asarray(mesh.vertices, np.float32),
                                 tri_verts=np.asarray(mesh.faces, np.int32)))


def _t(man):
    from .meshops import manifold_to_trimesh
    return manifold_to_trimesh(man)


def _cyl(r, z0, z1, n=128):
    import manifold3d as m3d
    return m3d.Manifold.cylinder(z1 - z0, r, r, n).translate([0, 0, z0])


def _ring(r0, r1, z0, z1, n=160):
    return _cyl(r1, z0, z1, n) - _cyl(r0, z0 - 0.5, z1 + 0.5, n)


def _thread_in(r_wall, depth, lead, turns, z0, n_per_turn=120, embed=0.4):
    """One right-hand ridge on the INSIDE of a bore of radius r_wall: a 45-degree triangle `depth` tall whose
    centre climbs `lead` per turn from z0. (cos a, sin a, z rising with a) is a right-hand helix whichever way up
    the part is printed."""
    import manifold3d as m3d
    n = max(12, int(n_per_turn * turns)); w = depth; V, F = [], []
    for i in range(n + 1):
        a = 2 * math.pi * turns * i / n; zc = z0 + lead * turns * i / n
        k = min(1.0, i / 8, (n - i) / 8)                         # the ridge ramps in and out over a few steps
        ca, sa = math.cos(a), math.sin(a)
        for rr, zz in ((r_wall + embed, zc - w - embed), (r_wall - depth * max(k, 0.15), zc), (r_wall + embed, zc + w + embed)):
            V.append([rr * ca, rr * sa, zz])
    for i in range(n):
        p_, q_ = 3 * i, 3 * (i + 1)
        for k in range(3):
            k2 = (k + 1) % 3
            F += [[p_ + k, q_ + k, q_ + k2], [p_ + k, q_ + k2, p_ + k2]]
    F += [[0, 2, 1], [3 * n, 3 * n + 1, 3 * n + 2]]
    mesh = trimesh.Trimesh(np.array(V), np.array(F), process=True)
    trimesh.repair.fix_winding(mesh); trimesh.repair.fix_normals(mesh)
    if mesh.volume < 0:
        mesh.invert()
    return _m(mesh)


def plan(shape_key, v, prof, shell):
    """-> (adds, cuts) manifold lists for this shape's fitting, or ([], [])."""
    import manifold3d as m3d
    adds, cuts = [], []
    if shape_key == "pendant":
        cuts.append(_cyl(E27_HOLE / 2, -1.0, 8.0))
    elif shape_key == "puck":
        r = PUCK[0] / 2 + PUCK_CLEAR; h = PUCK[1] + 0.3
        adds.append(_ring(r - 0.01, prof(h / 2) - shell * 0.5, 0.0, h + 2.0))      # solid collar the puck sits in
        cuts.append(_cyl(r, -1.0, h))
        cuts.append(m3d.Manifold.cube([14.0, prof(0) + 6, 9.0], False).translate([-7.0, -(prof(0) + 6), -0.5]))
    elif shape_key == "lantern":
        rin = prof(10) - shell - 0.05; top = 20.0
        adds.append(_cyl(rin, 0.0, top))
        cuts.append(_cyl(TEALIGHT_POCKET[0] / 2, top - TEALIGHT_POCKET[1], top + 1.0))
    elif shape_key == "cachepot":
        rid = (v["pot"] * 25.4 + POT_CLEAR) / 2; rr = rid * 0.62
        adds.append(_ring(rr, rr + 4.0, 0.5, 9.0))                                  # foot ring lifts the pot
    elif shape_key == "jarlid":
        M = MASON; r_in = v["inside"] / 2 + M["clear"]; h = v["skirt"] + M["top"]; r_out = prof(h / 2) - shell * 0.5
        adds.append(_cyl(r_out, 0.0, M["top"]))                                    # the top plate (printed on the bed)
        adds.append(_ring(r_in, r_out, M["top"] - 0.01, h))                        # the liner the thread grows from
        adds.append(_thread_in(r_in, M["depth"], M["pitch"], min(M["turns"], max(0.5, (v["skirt"] - M["start"] - 2 * M["depth"] - 1.0) / M["pitch"])),
                               M["top"] + M["start"] + M["depth"]))
    elif shape_key == "candle":
        top = v["height"]; sock = TAPER_BORE / 2
        for k in range(6):
            a = 2 * math.pi * k / 6
            rib = m3d.Manifold.cube([1.2, TAPER_RIB + 0.6, 16.0], True).translate([0, sock - TAPER_RIB / 2 + 0.3, top - 8.0])
            adds.append(rib.rotate([0, 0, math.degrees(a)]))
    return adds, cuts


def apply(parts, shape_key, v, prof, shell):
    """parts: [(name, mesh, slot, colour)] -> same with the fitting applied.
    Added solids become their own part in the floor's colour: Bambu merges overlapping parts of one filament
    (verified: two overlapping parts slice identical to their union), and a boolean union would shred fabric walls
    whose fins step out further than the shell (their layer-step faces overlap in one plane). Other colours have the
    solid carved out so each region has exactly one filament. Cuts are booleans on every part."""
    adds, cuts = plan(shape_key, v, prof, shell)
    if not adds and not cuts:
        return parts
    import manifold3d as m3d
    low = min(range(len(parts)), key=lambda i: parts[i][1].bounds[0][2])
    added = m3d.Manifold.batch_boolean(adds, m3d.OpType.Add) if adds else None
    out = []
    for i, (n, mesh, s, c) in enumerate(parts):
        if i != low and added is not None:
            man = _m(mesh) - added
        elif cuts:
            man = _m(mesh)
        else:
            out.append((n, mesh, s, c)); continue
        for cut in cuts:
            man = man - cut
        res = _t(man)
        if not len(res.faces) and len(mesh.faces):           # a sketch build's open mesh: a boolean empties it, and an
            res = mesh                                       # empty part crashes everything after. Keep it uncut.
        out.append((n, res, s, c))
    if added is not None:
        for cut in cuts:
            added = added - cut
        n, _, s, c = parts[low]
        out.append(("fitting", _t(added), s, c))
    return out


NOTES = {
    "pendant": "E27/E26 collar: 40 mm hole. LED bulbs only (≤10 W, PLA softens near 60 °C) and keep 30 mm between bulb and shade.",
    "puck": "Fits Bambu's LED Lamp Kit 001 puck (59 × 18 mm); the notch at the back is for its USB-C cable.",
    "lantern": "Tealight pocket 41 × 17 mm. Use an LED tealight or a glass cup — a real tealight puts out ~32 W.",
    "candle": "Taper bore 23 mm with crush ribs (grips ~22 mm candles). Never leave a lit candle unattended; PLA softens near 60 °C.",
    "cachepot": "Holds a nursery pot, not water — the foot ring lifts the pot so it can drain.",
    "jarlid": "Mason jar thread (4 per inch, right-hand), printed top down. Not print-verified: check the fit on your jar. "
              "It closes the jar but is not a canning seal; add a gasket for liquids.",
    "sleeve": "Slides over your glass liner (1 mm clearance a side, following its taper); the liner holds the water.",
}
