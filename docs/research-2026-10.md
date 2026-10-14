# text2print — Texture × Shape Research Report
*Compiled 2026-10-14. Target: Bambu Lab P2S + AMS 2 Pro (4 colours), nozzles 0.2–0.8, pipeline = mesh/3MF → Bambu Studio (no raw gcode).*

**Source-reading notes.** Tags: **[L]** = page loaded and read; **[S]** = claim taken from a search-result snippet only (weaker); **[2nd]** = secondary/aggregator blog. Blocked pages: wiki.bambulab.com returned 402 to WebFetch but loaded via curl with a browser UA; all3dp.com, makerworld.com, printables.com (some), cults3d, 3druck, Fabbaloo/3Dsynth, the ACM X-Hair paper, and bambulab.com/en/p2s pages returned 403 → snippet only. Laput hair PDF 404. Nothing found for "m_editat" or "GCode Zebra"; medium_things surfaced only as one Printables link. No Steve Mould overhang source found. No numbers in this report are invented; where a number is my own arithmetic it is labelled *(calc)*.

---

## 0. The three constraints that shape everything

1. **Spiral vase mode cannot change filament in Bambu Studio.** "Change filament" is greyed out in vase mode; feature request [BambuStudio #1713](https://github.com/bambulab/BambuStudio/issues/1713) is still open [L]; pause-and-swap leaves a gap in the spiral ([forum 62967](https://forum.bambulab.com/t/color-change-in-spiral-vase-mode/62967) [L]); vase mode refuses multi-material objects ([forum 83836](https://forum.bambulab.com/t/change-wall-thickness-in-vase-mode/83836) [S]). → Any AMS-coloured piece must be classic-wall (non-spiral).
2. **Every AMS swap costs ~0.5 g and ~40–70 s.** Bambu's own cube: 153 changes → 83 g wasted (≈0.54 g/change) ([Bambu wiki – reduce waste](https://wiki.bambulab.com/en/software/bambu-studio/reduce-wasting-during-filament-change) [L]); X1C measured 51.8 s/swap stock at 107 mm³ purge, 71.5 s at 400 mm³ ([forum 10037](https://forum.bambulab.com/t/ideas-on-boosting-speed-for-multi-color-printing-with-ams/10037) [L]). P2S AMS 2 Pro claims "10 minutes saved per 100 changes" (~6 s/change, feeding only) ([store P2S](https://us.store.bambulab.com/products/p2s) [L]). Per-layer alternation (halftone) on a 150 mm vase at 0.2 mm = ~749 swaps ≈ ~400 g waste and +7.5–14 h *(calc)*.
3. **Bambu Studio 2.5.3+ added native tools we can target from a 3MF**: structured fuzzy-skin noise (Perlin/Billow/Ridged/Voronoi) + a fuzzy-skin painting tool, and **Color Mixing** (sublayer alternation, Gradient mode with a Z curve in 2.7.1) ([3D Printing Journal on 2.5.3](https://www.3dprintingjournal.com/p/bambu-lab-releases-bambustudio-update) [L]; [Bambu wiki – Color Mixing](https://wiki.bambulab.com/en/bambu-studio/color-mixing) [L]; [release note 2.5.3](https://wiki.bambulab.com/en/software/bambu-studio/release/release-note-2-5-3) [L]).

---

## 1. Techniques not yet covered (25)

Mesh-feasible = producible by sending a mesh/3MF (incl. slicer settings, paint, modifiers, layer pauses) through stock Bambu Studio.

### A. Slicer-native surface textures

| # | Technique | What it is | How made | Parameters / printability | AMS colour potential | Mesh? | Sources |
|---|---|---|---|---|---|---|---|
| T1 | **Structured-noise fuzzy skin, painted** | Coherent noise instead of jitter: Perlin = orange peel, Billow = clumpy cast, Ridged = marble ridges, Voronoi = cell "stone"; painted onto chosen faces so smooth/textured zones alternate | Slicer setting (Bambu Studio 2.5.3: 4 noise types, Displacement/Extrusion/Combined modes, Fuzzy Skin Painting tool; Orca equivalent) | Bambu default point distance 0.8 mm, thickness 0.3 mm. User recipes: 0.2/0.1 or 0.4/0.05 subtle; Voronoi 0.3/0.3 "stone"; 0.3–0.4 deviation @1 mm spacing ≈ brushed/knit; 0.8–1.2 @2–3 mm ≈ rock. Keep off first layer (adhesion). Orca feature size default 1 mm | Strong: paint fuzzy zones a matte colour vs smooth silk bands; fuzzy "takes colour-shift filament to another level" | **YES** (paint persists in 3MF) | [3DPJ 2.5.3](https://www.3dprintingjournal.com/p/bambu-lab-releases-bambustudio-update) [L]; [Orca fuzzy skin wiki](https://www.orcaslicer.com/wiki/print_settings/others/others_settings_fuzzy_skin) [L]; [Bambu forum 249218](https://forum.bambulab.com/t/new-fuzzy-skin-textures-for-2-5-3/249218) [L] |
| T2 | **Ripple fuzzy skin** | Regular sine ripple per layer with phase offset → knit/corrugated cloth | Orca setting (ripples/layer default 1, offset 20%, layers between offset 1). Not listed in Bambu 2.5.3 notes → appears Orca-only | — | Height bands + phase shift = chevrons | **PARTIAL** (model as fine flutes for Bambu) | [Orca wiki](https://www.orcaslicer.com/wiki/print_settings/others/others_settings_fuzzy_skin) [L]; [Orca PR 7678](https://github.com/OrcaSlicer/OrcaSlicer/pull/7678) [S] |
| T3 | **Flow-modulated skin / velocity painting** | Wall stays put, bead swells/thins → image as gloss/thickness "tattoo" | Bambu/Orca "Extrusion" fuzzy mode (noise only; Orca warns keep 70–125% of nozzle); image-driven = Velocity Painting post-processor (speed→pressure lag) or nozzleboss Blender add-on (vertex-paint flow/speed, tool by vertex colour) | Best on single-wall hollow objects; translucent filament | nozzleboss can switch tool by vertex colour | Noise **YES** / image **NO** | [Hackaday velocity painting](https://hackaday.com/2018/07/05/tattoo-your-3d-prints-with-velocity-painting/) [S]; [nozzleboss GitHub](https://github.com/Heinz-Loepmeier/nozzleboss) [L] |

### B. Vase-mode geometry textures

| # | Technique | What it is | How made | Parameters | Colour | Mesh? | Sources |
|---|---|---|---|---|---|---|---|
| T4 | **FullControl ripple texture** | Spiral path wiggles in XY with a very wide flat bead → fabric-like strong wall | G-code (FullControl demo) | Extrusion width 2.5× nozzle, layer 0.6× nozzle (0.4 → 1.0 mm × 0.24 mm) | Silk / dual-colour silk shimmer | **PARTIAL** (mesh flutes at pitch ≈1–2× line width + wide outer wall) | [FullControl GitHub](https://github.com/FullControlXYZ/fullcontrol) [S]; [PrusaSlicer #8925](https://github.com/prusa3d/PrusaSlicer/issues/8925) [S] |
| T5 | **Pleats / flutes / twist / low-poly facets** | Cross-section geometry is the texture; printed as one seamless spiral | Geometry + spiral vase | Wall slightly > line width (0.5 mm on 0.4); 20–30 mm/s for cooling, ~40 mm/s crisp facets; low-poly twist fine at 0.2 mm, 3 bottom layers; "Velvet Petal Vase" 0.4 nozzle, Matte PLA, 0.28 mm | No AMS swaps in vase mode → use dual/tri-colour silk (T14) | **YES** | [Pleated spiral vase](https://www.printables.com/model/337080-pleated-spiral-vase/collections) [S]; [printpal vase generator](https://printpal.io/tools/vase-generator) [S]; [low-poly twist](https://www.printables.com/model/718782-low-poly-spiral-twist-vase-wider) [S]; [Velvet Petal Vase](https://makerworld.com/en/models/1065149-velvet-petal-vase) [S] |
| T6 | **Slit trick: hidden ribs / double wall in vase mode** | ~zero-width slits make the single spiral fold in and back → internal ribs or double walls; visible as shadow lines through translucent plastic | Geometry + "slice gap closing radius" = 0 | Slit ~0.0001–0.001 mm (or ½ nozzle so sides fuse into one rib); double wall = wall 2× perimeter width; example used 0.8 mm line on 0.4 nozzle; slits stop above bottom layers | Translucent PETG glow with dark rib lines | **YES** (verify Bambu's gap-closing setting) | [vorpal.se unconventional vase mode](https://vorpal.se/posts/2025/jun/23/3d-printing-with-unconventional-vase-mode/) [L]; [Hackaday](https://hackaday.com/2022/05/15/3d-printing-hack-leverages-vase-mode-structurally/) [S] |
| T7 | **Non-planar Z-wave vase** | Spiral rises and falls → layer lines themselves are waves | G-code only (Grasshopper/FullControl) | — | — | **NO** (fake with sine-wavy mesh surface; layers stay flat) | [Cura #9889](https://github.com/Ultimaker/Cura/issues/9889) [S]; [Wavy container](https://www.printables.com/model/70899-wavy-container-vase-mode-parametric) [403, S] |

### C. Hair, fur, bristles

| # | Technique | What it is | How made | Parameters | Colour | Mesh? | Sources |
|---|---|---|---|---|---|---|---|
| T8 | **Bridge-strand mane (Cepin "Furry Lion")** | Hundreds of bridged strands between core and a sacrificial outer shell; cut shell, comb into hair | Geometry: each hair = thin slab the slicer bridges | Element 0.2 mm tall × 0.8 mm wide (2 lines out/back, 0.4 nozzle @0.2); faster bridge speed, lower bridge flow, cooler nozzle, 100% fan; style with minimal heat + hands | Mane band in a different filament by height/paint | **YES** — the mesh-only route to fur; natural extension of our Droop family | [toms3d How to Furry](https://toms3d.org/2017/02/07/how-to-furry/) [L]; [3dwithus hairy prints](https://3dwithus.com/hairy-3d-prints) [S] |
| T9 | **Stringing hair (CMU Furbrication, X-Hair, Cilllia)** | Deposit a dot, pull away → ooze stretches into free hair | G-code (head/bed motions; X-Hair "two-step suspend printing") | — | — | **NO** | [CMU 3D printed hair](https://www.figlab.com/research/2015/3d-printed-hair) [L]; [X-Hair UIST'24](https://dl.acm.org/doi/fullHtml/10.1145/3654777.3676360) [403, S]; [Cilllia](https://dl.acm.org/doi/10.1145/2858036.2858257) [S] |

### D. Light and transmission

| # | Technique | What it is | How made | Parameters | Colour | Mesh? | Sources |
|---|---|---|---|---|---|---|---|
| T10 | **Lithophane shades (mono & CMYK)** | Wall thickness encodes an image visible when backlit | Geometry (thickness heightmap) | ~0.8 mm min → 2–3 mm max thickness; 0.1 mm layers (0.15 first); 100% infill; print upright, seam on image edge. CMYK: 0.08–0.12 mm layers, 0.2/0.4 nozzle | Bambu CMYK bundle: Cyan #0086D6, Magenta #EC008C, Yellow #F4EE2A + Jade White = exactly 4 AMS slots | **YES** | [makersphere lithophane lamp](https://www.themakersphere.com/3d-printed-lithophane-lamp/) [S]; [Bambu forum CMYK bundle](https://forum.bambulab.com/t/color-lithophanes-check-out-our-new-cmyk-filament-bundle/12397) [S]; [Bambu wiki CMYK](https://wiki.bambulab.com/en/knowledge-sharing/CMYK-color-lithophane-printing-instructions) [S] |
| T11 | **HueForge filament painting** | Stacked translucent layers blend into a painterly image using swap-by-layer only | Geometry relief + per-layer swap schedule using each filament's Transmission Distance (TD: ~1.5 mm opaque, ~10 mm translucent) | — | 4 automatic swaps fit AMS exactly | **YES** | [Polymaker wiki HueForge](https://wiki.polymaker.com/the-basics/applications/hueforge-painting) [S]; [Snapmaker HueForge](https://www.snapmaker.com/blog/hueforge-3d-printing/) [S] |
| T12 | **Height bands / Color Mixing gradient** | Stripes or ombré up a vessel; at high swap density bands dissolve to ombré (Wontek "Gradient") | Height Range Modifiers per band, or Bambu Studio Color Mixing (Normal 2–3 filaments; Gradient 2 filaments along a Z curve) | Vertical walls only; 0.12 mm base / 0.2 mm mixed layer; same material only; MakerWorld rejects mixed-filament 3MFs | Core 4-colour technique; gradient is very purge-heavy on single nozzle | **YES** | [Bambu wiki Color Mixing](https://wiki.bambulab.com/en/bambu-studio/color-mixing) [L]; [Yanko on Wontek](https://www.yankodesign.com/2026/09/14/the-3d-printed-vases-that-actually-look-hand-woven/) [L]; [bambuhub](https://bambuhub.net/guides/multi-color-techniques) [S] |
| T13 | **Translucent PETG glow shade** | Thin glowing wall; ribs/fuzz/matte diffuse and hide LEDs | Geometry + material | Wall 0.45–0.5 mm small shades, 0.7–0.8 mm for >200 mm tall; fan 0–20% on clear PETG (more cooling traps scattering micro-voids) | Tinted translucent bands = stained glass rings | **YES** | [lumaform3d](https://www.lumaform3d.com/vase-mode-3d-printing) [S]; [spoolharbo PETG](https://spoolharbo.com/clear-translucent-petg-print-guide/) [S] |

### E. Material-driven (the filament is the pattern)

| # | Technique | What it is | Notes | Colour | Mesh? | Sources |
|---|---|---|---|---|---|---|
| T14 | **Coextruded dual/tri-colour silk** | 2–3 colours side by side in one strand; visible colour depends on wall facing direction | Best in vase mode (spiral always same direction). On ribbed/twisted surfaces "the two colours stack the other way round" at direction changes → **a zero-swap face-dependent halftone** | One slot = 2–3 colours | **YES** | [CNC Kitchen dichromatic](https://www.cnckitchen.com/blog/dual-color-dichromatic-3d-printing-filament) [L]; [Bambu PLA Silk Multi](https://us.store.bambulab.com/products/pla-silk-multi-color) [S] |
| T15 | **Marble/speckle strata** | Particle-filled PLA; at 0.25–0.3 mm layers lines read as sedimentary banding | Alternate marble/plain bands for strata | — | **YES** | [facfox marble](https://facfox.com/docs/kb/marble-pla-marble-filament-brands-compared) [S]; [Bambu PLA Marble](https://us.store.bambulab.com/products/pla-marble) [S] |
| T16 | **Wood-fill temperature grain** | Wood fill darkens hotter → growth rings | M104 per layer ~175 °C (light) → 250 °C (dark); GcodeWoodener; Bambu Studio allows custom gcode at chosen layers (a handful by hand) | — | **PARTIAL** | [GcodeWoodener](https://github.com/manticorp/GcodeWoodener) [S]; [tridimake](https://www.tridimake.com/2012/10/shades-of-brown-with-wood-filament-via.html) [S] |

### F. Open / structural

| # | Technique | What it is | Parameters | Colour | Mesh? | Sources |
|---|---|---|---|---|---|---|
| T17 | **Visible-infill shade** | 0 perimeters, 0 solid layers → gyroid labyrinth is the skin | Gyroid 20%, semi-translucent PETG | Height bands show through depth | **YES** in Prusa/Orca; *unverified* whether Bambu Studio allows 0 wall loops — else model a TPMS mesh | [Printables visible gyroid shade](https://www.printables.com/model/80966-lamp-shade-with-visible-gyroid-infill) [S]; [Thingiverse 4659950](https://www.thingiverse.com/thing:4659950) [S] |
| T18 | **Voronoi / perforated shell** | Cellular web of openings | Struts ≥ 2 mm; ~0.6 mm wall; 0.2–0.3 mm layers at 45–60 mm/s; z-hop ~0.8 mm to avoid snapping webs | Paint cells | **YES** | [MakerWorld voronoi shade](https://makerworld.com/en/models/547681-voronoi-pattern-lampshade) [S]; [Printables voronoi vase](https://www.printables.com/model/47025-voronoi-vase) [S] |
| T19 | **Bridged lace / BridgeSlicer / Weave Lamp** | Holes come from toolpath bridges; or one bead climbing in a wave welding to itself (~80% open) | Re-slicing flattens it | — | **NO** (bridge slabs à la T8 get partway) | [CAADRIA 2023 BridgeSlicer](https://papers.cumincad.org/data/works/att/caadria2023_319.pdf) [S]; [Tarazi Studio](https://www.tarazistudio.com/bridgeslicer-a-creative-slicer-for-3d-printing-perforated-shells-2023/) [S]; [Weave-Trial](https://github.com/TTVV-7/Weave-Trial) [S] |
| T20 | **Print-in-place chainmail / dragon-scale fabric** | Interlinked hex scales that drape like cloth; can wrap a vessel | Hex side 7 mm; pitch 13 mm horizontal, 6.5 mm offset × 11 mm vertical (closer fuses); 0.2 mm layers, 2 walls; snap variants: +0.8 mm gap best of +0.2…+0.8 | Paint alternating scales | **YES** | [MakerWorld dragon scale](https://makerworld.com/en/models/134101-dragon-scale-hexagonal-chainmail-print-in-place) [S]; [Printables dragon scale fabric](https://www.printables.com/model/851001-dragon-scale-fabric) [S] |
| T21 | **Print-on-tulle** | Plastic motifs fused through real tulle/lace | Pause after 2–3 layers, clamp fabric taut, resume | Fabric = a 5th colour | **YES** (Add Pause in 3MF) | [Make: print on tulle](https://makezine.com/projects/how-to-3d-print-on-tulle-net-or-lace-fabrics/) [L] |

### G. Overhang / top-surface toolpaths

| # | Technique | Notes | Mesh? | Sources |
|---|---|---|---|---|
| T22 | **Arc / wave overhangs** | 90° overhangs filled with concentric arcs; decorative crystal-fan underside. ~2–5 mm/s PLA, heavy cooling; wave overhangs ~2 mm/s, 30–48% less sag than arcs. Orca's "make overhang printable" only cones (45–60°) | **NO** | [CNC Kitchen arc overhangs](https://www.cnckitchen.com/blog/arc-overhangs-a-new-way-of-printing-without-supports) [L]; [arc-overhang](https://github.com/stmcculloch/arc-overhang) [S]; [VoxelMatters wave toolpaths](https://www.voxelmatters.com/wave-based-toolpaths-enable-support-free-horizontal-overhangs-in-extrusion-3d-printing/) [L] |
| T23 | **Z anti-aliasing / non-planar ironing** | Z varies within a layer on top surfaces ≤ ~25°; Ra ~80→25 µm; "0.2 with ZAA ≈ 0.1 mm". In Orca 2.4.0 alpha ("Z Contouring") and Bambu forks, not stock Bambu Studio | **NO** (stock) | [CNC Kitchen ZAA](https://www.cnckitchen.com/blog/anti-aliasing-for-fdm-3d-printing-is-finally-here-micro-non-planar-printing) [L]; [NonPlanarIroning](https://github.com/TengerTechnologies/NonPlanarIroning) [L] |
| T24 | **Brick layers** | Alternate perimeters shifted ½ layer; subtle masonry look on translucent wall. Script didn't support Bambu at time of writing | **NO** | [Bricklayers](https://github.com/TengerTechnologies/Bricklayers) [S]; [Orca PR 8181](https://github.com/OrcaSlicer/OrcaSlicer/pull/8181) [S] |

### H. Geometry-baked

| # | Technique | Notes | Mesh? | Sources |
|---|---|---|---|---|
| T25 | **Displacement relief, knurl, emboss, seam-as-spine** | Image/procedural displacement (knurl, diamond, stone) baked into mesh; Bambu Emboss tool for text; an *aligned* seam as a deliberate vertical spine. Paint raised vs recessed in separate filaments | **YES** | [Printago Bambu texture guide](https://printago.io/guides/bambu-studio-texture) [L]; [Blender displacement](https://blenderartists.org/t/displacement-mapping-and-stls-for-3d-printing/642951) [S]; [Obico seam settings](https://www.obico.io/blog/orcaslicer-seam-settings/) [S] |

**Adjacent references** (close to existing families but useful benchmarks): **Wontek** (Warsaw) "loom" vases — colour bands by mid-print PLA swaps with folk motifs (checkerboards, chevrons, eye cutouts) plus deliberate puckers/folds ([Yanko Design, Sep 2026](https://www.yankodesign.com/2026/09/14/the-3d-printed-vases-that-actually-look-hand-woven/) [L]; [Moss & Fog](https://mossandfog.com/wontek-3d-printed-woven-vases/) [S]). **3Dsynth** online vase generator outputs gcode directly with bump-map/extrusion-texture/interference variants ([Fabbaloo](https://www.fabbaloo.com/news/3dsynth-launches-online-vase-generator-that-outputs-direct-gcode) [403, S]). **kowafatcompany Fire Vase**: 0.8–1.2 mm nozzle, vase mode, 0.32 mm layers, <35 mm/s ([Cubee3D](https://www.cubee3d.com/productsforcommunity/fire-vase) [L]; [Creality Cloud](https://www.crealitycloud.com/model-detail/62f77b60b3ddcd4320e01751) [S]) — **could not confirm** whether their two-colour pieces use AMS alternation or dual-colour filament; vase mode + the CNC Kitchen mechanism suggests dual-colour filament is plausible.

---

## 2. Design guides and principles (numbers)

### 2.1 Overhangs
- Unsupported overhang **45–60°** from vertical depending on nozzle/cooling; 360° cooling reaches 75°; 0.25 nozzle may be <45°. Use **chamfers, not fillets**, on bed-facing edges ([Prusa KB – Modeling with 3D printing in mind](https://help.prusa3d.com/article/modeling-with-3d-printing-in-mind_164135) [L]).
- Bambu Studio measures overhang as unsupported fraction of line width, bins 10–25/25–50/50–75/75–100%; "slow down for overhangs" on by default ([Bambu wiki](https://wiki.bambulab.com/en/software/bambu-studio/slow-down-for-overhang) [L]). Reported defaults 0/20/15/10 mm/s per bin, overhang fan 100% PLA ([makers101](https://makers101.com/bambu-studio-pla-cooling-settings/) [S, 2nd]).
- In vase mode, short sharp outward ledges print as **drooping loops** as long as layers overlap ([3DWithUs vase-mode designs](https://3dwithus.com/vase-mode-designs-and-settings) [L]) — the documented basis for our Droop family.

### 2.2 Bridges (for mid-air fabric walls)
- Bridge = 100% overhang. **Thick bridges** = round strand of nozzle diameter, "more reliable and can bridge longer distances"; off = short spans only. Line width can't be set in free air — unsupported plastic is always round ([Bambu wiki – Bridge](https://wiki.bambulab.com/en/software/bambu-studio/parameter/bridge) [L]; [Line width](https://wiki.bambulab.com/en/software/bambu-studio/parameter/line-width) [L]). Shorter span sags less — orient the bridge across the short dimension.
- Prusa: lower bridge flow and slow down to pull strand taut ([Prusa KB poor bridging](https://help.prusa3d.com/article/poor-bridging_1802) [L]).
- PLA span heuristics: 5–10 mm near-perfect, 20–30 mm acceptable, 50 mm+ risky ([3dmag](https://www.3dmag.com/3d-wikipedia/3d-printing-bridging-settings-materials-and-limits/) [S, 2nd]). PETG sags more and is often limited to ~30–80% fan ([Creality blog](https://www.creality.com/blog/3d-printing-bridging) [S]).
- **Rule for us:** keep unsupported strands ≲20–30 mm in PLA, much shorter in PETG; test per filament.

### 2.3 Layer height & line width vs nozzle
| Nozzle | Bambu layer range (20–70%) | Prusa cap (80%) | Bambu line width (0.75–1.5×) |
|---|---|---|---|
| 0.2 | 0.04–0.14 | 0.16 | 0.15–0.30 |
| 0.4 | 0.08–0.28 | 0.32 | 0.30–0.60 |
| 0.6 | 0.12–0.42 | 0.48 | 0.45–0.90 |
| 0.8 | 0.16–0.56 | 0.64 | 0.60–1.20 |
Sources: [Bambu wiki layer height](https://wiki.bambulab.com/en/software/bambu-studio/layer-height) [L] (first layer = nozzle × 50%); [Bambu wiki line width](https://wiki.bambulab.com/en/software/bambu-studio/parameter/line-width) [L]; [Prusa KB layers & perimeters](https://help.prusa3d.com/article/layers-and-perimeters_1748) [L]. Line-width column is my *(calc)* from Bambu's 0.75–1.5× rule.
- Bambu vase mode reportedly won't go above ~0.9 mm wall on 0.4 nozzle; 0.8 mm reported OK on X1C ([forum 5039](https://forum.bambulab.com/t/how-to-improve-wall-thickness-in-spiral-vase-mode/5039) [L]). Bambu PLA Basic max volumetric ~21 mm³/s ([bambureviews calc](https://bambureviews.com/bambu-calculator/) [S]).
- Prusa: bigger nozzle at same layer height in vase mode = thicker wall, nearly same time; recommends 0.6 nozzle for pots/vases ([Prusa nozzle blog](https://blog.prusa3d.com/everything-about-nozzles-with-a-different-diameter_8344/) [L]).

### 2.4 Designing for spiral vase mode
- Forces 1 wall, 0 top layers, 0% infill; model as **solid**; multiple vase objects need Print sequence = By object; **Smooth Spiral** (v1.9+) arc-fits layer transitions, threshold % of nozzle, best on smooth forms ([Bambu wiki spiral vase](https://wiki.bambulab.com/en/software/bambu-studio/spiral-vase) [L]).
- Strength: wider line / bigger nozzle; corrugations ("added lots of stiffness"; CAD corrugations "strong, stiff, efficient") ([3DQue vase mode functional](https://docs.3dque.com/docs/cool-stuff/vase-mode/) [L]); slit-rib trick (T6).
- Base: e.g. 0.2 mm layers + 0.6 mm wall → 3 bottom layers; very large thin boxes buckle ([DrLex vase-mode box](https://github.com/DrLex0/print3d-customizable-vase-mode-box) [L]). Wider lines = deeper colour, less translucency; thin = translucent for shades ([3DWithUs](https://3dwithus.com/vase-mode-designs-and-settings) [L]).

### 2.5 Watertightness
- **Prusa test data:** "one perimeter in vase mode was sufficient to become waterproof for all tested materials"; leaks come from **seams** and perimeter–infill junctions. Normal-mode minimum perimeters: PLA 4, PETG 4 (ABS/ASA/PC/PP/CPE 2). Lower layers seal better (0.15 mm good compromise); flow 105–110% helps ([Prusa blog watertight PT1](https://blog.prusa3d.com/watertight-3d-printing-pt1-vases-cups-and-other-open-models_48949/) [L]).
- Bambu: flow ratio +0.02–0.05, wider line, lower layer, **Concentric bottom pattern**, 2–4 walls; only reduces risk ([Bambu wiki reduce vase leaking](https://wiki.bambulab.com/en/filament/reduce-vase-leaking-guide) [L]).
- Prusa KB: 3–4 perimeters, nozzle +5–10 °C, extrusion +5–10%, layers ≤60–65% of nozzle, avoid nubs on wall ([Prusa KB watertight](https://help.prusa3d.com/article/watertight-prints_112324) [L]).
- **Implication:** woven/mesh/fringe walls are never watertight → offer a glass-liner sleeve mode (§3).

### 2.6 Food safety
- Grooves trap bacteria; pigments unknown; brass nozzles not food-safe; only certified epoxy coatings help; "We do not recommend using 3d-prints as food-containers" ([Prusa KB food-safe](https://help.prusa3d.com/article/food-safe-fdm-printing_112313) [L]). Label fruit/bread pieces "decorative / whole fruit / napkin liner".

### 2.7 Heat (candles, lamps)
| Material | Tg | HDT @0.45 MPa | Source |
|---|---|---|---|
| Bambu PLA Matte | 61 °C | 58 °C | [TDS PDF](https://store.bblcdn.com/s7/default/5b061f2feeac4ba88f355a33248bbda7/Bambu_PLA_Matte_Technical_Data_Sheet.pdf) [L] |
| Bambu PETG Basic | 69 °C | 71 °C | [TDS PDF](https://store.bblcdn.com/s1/default/cb94589bf7994fdcbfa833badefae9cd/Bambu_PETG_Basic_Technical_Data_Sheet.pdf) [L] |
- PLA shade + incandescent passed 45 °C fast and **deformed after 2–3 h**; LED never did → "LED lights only" ([FacFox safety test](https://facfox.com/docs/kb/3d-printed-lamp-shades-ideas-and-safety-test-led-vs-incandescent-bulbs) [L]). Keep ≥30 mm bulb-to-shade, don't fully enclose ([QIDI](https://qidi3d.com/blogs/print-lab/translucent-filaments-heat-safe-lampshades) [S]); ≤10 W LED ([x3dstudios](https://x3dstudios.com/blog/3d-printed-lamps-guide) [S]).
- A tealight emits ~32 W ([Wikipedia Tealight](https://en.wikipedia.org/wiki/Tealight) [L]). Use LED tealights or a glass/ceramic cup ([stlDenise3D](https://stldenise3d.com/how-safe-are-3d-printed-candle-holders/) [S]). **No authoritative flame-to-plastic distance found.**

### 2.8 Palettes for multicolour textured pieces
- **Neutral base + one accent** is "the most consistently successful"; complementary pairs = one dominant + small accent; analogous = calm/timeless; finish contrast (silk on matte) works as well as hue contrast ([OzFDM colour theory](https://ozfdm.com.au/blogs/knowledge-base/colour-theory-for-3d-printing-choosing-palettes-that-work) [L]).
- Analogous with enough contrast to separate, or grey/silver base + standout accents; use Adobe Color/Coolors/Color Hunt ([MatterHackers colour planning](https://www.matterhackers.com/articles/quick-tip-color-planning) [L]).
- Bambu Color Mixing: CMYW or RYBW bases; "even 10–20% of a dark colour can overpower a mix"; 2-filament mixes cleaner than 3 ([Bambu wiki Color Mixing](https://wiki.bambulab.com/en/bambu-studio/color-mixing) [L]).
- Translucents (TD ~5–8) blend layer stacks; opaque gives "zebra stripes" on shallow slopes ([Snapmaker Full Spectrum guide](https://www.snapmaker.com/blog/getting-started-with-full-spectrum-slicing/) [L]). Sunset = red→orange→yellow; analogous palettes hide residual mixing so need less purge ([Amolen](https://www.amolen.com/blogs/blog/multi-color-filament-printing-guide) [S]).
- **For halftone ribs:** pick a pair with a large *lightness* gap; check thin-wall show-through (TD) ([filascope TD](https://filascope.com/guides/what-is-hueforge-td) [S]).

---

## 3. Objects / shapes to add

Note: MakerWorld/Printables returned 403 to direct fetch; counts below are from search snippets and may be stale.

### 3.1 Standard interfaces ("fittings") to build once
| Interface | Value | Source |
|---|---|---|
| E26/E27 shade ring | 40 mm thread; ring OD 56–58 mm, ~14 mm tall | [lampholders.eu](https://www.lampholders.eu/en-us/shade-ring-for-lampholder-e27-and-e26-in-thermosetting/) [S]; [Sinolec](https://sinolec.co.uk/en/lamp-accessories/1211192-e27-lamp-holder-ring.html) [S] |
| Shade collar hole | ~40 mm (MakerWorld "40 mm negative circle for E27"); IKEA SEKOND snippet says ≤38 mm | [Swirl lamp](https://makerworld.com/en/models/1034574-the-swirl-lamp-e27) [S]; [Instructables SEKOND](https://www.instructables.com/IKEA-SEKOND-Pendant-Moon-Lamp/) [S] |
| Lamp-base socket bore | 40–41 mm | [Foxwood E27 base 2.0](https://makerworld.com/en/models/1258609-e27-base-for-lamp-2-0-by-foxwood) [S] |
| Bambu LED Lamp Kit 001 puck | Ø59 × 18 mm, 5 V 3 W | [3DJake](https://www.3djake.com/bambu-lab/led-lamp-kit-001) [S]; [Bambu store](https://us.store.bambulab.com/products/led-lamp-kit-001) [S] |
| Tealight | 38 × 16 mm → pocket 40–42 mm; Bambu LED tealight 37.2 × 36.6 mm | [Wikipedia](https://en.wikipedia.org/wiki/Tealight) [L]; [Bambu LED tealight](https://eu.store.bambulab.com/en-se/products/led-flame-tea-light-candle-set-warm-yellow) [S] |
| Taper candle | 7/8 in (~22 mm) → bore 22.5–23 mm, slight taper | [Floral Society](https://www.thefloralsociety.com/blogs/candle-holders/which-candle-holder-should-i-pair-with-my-candles) [S] |
| Nursery pots | 4 in = 4 × 3.5 in tall; 6 in = 6 × 5.75 in → cachepot ID ~106 / ~157 mm *(calc + clearance)* | [Greenhouse Megastore](https://www.greenhousemegastore.com/products/standard-round-pots) [S] |
| Propagation test tube | ≤17 mm Ø | [MakerWorld test-tube holder](https://makerworld.com/en/models/898855-test-tube-holder-for-plant-propagation-by-cutting) [S] |

### 3.2 Object table
Textures: **W** woven, **M** mesh fabric, **F** fringe/droop, **H** halftone, **R** reliefs, **Fz** painted fuzzy skin (new), **L** lithophane (new).

| # | Object | Typical size | Suits | Functional constraints | Demand evidence |
|---|---|---|---|---|---|
| 1 | **Pendant shade (E27 collar)** | Ø130–240 × 120–220 | M, F, W, H, L | Flat collar, 40 mm hole, ~3–4 mm solid to r≈35; ≥20–30 mm from bulb; LED ≤10 W | [Janberry Lamp Shade 2.0](https://makerworld.com/en/models/1009776-lamp-shade-2-0-spiral-vase) [S]; [HEMMA shade](https://makerworld.com/en/models/604216-lampshade-compatible-with-ikea-hemma-cord-set) [S]; [Printables Vase Hack Lamp Shade Toolkit](https://www.printables.com/model/894617-vase-hack-lamp-shade-toolkit) [S]; [Etsy category](https://www.etsy.com/market/3d_printed_pendant_lamp_shade) [S]; Gantri sells PLA-printed lamps at retail ([VoxelMatters](https://www.voxelmatters.com/online-lighting-gantri-3d-printing/) [S]) |
| 2 | **Table lamp base** (+matching shade) | Base Ø100–140 | H, R, W outside | 40–41 mm bore, cord channel, weighted foot/sand cavity | [Ridges E27 base](https://makerworld.com/en/models/856617-ridges-e27-lamp-base) [S]; [TELA](https://www.printables.com/model/745457-tela-table-lamp-e14-e27-e26-fast-print) [S] |
| 3 | **LED-puck lamp / mushroom lamp** | Puck pocket 59×18; 120–200 tall | M, H, R, F, Fz | Snap pocket, USB-C exit; no mains | [Mdesign mushroom for Kit 001](https://makerworld.com/en/models/375763-mushroom-light-for-led-lamp-kit-001) (377 ratings, S); Etsy voronoi mushroom 1.2k reviews @ $39.99 (S, [category](https://www.etsy.com/market/3d_printed_mushroom_lamp)); [Home Depot PLA mushroom lamp](https://www.homedepot.com/p/JONATHAN-Y-Mushroom-10-in-White-Green-Modern-Classic-Plant-Based-PLA-3D-Printed-Dimmable-LED-Table-Lamp-USA1004A/326153914) [S] |
| 4 | **Cachepot (nursery-pot cover)** | ID ~106 (4 in) / ~157 (6 in); 8 in ≈210 max | W, H, R, M — any texture | No water held; inner foot ring 5–10 mm | [Etsy nursery pot cover](https://www.etsy.com/market/nursery_pot_cover) [S]; ["Wendy" drop pot](https://www.etsy.com/listing/4315481511/wendy-pot-3d-printed-drop-pot-nursery) [S]; craft-fair guides say textured pots outsell plain ([clevercreations](https://clevercreations.org/things-to-3d-print-and-sell/) [S]) |
| 5 | **Planter + drainage + saucer / self-watering** | Ø100–180 | H, R, W outer skin | 3–5 drain holes 6–8 mm; PETG; ≥0.8 mm watertight wall | [Printables self-watering planter](https://www.printables.com/model/650303-self-watering-planter) [S]; [Helical SWP](https://www.printables.com/model/65450-helical-self-watering-planters) [S] |
| 6 | **Vase cover over glass** (jar/bottle/test tube) | Liner OD + 1–2 mm | M, W, F, H | Liner provides watertightness | [MyMiniFactory bottle-vase cover](https://www.myminifactory.com/object/3d-print-bottle-vase-slip-over-cover-to-turn-any-beer-standard-glass-bottle-into-a-modern-vase-175653) [S]; [Printables bottle sleeve 0.33 l](https://www.printables.com/model/35997-bottle-sleeve-033l) [S]; [Core77 Libero Rutilo](https://www.core77.com/posts/61421/These-Sleek-3D-Printed-Vases-Are-Plastic-Bottles-In-Disguise) [S] |
| 7 | **Tealight lantern** | Pocket 40–42; body 60–120 | M, R (drips!), H, W | LED or glass cup | [Printables wavy tealight](https://www.printables.com/model/773572-tea-candle-wave-holder) [S]; [loopy tealight](https://www.printables.com/model/61758-loopy-tealight-holder) [S]; [melting-candle holders](https://www.myminifactory.com/object/3d-print-melting-candle-tea-light-candle-holders-46606) [S] |
| 8 | **Taper candlestick** | Bore 22.5 × 15–20 deep; foot Ø70–100 | R, H | Crush ribs; bobeche suggestion; weighted foot | [MakerWorld taper collection (7 styles)](https://makerworld.com/en/models/500644-taper-candle-holder-collection-7-styles) [S]; [Printables wavy taper](https://www.printables.com/model/784184-wavy-taper-candle-holder) [S]; [Etsy wavy candle holder](https://www.etsy.com/market/wavy_candle_holder) [S] |
| 9 | **Pen cup** | Ø70–85 × 95–110 | H, R, W, Fz | Solid weighted base | Bambu 2025 data names "pen holders" in fastest-growing household category (MakerWorld China) ([3DPI](https://3dprintingindustry.com/news/bambu-lab-data-highlights-sustained-3d-printing-activity-and-creator-growth-on-makerworld-249474/) [S]); [Textured Trio](https://makerworld.com/en/models/1138073-textured-trio-geometric-pen-holders) [S] |
| 10 | Catch-all / valet tray | 150–220 × 100–150 × 25–40 | W, R, H | Smooth floor; felt pocket | [Etsy catch-all](https://www.etsy.com/market/3d_printed_catch_all_tray) [S]; [valet](https://www.etsy.com/market/3d_printed_valet_tray) [S] |
| 11 | Ring / jewellery dish | Ø80–120 × 15–25 | R, H, W | Central ring cone | Snippet: jewellery holders 10.8k–17.9k downloads ([MakerWorld search](https://makerworld.com/en/more-models/ring%20holder%203d%20print%20model%20download)) [S]; [Etsy ring dish](https://www.etsy.com/market/3d_printed_ring_dish) [S] |
| 12 | **Lidded jar / trinket box** | Ø60–100 | R, H, W | Smooth lip band; lid (see §4) | [Threaded jar w/ pattern](https://makerworld.com/en/models/488524-threaded-jar-and-lid-with-stylish-pattern) [S]; [triple-start jar](https://makerworld.com/en/models/547272-container-with-triple-start-threaded-lid) [S]; [Threaded Lid Generator](https://makerworld.com/en/models/2361460-threaded-lid-generator) [S] |
| 13 | Propagation station / bud vase | 1–10 tubes ≤17 mm | M, H, R | Tube pockets 17–18, optional tilt | [Elegant propagation station](https://makerworld.com/en/models/1181568-elegant-plant-propagation-station) [S]; [Printables hex station](https://www.printables.com/model/1013870-hexagon-propagation-station) [S] |
| 14 | Fruit bowl (footed) | Ø200–240 × 70–100 | W, M, R | Whole fruit only; stiffness | [Etsy Large Woven Bowl 8×3 in](https://www.etsy.com/listing/1582045934/large-woven-bowl-woven-basket-wicker) [S]; [spiral fruit bowl collection](https://makerworld.com/en/models/1919520-spiral-fruit-bowl-collection) [S] |
| 15 | Storage / cable basket (rect/oval, handles) | 150–240 × 100–150 | W, M | Non-round footprint; handles | [MakerWorld woven organizers collection (42 models)](https://makerworld.com/en/collections/23284792-woven-organizers-and-baskets) [S]; [customizable woven basket](https://makerworld.com/en/models/508654-woven-basket-customizable) [S] |
| 16 | Incense holder | Boat 150–250 or cone 60–80 | R, H | Stick hole 2–3 mm; ash lip | [Samurai holder](https://makerworld.com/en/models/591671-samurai-incense-holder) (13.5k views, S) |
| 17 | Hanging planter ("macramé" fringe) | Ø100–150 | F, W, M | 3–4 cord eyelets 2–3 mm; drip tray / liner | [Westbound hanging planter](https://makerworld.com/en/models/1427609-hanging-planter) [S]; [Etsy printed macramé hanger](https://www.etsy.com/listing/774295734/macrame-plant-hanger-3d-printed-hanging) [S] |
| 18 | Hex wall tile / wall pocket planter | Hex 100–150 flat-to-flat | H, R, W, L | Keyhole/cleat; inter-tile pegs | [Printables hex wall pot (1,013 dl, S)](https://www.printables.com/model/588746-hexagonal-wall-plant-pot); [MakerWorld hex panels](https://makerworld.com/en/models/1384619-hexagon-wall-panels-modular) [S] |
| 19 | Christmas ornament | Ø50–80, 5–16 g | M, H, R, F | Separate cap + loop | [Spiral baubles 5–8 g](https://makerworld.com/en/models/892307-spiral-christmas-ornaments-baubles-in-vase-mode) [S]; [vase-mode ornaments](https://makerworld.com/en/models/74753-vase-mode-christmas-ornaments) [S] |
| 20 | Coaster set + holder | Ø90–100; caddy for 4–6 | R, H, W | Flat top, cork pocket | [Coasters and Holder 7.2k dl, 4.9★/324 (S)](https://makerworld.com/en/models/189325-coasters-and-holder) |
| 21 | Utensil crock | Ø110–130 × 150–180 | H, R, W | Heavy base; PETG | [Etsy crock](https://www.etsy.com/listing/1402595498/unique-kitchen-utensil-holder-and) [S] |
| 22 | Napkin rings | ~42 ID × 52 OD × 40 | W, R, F | Batch plate | [Linen Loops](https://makerworld.com/en/models/836372-linen-loops-customizable-napkin-rings) [S] |
| — | Amphora, pinch/ginkgo vase | — | H, M | Fold into vase as **profile presets + cross-section morphs** | [Ginkgo Breeze Vase](https://makerworld.com/en/models/3359463-ginkgo-breeze-vase) [S]; no amphora-specific evidence found |
| — | Bookends, mirror frame, toothbrush holder | — | — | Low fit (slabs / CNC-dominated / hygiene) — skip | [Etsy bookends](https://www.etsy.com/market/3d_printed_bookends) [S] |

**Architecture implication:** most new demand = existing body + a standard fitting. A reusable fittings layer (collar, bore, puck pocket, tealight pocket, taper bore, pot clearance, glass-liner offset, tube pockets, lid lip) unlocks ~12 shapes. Also needed: **texture-free masked zones** (rims, collars, lid lands, dish floors) and **non-round footprints** (rect/oval/hex).

---

## 4. Lids

### 4.1 Clearances
| Source | Fit | Value |
|---|---|---|
| [Prusa KB](https://help.prusa3d.com/article/modeling-with-3d-printing-in-mind_164135) [L] | Accuracy / moving parts | ≥0.2 mm accuracy; moving parts ≥0.3 mm; use elephant-foot comp |
| [UF Marston Makerspace](https://makerspace.uflib.ufl.edu/3dprocess/recommended-software-for-3d-printing/designing-for-3d-printing-tolerances-on-the-mk4-and-xl) [L] | Separate parts | 0.20 snug · 0.25 sliding · **0.40 loose "covers"** |
| [Rigid Prints (Bambu A1/P1S)](https://www.rigidprints.co.uk/design-guide/tolerances-and-fits) [L] | Per face | press −0.05 · light press +0.05 · **running +0.15 ("lids that close cleanly")** · loose +0.3 · generous +0.5; XY PLA ±0.2, PETG ±0.3; >100 mm ±0.3% PLA / ±0.4% PETG |
| [Hubs enclosures](https://www.hubs.com/knowledge-base/enclosure-design-3d-printing-step-step-guide/) [L] | Base + lid | wall ≥2 mm; lips/lugs ≥5 mm wide to align |
| [Hubs snap-fits](https://www.hubs.com/knowledge-base/how-design-snap-fit-joints-3d-printing/) [L] | Snap | FDM clearance 0.5 mm; cantilever ≥1 mm, root fillet ≥0.5× thickness |
| [DrLex vase-mode box](https://github.com/DrLex0/print3d-customizable-vase-mode-box) [L] | Vase-mode lid | Grip/lead-in lip; **round boxes need more tolerance than rectangular**; reprint only the lid |
**Recommended start (PLA, tuned Bambu):** 0.15–0.25 mm/side friction, 0.3–0.4 mm/side lift-off; more for PETG, round/organic outlines, and large diameters (a 150 mm rim alone varies ±0.45 mm at ±0.3% *(calc)*). **Lip depth: no numeric source found** — validate by test ring.

### 4.2 Elephant foot
Bambu: Process → Quality → Precision → Elephant foot compensation; calibrate with a cube: comp = mean X/Y first-layer deviation, e.g. (0.09+0.11)/2 = 0.10 mm ([Bambu wiki](https://wiki.bambulab.com/en/software/bambu-studio/parameter/elephant-foot) [L]). Lids printed rim-down are tightest at the rim; add a ~0.4–0.6 mm 45° chamfer on bed edges. Bottom-opening pockets are "tighter at the opening" ([totalElement](https://totalelement.com/blogs/working-with-neodymium-magnets/magnet-pocket-clearance-for-3d-prints) [L]).

### 4.3 Threads
- rcolyer threads.scad `AugerThread(..., tooth_angle=30, tolerance=0.4)` — **default 0.4 mm tolerance** ([threads-scad](https://github.com/rcolyer/threads-scad) [L]). BOSL2 `$slop` enlarges internal threads by 4×$slop; `bottlecaps.scad` (SPI/Mason) ([BOSL2 threading](https://github.com/revarbat/BOSL2/wiki/threading.scad) [S]).
- Pitch ≥1 mm on 0.4 nozzle; 0.1–0.2 mm radial clearance; axis vertical, layers ≤0.2 ([Meshra](https://meshra.ai/blog/design-3d-printed-threads) [S]).
- **For jars:** coarse 2–4 mm pitch, ≥30° flank (self-supporting), ~0.4 mm diametral clearance, multi-start for quick closing (triple-start "seats in ½ turn": [MakerWorld](https://makerworld.com/en/models/547272-container-with-triple-start-threaded-lid) [S]).

### 4.4 Bayonet / twist-lock
SnapLock: Ø60, 4 tabs @90°, 20° twist + 5° entry clearance, **0.15 mm tolerance offset**, snap columns protrude 0.3–0.5 mm with filleted tip, notch Ø1.2 vs column Ø0.8; **print lid upside-down, 45° tab chamfer self-supports** ([SnapLock](https://github.com/flight505/SnapLock) [L]; [tutorial](https://raw.githubusercontent.com/flight505/SnapLock/main/tutorial.md) [L]).

### 4.5 Magnets
| Pocket | Clearance | Source |
|---|---|---|
| Press-fit | Ø+0.15, depth+0.2 | [totalElement](https://totalelement.com/blogs/working-with-neodymium-magnets/magnet-pocket-clearance-for-3d-prints) [L] |
| Glued | Ø+0.3, depth+0.2 | same |
| Captive (pause) | Ø+0.2, depth+0.2, then 2–4 cover layers | same |
- Bambu Studio: Preview → layer slider → right-click → **Add Pause**; pause occurs at the *start* of that layer — pick the first capping layer ([Printago magnet holes](https://printago.io/guides/bambu-studio-magnet-holes) [L]). 6×2 N52: 0.4 mm skin keeps ~45% pull, 1 mm ~21% ([totalElement embed](https://totalelement.com/blogs/magnet-projects/how-to-embed-magnets-in-3d-prints) [S]). Pause in vase mode breaks the spiral → normal mode only.

### 4.6 Knobs & orientation
45° chamfers not fillets on bed-facing faces ([Prusa KB](https://help.prusa3d.com/article/modeling-with-3d-printing-in-mind_164135) [L]); knob from a top-down lid needs only a ≤45° conical neck. Lid top-face-down gives a bed-smooth visible top; the skirt builds up without overhang.

### 4.7 Test prints
Print a short rim ring + lid ring at 3–5 clearance steps (0.15/0.20/0.25/0.30/0.40 per side) in the real material/nozzle/line width ("one test print of just the mating features costs almost nothing" — [Rigid Prints](https://www.rigidprints.co.uk/design-guide/tolerances-and-fits) [L]). Community gauges: [Printables tolerance test](https://www.printables.com/model/740643-tolerance-test) [S], [S-shaped 0.1–0.4 mm](https://www.printables.com/model/127569-s-shaped-tolerance-test-01-04mm-in-002mm-increment) [S].

---

## 5. Multicolour (up to 4 AMS colours)

### 5.1 Swap economics by pattern
Bambu rule: **swaps per layer = filaments on that layer − 1**; slicer starts each layer with the previous layer's last filament ([Bambu wiki reduce waste](https://wiki.bambulab.com/en/software/bambu-studio/reduce-wasting-during-filament-change) [L]).

| Pattern | Swaps | Cost | Notes |
|---|---|---|---|
| Colour bands by height | 1 per band edge | Very low | Wiki example: 3 changes → 10 g |
| Colour per woven course (N layers each) | 1 per course | Low–med | Thicker courses = fewer swaps |
| Colour per feature (rods vs frame on same layers) | (k−1)/layer | High | Every shared layer pays |
| Circumferential stripes / tartan (all colours on every layer) | up to 3/layer | Very high | Wiki: same part laid sideways = **22× waste, 11× time** |
| Speckle / terrazzo via AMS | many/layer | Prohibitive | Use speckle/marble filament instead *(inference)* |
| Per-layer halftone / Color Mixing | 1+/layer | Highest per mm | Bambu: "single-nozzle printers are not recommended" |

### 5.2 Measured costs
| Data | Value | Source |
|---|---|---|
| Bambu cube, 4 colours, 0.2 mm | 153 changes → 83 g (≈0.54 g/change) | [Bambu wiki](https://wiki.bambulab.com/en/software/bambu-studio/reduce-wasting-during-filament-change) [L] |
| Same at 0.28 mm | 111 changes → 61 g (−27% changes, −26% waste) | same |
| Color Mixing, ~170 changes | 130 g single-nozzle vs 35 g multi-nozzle | [Bambu wiki Color Mixing](https://wiki.bambulab.com/en/bambu-studio/color-mixing) [L] |
| X1C swap time | 51.8 s @107 mm³; 71.5 s @400 mm³ (stock) | [forum 10037](https://forum.bambulab.com/t/ideas-on-boosting-speed-for-multi-color-printing-with-ams/10037) [L] |
| P2S AMS 2 Pro | ~6 s faster/change (feeding only); no measured P2S swap time published | [Bambu store P2S](https://us.store.bambulab.com/products/p2s) [L] |
| Flush volumes | light→dark 100–200 mm³, mid 200–400, dark→light 500–800, →clear 700+ | [3dprofilefix](https://www.3dprofilefix.com/guides/flushing-volumes-guide.html) [2nd] |
| Community PETG calibration | manual ≈43% of auto; ">300 mm³ is overkill"; yellow→green 30 mm³ | [forum 37062](https://forum.bambulab.com/t/ams-flushing-volumes-calibration-purge-reduction/37062) [L] |
| H2C vs H2D vs H2S (Bambu demo) | purge 532 g vs 3032 g vs 3917 g | [Bambu store H2C](https://us.store.bambulab.com/products/h2c) [L] |
| P2S quirk | `VFLUSH` block reportedly purges even with table at 0; no staff answer | [forum 230326](https://forum.bambulab.com/t/p2s-how-to-stop-optimised-g-code-from-purging-filament/230326) [L] |
*(calc)* PLA ≈1.24 g/cm³: 107 mm³ ≈ 0.13 g; 400 mm³ ≈ 0.5 g; 800 mm³ ≈ 1.0 g.

### 5.3 Purge-reduction levers
| Lever | Effect | Source |
|---|---|---|
| Flushing multiplier | 0.8–0.9 per Bambu; community 0.4–0.6; too low = tinted layers | [Bambu wiki](https://wiki.bambulab.com/en/software/bambu-studio/reduce-wasting-during-filament-change) [L]; [stlDenise3D](https://stldenise3d.com/no-more-printer-poop-banish-bambu-purge-waste-with-these-hot-tips/) [L] |
| Edit table cells | Lower light→dark; keep dark→light high; "Re-calculate" resets | Bambu wiki [L] |
| Flush into infill | Hidden; but thin/light walls show it; needs prime tower; **vase walls have no infill** | Bambu wiki [L] |
| **Flush into this object** (companion parts) | ~70 g → <1 g in Bambu's example; forum: 115 g → 4.8 g with 0.5 multiplier; companions should match height | Bambu wiki [L]; [forum 29422](https://forum.bambulab.com/t/making-better-use-of-flush-into-object-in-bambu-studio/29422) [L] |
| Thicker layers | 0.2→0.28: −26% waste | Bambu wiki [L] |
| Put colour changes low | Tower stops at last change: 14.76 g → 9.05 g | Bambu wiki [L] |
| Per-layer filament order | "Auto" chooses least-flush sequence; customisable per range | Bambu wiki [L] |
| Many copies per plate | Swaps amortise across copies | Bambu wiki [L] |
| Prime tower | Per-filament prime volume (Studio 2.0+); not available in By-object mode | [Bambu wiki prime tower](https://wiki.bambulab.com/en/software/bambu-studio/parameter/prime-tower) [L] |
| Height-based Change Filament | 1 swap per band; layer-slider version only when whole plate is one colour, else Height Range Modifier | [forum 7954](https://forum.bambulab.com/t/change-filament-at-layer-height/7954) [S] |

### 5.4 Techniques that use 3–4 colours well (ranked by value/cost on P2S)
1. **Height bands / per-course colour** (W, Mix, H in bands) — cheap; analogous 3–4 colour stacks (sunset, sea-glass).
2. **Gradient via Color Mixing Gradient mode** between 2 colours, or stepped band ombré across 4 — vertical walls only; budget heavy purge.
3. **CMYK lithophane band** on shades — exactly 4 slots.
4. **HueForge-style relief** on tiles/coasters — ≤4 swaps.
5. **Painted fuzzy zones** (matte fuzz vs silk smooth) — only costs swaps where zones share layers; run zones as horizontal bands to keep it cheap.
6. **Dual/tri-colour silk** in one slot + 1–3 other slots → 4–6 apparent colours, zero extra swaps.
7. **Per-feature colour (rods vs frame)** — striking but pays a swap every shared layer.

### 5.5 Making halftone affordable (worked)
150 mm vase @0.2 mm, alternate every layer → ~749 swaps → ~400 g @0.54 g/swap and +7.5–14 h on P2S *(calc from §5.2)*. Mitigations: alternate in **blocks of N thin layers** (Full Spectrum: stacks <~0.2 mm still blend — [Snapmaker](https://www.snapmaker.com/blog/getting-started-with-full-spectrum-slicing/) [L]); restrict alternation to an **image band**, placed **low**; use translucent or analogous pairs with edited cells at 0.6–0.8 multiplier; fill the plate with **companion flush objects** of matching height; or skip AMS entirely with **dual-colour silk on wavy ribs** (face-dependent colour, [CNC Kitchen](https://www.cnckitchen.com/blog/dual-color-dichromatic-3d-printing-filament) [L]). All AMS-alternation must be classic-wall, not spiral vase.

---

## Top 12 to add next (prioritised)

| # | What | Why | Effort | Mesh-feasible |
|---|---|---|---|---|
| 1 | **Fittings layer + Pendant shade (E27 40 mm collar) and LED-puck lamp (59×18 pocket, mushroom preset)** | Lighting is the strongest demand signal (MakerWorld, Etsy 1.2k-review mushroom lamp, Gantri retail); our mesh/fringe/woven textures glow; puck = no mains wiring | M | Yes |
| 2 | **Glass-liner sleeve mode** (offset from jar/bottle/test-tube/cylinder) | Makes every non-watertight texture (W/M/F) a functional vase; best-documented watertight route | S | Yes |
| 3 | **Cachepot preset** (4 in / 6 in / 8 in nursery pots, foot ring) | Holds no water → every texture allowed; easy, high-demand Etsy category | S | Yes |
| 4 | **Halftone economy mode**: N-layer blocks, image band only, placed low, companion flush objects, auto flush-table edit; plus a **dual-colour-silk zero-swap halftone** option | Per-layer halftone ≈ 400 g purge + ~10 h per 150 mm vase on P2S — current halftone is commercially painful | M | Yes |
| 5 | **Painted structured fuzzy-skin zones** (Perlin/Ridged/Voronoi via Bambu 2.5.3 paint in 3MF) as a new texture + Mix band | New "stone / velvet / knit" family for near-zero geometry cost; zones pair with matte/silk filament contrast | M (needs 3MF paint-data format check) | Yes |
| 6 | **Lids**: slip-fit (0.15–0.25/side, lead-in chamfer, smooth land band), multi-start coarse thread (2–4 mm pitch, 0.4 mm clearance), optional magnet pocket + auto Add Pause; rim test-ring generator | Unlocks lidded jar, trinket box, catch-all with lid; no lip-depth standard exists so a test-ring is the honest path | M | Yes |
| 7 | **Bridge-strand fur/mane** (0.2×0.8 mm slabs to a sacrificial shell) as a Droop sibling | Only mesh-feasible route to hair/fur; striking on shades, ornaments, pen cups | M | Yes |
| 8 | **Candle fittings: tealight lantern (40–42 pocket) + taper candlestick (22.5 bore, crush ribs)** with LED/glass-cup safety copy | Popular, cheap, showcases drip/melt reliefs; safety baked into preset | S | Yes |
| 9 | **Vase-mode pleat/flute/twist cross-section morphs** (pinch/ginkgo, star, low-poly) + amphora profile presets | Seamless spiral prints in minutes with 0.6–0.8 nozzles; fills "bud vase / pinch vase" demand without new shapes | S | Yes |
| 10 | **CMYK lithophane band** (0.8–3 mm thickness map) for shades/tiles | Uses exactly the 4 AMS slots (Bambu CMYK bundle); photo-personalised shades are a sellable hook | M | Yes |
| 11 | **Slit-rib / double-wall vase mode** + **Voronoi/perforated shell** | Stiff thin translucent shades (ribs show as lines) and an open lattice that suits shades/planters | S (slits) / M (voronoi) | Yes (verify Bambu gap-closing radius) |
| 12 | **Non-round footprints (rect/oval/hex)** → storage basket with handles, catch-all, hex wall tile | Opens the woven-organizer niche (42-model MakerWorld collection) and modular wall tiles | L | Yes |

*Explicitly not recommended now (need gcode control): Z-wave non-planar vases, stringing hair, BridgeSlicer lace, arc/wave overhangs, brick layers, ZAA — approximate in geometry where possible (flutes for ripple, bridge slabs for lace).*
