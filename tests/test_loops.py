"""Loops on colour-knit: the named looks, their colour plans, and what the project must carry to print them."""
import json
import math
import zipfile

import numpy as np
import pytest

from text2print import build, colourwork, droop, loops, printer
from text2print.shapes import SHAPES

PEAR = dict(diameter=90, height=115, c0=70, c1=100, c2=90, c3=68, c4=44, neck=8, lip=1.5)
COLS = ["#151515", "#F4F2EC", "#C8102E"]


def make(look, **opts):
    return build.make("custom", "jacquard", PEAR, colours=COLS, options=dict(loops=look, band=2, stitch_size="fine", **opts), draft=True)


@pytest.mark.parametrize("look", list(loops.LOOKS))
def test_every_look_builds_watertight_parts_with_loops(look):
    b = make(look)
    assert b.stats["strands"] > 200 and all(m.is_watertight for _, m, _, _ in b.parts)
    assert b.preview is not None                                  # the hung-loop preview


@pytest.mark.parametrize("look", list(loops.LOOKS))
def test_loops_add_no_colour_changes(look):
    S = SHAPES["custom"]; v = S.resolve(PEAR); nz = printer.nozzle(0.4)
    opts = dict(band=2, stitch_size="fine")
    chart, _ = loops.resolve(look, opts, S, v, nz, 3)
    bare = build.make("custom", "jacquard", PEAR, colours=COLS, options=dict(opts, **({"chart": chart} if chart else {})), draft=True)
    assert make(look).stats["swaps"] == bare.stats["swaps"]


def test_a_loop_must_print_as_one_bead():
    o = make("tiers").overrides
    assert o["min_bead_width"] == "200%"                          # at the stock 85 % each loop splits into two thin lines
    assert set(o["enable_overhang_speed"]) == {"0"} and o["seam_position"] == "back"


def test_loops_in_one_layer_never_overlap():
    S = SHAPES["custom"]; v = S.resolve(PEAR); nz = printer.nozzle(0.4)
    _, spec = loops.resolve("tiers", {}, S, v, nz, 3)
    meshes, info = colourwork.build(S, v, nz, chart=[{"plain": 0, "mm": 200}], size="fine", draft=True, options={})
    prof = S.profile(v)[0]
    ev = droop.even_options(dict(spec, rows="even"))
    _, spots, _ = droop.colourwork_loops(prof, info["layer_h"], info["line_w"], ev, info, None, "layer")
    by_layer = {}
    for (th, w, _, z, _, _, line), _, _ in spots:
        by_layer.setdefault(int(z / info["layer_h"]), []).append((th, (w + line) / 2 / prof(z)))
    for row in by_layer.values():
        row.sort()
        for (a, ha), (b, hb) in zip(row, row[1:] + [(row[0][0] + 2 * math.pi, row[0][1])]):
            assert b - a >= ha + hb - 1e-6


def test_colour_plans_use_the_real_height_of_an_oversize_piece():
    """A piece past the picker's size limits (built raw) once had its chart laid out for the clamped height, so
    everything near the top landed 30 mm low."""
    big = dict(diameter=168, height=250, c0=72, c1=100, c2=90, c3=70, c4=46, neck=16, lip=3)
    b = build.make("custom", "jacquard", big, colours=COLS[:2], options=dict(loops="window", band=2, stitch_size="bold"), draft=True, _raw=True)
    top_white = max(float(m.bounds[1][2]) for _, m, _, c in b.parts if c == COLS[1])
    assert b.stats["size"][2] > 249 and top_white > 240          # the white line under the lip


def test_salt_keeps_most_rows_one_colour():
    S = SHAPES["custom"]; v = S.resolve(PEAR); nz = printer.nozzle(0.4)
    art = next(band["art"] for band in loops.salt_chart(S, v, nz, "fine", 2) if "art" in band)
    salted = sum("X" in row for row in art)
    assert 0.3 < salted / len(art) < 0.8 and sum(row.count("X") for row in art) / (len(art) * len(art[0])) < 0.3


