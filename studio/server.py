"""text2print studio — a local picker: shape, pattern, size, colours, nozzle -> live 3D preview -> Bambu project.

    python -m text2print studio          (http://127.0.0.1:7384)

Deep links pre-select everything, e.g. /?shape=tray&texture=twill&nozzle=0.4&width=117&c=8B3A2F,EDE3D1
Builds run in a worker process: a newer request (e.g. while dragging a slider) cancels the one in flight."""
import base64
import io
import json
import math
import multiprocessing as mp
import pathlib
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import webbrowser
import zipfile
from collections import OrderedDict

import numpy as np
from flask import Flask, Response, abort, jsonify, request, send_file, send_from_directory
from werkzeug.exceptions import HTTPException

from text2print import bambu, build, compose, halftone, lan, printer, sampler, store, verify
from text2print.shapes import SHAPES

STATIC = pathlib.Path(__file__).parent / "static"
WORK = pathlib.Path(tempfile.gettempdir()) / "text2print_studio"
DOWNLOADS = pathlib.Path.home() / "Downloads" / "text2print"
THUMBS = pathlib.Path(__file__).resolve().parent / "static" / "thumbs"
app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024
JOBS = OrderedDict()
PARTS = OrderedDict()                           # id -> an uploaded STL made into a project
KEEP = 8
STL_MAX = 64 * 1024 * 1024
_CTX = mp.get_context("fork")
_RUNNING = {"proc": None, "gen": 0}
_RUN_LOCK = threading.Lock()


# ── errors: every /api answer that is not a success is JSON {"error": "..."} the page can show ────────────────────
class ApiError(Exception):
    def __init__(self, message, code=400):
        super().__init__(message); self.message = message; self.code = code


_HTTP = {403: "Only the studio's own page may call this.", 404: "Not found.", 405: "That address does not take this kind of request.",
         413: "That file is too large for the studio."}


@app.errorhandler(ApiError)
def _api_error(e):
    return jsonify(error=e.message), e.code


@app.errorhandler(HTTPException)
def _http_error(e):
    if not request.path.startswith("/api/"):
        return e
    return jsonify(error=_HTTP.get(e.code) or e.description or e.name), e.code


@app.errorhandler(Exception)
def _crash(e):
    if not request.path.startswith("/api/"):
        raise e
    return jsonify(error=f"{type(e).__name__}: {e}"), 500


def _body():
    """The request's JSON object. Anything else (no body, broken JSON, a list) is a 400 that says so."""
    d = request.get_json(force=True, silent=True)
    if not isinstance(d, dict):
        raise ApiError("The request body must be a JSON object, e.g. {\"shape\": \"tray\", \"texture\": \"twill\"}.")
    return d


_HEX = re.compile(r"#[0-9a-fA-F]{6}")


def _colours(value, what="colours"):
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        raise ApiError(f"{what} must be a list of hex colours like [\"#8B3A2F\", \"#EDE3D1\"].")
    for c in value:
        if not isinstance(c, str) or not _HEX.fullmatch(c):
            raise ApiError(f"{c!r} is not a colour: use six-digit hex like #8B3A2F.")
    return list(value)


def _number(value, what):
    """A finite number (a numeric string is taken as one), or a 400 naming the field."""
    try:
        if isinstance(value, bool) or value is None:
            raise ValueError
        n = float(value)
        if not math.isfinite(n):
            raise ValueError
    except (TypeError, ValueError):
        raise ApiError(f"{what} must be a number (got {value!r}).") from None
    return n


def _nozzle(value):
    n = _number(value, "nozzle")
    if not any(abs(n - k) < 1e-6 for k in printer.NOZZLES):
        raise ApiError(f"nozzle must be one of {', '.join(f'{k:g}' for k in printer.NOZZLES)} mm (got {value!r}).")
    return round(n, 1)


def _design(req):
    """A build request checked before any work starts -> the same request with clean values. A bad colour used to
    build fine and only fail when the project was written; a bad size or nozzle came back as a Python message."""
    from text2print import plugins
    plugins.load_all()
    shape, texture = req.get("shape"), req.get("texture")
    if not isinstance(shape, str) or shape not in SHAPES:
        raise ApiError(f"Unknown shape {shape!r}. Shapes: {', '.join(SHAPES)}.")
    if not isinstance(texture, str) or texture not in build.TEXTURES:
        raise ApiError(f"Unknown texture {texture!r}. Textures: {', '.join(build.TEXTURES)}.")
    params, options = req.get("params") or {}, req.get("options") or {}
    if not isinstance(params, dict):
        raise ApiError("params must be an object of sizes in mm, e.g. {\"width\": 117}.")
    if not isinstance(options, dict):
        raise ApiError("options must be an object, e.g. {\"material\": \"petg\"}.")
    if options.get("lid_colours") is not None:
        _colours(options["lid_colours"], "lid_colours")
    return dict(req, shape=shape, texture=texture, nozzle=_nozzle(req.get("nozzle", printer.DEFAULT_NOZZLE)),
                params={str(k): _number(v, f"size {k!r}") for k, v in params.items()}, options=options,
                colours=_colours(req.get("colours")), draft=bool(req.get("draft")))


