"""
Goblin-bat mascot bust — Phase 1 base = Collin's STL (mascot_head_fixed.stl), untouched in form.
Rotate (file faces +X → −Y), seat on the bed, scale to 200 mm horn tip, centre the base on x = 0,
3 Taubin passes (removes the voxel stair-steps; 6+ starts to blur the eye rings and lips).
Usage: python mascot.py [out.stl]
"""
import sys, numpy as np, trimesh
SRC, H_TIP, SMOOTH = "mascot_head_ref.stl", 200.0, 3

def base():
    tm = trimesh.load(SRC, force="mesh")
    tm.apply_transform(trimesh.transformations.rotation_matrix(-np.pi / 2, [0, 0, 1]))
    tm.apply_translation([0, 0, -tm.bounds[0, 2]]); tm.apply_scale(H_TIP / tm.bounds[1, 2])
    bot = tm.vertices[:, 2] < 8; tm.apply_translation([-tm.vertices[bot, 0].mean(), 0, 0])
    if SMOOTH: trimesh.smoothing.filter_taubin(tm, lamb=0.5, nu=-0.53, iterations=SMOOTH)
    tm.apply_translation([0, 0, -tm.bounds[0, 2]])
    return tm

if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "mascot_p1.stl"
    tm = base(); tm.export(out); e = tm.extents
    print(f"wrote {out}: {e[0]:.1f} x {e[1]:.1f} x {e[2]:.1f} mm · {len(tm.faces):,} faces · watertight={tm.is_watertight}")