def test_petal_loops_take_their_own_petals_colour():
    S = SHAPES["custom"]; v = S.resolve(PEAR); nz = printer.nozzle(0.4)
    chart, spec = loops.resolve("petals", {"band": 2, "stitch_size": "fine"}, S, v, nz, 2)
    meshes, info = colourwork.build(S, v, nz, chart=chart, size="fine", band=2, draft=True, options={})
    ev = droop.even_options(dict(spec, rows="even"))
    _, spots, _ = droop.colourwork_loops(S.profile(v)[0], info["layer_h"], info["line_w"], ev, info, None, "petal")
    wrong = 0
    for (th, _, _, z, _, _, _), slot, _ in spots:
        lid = droop.petal_field(th, z, ev["petal"], ev["petal_sag"], int(ev["petals"]))[1]
        wrong += int(droop.petal_slot(lid, ev["petal_share"], int(ev["petal_seed"]))) != slot
    assert wrong <= 0.03 * len(spots)                             # a loop moves a layer or two; near a hem that can cross


def test_petg_uses_bambus_preset_without_the_pla_droop_offset():
    f = make("shag", material="petg").per_filament
    assert set(f["filament_settings_id"]) == {"Generic PETG @BBL P2S"} and set(f["filament_type"]) == {"PETG"}
    assert set(f["nozzle_temperature"]) == {"255"} and set(f["fan_max_speed"]) == {"20"}


def test_base_inlay_takes_the_other_colour_and_primes_on_a_block(tmp_path):
    b = build.make("custom", "jacquard", PEAR, colours=COLS[:2],
                   options=dict(loops="window", band=2, stitch_size="fine", inlay_text="abc", tower="inlay"), draft=True)
    assert b.prime_block and not b.tower and len(set(b.prime_block["colours"])) == 2
    p = b.write_3mf(tmp_path / "piece.3mf")
    with zipfile.ZipFile(p) as z:
        settings = z.read("Metadata/model_settings.config").decode()
        cfg = json.loads(z.read("Metadata/project_settings.config"))
    assert settings.count("<object ") == 1 and "prime 1" in settings and "prime 2" in settings   # parts of ONE object
    assert cfg["enable_prime_tower"] == "0"


def test_custom_shape_neck_is_straight_and_the_lip_flares():
    prof, H, _ = SHAPES["custom"].profile(SHAPES["custom"].resolve(PEAR))
    assert H == 115 and abs(prof(H - 6) - prof(H - 4)) < 0.05 and prof(H) > prof(H - 4) + 1.0


def test_the_picker_offers_loops_filament_and_even_droop_rows():
    keys = lambda fam: {o[0] for o in build.OPTIONS[fam]}
    assert {"loops", "loop_colour", "loop_size", "material"} <= keys("colourwork")
    assert {"rows", "panels", "material"} <= keys("droop") and all("material" in keys(f) for f in build.OPTIONS)


# ── defects found in review (Nov 2026): each of these crashed or wrote the wrong settings ──
C4 = ["#8B3A2F", "#EDE3D1", "#C58A3F", "#2E4E7E"]


def _cfg(b, path):
    with zipfile.ZipFile(b.write_3mf(path)) as z:
        return json.loads(z.read("Metadata/project_settings.config")), z.read("3D/3dmodel.model").decode()


def test_a_lid_in_its_own_colour_writes_with_petg_and_with_loops(tmp_path):
    b = build.make("cup", "zigzag", {"diameter": 60, "height": 40}, colours=C4, draft=True,
                   options={"material": "petg", "lid": "slip", "lid_texture": "plain", "lid_colours": ["#2E4E7E"], "lid_plate": "same"})
    cfg, _ = _cfg(b, tmp_path / "a.3mf")
    assert set(cfg["filament_type"]) == {"PETG"} and len(cfg["filament_type"]) == len(cfg["filament_colour"])
    b = build.make("vase", "jacquard", {}, colours=C4, draft=True,
                   options={"loops": "tiers", "lid": "slip", "lid_texture": "plain", "lid_colours": ["#2E4E7E"], "lid_plate": "same"})
    cfg, _ = _cfg(b, tmp_path / "b.3mf")
    assert len(cfg["slow_down_layer_time"]) == len(cfg["filament_colour"])


