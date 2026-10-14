"""close-up: crop the mesh to a box (world coords) and render it"""
import sys, trimesh, numpy as np
sys.path.insert(0, "tools"); from studio_render import render
stl, out, box = sys.argv[1], sys.argv[2], list(map(float, sys.argv[3].split(",")))
yaw, pitch = (float(sys.argv[4]), float(sys.argv[5])) if len(sys.argv) > 5 else (180, -4)
tm = trimesh.load(stl); c = tm.triangles_center
m = (c[:,0]>box[0])&(c[:,0]<box[1])&(c[:,1]>box[2])&(c[:,1]<box[3])&(c[:,2]>box[4])&(c[:,2]<box[5])
sub = tm.submesh([np.where(m)[0]], append=True); sub.export("/tmp/k2crop.stl"); render("/tmp/k2crop.stl", out, 1000, 800, yaw, pitch)