# ── catalogue ─────────────────────────────────────────────────────────────────
def _materials():
    """Materials a badge can be asked for: PLA, the Filament choices, and any material a print was recorded in."""
    out = ["pla"] + [k for k, _ in build.MATERIAL[3]]
    out += [k.split("@")[2] for k in verify.load() if k.count("@") == 2]
    return list(dict.fromkeys(out))


def _catalogue():
    from text2print import extras, pictures, plugins
    plugins.load_all()                                         # plugin textures appear without a restart
    shapes = [dict(key=s.key, name=s.name, blurb=s.blurb, families=list(s.families), round=s.round, lid=s.key in extras.LID_SHAPES,
                   params=[dict(key=p.key, label=p.label, lo=p.lo, hi=p.hi, step=p.step, default=p.default,
                                unit=p.unit, family=p.family) for p in s.params],
                   thumb=(f"/static/thumbs/shape_{s.key}.png" if (THUMBS / f"shape_{s.key}.png").exists()
                          else f"/api/thumb/shape/{s.key}"),
                   thumbs={f: f"/static/thumbs/shape_{s.key}__{f}.png" for f in s.families
                           if (THUMBS / f"shape_{s.key}__{f}.png").exists()}) for s in SHAPES.values()]
    textures = []; mats = _materials()
    for k, t in build.TEXTURES.items():
        # a print in PLA says nothing about PETG: one status table per material ("status" is the PLA one)
        by_mat = {m: {n: verify.status(k, n, m)[0] for n in printer.NOZZLES} for m in mats}
        textures.append(dict(key=k, name=t["name"], blurb=t["blurb"], family=t["family"], slots=t["slots"],
                             swaps=t["swaps"], round_only=bool(t.get("round_only")), status=by_mat["pla"], status_by_material=by_mat,
                             thumb=(f"/static/thumbs/texture_{k}.png" if (THUMBS / f"texture_{k}.png").exists()
                                    else f"/api/thumb/texture/{k}"), custom=bool(t.get("custom")), params=t.get("params") or {},
                             fits=[s.key for s in SHAPES.values() if build.compatible(s.key, k)]))
    nozzles = [dict(size=n, rod=f"{printer.nozzle(n).rod_w:.2f} × {printer.nozzle(n).rod_h:.2f}",
                    layer=printer.nozzle(n).layer_h, verified=printer.nozzle(n).verified) for n in printer.NOZZLES]
    options = {fam: [dict(key=k, label=lab, kind=kind, choices=[list(c) for c in (ch or [])], default=d)
                     for k, lab, kind, ch, d in opts] for fam, opts in build.OPTIONS.items()}
    mix = dict(textures=[dict(key=k, name=compose.NAMES[k],
                              family=("plain" if k == "plain" else build.TEXTURES[k]["family"])) for k in compose.MIXABLE],
               presets=[dict(key=k, name=v["name"], bands=v["bands"]) for k, v in compose.PRESETS.items()],
               default=compose.DEFAULT_PRESET, droop_options=[list(c) for c in build.OPTIONS["droop"][0][3]],
               pictures=[[c["key"], c["name"]] for c in pictures.choices() if c["key"] != "text"],
               noises=[[k, v] for k, v in __import__("text2print.shell", fromlist=["x"]).NOISE.items()],
               blends=[[k, v] for k, v in compose.BLEND_STYLES.items()], blendable=sorted(compose.BLENDABLE))
    from text2print import colourwork as cw
    charts = plugins.charts()
    colourwork = dict(motifs=[dict(key=k, name=m["name"], art=m["art"], group="Motifs") for k, m in cw.MOTIFS.items()]
                      + [dict(key=k, name=c["name"], art=c.get("art"), group="Your charts") for k, c in charts.items()],
                      presets=[dict(key=k, name=v["name"], bands=v["bands"]) for k, v in cw.PRESETS.items()],
                      default=cw.DEFAULT_PRESET)
    cfg = store.printer_config()
    return dict(printer=dict(name=printer.PRINTER, bed=printer.BED), nozzles=nozzles, shapes=shapes, options=options,
                mix=mix, colourwork=colourwork, textures=textures, palette=build.PALETTE, colours=build.DEFAULT_COLOURS,
                lid=dict(textures=build.lid_textures(), knobs=[list(k) for k in build.LID_KNOBS]),
                pictures=dict(choices=pictures.choices(), fonts=[list(f) for f in pictures.fonts()],
                              layouts=[list(l) for l in pictures.LAYOUTS], errors=dict(plugins.ERRORS)),
                defaults=dict(shape="tray", texture="twill", nozzle=printer.DEFAULT_NOZZLE),
                materials=[list(c) for c in build.MATERIAL[3]],
                slicer=bambu.slicer_available(), mac=platform.system() == "Darwin",
                lan=dict(configured=bool(cfg.get("ip") and cfg.get("serial") and cfg.get("access_code")),
                         name=cfg.get("name") or "", ip=cfg.get("ip", "")),
                plates=[dict(key=k, name=v["name"], coupons=[_coupon_name(c) for c in v["coupons"]] or
                             ["rims and lids at 0.15 / 0.20 / 0.25 / 0.30 / 0.40 mm a side — notches count the step"])
                        for k, v in sampler.PLATES.items()])


