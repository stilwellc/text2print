"""text2print — pick a shape, pick a texture, get a Bambu P2S project.

  python -m text2print studio                       open the picker in the browser
  python -m text2print list                         shapes, textures and which fit which
  python -m text2print make tray twill --set width=117 --colours "#8B3A2F,#EDE3D1" --out ~/Downloads/tray --slice
  python -m text2print thumbs                       re-render the studio's card thumbnails
  python -m text2print sampler --nozzle 0.4 --slice  test plates: a coupon of every texture
  python -m text2print verify fringe 0.4 ok --note "loops fell nicely"   record what a print showed
"""
import argparse
import json
import pathlib
import sys


def main(argv=None):
    ap = argparse.ArgumentParser(prog="text2print", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    st = sub.add_parser("studio"); st.add_argument("--port", type=int, default=7384); st.add_argument("--no-browser", action="store_true")
    sub.add_parser("list")
    mk = sub.add_parser("make")
    mk.add_argument("shape"); mk.add_argument("texture")
    mk.add_argument("--set", action="append", default=[], metavar="KEY=MM", help="shape size, e.g. width=117")
    mk.add_argument("--nozzle", type=float, default=0.4)
    mk.add_argument("--colours", default="", help="comma-separated hex colours, one per slot")
    mk.add_argument("--rim-loops", action="store_true"); mk.add_argument("--floor", default="solid")
    mk.add_argument("--option", action="append", default=[], metavar="KEY=VALUE",
                    help="texture option, e.g. picture=dots, band=2, density=dense, length=long")
    mk.add_argument("--image", help="halftone: your own picture (dark = colour 1), wrapped once around the wall")
    mk.add_argument("--out", default="."); mk.add_argument("--slice", action="store_true")
    mk.add_argument("--render", action="store_true")
    sub.add_parser("thumbs")
    sp = sub.add_parser("sampler"); sp.add_argument("--nozzle", type=float, default=0.4)
    sp.add_argument("--out", default="~/Downloads/text2print/test-plates"); sp.add_argument("--slice", action="store_true")
    vf = sub.add_parser("verify"); vf.add_argument("texture"); vf.add_argument("nozzle", type=float)
    vf.add_argument("result", choices=["ok", "fail"]); vf.add_argument("--note", default="")
    pc = sub.add_parser("pictures", help="list built-in, text and library pictures, and fonts")
    sub.add_parser("catalogue", help="everything a design can use, as JSON (for Claude)")
    pm = sub.add_parser("palette", help="palette match PHOTO: the photo's main colours as filaments")
    pm.add_argument("action", choices=["match"]); pm.add_argument("photo"); pm.add_argument("--k", type=int, default=4)
    dg = sub.add_parser("design", help="design check FILE.json: build, report, render a preview")
    dg.add_argument("action", choices=["check", "slice"]); dg.add_argument("file"); dg.add_argument("--preview", default=None)
    dg.add_argument("--draft", action="store_true")
    pt = sub.add_parser("picture", help="picture text WORDS (preview) | picture prepare PHOTO --out NAME")
    pt.add_argument("kind", choices=["text", "prepare"]); pt.add_argument("words")
    pt.add_argument("--crop", default=None, help="x0,y0,x1,y1 as fractions of the photo")
    pt.add_argument("--mode", default="halftone", choices=["halftone", "litho", "colour"])
    pt.add_argument("--contrast", type=float, default=1.0); pt.add_argument("--gamma", type=float, default=1.0)
    pt.add_argument("--equalize", action="store_true"); pt.add_argument("--posterize", type=int, default=0)
    pt.add_argument("--edges", action="store_true"); pt.add_argument("--threshold", type=float, default=None)
    pt.add_argument("--blur", type=float, default=0.0); pt.add_argument("--subject", action="store_true")
    pt.add_argument("--font", default="futura"); pt.add_argument("--layout", default="center", choices=["center", "repeat", "stack"])
    pt.add_argument("--aspect", type=float, default=3.0); pt.add_argument("--invert", action="store_true")
    pt.add_argument("--out", default="text.png")
    pg = sub.add_parser("plugin", help="plugins: list | check FILE | new picture|woven|stitch|chart|shape NAME")
    pg.add_argument("action", choices=["list", "check", "new"]); pg.add_argument("args", nargs="*")
    pg.add_argument("--out", default=None)
    tt = sub.add_parser("thumb-texture"); tt.add_argument("key"); tt.add_argument("out")   # studio helper
    ts = sub.add_parser("thumb-shape"); ts.add_argument("key"); ts.add_argument("out")
    a = ap.parse_args(argv)

    if a.cmd == "thumb-shape":
        from . import build, plugins, thumbs
        plugins.load_all()
        b = build.make(a.key, "domes", colours=[thumbs.FABRIC_TONE], draft=True)
        thumbs.render([(m, c) for _, m, _, c in b.parts], a.out, size=360, view=(1.0, -0.95, 0.45), zoom=1.12, rake=True)
        return 0
    if a.cmd == "thumb-texture":
        from . import build, plugins, thumbs
        plugins.load_all()
        if build.TEXTURES[a.key]["family"] == "lattice":
            b = build.make("coaster", a.key, {"width": 80, "height": 8, "dish": 0}, colours=["#8B3A2F", "#EDE3D1"], draft=True)
            thumbs.render([(m, c) for _, m, _, c in b.parts], a.out, size=360, view=(1.0, -0.95, 0.8), zoom=1.12)
        else:
            b = build.make("cup", a.key, {"diameter": 70, "height": 80}, colours=[thumbs.FABRIC_TONE], draft=True)
            thumbs.render([(m, c) for _, m, _, c in b.parts], a.out, size=360, view=(1.0, -0.9, 0.35), zoom=1.1, rake=True)
        return 0

    if a.cmd == "pictures":
        from . import pictures
        print("fonts:", ", ".join(k for k, _ in pictures.fonts()))
        for c in pictures.choices():
            print(f"  {c['group']:9s} {c['key']:20s} {c['name']}")
        return 0
    if a.cmd == "catalogue":
        from . import agent
        print(json.dumps(agent.catalogue(), indent=1)); return 0
    if a.cmd == "palette":
        from . import agent
        print(json.dumps(agent.palette_match(pathlib.Path(a.photo).expanduser(), a.k), indent=1)); return 0
    if a.cmd == "design" and a.action == "slice":
        from . import agent
        d = json.loads(pathlib.Path(a.file).expanduser().read_text())
        work = pathlib.Path(a.file).expanduser().with_suffix("")
        print(json.dumps(agent.slice_design(d, str(work) + "_slice"), indent=1, default=str)); return 0
    if a.cmd == "design":
        from . import agent
        d = json.loads(pathlib.Path(a.file).expanduser().read_text())
        prev = a.preview or str(pathlib.Path(a.file).expanduser().with_suffix(".png"))
        print(json.dumps(agent.check_design(d, prev, draft=a.draft), indent=1, default=str)); return 0
    if a.cmd == "picture" and a.kind == "prepare":
        from . import agent, pictures
        out = pathlib.Path(a.out).expanduser()
        if out.suffix.lower() != ".png":                 # a bare name -> the picture library
            pictures.LIB.mkdir(parents=True, exist_ok=True); out = pictures.LIB / f"{out.stem}.png"
        crop = tuple(float(x) for x in a.crop.split(",")) if a.crop else None
        print(agent.prepare(pathlib.Path(a.words).expanduser(), out, crop=crop, mode=a.mode, contrast=a.contrast,
                            gamma=a.gamma, equalize=a.equalize, posterize=a.posterize, edges=a.edges,
                            threshold=a.threshold, blur=a.blur, invert=a.invert, subject=a.subject))
        print(f"picture key: lib:{out.stem}"); return 0
    if a.cmd == "picture":
        from . import pictures
        pictures.render_text(a.words, a.font, a.layout, a.aspect, invert=a.invert).save(a.out); print(a.out); return 0
    if a.cmd == "plugin":
        from . import plugins
        if a.action == "list":
            keys = plugins.load_all()
            print(f"plugin folder: {plugins.DIR}")
            for k in keys:
                from .build import TEXTURES
                print(f"  {k:24s} {TEXTURES[k]['family']:8s} {TEXTURES[k]['name']}")
            for k, m in plugins.pictures().items():
                print(f"  {k:24s} picture  {m['name']}")
            for k, m in plugins.charts().items():
                print(f"  {k:24s} chart    {m['name']}")
            for stem, err in plugins.ERRORS.items():
                print(f"  ! {stem}: {err.strip().splitlines()[-1]}")
            return 0
        if a.action == "check":
            for f in a.args:
                print(json.dumps(plugins.check(f, a.out), indent=1))
            return 0
        if a.action == "new":
            kind, name = (a.args + ["", ""])[:2]
            path = plugins.new(kind, name or "my_" + kind); print(path); return 0

    if a.cmd == "studio":
        from studio.server import run
        return run(port=a.port, browser=not a.no_browser)
    if a.cmd == "sampler":
        from .sampler import write_all
        print(json.dumps(write_all(a.out, a.nozzle, slice_=a.slice), indent=1)); return 0
    if a.cmd == "verify":
        from . import verify
        from .build import TEXTURES
        if a.texture not in TEXTURES:
            print(f"unknown texture {a.texture!r}"); return 2
        verify.record(a.texture, a.nozzle, a.result, a.note); print(f"recorded {a.texture} @ {a.nozzle:g} mm: {a.result}")
        return 0
    if a.cmd == "thumbs":
        from .thumbs import render_all
        return render_all()

    from . import build
    from .shapes import SHAPES
    if a.cmd == "list":
        for s in SHAPES.values():
            fits = [t for t in build.TEXTURES if build.compatible(s.key, t)]
            sizes = ", ".join(f"{p.key} {p.default:g}{p.unit}" for p in s.params)
            print(f"{s.key:8s} {s.name:12s} {sizes}\n          textures: {', '.join(fits)}")
        return 0

    params = {}
    for kv in a.set:
        k, _, v = kv.partition("="); params[k.strip()] = float(v)
    colours = [c.strip() for c in a.colours.split(",") if c.strip()]
    b = build.make(a.shape, a.texture, params, nozzle=a.nozzle, colours=colours,
                   options={"rim_loops": a.rim_loops, "floor": a.floor, "image": a.image,
                            **dict(kv.split("=", 1) for kv in a.option)})
    out = pathlib.Path(a.out).expanduser(); out.mkdir(parents=True, exist_ok=True)
    stem = f"{a.shape}_{a.texture}"
    p3 = b.write_3mf(out / f"{stem}.3mf"); b.write_stls(out, stem)
    result = {"project": str(p3), "params": b.params, "stats": b.stats, "warnings": b.warnings}
    if a.render:
        from .render import render
        render([(m, c) for _, m, _, c in b.parts], out / f"{stem}.png", size=900); result["render"] = str(out / f"{stem}.png")
    if a.slice:
        from .bambu import slice_project
        result["slice"] = slice_project(p3, out / f".slice_{stem}")
    print(json.dumps(result, indent=1, default=float))
    return 0


if __name__ == "__main__":
    sys.exit(main())
