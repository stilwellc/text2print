"""Parts that are not in the catalogue: a bracket, a sleeve, a stand, a clip, a piece with your own outline.
Model the mesh however suits it (manifold3d, CadQuery, trimesh, a handed-over STL), then hand it to deliver():

    from text2print import part
    r = part.deliver("pipe_sleeve", [("Sleeve", mesh, 1)], colours=["#FFFFFF"], material="petg", slice=True,
                     check={"length": (30.0, "z"), "bore": (17.0, "x", (0, 0, 15))})

deliver() does what every one-off script used to copy by hand, and gets the parts right that were missed when it was
copied: the material's own speeds (PETG at PLA speeds printed rough, twice), a slow first layer when asked, the right
list shapes, one object with one part per colour, STLs, a render, a dimension drawing, the slice, and a report of
what the sliced file will really do. Several pieces (two halves, a lid and its base, two of the same) go on one plate:
pass {piece name: parts}."""
import pathlib

import numpy as np
import trimesh

from . import bambu, printer

SHOW = {"#FFFFFF": "#F2F0EA"}                       # pure white vanishes in a render
GAP = 6.0                                           # mm between pieces on the plate
TOWER_ZONE = (printer.BED - 58.0, 78.0)             # two colours: the tower owns x beyond this and y below this
EDGE = 3.0                                          # keep this far inside the bed


def span(meshes, at, axis):
    """The distance between the first surfaces met going both ways from `at` along axis "x" | "y" | "z". With `at` in
    an opening it is the INSIDE size (a bore, a slot, the gap between two legs); with `at` in material it is the wall
    thickness there. meshes: one mesh or several (a piece's colours together). -> (mm, low point, high point).
    Raises if there is no surface on one side (the point is outside the part, or the opening is open that way)."""
    meshes = [meshes] if hasattr(meshes, "vertices") else list(meshes)
    tri = np.vstack([np.asarray(m.vertices, float)[np.asarray(m.faces)] for m in meshes])
    o = np.asarray(at, float); k = "xyz".index(axis); d = np.zeros(3); d[k] = 1.0
    e1, e2 = tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]                 # Moller-Trumbore, one line against every face
    h = np.cross(d, e2); a = np.einsum("ij,ij->i", e1, h); ok = np.abs(a) > 1e-12
    f = np.where(ok, 1.0 / np.where(ok, a, 1.0), 0.0); s = o - tri[:, 0]
    u = f * np.einsum("ij,ij->i", s, h); q = np.cross(s, e1); v = f * (q @ d); t = f * np.einsum("ij,ij->i", e2, q)
    t = t[ok & (u >= -1e-9) & (v >= -1e-9) & (u + v <= 1 + 1e-9)]
    up, down = t[t > 1e-9], t[t < -1e-9]
    if not len(up) or not len(down):
        raise ValueError(f"nothing to measure along {axis} from {tuple(round(float(c), 2) for c in o)}: "
                         f"no surface on the {'far' if not len(up) else 'near'} side")
    lo, hi = o + d * down.max(), o + d * up.min()
    return float(up.min() - down.max()), lo, hi


def _pieces(parts):
    """-> [(piece name, [(part name, mesh copy, slot, *opts)])]. The caller's meshes are never moved."""
    if isinstance(parts, dict):
        groups = list(parts.items())
    else:
        groups = [(None, parts)]
    out = []
    for pname, ps in groups:
        out.append((pname, [(n, m.copy(), int(s)) + tuple(rest) for n, m, s, *rest in ps]))
    return out


