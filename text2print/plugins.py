"""Plugins: new textures and pictures as small Python files — what the skill writes when someone asks for a pattern
in words ("a koi halftone", "a herringbone weave", "fish-scale knit"). Files live in ~/.text2print/plugins (or
$T2P_PLUGINS); the studio and CLI pick them up on the next catalogue load, no restart.

A file defines any of:

    PICTURE = dict(name="Koi pond", colour=False)        # a picture for halftone / lithophane / CMYK
    def draw(u, v, aspect): ...                          # -> grey 0..1 (1 = dark) or RGB (..., 3)

    WOVEN = dict(name="Herringbone", blurb="...", slots=2, swaps="course", round_only=False)
    def pattern(region, nz, rods): ...                   # lattice API: Course(region, nz, i).lines(theta, ...),
                                                         # rods.line(a, b, slot), rods.path(pts, slot)

    STITCH = dict(name="Fish scales", blurb="...")       # a fabric stitch: displacement of the wall
    def displace(u, layer, band_layers, band, z_frac):   # u: stitch coordinate (1 per stitch, +0.5 on odd bands)
        ...                                              # -> 0..1 of the stitch depth (0 = the wall)

`python -m text2print plugin check FILE` builds every definition on a sample piece, checks it is watertight and
renders a preview PNG. Keys: woven/stitch -> "x_<file stem>", picture -> "lib:<file stem>"."""
import importlib.util
import os
import pathlib
import traceback

HOME = pathlib.Path(os.environ.get("T2P_HOME", pathlib.Path.home() / ".text2print"))
DIR = pathlib.Path(os.environ.get("T2P_PLUGINS", HOME / "plugins"))

_MODS = {}                     # path -> (mtime, module)


def param_values(meta, options):
    """{key: value} for a plugin's PARAMS from the design's options ("pp_<key>"), defaults otherwise."""
    out = {}
    for k, spec in (meta or {}).items():
        v = (options or {}).get(f"pp_{k}", spec.get("default"))
        try:
            v = float(v)
            v = min(max(v, float(spec.get("lo", v))), float(spec.get("hi", v)))
        except (TypeError, ValueError):
            v = spec.get("default")
        out[k] = v
    return out


def call(fn, *args, p=None):
    """Call a plugin function, handing it the slider values if it takes one more argument."""
    import inspect
    try:
        n = len(inspect.signature(fn).parameters)
    except (TypeError, ValueError):
        n = len(args)
    return fn(*args, p or {}) if n > len(args) else fn(*args)
ERRORS = {}                    # stem -> traceback text of the last failed load
_REGISTERED = set()


def _modules():
    out = []
    if not DIR.exists():
        return out
    for p in sorted(DIR.glob("*.py")):
        if p.name.startswith("_"):
            continue
        mt = p.stat().st_mtime
        cached = _MODS.get(str(p))
        if cached and cached[0] == mt:
            out.append((p, cached[1])); continue
        try:
            spec = importlib.util.spec_from_file_location(f"t2p_plugin_{p.stem}", p)
            mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
            _MODS[str(p)] = (mt, mod); ERRORS.pop(p.stem, None); out.append((p, mod))
        except Exception:
            ERRORS[p.stem] = traceback.format_exc(limit=3)
    return out


def pictures():
    return {f"lib:{p.stem}": dict(name=m.PICTURE.get("name", p.stem), kind="program", path=str(p),
                                  colour=bool(m.PICTURE.get("colour")), draw=m.draw, params=getattr(m, "PARAMS", None) or {})
            for p, m in _modules() if hasattr(m, "PICTURE") and callable(getattr(m, "draw", None))}


STITCHES = {}                  # "x_<stem>" -> displace(u, layer, band_layers, band, z_frac)


