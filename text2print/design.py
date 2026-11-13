"""A design as data: {shape, texture, params, nozzle, colours, options}. Everything the studio can build is one of
these, so the command line (and an agent driving it) can do what the picker does: load a design from a JSON file,
a studio share link or a saved design; build it; write the project; render, slice, save and link it."""
import json
import pathlib
import sys
import urllib.parse

STUDIO = "http://127.0.0.1:7384/"
KEYS = ("shape", "texture", "params", "nozzle", "colours", "options")


class DesignError(ValueError):
    """A problem with the request itself (unknown shape, bad option, unreadable file): report it, exit 2."""


def _toggles():
    from . import build
    return {o[0] for opts in build.OPTIONS.values() for o in opts if o[2] == "toggle"} | {"text_invert", "picture_invert"}


def from_link(url):
    """A studio share link (or just its query string) -> design. Size keys of the shape become params; `mix` and
    `chart` carry JSON; everything else is an option."""
    from .shapes import SHAPES
    q = urllib.parse.urlparse(url).query if "?" in url or "://" in url else url
    pairs = urllib.parse.parse_qsl(q.lstrip("?"), keep_blank_values=False)
    d = dict(pairs)
    if d.get("shape") not in SHAPES:
        raise DesignError(f"the link names no known shape (shape={d.get('shape')!r})")
    sizes = {p.key for p in SHAPES[d["shape"]].params}; toggles = _toggles()
    out = dict(shape=d["shape"], texture=d.get("texture", ""), params={}, nozzle=float(d.get("nozzle", 0.4)), colours=[], options={})
    for k, v in pairs:
        if k in ("shape", "texture", "nozzle"):
            continue
        if k == "c":
            out["colours"] = ["#" + h.strip().lstrip("#") for h in v.split(",") if h.strip()]
        elif k == "mix":
            out["options"]["bands"] = _json(v, "mix")
        elif k == "chart":
            out["options"]["chart"] = _json(v, "chart")
        elif k in sizes:
            out["params"][k] = float(v)
        elif k in toggles:
            out["options"][k] = v == "1"
        elif v[:1] in "[{":                                   # a structured value (a hand-set loop spec, a material list)
            try:
                out["options"][k] = json.loads(v)
            except json.JSONDecodeError:
                out["options"][k] = v
        else:
            out["options"][k] = v
    return out


def _json(text, what):
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise DesignError(f"{what} is not valid JSON: {e}") from None


def to_link(design, base=STUDIO):
    """Design -> a studio share link. -> (url, [option keys that a link cannot carry])."""
    from .shapes import SHAPES
    d = normalise(design); S = SHAPES[d["shape"]]
    q = [("shape", d["shape"]), ("texture", d["texture"]), ("nozzle", f"{d['nozzle']:g}")]
    defaults = {p.key: p.default for p in S.params}
    q += [(k, f"{float(v):g}") for k, v in d["params"].items() if k in defaults and float(v) != defaults[k]]
    if d["colours"]:
        q.append(("c", ",".join(c.lstrip("#") for c in d["colours"])))
    dropped = []
    for k, v in d["options"].items():
        if k == "bands":
            q.append(("mix", json.dumps(v, separators=(",", ":"))))
        elif k == "chart" and isinstance(v, list):
            q.append(("chart", json.dumps(v, separators=(",", ":"))))
        elif isinstance(v, bool):
            q.append((k, "1" if v else "0"))
        elif isinstance(v, (str, int, float)):
            if v != "":
                q.append((k, str(v)))
        elif isinstance(v, (dict, list)):
            q.append((k, json.dumps(v, separators=(",", ":"))))
        elif v is not None:
            dropped.append(k)
    return base.rstrip("/") + "/?" + urllib.parse.urlencode(q), dropped


