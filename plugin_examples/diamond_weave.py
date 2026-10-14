"""Woven plugin: courses at +60 and -60 degrees, colour by direction — open diamonds (from "diamond lattice weave")."""
import math

from text2print.lattice import Course, _pt

WOVEN = dict(name="Diamond weave", blurb="Rods at ±60° on alternate courses — an open diamond lattice", slots=2,
             swaps="course")


def pattern(region, nz, rods):
    for i in range(region.n):
        c = Course(region, nz, i)
        theta = math.radians(60 if i % 2 == 0 else -60)
        for j, t0, t1, pf in c.lines(theta, pitch=nz.pitch * 1.25):
            rods.line(_pt(pf, t0, c.z), _pt(pf, t1, c.z), i % 2)
