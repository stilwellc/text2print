"""Oct 15 vision board: colourwork (jacquard / beads + charts), lidded boxes, labyrinth lids, tube knob, paneled
vessels, CHART plugins."""
import re
import zipfile

import numpy as np
import trimesh
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


def test_gift_box_lid_is_flush_and_slides_over_a_smooth_neck():
    """Oct 25: the flush gift-box lid. The base's weave stops at the seam, a smooth neck steps in by the lid wall + the
    fit, and the woven lid closes flush with the base — the closed box is one block with one seam."""
    b = build.make("box", "twill", dict(width=140, depth=90, height=60, round=0, wall=10, floor=2), 0.4,
                   ["#1C1C1E", "#E8E4DC"], dict(lid="gift", lid_fit="slip", lid_height=24), draft=True)
    L = b.stats["lid"]
    assert L["style"] == "gift" and L["neck"] == pytest.approx(3.75) and L["lid_wall"] == pytest.approx(6.0)
    base = np.vstack([m.vertices for n, m, _, _ in b.parts if n != "neck"])
    lid = np.vstack([m.vertices for _, m, _, _ in b.assembled])
    assert np.abs(lid[:, :2]).max(0) == pytest.approx(np.abs(base[:, :2]).max(0), abs=0.05)   # flush outside
    assert base[:, 2].max() == pytest.approx(lid[:, 2].min(), abs=0.01) == pytest.approx(L["seam"], abs=0.06)   # one seam
    neck = [m for n, m, _, _ in b.parts if n == "neck"][0]
    w = lid[(lid[:, 2] > L["seam"] + 2) & (lid[:, 2] < L["closed_h"] - 4)]
    inner_x = w[(np.abs(w[:, 1]) < 20) & (w[:, 0] > 0)][:, 0].min()
    assert inner_x - neck.bounds[1][0] == pytest.approx(0.25, abs=0.02)                       # the slip fit
    assert not any(n == "Knob" for n, _, _, _ in b.extras)


def test_gift_box_lid_needs_room_for_a_lid_wall_and_a_neck():
    b = build.make("box", "twill", dict(width=140, depth=90, height=60, round=0, wall=6, floor=2), 0.4,
                   ["#1C1C1E", "#E8E4DC"], dict(lid="gift"), draft=True)
    assert b.stats["lid"]["style"] == "slip" and any("gift-box lid needs a wall" in w for w in b.warnings)


def test_gift_box_lid_over_an_insert_has_no_neck_and_closes_flush():
    """Oct 25: a liner standing up out of the box is the neck. The base is woven to its rim, the lid's wall is sized to
    slide over the liner with the fit a side and still close flush; the lid's edge sits on the base's rim."""
    b = build.make("box", "twill", dict(width=140, depth=90, height=40, round=0, wall=6, floor=2), 0.4,
                   ["#1C1C1E", "#E8E4DC"], dict(lid="gift", lid_height=24, lid_over_w=127, lid_over_d=77), draft=True)
    L = b.stats["lid"]
    assert L["mode"] == "over insert" and not any(n == "neck" for n, _, _, _ in b.parts)
    assert L["lid_wall"] == pytest.approx(6.25) and L["clearance"] == pytest.approx(0.25)
    base = np.vstack([m.vertices for _, m, _, _ in b.parts]); lid = np.vstack([m.vertices for _, m, _, _ in b.assembled])
    assert np.abs(lid[:, :2]).max(0) == pytest.approx(np.abs(base[:, :2]).max(0), abs=0.05)
    assert lid[:, 2].min() == pytest.approx(base[:, 2].max(), abs=0.01)
    w = lid[(lid[:, 2] > L["seam"] + 2) & (lid[:, 2] < L["closed_h"] - 4)]
    assert 2 * w[(np.abs(w[:, 1]) < 20) & (w[:, 0] > 0)][:, 0].min() == pytest.approx(127.5, abs=0.05)


