"""Print-cost, correctness and app plumbing added in v3."""
import json
import math
import zipfile

import numpy as np
import pytest

from text2print import bambu, build, compose, lan, printer, sampler, store, verify
from text2print.shapes import SHAPES

SMALL_CUP = {"diameter": 50, "height": 40}


def test_flush_volume_light_after_dark_costs_more():
    dark, light = "#2B2B2B", "#F4F1E8"
    assert bambu.flush_volume(dark, light) > bambu.flush_volume(light, dark) > 0
    assert bambu.flush_volume(dark, dark) == 0
    assert 90 <= bambu.flush_volume("#8B3A2F", "#EDE3D1") <= 600


def test_project_carries_flush_matrix_ranges_and_per_filament(tmp_path):
    b = build.make("cup", "mix", SMALL_CUP, options={"bands": compose.PRESETS["flame"]["bands"]}, colours=["#F3D34A", "#C3302C"])
    p = b.write_3mf(tmp_path / "m.3mf")
    with zipfile.ZipFile(p) as z:
        cfg = json.loads(z.read("Metadata/project_settings.config"))
        ranges = z.read("Metadata/layer_config_ranges.xml").decode()
    fm = [int(x) for x in cfg["flush_volumes_matrix"]]
    assert fm[0] == 0 and fm[3] == 0 and fm[1] != fm[2]                       # asymmetric, per colour pair
    assert '<object id="1">' in ranges and 'opt_key="layer_height">0.28<' in ranges
    assert "extruder" not in ranges and "line_width" not in ranges             # both break Bambu 2.8 (verified)
    assert len(cfg["fan_max_speed"]) == 2 and len(cfg["nozzle_temperature"]) == 2


def test_mix_halftone_band_edges_are_whole_layers():
    nz = printer.nozzle(0.4); S = SHAPES["cup"]
    _, _, info = compose.build(S, S.resolve(SMALL_CUP), nz, compose.PRESETS["flame"]["bands"])
    for z0, z1, opts in info["ranges"]:
        lh = float(opts["layer_height"]); n = (z1 - z0) / lh
        assert abs(n - round(n)) < 1e-6
    zs = [z for z, _, _ in info["layer_slots"]]
    assert all(b > a for a, b in zip(zs, zs[1:]))


def test_droop_slot_gets_droop_cooling_and_others_keep_full_fan():
    b = build.make("cup", "mix", SMALL_CUP, options={"bands": compose.PRESETS["skirt"]["bands"]}, colours=["#6A2C4F", "#E9B7C4"])
    fans = dict(zip(b.colours, b.per_filament["fan_max_speed"]))
    assert fans["#6A2C4F"] == "20" and fans["#E9B7C4"] == "100"


def test_colour_changes_match_the_geometry():
    """Independent check: section each colour part at every layer and count colour changes from the mesh."""
    b = build.make("cup", "mix", SMALL_CUP, options={"bands": [dict(texture="plain", share=40, slot=0),
                                                                dict(texture="halftone", share=30, slot=0, slot2=1),
                                                                dict(texture="wave", share=30, slot=1)]},
                   colours=["#F3D34A", "#C3302C"])
    _, _, info = compose.build(SHAPES["cup"], SHAPES["cup"].resolve(SMALL_CUP), printer.nozzle(0.4),
                               [dict(texture="plain", share=40, slot=0), dict(texture="halftone", share=30, slot=0, slot2=1),
                                dict(texture="wave", share=30, slot=1)])
    seq = []
    for z0, z1, _ in info["layer_slots"]:
        zm = (z0 + z1) / 2; here = []
        for _, m, slot, _ in b.parts:
            sec = m.section(plane_origin=[0, 0, zm], plane_normal=[0, 0, 1])
            if sec is not None and sec.length > 1:
                here.append(slot)
        assert len(here) == 1, (zm, here)
        seq.append(here[0])
    assert sum(1 for a, c in zip(seq, seq[1:]) if a != c) == b.stats["swaps"]


def test_lean_purge_cuts_the_estimate():
    std = build.make("cup", "halftone", {"height": 30}, colours=["#F3D34A", "#C3302C"])
    lean = build.make("cup", "halftone", {"height": 30}, colours=["#F3D34A", "#C3302C"], options={"purge": "lean"})
    assert lean.stats["grams_purge"] < std.stats["grams_purge"] and lean.flush_mult == 0.6


