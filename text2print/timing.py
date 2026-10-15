"""Instant print-time estimate (no slicing): a log-linear model fitted to 121 real Bambu Studio slices on the P2S
(0.4 nozzle) — leave-one-out median error 11 %, 90th percentile 27 %. "Get exact print time" still slices."""
import json
import math
import pathlib

_M = None


def _model():
    global _M
    if _M is None:
        _M = json.loads((pathlib.Path(__file__).parent / "data" / "time_model.json").read_text())
    return _M


def estimate(family, grams_part, swaps, height, area_mm2, nozzle=0.4):
    """-> minutes (None for families the model never saw). Other nozzles scale by flow: a 0.6 lays ~2x per pass."""
    m = _model()
    fam = family if family in m["fams"] else ("fabric" if family in ("flat",) else None)
    if fam is None:
        return None
    x = [math.log(grams_part + 1), math.log(swaps + 1), math.log(max(height, 1.0)), math.log(area_mm2 / 1000 + 0.01), 1.0]
    x += [1.0 if f == fam else 0.0 for f in m["fams"]]
    mins = math.exp(sum(a * b for a, b in zip(m["w"], x)))
    return round(mins * {0.2: 1.9, 0.4: 1.0, 0.6: 0.62, 0.8: 0.48}.get(nozzle, 1.0), 1)
