---
name: text2print
description: Textured 3D prints for a Bambu Lab P2S, picked from a catalogue. Use when someone wants a woven, basket, lattice, crosshatch, knit, fabric, zigzag, wave, drooping, fringe, loop, curl, fur, two-colour halftone-picture, vase-mode pleat/flute/twist, voronoi, lithophane, fuzzy-skin or CMYK-picture tray, platter, dish, coaster, cup, lamp shade, bowl, vase, cachepot, liner sleeve, tealight lantern, pendant shade, LED puck lamp, amphora, basket, catch-all or tile; asks to "pick a pattern / pick a shape"; or wants to open or extend the text2print studio. Produces a Bambu Studio project (one object, one part per AMS colour, P2S settings for the chosen nozzle).
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

More CLI: `sampler --nozzle 0.4 --slice` (test plates) · `verify <texture> <nozzle> ok|fail --note` (records a print;
drives the Printed badges and warnings) · `make ... --option zones=3 --option lid=lid`.
Options worth knowing: zones 1-4 + zone_style bands|stripes (fabric, droop; lattice with colour_by=height),
lid=slip|thread|magnets + lid_fit=snug|slip|loose (+ lid_colour) on cup/vase/bowl/dish/tray/custom, purge=lean,
picture/--image for halftone, litho and flat; halftone band=1|2|3, area=full|half|third, silk=silk,
purge_piece=coaster; spiral folds/turn; shell cell (voronoi), noise + fuzzy_bands (fuzzy).

