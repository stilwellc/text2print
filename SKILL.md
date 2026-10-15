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
r - R -> along the normal; floors scale in from 4 mm inside the wall). Basket handles: build._cut_handles. Non-round lids: extras.lid_outline (section under the rim -> opening polygon;
plug = opening buffered -clear, LIP_W ring; plate = convex hull of the outline + 0.6). Per-family shape cards:
thumbs.render_family_shapes -> static/thumbs/shape_<key>__<family>.png; the studio shows the picked family's card.
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

## Verification sweeps (Oct 14)
- Geometry: every shape x texture (519) builds watertight at 0.4 full and 0.8 draft (script pattern: loop
  build.compatible pairs, record wt/size/swaps/sec). Found + fixed: catchall+melt zero-volume flap (meshops.drop_flaps).
- Slicer: one texture per shape x family (121) slices with zero CLI errors; app colour-change counts equal the
  slicer's except the lantern (fitting shares layers; build._geom_transitions recounts from geometry, ~1 % off).
- Fittings (plinth, collar, foot ring) get a layer range with 20 % infill + 4 top layers (build._merge_range),
  or they slice hollow under the wall families' 0 % / no-top settings.
- Filament estimate vs slicer: within ~5 % for most families; vase mode subtracts both caps; fittings count
  shells + 20 % infill.

## Lids = caps of the piece (Oct 14)
build._lid_cap: lid = make(same shape [non-round] or cup at the rim radius [round], same texture/colours, height
8-14 mm, _raw=True) printed top-face down; the plain lid's plug (extras.plug_of, cut ABOVE the plate) is grafted on
at the rim plane over a column from the cap floor, + knob boss and hole (extras.graft: adds in the floor colour,
carved from other colours). Magnets: pedestal annulus with pockets in its face. Droop/fuzzy/litho -> plain mix cap;
mix -> top band's texture. Woven caps stripe the graft per course. Plate-wide change count (piece + lid) via
_geom_transitions when Build.lid_shares_plate(). Lid objects are multi-part (write_3mf groups extras by name);
a separate -lid.3mf with 2+ colours parks the tower front-right. Woven round openings come from the region
(extras.opening), vase mode from prof - line_w. Slicer-verified: 6 lid projects incl. 2-colour, counts equal.
Lid section options: lid (none|slip|thread|magnets), lid_texture (match|plain|texture key from build.lid_textures()),
lid_colours [hex, hex?], lid_height (5-40 mm, else auto 8-14), lid_knob (knob|button|none), lid_fit. Writer law:
every object carries an object-level extruder = its first part's (a one-part object otherwise prints filament 1).

## Custom pictures and patterns from a prompt (this is where Claude does the work)

The studio covers everything that needs no judgement. When someone asks for something it can't pick from a list,
make it — then hand back a studio link. Four routes, cheapest first:

1. **Words** ("put MOBI LABS on it", "her name in script"): no code. Studio link with
   `picture=text&text=...&font=futura|helvetica|avenir|didot|georgia|rockwell|typewriter|impact|script|chalk&text_layout=center|repeat|stack`
   (+ `text_invert=1`). Works on halftone, wall lithophane (`litho`), `flatlitho`, `cmyk`. Text renders at the wall's
   true proportions; `repeat` tiles a whole number of times around so no word is cut at the seam.
   Preview offline: `python -m text2print picture text "WORDS" --font didot --layout stack --aspect 3 --out x.png`.
2. **Their image**: copy it to `~/.text2print/pictures/<name>.png` (or they upload in the studio) -> `picture=lib:<name>`.
   Dark = the front colour / the thick part of a lithophane. CMYK uses the colours. Never trace someone else's
   artwork or a brand from the web; their own photos and drawings are fine.
3. **A picture from a prompt** ("koi pond", "art-deco sunburst", "a field of poppies"): write
   `~/.text2print/plugins/<name>.py` with `PICTURE = dict(name=..., colour=False)` and `draw(u, v, aspect)`:
   u 0..1 around the wall, v 0..1 up, aspect = width/height in mm — work in `x = u * aspect, y = v` so shapes
   aren't stretched; wrap x at the seam (`(dx + aspect/2) % aspect - aspect/2`). Return darkness 0..1 (1 = front
   colour), or RGB (..., 3) with `colour=True` for CMYK tiles. Build pictures from signed distances (ellipses,
   polygons, smooth unions), hash-seeded placement (deterministic), and keep features >= ~2 mm at print size:
   halftone resolves ~1 rib (~3 mm) across and 2 layers (0.56 mm) up. Example: plugin_examples/koi.py.
4. **A weave or stitch from a prompt** ("herringbone", "basket-weave diamonds", "fish-scale knit"):
   - `WOVEN = dict(name, blurb, slots=2, swaps="course", round_only=False)` + `pattern(region, nz, rods)` using
     the lattice API: `c = Course(region, nz, i)`; `c.lines(theta, pitch=..., keep=lambda j: ..., offset=...)` gives
     clipped rods; `rods.line(_pt(pf, t0, c.z), _pt(pf, t1, c.z), slot)`; curved rods via `rods.path(pts, slot)`.
     Woven laws hold automatically (rods clipped half a bead inside, every course full-width). Colour by course
     parity keeps one change per course. Example: plugin_examples/diamond_weave.py.
   - `STITCH = dict(name, blurb)` + `displace(u, layer, band_layers, band, z_frac)` -> 0..1 of the stitch depth
     (u: 1 per stitch, odd bands shifted half a stitch). It is printed on the knit (domes) proportions. Keep
     layer-to-layer changes gentle. Example: plugin_examples/fish_scales.py.
