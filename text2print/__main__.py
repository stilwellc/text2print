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
    mk = sub.add_parser("make", help="build a design and write its Bambu Studio project")
    mk.add_argument("shape", nargs="?"); mk.add_argument("texture", nargs="?")
    mk.add_argument("--design", metavar="SPEC", help="a design: JSON file, '-' for stdin, a studio link, or a saved design's name")
    mk.add_argument("--draft", action="store_true", help="quick sketch build (not for printing)")
    mk.add_argument("--preview", action="store_true", help="render a PNG with loops and strands hung as they will fall")
    mk.add_argument("--open", action="store_true", help="open the project in Bambu Studio")
    mk.add_argument("--no-stls", action="store_true"); mk.add_argument("--name", help="file stem (default shape_texture)")
    mk.add_argument("--save", metavar="NAME", help="also add it to the studio's Saved list")
    mk.add_argument("--set", action="append", default=[], metavar="KEY=MM", help="shape size, e.g. width=117")
    mk.add_argument("--nozzle", type=float, default=None)
    mk.add_argument("--colours", default="", help="comma-separated hex colours, one per slot")
    mk.add_argument("--rim-loops", action="store_true"); mk.add_argument("--floor", default="solid")
    mk.add_argument("--option", action="append", default=[], metavar="KEY=VALUE",
                    help="texture option, e.g. picture=dots, band=2, density=dense, length=long")
    mk.add_argument("--image", help="halftone: your own picture (dark = colour 1), wrapped once around the wall")
    mk.add_argument("--out", default="."); mk.add_argument("--slice", action="store_true")
    mk.add_argument("--render", action="store_true", help="render a PNG of the piece as printed")
    sub.add_parser("thumbs")
    op = sub.add_parser("options", help="options TEXTURE: every option that texture takes, its choices and default")
    op.add_argument("texture"); op.add_argument("--json", action="store_true")
    ds = sub.add_parser("designs", help="designs list | show NAME | delete NAME | save SPEC --name NAME")
    ds.add_argument("action", choices=["list", "show", "delete", "save"]); ds.add_argument("spec", nargs="?")
    ds.add_argument("--name"); ds.add_argument("--json", action="store_true")
    lk = sub.add_parser("link", help="link SPEC: a studio link for a design; given a link, the design as JSON")
    lk.add_argument("spec"); lk.add_argument("--port", type=int, default=7384)
    pr = sub.add_parser("printer", help="printer status | test (LAN connection check; never starts a print)")
    pr.add_argument("action", choices=["status", "test"])
    ak = sub.add_parser("ask", help='ask "WORDS": Design with Claude from the command line (starts a Claude run)')
    ak.add_argument("words"); ak.add_argument("--design", metavar="SPEC", help="the design to start from or to review")
    ak.add_argument("--ideas", type=int, default=0, help="ask for N different directions")
    ak.add_argument("--photo", help="a photo to work from; with --review, a photo of the print")
    ak.add_argument("--review", action="store_true", help="review a print of --design from --photo")
    ak.add_argument("--hours", type=float); ak.add_argument("--changes", type=int); ak.add_argument("--grams", type=float)
    tz = sub.add_parser("taste", help="taste like|dislike SPEC [--note ...]: teach it what you like")
    tz.add_argument("verdict", choices=["like", "dislike"]); tz.add_argument("spec"); tz.add_argument("--note", default="")
    sd = sub.add_parser("send", help="send SPEC --confirm: slice a design and START PRINTING it on the configured printer")
    sd.add_argument("spec"); sd.add_argument("--confirm", action="store_true"); sd.add_argument("--out", default=None)
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
        res = agent.slice_design(d, str(work) + "_slice")
        print(json.dumps(res, indent=1, default=str)); return 1 if isinstance(res, dict) and res.get("error") else 0
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
                from .shapes import SHAPES
                if k in TEXTURES:
                    print(f"  {k:24s} {TEXTURES[k]['family']:8s} {TEXTURES[k]['name']}")
                elif k in SHAPES:                                   # a shape plugin is not a texture
                    print(f"  {k:24s} shape    {SHAPES[k].name}")
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
        from . import plugins, printer
        plugins.load_all()
        if a.texture not in TEXTURES:
            print(f"unknown texture {a.texture!r}", file=sys.stderr); return 2
        if round(a.nozzle, 1) not in printer.NOZZLES:
            print(f"no {a.nozzle:g} mm nozzle (have {', '.join(f'{n:g}' for n in printer.NOZZLES)})", file=sys.stderr); return 2
        verify.record(a.texture, a.nozzle, a.result, a.note); print(f"recorded {a.texture} @ {a.nozzle:g} mm: {a.result}")
        return 0
    if a.cmd == "thumbs":
        from .thumbs import render_all
        return render_all()

    from . import build, design as dz
    from .shapes import SHAPES
    if a.cmd == "list":
        for s in SHAPES.values():
            fits = [t for t in build.TEXTURES if build.compatible(s.key, t)]
            sizes = ", ".join(f"{p.key} {p.default:g}{p.unit}" for p in s.params)
            print(f"{s.key:8s} {s.name:12s} {sizes}\n          textures: {', '.join(fits)}")
        return 0
    try:
        return _design_commands(a, build, dz)
    except dz.DesignError as e:                       # a problem with the request: say what to fix, exit 2
        print(json.dumps({"error": str(e)}, indent=1)); print(f"error: {e}", file=sys.stderr)
        return 2