def _coupon_name(c):
    shape, tex, params, opts = c
    if tex == "mix":
        return " + ".join(compose.NAMES[b["texture"]] for b in opts["bands"])
    return build.TEXTURES[tex]["name"]


PORT = [7384]                                   # the port this server answers on (set by run)


def _loopback(netloc):
    """127.0.0.1 or localhost on this server's port. (No port at all is Flask's test client: no socket, no browser.)"""
    host, sep, port = (netloc or "").rpartition(":")
    if not sep:
        return netloc == "localhost" and app.testing
    return host in ("127.0.0.1", "localhost") and port == str(PORT[0])


@app.before_request
def only_this_machine():
    """The studio can write files, launch Claude and start a print, so only its own page may call it.
    Host must be this server: that stops DNS rebinding, because a rebound page still sends its own host name.
    A request that carries an Origin must come from this server: browsers attach Origin to every cross-site
    request that can change state, so another site's script or form is refused. A request with no Origin is not
    from a web page (curl, the tests) and is allowed."""
    if not _loopback(request.host):
        abort(403)
    origin = request.headers.get("Origin")
    if origin is not None and not _loopback(origin.split("://", 1)[-1]):
        abort(403)


@app.get("/")
def index():
    return send_from_directory(STATIC, "index.html")


@app.get("/static/<path:name>")
def static_file(name):
    resp = send_from_directory(STATIC, name)
    if name.endswith((".js", ".css", ".html")):
        resp.headers["Cache-Control"] = "no-cache"
    return resp


@app.get("/api/catalogue")
def catalogue():
    return jsonify(_catalogue())


# ── builds (cancellable worker process) ───────────────────────────────────────
def _slim(b):
    """Before the build crosses the pipe: drop trimesh's derived caches (a 4.6 M-triangle wall carries a
    per-triangle coordinate array, normals, edge tables… several times the mesh itself) and store vertices as
    float32 / faces as int32. Pickling those caches was seconds per full build."""
    import numpy as _np
    seen = set()
    for group in (b.parts, b.preview or [], b.extras, b.assembled):
        for item in group:
            m = item[1]
            if id(m) in seen:
                continue
            seen.add(id(m))
            m._cache.clear()
            m.vertices = _np.ascontiguousarray(m.vertices, dtype=_np.float32)
            m.faces = _np.ascontiguousarray(m.faces, dtype=_np.int32)
            m._cache.clear()


BUILD_CACHE = OrderedDict()            # request -> (status, build, secs): revisiting a design is instant
BUILD_CACHE_N = 12


def _cache_key(req):
    return json.dumps({k: req.get(k) for k in ("shape", "texture", "params", "nozzle", "colours", "options", "draft")},
                      sort_keys=True, default=str)



def _worker(conn, req):
    try:
        t = time.time()
        b = build.make(req.get("shape"), req.get("texture"), req.get("params") or {},
                       nozzle=req.get("nozzle", printer.DEFAULT_NOZZLE), colours=req.get("colours") or None,
                       options=req.get("options") or {}, draft=bool(req.get("draft")))
        _slim(b)
        conn.send(("ok", b, time.time() - t))
    except ValueError as e:
        conn.send(("bad", str(e), 0))
    except Exception as e:                                           # surfaced to the UI, never swallowed
        conn.send(("err", f"{type(e).__name__}: {e}", 0))
    finally:
        conn.close()


