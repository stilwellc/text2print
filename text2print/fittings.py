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
        out.append((n, _t(man), s, c))
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
    "sleeve": "Slides over your glass liner (1 mm clearance a side); the liner holds the water.",
}
