"""text2print studio — a local picker: shape, pattern, size, colours, nozzle -> live 3D preview -> Bambu project.

    python -m text2print studio          (http://127.0.0.1:7384)

Deep links pre-select everything, e.g. /?shape=tray&texture=twill&nozzle=0.4&width=117&c=8B3A2F,EDE3D1"""
import io
import json
import pathlib
import platform
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
import webbrowser
import zipfile
from collections import OrderedDict

import numpy as np
from flask import Flask, Response, abort, jsonify, request, send_file, send_from_directory

from text2print import bambu, build, printer
from text2print.shapes import SHAPES

STATIC = pathlib.Path(__file__).parent / "static"
WORK = pathlib.Path(tempfile.gettempdir()) / "text2print_studio"
DOWNLOADS = pathlib.Path.home() / "Downloads" / "text2print"
app = Flask(__name__, static_folder=None)
JOBS = OrderedDict()                     # id -> {"build": Build, "slice": {...}}
LOCK = threading.Lock()                  # builds are CPU-bound: one at a time
KEEP = 8


def _catalogue():
    shapes = [dict(key=s.key, name=s.name, blurb=s.blurb, families=list(s.families), round=s.round,
                   params=[dict(key=p.key, label=p.label, lo=p.lo, hi=p.hi, step=p.step, default=p.default,
                                unit=p.unit, family=p.family) for p in s.params],
                   thumb=f"/static/thumbs/shape_{s.key}.png") for s in SHAPES.values()]
    textures = [dict(key=k, name=t["name"], blurb=t["blurb"], family=t["family"], slots=t["slots"], swaps=t["swaps"],
                     round_only=bool(t.get("round_only")), thumb=f"/static/thumbs/texture_{k}.png",
                     fits=[s.key for s in SHAPES.values() if build.compatible(s.key, k)])
                for k, t in build.TEXTURES.items()]
    nozzles = [dict(size=n, rod=f"{printer.nozzle(n).rod_w:.2f} × {printer.nozzle(n).rod_h:.2f}",
                    layer=printer.nozzle(n).layer_h, verified=printer.nozzle(n).verified) for n in printer.NOZZLES]
    return dict(printer=dict(name=printer.PRINTER, bed=printer.BED), nozzles=nozzles, shapes=shapes,
                textures=textures, palette=build.PALETTE, colours=build.DEFAULT_COLOURS,
                defaults=dict(shape="tray", texture="twill", nozzle=printer.DEFAULT_NOZZLE),
                slicer=bambu.slicer_available(), mac=platform.system() == "Darwin")


@app.get("/")
def index():
    return send_from_directory(STATIC, "index.html")


@app.get("/static/<path:name>")
def static_file(name):
    return send_from_directory(STATIC, name)


@app.get("/api/catalogue")
def catalogue():
    return jsonify(_catalogue())


@app.post("/api/build")
def api_build():
    req = request.get_json(force=True) or {}
    try:
        with LOCK:
            t = time.time()
            b = build.make(req.get("shape"), req.get("texture"), req.get("params") or {},
                           nozzle=req.get("nozzle", printer.DEFAULT_NOZZLE), colours=req.get("colours") or None,
                           options=req.get("options") or {})
            secs = time.time() - t
    except ValueError as e:
        return jsonify(error=str(e)), 400
    jid = uuid.uuid4().hex[:10]
    JOBS[jid] = {"build": b, "slice": None, "dir": WORK / jid}
    while len(JOBS) > KEEP:
        _, old = JOBS.popitem(last=False); shutil.rmtree(old["dir"], ignore_errors=True)
    return jsonify(id=jid, title=b.title(), params=b.params, stats=b.stats, warnings=b.warnings, seconds=round(secs, 2),
                   parts=[dict(n=i, name=n, slot=s, colour=c, triangles=int(len(m.faces)), url=f"/api/job/{jid}/mesh/{i}")
                          for i, (n, m, s, c) in enumerate(b.parts)])


def _job(jid):
    j = JOBS.get(jid)
    if not j:
        abort(404)
    return j


@app.get("/api/job/<jid>/mesh/<int:n>")
def mesh(jid, n):
    """Indexed mesh as raw bytes: uint32 vertex count, uint32 face count, float32 xyz..., uint32 abc..."""
    m = _job(jid)["build"].parts[n][1]
    v = np.ascontiguousarray(m.vertices, dtype=np.float32); f = np.ascontiguousarray(m.faces, dtype=np.uint32)
    head = np.array([len(v), len(f)], dtype=np.uint32).tobytes()
    return Response(head + v.tobytes() + f.tobytes(), mimetype="application/octet-stream",
                    headers={"Cache-Control": "no-store"})


def _stem(b):
    return f"{b.shape}-{b.texture}-{b.nozzle:g}mm"


def _project(j):
    b = j["build"]; d = j["dir"]; d.mkdir(parents=True, exist_ok=True)
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
    j = _job(jid); b = j["build"]; buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, m, s, _ in b.parts:
            z.writestr(f"{_stem(b)}_{s}.stl", m.export(file_type="stl"))
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name=f"{_stem(b)}_stls.zip", mimetype="application/zip")


@app.post("/api/job/<jid>/open")
def open_in_bambu(jid):
    """Save the project to ~/Downloads/text2print and open it in Bambu Studio."""
    j = _job(jid); p = _project(j); DOWNLOADS.mkdir(parents=True, exist_ok=True)
    dest = DOWNLOADS / p.name; shutil.copy(p, dest)
    if platform.system() == "Darwin":
        app_name = "BambuStudio" if bambu.slicer_available() else None
        subprocess.Popen(["open", "-a", app_name, str(dest)] if app_name else ["open", "-R", str(dest)])
    return jsonify(saved=str(dest))


@app.post("/api/job/<jid>/slice")
def slice_start(jid):
    j = _job(jid)
    if j["slice"] and j["slice"].get("state") in ("running", "done"):
        return jsonify(j["slice"])
    j["slice"] = {"state": "running", "started": time.time()}

    def work():
        try:
            res = bambu.slice_project(_project(j), j["dir"] / "slice")
            j["slice"] = {"state": "error" if "error" in res else "done", **res}
        except Exception as e:                                        # surfaced in the UI, never swallowed
            j["slice"] = {"state": "error", "error": str(e)}
    threading.Thread(target=work, daemon=True).start()
    return jsonify(j["slice"])


@app.get("/api/job/<jid>/slice")
def slice_status(jid):
    return jsonify(_job(jid)["slice"] or {"state": "idle"})


def run(port=7384, browser=True):
    WORK.mkdir(parents=True, exist_ok=True)
    url = f"http://127.0.0.1:{port}/"
    if browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    print(f"text2print studio on {url}")
    app.run(host="127.0.0.1", port=port, threaded=True, debug=False, use_reloader=False)
    return 0