def _run_build(req, export=False):
    """export=True: the full build behind a download, a slice or a send. It runs beside the preview builds: it does
    not cancel one and a newer preview does not cancel it (touching a slider used to kill an export in flight)."""
    parent, child = _CTX.Pipe(duplex=False)
    if export:
        proc = _CTX.Process(target=_worker, args=(child, req), daemon=True); proc.start(); child.close()
        try:
            while proc.is_alive() or parent.poll(0.05):
                if parent.poll(0.1):
                    return parent.recv()
        except EOFError:
            pass
        proc.join(timeout=1)
        return ("err", "the build worker stopped unexpectedly", 0)
    with _RUN_LOCK:
        old = _RUNNING["proc"]
        if old is not None and old.is_alive():
            old.terminate()                                          # superseded by this request
        _RUNNING["gen"] += 1; gen = _RUNNING["gen"]
        proc = _CTX.Process(target=_worker, args=(child, req), daemon=True); proc.start()
        _RUNNING["proc"] = proc
    child.close()
    while True:
        if parent.poll(0.05):
            try:
                return parent.recv()
            except EOFError:
                break
        if not proc.is_alive() and not parent.poll(0.05):
            break
    proc.join(timeout=1)
    return ("cancelled", None, 0) if _RUNNING["gen"] != gen else ("err", "the build worker stopped unexpectedly", 0)


def _filaments(b):
    """The filament preset each project colour prints with, in filament order: Bambu's PLA Matte unless the design's
    material says otherwise (one material for all, or one per colour)."""
    cols = b.project_colours()
    stock = (printer.base_config(b.nozzle).get("filament_settings_id") or ["Bambu PLA Matte"])[0]
    ids = list((b.per_filament or {}).get("filament_settings_id") or [])[:len(cols)]
    if len(ids) < len(cols):                                   # a lid's own colour: the first material, as written
        pad = stock
        if ids and b.material:
            try:
                pad = printer.material_settings(b.nozzle, [b.material[0]])["filament_settings_id"][0]
            except Exception:
                pad = ids[0]
        ids += [pad] * (len(cols) - len(ids))
    return [dict(colour=c, preset=(i or stock).split(" @")[0]) for c, i in zip(cols, ids)]


@app.post("/api/build")
def api_build():
    req = _design(_body())
    ck = _cache_key(req)
    if ck in BUILD_CACHE:
        BUILD_CACHE.move_to_end(ck); status, b, secs = BUILD_CACHE[ck]; secs = 0.0
    else:
        status, b, secs = _run_build(req)
        if status == "ok":
            BUILD_CACHE[ck] = (status, b, secs)
            while len(BUILD_CACHE) > BUILD_CACHE_N:
                BUILD_CACHE.popitem(last=False)
    if status == "cancelled":
        return jsonify(error="superseded"), 409
    if status == "bad":
        return jsonify(error=b), 400
    if status == "err":
        return jsonify(error=b), 500
    jid = uuid.uuid4().hex[:10]
    design = {k: req.get(k) for k in ("shape", "texture", "params", "nozzle", "colours", "options")}
    key = store.design_key(dict(design, params=b.params))
    JOBS[jid] = {"build": b, "slice": None, "dir": WORK / jid, "key": key, "design": design}
    while len(JOBS) > KEEP:
        _, old = JOBS.popitem(last=False); shutil.rmtree(old["dir"], ignore_errors=True)
    cached = None if b.draft else store.get_slice(key)
    if cached:
        JOBS[jid]["slice"] = dict({k: v for k, v in cached.items() if k != "preview"}, state="done")
    return jsonify(id=jid, title=b.title(), params=b.params, stats=b.stats, warnings=b.warnings, seconds=round(secs, 2),
                   draft=b.draft, slice=JOBS[jid]["slice"], filaments=_filaments(b),
                   parts=[dict(n=i, name=n, slot=s, colour=c, triangles=int(len(m.faces)), url=f"/api/job/{jid}/mesh/{i}")
                          for i, (n, m, s, c) in enumerate(b.parts)],
                   preview=[dict(n=i, colour=c, url=f"/api/job/{jid}/mesh/{i}?view=draped")
                            for i, (n, m, s, c) in enumerate(b.preview)] if b.preview else None,
                   lid=[dict(n=i, name=n, colour=c, url=f"/api/job/{jid}/mesh/{i}?view=lid")
                        for i, (n, m, s, c) in enumerate(b.assembled)])


def _job(jid):
    j = JOBS.get(jid)
    if not j:
        raise ApiError("That build is no longer in memory (the studio keeps the newest few). Change anything to rebuild it.", 404)
    return j