def test_material_accepts_a_mixed_list_any_case_and_families_with_their_own_colours(tmp_path):
    cfg, _ = _cfg(build.make("cup", "zigzag", {}, colours=C4, options={"zones": 2, "material": ["pla", "petg"]}, draft=True), tmp_path / "a.3mf")
    assert cfg["filament_type"] == ["PLA", "PETG"]
    assert build.make("cup", "zigzag", {}, options={"material": "PLA"}, draft=True).per_filament is None
    cfg, _ = _cfg(build.make("tile", "flatlitho", {}, options={"material": "petg"}, draft=True), tmp_path / "b.3mf")
    assert set(cfg["filament_type"]) == {"PETG"}
    with pytest.raises(ValueError, match="Materials: pla"):
        build.make("cup", "zigzag", {}, options={"material": "nylon"}, draft=True)


def test_petg_keeps_a_familys_own_cooling_but_not_pla_stock_values():
    mix = build.make("cup", "mix", {}, colours=C4, options={"material": "petg"}, draft=True).per_filament
    assert set(mix["fan_max_speed"]) == {"90"}                   # the PETG preset's, not PLA Matte's 100
    fur = build.make("cup", "fur", {"diameter": 60, "height": 60}, colours=C4, options={"zones": 2}, draft=True).per_filament
    assert set(fur["fan_max_speed"]) == {"100"}                  # fur needs full fan; zones once gave it the droop fan


def test_inlay_priming_stays_on_the_tower_when_a_lid_shares_the_job():
    b = build.make("vase", "jacquard", {}, colours=C4[:2], options={"inlay_text": "CS", "tower": "inlay", "lid": "slip"}, draft=True)
    assert b.tower and not b.prime_block and any("tower=inlay" in w for w in b.warnings)


def test_a_wide_piece_is_written_on_the_bed(tmp_path):
    import re
    b = build.make("box", "twill", {"width": 250, "depth": 200}, colours=C4[:2], draft=True)
    _, model = _cfg(b, tmp_path / "a.3mf")
    t = re.search(r'<item[^>]*transform="([^"]+)"', model).group(1).split(); px, py = float(t[9]), float(t[10])
    v = np.vstack([m.vertices[:, :2] for _, m, _, _ in b.parts])
    assert v[:, 0].min() + px >= 0 and v[:, 0].max() + px <= printer.BED and v[:, 1].min() + py >= 0 and v[:, 1].max() + py <= printer.BED


def test_even_rows_alone_switch_the_rows_on():
    loose = build.make("cup", "fringe", {"diameter": 60, "height": 70}, draft=True).stats
    even = build.make("cup", "fringe", {"diameter": 60, "height": 70}, options={"rows": "even"}, draft=True).stats
    assert even["strands"] != loose["strands"] and even["reach"] < loose["reach"]


def test_course_boundaries_never_fall_inside_a_strand():
    nz = printer.nozzle(0.4); S = SHAPES["cup"]; v = S.defaults(); prof = S.profile(v)[0]; lh = nz.layer_h
    spots = droop._rows("fringe", prof, v["height"], nz, 1.0, 1.0, aligned=True)
    layers = [(math.floor(z / lh), math.floor(z / lh) + round(hh / lh)) for _, _, _, z, hh, _, _ in spots]
    for edge in droop.courses(spots, lh):
        k = round(edge / lh)
        assert not any(a < k < b for a, b in layers)


def test_short_loops_do_not_fold_back_through_the_wall():
    from shapely.geometry import Polygon
    for L in (2.2, 3.0, 4.0, 9.0):
        u, s_ = droop._teardrop(L, 4.0, 0.7)
        assert u.min() >= -1e-9 and Polygon(np.column_stack([u, s_])).is_valid


def test_petals_on_bead_knit_keep_their_collar_and_colours():
    S = SHAPES["cup"]; v = S.defaults(); nz = printer.nozzle(0.4)
    chart, spec = loops.resolve("petals", {"band": 2}, S, v, nz, 2, style="beads")
    meshes, info = colourwork.build(S, v, nz, style="beads", chart=chart, band=2, draft=True, options={})
    knit_top = max(i for i, s_ in enumerate(info["seq"]) if s_[0] == "cw") * info["layer_h"]
    assert knit_top < v["height"] - spec["collar"] + 3.0          # the bare collar is still there


