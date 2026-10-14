"""Shared mesh helpers."""

def manifold_to_trimesh(man, min_volume=0.05, split=True):
    """Manifold -> watertight trimesh. Manifold may split a vertex where different inputs met; it records those
    pairs in merge_from_vert/merge_to_vert. Applying exactly those (never a blanket merge, which would fuse
    rings that only touch) gives the true topology. Zero-volume slivers from coplanar cuts are dropped — found
    with Manifold's own decompose/volume (C++), not trimesh's graph split, which dominated big builds."""
    import numpy as np
    import trimesh
    import manifold3d as m3d
    comps = man.decompose() if split else [man]          # split=False: many disjoint bodies (woven rods) on
    if len(comps) > 1:                                    # purpose — check slivers afterwards with drop_flaps
        keep = [c for c in comps if abs(c.volume()) > min_volume]
        if len(keep) != len(comps):
            man = m3d.Manifold.compose(keep) if keep else m3d.Manifold()
    out = man.to_mesh()
    verts = np.asarray(out.vert_properties)[:, :3]; tris = np.asarray(out.tri_verts).astype(np.int64)
    mf, mt = np.asarray(out.merge_from_vert), np.asarray(out.merge_to_vert)
    if len(mf):
        remap = np.arange(len(verts)); remap[mf] = mt; tris = remap[tris]
    m = trimesh.Trimesh(verts, tris, process=False)
    if len(mf):
        m.remove_unreferenced_vertices()
    return m                                       # Manifold output is consistently outward: no sign fix needed


def drop_flaps(mesh, min_volume=1e-3):
    """Remove zero-volume flaps (e.g. two back-to-back triangles a relief can leave at one radius). Only touches a
    mesh that isn't already watertight; returns it unchanged when there's nothing to drop."""
    import trimesh
    if watertight(mesh):
        return mesh
    bodies = mesh.split(only_watertight=False)
    keep = [b for b in bodies if abs(b.volume) > min_volume]
    if not keep or len(keep) == len(bodies):
        return mesh
    out = trimesh.util.concatenate(keep)
    return out


def volume(mesh):
    """Signed volume by the divergence theorem — what the stats need, without trimesh's full mass properties
    (inertia tensors etc.), which cost seconds on multi-million-triangle walls."""
    import numpy as np
    t = mesh.vertices[mesh.faces]
    return float(np.einsum("ij,ij->i", t[:, 0], np.cross(t[:, 1], t[:, 2])).sum() / 6.0)


def watertight(mesh):
    """Every edge shared by exactly two faces. Depends on faces only, so it is remembered on the mesh (moves and
    outline warps don't change it)."""
    import numpy as np
    key = ("wt", len(mesh.faces), int(mesh.faces[:7].sum()) if len(mesh.faces) else 0)
    if mesh.metadata.get("_wt_key") == key:
        return mesh.metadata["_wt"]
    f = np.asarray(mesh.faces, np.int64)
    e = np.sort(np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]]), axis=1)
    code = e[:, 0] * (int(f.max()) + 1 if len(f) else 1) + e[:, 1]
    _, counts = np.unique(code, return_counts=True)
    ok = bool(len(f)) and bool((counts == 2).all())
    mesh.metadata["_wt_key"] = key; mesh.metadata["_wt"] = ok
    return ok
