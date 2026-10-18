"""Oct 15 vision board: colourwork (jacquard / beads + charts), lidded boxes, labyrinth lids, tube knob, paneled
vessels, CHART plugins."""
import re
import zipfile

import numpy as np
import pytest

from text2print import bambu, build, colourwork as cw, lattice, plugins, printer
from text2print.shapes import SHAPES, panel_factor

C3 = ["#8B3A2F", "#F4F1E8", "#C58A3F"]


def _wt(b):
    return all(m.is_watertight for _, m, _, _ in b.parts)


def test_motifs_parse_and_tile_whole_repeats():
    for k, m in cw.MOTIFS.items():
        a = cw.art_grid(m["art"])
        assert a.ndim == 2 and a.max() <= 2, k
    a = cw.art_grid(cw.MOTIFS["hearts"]["art"])                 # 8 wide
    t = cw.tile(a, 85)
    assert t.shape == (a.shape[0], 85)
    assert (t[:, :8] == a).all()                                 # starts with a whole repeat, no cut
    once = cw.tile(a, 85, once=True)
    assert once.sum() == a.sum() and once[:, :30].sum() == 0     # one copy, centred


@pytest.mark.parametrize("style", ["jacquard", "beads"])
@pytest.mark.parametrize("preset", list(cw.PRESETS))
def test_colourwork_presets_build_watertight(style, preset):
    b = build.make("cup", style, {"diameter": 70, "height": 50}, colours=C3, options={"chart_preset": preset})
    assert _wt(b)
    assert b.stats["swaps"] >= 1 or preset == "picture"


def test_colours_follow_the_chart_layer_by_layer():
    """A two-colour band alternates its colours every layer; a plain band costs nothing."""
    m, info = cw.build(SHAPES["cup"], SHAPES["cup"].resolve({"diameter": 60, "height": 40}), printer.nozzle(0.4),
                       chart=[{"plain": 0, "mm": 10}, {"motif": "checks", "colours": [0, 1], "gap": 0}, {"plain": 1, "mm": 10}])
    seq = info["slot_seq"]; lh = info["layer_h"]
    n_plain = int(round(10 / lh))
    fl = info["floor_layers"]
    assert set(seq[:fl + n_plain]) == {0}
    mid = seq[fl + n_plain: fl + n_plain + 10]                    # first chart row (10 layers): alternates,
    assert mid == [0, 1] * 5                                      # starting on the colour already loaded
    assert seq[fl + n_plain + 10] == seq[fl + n_plain + 9]        # next row carries on with it: no extra change
    txt = "".join(map(str, seq))                                  # then the plain band in colour 2 (the chart repeats)
    assert "1" * n_plain in txt                                  # (the last chart layer may run into it: no change)


def test_three_colour_band_cycles_three():
    _, info = cw.build(SHAPES["cup"], SHAPES["cup"].resolve({"diameter": 60, "height": 40}), printer.nozzle(0.4),
                       chart=[{"motif": "diamonds", "colours": [0, 1, 2], "gap": 0}])
    seq = info["slot_seq"][info["floor_layers"]:]
    assert set(seq) == {0, 1, 2}
    trip = [seq[i:i + 3] for i in range(len(seq) - 2)]
    assert any(len(set(t)) == 3 for t in trip)                    # accent rows cycle all three colours


def test_one_colour_rows_cost_no_changes_and_keep_the_ribs():
    nz = printer.nozzle(0.4); S = SHAPES["cup"]; v = S.resolve({"diameter": 60, "height": 40})
    m, info = cw.build(S, v, nz, chart=[{"art": ["XXXX", "X..X"], "colours": [0, 1], "gap": 3}])
    seq = info["slot_seq"][info["floor_layers"]:]
    runs = "".join(map(str, seq))
    assert "0" * 20 in runs                                      # the 3 ground rows: one colour, no alternation
    assert info["swaps"] < 0.75 * len(seq)


