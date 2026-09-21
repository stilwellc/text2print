"""The eye plug: a front hemisphere (r = eye_r) on a 2 mm skirt that slides
into the head's cup (0.25 mm clearance a side), 3.4 mm pin socket in the
flat base. Crisp sofubi detailing on the dome: a flat-floored pupil, an iris
ring groove, 16 radial striations, a raised catchlight. Print base-down,
dome-up, 0.08 mm layers. All cuts are uniform-depth: each is a cylinder
∩ the shell between the dome and an inner offset sphere."""
import numpy as np, trimesh, kaiju_head as K
R, SKIRT = K.eye_r, 2.0
C = np.array([0, 0, SKIRT])
def sphere(r): s = trimesh.creation.icosphere(subdivisions=5, radius=r); s.apply_translation(C); return s
def cyl(r, h=40.0): return trimesh.creation.cylinder(radius=r, height=h, sections=96)
prof = [(0, 0), (R, 0), (R, SKIRT)] + [(float(R * np.cos(a)), float(SKIRT + R * np.sin(a))) for a in np.linspace(0.02, np.pi / 2, 60)]
prof[-1] = (0.0, float(SKIRT + R))
plug = trimesh.creation.revolve(prof, sections=192)
def shell(depth): return sphere(R + 1.0).difference(sphere(R - depth), engine="manifold")
cuts = []
cuts.append(cyl(2.7).intersection(shell(0.8), engine="manifold"))                                   # pupil
cuts.append(cyl(5.9).difference(cyl(5.2), engine="manifold").intersection(shell(0.5), engine="manifold"))   # iris ring
for k in range(16):                                                                                  # striations
    b = trimesh.creation.box(extents=(4.9 - 3.1, 0.55, 40.0)); b.apply_translation(((4.9 + 3.1) / 2, 0, 0))
    b.apply_transform(trimesh.transformations.rotation_matrix(np.radians(k * 360 / 16), [0, 0, 1]))
    cuts.append(b.intersection(shell(0.3), engine="manifold"))
sock = cyl(1.7, 12.0)   # 6 mm deep from the base
for c in cuts + [sock]: plug = plug.difference(c, engine="manifold")
# catchlight: a 1.3 mm bead sitting 0.5 mm proud, upper-outer at 45°
ang = np.radians(135); rr = 3.4; zz = SKIRT + np.sqrt(R * R - rr * rr)
cl = trimesh.creation.icosphere(subdivisions=4, radius=1.3); n = np.array([rr * np.cos(ang), rr * np.sin(ang), zz - SKIRT]); n /= np.linalg.norm(n)
cl.apply_translation(np.array([rr * np.cos(ang), rr * np.sin(ang), zz]) - n * 0.8)
plug = plug.union(cl, engine="manifold")
plug.export("sofubi_ape_eye.stl")
import manifold3d as m3d
mm = m3d.Manifold(m3d.Mesh(np.asarray(plug.vertices, np.float32), np.asarray(plug.faces, np.uint32)))
print(f"eye plug {plug.extents[0]:.1f} x {plug.extents[1]:.1f} x {plug.extents[2]:.1f} mm  {len(plug.faces):,} faces  watertight={plug.is_watertight}  manifold3d={mm.status()}  {plug.volume/1000*1.24:.1f} g  · print 2, dome up, 0.08 mm layers")
