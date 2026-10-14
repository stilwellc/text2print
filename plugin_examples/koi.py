"""Picture plugin: koi drifting through ripples (written from the prompt "koi pond halftone")."""
import numpy as np

PICTURE = dict(name="Koi pond", colour=False)


def _hash(i, salt=0.0):
    return (np.sin(i * 127.1 + salt * 311.7) * 43758.5453) % 1.0


def draw(u, v, aspect):
    """u 0..1 around the wall, v 0..1 up; aspect = width/height in mm. Returns darkness 0..1 (1 = front colour)."""
    x, y = u * aspect, v                               # work in true proportions so fish aren't stretched
    out = np.zeros_like(u, dtype=float)
    n = max(3, int(round(aspect * 2.2)))               # about two fish per square of wall
    for k in range(n):
        cx = (k + 0.5 + 0.35 * (_hash(k) - 0.5)) * aspect / n
        cy = 0.18 + 0.64 * _hash(k, 1.0)
        ang = 2 * np.pi * _hash(k, 2.0); L = 0.16 + 0.06 * _hash(k, 3.0)
        ca, sa = np.cos(ang), np.sin(ang)
        dx = x - cx; dx = (dx + aspect / 2) % aspect - aspect / 2       # wrap around the seam
        dy = y - cy
        px, py = dx * ca + dy * sa, -dx * sa + dy * ca                  # fish frame: +px = head
        bend = 0.25 * L * np.sin(np.pi * np.clip((-px / L + 0.2), 0, 1.2))
        body = (px / L) ** 2 + ((py - bend) / (0.32 * L)) ** 2 < 1.0
        tail = (px < -0.85 * L) & (px > -1.45 * L) & (np.abs(py - bend) < 0.55 * (-px - 0.85 * L) + 0.02)
        fins = ((px - 0.15 * L) / (0.18 * L)) ** 2 + ((np.abs(py) - 0.36 * L) / (0.1 * L)) ** 2 < 1.0
        out = np.maximum(out, (body | tail | fins).astype(float))
    ripple = 0.5 + 0.5 * np.sin(2 * np.pi * (np.hypot((x % 1.0) - 0.5, y - 0.5) * 7.0))
    return np.clip(out + 0.18 * (ripple > 0.92), 0, 1)
