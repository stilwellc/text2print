"""text2print studio — a local picker: shape, pattern, size, colours, nozzle -> live 3D preview -> Bambu project.

    python -m text2print studio          (http://127.0.0.1:7384)

Deep links pre-select everything, e.g. /?shape=tray&texture=twill&nozzle=0.4&width=117&c=8B3A2F,EDE3D1
Builds run in a worker process: a newer request (e.g. while dragging a slider) cancels the one in flight."""
import base64
import io
import json
import multiprocessing as mp
import pathlib
import platform
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

from text2print import bambu, build, compose, halftone, lan, printer, sampler, store, verify
from text2print.shapes import SHAPES

STATIC = pathlib.Path(__file__).parent / "static"
WORK = pathlib.Path(tempfile.gettempdir()) / "text2print_studio"
DOWNLOADS = pathlib.Path.home() / "Downloads" / "text2print"
THUMBS = pathlib.Path(__file__).resolve().parent / "static" / "thumbs"
app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024
JOBS = OrderedDict()
KEEP = 8
_CTX = mp.get_context("fork")
_RUNNING = {"proc": None, "gen": 0}
_RUN_LOCK = threading.Lock()


# ── catalogue ─────────────────────────────────────────────────────────────────
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
    textures = []
    for k, t in build.TEXTURES.items():
        st = {n: verify.status(k, n)[0] for n in printer.NOZZLES}
        textures.append(dict(key=k, name=t["name"], blurb=t["blurb"], family=t["family"], slots=t["slots"],
                             swaps=t["swaps"], round_only=bool(t.get("round_only")), status=st,
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


def _run_build(req):
    parent, child = _CTX.Pipe(duplex=False)
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


@app.post("/api/build")
def api_build():
    req = request.get_json(force=True) or {}
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
                   draft=b.draft, slice=JOBS[jid]["slice"],
                   parts=[dict(n=i, name=n, slot=s, colour=c, triangles=int(len(m.faces)), url=f"/api/job/{jid}/mesh/{i}")
                          for i, (n, m, s, c) in enumerate(b.parts)],
                   preview=[dict(n=i, colour=c, url=f"/api/job/{jid}/mesh/{i}?view=draped")
                            for i, (n, m, s, c) in enumerate(b.preview)] if b.preview else None,
                   lid=[dict(n=i, name=n, colour=c, url=f"/api/job/{jid}/mesh/{i}?view=lid")
                        for i, (n, m, s, c) in enumerate(b.assembled)])


def _job(jid):
    j = JOBS.get(jid)
    if not j:
        abort(404)
    return j


@app.post("/api/ask")
def api_ask():
    """Design with Claude: a first message, a follow-up in a thread, variations, a set, or a print review."""
    from text2print import plugins
    from . import ask
    if not ask.available():
        return jsonify(error="The Claude CLI isn't installed on this machine."), 400
    body = request.get_json(force=True) or {}
    words = (body.get("request") or "").strip()
    mode = body.get("mode", "design")
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
                         thread=body.get("thread"), mode=mode, variations=int(body.get("variations") or 0),
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
    b = request.get_json(force=True) or {}
    if b.get("verdict") not in ("like", "dislike"):
        return jsonify(error="like or dislike"), 400
    return jsonify(line=ask.note_taste(b["verdict"], b.get("design"), (b.get("note") or "")[:300]))


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
    m = (b.assembled if view == "lid" else b.preview if view == "draped" and b.preview else b.parts)[n][1]
    v = np.ascontiguousarray(m.vertices, dtype=np.float32); f = np.ascontiguousarray(m.faces, dtype=np.uint32)
    head = np.array([len(v), len(f)], dtype=np.uint32).tobytes()
    return Response(head + v.tobytes() + f.tobytes(), mimetype="application/octet-stream",
                    headers={"Cache-Control": "no-store"})


def _stem(b):
    return f"{b.shape}-{b.texture}-{b.nozzle:g}mm"


def _full(j):
    """Downloads, slicing and sending always use a full build, even if the preview was a draft."""
    if j["build"].draft:
        status, b, _ = _run_build(dict(j["design"], draft=False))
        if status != "ok":
            abort(409 if status == "cancelled" else 500)
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
            import re
            import zipfile
            g = zipfile.ZipFile(sl).read("Metadata/plate_1.gcode").decode(errors="ignore")
            res["changes"] = len(re.findall(r"^M620 S\dA", g, re.M))
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
    d = request.get_json(force=True) or {}
    thumb = d.pop("thumb", None)
    entry = store.save_design({k: d.get(k) for k in ("id", "name", "link", "design", "stats")})
    if thumb and thumb.startswith("data:image/png;base64,"):
        store.save_thumb(entry["id"], base64.b64decode(thumb.split(",", 1)[1]))
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
    req = request.get_json(force=True) or {}
    nozzle = float(req.get("nozzle", 0.4)); key = req.get("plate")
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
    c = store.save_printer_config(request.get_json(force=True) or {})
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
    req = request.get_json(force=True) or {}
    if req.get("confirm") is not True:
        return jsonify(error="sending starts a print — confirm first"), 400
    j = _job(jid); cfg = store.printer_config()
    try:
        lan.check(cfg)
        _slice_job(j)
        sliced = j["dir"] / "slice" / "sliced.3mf"
        b = j["build"]
        cmd = lan.send(sliced, cfg, b.title(), ams_mapping=list(range(len(b.parts))))
    except Exception as e:
        return jsonify(error=str(e)), 502
    return jsonify(ok=True, sent=cmd["print"]["subtask_name"])


def run(port=7384, browser=True):
    WORK.mkdir(parents=True, exist_ok=True)
    url = f"http://127.0.0.1:{port}/"
    if browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    print(f"text2print studio on {url}")
    app.run(host="127.0.0.1", port=port, threaded=True, debug=False, use_reloader=False)
    return 0