Deliver to ~/Downloads/<project>/ (Collin's rule): the .3mf, the per-colour STLs, a render, and the numbers
from `--slice` plus the AMS change estimate in `stats`.

## Catalogue

Shapes (`text2print/shapes.py`): tray, platter, dish (round), coaster, cup, shade, basket, catchall, hextile, and every round Profiled vessel (bowl, vase, goblet, custom, cachepot, sleeve, amphora via `Profiled.lattice`: ring follows the profile, course-to-course step <= LEAN 0.8 mm/mm both faces, fitted kinds grow outward) — woven; cup, bowl, vase, goblet — fabric;
cup, bowl, vase, goblet, candle (solid bell + taper socket) — droop.
Woven textures (`lattice.PATTERNS`): grid "Weave", twill, kagome, polar "Rose window" (round shapes only),
ripple, selvedge, beat "Moiré", overunder, tartan. Fabric (`fabric.STITCHES`): zigzag, domes "Knit", wave;
options rim_loops and floor = solid | diamonds | lens. Droop (`droop.STYLES`): fringe, swag, curls, unraveled;
options density = sparse | medium | dense, length = short | medium | long. Multi-colour droop: zones 2-4 with
zone_style courses (default for droop; woven-style, colour per strand row via droop.courses() cut-safe row
boundaries + build._course_edges; curls snap to the row grid when aligned) | bands | stripes; course_rows 1-4.
Slicer-verified: 3-colour swag cup = 13 changes in both app and slicer. `Build.preview` holds the strands hung
by gravity (display only — strands pass through each other); the print files carry the flat strands.
Halftone (`halftone.py`, texture "halftone" on cup/vase/bowl/goblet): options picture = flames|fade|dots|chevron|waves,
band = 1|2 layers per colour, CLI `--image path` (dark = colour 1). Recipe `halftone.RECIPE`: layer = nozzle max
(0.7 x nozzle), one line 2.5x (0.2/0.4) to 1.75x (0.8) the nozzle, 1 wall, 0 % infill. Colour flips every layer;
rib swing = min(0.5, 0.6 - local wall lean) x line. Stats split grams_part and grams_purge.
Vase mode (`spiral.py`, family "spiral"): pleats, flutes, twist, lowpoly, pinch print in spiral_mode (one wall,
ONE colour: spiral mode can't change filament); ribs = solid body cut by 0.02 mm radial slits (`_slits`) so vase
mode traces fins. Section clamp 0.9 mm/mm. Shell (`shell.py`): voronoi (scipy cells, CCW-oriented, gable roofs,
`_radial_prism` warp, largest body kept), litho (thick wall, wall_loops >= ceil(3.2/line_w)), fuzzy (layer
ranges with fuzzy_skin + noise per band). Flat (`flat.py`, tile/hextile): litho (white, 0.12 layers) and cmyk
(C, M, Y under white; height-field slabs trimmed by a footprint prism; info["backlit"] = RGBA estimate).
Fur (`droop.fur`): one-layer hair slabs 2 lines wide bridged to a sacrificial shell; Build.preview = trimmed.
Fittings (`fittings.py`): pendant E27 40 mm hole, puck 59x18 collar + cable notch, lantern 41x17 tealight
plinth, cachepot foot ring (pot 3-7 in + 5 mm), candle 23 mm bore + 6 crush ribs; added solids are a separate
floor-colour part (never unioned into fabric walls), cuts are booleans; `NOTES` = safety copy.
Footprints: basket (rounded box + arched handle holes), catchall, hextile, tile. Non-round plans for the
wall families: `shapes.Outline` (contour -> arc-length samples + smoothed normals); the shape's profile() is the
round radius R = perimeter/2pi; build.make warps every part/preview with Outline.warp (angle -> arc length,
r - R -> along the normal; floors scale in from 4 mm inside the wall). Basket handles: build._cut_handles.
Mix (`compose.py`, texture "mix" on cup/vase/bowl/goblet): options {"bands": [{texture, share, slot, slot2?, options}]}
bottom-up; textures from `compose.MIXABLE` (plain + fabric + halftone + droop; never lattice or candle). One layer
height (nozzle standard) and the fabric shell for all bands; each band emits per-layer contours, same-colour runs
become staircase solids, a same-colour neighbour reaches 1/4 layer down and is unioned (never coplanar); droop
strands union into their band's colour (a strand adding a body raises). Any droop band -> droop cooling for the
whole print. Presets in `compose.PRESETS`. A "fuzzy" band adds a fuzzy-skin layer range. Woven bands (`compose.WOVEN` = grid, twill,
ripple, beat, polar; slot = even courses, slot2 = odd): ring centred on the wall (prof - shell/2 +- wall/2, wall
option default 6, LEAN 0.8 per course), odd course count, 45 deg collar below (floor disc if bottom band) and cap
above (none if top band), range wall_loops=rod_lines over the band, woven speeds globally. Slicer-verified counts.

## Laws (print-verified; tests enforce the geometric ones)

- Woven: flat full-size first course; no course ever reaches past the one below (Collin rejected fringes,
  lips and a river-stone bottom). Shrinking upward (the pillowed top edge) is fine.
- Nothing square: rounded plan corners, round beads (octagon section, the printed tray's exact bead), round dishes.
- One object, one part per colour. Separate objects per colour leave empty layers and Bambu refuses to slice.
- Colour by direction = one AMS change per course. Over-under and tartan mix colours inside a course: about one
  change per LAYER. Same colour on two slots merges the parts (no changes).
- Rod spans are "overhang walls" to the slicer: the overrides run overhang/bridge at 50 mm/s (stock 10 doubles time).
- Fabric: layer height is geometry; the stitch swing scales with the local radius so the swing/wavelength ratio holds.
- Objects <= 200 mm so the prime tower (216, 216) fits; meshes centred, the writer places by centre. 3+ colours:
  the tower parks front-right at (BED-50, 20) and the piece shifts left (a deep tower at 216 overflowed the bed).
- Bambu CLI: run `--slice 0 --export-3mf <abs>` from the output dir; never `--outputdir`. Weight is one number
  per filament (comma list): sum it.
- Boolean safety: fabric zigzag walls have coplanar overlapping step faces; a manifold union shreds them. Add
  solids as a separate same-colour part; `meshops.manifold_to_trimesh` (merge vectors, never merge_vertices).
- Lids/knobs/coasters on a shared plate get per-object SOLID settings (walls 3, 20 % infill, 4 top/bottom,
  spiral off) or they inherit the piece's 0 % infill. Thread: 2-start, 3 mm pitch, 1.2 deep, 0.2 clear.
  Magnets 6x2, pocket +0.15 dia / +0.2 deep. Fits snug 0.15 / slip 0.25 / loose 0.40 a side.
- Droop (UNRAVEL, print-verified July 2026): a strand is a flat ribbon anchored INTO the wall at both ends,
  never an r(theta) displacement. One extrusion wide (swag: 2), <= 4 layers tall, rows a strand + a layer
  apart, strands never intersect in the mesh (`_never_touch`), strand faces on the 1/4-layer grid and wall
  rings on the 3/4-layer grid (coplanar unions leave slivers). Print: overhang slow-down OFF, fan <= 20 %,
  nozzle +5 C — slow strands freeze and don't droop. Verify with a G-code layer plot: one line out, one back.
- Bambu CLI facts (verified Oct 14): it honours part->AMS slot when every per-filament list is n_fil long (the
  writer pads them); layer ranges live in Metadata/layer_config_ranges.xml keyed by build position, must include
  layer_height, must NOT include line widths or extruder; the prime tower needs identical ranges on every object.
- Colour zones split on layer boundaries (woven: whole rods by centre, never cut). Lids print top-face down;
  knob press-fits (6.0 hole / 5.85 peg).
- Reliefs (garland, drips, melt) ramp every underside at <= 45 deg; test enforces it.
- Only the 0.4 nozzle is print-verified. 0.2/0.6/0.8 are computed from it — say so.

## Extending

New woven texture: a function `p_name(region, nz, rods)` in `lattice.py` that walks `region.n` courses, uses
`Course(region, nz, i).lines(theta, ...)` / `.curve(...)`, and calls `rods.line(a, b, slot)` / `rods.path(pts, slot)`;
register it in `PATTERNS` (name, blurb, slots, swaps, round_only). New droop style: a `_SPEC` + `STYLES` entry
(and a `HANG` angle range). New fabric stitch: `fabric.STITCHES` +
the `scaled()` displacement. New shape: a `Block`, `Vessel` or `Profiled` entry in `SHAPES` with `Param`s.
Then `python -m text2print thumbs` and `python -m pytest`. Verify visually: render, and screenshot the studio.
