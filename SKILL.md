---
name: text2print
description: Textured 3D prints for a Bambu Lab P2S, picked from a catalogue. Use when someone wants a woven, basket, lattice, crosshatch, knit, fabric, zigzag, wave, drooping, fringe, loop, curl or two-colour halftone-picture tray, platter, dish, coaster, cup, lamp shade, bowl or vase; asks to "pick a pattern / pick a shape"; or wants to open or extend the text2print studio. Produces a Bambu Studio project (one object, one part per AMS colour, P2S settings for the chosen nozzle).
---

# text2print — pick a shape, pick a texture

Everything here is a TEXTURE ON A SHAPE. Don't model from scratch: pick from the catalogue, set sizes,
build, and hand over the Bambu project. Repo: ~/Dev/text2print (python package `text2print`, studio in `studio/`).

## Use it

```bash
cd ~/Dev/text2print
.venv/bin/python -m text2print list                                   # shapes, textures, what fits
.venv/bin/python -m text2print studio                                 # the picker, http://127.0.0.1:7384
.venv/bin/python -m text2print make <shape> <texture> --set key=mm ... --colours "#hex,#hex" \
    --nozzle 0.4 --out ~/Downloads/<name> --slice --render              # 3MF + STLs (+ CLI slice, render)
```

Deep-link the studio to a pick for the user: `/?shape=tray&texture=twill&nozzle=0.4&width=117&c=8B3A2F,EDE3D1`.
In Python: `from text2print import build; b = build.make("tray", "twill", {"width": 117}); b.write_3mf(path)`.

Deliver to ~/Downloads/<project>/ (Collin's rule): the .3mf, the per-colour STLs, a render, and the numbers
from `--slice` plus the AMS change estimate in `stats`.

## Catalogue

Shapes (`text2print/shapes.py`): tray, platter, dish (round), coaster, cup, shade — woven; cup, bowl, vase, goblet — fabric;
cup, bowl, vase, goblet, candle (solid bell + taper socket) — droop.
Woven textures (`lattice.PATTERNS`): grid "Weave", twill, kagome, polar "Rose window" (round shapes only),
ripple, selvedge, beat "Moiré", overunder, tartan. Fabric (`fabric.STITCHES`): zigzag, domes "Knit", wave;
options rim_loops and floor = solid | diamonds | lens. Droop (`droop.STYLES`): fringe, swag, curls, unraveled;
options density = sparse | medium | dense, length = short | medium | long. `Build.preview` holds the strands hung
by gravity (display only — strands pass through each other); the print files carry the flat strands.
Halftone (`halftone.py`, texture "halftone" on cup/vase/bowl/goblet): options picture = flames|fade|dots|chevron|waves,
band = 1|2 layers per colour, CLI `--image path` (dark = colour 1). Recipe `halftone.RECIPE`: layer = nozzle max
(0.7 x nozzle), one line 2.5x (0.2/0.4) to 1.75x (0.8) the nozzle, 1 wall, 0 % infill. Colour flips every layer;
rib swing = min(0.5, 0.6 - local wall lean) x line. Stats split grams_part and grams_purge.

## Laws (print-verified; tests enforce the geometric ones)

- Woven: flat full-size first course; no course ever reaches past the one below (Collin rejected fringes,
  lips and a river-stone bottom). Shrinking upward (the pillowed top edge) is fine.
- Nothing square: rounded plan corners, round beads (octagon section, the printed tray's exact bead), round dishes.
- One object, one part per colour. Separate objects per colour leave empty layers and Bambu refuses to slice.
- Colour by direction = one AMS change per course. Over-under and tartan mix colours inside a course: about one
  change per LAYER. Same colour on two slots merges the parts (no changes).
- Rod spans are "overhang walls" to the slicer: the overrides run overhang/bridge at 50 mm/s (stock 10 doubles time).
- Fabric: layer height is geometry; the stitch swing scales with the local radius so the swing/wavelength ratio holds.
- Objects <= 200 mm so the prime tower (216, 216) fits; meshes centred, the writer places by centre.
- Bambu CLI: run `--slice 0 --export-3mf <abs>` from the output dir; never `--outputdir`. CLI numbers are
  single-colour (it ignores part->filament); add `stats.swap_minutes`.
- Droop (UNRAVEL, print-verified July 2026): a strand is a flat ribbon anchored INTO the wall at both ends,
  never an r(theta) displacement. One extrusion wide (swag: 2), <= 4 layers tall, rows a strand + a layer
  apart, strands never intersect in the mesh (`_never_touch`), strand faces on the 1/4-layer grid and wall
  rings on the 3/4-layer grid (coplanar unions leave slivers). Print: overhang slow-down OFF, fan <= 20 %,
  nozzle +5 C — slow strands freeze and don't droop. Verify with a G-code layer plot: one line out, one back.
- Only the 0.4 nozzle is print-verified. 0.2/0.6/0.8 are computed from it — say so.

## Extending

New woven texture: a function `p_name(region, nz, rods)` in `lattice.py` that walks `region.n` courses, uses
`Course(region, nz, i).lines(theta, ...)` / `.curve(...)`, and calls `rods.line(a, b, slot)` / `rods.path(pts, slot)`;
register it in `PATTERNS` (name, blurb, slots, swaps, round_only). New droop style: a `_SPEC` + `STYLES` entry
(and a `HANG` angle range). New fabric stitch: `fabric.STITCHES` +
the `scaled()` displacement. New shape: a `Block`, `Vessel` or `Profiled` entry in `SHAPES` with `Param`s.
Then `python -m text2print thumbs` and `python -m pytest`. Verify visually: render, and screenshot the studio.