def normalise(d):
    """Fill the gaps, check the names, coerce the types. Raises DesignError with a message that says what to fix."""
    from . import build, plugins
    from .shapes import SHAPES
    plugins.load_all()
    if not isinstance(d, dict):
        raise DesignError("a design is a JSON object: {shape, texture, params, nozzle, colours, options}")
    unknown = sorted(set(d) - set(KEYS) - {"name", "id", "link", "stats", "saved", "design"})
    if unknown:
        raise DesignError(f"unknown design keys {unknown}; sizes go in params, everything else in options")
    shape, texture = d.get("shape"), d.get("texture")
    if shape not in SHAPES:
        raise DesignError(f"unknown shape {shape!r}. Shapes: {', '.join(SHAPES)}")
    if texture not in build.TEXTURES:
        raise DesignError(f"unknown texture {texture!r}. Textures: {', '.join(build.TEXTURES)}")
    if not build.compatible(shape, texture):
        fits = [t for t in build.TEXTURES if build.compatible(shape, t)]
        raise DesignError(f"{texture} does not fit a {shape}. On a {shape}: {', '.join(fits)}")
    sizes = {p.key: p for p in SHAPES[shape].params}
    params = {}
    for k, v in (d.get("params") or {}).items():
        if k not in sizes:
            raise DesignError(f"{shape} has no size {k!r}. Sizes: {', '.join(f'{p.key} ({p.lo:g}-{p.hi:g})' for p in sizes.values())}")
        try:
            params[k] = float(v)
        except (TypeError, ValueError):
            raise DesignError(f"size {k} must be a number, got {v!r}") from None
    colours = list(d.get("colours") or [])
    for c in colours:
        if not (isinstance(c, str) and len(c) == 7 and c[0] == "#" and all(ch in "0123456789abcdefABCDEF" for ch in c[1:])):
            raise DesignError(f"colour {c!r} is not a #RRGGBB hex value")
    try:
        nozzle = float(d.get("nozzle") or 0.4)
    except (TypeError, ValueError):
        raise DesignError(f"nozzle must be a number, got {d.get('nozzle')!r}") from None
    from . import printer
    if round(nozzle, 1) not in printer.NOZZLES:
        raise DesignError(f"no profile for a {nozzle:g} mm nozzle. Nozzles: {', '.join(f'{n:g}' for n in printer.NOZZLES)}")
    return dict(shape=shape, texture=texture, params=params, nozzle=nozzle, colours=colours, options=dict(d.get("options") or {}))


def option_notes(design):
    """Soft checks on options: values outside a picker option's choices. -> [messages] (never an error: plenty of
    options are free-form or not in the picker)."""
    from . import build
    fam = build.TEXTURES[design["texture"]]["family"]; notes = []
    for key, label, kind, choices, _default in build.OPTIONS.get(fam, []):
        v = design["options"].get(key)
        if v is None or kind != "seg" or not choices or isinstance(v, (dict, list)):
            continue
        allowed = [str(c[0]) for c in choices]
        if str(v) not in allowed:
            notes.append(f"option {key}={v!r} is not one of {', '.join(allowed)}")
    return notes


def load(spec):
    """A design from: a JSON file, '-' (stdin), a studio link, or the name or id of a saved design."""
    from . import store
    if spec == "-":
        return _json(sys.stdin.read(), "stdin")
    if "://" in spec or spec.startswith("?") or "shape=" in spec:
        return from_link(spec)
    p = pathlib.Path(spec).expanduser()
    if p.is_file():
        d = _json(p.read_text(), str(p))
        return d.get("design") if isinstance(d.get("design"), dict) else d
    hits = [s for s in store.designs() if s.get("id") == spec or (s.get("name") or "").lower() == spec.lower()]
    if not hits:
        raise DesignError(f"{spec!r} is not a file, a studio link, or a saved design (see: designs list)")
    s = hits[-1]
    return s["design"] if isinstance(s.get("design"), dict) else from_link(s.get("link", ""))


def build_design(design, draft=False):
    from . import build
    d = normalise(design)
    try:
        return d, build.make(d["shape"], d["texture"], d["params"], nozzle=d["nozzle"], colours=d["colours"] or None,
                             options=dict(d["options"]), draft=draft)
    except (ValueError, KeyError, TypeError, IndexError, FileNotFoundError) as e:
        raise DesignError(f"could not build it ({type(e).__name__}): {e}") from None


def view_of(b, hung=True):
    """The meshes to show: loops and strands hung as they will fall (when there are any), plus a lid on its piece."""
    return [(m, c) for _, m, _, c in ((b.preview if hung and b.preview else b.parts) + list(b.assembled)) if m is not None and len(m.faces)]


def render_png(b, path, size=900, hung=True):
    from .thumbs import render
    s = b.stats["size"]; tall = s[2] > 0.6 * max(s[:2])
    parts = view_of(b, hung)
    render(parts, str(path), size=size, view=(1.0, -0.9, 0.3 if tall else 0.7), zoom=1.08, rake=len({c for _, c in parts}) == 1)
    return str(path)


def save(design, b, name):
    """Add to the studio's Saved list (with a thumbnail). -> the saved entry."""
    import tempfile
    from . import store
    d = normalise(design); link, _ = to_link(d)
    entry = store.save_design(dict(name=name, link=link, design=d, stats=b.stats))
    with tempfile.TemporaryDirectory() as tmp:
        png = pathlib.Path(tmp) / "t.png"; render_png(b, png, size=360)
        store.save_thumb(entry["id"], png.read_bytes())
    return entry
