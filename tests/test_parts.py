"""Parts that are not in the catalogue, and the checks that go with them (Nov 2026 audit)."""
import json
import pathlib
import zipfile

import numpy as np
import pytest
import trimesh

from text2print import bambu, build, drawing, extras, lattice, meshops, part, printer, verify
from text2print.__main__ import main


def _cfg(p):
    with zipfile.ZipFile(p) as z:
        return json.loads(z.read("Metadata/project_settings.config")), z.read("Metadata/model_settings.config").decode()


def _sleeve():
    return meshops.manifold_to_trimesh(extras.revolve([(8.5, 0), (20, 0), (20, 0.6), (10.1, 20), (10.1, 30), (8.5, 30)]))


def test_deliver_writes_a_petg_part_at_petg_speeds_with_its_files(tmp_path):
    r = part.deliver("sleeve", [("Sleeve", _sleeve(), 1)], ["#FFFFFF"], material="petg", out=tmp_path,
                     check={"length": (30.0, "z"), "bell": (40.0, "x")}, first_layer=15)
    cfg, _ = _cfg(r["project"])
    first = lambda k: float(cfg[k][0])
    assert cfg["filament_type"] == ["PETG"] and first("outer_wall_speed") <= 60 and first("initial_layer_speed") == 15
    assert cfg["wall_loops"] == "3" and cfg["sparse_infill_density"] == "20%" and cfg["enable_prime_tower"] == "0"
    assert r["size"] == [40.0, 40.0, 30.0] and all((tmp_path / f).exists() for f in ("sleeve.stl", "sleeve.png", "sleeve_dimensions.png"))
    pla, _ = _cfg(part.deliver("s2", [("Sleeve", _sleeve(), 1)], ["#FFFFFF"], out=tmp_path / "pla", render=False, drawing=False)["project"])
    assert pla["filament_type"] == ["PLA"] and float(pla["outer_wall_speed"][0]) == 200      # PLA keeps the stock speeds


def test_deliver_refuses_a_fit_part_at_the_wrong_size(tmp_path):
    with pytest.raises(ValueError, match="built 30.00 mm on z, wanted 33.00"):
        part.deliver("s", [("Sleeve", _sleeve(), 1)], ["#FFFFFF"], out=tmp_path, check={"length": (33.0, "z")}, render=False, drawing=False)
    with pytest.raises(ValueError, match="colour slot 2"):
        part.deliver("s", [("Sleeve", _sleeve(), 2)], ["#FFFFFF"], out=tmp_path, render=False, drawing=False)


def test_two_colours_go_in_one_object_and_black_can_print_first(tmp_path):
    a = trimesh.creation.box((30, 30, 2)); a.apply_translation([0, 0, 1])
    b = trimesh.creation.box((10, 10, 0.4)); b.apply_translation([0, 0, 2.2])
    r = part.deliver("tag", [("White", a, 1), ("Black", b, 2)], ["#FFFFFF", "#111111"], material="petg", out=tmp_path,
                     first_layer_order=(2, 1), render=False, drawing=False)
    cfg, settings = _cfg(r["project"])
    assert settings.count("<object ") == 1 and '<metadata key="first_layer_print_sequence" value="2 1"/>' in settings
    assert cfg["enable_prime_tower"] == "1" and cfg["filament_type"] == ["PETG", "PETG"] and len(r["stls"]) == 2


def test_a_scalar_override_takes_the_configs_list_shape_on_every_nozzle(tmp_path):
    box = trimesh.creation.box((20, 20, 5)); box.apply_translation([0, 0, 2.5])
    for size in (0.4, 0.8):
        base = printer.base_config(size)
        p = bambu.write_3mf(str(tmp_path / f"{size}.3mf"), [{"name": "b", "position": (128, 128), "parts": [("b", box, 1)]}],
                            colours=("#FFFFFF",), base=base, overrides={**bambu.PERFORATED_WALLS, **bambu.SMALL_LOOPS_FIRST_LAYER})
        cfg, _ = _cfg(p)
        for k in ("small_perimeter_speed", "initial_layer_speed", "initial_layer_acceleration"):
            assert isinstance(cfg[k], list) and len(cfg[k]) == len(base[k]) and set(cfg[k]) == {str(bambu.SMALL_LOOPS_FIRST_LAYER.get(k, bambu.PERFORATED_WALLS.get(k)))}


