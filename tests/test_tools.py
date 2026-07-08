"""Tests for the tools/ pipeline: loader, converter, runner, renderer."""
import os
import subprocess
import sys

import pytest

from conftest import REPO_ROOT
import mesh_io
import stl_to_3mf
import run_cadquery_model


# ── mesh_io ──────────────────────────────────────────────────────────

def test_load_mesh_roundtrip(cube_stl):
    tm = mesh_io.load_mesh(cube_stl)
    assert tm.is_watertight
    assert len(tm.faces) == 12


def test_load_mesh_missing_and_garbage(tmp_path):
    with pytest.raises(ValueError, match="could not read STL"):
        mesh_io.load_mesh(tmp_path / "absent.stl")
    junk = tmp_path / "junk.stl"
    junk.write_bytes(b"this is not geometry")
    with pytest.raises(ValueError):
        mesh_io.load_mesh(junk)


def test_mesh_io_never_imports_pyrender():
    # this process already has pyrender loaded via other tests, so the
    # only honest check is a clean subprocess
    code = ("import sys, mesh_io; "
            "sys.exit(1 if 'pyrender' in sys.modules else 0)")
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=os.path.join(REPO_ROOT, "tools"), capture_output=True)
    assert proc.returncode == 0, proc.stderr.decode()


# ── stl_to_3mf ───────────────────────────────────────────────────────

def test_convert_writes_3mf(cube_stl):
    out = stl_to_3mf.convert(cube_stl)
    assert out.suffix == ".3mf"
    assert out.stat().st_size > 0


def test_convert_cli_error_on_missing(tmp_path):
    rc = stl_to_3mf.main([str(tmp_path / "nope.stl")])
    assert rc == 1


# ── run_cadquery_model ───────────────────────────────────────────────

def _script(tmp_path, body):
    path = tmp_path / "model.py"
    path.write_text(body)
    return path


def test_runner_happy_path(tmp_path):
    script = _script(tmp_path, (
        "import trimesh\n"
        "trimesh.creation.box(extents=(8, 8, 8)).export('part.stl')\n"
        "print('done')\n"))
    result = run_cadquery_model.run(script)
    assert result["success"] is True
    assert result["stl"] == "part.stl"
    assert result["watertight"]["part.stl"] is True
    assert "done" in result["stdout"]


def test_runner_reports_script_failure(tmp_path):
    script = _script(tmp_path, "raise RuntimeError('geometry exploded')\n")
    result = run_cadquery_model.run(script)
    assert result["success"] is False
    assert "geometry exploded" in result["stderr"]
    assert result["stl"] is None


def test_runner_requires_an_export(tmp_path):
    script = _script(tmp_path, "print('forgot to export')\n")
    result = run_cadquery_model.run(script)
    assert result["success"] is False
    assert "no STL" in result["error"]


def test_runner_strict_rejects_open_mesh(tmp_path):
    script = _script(tmp_path, (
        "import numpy as np, trimesh\n"
        "v = np.array([[0,0,0],[10,0,0],[0,10,0]], dtype=float)\n"
        "trimesh.Trimesh(vertices=v, faces=[[0,1,2]]).export('open.stl')\n"))
    result = run_cadquery_model.run(script, strict=True)
    assert result["success"] is False
    assert "not watertight" in result["error"]


# ── preview (render smoke test) ──────────────────────────────────────

def test_preview_sheet_renders(cube_stl, tmp_path):
    import preview
    tm = mesh_io.load_mesh(cube_stl)
    out = tmp_path / "sheet.png"
    preview.render_multi_view(tm, str(out), resolution=180,
                              title="cube", src_path=str(cube_stl))
    assert out.stat().st_size > 10_000