def load_all():
    """(Re)register woven patterns and stitches into the live registries. Cheap when nothing changed."""
    from . import build, lattice
    seen = set()
    for p, m in _modules():
        key = f"x_{p.stem}"
        if hasattr(m, "WOVEN") and callable(getattr(m, "pattern", None)):
            meta = dict(name=m.WOVEN.get("name", p.stem), blurb=m.WOVEN.get("blurb", "A custom weave"),
                        slots=int(m.WOVEN.get("slots", 2)), swaps=m.WOVEN.get("swaps", "course"),
                        round_only=bool(m.WOVEN.get("round_only", False)), custom=True,
                        params=getattr(m, "PARAMS", None) or {})
            lattice.PATTERNS[key] = dict(meta, fn=m.pattern)
            build.TEXTURES[key] = dict(family="lattice", **meta); seen.add(key)
        elif hasattr(m, "STITCH") and callable(getattr(m, "displace", None)):
            STITCHES[key] = m.displace
            build.TEXTURES[key] = dict(family="fabric", slots=1, swaps="none", custom=True,
                                       name=m.STITCH.get("name", p.stem), blurb=m.STITCH.get("blurb", "A custom stitch"),
                                       params=getattr(m, "PARAMS", None) or {})
            seen.add(key)
        if hasattr(m, "SHAPE"):
            from . import extras, shapes
            S = m.SHAPE; skey = f"s_{p.stem}"
            params = [shapes.Param(*pp) if not isinstance(pp, shapes.Param) else pp for pp in S.get("params", [])]
            if not any(pp.key == "height" for pp in params):
                params.append(shapes.Param("height", "Height", 10, 240, 1, 80))
            if S.get("kind", "round") == "outline" and callable(getattr(m, "outline", None)):
                ext = getattr(m, "extent", None) or (lambda v: max(v.get("width", 100), v.get("depth", 100)) / 2 + 2)
                shp = shapes.PluginOutline(skey, S.get("name", p.stem), S.get("blurb", "A custom shape"), params, m.outline, ext)
            elif callable(getattr(m, "radius", None)):
                shp = shapes.PluginRound(skey, S.get("name", p.stem), S.get("blurb", "A custom shape"), params, m.radius)
            else:
                shp = None
            if shp is not None:
                shapes.SHAPES[skey] = shp; extras.LID_SHAPES.add(skey); seen.add(skey)
    for key in _REGISTERED - seen:                                     # a deleted or broken file: unregister
        from . import extras, shapes
        build.TEXTURES.pop(key, None); lattice.PATTERNS.pop(key, None); STITCHES.pop(key, None)
        shapes.SHAPES.pop(key, None); extras.LID_SHAPES.discard(key)
    _REGISTERED.clear(); _REGISTERED.update(seen)
    return sorted(seen)


