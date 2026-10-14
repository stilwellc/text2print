"""Coarse grid over the Phase-1 warps, scored by mascot_map IoU (front weighted 2:1 over three-quarter)."""
import itertools, subprocess, re, sys, json, mascot
S = "/private/tmp/claude-501/-Users-collin/ef956a5a-39a6-4219-99f0-1df75b8b70a5/scratchpad"
grid = dict(head_tilt_deg=[10, 16, 22], ear_lift_deg=[8, 12], ear_sweep_deg=[0, 14], ear_scale=[0.94], ear_r_scale=[0.92], cheek_slim=[0.10], right_slim=[0.06])
rows = []
for combo in itertools.product(*grid.values()):
    W = dict(mascot.WARP); W.update(dict(zip(grid.keys(), combo)))
    tm = mascot.build(W); tm.export(f"{S}/search.stl")
    out = subprocess.run([sys.executable, "mascot_map.py", f"{S}/search.stl", f"{S}/search", "--az3", "42", "--azp", "70"], capture_output=True, text=True).stdout
    ious = [float(m) for m in re.findall(r"IoU ([\d.]+)", out)]
    score = (2 * ious[0] + ious[1] + ious[2] + ious[3]) / 5
    rows.append((score, ious, dict(zip(grid.keys(), combo)))); print(f"{score:.4f} F {ious[0]:.3f} 3Q {ious[1]:.3f} P {ious[2]:.3f} B {ious[3]:.3f} {dict(zip(grid.keys(), combo))}", flush=True)
rows.sort(key=lambda r: -r[0]); json.dump(rows[:5], open(f"{S}/search_top.json", "w"), indent=1)
print("BEST", rows[0])