def test_band_two_halves_the_changes():
    kw = dict(colours=C3, options={"chart": [{"motif": "checks", "colours": [0, 1]}]})
    one = build.make("cup", "jacquard", {"diameter": 60, "height": 50}, **kw)
    two = build.make("cup", "jacquard", {"diameter": 60, "height": 50}, **{**kw, "options": {**kw["options"], "band": 2}})
    assert two.stats["swaps"] < 0.6 * one.stats["swaps"]


def test_picture_and_inline_art_bands():
    b = build.make("vase", "jacquard", {"diameter": 100, "height": 120}, colours=C3, options={"chart": [
        {"plain": 0, "mm": 8}, {"picture": "text", "text": "HI", "font": "impact", "fill": True, "colours": [0, 1]},
        {"art": ["..X..", ".XoX.", "XoooX"], "colours": [0, 1, 2]}]})
    assert _wt(b) and len(b.parts) == 3


def test_bulges_respect_the_overhang_law():
    """No layer steps out more than half a line past the layer below it (the halftone law)."""
    lh, lw = cw.RECIPE[0.4]
    m, info = cw.build(SHAPES["cup"], SHAPES["cup"].resolve({"diameter": 60, "height": 30}), printer.nozzle(0.4),
                       style="beads", chart=[{"motif": "seed", "colours": [0, 1], "gap": 0}])
    V = np.vstack([x.vertices for x in m.values()])
    r = np.hypot(V[:, 0], V[:, 1]); z = V[:, 2]
    R = 30.0
    assert r.max() <= R + 0.5 * lw + 1e-6


def test_rim_braid_adds_layers_in_one_colour():
    plain = build.make("cup", "beads", {"diameter": 70, "height": 40}, colours=C3, options={"chart_preset": "hearts"})
    braid = build.make("cup", "beads", {"diameter": 70, "height": 40}, colours=C3,
                       options={"chart_preset": "hearts", "rim": "braid", "rim_slot": 2})
    assert _wt(braid)
    top = max(m.bounds[1][2] for _, m, _, c in braid.parts if c == C3[2])
    assert abs(top - braid.stats["size"][2]) < 0.6


@pytest.mark.parametrize("rnd,shape_ok", [(100, True), (0, True)])
def test_lidded_box_roundness(rnd, shape_ok):
    b = build.make("box", "beads", {"width": 160, "depth": 90, "height": 40, "round": rnd}, colours=C3,
                   options={"chart_preset": "hearts"})
    assert _wt(b)
    V = np.vstack([m.vertices for _, m, _, _ in b.parts])
    corner = V[(V[:, 0] > 70) & (V[:, 1] > 35)]
    assert (len(corner) == 0) == (rnd == 100)                    # a stadium has no square-ish corner


def test_box_gets_a_labyrinth_lid_with_a_tube_knob():
    b = build.make("box", "beads", {"width": 150, "depth": 90, "height": 45}, colours=C3,
                   options={"chart_preset": "hearts", "lid": "slip", "lid_texture": "labyrinth", "lid_knob": "tube"})
    assert b.stats["lid"]["cap"] == "Labyrinth" and b.stats["lid"]["knob"] == "tube"
    assert all(m.is_watertight for _, m, _, _ in b.extras)
    assert len({c for _, _, _, c in b.extras}) >= 2


def test_labyrinth_rings_on_the_face_that_shows():
    nz = printer.nozzle(0.4); S = SHAPES["coaster"]; v = S.resolve({"width": 100, "height": 8, "dish": 0})
    for face, expect_low in (("top", False), ("bottom", True)):
        rods = lattice.weave(S.lattice(v, nz.rod_h), nz, "labyrinth", face=face)
        zs = [p[:, 2].mean() for p in rods.paths.get(2, [])]
        assert zs
        low = np.mean(zs) < 2 * nz.rod_h
        assert low == expect_low


