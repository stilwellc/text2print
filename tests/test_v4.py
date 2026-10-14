"""Research top-12 features: fittings, halftone economy, vase mode, shell textures, fur, lid styles, footprints, flat."""
import json
import math
import pathlib
import zipfile

import numpy as np
import pytest

from text2print import bambu, build, extras, fittings, flat, printer, sampler
from text2print.shapes import SHAPES


def _solid_at(b, pt):
    return any(m.contains([pt])[0] for _, m, _, _ in b.parts)


def _ok(b):
    assert b.parts and all(m.is_watertight and m.volume > 0 for _, m, _, _ in b.parts)


# ── fittings ──────────────────────────────────────────────────────────────────────────────────────────────
def test_puck_lamp_has_a_pocket_and_a_cable_notch():
    b = build.make("puck", "zigzag", draft=True)
    _ok(b)
    r = fittings.PUCK[0] / 2
    for pt in ([0, 0, 9], [r - 0.2, 0, 9], [0, -(r + 1.0), 4]):           # pocket centre, pocket edge, notch
        assert not _solid_at(b, pt), pt
    assert any(fittings.NOTES["puck"][:20] in w for w in b.warnings)


def test_pendant_has_the_e27_hole():
    b = build.make("pendant", "zigzag", draft=True)
    _ok(b)
    for x in (0.0, fittings.E27_HOLE / 2 - 0.3):
        assert not _solid_at(b, [x, 0, 3.0])


def test_lantern_plinth_holds_a_tealight():
    b = build.make("lantern", "voronoi", draft=True)
    _ok(b)
    assert _solid_at(b, [0, 0, 1.5])                                       # plinth under the pocket
    assert not _solid_at(b, [0, 0, 20.0 - fittings.TEALIGHT_POCKET[1] / 2])  # the pocket itself
    assert any("flame" in w.lower() or "candle" in w.lower() or "tealight" in w.lower() for w in b.warnings)


def test_taper_candle_socket_has_crush_ribs():
    b = build.make("candle", "curls", draft=True)
    _ok(b)
    top = b.params["height"]; sock = fittings.TAPER_BORE / 2
    assert _solid_at(b, [0, sock - 0.2, top - 6])                          # rib face
    assert not _solid_at(b, [0, 0, top - 6])                               # the bore


def test_cachepot_sizes_to_the_nursery_pot():
    a = build.make("cachepot", "pleats", {"pot": 4}, draft=True)
    c = build.make("cachepot", "pleats", {"pot": 6}, draft=True)
    _ok(a); _ok(c)
    assert c.stats["size"][0] - a.stats["size"][0] >= 2 * 25.4 - 1


# ── halftone economy ─────────────────────────────────────────────────────────────────────────────────────
def test_halftone_levers_cut_colour_changes():
    dims = {"diameter": 60, "height": 50}
    base = build.make("cup", "halftone", dims, draft=True).stats["swaps"]
    band3 = build.make("cup", "halftone", dims, options={"band": "3"}, draft=True).stats["swaps"]
    third = build.make("cup", "halftone", dims, options={"area": "third"}, draft=True).stats["swaps"]
    silk = build.make("cup", "halftone", dims, options={"silk": "silk"}, draft=True)
    assert band3 < base / 2 and third < base / 2
    assert silk.stats["swaps"] == 0 and len(silk.parts) == 1


# ── vase mode ────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("texture", ["pleats", "flutes", "twist", "lowpoly", "pinch"])
def test_vase_mode_is_one_wall_in_spiral_mode(texture):
    b = build.make("vase", texture, {"diameter": 70, "height": 90}, draft=True)
    _ok(b)
    assert len(b.parts) == 1 and b.overrides.get("spiral_mode") == "1"
    assert len(b.parts[0][1].split(only_watertight=False)) == 1


def test_slit_ribs_cut_the_solid_body_without_spiral_mode():
    b = build.make("vase", "ribs", {"diameter": 70, "height": 90}, draft=True)
    _ok(b)
    assert b.stats.get("sections", 0) > 0


def test_amphora_keeps_the_overhang_law():
    S = SHAPES["amphora"]; v = S.resolve({})
    prof, h = S.profile(v)[:2]
    z = np.linspace(0, h, 400); r = np.array([prof(zz) for zz in z])
    assert (np.diff(r) / np.diff(z)).max() <= 1.0 + 1e-6                  # never wider than 45 deg per mm


