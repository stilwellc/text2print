"""Print-ready 90 mm tiles for the kept weave patterns (see textures/rodweave.py). One Bambu project per pattern,
one object with one part per colour, STLs beside it, CLI slice numbers in tiles_report.json.
Run: .venv/bin/python pattern_export.py [pattern ...]      -> ~/Downloads/woven_tray/patterns/<pattern>/"""
import json, pathlib, shutil, sys
sys.path.insert(0, ".")
from textures import rodweave as rw

KEEP = ["kagome", "polar", "ripple", "selvedge", "beat", "overunder", "tartan"]
TILE, TH, CORNER = 90.0, 12.0, 14.0
OUT = pathlib.Path.home() / "Downloads/woven_tray/patterns"
names = sys.argv[1:] or KEEP
report = json.load(open(OUT / "tiles_report.json")) if (OUT / "tiles_report.json").exists() else {}
for name in names:
    outline = rw.Circle(TILE) if name == "polar" else rw.RoundedSquare(TILE, CORNER)
    rods = rw.PATTERNS[name](outline, TH)
    d = OUT / name; d.mkdir(parents=True, exist_ok=True)
    for f in d.glob("tile_*"):
        f.unlink()
    n_col = len({c for _, c in rods})
    p3 = rw.export_bambu(d / f"tile_{name}_{n_col}color.3mf", rods, title=f"woven tile {name}")
    r = rw.slice_cli(p3, pathlib.Path("slice_out/woven/tiles") / name)
    r.update({"colours": n_col, "rods": len(rods), "swaps": rw.SWAP_COST[name]})
    report[name] = r; print(name, r, flush=True)
    png = {"ripple": "pattern_rippled.png", "overunder": "pattern_true.png"}.get(name, f"pattern_{name}.png")
    if pathlib.Path(png).exists():
        shutil.copy(png, d / f"tile_{name}_render.png")
json.dump(report, open(OUT / "tiles_report.json", "w"), indent=1)