def check(path, out_dir=None):
    """Load one plugin file, build what it defines on a sample piece, verify, render previews. -> report dict."""
    from . import build, pictures as pics, thumbs
    path = pathlib.Path(path); out_dir = pathlib.Path(out_dir or path.parent / "previews"); out_dir.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location(f"t2p_check_{path.stem}", path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    report = dict(file=str(path), items=[])
    if hasattr(m, "PICTURE"):
        im = pics.image_for({"picture": f"lib:{path.stem}"}, 3.0, colour=bool(m.PICTURE.get("colour")))
        if im is None:                                                  # not in the library dir: draw directly
            import numpy as np
            from PIL import Image
            u, v = np.meshgrid((np.arange(900) + 0.5) / 900, 1 - (np.arange(300) + 0.5) / 300)
            g = np.asarray(m.draw(u, v, 3.0), float)
            im = Image.fromarray(((1 - np.clip(g, 0, 1)) * 255).astype(np.uint8)) if g.ndim == 2 else \
                Image.fromarray((np.clip(g, 0, 1) * 255).astype(np.uint8), "RGB")
        p = out_dir / f"{path.stem}_picture.png"; im.save(p)
        report["items"].append(dict(kind="picture", preview=str(p)))
    if hasattr(m, "SHAPE"):
        if path.parent.resolve() != DIR.resolve():
            raise ValueError("put shape plugins in the plugin folder, then check them there")
        load_all(); skey = f"s_{path.stem}"
        for tex, cols in (("domes", ["#D2B48C"]), ("twill", ["#8B3A2F", "#EDE3D1"])):
            b = build.make(skey, tex, colours=cols)
            ok = all(mm.is_watertight for _, mm, _, _ in b.parts)
            p = out_dir / f"{path.stem}_{tex}.png"
            thumbs.render([(mm, c) for _, mm, _, c in b.parts], p, size=520, view=(1.0, -0.9, 0.45), zoom=1.1, rake=tex == "domes")
            report["items"].append(dict(kind="shape", key=skey, texture=tex, watertight=ok, size=b.stats["size"],
                                        preview=str(p), verdict="ok" if ok else "leaks"))
    if hasattr(m, "WOVEN") or hasattr(m, "STITCH"):
        keys = load_all(); key = f"x_{path.stem}"
        if path.parent.resolve() != DIR.resolve() or key not in keys:  # checking a file outside the plugin dir
            from . import lattice
            if hasattr(m, "WOVEN"):
                meta = dict(name=m.WOVEN.get("name", path.stem), blurb="", slots=int(m.WOVEN.get("slots", 2)),
                            swaps=m.WOVEN.get("swaps", "course"), round_only=bool(m.WOVEN.get("round_only")))
                lattice.PATTERNS[key] = dict(meta, fn=m.pattern); build.TEXTURES[key] = dict(family="lattice", **meta)
            else:
                STITCHES[key] = m.displace
                build.TEXTURES[key] = dict(family="fabric", slots=1, swaps="none", name=m.STITCH.get("name", path.stem), blurb="")
        shape = "coaster" if hasattr(m, "WOVEN") else "cup"
        dims = {"width": 80, "height": 8, "dish": 0} if shape == "coaster" else {"diameter": 70, "height": 60}
        b = build.make(shape, key, dims, colours=["#8B3A2F", "#EDE3D1"])
        ok = all(mm.is_watertight for _, mm, _, _ in b.parts)
        p = out_dir / f"{path.stem}_{shape}.png"
        thumbs.render([(mm, c) for _, mm, _, c in b.parts], p, size=520, view=(1.0, -0.9, 0.6 if shape == "coaster" else 0.35),
                      zoom=1.1, rake=shape == "cup")
        oh = max(overhang_share(mm) for _, mm, _, _ in b.parts)
        report["items"].append(dict(kind="woven" if hasattr(m, "WOVEN") else "stitch", key=key, shape=shape,
                                    watertight=ok, swaps=b.stats["swaps"], triangles=b.stats["triangles"],
                                    overhang_share=round(oh, 4), preview=str(p),
                                    verdict=("ok" if ok and (hasattr(m, "WOVEN") or oh <= OVERHANG_REF) else
                                             "leaks" if not ok else
                                             "steeper than the built-in stitches: soften layer-to-layer changes")))
    return report


TEMPLATES = {
    "shape": '''"""Shape plugin: {name}."""
import math

SHAPE = dict(name="{title}", blurb="Describe the shape", kind="round",
             params=[("diameter", "Widest", 60, 200, 1, 110), ("height", "Height", 40, 220, 1, 120)])


def radius(v, z):
    """Outer radius (mm) at height z for sizes v. Never lean out faster than ~0.9 mm per mm (it's clamped)."""
    R, h = v["diameter"] / 2, v["height"]
    t = z / h
    return R * (0.7 + 0.3 * math.sin(math.pi * t))
''',
    "picture": '''"""Picture plugin: {name}."""
import numpy as np

PICTURE = dict(name="{title}", colour=False)


def draw(u, v, aspect):
    """u 0..1 across (around a wall), v 0..1 up, aspect = width/height in mm -> darkness 0..1 (1 = front colour)."""
    x, y = u * aspect, v                       # true proportions
    return (np.sin(2 * np.pi * x * 3) * np.sin(2 * np.pi * y * 2) > 0).astype(float)
''',
    "woven": '''"""Woven plugin: {name}."""
import math

from text2print.lattice import Course, _pt

WOVEN = dict(name="{title}", blurb="Describe the weave", slots=2, swaps="course")


def pattern(region, nz, rods):
    for i in range(region.n):                  # one course per rod height; colour by direction (slot 0 / 1)
        c = Course(region, nz, i)
        theta = 0.0 if i % 2 == 0 else math.pi / 2
        for j, t0, t1, pf in c.lines(theta, pitch=nz.pitch):
            rods.line(_pt(pf, t0, c.z), _pt(pf, t1, c.z), i % 2)
''',
    "stitch": '''"""Stitch plugin: {name}."""
import numpy as np

STITCH = dict(name="{title}", blurb="Describe the stitch")


def displace(u, layer, band_layers, band, z_frac):
    """u: 1 per stitch around (odd bands shifted half); layer: 0..band_layers-1 -> 0..1 of the stitch depth.
    Keep layer-to-layer changes gentle (the check reports overhang): a 45 deg law, like every other texture."""
    x = np.mod(u, 1.0); t = (layer + 0.5) / band_layers
    return np.sin(np.pi * x) ** 2 * np.sin(np.pi * t)
''',
}


def new(kind, name):
    """Write a starter plugin into the plugin folder; returns its path."""
    if kind not in TEMPLATES:
        raise ValueError("kind is picture, woven, stitch or shape")
    DIR.mkdir(parents=True, exist_ok=True)
    stem = "".join(ch if ch.isalnum() else "_" for ch in name.lower()).strip("_") or kind
    path = DIR / f"{stem}.py"
    if path.exists():
        raise FileExistsError(path)
    path.write_text(TEMPLATES[kind].format(name=name, title=name.replace("_", " ").title()))
    return path


OVERHANG_REF = 0.30     # every fabric wall is a staircase of layer ledges: built-ins measure knit 0.13,
                        # wave 0.24, zigzag 0.29 (print-proven). A stitch above zigzag's share gets flagged.


def overhang_share(mesh, limit_deg=45.0):
    """Share of the surface (by area) that faces downward steeper than the limit, ignoring the bed face."""
    import numpy as np
    n = mesh.face_normals; a = mesh.area_faces; zc = mesh.triangles_center[:, 2]
    down = (n[:, 2] < -np.sin(np.radians(90 - limit_deg))) & (zc > mesh.bounds[0][2] + 0.05)
    return float(a[down].sum() / max(a.sum(), 1e-9))
