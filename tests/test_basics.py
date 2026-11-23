"""Plain cans, boxes and plaques, and a catalogue shape traced from a picture."""
import json

import numpy as np
import pytest

from text2print import basics, extras, fits, part, shapes
from text2print.__main__ import main


def _seated(base, lid, top):
    return (extras._m3d(base) ^ extras._m3d(lid).rotate([180, 0, 0]).translate([0, 0, top + extras.LID_T]))


def test_a_can_is_solid_walled_and_its_lids_seat_without_cutting_in():
    c = basics.can(70, 40); base, lid = c["parts"]["Base"][0][1], c["parts"]["Lid"][0][1]
    assert base.is_watertight and lid.is_watertight and len(base.split()) == 1 and len(lid.split()) == 1
    assert round(part.span(base, (33.5, 0, 10), "x")[0], 2) == 2.4 and abs(lid.bounds[1][0] - 35.0) < 0.01     # wall; lid flush
    overlap = [_seated(base, lid, 40).rotate([0, 0, 0]).volume()] + \
              [(extras._m3d(base) ^ extras._m3d(lid).rotate([180, 0, 0]).translate([0, 0, 40 + extras.LID_T]).rotate([0, 0, a])).volume() for a in range(6, 360, 6)]
    assert min(overlap) < 0.5                                                           # one turn finds the seat
    s = basics.can(60, 30, lid="slip")
    assert _seated(s["parts"]["Base"][0][1], s["parts"]["Lid"][0][1], 30).volume() < 0.01
    assert list(basics.can(60, 30, lid="none")["parts"]) == ["Base"]
    with pytest.raises(ValueError, match="42 mm"):
        basics.can(36, 30)


def test_a_box_lid_follows_the_opening():
    b = basics.box(90, 60, 35); base, lid = b["parts"]["Base"][0][1], b["parts"]["Lid"][0][1]
    assert base.is_watertight and lid.is_watertight and _seated(base, lid, 35).volume() < 0.01
    gap = part.span(base, (0, 0, 6), "x")[0] - 2 * extras.LIP_W - (part.span(lid, (0, 0, 5), "x")[0])            # opening - plug
    assert round(part.span(base, (0, 0, 6), "x")[0], 2) == 85.2 and lid.bounds[1][0] <= 45.0 + 1e-6


def test_a_plaque_sets_its_words_flush_and_reports_what_prints():
    p = basics.plaque(90, 36, text="STILWELL", hole=4)
    plate, art = p["parts"][0][1], p["parts"][1][1]
    assert plate.is_watertight and art.is_watertight and abs(plate.volume + art.volume - (90 * 36 - (4 - np.pi) * 16 - np.pi * 4) * 3) < 15
    assert art.bounds[0][2] == 0 and abs(art.bounds[1][2] - 0.6) < 1e-6 and p["mirror"] and np.abs(art.bounds[:, 0]).max() <= 39.01
    tiny = basics.plaque(40, 12, text="a very long line of words", margin=2)
    assert any("lose detail" in n for n in tiny["notes"])
    with pytest.raises(ValueError, match="text, an image"):
        basics.plaque(90, 36)


def test_the_cli_delivers_a_can_and_a_coupon(tmp_path, capsys):
    assert main(["basic", "can", "--set", "diameter=60", "--set", "height=30", "--lid", "slip", "--material", "petg", "--out", str(tmp_path / "can")]) == 0
    r = json.loads(capsys.readouterr().out)
    assert r["pieces"]["Base"] == [60.0, 60.0, 30.0] and abs(r["pieces"]["Lid"][0] - 60) < 0.05 and (tmp_path / "can" / "can_lid.stl").exists()
    assert main(["coupon", "hole", "16", "--out", str(tmp_path / "c")]) == 0
    assert json.loads(capsys.readouterr().out)["steps"] == list(fits.STEPS)
    assert main(["basic", "can", "--set", "diameter=30", "--out", str(tmp_path / "x")]) == 2 and "error" in json.loads(capsys.readouterr().out)


def test_a_shape_traced_from_a_picture_joins_the_catalogue(tmp_path, monkeypatch):
    from PIL import Image, ImageDraw
    from text2print import build, plugins
    im = Image.new("L", (600, 400), 255); d = ImageDraw.Draw(im)
    d.ellipse([40, 60, 400, 340], fill=0); d.ellipse([300, 100, 560, 300], fill=0)               # a pebble: two blobs joined
    im.save(tmp_path / "pebble.png")
    monkeypatch.setattr(plugins, "DIR", tmp_path / "plugins")
    path = plugins.new("shape", "my_pebble", image=tmp_path / "pebble.png", width=120)
    assert path.exists() and "polygon_sdf" in path.read_text()
    try:
        assert "s_my_pebble" in plugins.load_all()
        S = shapes.SHAPES["s_my_pebble"]; v = S.resolve({"width": 120, "height": 30})
        sdf = S._fn(v)
        assert sdf(0.0, 0.0) < 0 and sdf(200.0, 0.0) > 0 and abs(float(sdf(np.array([60.0]), np.array([0.0]))[0])) < 6     # 120 wide
        b = build.make("s_my_pebble", "zigzag", {"width": 120, "height": 30}, draft=True)
        size = np.ptp(np.vstack([m.vertices for _, m, *_ in b.parts]), axis=0)
        assert 110 < size[0] < 130 and 55 < size[1] < 85                                           # the picture's own proportions
    finally:
        shapes.SHAPES.pop("s_my_pebble", None); extras.LID_SHAPES.discard("s_my_pebble")
    f = shapes.polygon_sdf([(-10, -5), (10, -5), (10, 5), (-10, 5)])
    assert abs(float(f(0, 0)) + 5) < 0.2 and abs(float(f(13, 0)) - 3) < 0.2
