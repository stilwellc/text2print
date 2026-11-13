"""Colourwork: a stitch CHART knitted into the wall in two or three colours — jacquard ribs or bead knit.

The halftone trick, made exact: the colours of a band take turns layer by layer (A, B[, C]), and in every layer the
stitches whose chart cell is that layer's colour bulge outward while the rest stay flat behind. From outside you see
one colour per stitch, so a chart reads like fair-isle knitting, a woven folk-art panel or a beaded wall.

    jacquard — vertical ribs: each stitch is a rib, pixels stack into long columns (the folk-art vase look)
    beads    — each stitch bulges as a dome inside its row: a beaded / knitted surface

A chart is a list of BANDS, bottom to top (options["chart"]), each one of:

    {"motif": "hearts", "colours": [ground, motif(, accent)], "repeat": 1, "gap": 1}   from the motif library
    {"art": ["..X..", ".XoX.", ...], "colours": [...], "once": false}                  inline pixel art, top row first
    {"chart": "<plugin stem>", "rows": 12, "colours": [...]}                           a CHART plugin (Claude draws)
    {"picture": "text" | "lib:koi" | ..., "rows" or "mm" or "fill", "tones": 2|3,      any picture, posterised
     "colours": [...], + picture options (text, font, picture_place, ...)}
    {"plain": slot, "mm": 6}                                                           one colour, no changes
    {"stripes": [slot, slot, ...], "mm": 10, "layers": 2}                              thin stacked stripes
    {"course": [slot, slot, ...]}                                                      one colour per layer, spelled out

Art legend: "." ground, "X" motif, "o" accent (colours[0], [1], [2]). Motifs tile an integer number of times
around (spare columns spread as ground between repeats, so nothing is cut at the seam); "once": true places the art
a single time at the front. With no "fill" band the chart repeats up the wall; a "fill" band takes the rest.

Print: the halftone recipe (one wide wall, 0 % infill, layers at 0.7 x nozzle). Colour changes: about one per layer
inside two- and three-colour bands, none in plain bands — "band" (layers per colour) halves them."""
import math

import numpy as np
import trimesh

from .halftone import RECIPE, _ring

STYLES = {
    "jacquard": dict(name="Jacquard", slots=3, blurb="A knitted chart in ribs — fair-isle bands, motifs, pictures, 2–3 colours"),
    "beads": dict(name="Bead knit", slots=3, blurb="Every stitch a bead — beaded colourwork bands, 2–3 colours"),
}

LEGEND = {".": 0, " ": 0, "-": 0, "0": 0, "X": 1, "x": 1, "#": 1, "1": 1, "o": 2, "O": 2, "*": 2, "2": 2}

MOTIFS = {   # top row first; "." ground, "X" motif, "o" accent
    "hearts": dict(name="Hearts", art=[
        ".XX.XX..", "XXXXXXX.", "XXXXXXX.", ".XXXXX..", "..XXX...", "...X...."]),
    "tiny_hearts": dict(name="Tiny hearts", art=["X.X.....", ".X......", "....X.X.", ".....X.."]),
    "diamonds": dict(name="Diamonds", art=[
        "....X....", "...XoX...", "..XoooX..", ".XoooooX.", "..XoooX..", "...XoX...", "....X...."]),
    "eyes": dict(name="Eyes", art=[
        "...XXXXX....", ".XX.....XX..", "X...ooo...X.", "X..ooXoo..X.", "X...ooo...X.", ".XX.....XX..", "...XXXXX...."]),
    "meander": dict(name="Greek key", art=[
        "XXXXX.", "....X.", "XXX.X.", "X.X.X.", "X...X.", "XXXXXX"]),
    "zigzag": dict(name="Zigzag", art=["X.....", ".X...X", "..X.X.", "...X.."]),
    "checks": dict(name="Checks", art=["XX..", "XX..", "..XX", "..XX"]),
    "seed": dict(name="Seed stitch", art=["X...", "..X."]),
    "lice": dict(name="Lice dots", art=["X...", "....", "..X.", "...."]),
    "snowflake": dict(name="Snowflake", art=[
        "....X.....", ".X..X..X..", "..X.X.X...", "...XXX....", "XXXXoXXXX.", "...XXX....", "..X.X.X...",
        ".X..X..X..", "....X....."]),
    "tree": dict(name="Pine", art=[
        "...X....", "..XXX...", ".XXXXX..", "...X....", "..XXX...", ".XXXXX..", "XXXXXXX.", "...o...."]),
    "daisy": dict(name="Daisy", art=[
        "...X....", ".X.X.X..", "..XoX...", "XXoooXX.", "..XoX...", ".X.X.X..", "...X...."]),
    "waves": dict(name="Waves", art=[".XX.....", "X..X...X", "....XXX."]),
    "teeth": dict(name="Teeth", art=["..X...", ".XXX..", "XXXXX."]),
    "crosses": dict(name="Crosses", art=["..X...", ".XoX..", "..X...", "......"]),
    "line": dict(name="Line", art=["X"]),
}

