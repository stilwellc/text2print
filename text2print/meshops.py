"""Shared mesh helpers."""

def manifold_to_trimesh(man, min_volume=0.05):
    """Manifold -> watertight trimesh. Manifold may split a vertex where different inputs met; it records those
    pairs in merge_from_vert/merge_to_vert. Applying exactly those (never a blanket merge, which would fuse
    rings that only touch) gives the true topology. Zero-volume slivers from coplanar cuts are dropped."""
    import numpy as np
    import trimesh
    out = man.to_mesh()
    verts = np.asarray(out.vert_properties)[:, :3]; tris = np.asarray(out.tri_verts).copy()
    mf, mt = np.asarray(out.merge_from_vert), np.asarray(out.merge_to_vert)
    if len(mf):
        remap = np.arange(len(verts)); remap[mf] = mt; tris = remap[tris]
    m = trimesh.Trimesh(verts, tris, process=False)
    m.remove_unreferenced_vertices()
    bodies = m.split(only_watertight=False)
    keep = [b for b in bodies if abs(b.volume) > min_volume]
    if len(keep) != len(bodies):
        m = trimesh.util.concatenate(keep)
    if len(m.faces) and m.volume < 0:
        m.invert()
    return m


def drop_flaps(mesh, min_volume=1e-3):
    """Remove zero-volume flaps (e.g. two back-to-back triangles a relief can leave at one radius). Only touches a
    mesh that isn't already watertight; returns it unchanged when there's nothing to drop."""
    import trimesh
    if mesh.is_watertight:
        return mesh
    bodies = mesh.split(only_watertight=False)
    keep = [b for b in bodies if abs(b.volume) > min_volume]
    if not keep or len(keep) == len(bodies):
        return mesh
    out = trimesh.util.concatenate(keep)
    return out