@app.post("/api/ask")
def api_ask():
    """Design with Claude: a first message, a follow-up in a thread, variations, a set, or a print review."""
    from text2print import plugins
    from . import ask
    if not ask.available():
        return jsonify(error="The Claude CLI isn't installed on this machine."), 400
    body = _body()
    words = str(body.get("request") or "").strip()
    mode = body.get("mode", "design")
    if not isinstance(body.get("current") or {}, dict):
        return jsonify(error="current must be the design as an object."), 400
    variations = int(_number(body.get("variations") or 0, "variations"))
    if len(words) < 3 and mode != "review":
        return jsonify(error="Describe what you want."), 400
    cur = body.get("current") or {}
    photo = None
    img = body.get("photo") or (cur.get("options") or {}).get("image")
    if img:
        pth = store.image_path(img)
        photo = str(pth) if pth and pathlib.Path(pth).exists() else None
    if mode == "review" and not photo:
        return jsonify(error="Add a photo of the print to review it."), 400
    tid, err = ask.start(words[:2000] or "Here's how it printed.", cur, sys.executable, plugins.DIR, photo=photo,
                         thread=body.get("thread"), mode=mode, variations=variations,
                         budget=body.get("budget"))
    if err:
        return jsonify(error=err), 409
    return jsonify(id=tid)


@app.get("/api/ask/<tid>")
def api_ask_status(tid):
    from . import ask
    st = ask.status(tid)
    if st is None:
        abort(404)
    return jsonify(st)


@app.get("/api/ask/<tid>/file/<name>")
def api_ask_file(tid, name):
    """Interim and final previews Claude rendered for a thread."""
    from . import ask
    T = ask.THREADS.get(tid)
    if not T or "/" in name or not name.endswith(".png"):
        abort(404)
    p = T["work"] / name
    if not p.exists():
        abort(404)
    return Response(p.read_bytes(), mimetype="image/png", headers={"Cache-Control": "no-store"})


@app.post("/api/taste")
def api_taste():
    from . import ask
    b = _body()
    if b.get("verdict") not in ("like", "dislike"):
        return jsonify(error="like or dislike"), 400
    d = b.get("design") if isinstance(b.get("design"), dict) else {}
    clean = lambda v: " ".join(str(v).split())[:60]             # one line, short: this text is pasted into prompts
    d = dict(d, shape=clean(d.get("shape", "")), texture=clean(d.get("texture", "")),
             colours=[clean(c)[:9] for c in (d.get("colours") or [])[:4] if isinstance(c, str)])
    return jsonify(line=ask.note_taste(b["verdict"], d, clean(b.get("note") or "")[:300]))


@app.get("/api/thumb/shape/<key>")
def shape_thumb(key):
    """Plugin shapes: a card rendered on first view in a child process (macOS OpenGL), cached per file change."""
    from text2print import plugins
    from text2print.shapes import SHAPES
    plugins.load_all()
    if key not in SHAPES:
        abort(404)
    src = next((p for p in plugins.DIR.glob("*.py") if f"s_{p.stem}" == key), None)
    out = plugins.HOME / "cache" / f"shape_{key}_{int(src.stat().st_mtime) if src else 0}.png"
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        r = subprocess.run([sys.executable, "-m", "text2print", "thumb-shape", key, str(out)],
                           cwd=str(pathlib.Path(__file__).resolve().parent.parent), capture_output=True, timeout=180)
        if r.returncode != 0 or not out.exists():
            abort(500)
    return Response(out.read_bytes(), mimetype="image/png")


@app.get("/api/thumb/texture/<key>")
def texture_thumb(key):
    """Plugin textures: render a card on first view, cached by the plugin file's change time."""
    from text2print import plugins, thumbs
    plugins.load_all()
    if key not in build.TEXTURES:
        abort(404)
    fam = build.TEXTURES[key]["family"]
    src = next((p for p in plugins.DIR.glob("*.py") if f"x_{p.stem}" == key), None)
    stamp = int(src.stat().st_mtime) if src else 0
    out = plugins.HOME / "cache" / f"thumb_{key}_{stamp}.png"
    if not out.exists():
        # OpenGL must run on a process's main thread on macOS (a Flask thread aborts the whole server): render in
        # a short-lived child process, which also keeps any renderer crash out of the studio
        out.parent.mkdir(parents=True, exist_ok=True)
        r = subprocess.run([sys.executable, "-m", "text2print", "thumb-texture", key, str(out)],
                           cwd=str(pathlib.Path(__file__).resolve().parent.parent), capture_output=True, timeout=180)
        if r.returncode != 0 or not out.exists():
            abort(500)
    return Response(out.read_bytes(), mimetype="image/png")


