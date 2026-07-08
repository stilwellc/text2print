# Design review checklist

The visual pass every model gets before a verification gate. Numbers
alone lie; these views catch what `is_watertight` cannot.

## Render these, every time

1. **Full elevation** — the whole part from the side, at a distance
   that fits it with margin. Checks silhouette, proportions, and
   whether texture zones read as intended at arm's length.
2. **Macro** — camera close to the surface at a grazing angle.
   Checks stitch/band geometry: are bands flowing or stacking? Are
   windows open? Do transitions land where the parameters say?
3. **Top-down / floor** — straight into the part. Checks cutout
   patterns, web widths, and interior features.

## What to look for

- **Band rhythm** — fabric bands at ~0.15x stitch width flow; taller
  reads as stacked slabs; per-layer flips collapse into vertical ribs.
- **Scale honesty** — a texture that reads at macro distance may
  vanish at elevation distance. Judge at the distance the object will
  actually be seen.
- **Transitions** — zone boundaries (separators, morphs, rim bands)
  should look deliberate, not like a parameter ran out.
- **Floor webs** — material between cutouts >= ~3mm; islands are
  impossible (the tooling raises), but *near*-islands print weak.
- **Seam and bed edges** — the first pattern band should meet the
  solid base cleanly; the rim band should finish, not truncate.

## The numbers that ride along

Every review pairs the renders with: watertight, body count (must be
1), bounding box vs. requirements, max lower-wall slope (<= 1.0 for
supportless), and the unsupported span vs. the material bridge limit.