def test_a_seated_threaded_lid_does_not_cut_into_its_ring():
    """The helix was squeezed to 3.5 mm of travel a turn instead of 6: ridges merged and the lid overlapped the ring."""
    import manifold3d as m3d
    top = 50.0; s = extras.lid_set("thread", 40.0, 36.0, top)
    ring = m3d.Manifold.batch_boolean([extras._m3d(m) for m in s["rim"]], m3d.OpType.Add)
    lid = extras._m3d(s["lid"]).rotate([180, 0, 0]).translate([0, 0, top + extras.LID_T])
    overlap = [(ring ^ lid.rotate([0, 0, a])).volume() for a in range(0, 360, 6)]
    assert min(overlap) < 0.5 and max(overlap) > 50                # one turn finds the seat; elsewhere the ridges meet
    T = extras.THREAD; r = extras.helix_ridge(20.0, T["depth"], T["pitch"], T["starts"], 0.0, 14.4, +1)
    m = meshops.manifold_to_trimesh(r, split=False)
    assert abs(float(m.bounds[1][2] - m.bounds[0][2]) - (14.4 + 0.6)) < 0.2     # it fills the height it was given
    rad = np.hypot(m.vertices[:, 0], m.vertices[:, 1]); crest = m.vertices[rad > rad.max() - 0.05]
    drift = lambda lead: 1 - abs(np.exp(1j * T["starts"] * (np.arctan2(crest[:, 1], crest[:, 0]) - 2 * np.pi * crest[:, 2] / lead)).mean())
    assert drift(T["pitch"] * T["starts"]) < 1e-6 and drift(3.5) > 0.5             # the crest climbs pitch x starts a turn


def test_fine_rods_weave_on_an_outline_with_a_hole_and_the_audit_reads_it():
    nz = printer.fine_rod(0.4)
    assert (nz.rod_w, nz.rod_h, nz.pitch, nz.verified) == (0.84, 0.4, 1.8, False) and printer.nozzle(0.4).rod_w == 1.68
    sdf = lambda x, y: np.maximum(np.maximum(np.abs(x) - 30, np.abs(y) - 18), 10 - np.hypot(x, y))
    rods = lattice.weave_region(sdf, 5, nz, "chevron", extent=30, min_rod=2.0)
    by = rods.meshes(); allv = np.vstack([m.vertices for m in by.values()])
    assert set(by) == {0, 1} and np.hypot(allv[:, 0], allv[:, 1]).min() > 9.9 and abs(allv[:, 2].max() - 2.0) < 1e-6
    a = lattice.support_audit(rods)
    assert a["rods"] > 50 and a["loose_ends"] == 0 and a["longest_span"] < 1.5 * nz.pitch
    loose = lattice.Rods(nz); loose.line((-10, 0, 0.2), (10, 0, 0.2), 0); loose.line((0, -1, 0.6), (0, 9, 0.6), 1)
    b = lattice.support_audit(loose)
    assert b["loose_ends"] == 1 and b["longest_loose_end"] > 7       # 8.6 mm of rod past its one support
    held = lattice.support_audit(loose, frame=[(1, [(-10, 9), (10, 9)], 1.68)])
    assert held["loose_ends"] == 0 and held["longest_span"] > 7      # the same rod, now a bridge to a rim


def test_overrides_and_solid_part_follow_the_material():
    pla = printer.overrides(0.4, "lattice", slots=2); petg = printer.overrides(0.4, "lattice", slots=2, material="petg")
    assert float(pla["initial_layer_speed"][0]) == 35 and float(petg["initial_layer_speed"][0]) == 20
    assert float(petg["bridge_speed"][0]) == 30 and float(petg["inner_wall_speed"][0]) == 100
    assert printer.overrides(0.4, "droop", material="petg") == printer.overrides(0.4, "droop")   # strands are laid fast
    s = printer.solid_part(0.4, colours=2, material="petg", first_layer=15)
    assert s["enable_prime_tower"] == "1" and float(s["initial_layer_speed"][0]) == 15 and float(s["travel_speed"][0]) == 300
    assert float(printer.slow_first_layer(0.4, 40, {"initial_layer_speed": ["12", "12", "12"]})["initial_layer_speed"][0]) == 12


GCODE = """; model printing time: 1h 2m 3s; total estimated time: 1h 9m 0s
; total filament weight [g] : 3.50,1.25
M204 S300
; CHANGE_LAYER
G1 Z0.2 F600
G1 X0 Y0 F18000
; FEATURE: Outer wall
G1 X10 Y10 F18000
G1 X60 Y10 E2 F900
G1 X60 Y60 E2 F900
T1
G1 X10 Y60 E2 F900
; CHANGE_LAYER
G1 Z0.4 F600
M204 S4000
T0
; FEATURE: Inner wall
G1 X10 Y10 F18000
G1 X60 Y10 E2 F6000
T1
G1 X60 Y60 E2 F3600
"""