@app.get("/api/job/<jid>/mesh/<int:n>")
def mesh(jid, n):
    """Indexed mesh as raw bytes: uint32 vertex count, uint32 face count, float32 xyz..., uint32 abc..."""
    b = _job(jid)["build"]
    view = request.args.get("view")
    group = b.assembled if view == "lid" else b.preview if view == "draped" and b.preview else b.parts
    if n >= len(group):
        raise ApiError(f"This build has no mesh {n}.", 404)
    m = group[n][1]
    v = np.ascontiguousarray(m.vertices, dtype=np.float32); f = np.ascontiguousarray(m.faces, dtype=np.uint32)
    head = np.array([len(v), len(f)], dtype=np.uint32).tobytes()
    return Response(head + v.tobytes() + f.tobytes(), mimetype="application/octet-stream",
                    headers={"Cache-Control": "no-store"})


def _stem(b):
    return f"{b.shape}-{b.texture}-{b.nozzle:g}mm"


def _full(j):
    """Downloads, slicing and sending always use a full build, even if the preview was a draft."""
    if j["build"].draft:
        status, b, _ = _run_build(dict(j["design"], draft=False), export=True)
        if status != "ok":
            raise ApiError(b or "The full build was cancelled; try again.", {"bad": 400, "cancelled": 409}.get(status, 500))
        j["build"] = b
    return j["build"]


def _project(j):
    b = _full(j); d = j["dir"]; d.mkdir(parents=True, exist_ok=True)
    p = d / f"{_stem(b)}.3mf"
    if not p.exists():
        b.write_3mf(p)
    return p


@app.get("/api/job/<jid>/download")
def download(jid):
    j = _job(jid); p = _project(j)
    return send_file(p, as_attachment=True, download_name=p.name)


@app.get("/api/job/<jid>/stls")
def stls(jid):
    j = _job(jid); b = _full(j); buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, m, s, _ in b.parts:
            z.writestr(f"{_stem(b)}_{s}.stl", m.export(file_type="stl"))
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name=f"{_stem(b)}_stls.zip", mimetype="application/zip")


def _open(path):
    if platform.system() == "Darwin":
        subprocess.Popen(["open", "-a", "BambuStudio", str(path)] if bambu.slicer_available() else ["open", "-R", str(path)])


@app.post("/api/job/<jid>/open")
def open_in_bambu(jid):
    j = _job(jid); p = _project(j); DOWNLOADS.mkdir(parents=True, exist_ok=True)
    dest = DOWNLOADS / p.name; shutil.copy(p, dest); _open(dest)
    return jsonify(saved=str(dest))


def _slice_job(j):
    res = bambu.slice_project(_project(j), j["dir"] / "slice")
    if "error" not in res:
        sl = j["dir"] / "slice" / "sliced.3mf"
        try:                                                    # what actually prints: the sliced paths, front view
            b = j["build"]
            bambu.gcode_preview(sl, j["dir"] / "sliced.png", list(b.colours) + [c for *_, c in b.extras])
            res["preview"] = True
        except Exception as e:
            res["preview_error"] = str(e)[:200]
        store.put_slice(j["key"], res)
    return res


@app.post("/api/job/<jid>/slice")
def slice_start(jid):
    j = _job(jid)
    if j["slice"] and j["slice"].get("state") in ("running", "done"):
        return jsonify(j["slice"])
    j["slice"] = {"state": "running", "started": time.time()}

    def work():
        try:
            res = _slice_job(j)
            j["slice"] = {"state": "error" if "error" in res else "done", **res}
        except Exception as e:
            j["slice"] = {"state": "error", "error": str(e)}
    threading.Thread(target=work, daemon=True).start()
    return jsonify(j["slice"])


@app.get("/api/job/<jid>/slice")
def slice_status(jid):
    return jsonify(_job(jid)["slice"] or {"state": "idle"})


@app.get("/api/job/<jid>/sliced.png")
def sliced_png(jid):
    p = _job(jid)["dir"] / "sliced.png"
    if not p.exists():
        abort(404)
    return Response(p.read_bytes(), mimetype="image/png", headers={"Cache-Control": "no-store"})


@app.get("/api/job/<jid>/report")
def slice_report(jid):
    """Check the sliced file: what its G-code will really do (bambu.print_report) — the first layer's speed per
    feature, the fastest travel, filament changes, time and grams. Read once per slice, then kept with it."""
    j = _job(jid); sl = j["slice"] or {}
    if sl.get("state") != "done":
        raise ApiError("Slice the design first (Get exact print time), then check the sliced file.", 409)
    if not sl.get("report"):
        f = j["dir"] / "slice" / "sliced.3mf"
        if not f.exists():                                      # a slice remembered from an earlier session: its
            j["slice"] = None                                   # numbers were kept, the file was not
            raise ApiError("The sliced file from an earlier session is gone. Slice again, then check it.", 409)
        sl["report"] = bambu.print_report(f)
        store.put_slice(j["key"], {k: v for k, v in sl.items() if k != "state"})
    return jsonify(sl["report"])