# ── shell textures ───────────────────────────────────────────────────────────────────────────────────────
def test_voronoi_is_one_body_with_holes():
    b = build.make("cup", "voronoi", {"diameter": 70, "height": 80}, draft=True)
    _ok(b)
    m = b.parts[0][1]
    assert len(m.split(only_watertight=False)) == 1 and b.stats["cells"] > 5
    plain = build.make("cup", "litho", {"diameter": 70, "height": 80}, draft=True).parts[0][1]
    assert m.volume < plain.volume


def test_fuzzy_bands_are_layer_ranges():
    b = build.make("cup", "fuzzy", {"diameter": 70, "height": 80}, options={"fuzzy_bands": "2"}, draft=True)
    _ok(b)
    fz = [r for r in b.ranges if r[2].get("fuzzy_skin", "none") != "none"]
    assert fz and all("layer_height" in r[2] for r in b.ranges)


def test_litho_wall_is_thick_enough_to_light():
    b = build.make("cup", "litho", {"diameter": 70, "height": 80}, draft=True)
    _ok(b)
    assert int(b.overrides["wall_loops"]) * printer.nozzle(0.4).line_w >= 3.0


# ── fur ──────────────────────────────────────────────────────────────────────────────────────────────────
def test_fur_hairs_are_bridges_on_their_own_cooling():
    b = build.make("cup", "fur", {"diameter": 60, "height": 50}, draft=True)
    _ok(b)
    assert b.stats["strands"] > 50
    assert b.per_filament and b.per_filament.get("fan_max_speed") == ["100"]


# ── lids ─────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("style", ["slip", "thread", "magnets"])
def test_lid_styles(style):
    b = build.make("cup", "zigzag", {"diameter": 80, "height": 60}, options={"lid": style}, draft=True)
    assert b.stats["lid"]["style"] == style
    assert all(m.is_watertight for _, m, _, _ in b.extras)
    rims = [m for n, m, _, _ in b.parts if n == "rim"]
    assert bool(rims) == (style != "slip") and all(m.is_watertight for m in rims)


@pytest.mark.parametrize("fit,clear", list(extras.FITS.items()))
def test_lid_fit_sets_the_clearance(fit, clear):
    b = build.make("cup", "zigzag", {"diameter": 80, "height": 60}, options={"lid": "slip", "lid_fit": fit}, draft=True)
    assert b.stats["lid"]["clearance"] == clear


def test_fit_plate_builds():
    p = sampler.plate("fit")
    assert len(p["objects"]) >= 2
    assert all(m.is_watertight for ob in p["objects"] for _, m, _ in ob["parts"])


# ── footprints ───────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("shape,texture", [("basket", "twill"), ("catchall", "grid"), ("hextile", "kagome"),
                                           ("tile", "flatlitho"), ("hextile", "cmyk")])
def test_non_round_footprints(shape, texture):
    b = build.make(shape, texture, draft=True)
    _ok(b)
    x, y, _ = b.stats["size"]
    assert x < printer.BED and y < printer.BED


def test_basket_has_handle_holes():
    b = build.make("basket", "twill", draft=True)
    v = b.params; top = b.stats["size"][2]
    x = b.stats["size"][0] / 2 - 1.0
    assert not _solid_at(b, [x, 0, top - 12]) or not _solid_at(b, [-x, 0, top - 12])


# ── flat pictures ────────────────────────────────────────────────────────────────────────────────────────
def test_cmyk_tile_is_four_clean_parts_with_counted_changes():
    b = build.make("tile", "cmyk", {"width": 70, "depth": 60}, draft=True)
    _ok(b)
    assert [c for *_, c in b.parts] == list(flat.CMYK)[:len(b.parts)] and len(b.parts) == 4
    assert 0 < b.stats["swaps"] < 40


def test_flat_backlit_preview_matches_the_footprint():
    S = SHAPES["hextile"]; v = S.resolve({})
    _, info = flat.build(S, v, printer.nozzle(0.4), "cmyk", draft=True)
    im = info["backlit"]
    assert im.ndim == 3 and im.shape[2] == 4 and 0 < (im[..., 3] > 0).mean() < 1


# ── plate layout ─────────────────────────────────────────────────────────────────────────────────────────
def test_three_colours_park_the_tower_front_right_and_the_piece_clear(tmp_path):
    b = build.make("cup", "zigzag", {"diameter": 80, "height": 40}, colours=["#8B3A2F", "#EDE3D1", "#2E4E7E"],
                   options={"zones": "3"}, draft=True)
    p = b.write_3mf(tmp_path / "c.3mf")
    tx = float(b.overrides["wipe_tower_x"][0]); ty = float(b.overrides["wipe_tower_y"][0])
    assert tx + printer.TOWER[2] + 20 <= printer.BED + 1e-6 and ty == 20
    with zipfile.ZipFile(p) as z:
        assert "plate_1" in " ".join(z.namelist()) or z.read("3D/3dmodel.model")