def test_print_report_reads_the_first_layer_from_the_gcode(tmp_path):
    f = tmp_path / "a.gcode"; f.write_text(GCODE)
    r = bambu.print_report(f)
    assert r["first_layer"]["Outer wall"] == {"mm": 150, "speed": 15, "fastest": 15} and r["rest"]["Inner wall"]["fastest"] == 100
    assert r["first_layer_order"] == ["T?", 2] and r["changes"] == 3 and r["accelerations"] == [300, 4000]
    assert r["grams_by_filament"] == [3.5, 1.25] and r["time"].startswith("1h 2m 3s") and r["fastest_travel"]["first_layer"] == 300


def test_verified_prints_are_kept_per_material(tmp_path, monkeypatch):
    monkeypatch.setattr(verify, "FILE", tmp_path / "v.json")
    verify.record("twill", 0.4, "ok", "tray")
    assert verify.status("twill", 0.4)[0] == "printed" and verify.status("twill", 0.4, "petg")[0] == "untested"
    b = build.make("tray", "twill", {}, options={"material": "petg"}, draft=True)
    assert "Printed in PLA; not yet in PETG" in b.warnings
    verify.record("twill", 0.4, "ok", "tray", material="petg")
    assert verify.status("twill", 0.4, "PETG")[0] == "printed" and set(verify.load()) == {"twill@0.4", "twill@0.4@petg"}


def test_cli_material_flag_check_and_part(tmp_path, capsys):
    assert main(["make", "tray", "grid", "--material", "petg", "--draft", "--out", str(tmp_path), "--no-stls"]) == 0
    cfg, _ = _cfg(json.loads(capsys.readouterr().out)["project"])
    assert set(cfg["filament_type"]) == {"PETG"} and float(cfg["initial_layer_speed"][0]) == 20
    f = tmp_path / "a.gcode"; f.write_text(GCODE)
    assert main(["check", str(f)]) == 0 and json.loads(capsys.readouterr().out)["changes"] == 3
    assert main(["check", str(tmp_path / "missing.3mf")]) == 2 and "no such file" in capsys.readouterr().out
    stl = tmp_path / "sleeve.stl"; _sleeve().export(stl)
    assert main(["part", str(stl), "--material", "petg", "--out", str(tmp_path / "p"), "--first-layer", "15"]) == 0
    r = json.loads(capsys.readouterr().out)
    assert r["size"] == [40.0, 40.0, 30.0] and float(_cfg(r["project"])[0]["initial_layer_speed"][0]) == 15


def test_dimension_sheet_measures_the_meshes_it_is_given(tmp_path):
    box = trimesh.creation.box((60, 27, 12.5)); box.apply_translation([0, 0, 6.25])
    assert drawing.dimension_sheet([(box, "#FFFFFF")], tmp_path / "d.png", dims=[("top", (-9.5, 0), (9.5, 0), "19.0")]) == (60.0, 27.0, 12.5)
    assert (tmp_path / "d.png").stat().st_size > 5000 and meshops.seat(trimesh.creation.box((4, 4, 4))).bounds[0][2] == 0


@pytest.mark.slicer
def test_the_real_slicer_reports_changes_grams_per_filament_and_the_sliced_file(tmp_path):
    if not bambu.slicer_available():
        pytest.skip("Bambu Studio not installed")
    a = trimesh.creation.box((30, 30, 2)); a.apply_translation([0, 0, 1])
    b = trimesh.creation.box((10, 10, 0.4)); b.apply_translation([0, 0, 2.2])
    r = part.deliver("tag", [("White", a, 1), ("Black", b, 2)], ["#FFFFFF", "#111111"], material="petg", out=tmp_path, slice=True)
    s = r["slice"]
    assert s["changes"] >= 1 and len(s["grams_by_filament"]) == 2 and abs(sum(s["grams_by_filament"]) - s["grams"]) < 0.02
    assert max(v["speed"] for v in r["report"]["first_layer"].values()) <= 30


# ── second audit: the delivery path's own bugs ─────────────────────────────────────────────────────────────────────
def _box(x, y, z, at=(0, 0, 0)):
    b = trimesh.creation.box((x, y, z)); b.apply_translation([at[0], at[1], at[2] + z / 2]); return b


def _u(inside=40.0, leg=3.0, deep=20.0, tall=10.0):
    back = _box(inside + 2 * leg, leg, tall, (0, deep / 2, 0))
    legs = [_box(leg, deep, tall, (sx * (inside + leg) / 2, -leg / 2, 0)) for sx in (-1, 1)]
    return trimesh.util.concatenate([back] + legs)