# ── a handed-over STL as a project ────────────────────────────────────────────
def _part(pid):
    r = PARTS.get(pid)
    if not r:
        raise ApiError("That part is no longer in memory. Upload the STL again.", 404)
    return r


@app.post("/api/part")
def part_from_stl():
    """An STL (or one per colour) -> a Bambu project with the material's own settings and a dimension drawing.
    The STL is the model: part.from_stl places it on the plate and never reshapes it."""
    import trimesh
    from text2print import part
    try:
        request.max_content_length = STL_MAX                    # meshes outgrow the picture limit (Flask 3.1+)
    except AttributeError:
        pass
    files = [f for f in request.files.getlist("stl") if f and f.filename]
    if not files:
        raise ApiError("Choose an STL file (or one per colour).")
    if len(files) > 4:
        raise ApiError("At most four STLs: one per AMS colour.")
    material = (request.form.get("material") or "pla").strip().lower()
    if material not in ("pla", *printer.MATERIALS):
        raise ApiError(f"Unknown material {material!r}. Materials: pla, {', '.join(printer.MATERIALS)}.")
    colours = _colours([c for c in (request.form.get("colours") or "").split(",") if c]) or ["#FFFFFF"]
    nozzle = _nozzle(request.form.get("nozzle") or printer.DEFAULT_NOZZLE)
    pid = uuid.uuid4().hex[:10]; d = WORK / f"part-{pid}"; (d / "stl").mkdir(parents=True, exist_ok=True)
    try:
        paths = []
        for i, f in enumerate(files):
            if not f.filename.lower().endswith(".stl"):
                raise ApiError(f"{f.filename!r} is not an STL file.")
            stem = re.sub(r"[^A-Za-z0-9_-]+", "_", pathlib.Path(f.filename).stem).strip("_")[:40] or f"part{i + 1}"
            path = d / "stl" / f"{stem}.stl"
            if path.exists():
                path = d / "stl" / f"{stem}_{i + 1}.stl"
            f.save(path); paths.append(path)
            try:
                ok = len(trimesh.load(path, force="mesh").faces) > 0
            except Exception:
                ok = False
            if not ok:
                raise ApiError(f"Couldn't read {f.filename!r} as an STL mesh. Export it again as a binary or ASCII STL.")
        try:
            r = part.from_stl(paths, name=paths[0].stem, colours=colours, material=material, nozzle=nozzle, out=d,
                              slice=False, render=False, drawing=True, stls=False)
        except FileNotFoundError as e:
            raise ApiError(f"{e}. PETG takes its filament preset from Bambu Studio: install it, or pick PLA.") from None
        except ValueError as e:
            raise ApiError(str(e)) from None
    except ApiError:
        shutil.rmtree(d, ignore_errors=True)
        raise
    warnings = list(r.get("warnings") or [])
    if max(r["size"]) > printer.BED:
        warnings.append(f"It is {max(r['size']):g} mm on its longest side — larger than the {printer.BED:g} mm plate.")
    n = len(paths); cols = (colours + ["#111111"] * n)[:n]
    stock = (printer.base_config(nozzle).get("filament_settings_id") or ["Bambu PLA Matte"])[0]
    preset = stock if material == "pla" else printer.MATERIALS[material]
    PARTS[pid] = dict(dir=d, project=pathlib.Path(r["project"]), drawing=pathlib.Path(r["drawing"]))
    while len(PARTS) > KEEP:
        _, old = PARTS.popitem(last=False); shutil.rmtree(old["dir"], ignore_errors=True)
    return jsonify(id=pid, name=paths[0].stem, size=r["size"], warnings=warnings, material=material,
                   filaments=[dict(colour=c, preset=preset.split(" @")[0]) for c in cols],
                   drawing=f"/api/part/{pid}/drawing.png", download=f"/api/part/{pid}/download")


@app.get("/api/part/<pid>/drawing.png")
def part_drawing(pid):
    return Response(_part(pid)["drawing"].read_bytes(), mimetype="image/png", headers={"Cache-Control": "no-store"})


@app.get("/api/part/<pid>/download")
def part_download(pid):
    p = _part(pid)["project"]
    return send_file(p, as_attachment=True, download_name=p.name)