PRESETS = {
    "fairisle": dict(name="Fair isle", bands=[
        {"stripes": [0, 1], "mm": 5, "layers": 2}, {"motif": "zigzag", "colours": [0, 1]},
        {"motif": "diamonds", "colours": [0, 1, 2]}, {"motif": "zigzag", "colours": [0, 1]},
        {"plain": 0, "mm": 5}, {"motif": "hearts", "colours": [0, 2]}, {"plain": 0, "mm": 5}]),
    "hearts": dict(name="Tiny hearts", bands=[{"motif": "tiny_hearts", "colours": [0, 1], "gap": 0}]),
    "eyes": dict(name="Eyes", bands=[
        {"stripes": [0, 2], "mm": 14, "layers": 3}, {"motif": "eyes", "colours": [0, 1, 2]},
        {"stripes": [0, 2], "mm": 14, "layers": 3}, {"motif": "meander", "colours": [0, 1]}]),
    "snow": dict(name="Snowflakes", bands=[
        {"motif": "seed", "colours": [0, 1], "gap": 0, "repeat": 3}, {"motif": "snowflake", "colours": [0, 1, 2]},
        {"motif": "seed", "colours": [0, 1], "gap": 0, "repeat": 3}, {"motif": "tree", "colours": [0, 1, 2]}]),
    "checks": dict(name="Checks", bands=[{"motif": "checks", "colours": [0, 1], "gap": 0}]),
    "picture": dict(name="Picture", bands=[{"picture": None, "fill": True, "colours": [0, 1]}]),
}
DEFAULT_PRESET = "fairisle"
SIZES = {"fine": 2.6, "regular": 3.2, "bold": 4.4}       # stitch width (mm) at a 0.4 nozzle; scales with the line


def art_grid(rows):
    """Pixel-art strings (top row first) -> int8 array (h, w) of 0/1/2, padded to a rectangle."""
    rows = [str(r) for r in rows if r is not None]
    w = max((len(r) for r in rows), default=1)
    return np.array([[LEGEND.get(ch, 0) for ch in r.ljust(w, ".")] for r in rows] or [[0]], np.int8)


def tile(art, cols, once=False):
    """Repeat art (h, w) around `cols` columns a whole number of times; spare columns become ground between the
    repeats (so no motif is cut at the seam). once: a single copy centred at the front (pictures.FRONT_U)."""
    h, w = art.shape
    if w >= cols:
        s = (w - cols) // 2
        return art[:, s:s + cols]
    if once:                                                    # centred on the FRONT: the side the studio camera and
        out = np.zeros((h, cols), np.int8); out[:, :w] = art    # a "front" picture face (pictures.FRONT_U), not 180 deg
        from .pictures import FRONT_U
        return np.roll(out, int(round(FRONT_U * cols - w / 2)), axis=1)
    reps = cols // w; extra = cols - reps * w
    parts = []
    for i in range(reps):
        parts.append(art)
        g = extra * (i + 1) // reps - extra * i // reps
        if g:
            parts.append(np.zeros((h, g), np.int8))
    return np.hstack(parts)[:, :cols]


