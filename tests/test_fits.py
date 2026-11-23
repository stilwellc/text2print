"""Helpers for functional parts: coupons, the keyed split, grips, grilles, inlaid art and its check."""
import manifold3d as m3
import numpy as np
import pytest
import trimesh
from shapely.geometry import Point, box

from text2print import bambu, fits, meshops, part


def _bell():
    return m3.Manifold.cylinder(30, 22, 12, 128) - m3.Manifold.cylinder(32, 8.5, 8.5, 96).translate([0, 0, -1])


def test_coupons_are_one_solid_each_and_step_from_tight_to_loose():
    for kind, nominal, n_parts in (("hole", 16, 1), ("slot", 3, 1), ("dovetail", 0, 2)):
        c = fits.coupon(kind, nominal)
        assert c["steps"] == fits.STEPS and len(c["parts"]) == n_parts
        assert all(m.is_watertight and len(m.split()) == 1 for _, m in c["parts"]) and max(c["size"]) < 200
    hole = fits.coupon("hole", 16)["parts"][0][1]; y = -1.5
    xs = np.linspace(hole.bounds[0][0] + 0.01, hole.bounds[1][0] - 0.01, 6 * 2 + 1)[1::2]      # one point in each hole
    got = [round(part.span(hole, (x, y, 2), "x")[0] - 16, 2) for x in xs]
    assert np.allclose(got, [2 * s for s in fits.STEPS], atol=0.03)                             # diameter grows by two clearances
    slot = fits.coupon("slot", 3)["parts"][0][1]
    assert round(part.span(slot, (slot.bounds[0][0] + 3 + 1.9, 0, 6), "x")[0], 2) == round(3 + 2 * fits.STEPS[0], 2)
    with pytest.raises(ValueError, match="1 to 40"):
        fits.coupon("hole", 60)


def test_a_keyed_split_gives_two_halves_that_meet_without_colliding():
    body = _bell(); A, B = fits.split_keyed(body, (-13, 13))
    assert (A ^ B).volume() < 1e-6 and abs(A.volume() + B.volume() - body.volume()) < body.volume() * 0.01
    a, b = meshops.manifold_to_trimesh(A, split=False), meshops.manifold_to_trimesh(B, split=False)
    assert a.is_watertight and b.is_watertight and a.bounds[0][1] < -1.9 and b.bounds[1][1] <= 1e-6   # keys reach into B's side
    slot_w = part.span(b, (13, -1.9, 1), "x")[0]
    assert abs(slot_w - (fits.DOVETAIL["head"] + 2 * fits.DOVETAIL["clear"])) < 0.25                # the slot is the key plus clearance
    with pytest.raises(ValueError, match="leaves the body"):
        fits.split_keyed(body, (-21.5, 21.5))


def test_grips_stand_where_they_were_asked_to():
    ribs = fits.crush_ribs(23.0, 16.0, n=6, bite=0.3); v = meshops.manifold_to_trimesh(ribs, split=False).vertices
    assert len(ribs.decompose()) == 6 and abs(np.hypot(v[:, 0], v[:, 1]).min() - (11.5 - 0.3)) < 0.02
    lo = fits.bump((10, 0, 5), "+x", proud=1.2, width=12).bounding_box()
    assert np.allclose(lo, [9.7, -6, 3.8, 11.2, 6, 6.2], atol=1e-6)
    lo = fits.bump((0, -10, 5), "-y", proud=1.2, width=12).bounding_box()
    assert abs(lo[1] - (-11.2)) < 1e-6 and abs(lo[3] - 6) < 1e-6
    s = fits.sheet_slot(3.0, 20.0, 8.0, clear=0.25).bounding_box()
    assert np.allclose(s, [-2.35, -10, -8, 2.35, 10, 0.5], atol=1e-6)                               # 3.5 wide below a 0.6 lead-in


def test_a_grille_refuses_holes_the_plate_cannot_print_and_keeps_its_lands():
    with pytest.raises(ValueError, match="will not all print"):
        fits.grille(60, 90, 1.6, hole=1.8)
    fits.grille(60, 90, 1.6, hole=1.8, on_plate=False)
    for pattern in ("square", "hex"):
        cut, n = fits.grille(60, 90, 1.6, corner=10, pattern=pattern)
        cs = np.array([[(b.bounding_box()[0] + b.bounding_box()[3]) / 2, (b.bounding_box()[1] + b.bounding_box()[4]) / 2] for b in cut.decompose()])
        d = np.hypot(*(cs[:, None] - cs[None]).transpose(2, 0, 1)); d[d == 0] = 9e9
        assert n == len(cs) > 50 and d.min() >= fits.MIN_HOLE + fits.MIN_LAND - 1e-6               # every land holds
        assert np.abs(cs[:, 0]).min() < 1e-6 and np.abs(cs).max(0)[0] <= 30 - 2.5 - 1.5 + 1e-6      # a centre column; inside the margin
    cut, n = fits.grille(60, 90, 2.0, blind=0.4)
    assert abs(cut.bounding_box()[2] - 0.4) < 1e-6