def _layout(sizes, towered):
    """Centres for boxes (x, y sizes) laid in rows, the group centred on the bed and, with a prime tower, moved clear
    of its corner. -> ([(cx, cy)], [warnings])."""
    bed = printer.BED; wide = bed - 2 * EDGE
    rows, row, w = [], [], 0.0
    for i, (sx, sy) in enumerate(sizes):
        if row and w + GAP + sx > (TOWER_ZONE[0] - EDGE if towered else wide):
            rows.append(row); row, w = [], 0.0
        row.append(i); w += (GAP if len(row) > 1 else 0) + sx
    rows.append(row)
    row_w = [sum(sizes[i][0] for i in r) + GAP * (len(r) - 1) for r in rows]
    row_d = [max(sizes[i][1] for i in r) for r in rows]
    W, D = max(row_w), sum(row_d) + GAP * (len(rows) - 1)
    cx, cy = bed / 2, bed / 2; warn = []
    if W > wide or D > wide:
        warn.append(f"the plate needs {W:.0f} x {D:.0f} mm and the bed has {wide:.0f}: it does not fit; split it over two projects")
    elif towered and cx + W / 2 > TOWER_ZONE[0] and cy - D / 2 < TOWER_ZONE[1]:
        if W <= TOWER_ZONE[0] - EDGE:                                   # slide left of the tower
            cx = TOWER_ZONE[0] - W / 2
        elif D <= bed - EDGE - TOWER_ZONE[1]:                           # or behind it
            cy = TOWER_ZONE[1] + D / 2
        else:
            warn.append(f"a {W:.0f} x {D:.0f} mm plate overlaps the prime tower in the front-right corner: "
                        "place it by hand (position=, and wipe_tower_x / wipe_tower_y in overrides)")
    centres = [None] * len(sizes); y = cy - D / 2
    for r, rw, rd in zip(rows, row_w, row_d):
        x = cx - rw / 2
        for i in r:
            centres[i] = (x + sizes[i][0] / 2, y + rd / 2); x += sizes[i][0] + GAP
        y += rd + GAP
    return centres, warn