def motif_choices():
    """Built-in motifs plus CHART plugins: [(key, name)]."""
    from . import plugins
    return [(k, m["name"]) for k, m in MOTIFS.items()] + [(k, c["name"]) for k, c in plugins.charts().items()]


def _band_cells(b, cols, row_mm, col_mm, rows_left, options):
    """One band -> (cells (rows, cols) of LOCAL colour index, bottom row first) — or None for plain/stripes."""
    from . import plugins
    gap = int(b.get("gap", 1))
    if b.get("motif") or b.get("art") is not None or b.get("chart"):
        key = b.get("motif") or b.get("chart")
        if b.get("art") is not None:
            art = art_grid(b["art"])
        elif key in MOTIFS:
            art = art_grid(MOTIFS[key]["art"])
        else:
            ch = plugins.charts().get(key) or plugins.charts().get(str(key).replace("chart:", ""))
            if ch is None:
                raise KeyError(f"no motif or chart called {key!r}")
            if ch.get("art") is not None:
                art = art_grid(ch["art"])
            else:
                rows = int(b.get("rows") or ch.get("rows") or 12)
                g = np.asarray(plugins.call(ch["fn"], cols, rows, p=plugins.param_values(ch.get("params"), options)))
                art = np.clip(np.rint(g), 0, 2).astype(np.int8)
                if art.shape[1] == cols:                       # a full-width chart: already laid out around
                    return _stack(art, int(b.get("repeat", 1)), gap)
        return _stack(tile(art, cols, once=bool(b.get("once"))), int(b.get("repeat", 1)), gap)
    if "picture" in b:
        from . import pictures
        rows = int(b.get("rows") or (round(float(b["mm"]) / row_mm) if b.get("mm") else rows_left))
        rows = max(1, rows)
        pic = dict(options, **{k: x for k, x in b.items() if k not in ("picture", "colours", "rows", "mm", "fill", "tones")})
        if b.get("picture"):
            pic["picture"] = b["picture"]
        f = pictures.darkness(pic, cols * col_mm / max(rows * row_mm, 1e-6))
        u = (np.arange(cols) + 0.5) / cols; v = (np.arange(rows) + 0.5) / rows
        U, V = np.meshgrid(u, v)
        g = f(U, V)
        if int(b.get("tones", 2)) >= 3:
            cells = np.where(g > 2 / 3, 1, np.where(g > 1 / 3, 2, 0)).astype(np.int8)
        else:
            cells = (g > 0.5).astype(np.int8)
        return cells                                           # already bottom row first (v up)
    return None


def _stack(art_top_first, repeat, gap):
    a = np.vstack([art_top_first] * max(1, repeat))
    if gap:
        z = np.zeros((gap, a.shape[1]), np.int8); a = np.vstack([z, a, z])
    return a[::-1]                                             # bottom row first