def test_art_too_fine_to_print_is_removed_and_an_inlay_sits_flush():
    art = Point(0, 0).buffer(6).union(box(6, -0.1, 12, 0.1)).difference(box(-0.1, -7, 0.1, 7)).union(Point(15, 0).buffer(0.15))
    clean, info = fits.printable(art, min_feature=0.4)
    assert info["pieces"] == 1 and clean.bounds[2] < 6.2 and abs(clean.area - Point(0, 0).buffer(6).area) < 1.0   # hairline, slit and speck gone
    word, _ = fits.words("OK", 10)
    disc = m3.Manifold.cylinder(3, 20, 20, 128)
    body, plug = fits.inlay(disc, word, depth=0.6)
    assert (body ^ plug).volume() < 1e-6 and abs(body.volume() + plug.volume() - disc.volume()) < 1e-3
    assert abs(plug.volume() - word.area * 0.6) < 0.5 and plug.bounding_box()[2] == 0 and abs(plug.bounding_box()[5] - 0.6) < 1e-6
    top = fits.inlay(disc, word, depth=0.6, face="top")[1].bounding_box()
    assert abs(top[2] - 2.4) < 1e-6 and abs(top[5] - 3.0) < 1e-6
    with pytest.raises(ValueError, match="misses"):
        fits.inlay(disc, word, at=(60, 0))


def test_a_traced_picture_comes_out_at_the_size_asked(tmp_path):
    from PIL import Image, ImageDraw
    im = Image.new("L", (400, 300), 255); d = ImageDraw.Draw(im)
    d.ellipse([50, 50, 350, 250], fill=0); d.ellipse([150, 100, 250, 200], fill=255); d.line([0, 5, 400, 5], fill=0, width=1)
    im.save(tmp_path / "mark.png")
    art, info = fits.trace(tmp_path / "mark.png", 40.0)
    assert len(art.interiors if hasattr(art, "interiors") else art.geoms[0].interiors) == 1             # the white middle stays white
    assert info["pieces"] == 1 and 25 < info["size"][0] <= 40.5                                         # the hairline is dropped


def test_the_artwork_check_reads_a_layer_by_filament(tmp_path):
    def fill(x0, x1, y0, y1):                                           # 0.42 lines at 0.2: E per mm = w * h / filament area
        out = []; e = 0.42 * 0.2 / (np.pi * 0.875 ** 2)
        for k, y in enumerate(np.arange(y0 + 0.21, y1, 0.42)):
            a, b = (x0, x1) if k % 2 == 0 else (x1, x0)
            out += [f"G1 X{100 + a:.3f} Y{100 + y:.3f} F6000", f"G1 X{100 + b:.3f} Y{100 + y:.3f} E{e * abs(b - a):.5f} F900"]
        return out
    g = ["; filament_flow_ratio = 1,1", ";VT0 H-1", "; CHANGE_LAYER", "; Z_HEIGHT: 0.2", "; LAYER_HEIGHT: 0.2", "G1 Z0.2 F600"]
    g += fill(-10, 10, -10, 0) + ["T1"] + fill(-10, 0, 0, 10)                       # white lower half; black only on the upper LEFT
    f = tmp_path / "a.gcode"; f.write_text("\n".join(g))
    r = fits.artwork_check(f, {1: box(-10, -10, 10, 0), 2: box(-10, 0, 10, 10)}, centre=(100, 100), out_png=tmp_path / "a.png")
    assert r[1]["printed"] > 0.97 and 0.45 < r[2]["printed"] < 0.55 and 0.45 < r[2]["bare"] < 0.55 and (tmp_path / "a.png").exists()
    r = fits.artwork_check(f, {2: box(0, 0, 10, 10)}, centre=(100, 100), mirror=True)   # mirrored art lands on the printed half
    assert r[2]["printed"] > 0.95
    r = fits.artwork_check(f, {2: box(-10, -10, 10, 0)}, centre=(100, 100))
    assert r[2]["wrong_colour"] > 0.95