def _value(text):
    """An option value from the command line: JSON when it is JSON (lists, objects, true/false), else the text."""
    t = text.strip()
    if t[:1] in "[{" or t in ("true", "false", "null"):
        try:
            return json.loads(t)
        except json.JSONDecodeError as e:
            from .design import DesignError
            raise DesignError(f"option value looks like JSON but is not valid: {e}") from None
    return text


def _design_commands(a, build, dz):
    from . import store
    if a.cmd == "options":
        from . import plugins
        plugins.load_all()
        if a.texture not in build.TEXTURES:
            raise dz.DesignError(f"unknown texture {a.texture!r}. Textures: {', '.join(build.TEXTURES)}")
        fam = build.TEXTURES[a.texture]["family"]
        rows = [dict(key=k, label=lab, kind=kind, choices=[c[0] for c in (ch or [])], default=d) for k, lab, kind, ch, d in build.OPTIONS.get(fam, [])]
        if a.json:
            print(json.dumps(dict(texture=a.texture, family=fam, options=rows), indent=1)); return 0
        print(f"{a.texture} ({fam}): pass each as --option key=value")
        for r in rows:
            print(f"  {r['key']:16s} {r['label']:22s} {' | '.join(map(str, r['choices'])) or ('true | false' if r['kind'] == 'toggle' else 'text')}   [default {r['default']}]")
        print("  more (lids, engraving, pictures, mixes, charts): python -m text2print catalogue")
        return 0
    if a.cmd == "designs":
        saved = sorted(store.designs(), key=lambda d: -d.get("saved", 0))
        if a.action == "list":
            rows = [dict(id=d["id"], name=d.get("name"), link=d.get("link")) for d in saved]
            if a.json:
                print(json.dumps(rows, indent=1)); return 0
            for r in rows:
                print(f"{r['id']}  {r['name'] or '(unnamed)'}")
            print(f"{len(rows)} saved. Build one: make --design NAME")
            return 0
        if not a.spec:
            raise dz.DesignError(f"designs {a.action} needs a name, an id{' or a design' if a.action == 'save' else ''}")
        if a.action == "save":
            d, b = dz.build_design(dz.load(a.spec), draft=True)
            e = dz.save(d, b, a.name or b.title()); print(json.dumps(dict(saved=e["id"], name=e["name"], link=e["link"]), indent=1)); return 0
        hits = [d for d in saved if d["id"] == a.spec or (d.get("name") or "").lower() == a.spec.lower()]
        if not hits:
            raise dz.DesignError(f"no saved design called {a.spec!r} (see: designs list)")
        if a.action == "show":
            print(json.dumps(dict(id=hits[0]["id"], name=hits[0].get("name"), link=hits[0].get("link"), design=dz.normalise(dz.load(hits[0]["id"]))), indent=1)); return 0
        store.delete_design(hits[0]["id"]); print(json.dumps(dict(deleted=hits[0]["id"], name=hits[0].get("name")))); return 0
    if a.cmd == "link":
        if "://" in a.spec or "shape=" in a.spec:
            print(json.dumps(dz.normalise(dz.from_link(a.spec)), indent=1)); return 0
        url, dropped = dz.to_link(dz.load(a.spec), f"http://127.0.0.1:{a.port}/")
        print(url)
        if dropped:
            print(f"note: a link cannot carry these options: {', '.join(dropped)}", file=sys.stderr)
        return 0
    if a.cmd == "printer":
        from . import lan
        c = store.printer_config(); ready = bool(c.get("ip") and c.get("serial") and c.get("access_code"))
        if a.action == "status":
            print(json.dumps(dict(configured=ready, name=c.get("name", ""), ip=c.get("ip", ""), serial=c.get("serial", "")), indent=1)); return 0
        try:
            print(json.dumps(lan.test(c), indent=1, default=str)); return 0
        except ValueError as e:
            raise dz.DesignError(str(e)) from None
    if a.cmd == "taste":
        from studio import ask
        d = dz.normalise(dz.load(a.spec))
        print(json.dumps(dict(noted=ask.note_taste(a.verdict, d, " ".join(a.note.split())[:300])), indent=1)); return 0
    if a.cmd == "ask":
        import time
        from studio import ask
        from . import plugins
        if not ask.available():
            raise dz.DesignError("the Claude CLI is not installed on this machine")
        cur = dz.normalise(dz.load(a.design)) if a.design else {}
        photo = None
        if a.photo:
            photo = pathlib.Path(a.photo).expanduser()
            if not photo.is_file():
                raise dz.DesignError(f"no such photo: {a.photo}")
            photo = str(photo.resolve())
        if a.review and not (photo and cur):
            raise dz.DesignError("a review needs --design (what was printed) and --photo (how it came out)")
        if len(a.words.strip()) < 3 and not a.review:
            raise dz.DesignError("describe what you want in a few words")
        budget = {k: v for k, v in (("hours", a.hours), ("changes", a.changes), ("grams", a.grams)) if v}
        tid, err = ask.start(a.words.strip()[:2000] or "Here's how it printed.", cur, sys.executable, plugins.DIR, photo=photo,
                             mode="review" if a.review else "design", variations=max(0, a.ideas), budget=budget)
        if err:
            raise dz.DesignError(err)
        seen = 0
        while True:                                         # progress on stderr, the result as JSON on stdout
            st = ask.status(tid) or {}
            for step in (st.get("steps") or [])[seen:]:
                print(f"  {step}", file=sys.stderr)
            seen = len(st.get("steps") or [])
            if st.get("state") != "running":
                break
            time.sleep(1.0)
        print(json.dumps({k: st.get(k) for k in ("state", "result", "error")}, indent=1, default=str))
        return 0 if st.get("state") == "done" else 1
    if a.cmd == "send":
        from . import bambu, lan
        if not a.confirm:
            raise dz.DesignError("sending STARTS A PRINT on the configured printer. Add --confirm when that is what is wanted")
        cfg = store.printer_config()
        try:
            lan.check(cfg)
        except ValueError as e:
            raise dz.DesignError(str(e)) from None
        d, b = dz.build_design(dz.load(a.spec))
        out = pathlib.Path(a.out or "~/Downloads/text2print").expanduser(); out.mkdir(parents=True, exist_ok=True)
        p3 = b.write_3mf(out / f"{d['shape']}_{d['texture']}.3mf")
        res = bambu.slice_project(p3, out / f".slice_{d['shape']}_{d['texture']}")
        if "error" in res:
            print(json.dumps(dict(error="slice failed", slice=res), indent=1)); return 1
        cmd = lan.send(out / f".slice_{d['shape']}_{d['texture']}" / "sliced.3mf", cfg, b.title(), ams_mapping=b.ams_mapping())
        print(json.dumps(dict(sent=cmd["print"]["subtask_name"], project=str(p3), slice=res), indent=1)); return 0

    # make
    if a.design:
        d = dz.load(a.design)
        d = {k: d.get(k) for k in dz.KEYS if d.get(k) is not None}
        if a.shape or a.texture:
            raise dz.DesignError("give either SHAPE TEXTURE or --design, not both (use --set/--option to change a design)")
    else:
        if not (a.shape and a.texture):
            raise dz.DesignError("make needs SHAPE TEXTURE, or --design FILE|LINK|NAME (see: list)")
        d = dict(shape=a.shape, texture=a.texture)
    d.setdefault("params", {}); d.setdefault("options", {})
    for kv in a.set:
        k, sep, v = kv.partition("=")
        if not sep:
            raise dz.DesignError(f"--set wants KEY=MM, got {kv!r}")
        d["params"][k.strip()] = v
    for kv in a.option:
        k, sep, v = kv.partition("=")
        if not sep:
            raise dz.DesignError(f"--option wants KEY=VALUE, got {kv!r}")
        d["options"][k.strip()] = _value(v)
    if a.rim_loops:
        d["options"]["rim_loops"] = True
    if a.floor != "solid":
        d["options"]["floor"] = a.floor
    if a.image:
        img = pathlib.Path(a.image).expanduser()
        if not img.is_file():
            raise dz.DesignError(f"no such picture file: {a.image}")
        d["options"]["image"] = str(img)
    if a.colours:
        d["colours"] = [c.strip() for c in a.colours.split(",") if c.strip()]
    if a.nozzle is not None:
        d["nozzle"] = a.nozzle
    d, b = dz.build_design(d, draft=a.draft)
    out = pathlib.Path(a.out).expanduser(); out.mkdir(parents=True, exist_ok=True)
    stem = a.name or f"{d['shape']}_{d['texture']}"
    p3 = b.write_3mf(out / f"{stem}.3mf")
    link, dropped = dz.to_link(d)
    result = {"project": str(p3), "design": d, "link": link, "params": b.params, "stats": b.stats,
              "warnings": b.warnings + dz.option_notes(d) + (["DRAFT build: a sketch, not for printing"] if a.draft else []),
              "watertight": None if a.draft else all(m.is_watertight for _, m, _, _ in b.parts)}
    if not a.no_stls:
        b.write_stls(out, stem)
    if a.render:                                    # as printed: loops and strands flat, the way the files carry them
        result["render"] = dz.render_png(b, out / f"{stem}.png", hung=False)
    if a.preview:                                   # as it will look: loops and strands hung, the lid on
        result["preview"] = dz.render_png(b, out / f"{stem}_preview.png", hung=True)
    lid_project = out / f"{stem}-lid.3mf"
    if b.extras and b.lid_plate == "own" and lid_project.exists():
        result["lid_project"] = str(lid_project)
    if a.slice and not a.draft:
        from .bambu import slice_project
        result["slice"] = slice_project(p3, out / f".slice_{stem}")
    if a.save:
        result["saved"] = dz.save(d, b, a.save)["id"]
    if a.open:
        import platform
        import subprocess
        if platform.system() == "Darwin":
            subprocess.Popen(["open", "-a", "BambuStudio", str(p3)]); result["opened"] = True
        else:
            result["opened"] = False
    print(json.dumps(result, indent=1, default=float))
    failed = isinstance(result.get("slice"), dict) and "error" in result["slice"]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