@pytest.mark.parametrize("texture", ["zigzag", "fringe", "halftone", "mix"])
def test_draft_is_lighter_and_flagged(texture):
    full = build.make("cup", texture, SMALL_CUP); draft = build.make("cup", texture, SMALL_CUP, draft=True)
    assert draft.draft and draft.stats["triangles"] < full.stats["triangles"]


def test_custom_profile_never_leans_out_past_the_overhang_law():
    S = SHAPES["custom"]
    v = S.resolve({"c0": 20, "c1": 100, "c2": 20, "c3": 100, "c4": 20, "height": 80, "diameter": 160})
    f, h, _ = S.profile(v)
    zs = np.arange(0, h, 0.2); r = np.array([f(z) for z in zs])
    assert (np.diff(r) <= 0.9 * 0.2 + 1e-6).all() and r.min() >= 12.0


@pytest.mark.parametrize("kind", ["garland", "drips", "melt"])
def test_reliefs_build_and_ramp_gently_from_below(kind):
    b = build.make("cup", kind, SMALL_CUP)
    m = b.parts[0][1]
    assert m.is_watertight and len(m.split(only_watertight=False)) == 1
    from text2print.fabric import relief
    th = np.linspace(0, 2 * np.pi, 2000, endpoint=False)
    zs = np.arange(6, 38, 0.1); d = np.array([relief(kind, th, z, 25, 6, 40, 2.0) for z in zs])
    up = np.diff(d, axis=0) / 0.1                                          # outward growth per mm going up
    assert up.max() <= 1.02                                                # <= 45 deg undersides


def test_verification_registry(tmp_path, monkeypatch):
    monkeypatch.setattr(verify, "FILE", tmp_path / "v.json")
    assert verify.status("fringe", 0.4)[0] == "untested"
    assert verify.status("halftone", 0.8)[0] == "published"
    verify.record("fringe", 0.4, "ok", "nice")
    assert verify.status("fringe", 0.4) == ("printed", "nice")
    b = build.make("cup", "fringe", SMALL_CUP)
    assert not any("Not printed yet" in w for w in b.warnings)


def test_store_designs_images_and_printer(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "HOME", tmp_path); monkeypatch.setattr(store, "IMAGES", tmp_path / "images")
    from PIL import Image
    import io
    buf = io.BytesIO(); Image.new("RGB", (40, 30), (10, 200, 30)).save(buf, format="PNG")
    key = store.save_image(buf.getvalue())
    assert store.image_path(key) and store.image_path("../etc") is None
    e = store.save_design({"name": "x", "link": "?shape=cup"}); assert store.designs()[0]["id"] == e["id"]
    store.delete_design(e["id"]); assert store.designs() == []
    c = store.save_printer_config({"ip": " 10.0.0.5 ", "serial": "S", "access_code": "A", "extra": "no"})
    assert c == {"ip": "10.0.0.5", "serial": "S", "access_code": "A", "name": ""}
    assert oct((tmp_path / "printer.json").stat().st_mode)[-3:] == "600"


def test_uploaded_image_drives_the_halftone(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "HOME", tmp_path); monkeypatch.setattr(store, "IMAGES", tmp_path / "images")
    from PIL import Image
    import io
    im = Image.new("L", (100, 100), 255); im.paste(0, (0, 0, 50, 100))                 # left half dark
    buf = io.BytesIO(); im.save(buf, format="PNG"); key = store.save_image(buf.getvalue())
    a = build.make("cup", "halftone", {"height": 20}, nozzle=0.8, options={"image": key})
    b = build.make("cup", "halftone", {"height": 20}, nozzle=0.8)
    va, vb = a.parts[0][1].vertices, b.parts[0][1].vertices
    assert va.shape == vb.shape and np.abs(va - vb).max() > 0.2                # the ribs moved with the picture