def deliver(name, parts, colours, material="pla", out=None, overrides=None, nozzle=printer.DEFAULT_NOZZLE, layer_h=None,
            walls=None, infill=None, first_layer=None, position=None, slice=False, render=True, drawing=True, dims=(),
            check=None, tol=0.05, plate=None, first_layer_order=None, title=None, stls=True, base_overrides=None,
            copies=1, assumed=(), _sources=()):
    """Write a functional part as a Bambu Studio project in ~/Downloads/<name>/ and report on it.

    parts      [(name, mesh, slot)] — one mesh per colour, slot = the 1-based index into colours. They go in ONE
               object (separate objects per colour leave empty layers and Bambu refuses to slice). Meshes are in the
               pose they print; each piece is seated on the plate and laid out for you. Your meshes are not moved.
               Several pieces on one plate: {piece name: [(name, mesh, slot), ...], ...}; copies=2 prints two of each.
    material   "pla", "petg", ... or one per colour. Sets the filament preset and the process speeds.
    overrides  slicer settings on top of printer.solid_part(...) (scalars are fine); base_overrides replaces
               solid_part entirely, e.g. printer.overrides(nozzle, "lattice", slots=2, material=material) for rods
               (layer_h, walls and infill still apply when you pass them).
    first_layer  mm/s for layer one, for small or fine features on the textured plate (PETG rods: 15).
    first_layer_order  filaments in the order they print on layer one, e.g. (2, 1) = black before white.
    check      {label: (mm, axis)} asserts the OUTSIDE size on axis "x" | "y" | "z" within tol;
               {label: (mm, axis, (x, y, z))} asserts the span through that point of YOUR model (see span()): the
               inside of a bore or slot, the gap between two legs, or a wall's thickness. With several pieces add the
               piece name last: (mm, axis, point_or_None, "Lid"). A fit part cannot be delivered at the wrong size,
               and outside can no longer be mistaken for inside. Every check is drawn on the dimension drawing.
    assumed    numbers nobody measured ("pocket 69 mm"): printed on the drawing and returned in warnings.
    -> {"project", "stls", "render", "drawing", "size", "pieces", "checks", "centres" (where each piece sits on the
       plate: what fits.artwork_check wants), "slice", "report", "warnings"}"""
    out = pathlib.Path(out).expanduser() if out else pathlib.Path.home() / "Downloads" / name
    out.mkdir(parents=True, exist_ok=True)
    pieces = _pieces(parts); multi = len(pieces) > 1 or pieces[0][0] is not None
    colours = list(colours); n_col = max(s for _, ps in pieces for _, _, s, *_ in ps)
    if n_col > len(colours):
        raise ValueError(f"a part uses colour slot {n_col} but only {len(colours)} colours were given")
    mats = [material] * n_col if isinstance(material, str) else list(material)
    if len(mats) == 1:
        mats = mats * n_col
    if len(mats) < n_col:
        raise ValueError(f"{len(mats)} materials for {n_col} colours: give one, or one per colour")
    mats = mats[:n_col]
    warnings = [f"assumed, not measured: {a}" for a in assumed]
    for pname, ps in pieces:
        for n, m, *_ in ps:
            if not m.is_watertight:
                warnings.append(f"{n}: the mesh is not watertight (many separate rods in one part read that way; a solid should not)")

    # measure in the caller's coordinates, before anything is moved
    boxes = {}
    for pname, ps in pieces:
        v = np.vstack([np.asarray(m.vertices) for _, m, *_ in ps]); boxes[pname] = (v.min(0), v.max(0))
    measured, check_dims = {}, {pname: [] for pname, _ in pieces}
    for label, spec in (check or {}).items():
        want, axis, at, pname = (tuple(spec) + (None, None))[:4]
        if pname is None and len(pieces) > 1:
            raise ValueError(f"check '{label}': name the piece it measures, one of {[p for p, _ in pieces]}")
        pname = pieces[0][0] if pname is None else pname
        if pname not in boxes:
            raise ValueError(f"check '{label}': no piece called '{pname}'")
        lo, hi = boxes[pname]; k = "xyz".index(axis)
        if at is None:
            got = float(hi[k] - lo[k]); kind = "outside"
        else:
            got, p0, p1 = span([m for _, m, *_ in dict(pieces)[pname]], at, axis); kind = "through the point given"
            check_dims[pname].append((axis, p0, p1, f"{got:.2f} {label}"))
        if abs(got - want) > tol:
            raise ValueError(f"{label}: built {got:.2f} mm on {axis}, wanted {want:.2f} ({kind})")
        measured[label] = round(got, 3)

    # seat each piece, then lay the plate out
    sizes = {}
    for pname, ps in pieces:
        lo, hi = boxes[pname]; shift = np.array([-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]])
        for _, m, *_ in ps:
            m.apply_translation(shift)
        check_dims[pname] = [(ax, p0 + shift, p1 + shift, lab) for ax, p0, p1, lab in check_dims[pname]]
        sizes[pname] = (hi - lo).astype(float)
    placed = [(pname, ps) for pname, ps in pieces for _ in range(max(1, int(copies)))]
    centres, lay_warn = _layout([tuple(sizes[p][:2]) for p, _ in placed], n_col > 1)
    if position is not None:
        if len(placed) > 1:
            off = np.asarray(position, float) - np.mean(centres, axis=0)
            centres = [tuple(np.asarray(c) + off) for c in centres]
        else:
            centres = [tuple(position)]
    else:
        warnings.extend(lay_warn)

    over = dict(base_overrides) if base_overrides is not None else \
        printer.solid_part(nozzle, layer_h, 3 if walls is None else walls, "20%" if infill is None else infill, colours=n_col)
    if base_overrides is not None:                     # the caller's own settings, but these three still mean what they say
        if layer_h is not None:
            over["layer_height"] = f"{float(layer_h):g}"
        if walls is not None:
            over["wall_loops"] = str(int(walls))
        if infill is not None:
            over["sparse_infill_density"] = str(infill)
    over.update({k: (str(v) if not isinstance(v, (list, tuple, dict)) else v) for k, v in (overrides or {}).items()})
    plain = all(str(m).strip().lower() in ("pla", "") for m in mats)
    if not plain:
        over.update(printer.process_for(nozzle, mats, over))
    if first_layer:
        over.update(printer.slow_first_layer(nozzle, first_layer, over))
    pm = dict(plate or {})
    if first_layer_order:
        pm["first_layer_print_sequence"] = " ".join(str(int(i)) for i in first_layer_order)
    p3mf = out / f"{name}.3mf"
    objects = []
    for (pname, ps), c in zip(placed, centres):
        objects.append({"name": pname or title or name, "position": (float(c[0]), float(c[1])), "parts": ps})
    bambu.write_3mf(str(p3mf), objects, title=title or name, colours=tuple(colours[:n_col]), overrides=over,
                    base=printer.base_config(nozzle),
                    per_filament=None if plain else printer.material_settings(nozzle, mats), plate=pm or None)
    whole = np.array([max(sizes[p][k] for p, _ in pieces) for k in range(3)]) if multi else sizes[pieces[0][0]]
    res = {"project": str(p3mf), "size": [round(float(x), 2) for x in whole], "warnings": warnings, "stls": [],
           "pieces": {(p or name): [round(float(x), 2) for x in sizes[p]] for p, _ in pieces}, "checks": measured,
           "centres": [(p or name, round(float(c[0]), 2), round(float(c[1]), 2)) for (p, _), c in zip(placed, centres)]}
    slug = lambda s: str(s).lower().replace(" ", "_")
    sources = {pathlib.Path(s).expanduser().resolve() for s in _sources}
    if stls:
        for pname, ps in pieces:
            for n, m, *_ in ps:
                stem = "_".join([name] + ([slug(pname)] if pname else []) + ([slug(n)] if len(ps) > 1 or (not pname and len(pieces[0][1]) > 1) else []))
                f = out / f"{stem}.stl"
                if f.resolve() in sources:             # the handed-over file is the model: it is never written over
                    res["stls"].append(str(f)); continue
                m.export(f); res["stls"].append(str(f))
    col = lambda s: SHOW.get(colours[s - 1].upper(), colours[s - 1])
    if render:
        from .render import render as _render
        shown = []
        for (pname, ps), c in zip(placed, centres):
            for _, m, s, *_ in ps:
                mm = m.copy(); mm.apply_translation([c[0] - printer.BED / 2, c[1] - printer.BED / 2, 0]); shown.append((mm, col(s)))
        _render(shown, str(out / f"{name}.png"), size=1200, view=(0.6, -1.0, 0.8)); res["render"] = str(out / f"{name}.png")
    if drawing:
        from .drawing import dimension_sheet
        res["drawings"] = []
        for pname, ps in pieces:
            f = out / (f"{name}_{slug(pname)}_dimensions.png" if pname else f"{name}_dimensions.png")
            auto = [("front" if ax == "z" else "top", (p0[0], p0[2] if ax == "z" else p0[1]), (p1[0], p1[2] if ax == "z" else p1[1]), lab)
                    for ax, p0, p1, lab in check_dims[pname]]
            dimension_sheet([(m, col(s)) for _, m, s, *_ in ps], str(f), dims=list(dims if not multi or len(pieces) == 1 else ()) + auto,
                            title=" · ".join(x for x in (title or name, pname) if x), notes=[f"assumed, not measured: {a}" for a in assumed])
            res["drawings"].append(str(f))
        res["drawing"] = res["drawings"][0]
    if slice:
        res["slice"] = s_ = bambu.slice_project(p3mf, out / "_slice")
        if "error" in s_:
            warnings.append(f"slice failed: {s_['error']}")
        else:
            warnings.extend(s_.get("warnings") or [])
            res["report"] = rep = bambu.print_report(s_["sliced"])
            walls_l1 = [v["speed"] for k, v in rep["first_layer"].items() if "wall" in k.lower()]
            if not plain and walls_l1 and max(walls_l1) > 25:
                warnings.append(f"first layer walls run at {max(walls_l1)} mm/s on {mats[0]}; pass first_layer=15-20 for fine features")
    return res


def from_stl(paths, name=None, colours=("#FFFFFF",), **kw):
    """A handed-over STL (or one per colour) as a project. The STL is the model: it is placed, never reshaped, and
    the file itself is never written over (a copy seated on the plate is saved only when it would not replace it)."""
    paths = [pathlib.Path(p).expanduser() for p in ([paths] if isinstance(paths, (str, pathlib.Path)) else paths)]
    for p in paths:
        if not p.exists():
            raise FileNotFoundError(f"no such file: {p}")
    parts = [(p.stem, trimesh.load(p, force="mesh"), i + 1) for i, p in enumerate(paths)]
    cols = list(colours) + ["#111111"] * max(0, len(parts) - len(colours))
    return deliver(name or paths[0].stem, parts, cols, _sources=paths, **kw)