# ── real slicer ──────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.slicer
@pytest.mark.parametrize("shape,texture,dims,opts", [
    ("vase", "pleats", {"diameter": 60, "height": 60}, {}),
    ("cup", "voronoi", {"diameter": 60, "height": 50}, {}),
    ("tile", "cmyk", {"width": 60, "depth": 50}, {}),
    ("puck", "zigzag", {}, {}),
    ("cup", "zigzag", {"diameter": 70, "height": 40}, {"lid": "thread"}),
])
def test_real_slicer_accepts_the_new_families(tmp_path, shape, texture, dims, opts):
    if not bambu.slicer_available():
        pytest.skip("Bambu Studio not installed")
    b = build.make(shape, texture, dims, options=opts, draft=False)
    r = bambu.slice_project(b.write_3mf(tmp_path / "m.3mf"), tmp_path / "s")
    assert "error" not in r, r


def test_vase_mode_estimate_counts_one_wall_not_the_solid_body():
    b = build.make("vase", "pleats", draft=True)
    assert 15 < b.stats["grams_est"] < 150


# ── multi-colour droop: woven-style courses ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize("style", ["fringe", "swag", "curls", "unraveled"])
def test_droop_courses_never_cut_a_strand(style):
    import math
    from text2print import droop
    nz = printer.nozzle(0.4); S = SHAPES["cup"]; v = S.resolve({"diameter": 70, "height": 80})
    _, info = droop.build(S, v, nz, style, preview=False, draft=True, aligned=True)
    edges, zone_of = build._course_edges(info["courses"], info["course_gap"], 80.0, 2)
    assert len(edges) > 8 and set(zone_of) == {0, 1}
    lh = nz.layer_h
    spots = droop._rows(style, S.profile(v)[0], 80.0, nz, 1.0, 1.0, aligned=True)
    for e in edges[1:-1]:
        k = round(e / lh)
        for *_, z, hh, _, _ in spots:
            a = math.floor(z / lh + 1e-9)
            assert not (a < k <= a + round(hh / lh)), (style, e, z)


def test_droop_courses_change_once_per_course_and_rows_cut_it():
    one = build.make("cup", "fringe", {"diameter": 70, "height": 80}, colours=["#2E4E7E", "#EDE3D1"],
                     options={"zones": "2"}, draft=True)
    three = build.make("cup", "fringe", {"diameter": 70, "height": 80}, colours=["#2E4E7E", "#EDE3D1"],
                       options={"zones": "2", "course_rows": "3"}, draft=True)
    assert len(one.parts) == 2 and one.stats["swaps"] > 20
    assert three.stats["swaps"] <= one.stats["swaps"] / 2.5
    assert len(one.preview) == 2                                  # hung strands keep their course colour


@pytest.mark.slicer
def test_real_slicer_counts_droop_course_changes(tmp_path):
    if not bambu.slicer_available():
        pytest.skip("Bambu Studio not installed")
    import re
    b = build.make("cup", "swag", {"diameter": 60, "height": 60}, colours=["#2E4E7E", "#EDE3D1", "#C3302C"],
                   options={"zones": "3"})
    r = bambu.slice_project(b.write_3mf(tmp_path / "d.3mf"), tmp_path / "s")
    assert "error" not in r, r
    g = zipfile.ZipFile(tmp_path / "s" / "sliced.3mf").read("Metadata/plate_1.gcode").decode(errors="ignore")
    assert len(re.findall(r"^M620 S\dA", g, re.M)) == b.stats["swaps"]


# ── woven on profiled vessels ────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("shape", ["vase", "bowl", "goblet", "custom", "cachepot", "sleeve", "amphora"])
def test_woven_follows_the_silhouette_and_every_course_rests_on_the_last(shape):
    S = SHAPES[shape]; v = S.resolve({}); nz = printer.nozzle(0.4)
    reg = S.lattice(v, nz.rod_h)
    xs = np.linspace(-reg.extent - 2, reg.extent + 2, 801)
    def radii(i):                                     # outer and inner edge along +x at course i
        inside = xs[(reg.sdf(reg.z(i))(xs, np.zeros_like(xs)) <= 0) & (xs >= 0)]
        return inside.max(), inside.min()
    tol = S.LEAN * nz.rod_h + 2 * (xs[1] - xs[0])      # sampling grid
    prev = radii(0)
    for i in range(1, reg.n):
        cur = radii(i)
        assert abs(cur[0] - prev[0]) <= tol
        if i > reg.floor_courses and prev[1] > 1.0 and cur[1] > 1.0:   # both hollow: the inner face steps gently too
            assert abs(cur[1] - prev[1]) <= tol
        prev = cur
    b = build.make(shape, "twill", draft=True)
    _ok(b)


