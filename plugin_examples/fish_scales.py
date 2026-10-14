"""Stitch plugin: overlapping fish scales — each scale a rounded tongue raised at its lower edge (from "fish-scale knit")."""
import numpy as np

STITCH = dict(name="Fish scales", blurb="Overlapping rounded scales, offset row to row like a pinecone")


def displace(u, layer, band_layers, band, z_frac):
    """u: 1 per scale around (odd bands shifted half a scale); layer within the band (0 = bottom).
    Returns 0..1 of the stitch depth. A scale is deepest at its rounded lower edge and fades upward."""
    x = np.mod(u, 1.0) - 0.5                         # -0.5..0.5 across the scale
    t = (layer + 0.5) / band_layers                  # 0 at the bottom of the band, 1 at the top
    edge = 0.15 + 0.55 * (1 - np.sqrt(np.clip(1 - (2 * x) ** 2, 0, 1)))   # the U-shaped lower edge
    inside = t >= edge
    return np.where(inside, np.clip(1.0 - (t - edge) * 1.6, 0, 1) * np.sqrt(np.clip(1 - (2 * x) ** 2, 0, 1)), 0.0)