def test_a_handed_over_stl_is_never_written_over(tmp_path):
    src = tmp_path / "bracket.stl"; m = _box(20, 10, 5, at=(40, 7, 3)); m.export(src); before = src.read_bytes()
    r = part.from_stl(src, out=tmp_path, render=False, drawing=False)                 # the output folder IS its folder
    assert src.read_bytes() == before and r["stls"] == [str(src)] and (tmp_path / "bracket.3mf").exists()
    r2 = part.from_stl(src, out=tmp_path / "o", render=False, drawing=False)          # elsewhere: a seated copy is saved
    assert src.read_bytes() == before and (tmp_path / "o" / "bracket.stl").exists()
    with pytest.raises(FileNotFoundError):
        part.from_stl(tmp_path / "missing.stl", out=tmp_path)


def test_deliver_leaves_the_callers_mesh_where_it_was(tmp_path):
    m = _box(20, 10, 5, at=(40, 7, 3)); before = m.bounds.copy()
    for _ in range(2):
        part.deliver("b", [("B", m, 1)], ["#FFFFFF"], out=tmp_path, render=False, drawing=False)
    assert np.allclose(m.bounds, before)


def test_one_material_covers_every_colour_and_a_short_list_is_refused(tmp_path):
    a, b = _box(30, 30, 2), _box(10, 10, 0.4, at=(0, 0, 2))
    for mat in ("petg", ["petg"]):
        cfg, _ = _cfg(part.deliver("t", [("W", a, 1), ("K", b, 2)], ["#FFFFFF", "#111111"], material=mat, out=tmp_path,
                                   render=False, drawing=False)["project"])
        assert cfg["filament_type"] == ["PETG", "PETG"] and len(cfg["nozzle_temperature"]) == 2
    c = _box(5, 5, 0.4, at=(10, 10, 2))
    with pytest.raises(ValueError, match="2 materials for 3 colours"):
        part.deliver("t", [("W", a, 1), ("K", b, 2), ("R", c, 3)], ["#FFFFFF", "#111111", "#C0392B"], material=["petg", "pla"],
                     out=tmp_path, render=False, drawing=False)


def test_an_inside_size_is_checked_as_inside(tmp_path):
    u = _u(inside=40.0)
    assert round(part.span(u, (0, -3, 5), "x")[0], 3) == 40.0 and round(part.span(u, (21.5, -3, 5), "x")[0], 3) == 3.0
    r = part.deliver("u", [("U", u, 1)], ["#FFFFFF"], out=tmp_path, render=False,
                     check={"between the legs": (40.0, "x", (0, -3, 5)), "outside": (46.0, "x")}, assumed=["leg 3 mm"])
    assert r["checks"] == {"between the legs": 40.0, "outside": 46.0} and (tmp_path / "u_dimensions.png").exists()
    assert "assumed, not measured: leg 3 mm" in r["warnings"]
    with pytest.raises(ValueError, match="between the legs: built 40.00 mm on x, wanted 46.00"):   # outside taken for inside
        part.deliver("u", [("U", u, 1)], ["#FFFFFF"], out=tmp_path, render=False, drawing=False, check={"between the legs": (46.0, "x", (0, -3, 5))})
    with pytest.raises(ValueError, match="nothing to measure"):
        part.span(u, (0, -3, 5), "y")                                                 # the U is open that way


def test_several_pieces_share_one_plate_without_touching(tmp_path):
    lid, base = _box(60, 60, 4), _box(60, 60, 30)
    r = part.deliver("can", {"Lid": [("Lid", lid, 1)], "Base": [("Base", base, 1)]}, ["#FFFFFF"], out=tmp_path, render=False,
                     check={"lid": (4.0, "z", None, "Lid"), "base": (30.0, "z", None, "Base")}, copies=2)
    cfg, settings = _cfg(r["project"])
    assert settings.count("<object ") == 4 and r["pieces"] == {"Lid": [60.0, 60.0, 4.0], "Base": [60.0, 60.0, 30.0]}
    assert sorted(pathlib.Path(f).name for f in r["stls"]) == ["can_base.stl", "can_lid.stl"] and len(r["drawings"]) == 2
    centres, warn = part._layout([(60, 60)] * 4, False)
    assert not warn and all(abs(a[0] - b[0]) >= 66 - 1e-6 or abs(a[1] - b[1]) >= 66 - 1e-6 for i, a in enumerate(centres) for b in centres[i + 1:])
    with pytest.raises(ValueError, match="name the piece"):
        part.deliver("can", {"Lid": [("Lid", lid, 1)], "Base": [("Base", base, 1)]}, ["#FFFFFF"], out=tmp_path, render=False,
                     drawing=False, check={"lid": (4.0, "z")})


