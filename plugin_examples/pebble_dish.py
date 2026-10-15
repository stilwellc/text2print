"""Shape plugin: a pebble-shaped valet dish — a soft superellipse outline (from "a pebble catch-all")."""
import numpy as np

SHAPE = dict(name="Pebble dish", blurb="A low dish with a pebble outline — softer than a rounded rectangle", kind="outline",
             params=[("width", "Width", 80, 200, 1, 150), ("depth", "Depth", 60, 160, 1, 105), ("height", "Height", 12, 60, 1, 26)])


def outline(v):
    a, b = v["width"] / 2, v["depth"] / 2
    def sdf(x, y):                         # superellipse |x/a|^n + |y/b|^n = 1 (n 2.6: pebble), as an approx. distance
        n = 2.6
        r = (np.abs(x / a) ** n + np.abs(y / b) ** n) ** (1 / n)
        return (r - 1.0) * min(a, b)
    return sdf


def extent(v):
    return max(v["width"], v["depth"]) / 2 + 2