def test_lan_command_shape_and_guard():
    cmd = lan.project_command("x.3mf", "Tray", [0, 1], "abc")["print"]
    assert cmd["command"] == "project_file" and cmd["url"] == "ftp://x.3mf" and cmd["ams_mapping"] == [0, 1]
    assert cmd["param"] == "Metadata/plate_1.gcode" and cmd["use_ams"] is True
    with pytest.raises(ValueError):
        lan.check({"ip": "1.2.3.4"})


def test_plate_layout_stays_on_the_bed_and_off_the_tower():
    for key in ("woven", "fabric"):
        p = sampler.plate(key)
        tx, ty, tw = printer.TOWER
        for ob in p["objects"]:
            cx, cy = ob["position"]
            half = max(np.abs(m.bounds[:, :2]).max() for _, m, _ in ob["parts"])
            assert 0 < cx - half and cx + half < printer.BED and 0 < cy - half and cy + half < printer.BED
            assert not (cx + half > tx - tw / 2 and cy + half > ty - tw / 2)


@pytest.mark.slicer
def test_real_slicer_counts_the_same_colour_changes(tmp_path):
    if not bambu.slicer_available():
        pytest.skip("Bambu Studio not installed")
    import re
    b = build.make("cup", "mix", {"diameter": 50, "height": 30}, options={"bands": compose.PRESETS["flame"]["bands"]},
                   colours=["#F3D34A", "#C3302C"])
    r = bambu.slice_project(b.write_3mf(tmp_path / "m.3mf"), tmp_path / "s")
    assert "error" not in r
    g = zipfile.ZipFile(tmp_path / "s" / "sliced.3mf").read("Metadata/plate_1.gcode").decode(errors="ignore")
    assert len(re.findall(r"^M620 S\dA", g, re.M)) == b.stats["swaps"]
    heights = {round(float(x), 2) for x in re.findall(r"^; LAYER_HEIGHT: ([\d.]+)", g, re.M)}
    assert {0.2, 0.28} <= heights


@pytest.mark.parametrize("texture,opts", [("zigzag", {"zones": "4"}), ("fringe", {"zones": "3", "zone_style": "stripes"}),
                                          ("twill", {"colour_by": "height", "zones": "4"}),
                                          ("polar", {"colour_by": "height", "zones": "2"})])
def test_colour_zones_are_clean_parts_on_layer_boundaries(texture, opts):
    shape = {"twill": "coaster", "polar": "dish"}.get(texture, "cup")
    params = {"coaster": {"width": 70, "height": 8, "dish": 0}, "dish": {"diameter": 70, "height": 10, "dish": 44, "floor": 3}}.get(shape, SMALL_CUP)
    b = build.make(shape, texture, params, colours=["#8B3A2F", "#EDE3D1", "#C58A3F", "#2E4E7E"], options=opts)
    n = int(opts["zones"])
    assert len(b.parts) == n and all(m.is_watertight for _, m, _, _ in b.parts)
    assert b.stats["swaps"] >= n - 1


@pytest.mark.parametrize("shape,texture", [("cup", "zigzag"), ("vase", "wave"), ("tray", "twill"), ("dish", "polar"),
                                           ("bowl", "fringe"), ("custom", "garland"), ("cup", "mix")])
def test_lids_fit_inside_the_opening(shape, texture):
    from text2print import extras
    b = build.make(shape, texture, options={"lid": "lid"})
    assert list(dict.fromkeys(n for n, *_ in b.extras)) == ["Lid", "Knob"]
    lid_m = b.extras[0][1]
    assert lid_m.is_watertight and b.extras[1][1].is_watertight
    rim, open_r = extras.opening(b, SHAPES[shape], b.params)
    assert b.stats["lid"]["plug"] == pytest.approx(2 * (open_r - extras.FITS["slip"]), abs=0.1) and open_r < rim


def test_lid_shares_the_plate_when_it_fits(tmp_path):
    b = build.make("cup", "zigzag", {"diameter": 70, "height": 50}, options={"lid": "lid"})
    p = b.write_3mf(tmp_path / "c.3mf")
    with zipfile.ZipFile(p) as z:
        assert z.read("Metadata/model_settings.config").decode().count("<object id=") == 3
    big = build.make("tray", "twill", options={"lid": "lid"})
    big.write_3mf(tmp_path / "t.3mf")
    assert (tmp_path / "t-lid.3mf").exists()