5. **A shape from a prompt** ("a planter with a rolled rim", "a pebble-shaped dish", "a pen cup"):
   `SHAPE = dict(name, blurb, kind="round"|"outline", params=[(key, label, lo, hi, step, default[, unit])])`
   plus `radius(v, z)` (round: outer radius in mm at height z; it is clamped to lean out <= 0.9 mm/mm) or
   `outline(v)` returning `sdf(x, y)` (negative inside, ~mm distance) + `extent(v)` (outline: straight walls,
   `height` param). Every texture family works on it (wall families map onto outlines; woven builds a rod ring),
   and lids, engraving and pictures too. Examples: plugin_examples/planter.py, pebble_dish.py.
   Keys: woven/stitch -> texture `x_<file stem>`, picture -> `lib:<file stem>`, shape -> `s_<file stem>`.

Always: `python -m text2print plugin check ~/.text2print/plugins/<name>.py` -> builds it on a sample piece,
checks watertight + overhang against the built-in stitches (verdict "ok"), renders a preview PNG — LOOK at the
preview and iterate before handing over. Then `plugin list` (shows load errors) and give the studio link
(`/?shape=vase&texture=x_<name>` or `/?shape=cup&texture=halftone&picture=lib:<name>`). The studio picks plugins
up on the next load — no restart. `python -m text2print plugin new picture|woven|stitch|shape NAME` writes a starter. The studio's "Make a new
one" box runs exactly this flow through a headless `claude -p` (studio/ask.py).

## Designing with Claude (the studio's "Design with Claude" box; also any chat request for a whole piece)

You are the designer: a sentence in, a finished design out. Tools: `python -m text2print catalogue` (all
shapes/textures/options/blends/pictures/fonts/plugins/palette/saved designs), `design check FILE.json` (build,
numbers, preview PNG — look at it), `picture prepare PHOTO --out NAME` (photo -> library picture), `plugin check`.
A design = {"shape", "texture", "params", "nozzle", "colours", "options"} — the studio loads it as-is.

Composing well:
- **Blend, don't stack.** Layered requests use texture "mix" + options.bands (bottom-up). Every band above the
  first gets "blend": {"style": fade | dither (dissolve) | wave | zigzag | scallop | drip | noise (torn), "size":
  mm}. Blends work between plain, fuzzy, zigzag, knit, wave, garland, drips, melt and droop walls; halftone and
  woven bands keep hard joins (collar/cap). Size ~12-30 mm: bigger reads softer. Different colours across a blend
  become a stripe gradient (whole layers, ordered dither) — that's how to "fade blue into cream".
- **Shape the piece to the request:** pick the shape whose silhouette fits, then sizes within the catalogue's ranges.
- **Colour:** palette names map to Bambu filaments the person likely has; 1-2 colours unless they ask for more.
  Watch colour changes in the check: woven `course_group` 2-4, a blend instead of alternating bands, halftone only
  where the picture matters.
- **Pictures** (halftone walls, lithophanes, CMYK tiles, fabric masks): words -> picture "text" + font/layout/
  placement (front for a name, wrap for a pattern, repeat for a motto). A photo -> `picture prepare`: crop to the
  subject (`--crop`, fractions), `--subject` lifts it off a plain background, `--equalize`/`--contrast` for punch;
  halftone wants bold shapes (posterize 2-3 or threshold), lithophanes want smooth tones (equalize, no posterize).
  Look at the result before using it. There's no image generator: "text to image" means you DRAW it as a PICTURE
  plugin (shapes, gradients, symmetry, hash-seeded scatter) — keep features >= ~3 mm on the wall.
- **Build on what they have:** saved designs (catalogue.saved_designs, their links) and plugins are fair game —
  "an autumn version of my tray" means start from that link's parameters.
- Finish with the check's numbers in mind and say any trade-off in the summary (time, purge, colour changes).

### Sliders, budgets, variations, sets, memory, print reviews
- **Sliders on every plugin.** Add `PARAMS = {"key": dict(label=..., lo=..., hi=..., default=..., step=..., unit=...)}`
  (2-4 of the knobs that matter: count, size, density, angle…) and take one more argument: `draw(u, v, aspect, p)`,
  `pattern(region, nz, rods, p)`, `displace(u, layer, band_layers, band, z_frac, p)`, read `p["key"]`. The studio
  shows them as sliders (options `pp_<key>`), so the person tunes without asking again. Example: plugin_examples/koi.py.
- **Budgets** ("under 6 hours", "≤ 50 colour changes", "≤ 120 g"): `design slice FILE.json` gives Bambu Studio's
  real time, grams and colour changes plus `sliced_preview.png` (the paths as printed, front view). Iterate until
  it fits: course_group, fewer halftone layers (band 2-3), smaller piece, blends with stripe gradients only where
  they matter, tower off.
- **Variations** ("3 ideas"): genuinely different directions — texture family, blend style, colour story — each
  checked, each with its preview file named in the reply. **Sets** ("a matching cup, coaster and tray"): one design
  per piece with the same motif, colours and proportions.
- **Reference photos** ("make something like this"): Read it, infer silhouette → shape + params, surface → texture
  family, colours → `palette match PHOTO`.
- **Memory.** `~/.text2print/taste.md` (their likes/dislikes; the studio's "More like this / Not this" buttons
  append to it) and `~/.text2print/knowledge.md` (what printed well or failed on their P2S) are given to every run.
  Append a line to taste.md when they state a lasting preference.
- **Print reviews.** With a photo of a finished print: compare with the design's preview, name what worked and what
  didn't and why, append a dated, specific bullet to knowledge.md, record `verify <texture> 0.4 ok|fail --note …`,
  and return a corrected design.
