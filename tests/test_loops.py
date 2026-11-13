"""Loops on colour-knit: the named looks, their colour plans, and what the project must carry to print them."""
import json
import math
import zipfile

import numpy as np
import pytest

from text2print import build, colourwork, droop, loops, printer
from text2print.shapes import SHAPES

PEAR = dict(diameter=90, height=115, c0=70, c1=100, c2=90, c3=68, c4=44, neck=8, lip=1.5)
COLS = ["#151515", "#F4F2EC", "#C8102E"]


def make(look, **opts):
    return build.make("custom", "jacquard", PEAR, colours=COLS, options=dict(loops=look, band=2, stitch_size="fine", **opts), draft=True)


@pytest.mark.parametrize("look", list(loops.LOOKS))
def test_every_look_builds_watertight_parts_with_loops(look):
    b = make(look)
    assert b.stats["strands"] > 200 and all(m.is_watertight for _, m, _, _ in b.parts)
    assert b.preview is not None                                  # the hung-loop preview


@pytest.mark.parametrize("look", list(loops.LOOKS))
def test_loops_add_no_colour_changes(look):
    S = SHAPES["custom"]; v = S.resolve(PEAR); nz = printer.nozzle(0.4)
    opts = dict(band=2, stitch_size="fine")
    chart, _ = loops.resolve(look, opts, S, v, nz, 3)
    bare = build.make("custom", "jacquard", PEAR, colours=COLS, options=dict(opts, **({"chart": chart} if chart else {})), draft=True)
    assert make(look).stats["swaps"] == bare.stats["swaps"]


def test_a_loop_must_print_as_one_bead():
    o = make("tiers").overrides
    assert o["min_bead_width"] == "200%"                          # at the stock 85 % each loop splits into two thin lines
    assert set(o["enable_overhang_speed"]) == {"0"} and o["seam_position"] == "back"


def test_loops_in_one_layer_never_overlap():
    S = SHAPES["custom"]; v = S.resolve(PEAR); nz = printer.nozzle(0.4)
    _, spec = loops.resolve("tiers", {}, S, v, nz, 3)
    meshes, info = colourwork.build(S, v, nz, chart=[{"plain": 0, "mm": 200}], size="fine", draft=True, options={})
    prof = S.profile(v)[0]
    ev = droop.even_options(dict(spec, rows="even"))
    _, spots, _ = droop.colourwork_loops(prof, info["layer_h"], info["line_w"], ev, info, None, "layer")
    by_layer = {}
    for (th, w, _, z, _, _, line), _, _ in spots:
        by_layer.setdefault(int(z / info["layer_h"]), []).append((th, (w + line) / 2 / prof(z)))
    for row in by_layer.values():
        row.sort()
        for (a, ha), (b, hb) in zip(row, row[1:] + [(row[0][0] + 2 * math.pi, row[0][1])]):
            assert b - a >= ha + hb - 1e-6


def test_colour_plans_use_the_real_height_of_an_oversize_piece():
    """A piece past the picker's size limits (built raw) once had its chart laid out for the clamped height, so
    everything near the top landed 30 mm low."""
    big = dict(diameter=168, height=250, c0=72, c1=100, c2=90, c3=70, c4=46, neck=16, lip=3)
    b = build.make("custom", "jacquard", big, colours=COLS[:2], options=dict(loops="window", band=2, stitch_size="bold"), draft=True, _raw=True)
    top_white = max(float(m.bounds[1][2]) for _, m, _, c in b.parts if c == COLS[1])
    assert b.stats["size"][2] > 249 and top_white > 240          # the white line under the lip


def test_salt_keeps_most_rows_one_colour():
    S = SHAPES["custom"]; v = S.resolve(PEAR); nz = printer.nozzle(0.4)
    art = next(band["art"] for band in loops.salt_chart(S, v, nz, "fine", 2) if "art" in band)
    salted = sum("X" in row for row in art)
    assert 0.3 < salted / len(art) < 0.8 and sum(row.count("X") for row in art) / (len(art) * len(art[0])) < 0.3


def test_petal_loops_take_their_own_petals_colour():
    S = SHAPES["custom"]; v = S.resolve(PEAR); nz = printer.nozzle(0.4)
    chart, spec = loops.resolve("petals", {"band": 2, "stitch_size": "fine"}, S, v, nz, 2)
    meshes, info = colourwork.build(S, v, nz, chart=chart, size="fine", band=2, draft=True, options={})
    ev = droop.even_options(dict(spec, rows="even"))
    _, spots, _ = droop.colourwork_loops(S.profile(v)[0], info["layer_h"], info["line_w"], ev, info, None, "petal")
    wrong = 0
    for (th, _, _, z, _, _, _), slot, _ in spots:
        lid = droop.petal_field(th, z, ev["petal"], ev["petal_sag"], int(ev["petals"]))[1]
        wrong += int(droop.petal_slot(lid, ev["petal_share"], int(ev["petal_seed"]))) != slot
    assert wrong <= 0.03 * len(spots)                             # a loop moves a layer or two; near a hem that can cross


def test_petg_uses_bambus_preset_without_the_pla_droop_offset():
    f = make("shag", material="petg").per_filament
    assert set(f["filament_settings_id"]) == {"Generic PETG @BBL P2S"} and set(f["filament_type"]) == {"PETG"}
    assert set(f["nozzle_temperature"]) == {"255"} and set(f["fan_max_speed"]) == {"20"}


def test_base_inlay_takes_the_other_colour_and_primes_on_a_block(tmp_path):
    b = build.make("custom", "jacquard", PEAR, colours=COLS[:2],
                   options=dict(loops="window", band=2, stitch_size="fine", inlay_text="abc", tower="inlay"), draft=True)
    assert b.prime_block and not b.tower and len(set(b.prime_block["colours"])) == 2
    p = b.write_3mf(tmp_path / "piece.3mf")
    with zipfile.ZipFile(p) as z:
        settings = z.read("Metadata/model_settings.config").decode()
        cfg = json.loads(z.read("Metadata/project_settings.config"))
    assert settings.count("<object ") == 1 and "prime 1" in settings and "prime 2" in settings   # parts of ONE object
    assert cfg["enable_prime_tower"] == "0"


def test_custom_shape_neck_is_straight_and_the_lip_flares():
    prof, H, _ = SHAPES["custom"].profile(SHAPES["custom"].resolve(PEAR))
    assert H == 115 and abs(prof(H - 6) - prof(H - 4)) < 0.05 and prof(H) > prof(H - 4) + 1.0


def test_the_picker_offers_loops_filament_and_even_droop_rows():
    keys = lambda fam: {o[0] for o in build.OPTIONS[fam]}
    assert {"loops", "loop_colour", "loop_size", "material"} <= keys("colourwork")
    assert {"rows", "panels", "material"} <= keys("droop") and all("material" in keys(f) for f in build.OPTIONS)