@app.post("/api/part/<pid>/open")
def part_open(pid):
    p = _part(pid)["project"]; DOWNLOADS.mkdir(parents=True, exist_ok=True)
    dest = DOWNLOADS / p.name; shutil.copy(p, dest); _open(dest)
    return jsonify(saved=str(dest))


# ── uploads, saved designs, test plates ───────────────────────────────────────
@app.post("/api/upload")
def upload():
    f = request.files.get("image")
    if not f:
        return jsonify(error="no image"), 400
    try:
        key = store.save_image(f.read())
    except Exception as e:
        return jsonify(error=f"couldn't read that image: {e}"), 400
    return jsonify(id=key, url=f"/api/image/{key}")


@app.get("/api/image/<key>")
def image(key):
    p = store.image_path(key)
    if not p:
        abort(404)
    return send_file(p, mimetype="image/png")


@app.get("/api/designs")
def designs():
    return jsonify(sorted(store.designs(), key=lambda d: -d.get("saved", 0)))


@app.post("/api/designs")
def save_design():
    d = _body()
    thumb = d.pop("thumb", None)
    entry = store.save_design({k: d.get(k) for k in ("id", "name", "link", "design", "stats")})
    if isinstance(thumb, str) and thumb.startswith("data:image/png;base64,"):
        try:
            store.save_thumb(entry["id"], base64.b64decode(thumb.split(",", 1)[1]))
        except ValueError:
            pass                                                # a broken thumbnail never loses the design
    return jsonify(entry)


@app.delete("/api/designs/<did>")
def delete_design(did):
    store.delete_design(did)
    return jsonify(ok=True)


@app.get("/api/designs/<did>/thumb")
def design_thumb(did):
    p = store.thumb_path(did)
    if not p:
        abort(404)
    return send_file(p, mimetype="image/png")


@app.post("/api/plates")
def plates():
    req = _body()
    nozzle = _nozzle(req.get("nozzle", printer.DEFAULT_NOZZLE)); key = req.get("plate")
    if key is not None and key not in sampler.PLATES:
        raise ApiError(f"Unknown test plate {key!r}. Plates: {', '.join(sampler.PLATES)}.")
    out = DOWNLOADS / "test-plates"; out.mkdir(parents=True, exist_ok=True)
    keys = [key] if key in sampler.PLATES else list(sampler.PLATES)
    made = []
    for k in keys:
        path = out / f"test-plate-{k}-{nozzle:g}mm.3mf"
        sampler.write(k, path, nozzle)
        made.append(str(path))
    if len(made) == 1:
        _open(made[0])
    elif platform.system() == "Darwin":
        subprocess.Popen(["open", str(out)])
    return jsonify(saved=made)


# ── printer (LAN) ─────────────────────────────────────────────────────────────
@app.get("/api/printer")
def printer_get():
    c = store.printer_config()
    return jsonify(configured=bool(c.get("ip") and c.get("serial") and c.get("access_code")),
                   name=c.get("name", ""), ip=c.get("ip", ""), serial=c.get("serial", ""))


@app.post("/api/printer")
def printer_set():
    c = store.save_printer_config(_body())
    return jsonify(configured=bool(c["ip"] and c["serial"] and c["access_code"]), name=c["name"], ip=c["ip"])


@app.post("/api/printer/test")
def printer_test():
    """Connection check — never starts a print."""
    try:
        return jsonify(lan.test(store.printer_config()))
    except ValueError as e:
        return jsonify(error=str(e)), 400


@app.post("/api/job/<jid>/send")
def send(jid):
    req = _body()
    if req.get("confirm") is not True:
        return jsonify(error="sending starts a print — confirm first"), 400
    j = _job(jid); cfg = store.printer_config()
    try:
        lan.check(cfg)
        res = _slice_job(j)
        if "error" in res:                                       # never send a project the slicer rejected
            return jsonify(error=f"the slicer could not slice it: {res['error']}"), 502
        sliced = j["dir"] / "slice" / "sliced.3mf"
        b = j["build"]
        cmd = lan.send(sliced, cfg, b.title(), ams_mapping=b.ams_mapping())
    except Exception as e:
        return jsonify(error=str(e)), 502
    return jsonify(ok=True, sent=cmd["print"]["subtask_name"])


def run(port=7384, browser=True):
    WORK.mkdir(parents=True, exist_ok=True)
    PORT[0] = int(port)
    url = f"http://127.0.0.1:{port}/"
    if browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    print(f"text2print studio on {url}")
    app.run(host="127.0.0.1", port=port, threaded=True, debug=False, use_reloader=False)
    return 0
