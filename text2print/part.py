"""Parts that are not in the catalogue: a bracket, a sleeve, a stand, a clip, a piece with your own outline.
Model the mesh however suits it (manifold3d, CadQuery, trimesh, a handed-over STL), then hand it to deliver():

    from text2print import part
    r = part.deliver("pipe_sleeve", [("Sleeve", mesh, 1)], colours=["#FFFFFF"], material="petg", slice=True,
                     check={"length": (30.0, "z"), "bell": (45.0, "x")})

deliver() does what every one-off script used to copy by hand, and gets the parts right that were missed when it was
copied: the material's own speeds (PETG at PLA speeds printed rough, twice), a slow first layer when asked, the right
list shapes, one object with one part per colour, STLs, a render, a dimension drawing, the slice, and a report of
what the sliced file will really do."""
import pathlib

import numpy as np
import trimesh

from . import bambu, printer

SHOW = {"#FFFFFF": "#F2F0EA"}                       # pure white vanishes in a render


def deliver(name, parts, colours, material="pla", out=None, overrides=None, nozzle=printer.DEFAULT_NOZZLE, layer_h=None,
            walls=3, infill="20%", first_layer=None, position=None, slice=False, render=True, drawing=True, dims=(),
            check=None, tol=0.05, plate=None, first_layer_order=None, title=None, stls=True, base_overrides=None):
    """Write a functional part as a Bambu Studio project in ~/Downloads/<name>/ (Collin's rule) and report on it.

    parts      [(name, mesh, slot)] — one mesh per colour, slot = the 1-based index into colours. All the parts go in
               ONE object (separate objects per colour leave empty layers and Bambu refuses to slice). Meshes are in
               the pose they print, z = 0 on the plate; they are centred on the plate together.
    material   "pla", "petg", ... or one per colour. Sets the filament preset and the process speeds.
    overrides  slicer settings on top of printer.solid_part(...) (scalars are fine); base_overrides replaces
               solid_part entirely, e.g. printer.overrides(nozzle, "lattice", slots=2, material=material) for rods.
    first_layer  mm/s for layer one, for small or fine features on the textured plate (PETG rods: 15).
    first_layer_order  filaments in the order they print on layer one, e.g. (2, 1) = black before white.
    check      {label: (expected_mm, axis)} with axis "x" | "y" | "z": asserts the overall size on that axis within
               tol, so a fit part cannot be delivered at the wrong size. Use dims for anything else in the drawing.
    -> {"project", "stls", "render", "drawing", "size", "slice", "report", "warnings"}"""
    out = pathlib.Path(out).expanduser() if out else pathlib.Path.home() / "Downloads" / name
    out.mkdir(parents=True, exist_ok=True)
    parts = [(n, m, int(s)) + tuple(rest) for n, m, s, *rest in parts]
    colours = list(colours); n_col = max(s for _, _, s, *_ in parts)
    if n_col > len(colours):
        raise ValueError(f"a part uses colour slot {n_col} but only {len(colours)} colours were given")
    warnings = []
    for n, m, *_ in parts:
        if not m.is_watertight:
            warnings.append(f"{n}: the mesh is not watertight (many separate rods in one part read that way; a solid should not)")
    allv = np.vstack([np.asarray(m.vertices) for _, m, *_ in parts]); lo, hi = allv.min(0), allv.max(0)
    shift = np.array([-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]])
    if np.abs(shift).max() > 1e-6:
        for _, m, *_ in parts:
            m.apply_translation(shift)
    size = (hi - lo).astype(float)
    for label, (want, axis) in (check or {}).items():
        got = float(size["xyz".index(axis)])
        if abs(got - want) > tol:
            raise ValueError(f"{label}: built {got:.2f} mm on {axis}, wanted {want:.2f}")
    mats = [material] * n_col if isinstance(material, str) else list(material)[:n_col]
    over = dict(base_overrides) if base_overrides is not None else printer.solid_part(nozzle, layer_h, walls, infill, colours=n_col)
    over.update({k: (str(v) if not isinstance(v, (list, tuple, dict)) else v) for k, v in (overrides or {}).items()})
    plain = all(str(m).strip().lower() in ("pla", "") for m in mats)
    if not plain:
        over.update(printer.process_for(nozzle, mats, over))
    if first_layer:
        over.update(printer.slow_first_layer(nozzle, first_layer, over))
    half = float(max(size[0], size[1]) / 2)
    if position is None:                               # two colours: leave the front-right corner to the prime tower
        position = (printer.BED / 2 - (18 if n_col > 1 and half > 60 else 0), printer.BED / 2)
    pm = dict(plate or {})
    if first_layer_order:
        pm["first_layer_print_sequence"] = " ".join(str(int(i)) for i in first_layer_order)
    p3mf = out / f"{name}.3mf"
    bambu.write_3mf(str(p3mf), [{"name": title or name, "position": tuple(position), "parts": parts}], title=title or name,
                    colours=tuple(colours[:n_col]), overrides=over, base=printer.base_config(nozzle),
                    per_filament=None if plain else printer.material_settings(nozzle, mats), plate=pm or None)
    res = {"project": str(p3mf), "size": [round(float(x), 2) for x in size], "warnings": warnings, "stls": []}
    shown = [(m, SHOW.get(colours[s - 1].upper(), colours[s - 1])) for _, m, s, *_ in parts]
    if stls:
        for n, m, s, *_ in parts:
            f = out / (f"{name}.stl" if len(parts) == 1 else f"{name}_{n.lower().replace(' ', '_')}.stl")
            m.export(f); res["stls"].append(str(f))
    if render:
        from .render import render as _render
        _render(shown, str(out / f"{name}.png"), size=1200, view=(0.6, -1.0, 0.8)); res["render"] = str(out / f"{name}.png")
    if drawing:
        from .drawing import dimension_sheet
        dimension_sheet(shown, str(out / f"{name}_dimensions.png"), dims=dims, title=title or name)
        res["drawing"] = str(out / f"{name}_dimensions.png")
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
    """A handed-over STL (or one per colour) as a project. The STL is the model: it is placed, never reshaped."""
    paths = [pathlib.Path(p).expanduser() for p in ([paths] if isinstance(paths, (str, pathlib.Path)) else paths)]
    parts = [(p.stem, trimesh.load(p, force="mesh"), i + 1) for i, p in enumerate(paths)]
    cols = list(colours) + ["#111111"] * max(0, len(parts) - len(colours))
    return deliver(name or paths[0].stem, parts, cols, **kw)
