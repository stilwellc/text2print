"""Validated STL loading for text2print.

Deliberately import-light: trimesh only, never pyrender, so headless
tools (the 3MF converter, strict checks, CI) can load meshes without
dragging in an OpenGL stack.
"""
import trimesh


def load_mesh(path):
    """Load *path* as a single triangle mesh.

    Returns a trimesh.Trimesh. Raises ValueError for anything that
    cannot become one: missing file, unparseable data, or a file with
    no triangles.
    """
    try:
        mesh = trimesh.load(str(path), force="mesh")
    except Exception as exc:
        raise ValueError(f"could not read STL {path!r}: {exc}") from exc
    if not isinstance(mesh, trimesh.Trimesh) or len(mesh.faces) == 0:
        raise ValueError(f"could not read STL {path!r}: no triangles found")
    return mesh