def test_woven_sleeve_still_fits_its_glass():
    S = SHAPES["sleeve"]; v = S.resolve({"liner": 70}); reg = S.lattice(v, printer.nozzle(0.4).rod_h)
    xs = np.linspace(0, 60, 1201)
    inside = xs[reg.sdf(reg.z(reg.n // 2))(xs, np.zeros_like(xs)) <= 0]
    assert inside.min() >= 35.0                       # the glass (70 mm) slides in


# ── woven bands in a mix ─────────────────────────────────────────────────────────────────────────────────
from text2print import compose as _compose


@pytest.mark.parametrize("bands", [
    _compose.PRESETS["basket"]["bands"],
    [dict(texture="grid", share=50, slot=0, slot2=1), dict(texture="fringe", share=50, slot=1)],     # woven at the bottom
    [dict(texture="zigzag", share=50, slot=0), dict(texture="polar", share=50, slot=1, slot2=0)],   # woven on top
    [dict(texture="plain", share=30, slot=0), dict(texture="ripple", share=40, slot=0, slot2=1),
     dict(texture="beat", share=30, slot=1, slot2=0)],                                             # woven on woven
])
def test_woven_bands_mix(bands):
    b = build.make("cup", "mix", {"diameter": 70, "height": 70}, options={"bands": bands},
                   colours=["#8B3A2F", "#EDE3D1"], draft=True)
    _ok(b)
    assert any(r[2].get("wall_loops") == str(printer.nozzle(0.4).rod_lines) for r in b.ranges)
    assert b.overrides["overhang_totally_speed"][0] == "50"


def test_woven_band_changes_colour_once_per_course_and_starts_on_a_45_degree_collar():
    nz = printer.nozzle(0.4); S = SHAPES["cup"]; v = S.resolve({"diameter": 70, "height": 70})
    bands = _compose.PRESETS["basket"]["bands"]
    parts, _, info = _compose.build(S, v, nz, bands, draft=True)
    z0, z1 = info["bands"][0][1], info["bands"][0][1] + info["bands"][1][1]
    woven = [s_ for a, b_, s_ in info["layer_slots"] if z0 - 1e-6 <= a and b_ <= z1 + 1e-6]
    changes = sum(1 for x, y in zip(woven, woven[1:]) if x != y)
    courses = round((z1 - z0) / nz.rod_h)
    assert courses / 2 < changes < courses                     # rod courses alternate; collar and cap don't
    # collar: wall below -> ring, never wider than 45 deg
    shell = _compose.fabric_preset(0.4, diameter=70, stitch="zigzag")["fabric"]["shell_t"]
    ramp = int(math.ceil(((6.0 - shell) / 2 + 0.5) / nz.rod_h))
    assert ramp * nz.rod_h >= (6.0 - shell) / 2               # rise >= run on each face


@pytest.mark.slicer
def test_real_slicer_counts_woven_mix_changes(tmp_path):
    if not bambu.slicer_available():
        pytest.skip("Bambu Studio not installed")
    import re
    b = build.make("cup", "mix", {"diameter": 60, "height": 50}, options={"bands": _compose.PRESETS["basket"]["bands"]},
                   colours=["#8B3A2F", "#EDE3D1"])
    r = bambu.slice_project(b.write_3mf(tmp_path / "w.3mf"), tmp_path / "s")
    assert "error" not in r, r
    g = zipfile.ZipFile(tmp_path / "s" / "sliced.3mf").read("Metadata/plate_1.gcode").decode(errors="ignore")
    assert len(re.findall(r"^M620 S\dA", g, re.M)) == b.stats["swaps"]


@pytest.mark.parametrize("style", ["fringe", "swag", "curls", "unraveled"])
def test_droop_plain_bands_are_minimal(style):
    from text2print import droop
    nz = printer.nozzle(0.4); S = SHAPES["cup"]; v = S.resolve({"diameter": 70, "height": 80})
    spots = droop._rows(style, S.profile(v)[0], 80.0, nz, 1.0, 1.0)
    zs = [z for *_, z, _, _, _ in [s[:4] + (0, 0, 0) for s in spots]]
    gap = max(droop._SPEC[style]["row"], droop._SPEC[style]["tall"] + 1) * nz.layer_h
    assert min(zs) < 12.0                                         # strands start near the foot (short loops there)
    assert max(zs) > 80.0 - 1.0 - 4 * nz.layer_h - 2 * gap - 1.0  # ...and run to just under the rim
    assert all(z - bu >= droop.CLEAR - 1e-6 for _, _, bu, z, *_ in spots)


# ── wall textures on non-round plans ─────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("shape,texture", [("tray", "zigzag"), ("platter", "halftone"), ("dish", "domes"), ("coaster", "wave"),
                                           ("basket", "fringe"), ("catchall", "mix"), ("hextile", "voronoi"), ("tray", "pleats")])
def test_wall_textures_follow_the_outline(shape, texture):
    b = build.make(shape, texture, draft=True)
    _ok(b)
    v = b.params; W = v.get("width", v.get("diameter")); D = v.get("depth", W if shape != "hextile" else W * 1.1547)
    x, y, _ = b.stats["size"]
    reach = 2 * (b.stats.get("reach") or 0) + 10
    assert W - 2 <= x <= W + reach and D - 6 <= y <= D + reach


def test_outline_keeps_the_circumference_and_wall_thickness():
    o = SHAPES["basket"].outline(SHAPES["basket"].resolve({}))
    assert abs(2 * math.pi * o.R - o.L) < 1e-6
    import trimesh
    ring = trimesh.creation.annulus(o.R - 1.0, o.R, height=5.0, sections=2048)
    o.warp(ring)
    # a 1 mm round wall stays ~1 mm thick on every side of the rectangle
    for x in (0.0, 30.0):
        ys = ring.vertices[np.abs(ring.vertices[:, 0] - x) < 0.3][:, 1]
        top = np.sort(ys[ys > 0])
        assert top[-1] - top[0] == pytest.approx(1.0, abs=0.15)


def test_basket_handles_cut_through_wall_textures():
    b = build.make("basket", "zigzag", draft=True)
    _ok(b)
    W, H = b.params["width"], b.params["height"]
    assert not _solid_at(b, [W / 2, 0, H - 20]) and not _solid_at(b, [-W / 2, 0, H - 20])
    spiral = build.make("basket", "pleats", draft=True)
    assert any("handle" in w for w in spiral.warnings)


@pytest.mark.parametrize("shape,texture", [("tray", "zigzag"), ("basket", "domes"), ("catchall", "fringe")])
def test_non_round_wall_pieces_get_a_slip_lid_that_follows_the_opening(shape, texture):
    b = build.make(shape, texture, options={"lid": "thread"}, draft=True)
    assert list(dict.fromkeys(n for n, *_ in b.extras)) == ["Lid", "Knob"] and all(m.is_watertight for _, m, _, _ in b.extras)
    assert b.stats["lid"]["style"] == "slip" and any("round rim" in w for w in b.warnings)
    W = b.params["width"]
    assert b.stats["lid"]["plug"] < min(W, b.params.get("depth", W))


def test_round_fabric_dish_takes_a_screw_lid():
    b = build.make("dish", "wave", options={"lid": "thread"}, draft=True)
    assert b.stats["lid"]["style"] == "thread"


def test_relief_flaps_never_leave_a_leaking_part():
    b = build.make("catchall", "melt")                 # found by the full sweep: a 2-triangle zero-volume flap
    assert all(m.is_watertight for _, m, _, _ in b.parts) and not any("watertight" in w for w in b.warnings)


def test_fur_unions_one_solid_per_layer():
    b = build.make("cup", "fur", {"diameter": 60, "height": 40})
    m = b.parts[0][1]
    assert m.is_watertight and len(m.split(only_watertight=False)) == 1 and b.stats["strands"] > 1000


def test_fittings_get_infill_and_a_top_through_a_layer_range():
    b = build.make("lantern", "domes", draft=True)
    r = [o for a, z, o in b.ranges if a < 10 < z]
    assert r and r[0]["sparse_infill_density"] == "20%" and r[0]["top_shell_layers"] == "4" and "layer_height" in r[0]


def test_merge_range_splits_and_keeps_layer_height():
    out = build._merge_range([(10.0, 30.0, {"layer_height": "0.28"})], 0.0, 20.0, {"top_shell_layers": "4"}, 0.2)
    assert [(a, b) for a, b, _ in out] == [(0.0, 10.0), (10.0, 20.0), (20.0, 30.0)]
    assert out[0][2] == {"top_shell_layers": "4", "layer_height": "0.20"}
    assert out[1][2] == {"layer_height": "0.28", "top_shell_layers": "4"} and out[2][2] == {"layer_height": "0.28"}


# ── textured lids: the lid gets the piece's own treatment ───────────────────────────────────────────────
@pytest.mark.parametrize("shape,texture,style,cap", [("cup", "twill", "thread", "Twill"), ("basket", "domes", "slip", "Knit"),
                                                     ("tray", "twill", "slip", "Twill"), ("cup", "fringe", "slip", "Plain"),
                                                     ("cup", "mix", "slip", "Zigzag"), ("vase", "zigzag", "magnets", "Zigzag"),
                                                     ("cachepot", "pleats", "slip", "Pleats"), ("basket", "twill", "slip", "Twill"),
                                                     ("catchall", "grid", "slip", "Weave"), ("platter", "twill", "slip", "Twill")])
def test_lid_is_a_cap_of_the_piece(shape, texture, style, cap):
    b = build.make(shape, texture, options={"lid": style}, colours=["#8B3A2F", "#EDE3D1"], draft=True)
    assert b.stats["lid"]["cap"] == cap
    lid = [m for n, m, _, _ in b.extras if n == "Lid"]
    assert lid and all(m.is_watertight for m in lid)
    # the plug reaches below the cap's rim plane into the piece once assembled
    top = b.stats["size"][2]
    low = min(m.bounds[0][2] for n, m, _, _ in b.assembled if n == "Lid")
    assert low < top - 2.5


def test_woven_lid_plug_follows_the_course_colours():
    b = build.make("cup", "twill", {"diameter": 70, "height": 50}, options={"lid": "slip"},
                   colours=["#8B3A2F", "#EDE3D1"], draft=True)
    rh = printer.nozzle(0.4).rod_h
    lid = [(m, c) for n, m, _, c in b.extras if n == "Lid"]
    assert len({c for _, c in lid}) == 2 and all(m.is_watertight for m, _ in lid)
    # every course band of the lid is a single colour: no layer mixes the two
    for k in range(int(max(m.bounds[1][2] for m, _ in lid) / rh)):
        zc = (k + 0.5) * rh
        here = {c for m, c in lid if m.bounds[0][2] < zc < m.bounds[1][2] and
                m.section(plane_origin=[0, 0, zc], plane_normal=[0, 0, 1]) is not None}
        assert len(here) <= 1, (k, here)


def test_plate_wide_change_count_includes_the_lid():
    b = build.make("cup", "twill", {"diameter": 70, "height": 50}, options={"lid": "thread"},
                   colours=["#8B3A2F", "#EDE3D1"], draft=True)
    plain = build.make("cup", "twill", {"diameter": 70, "height": 50}, colours=["#8B3A2F", "#EDE3D1"], draft=True)
    assert b.stats["swaps"] >= plain.stats["swaps"]


# ── the Lid section: any look, colours, height and knob ─────────────────────────────────────────────────
@pytest.mark.parametrize("shape,texture,opts,cap,cols", [
    ("cup", "zigzag", {"lid_texture": "twill", "lid_colours": ["#2E4E7E", "#EDE3D1"]}, "Twill", {"#2E4E7E", "#EDE3D1"}),
    ("tray", "zigzag", {"lid_texture": "halftone", "lid_colours": ["#F3D34A", "#C3302C"]}, "Halftone", {"#F3D34A", "#C3302C"}),
    ("basket", "twill", {"lid_texture": "domes", "lid_colours": ["#EDE3D1"]}, "Knit", {"#EDE3D1"}),
    ("cup", "halftone", {"lid_texture": "plain", "lid_colours": ["#2E4E7E"]}, "Plain", {"#2E4E7E"}),
    ("tray", "twill", {"lid_texture": "polar"}, "Plain", None),                      # doesn't fit a square: plain + note
])
def test_lid_section_picks_any_look(shape, texture, opts, cap, cols):
    b = build.make(shape, texture, options={"lid": "slip", **opts}, colours=["#8B3A2F", "#EDE3D1"], draft=True)
    assert b.stats["lid"]["cap"] == cap
    lid = [(m, c) for n, m, _, c in b.extras if n == "Lid"]
    assert all(m.is_watertight for m, _ in lid)
    if cols:
        assert {c for _, c in lid} == cols
    if texture == "twill" and opts.get("lid_texture") == "polar":
        assert any("doesn't fit" in w for w in b.warnings)


def test_lid_height_and_knob_styles():
    tall = build.make("cup", "zigzag", options={"lid": "slip", "lid_height": 24, "lid_knob": "none"}, draft=True)
    assert tall.stats["lid"]["cap_h"] == 24 and not any(n == "Knob" for n, *_ in tall.extras)
    btn = build.make("cup", "zigzag", options={"lid": "slip", "lid_knob": "button"}, draft=True)
    knob = [m for n, m, _, _ in btn.extras if n == "Knob"][0]
    assert knob.is_watertight and knob.bounds[1][2] - knob.bounds[0][2] < 7.0      # low button + peg


def test_studio_catalogue_lists_lid_looks():
    from studio import server
    c = server.app.test_client().get("/api/catalogue").get_json()
    keys = [t["key"] for t in c["lid"]["textures"]]
    assert keys[:2] == ["match", "plain"] and "twill" in keys and "fringe" not in keys and "fuzzy" not in keys


def test_one_part_objects_carry_their_filament_at_object_level(tmp_path):
    import re
    b = build.make("cup", "zigzag", {"diameter": 70, "height": 50}, options={"lid": "slip", "lid_texture": "plain",
                   "lid_colours": ["#2E4E7E"]}, colours=["#8B3A2F"], draft=True)
    ms = zipfile.ZipFile(b.write_3mf(tmp_path / "k.3mf")).read("Metadata/model_settings.config").decode()
    for ob in re.findall(r'<object id="\d+">(.*?)</object>', ms, re.S):
        obj_ext = re.search(r'^    <metadata key="extruder" value="(\d)"/>', ob, re.M).group(1)
        part_ext = re.findall(r'<part .*?key="extruder" value="(\d)"', ob, re.S)[0]
        assert obj_ext == part_ext                     # the knob is blue, not filament 1


@pytest.mark.slicer
def test_real_slicer_counts_a_three_colour_lid(tmp_path):
    if not bambu.slicer_available():
        pytest.skip("Bambu Studio not installed")
    import re
    b = build.make("cup", "zigzag", {"diameter": 70, "height": 50}, options={"lid": "slip", "lid_texture": "twill",
                   "lid_colours": ["#2E4E7E", "#EDE3D1"]}, colours=["#8B3A2F"])
    r = bambu.slice_project(b.write_3mf(tmp_path / "l.3mf"), tmp_path / "s")
    assert "error" not in r, r
    g = zipfile.ZipFile(tmp_path / "s" / "sliced.3mf").read("Metadata/plate_1.gcode").decode(errors="ignore")
    assert len(re.findall(r"^M620 S\dA", g, re.M)) == b.stats["swaps"]


# ── cheaper multi-colour: courses per colour, no tower, lid on its own plate ─────────────────────────────
@pytest.mark.parametrize("g", [2, 3, 4])
def test_courses_per_colour_divides_the_changes(g):
    one = build.make("cup", "twill", {"diameter": 70, "height": 50}, colours=["#8B3A2F", "#EDE3D1"], draft=True)
    grp = build.make("cup", "twill", {"diameter": 70, "height": 50}, options={"course_group": str(g)},
                     colours=["#8B3A2F", "#EDE3D1"], draft=True)
    assert grp.stats["swaps"] <= one.stats["swaps"] / g + 1 and len(grp.parts) == 2


def test_tower_off_writes_no_tower_and_drops_its_purge(tmp_path):
    on = build.make("cup", "twill", {"diameter": 70, "height": 50}, colours=["#8B3A2F", "#EDE3D1"], draft=True)
    off = build.make("cup", "twill", {"diameter": 70, "height": 50}, options={"tower": "off"},
                     colours=["#8B3A2F", "#EDE3D1"], draft=True)
    cfg = json.loads(zipfile.ZipFile(off.write_3mf(tmp_path / "o.3mf")).read("Metadata/project_settings.config"))
    assert cfg["enable_prime_tower"] == "0" and off.stats["grams_purge"] < on.stats["grams_purge"]


def test_auto_puts_a_costly_lid_on_its_own_plate(tmp_path):
    o = {"lid": "slip", "lid_texture": "twill", "lid_colours": ["#2E4E7E", "#EDE3D1"]}
    auto = build.make("cup", "zigzag", {"diameter": 70, "height": 50}, options=o, colours=["#8B3A2F"], draft=True)
    same = build.make("cup", "zigzag", {"diameter": 70, "height": 50}, options=dict(o, lid_plate="same"),
                      colours=["#8B3A2F"], draft=True)
    assert auto.stats["lid"]["plate"] == "own" and auto.stats["swaps"] < same.stats["swaps"]
    auto.write_3mf(tmp_path / "a.3mf")
    assert (tmp_path / "a-lid.3mf").exists()
    plain = build.make("cup", "zigzag", {"diameter": 70, "height": 50}, options={"lid": "slip"}, draft=True)
    assert plain.stats["lid"]["plate"] == "same"                     # a matching lid shares the plate for free


@pytest.mark.slicer
@pytest.mark.parametrize("opts", [{"course_group": "3"}, {"tower": "off"}])
def test_real_slicer_on_cheaper_colour_options(tmp_path, opts):
    if not bambu.slicer_available():
        pytest.skip("Bambu Studio not installed")
    import re
    b = build.make("cup", "twill", {"diameter": 60, "height": 40}, options=opts, colours=["#8B3A2F", "#EDE3D1"])
    r = bambu.slice_project(b.write_3mf(tmp_path / "c.3mf"), tmp_path / "s")
    assert "error" not in r, r
    g = zipfile.ZipFile(tmp_path / "s" / "sliced.3mf").read("Metadata/plate_1.gcode").decode(errors="ignore")
    assert len(re.findall(r"^M620 S\dA", g, re.M)) == b.stats["swaps"]
    if opts.get("tower") == "off":
        assert "; FEATURE: Prime tower" not in g


# ── picture library, text, plugins ──────────────────────────────────────────────────────────────────────
def test_text_pictures_fit_the_wall_and_drive_every_picture_texture():
    from text2print import pictures
    im = pictures.render_text("MOBI", "futura", "repeat", aspect=4.0)
    assert im.size[0] == pytest.approx(4 * im.size[1], rel=0.02)
    o = {"picture": "text", "text": "HI", "font": "impact"}
    a = build.make("cup", "halftone", {"diameter": 60, "height": 40}, options=o, colours=["#F3D34A", "#2E4E7E"], draft=True)
    b = build.make("cup", "halftone", {"diameter": 60, "height": 40}, colours=["#F3D34A", "#2E4E7E"], draft=True)
    _ok(a)
    assert abs(a.parts[0][1].volume - b.parts[0][1].volume) > 1.0      # the words change the ribs
    for shape, tex in (("cup", "litho"), ("tile", "flatlitho"), ("tile", "cmyk")):
        _ok(build.make(shape, tex, options=o, draft=True))


def test_plugins_register_build_and_unregister(tmp_path, monkeypatch):
    import shutil, pathlib as pl
    from text2print import plugins, pictures, lattice
    src = pl.Path(__file__).resolve().parent.parent / "plugin_examples"
    for f in src.glob("*.py"):
        shutil.copy(f, tmp_path / f.name)
    monkeypatch.setattr(plugins, "DIR", tmp_path)
    keys = plugins.load_all()
    assert {"x_diamond_weave", "x_fish_scales"} <= set(keys) and "lib:koi" in pictures.library()
    w = build.make("coaster", "x_diamond_weave", {"width": 70, "height": 6, "dish": 0}, colours=["#8B3A2F", "#EDE3D1"], draft=True)
    f = build.make("cup", "x_fish_scales", {"diameter": 60, "height": 40}, draft=True)
    k = build.make("cup", "halftone", {"diameter": 60, "height": 40}, options={"picture": "lib:koi"},
                   colours=["#F3D34A", "#2E4E7E"], draft=True)
    for b in (w, f, k):
        _ok(b)
    assert build.compatible("tray", "x_diamond_weave") and build.compatible("bowl", "x_fish_scales")
    (tmp_path / "fish_scales.py").unlink()
    plugins.load_all()
    assert "x_fish_scales" not in build.TEXTURES and "x_diamond_weave" in lattice.PATTERNS
    monkeypatch.setattr(plugins, "DIR", tmp_path / "none"); plugins.load_all()
    assert "x_diamond_weave" not in build.TEXTURES


def test_plugin_check_reports_and_a_broken_plugin_never_breaks_the_catalogue(tmp_path, monkeypatch):
    from text2print import plugins
    monkeypatch.setattr(plugins, "DIR", tmp_path)
    p = plugins.new("stitch", "soft ridges")
    r = plugins.check(p, tmp_path / "prev")
    item = r["items"][0]
    assert item["watertight"] and item["verdict"] == "ok" and pathlib.Path(item["preview"]).exists()
    (tmp_path / "broken.py").write_text("WOVEN = dict(name='x')\ndef pattern(:\n")
    plugins.load_all()
    assert "broken" in plugins.ERRORS
    from studio import server
    c = server.app.test_client().get("/api/catalogue").get_json()
    assert "broken" in c["pictures"]["errors"] and any(t["key"] == "x_soft_ridges" for t in c["textures"])
    monkeypatch.setattr(plugins, "DIR", tmp_path / "none"); plugins.load_all()
