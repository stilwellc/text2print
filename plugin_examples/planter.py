"""Shape plugin: a planter with a rolled lip (from "a planter with a soft rolled rim")."""
import math

SHAPE = dict(name="Planter", blurb="Tapered planter that swells into a soft rolled rim", kind="round",
             params=[("diameter", "Rim", 80, 220, 1, 150), ("height", "Height", 60, 220, 1, 130),
                     ("base", "Base", 40, 90, 1, 66, "%")])


def radius(v, z):
    R, h = v["diameter"] / 2, v["height"]
    t = min(max(z / h, 0.0), 1.0)
    body = R * (v["base"] / 100 + (0.9 - v["base"] / 100) * t ** 0.9)       # straight taper up to 90 % of the rim
    lip = 0.1 * R * math.sin(math.pi / 2 * max(0.0, (t - 0.82) / 0.18)) if t > 0.82 else 0.0
    return body + lip                                                         # the rim rolls out at <= 0.9 mm/mm