def plan(chart, cols, n_layers, lh, row_mm, col_mm, econ, options):
    """Chart bands -> per layer (slot, bulge cells or None, row-phase 0..1). Repeats the chart up the wall unless a
    band says "fill" (that band takes what the others leave)."""
    bands = [dict(b) for b in (chart or PRESETS[DEFAULT_PRESET]["bands"])]

    def rows_for(cyc):                                         # layers per pixel row: whole colour cycles, ~square
        unit = cyc * econ
        return unit * max(1, int(round(row_mm / (unit * lh))))

    def layers_of(b, rows_left_layers):
        slots = b.get("colours") or [0, 1, 2]
        if "plain" in b:
            last[0] = int(b["plain"])
            return [("plain", int(b["plain"]), None)] * max(1, int(round(float(b.get("mm", 4)) / lh)))
        if "course" in b:                                      # one colour per LAYER, spelled out (row-coloured tiers)
            out = [("plain", int(s), None) for s in b["course"]] or [("plain", 0, None)]
            last[0] = out[-1][1]
            return out
        if "stripes" in b:
            seq = [int(s) for s in b["stripes"]] or [0]; per = max(1, int(b.get("layers", 2)))
            n = max(1, int(round(float(b.get("mm", 8)) / lh)))
            out = [("plain", seq[(k // per) % len(seq)], None) for k in range(n)]
            last[0] = out[-1][1]
            return out
        # a row is as many layers as the band has colours (x band): a 3-tone picture's rows are taller than a
        # 2-colour one's, so size the picture with the cycle it will really be laid at
        three = "picture" in b and int(b.get("tones", 2)) >= 3 and len(set(int(x) for x in slots[:3])) >= 3
        Rg = rows_for(3 if three else 2)
        cells = _band_cells(b, cols, Rg * lh, col_mm, max(1, rows_left_layers // Rg), options)
        used = sorted(set(np.unique(cells).tolist()))
        loc = [i for i in used if i < len(slots)] or [0]
        gslots = [int(slots[i]) for i in loc]
        order = list(dict.fromkeys(gslots))                    # the band's colour cycle (distinct slots)
        R = rows_for(len(order)) if len(order) > 1 else rows_for(1)
        if b.get("fill") and "picture" not in b and rows_left_layers:      # a motif that fills: repeat it up the wall
            want = max(cells.shape[0], rows_left_layers // R)
            cells = np.vstack([cells] * (want // cells.shape[0] + 1))[:want]       # the last repeat may be cut at the rim
        out = []
        slot_cells = np.vectorize(lambda i: int(slots[i]) if i < len(slots) else int(slots[0]))(cells)
        for r in range(cells.shape[0]):
            here = [s for s in order if (slot_cells[r] == s).any()]          # only the colours this row shows
            if len(here) == 1:                                               # one colour: every stitch bulges every
                for l in range(R):                                           # layer — the ribs carry on, no changes
                    out.append(("cw", here[0], (np.ones(cols, bool), (l + 0.5) / R)))
                continue
            k = here.index(last[0]) if last[0] in here else 0                # start on the colour already loaded
            cyc = here[k:] + here[:k]
            for l in range(R):
                s = cyc[(l // econ) % len(cyc)]
                out.append(("cw", s, (slot_cells[r] == s, (l + 0.5) / R)))
            last[0] = out[-1][1]
        if b.get("fill") and out and 0 < rows_left_layers - len(out) < 4 * R:
            out += out[-R:][: rows_left_layers - len(out)] * 1   # "takes the rest": the top row carries on to the rim
            while len(out) < rows_left_layers:
                out.append(out[-R])
        if out:
            last[0] = out[-1][1]
        return out

    last = [None]                                              # the colour loaded at the end of the previous row

    fill = [i for i, b in enumerate(bands) if b.get("fill")]
    if fill:
        fixed = {i: layers_of(b, 0) for i, b in enumerate(bands) if i not in fill}
        left = max(0, n_layers - sum(len(x) for x in fixed.values()))
        per = left // len(fill)
        seq = []
        for i, b in enumerate(bands):
            seq += fixed[i] if i in fixed else layers_of(b, per)
        return seq[:n_layers]
    seq, k = [], 0
    while len(seq) < n_layers and k < 400:
        seq += layers_of(bands[k % len(bands)], n_layers - len(seq)); k += 1
    return seq[:n_layers]


def build(shape, v, nz, style="jacquard", chart=None, size="regular", band=1, rim="none", rim_slot=None, draft=False,
          options=None):
    lh, lw = RECIPE[nz.size]
    prof, height, rmax = shape.profile(v)
    floor_t = max(1.2, 4 * lh)
    n_floor = int(math.ceil(floor_t / lh))
    rim_layers = int(round(3.4 / lh)) if rim in ("braid", "rope") else 0
    n_layers = int(round(height / lh)); n_wall = max(4, n_layers - n_floor - rim_layers)
    col_mm = max(SIZES.get(size, 3.2) * lw / 1.0, 2.6 * lw)
    cols = max(24, int(round(2 * math.pi * rmax / col_mm)))
    col_mm = 2 * math.pi * rmax / cols
    row_mm = col_mm * (1.0 if style == "beads" else 0.95)
    econ = max(1, int(band))
    seq = plan(chart, cols, n_wall, lh, row_mm, col_mm, econ, options or {})
    per_col = 3 if draft else 6
    n_th = cols * per_col
    th = np.linspace(0, 2 * np.pi, n_th, endpoint=False)
    col_of = (np.floor(th / (2 * np.pi) * cols).astype(int)) % cols
    wave = 0.5 - 0.5 * np.cos(cols * th)                       # 0 between stitches, 1 at a stitch's centre
    th_flat = np.linspace(0, 2 * np.pi, max(180, cols * 2), endpoint=False)
    parts = {}
    first = seq[0][1] if seq else 0
    disc = trimesh.creation.cylinder(radius=prof(floor_t / 2), height=n_floor * lh, sections=max(96, cols * 2))
    disc.apply_translation([0, 0, n_floor * lh / 2])
    inlay_slot = None
    inl = (options or {}).get("floor_inlay")            # {"geom": shapely shape (mm, centred), "slot", "layers": 2}
    if inl:                                             # a mark inlaid flush in the bottom face, read from below
        from shapely import affinity
        from . import extras
        g = affinity.scale(inl["geom"], -1, 1, origin=(0, 0)) if inl.get("mirror", True) else inl["geom"]
        polys = list(g.geoms) if hasattr(g, "geoms") else [g]
        h = int(inl.get("layers", 2)) * lh
        disc = extras._tm(extras._m3d(disc) - extras.prism(polys, -0.1, h))
        inlay_slot = int(inl["slot"]) if inl.get("slot") is not None else (1 if first == 0 else 0)   # not the floor's colour
        parts.setdefault(inlay_slot, []).append(extras._tm(extras.prism(polys, 0.0, h)))
    parts.setdefault(first, []).append(disc)
    slots_seq = [first] * n_floor
    for k, (kind, slot, data) in enumerate(seq):
        L = n_floor + k; z0, z1 = L * lh, (L + 1) * lh; zm = (z0 + z1) / 2
        R = prof(zm)
        step = max(prof(zm) - prof(zm - lh), 0.0)
        amp = max(0.2 * lw, min(0.5 * lw, 0.6 * lw - step))
        if kind == "plain":
            parts.setdefault(slot, []).append(_ring(th_flat, np.full(len(th_flat), R - lw), np.full(len(th_flat), R), z0, z1))
        else:
            on, phase = data
            g = on[col_of].astype(float) * wave
            if style == "beads":
                g = g * math.sin(math.pi * phase) ** 0.7
            outer = R + amp * g
            parts.setdefault(slot, []).append(_ring(th, outer - lw, outer, z0, z1))
        slots_seq.append(slot)
    if rim_layers:                                              # a braided / rope edge in one colour, no changes
        rs = int(rim_slot) if rim_slot is not None else (slots_seq[-1] if slots_seq else 0)
        n_r = cols * 4; tr = np.linspace(0, 2 * np.pi, n_r, endpoint=False); a = 0.35 * lw; w = 1.5 * lw
        for j in range(rim_layers):
            L = n_floor + len(seq) + j; z0, z1 = L * lh, (L + 1) * lh; R = prof(min(z1, height))
            ph = (math.pi * ((j // 2) % 2)) if rim == "braid" else (2 * math.pi * j / 8)
            mid = R - lw / 2 + a * np.cos(max(1, round(cols / 2)) * tr + ph)      # whole waves: no step at the seam
            parts.setdefault(rs, []).append(_ring(tr, mid - w / 2, mid + w / 2, z0, z1))
            slots_seq.append(rs)
    swaps = sum(1 for a_, b_ in zip(slots_seq, slots_seq[1:]) if a_ != b_)
    meshes = {s: trimesh.util.concatenate(ms) for s, ms in parts.items() if ms}
    return meshes, dict(layers=len(slots_seq), cols=cols, stitch_mm=round(col_mm, 2), layer_h=lh, line_w=lw,
                        floor_layers=n_floor, swaps=swaps, slot_seq=slots_seq, seq=seq, wall_top=(n_floor + len(seq)) * lh,
                        floor_slot=first, inlay_slot=inlay_slot)


def preview(prof, info, style="jacquard", sub=6):
    """Preview only: the wall as the eye reads it. In each layer a stitch's crown takes the colour that bulges there
    (its own layer's, or the neighbouring layer's whose stitch stands in front) and the valleys between stitches keep
    the layer's own colour, so the chart shows with the softened contrast a real colour-knit has. -> {slot: mesh}"""
    seq, n_floor, cols, lh, lw = info["seq"], info["floor_layers"], info["cols"], info["layer_h"], info["line_w"]
    n = len(seq)
    own = np.array([s_[1] for s_ in seq])
    on = np.array([np.ones(cols, bool) if (s_[0] == "plain" or s_[2] is None) else np.asarray(s_[2][0], bool) for s_ in seq])
    phase = np.array([0.5 if (s_[0] == "plain" or s_[2] is None) else s_[2][1] for s_ in seq])
    plain = np.array([s_[0] == "plain" for s_ in seq])
    app = np.where(on, own[:, None], -1)
    for d in range(1, 9):                                       # a flat stitch shows the nearest layer that bulges
        for sgn in (1, -1):
            sh = np.full_like(app, -1)
            if sgn > 0:
                sh[:-d] = np.where(on[d:], own[d:, None], -1)
            else:
                sh[d:] = np.where(on[:-d], own[:-d, None], -1)
            app = np.where(app < 0, sh, app)
    app = np.where(app < 0, own[:, None], app)
    n_th = cols * sub
    th = np.linspace(0, 2 * np.pi, n_th, endpoint=False)
    wave = 0.5 - 0.5 * np.cos(cols * th)
    zc = (n_floor + np.arange(n) + 0.5) * lh
    R = np.array([prof(z) for z in zc])
    dome = np.where(plain, 0.0, np.sin(np.pi * phase) ** 0.7 if style == "beads" else 1.0)
    rad = R[:, None] + 0.5 * lw * dome[:, None] * wave[None, :] - 0.12 * lw * (1 - wave[None, :])
    c, s_ = np.cos(th), np.sin(th)
    V = np.empty((n, 2, n_th, 3))
    rad_top = np.vstack([rad[1:], rad[-1:]])                     # each strip leans to meet the next layer: on a steep
    V[:, 0, :, 0] = rad * c; V[:, 0, :, 1] = rad * s_            # shoulder upright strips leave slits you see through
    V[:, 1, :, 0] = rad_top * c; V[:, 1, :, 1] = rad_top * s_
    V[:, 0, :, 2] = (zc - lh / 2)[:, None]; V[:, 1, :, 2] = (zc + lh / 2)[:, None]
    V = V.reshape(-1, 3)
    j = np.arange(n_th); jn = (j + 1) % n_th
    crown = (j % sub >= 1) & (j % sub < sub - 1)
    col_of = j // sub
    cell = np.where(crown[None, :], app[:, col_of], own[:, None])           # (layers, n_th) slot per quad
    base = (np.arange(n) * 2 * n_th)[:, None]
    a0 = base + j[None, :]; a1 = base + jn[None, :]; b0 = a0 + n_th; b1 = a1 + n_th
    out = {}
    for slot in np.unique(cell):
        m = cell == slot
        F = np.vstack([np.column_stack([a0[m], a1[m], b1[m]]), np.column_stack([a0[m], b1[m], b0[m]])])
        out[int(slot)] = [trimesh.Trimesh(V, F, process=False)]
    first = int(np.bincount(own).argmax()) if n else 0          # the inside shows the wall's main colour
    zs = np.concatenate([[0.0], zc, [zc[-1] + lh / 2]]) if n else np.array([0.0, 1.0])
    inner = [(max(prof(z) - lw, 1.0), z) for z in zs]; outer = [(max(prof(z) - 0.4 * lw, 1.2), z) for z in zs[::-1]]
    liner = trimesh.creation.revolve(np.array([(0.0, 0.0)] + [(prof(0.0), 0.0)] + outer[::-1][1:] + inner[::-1] + [(0.0, n_floor * lh)]),
                                     sections=max(96, cols))
    out.setdefault(first, []).append(liner)
    last = int(own[-1]) if n else first
    out.setdefault(last, []).append(_ring(th, rad[-1] - lw, rad[-1], zc[-1] - lh / 2, zc[-1] + lh / 2))
    return {k: trimesh.util.concatenate(ms) for k, ms in out.items()}