# ── the open items from the review, closed ──
def test_a_piece_that_nearly_fills_the_bed_goes_in_the_corner_clear_of_the_tower(tmp_path):
    import re
    b = build.make("tray", "zigzag", {"width": 200, "height": 12}, colours=C4, options={"zones": 3}, draft=True)
    cfg, model = _cfg(b, tmp_path / "a.3mf")
    t = re.search(r'<item[^>]*transform="([^"]+)"', model).group(1).split(); px, py = float(t[9]), float(t[10])
    v = np.vstack([m.vertices[:, :2] for _, m, _, _ in b.parts]) + [px, py]
    tx, ty = float(cfg["wipe_tower_x"][0]), float(cfg["wipe_tower_y"][0])
    near = v[(v[:, 0] > tx - 5) & (v[:, 1] < ty + 60)]
    assert not len(near) and v.min() >= 0 and v.max() <= printer.BED          # once the tower sat inside the piece


def test_the_purge_coaster_prints_on_the_pieces_plate(tmp_path):
    b = build.make("cup", "halftone", {"diameter": 60, "height": 40}, colours=C4[:2], options={"lid": "slip", "purge_piece": "coaster"}, draft=True)
    with zipfile.ZipFile(b.write_3mf(tmp_path / "a.3mf")) as z:
        s = z.read("Metadata/model_settings.config").decode()
    assert 'value="Purge coaster"' in s and "flush_into_objects" in s
    big = build.make("cup", "halftone", {"diameter": 160, "height": 40}, colours=C4[:2], options={"purge_piece": "coaster"}, draft=True)
    big.write_3mf(tmp_path / "b.3mf")
    assert not (tmp_path / "b-lid.3mf").exists() and any("coaster" in w and "left out" in w for w in big.warnings)


def test_ams_trays_follow_the_colours_as_chosen():
    b = build.make("cup", "mix", {}, colours=C4, draft=True,
                   options={"bands": [{"texture": "plain", "share": 1, "slot": 0}, {"texture": "zigzag", "share": 1, "slot": 2}]})
    assert b.project_colours() == [C4[0], C4[2]] and b.ams_mapping() == [0, 2]      # trays 1 and 3, not 1 and 2


@pytest.mark.parametrize("shape, texture", [("lantern", "zigzag"), ("puck", "fringe"), ("cachepot", "zigzag"), ("pendant", "zigzag")])
def test_sketch_builds_of_fitted_shapes_take_colour_zones(shape, texture):
    assert build.make(shape, texture, {}, colours=C4, options={"zones": 2}, draft=True).parts


def test_fill_bands_reach_the_rim_and_three_tone_pictures_keep_their_height():
    S = SHAPES["cup"]; v = S.defaults(); nz = printer.nozzle(0.4)
    top = lambda chart: colourwork.build(S, v, nz, chart=chart, draft=True, options={})[1]
    assert top([{"motif": "hearts", "fill": True, "colours": [0, 1]}])["wall_top"] > v["height"] - 0.5
    assert top([{"picture": "fade", "fill": True, "tones": 3, "colours": [0, 1, 2]}])["wall_top"] > v["height"] - 0.5
    info = top([{"picture": "fade", "mm": 40, "tones": 3, "colours": [0, 1, 2]}, {"plain": 0, "mm": 200}])
    assert abs(sum(1 for q in info["seq"] if q[0] == "cw") * info["layer_h"] - 40) < 2.5


def test_front_is_one_angle_for_motifs_pictures_and_loop_windows():
    from text2print import pictures
    t = colourwork.tile(colourwork.art_grid(["XXX"]), 120, once=True)
    assert abs((np.where(t[0] == 1)[0].mean() + 0.5) / 120 - pictures.FRONT_U) < 0.02
    S = SHAPES["cup"]; v = S.defaults(); nz = printer.nozzle(0.4); front = 2 * math.pi * pictures.FRONT_U
    for look in ("window", "fringe"):
        _, spec = loops.resolve(look, {}, S, v, nz, 2)
        assert not droop.in_panels(front, droop.panel_windows(spec["panels"], spec["panel_width"], spec["panel_offset"]))