def test_a_gift_lid_that_cannot_be_built_falls_back_to_a_slip_lid_without_a_knob():
    b = build.make("box", "twill", dict(width=140, depth=90, height=60, round=0, wall=6, floor=2), 0.4,
                   ["#1C1C1E", "#E8E4DC"], dict(lid="gift"), draft=True)
    assert b.stats["lid"]["style"] == "slip" and b.stats["lid"]["knob"] == "none"


def test_ombre_ends_hold_the_first_and_last_colour():
    region = SHAPES["box"].lattice(SHAPES["box"].resolve(dict(width=120, depth=80, height=40, wall=6, floor=2)), 0.8)
    rods = lattice.weave(region, printer.nozzle(0.4), "twill", ombre=[0, 1], ombre_ends=4)
    for kind, g, sl in lattice._all(rods):
        c = lattice._course(rods, g[0][2])
        if c < 4:
            assert sl == 0
        elif c > region.n - 5:
            assert sl == 1


def test_floor_skin_gives_a_woven_box_a_solid_first_layer():
    """Oct 25: a woven box's bed face was 25 loose round rods (27 % of the footprint) and failed every first layer."""
    from shapely.geometry import Polygon
    b = build.make("box", "twill", dict(width=140, depth=90, height=40, round=0, wall=6, floor=2), 0.4,
                   ["#2B2B2B", "#F4F1E8"], dict(floor_skin=0.6), draft=True)
    m = trimesh.util.concatenate([m for _, m, _, _ in b.parts])
    s = m.section([0, 0, 1], [0, 0, 0.1])
    assert max(Polygon(e[:, :2]).buffer(0).area for e in s.discrete) > 0.97 * 140 * 90 * 0.98
    assert any(o.get("sparse_infill_density") == "100%" for _, _, o in b.ranges)


def test_3mf_beds_default_to_60c_on_the_textured_plate(tmp_path):
    import json, zipfile
    m = trimesh.creation.box([20, 20, 5]); m.apply_translation([0, 0, 2.5])
    f = tmp_path / "t.3mf"
    bambu.write_3mf(f, [{"name": "t", "position": (128, 128), "parts": [("t", m, 1)]}], colours=("#E8E4DC",))
    cfg = json.loads(zipfile.ZipFile(f).read("Metadata/project_settings.config"))
    assert cfg["curr_bed_type"] == "Textured PEI Plate"
    assert cfg["textured_plate_temp"] == ["60"] and cfg["textured_plate_temp_initial_layer"] == ["60"]


def test_twill_never_leaves_cross_rods_floating():
    """Oct 25: on a 6 mm wall the twill skip landed on the wall band's only lengthwise rod every 16 courses, and the
    next course's cross rods had nothing under them (440 floating islands on the watch-case base)."""
    from shapely.ops import unary_union
    b = build.make("box", "twill", dict(width=140, depth=92, height=30, round=0, wall=6, floor=2), 0.4,
                   ["#2B2B2B", "#F4F1E8"], dict(floor_skin=1.0), draft=True)
    zs = list(np.arange(0.1, 29.9, 0.2)); per = [m.section_multiplane([0, 0, 0], [0, 0, 1], zs) for _, m, _, _ in b.parts]
    layers = [unary_union([p.buffer(0) for k in range(len(per)) if per[k][i] is not None
                           for p in per[k][i].polygons_full if p.area > 0.02]) for i in range(len(zs))]
    for i in range(1, len(layers)):
        for p in getattr(layers[i], "geoms", [layers[i]]):
            if p.area > 0.05:
                assert p.intersection(layers[i - 1]).area > 0, f"floating island at z={zs[i]:.1f}"


def test_floor_inlay_border_and_word_sit_flush_in_the_first_layers():
    b = build.make("box", "twill", dict(width=140, depth=90, height=30, round=0, wall=6, floor=2), 0.4,
                   ["#2B2B2B", "#F4F1E8"], dict(floor_skin=1.0, floor_border=6, floor_text="cns"), draft=True)
    ink = [m for n, m, _, c in b.parts if n == "floor inlay"]
    assert ink and ink[0].bounds[0][2] == pytest.approx(0.0, abs=1e-6) and ink[0].bounds[1][2] <= 0.41
    assert [c for n, _, _, c in b.parts if n == "floor inlay"][0] == "#F4F1E8"
