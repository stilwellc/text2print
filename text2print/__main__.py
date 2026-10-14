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
    a = ap.parse_args(argv)

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