def test_mason_jar_lid_has_one_right_hand_thread_inside_a_clear_bore():
    from text2print.fittings import MASON
    b = build.make("jarlid", "domes", {"inside": 86, "skirt": 19})
    fit = next(m for n, m, _, _ in b.parts if n == "fitting")
    assert all(m.is_watertight for _, m, _, _ in b.parts)
    def bore(z):
        pts = np.vstack(list(fit.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1]).discrete))
        return 2 * np.hypot(pts[:, 0], pts[:, 1]).min()
    assert abs(bore(MASON["top"] + 1.0) - (86 + 2 * MASON["clear"])) < 0.1           # clear of the glass threads
    assert abs(bore(MASON["top"] + 9.0) - (86 + 2 * MASON["clear"] - 2 * MASON["depth"])) < 0.3     # the ridge
    # right-hand: the ridge climbs as the angle increases
    v = fit.vertices; r = np.hypot(v[:, 0], v[:, 1]); crest = v[r < 43 + MASON["clear"] - 0.8 * MASON["depth"]]
    ang = np.unwrap(np.arctan2(crest[:, 1], crest[:, 0])[np.argsort(crest[:, 2])])
    assert ang[-1] - ang[0] > np.pi and abs((crest[:, 2].max() - crest[:, 2].min()) / ((ang[-1] - ang[0]) / (2 * np.pi)) - MASON["pitch"]) < 0.8


@pytest.mark.parametrize("nozzle", [0.4, 0.8])
def test_pour_cap_screws_into_an_open_hole_without_clashing(nozzle):
    import manifold3d as m3d
    import trimesh
    from text2print.fittings import POUR, _m, _pour
    b = build.make("jarlid", "domes", {"inside": 86, "skirt": 19, "pour": 30}, nozzle=nozzle)
    r, cx, _ = _pour(b.params)
    assert [n for n, *_ in b.extras] == ["Pour cap"] and all(m.is_watertight for _, m, _, _ in b.parts + b.extras)
    whole = trimesh.util.concatenate([p[1] for p in b.parts])
    assert not len(whole.ray.intersects_location([[cx, 0.3, -50.0]], [[0, 0, 1.0]])[0])            # open right through
    lid = m3d.Manifold.batch_boolean([_m(m) for _, m, _, _ in b.parts], m3d.OpType.Add); cap = _m(b.extras[0][1])
    seat = min(((lid ^ cap.rotate([0, 0, d]).translate([cx, 0, -POUR["cap_t"]])).volume(), d) for d in range(0, 180, 3))
    assert seat[0] < 0.5                                                                           # seated flush
    assert (lid ^ cap.rotate([0, 0, seat[1] - 90]).translate([cx, 0, -POUR["cap_t"] - 1.5])).volume() < 0.5   # and on the way out
    assert not build.make("jarlid", "domes", {"inside": 86, "skirt": 19}).extras                  # no opening: no cap


def test_jar_lid_fluted_grip_is_one_clean_solid():
    """grip=1: the lid is one solid with finger flutes that stop under a plain band, at the asked wall; the second
    colour is a line and a dot in the first five layers only; the pour boss stays clear of the jar's glass rim."""
    import numpy as np
    from text2print.fittings import GRIP, MASON, POUR, _pour
    b = build.make("jarlid", "domes", {"inside": 86, "skirt": 19, "wall": 6.35, "pour": 30, "grip": 1}, colours=["#F4F1E8", "#151515"])
    assert [n for n, *_ in b.parts] == ["fitting", "mark"] and [n for n, *_ in b.extras] == ["Pour cap", "Pour cap dot"]
    lid = b.parts[0][1]
    assert all(m.is_watertight and len(m.split(only_watertight=False)) == 1 for _, m, _, _ in b.parts + b.extras)
    assert all(m.bounds[1][2] <= 1.0 + 1e-6 and c == "#151515" for n, m, _, c in b.parts + b.extras if n in ("mark", "Pour cap dot"))
    R = 86 / 2 + MASON["clear"] + 6.35

    def r_at(z, deg):
        pts = np.vstack(list(lid.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1]).discrete))
        a = np.degrees(np.arctan2(pts[:, 1], pts[:, 0])); r = np.hypot(pts[:, 0], pts[:, 1])
        return r[np.abs(a - deg) < 1].max()
    n = max(8, int(round(2 * np.pi * R / GRIP["pitch"]))); flute = 180.0 / n; land = 360.0 / n
    assert abs(r_at(12, land) - R) < 0.05                                   # the lands keep the full wall
    assert abs(r_at(12, flute) - (R - GRIP["depth"])) < 0.1                 # the flutes are cut to depth
    assert abs(r_at(GRIP["band"] - 0.5, flute) - R) < 0.05                  # and stop under the plain band
    r, cx, _ = _pour(b.params)
    assert abs(2 * r - 30) < 1e-6 and 86 / 2 + MASON["clear"] - (cx + r + POUR["boss"]) >= POUR["jar"] - 1e-6
