"""Bambu Studio's GUI rejects a project whose per-filament lists don't match its filament count, reporting
"The file does not contain any geometry data" (Oct 19 2026) — the CLI slicer still slices it, so only this test
catches it. Every per-filament list must be exactly n_fil long, for 1- and 2-filament projects alike."""
import json
import zipfile

import trimesh

from text2print import bambu, printer


def _cfg(path):
    return json.loads(zipfile.ZipFile(path).read("Metadata/project_settings.config"))


def _per_filament_bad(cfg):
    n = len(cfg["filament_colour"])
    return {k: v for k, v in cfg.items()
            if k.startswith(bambu.PER_FILAMENT_PREFIXES) and k not in bambu.NOT_PER_FILAMENT
            and isinstance(v, list) and len(v) != n}


def test_single_filament_project_has_single_filament_lists(tmp_path):
    p = tmp_path / "one.3mf"
    over = {"textured_plate_temp": ["55", "55"], "textured_plate_temp_initial_layer": ["60", "60"]}  # 2-long on purpose
    bambu.write_3mf(str(p), [{"name": "box", "position": (128, 128), "parts": [("box", trimesh.creation.box((20, 20, 20)), 1)]}],
                    colours=("#F2F2F0",), overrides=over, base=printer.base_config(0.4))
    cfg = _cfg(p)
    assert len(cfg["filament_colour"]) == 1
    assert cfg["filament_self_index"] == ["1"]
    assert _per_filament_bad(cfg) == {}


def test_two_filament_project_lists(tmp_path):
    p = tmp_path / "two.3mf"
    parts = [("a", trimesh.creation.box((20, 20, 20)), 1), ("b", trimesh.creation.box((5, 5, 5)), 2)]
    bambu.write_3mf(str(p), [{"name": "ab", "position": (128, 128), "parts": parts}], colours=("#F2F2F0", "#1C1C1C"),
                    base=printer.base_config(0.4))
    cfg = _cfg(p)
    assert cfg["filament_self_index"] == ["1", "2"]
    assert _per_filament_bad(cfg) == {}


def test_repair_fixes_an_old_file(tmp_path):
    p = tmp_path / "old.3mf"
    bambu.write_3mf(str(p), [{"name": "box", "position": (128, 128), "parts": [("box", trimesh.creation.box((20, 20, 20)), 1)]}],
                    colours=("#F2F2F0",), base=printer.base_config(0.4))
    z = zipfile.ZipFile(p); files = {i.filename: z.read(i) for i in z.infolist()}; z.close()
    cfg = json.loads(files["Metadata/project_settings.config"]); cfg["filament_self_index"] = ["1", "2"]
    files["Metadata/project_settings.config"] = json.dumps(cfg).encode()
    with zipfile.ZipFile(p, "w") as out:
        for k, v in files.items():
            out.writestr(k, v)
    assert "filament_self_index" in bambu.repair_3mf(str(p))
    assert _cfg(p)["filament_self_index"] == ["1"] and bambu.repair_3mf(str(p)) == []
