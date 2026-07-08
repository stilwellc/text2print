import sys
from pathlib import Path

import pytest
import trimesh

ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT), str(ROOT / "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)

REPO_ROOT = str(ROOT)   # kept for tests that shell out


@pytest.fixture
def cube_stl(tmp_path):
    """A watertight 10mm cube STL, generated directly (no CAD kernel)."""
    path = tmp_path / "cube.stl"
    trimesh.creation.box(extents=(10, 10, 10)).export(str(path))
    return path
