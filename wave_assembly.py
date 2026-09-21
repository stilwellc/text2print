"""Assembly step renders for the wave panel: what goes into what, in order.
Each step is built by placing the real tile STLs and real 22 mm dowels in
world space, then rendered on the studio plate."""
import numpy as np, trimesh, pathlib
from tools.studio_render import render
TMP = pathlib.Path("/private/tmp/claude-501/-Users-collin/d0228fab-dcad-4e14-901d-16b88e6ce15e/scratchpad/wave")
TW, TD = 203.2, 177.8
PIN_Y = [TD * 0.2, TD * 0.8]                 # sockets on the left/right edges
PIN_X = [1.5 * TW / 9, 7.5 * TW / 9]         # sockets on the top/bottom edges
PIN_L, PIN_R = 22.0, 0.875                   # 22 mm of 1.75 mm filament

def tile(r, c, dx=0.0, dy=0.0):
    m = trimesh.load(f"wave_tile_r{r}_c{c}.stl", force="mesh")
    m.apply_translation((c * TW + dx, r * TD + dy, 0)); return m

def pin(x, y, axis):
    p = trimesh.creation.cylinder(radius=PIN_R, height=PIN_L, sections=24)
    R = trimesh.geometry.align_vectors([0, 0, 1.0], axis)
    p.apply_transform(R); p.apply_translation((x, y, 2.0)); return p

X, Y = np.array([1.0, 0, 0]), np.array([0, 1.0, 0])

def shot(parts, name, yaw, pitch):
    m = trimesh.util.concatenate(parts); f = TMP / (name + ".stl"); m.export(f)
    render(str(f), f"{name}.png", yaw_deg=yaw, pitch_deg=pitch); print("rendered", name)

# built in reverse so the studio gallery (newest first) reads step 1 downward
shot([tile(r, c) for r in (0, 1) for c in range(6)], "wave_step_4_run", -22, -26)

rows = [tile(0, c, dy=-40) for c in range(6)] + [tile(1, c, dy=40) for c in range(6)]
rows += [pin(x + c * TW, TD + 40 - 11 + 0.0, Y) for c in range(6) for x in PIN_X]
shot(rows, "wave_step_3_rows", -22, -30)

strip = [tile(0, c, dx=(18 * c)) for c in range(6)]
strip += [pin((c + 1) * TW + 18 * c + 9, y, X) for c in range(5) for y in PIN_Y]
shot(strip, "wave_step_2_strip", -20, -34)

pair = [tile(0, 0), tile(0, 1, dx=60)]
pair += [pin(TW + 30, y, X) for y in PIN_Y]
shot(pair, "wave_step_1_joint", -34, -30)