def test_a_long_two_colour_part_is_moved_clear_of_the_prime_tower():
    zx, zy = part.TOWER_ZONE
    (c,), warn = part._layout([(190, 200)], True)                                      # slides left
    assert not warn and c[0] + 95 <= zx + 1e-6 and c[0] - 95 >= part.EDGE
    (c,), warn = part._layout([(230, 120)], True)                                     # too long to slide: goes behind
    assert not warn and c[1] - 60 >= zy - 1e-6
    _, warn = part._layout([(230, 230)], True)
    assert warn and "prime tower" in warn[0]
    _, warn = part._layout([(300, 20)], False)
    assert warn and "does not fit" in warn[0]


def test_base_overrides_still_take_layer_walls_and_infill(tmp_path):
    base = printer.overrides(0.4, "lattice", slots=1)
    cfg, _ = _cfg(part.deliver("b", [("B", _box(20, 20, 5), 1)], ["#FFFFFF"], out=tmp_path, render=False, drawing=False,
                               base_overrides=base, layer_h=0.12, walls=2, infill="35%")["project"])
    assert (cfg["layer_height"], cfg["wall_loops"], cfg["sparse_infill_density"]) == ("0.12", "2", "35%")
    assert printer.solid_part(0.2)["initial_layer_print_height"] == "0.1" and printer.solid_part(0.4)["initial_layer_print_height"] == "0.2"


def test_the_support_audit_counts_shifted_and_skipped_courses():
    nz = printer.nozzle(0.4); rh = nz.rod_h
    def rods(zs):
        r = lattice.Rods(nz)
        for i, z in enumerate(zs):
            for k in range(-2, 3):
                a, b = ((-10, k * 3.6, z), (10, k * 3.6, z)) if i % 2 == 0 else ((k * 3.6, -10, z), (k * 3.6, 10, z))
                r.line(np.array(a, float), np.array(b, float), 0)
        return r
    flat = lattice.support_audit(rods([rh * (i + 0.5) for i in range(3)]))
    lifted = lattice.support_audit(rods([7.3 + rh * (i + 0.5) for i in range(3)]))    # the same weave, raised off z = 0
    assert flat["rods"] == lifted["rods"] == 10 and flat == lifted and flat["unsupported_courses"] == []
    gap = lattice.support_audit(rods([rh * 0.5, rh * 2.5]))                           # a course is missing under the top one
    assert gap["unsupported_courses"] == [2] and gap["loose_ends"] == 5 and gap["longest_loose_end"] == 20.0


def test_the_report_measures_arcs_and_names_the_first_filament(tmp_path):
    g = ["; filament: 1,2", ";VT1 H-1", "; CHANGE_LAYER", "G1 Z0.2 F600", "; FEATURE: Outer wall", "G1 X10 Y0 F1200",
         "G3 X-10 Y0 I-10 J0 E1 F1200", "G3 X10 Y0 I10 J0 E1", "T0", "; FEATURE: Inner wall", "G1 X5 Y0 F1200", "G1 X5 Y8 E1",
         "; total filament weight [g] : 1.00,2.00"]
    f = tmp_path / "a.gcode"; f.write_text("\n".join(g))
    rep = bambu.print_report(f)
    assert rep["first_layer"]["Outer wall"]["mm"] == round(2 * np.pi * 10) and rep["first_layer_order"] == [2, 1]
    assert abs(bambu._move_length("G2 X10 Y10 I0 J10", (0, 0), 10, 10) - np.pi * 5 * 3) < 1e-6      # clockwise: three quarters
    assert abs(bambu._move_length("G3 X10 Y10 I0 J10", (0, 0), 10, 10) - np.pi * 5) < 1e-6          # the other way: one quarter


def test_a_failed_slice_never_reads_back_an_old_result(tmp_path, monkeypatch):
    import subprocess
    (tmp_path / "result.json").write_text(json.dumps({"return_code": 0})); (tmp_path / "sliced.3mf").write_text("old")
    monkeypatch.setattr(bambu, "slicer_available", lambda: True)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: None)                       # the slicer dies without writing anything
    assert bambu.slice_project(tmp_path / "x.3mf", tmp_path) == {"error": "slicer produced no result"}
    assert not (tmp_path / "sliced.3mf").exists()
