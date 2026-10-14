"""Catalogue, P2S profiles and the Bambu project files."""
import json
import zipfile

import pytest

from text2print import build, fabric, printer
from text2print.shapes import SHAPES


def test_every_shape_has_textures_and_every_texture_a_shape():
    for s in SHAPES:
        assert any(build.compatible(s, t) for t in build.TEXTURES), s
    for t in build.TEXTURES:
        assert any(build.compatible(s, t) for s in SHAPES), t


@pytest.mark.parametrize("size", printer.NOZZLES)
def test_resolved_profiles_match_their_nozzle(size):
    c = printer.base_config(size); n = printer.nozzle(size)
    assert c["nozzle_diameter"] == [f"{size}"]
    assert float(c["layer_height"]) == pytest.approx(n.layer_h)
    assert c["printer_settings_id"] == f"Bambu Lab P2S {size} nozzle"
    assert c["print_compatible_printers"] == [c["printer_settings_id"]]
    assert c["printable_area"][2] == "256x256"


@pytest.mark.parametrize("size", printer.NOZZLES)
def test_project_3mf_carries_nozzle_settings_and_one_part_per_colour(tmp_path, size):
    b = build.make("coaster", "grid", {"width": 70, "height": 6, "dish": 0}, nozzle=size)
    p = b.write_3mf(tmp_path / "t.3mf")
    with zipfile.ZipFile(p) as z:
        cfg = json.loads(z.read("Metadata/project_settings.config"))
        settings = z.read("Metadata/model_settings.config").decode()
    assert cfg["layer_height"] == f"{printer.nozzle(size).layer_h:.2f}"
    assert cfg["wall_loops"] == str(printer.nozzle(size).rod_lines)
    assert cfg["enable_prime_tower"] == "1" and len(cfg["filament_colour"]) == 2
    assert settings.count('key="extruder" value="1"') == 1 and settings.count('key="extruder" value="2"') == 1


def test_fabric_build_is_one_part_with_fabric_settings(tmp_path):
    b = build.make("cup", "zigzag", {"diameter": 60, "height": 30})
    assert len(b.parts) == 1 and b.parts[0][1].is_watertight
    assert b.overrides["wall_loops"] == "2" and b.overrides["enable_prime_tower"] == "0"


@pytest.mark.parametrize("shape", ["cup", "bowl", "vase"])
@pytest.mark.parametrize("stitch", list(fabric.STITCHES))
def test_fabric_every_shape_and_stitch(shape, stitch):
    small = {"cup": {"diameter": 60, "height": 30}, "bowl": {"diameter": 90, "height": 30},
             "vase": {"diameter": 80, "height": 80}}[shape]
    b = build.make(shape, stitch, small)
    assert b.parts[0][1].is_watertight


def test_fabric_floor_cutouts_stay_one_body():
    b = build.make("bowl", "zigzag", {"diameter": 120, "height": 30}, options={"floor": "diamonds"})
    m = b.parts[0][1]
    assert m.is_watertight and len(m.split(only_watertight=False)) == 1


def test_sizes_are_clamped_to_the_shape_limits():
    b = build.make("tray", "grid", {"width": 999, "height": 1})
    assert b.params["width"] == 200 and b.params["height"] == 12