def test_labyrinth_is_one_change_a_course():
    b = build.make("box", "labyrinth", {"width": 120, "depth": 80, "height": 14}, colours=C3)
    assert _wt(b) and b.stats["swaps"] <= 2 * b.stats["courses"]


def test_panel_factor_and_paneled_shapes():
    th = np.linspace(0, 2 * np.pi, 721)
    f = panel_factor(th, 8, 0)
    assert abs(f.max() - 1) < 1e-3 and abs(f.min() - np.cos(np.pi / 8)) < 1e-3
    assert (panel_factor(th, 0, 3) == 1).all()
    for shape, tex in (("gourd", "jacquard"), ("jar", "twill"), ("gourd", "domes")):
        b = build.make(shape, tex, {}, colours=C3)
        assert _wt(b), (shape, tex)
        V = np.vstack([m.vertices for _, m, _, _ in b.parts]); r = np.hypot(V[:, 0], V[:, 1])
        ang = np.arctan2(V[:, 1], V[:, 0])
        ridge = r[np.abs(((ang + np.pi / 8) % (np.pi / 4)) - np.pi / 8) < 0.02].max()
        flat = r[np.abs((ang % (np.pi / 4)) - np.pi / 8) < 0.02].max()   # mid-panel
        assert flat < ridge - 1.0, shape


def test_chart_plugin_loads_checks_and_builds(tmp_path, monkeypatch):
    monkeypatch.setattr(plugins, "DIR", tmp_path)
    p = plugins.new("chart", "folk bird")
    assert "folk_bird" in plugins.charts()
    r = plugins.check(p, tmp_path / "prev")
    item = r["items"][0]
    assert item["kind"] == "chart" and item["verdict"] == "ok"
    b = build.make("cup", "jacquard", {"diameter": 70, "height": 40}, colours=C3,
                   options={"chart": [{"chart": "folk_bird", "colours": [0, 1, 2]}]})
    assert _wt(b)


def test_catalogue_explains_colourwork_to_claude():
    from text2print import agent
    c = agent.catalogue()
    assert "art" in c["colourwork"]["band_kinds"] and "hearts" in c["colourwork"]["motifs"]
    assert "box" in c["shapes"] and "labyrinth" in c["textures"]
    assert "jacquard" in c["textures"]["jacquard"]["name"].lower() or c["textures"]["jacquard"]["family"] == "colourwork"


@pytest.mark.slicer
def test_real_slicer_counts_colourwork_changes(tmp_path):
    if not bambu.slicer_available():
        pytest.skip("Bambu Studio not installed")
    b = build.make("cup", "jacquard", {"diameter": 60, "height": 30}, colours=C3,
                   options={"chart": [{"plain": 0, "mm": 4}, {"motif": "diamonds", "colours": [0, 1, 2]}]})
    r = bambu.slice_project(b.write_3mf(tmp_path / "c.3mf"), tmp_path / "s")
    assert "error" not in r, r
    g = zipfile.ZipFile(tmp_path / "s" / "sliced.3mf").read("Metadata/plate_1.gcode").decode(errors="ignore")
    assert len(re.findall(r"^M620 S\dA", g, re.M)) == b.stats["swaps"]


@pytest.mark.slicer
def test_real_slicer_takes_the_labyrinth_lid_box(tmp_path):
    if not bambu.slicer_available():
        pytest.skip("Bambu Studio not installed")
    b = build.make("box", "beads", {"width": 120, "depth": 70, "height": 30}, colours=C3,
                   options={"chart_preset": "hearts", "rim": "braid", "lid": "slip", "lid_texture": "labyrinth",
                            "lid_knob": "tube", "lid_plate": "own"})
    proj = b.write_3mf(tmp_path / "b.3mf")
    r = bambu.slice_project(proj, tmp_path / "s")
    assert "error" not in r, r
    lid = tmp_path / "b-lid.3mf"
    if lid.exists():
        rl = bambu.slice_project(lid, tmp_path / "sl")
        assert "error" not in rl, rl
