"""Bambu Studio project 3MF writer — any number of objects, each made of parts pre-assigned to
filament slots, placed on the plate, with a full project_settings.config so printer, process and
filament presets travel with the file (generalised from megalodon_bambu.py; same verified layout).

    write_3mf("x.3mf", objects=[
        {"name": "lid",   "parts": [("body", mesh, 1), ("inlay", mesh2, 2)], "position": (128, 180)},
        {"name": "frame", "parts": [("frame", mesh3, 1)],                    "position": (128,  70)},
    ])
Meshes are in print orientation with Z >= 0; `position` is the object's XY centre on the bed."""
import io
import json
import math
import pathlib
import uuid
import zipfile
from xml.sax.saxutils import escape as _esc
import numpy as np

APP = "BambuStudio-02.09.01.70"
BASE_SETTINGS = pathlib.Path(__file__).with_name("data") / "p2s_0.4.json"   # P2S 0.4 nozzle + 0.20mm
#   Standard + Bambu PLA Basic x2, as exported by the Bambu Studio CLI (--export-settings)
DEFAULT_OVERRIDES = {
    "wall_loops": "3", "sparse_infill_density": "15%", "sparse_infill_pattern": "gyroid",
    "bottom_shell_layers": "4", "top_shell_layers": "5", "seam_position": "back",
    "elefant_foot_compensation": "0.15", "enable_prime_tower": "1", "timelapse_type": "0",
}
# PLA bed: 60 °C on the PEI plates, first layer too (Collin, Oct 25: the stock preset's 55 kept coming through and
# woven first layers let go). A design's own bed setting still wins.
BED_DEFAULTS = {k: ["60"] for k in ("textured_plate_temp", "textured_plate_temp_initial_layer", "hot_plate_temp",
                                    "hot_plate_temp_initial_layer", "eng_plate_temp", "eng_plate_temp_initial_layer")}
BED_DEFAULTS["curr_bed_type"] = "Textured PEI Plate"           # the P2S's plate; a CLI slice otherwise assumes Cool Plate
NS = ('xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
      'xmlns:BambuStudio="http://schemas.bambulab.com/package/2021" '
      'xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06" '
      'requiredextensions="p"')
GROUND = "#2b2f33"


def _mesh_xml(obj_id, mesh):
    v = np.asarray(mesh.vertices, float); f = np.asarray(mesh.faces, int)
    # one C-level format over the flat arrays (2.4x faster than a per-vertex map, byte-identical)
    vs = (('     <vertex x="%.4f" y="%.4f" z="%.4f"/>\n' * len(v)) % tuple(v.ravel().tolist()))[:-1]
    ts = (('     <triangle v1="%d" v2="%d" v3="%d"/>\n' * len(f)) % tuple(f.ravel().tolist()))[:-1]
    return (f'  <object id="{obj_id}" p:UUID="{uuid.uuid4()}" type="model">\n   <mesh>\n'
            f'    <vertices>\n{vs}\n    </vertices>\n    <triangles>\n{ts}\n    </triangles>\n'
            f'   </mesh>\n  </object>\n')


def _thumbnail(objects, colours, size, bed=256.0):
    """Plate view from above at z = 0.02: each part's bed footprint in its filament colour."""
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon as MplPoly
    fig = plt.figure(figsize=(size / 100, size / 100), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_facecolor(GROUND); fig.patch.set_facecolor(GROUND)
    for ob in objects:
        px, py = ob["position"]
        for p in ob["parts"]:
            if len(p) > 3 and p[3].get("modifier"):
                continue                      # a modifier volume prints nothing — not in the thumbnail
            _, m, slot = p[:3]
            sec = m.section(plane_origin=[0, 0, 0.02], plane_normal=[0, 0, 1])
            if sec is None:
                continue
            p2, _ = sec.to_2D(to_2D=np.eye(4))   # identity: keep bed XY
            try:
                polys = p2.polygons_full
            except ValueError:                   # odd outline: the thumbnail is cosmetic, skip it
                continue
            for poly in polys:
                xy = np.array(poly.exterior.coords) + [px, py]
                ax.add_patch(MplPoly(xy, closed=True, facecolor=colours[slot - 1], edgecolor="none"))
                for hole in poly.interiors:
                    ax.add_patch(MplPoly(np.array(hole.coords) + [px, py], closed=True, facecolor=GROUND, edgecolor="none"))
    ax.set_xlim(0, bed); ax.set_ylim(0, bed); ax.set_aspect("equal"); ax.axis("off")
    buf = io.BytesIO(); fig.savefig(buf, format="png", dpi=100); plt.close(fig)
    return buf.getvalue()


def _lum(hex_):
    r, g, b = (int(hex_[k:k + 2], 16) / 255 for k in (1, 3, 5))
    lin = lambda c: c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b), max(r, g, b) - min(r, g, b)


def flush_volume(c_from, c_to):
    """mm3 to purge when changing c_from -> c_to. Light after dark needs the most; dark after light very little
    (the same shape as Bambu's own calculator, tuned to its 280 mm3 default for a mid-contrast pair)."""
    if c_from.lower() == c_to.lower():
        return 0
    (y0, s0), (y1, s1) = _lum(c_from), _lum(c_to)
    if y1 > y0:                                    # going lighter: the dark trace shows through
        v = 140 + 560 * (y1 - y0) ** 0.75 + 120 * abs(s1 - s0)
    else:
        v = 110 + 160 * (y0 - y1) + 80 * abs(s1 - s0)
    return int(max(90, min(600, v)))


def flush_matrix(colours):
    return [[flush_volume(a, b) for b in colours] for a in colours]


def _ranges_xml(objects):
    body = ""
    for idx, ob in enumerate(objects, 1):                   # keyed by position in the build (verified, BS 2.8)
        rs = ob.get("ranges") or []
        if not rs:
            continue
        body += f' <object id="{idx}">\n'
        for z0, z1, opts in rs:
            body += f'  <range min_z="{z0:.4f}" max_z="{z1:.4f}">\n'
            body += "".join(f'   <option opt_key="{k}">{v}</option>\n' for k, v in opts.items())
            body += "  </range>\n"
        body += " </object>\n"
    return f'<?xml version="1.0" encoding="utf-8"?>\n<objects>\n{body}</objects>\n' if body else None


def _x(s):
    return _esc(str(s), {'"': "&quot;"})


PER_FILAMENT_PREFIXES = ("filament_", "nozzle_temperature", "fan_", "overhang_fan", "additional_cooling", "slow_down_",
                         "close_fan", "cool_plate", "hot_plate", "textured_plate", "eng_plate", "supertack_plate")
NOT_PER_FILAMENT = ("flush_volumes_vector", "flush_volumes_matrix", "filament_dev_ams_drying_ams_limitations")


def fix_filament_lists(cfg, n_fil):
    """Make every per-filament list in a project config EXACTLY n_fil long (padded when short, cut when long).

    Bambu Studio's GUI refuses a project whose per-filament lists disagree with its filament count — e.g. a
    1-filament project carrying filament_self_index ['1', '2'] from the 2-colour base config — and reports it as
    "The file does not contain any geometry data" (Oct 19 2026). The CLI slicer doesn't care, and its --export-3mf
    copies the mismatch through, so a CLI slice passing proves nothing about the GUI opening the file."""
    for key in list(cfg):
        if key.startswith(PER_FILAMENT_PREFIXES) and key not in NOT_PER_FILAMENT \
                and isinstance(cfg[key], list) and len(cfg[key]) >= 1 and len(cfg[key]) != n_fil:
            cfg[key] = (cfg[key] + [cfg[key][-1]] * n_fil)[:n_fil]
    cfg["filament_self_index"] = [str(i + 1) for i in range(n_fil)]
    return cfg


def repair_3mf(path):
    """Fix the per-filament lists of an existing .3mf in place (see fix_filament_lists). Returns the keys changed."""
    import shutil
    import tempfile
    with zipfile.ZipFile(path) as z:
        if "Metadata/project_settings.config" not in z.namelist():
            return []                                          # not a Bambu project (plain 3MF): nothing to fix
        cfg = json.loads(z.read("Metadata/project_settings.config"))
        before = json.dumps(cfg, sort_keys=True)
        n_fil = len(cfg.get("filament_colour") or [1])
        old = {k: v for k, v in cfg.items()}
        fix_filament_lists(cfg, n_fil)
        changed = sorted(k for k in cfg if cfg[k] != old.get(k))
        if json.dumps(cfg, sort_keys=True) == before:
            return []
        tmp = tempfile.mktemp(suffix=".3mf")
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as out:
            for item in z.infolist():
                data = json.dumps(cfg, indent=4).encode() if item.filename == "Metadata/project_settings.config" else z.read(item)
                out.writestr(item, data)
    shutil.move(tmp, path)
    return changed



def write_3mf(path, objects, title="model", colours=("#1C1C1C", "#F2F2F2"), overrides=DEFAULT_OVERRIDES, base=None,
              per_filament=None):
    """objects: [{name, position, parts: [(name, mesh, slot) | (name, mesh, slot, opts)], ranges?: [(z0, z1, {opt: value})]}].
    opts (optional): {"modifier": True} makes the part a modifier volume (it prints nothing; its "settings"
    apply to whatever it overlaps — e.g. fuzzy skin on one surface); {"settings": {key: value}} sets per-part options.
    per_filament: {key: [value per filament]} for filament-level settings (fan, temperature)."""
    n_fil = max(p[2] for ob in objects for p in ob["parts"])
    overrides = {**BED_DEFAULTS, **dict(overrides or {})}
    ident = "1 0 0 0 1 0 0 0 1 0 0 0"
    next_id = 1
    object_files, root_objects, build_items, settings_objects, plate_instances, rels, cut_objs = {}, "", "", "", "", "", ""
    for ob in objects:
        part_ids = list(range(next_id, next_id + len(ob["parts"])))
        obj_id = next_id + len(ob["parts"]); next_id = obj_id + 1
        sub_path = f"/3D/Objects/object_{len(object_files) + 1}.model"     # numbered in sequence, as Bambu Studio writes them
        object_files[sub_path] = (f'<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" xml:lang="en-US" {NS}>\n'
                                  f' <metadata name="BambuStudio:3mfVersion">1</metadata>\n <resources>\n'
                                  + "".join(_mesh_xml(pid, p[1]) for pid, p in zip(part_ids, ob["parts"]))
                                  + ' </resources>\n <build/>\n</model>\n')
        rels += (f' <Relationship Target="{sub_path}" Id="rel-{obj_id}" '
                 'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>\n')
        comps = "".join(f'    <component p:path="{sub_path}" objectid="{pid}" p:UUID="{uuid.uuid4()}" transform="{ident}"/>\n'
                        for pid in part_ids)
        root_objects += (f'  <object id="{obj_id}" p:UUID="{uuid.uuid4()}" type="model">\n'
                         f'   <components>\n{comps}   </components>\n  </object>\n')
        px, py = ob["position"]
        build_items += (f'  <item objectid="{obj_id}" p:UUID="{uuid.uuid4()}" '
                        f'transform="1 0 0 0 1 0 0 0 1 {px} {py} 0" printable="1"/>\n')
        part_xml = ""
        for pid, p in zip(part_ids, ob["parts"]):
            name, m, slot = p[:3]
            opts = p[3] if len(p) > 3 else {}
            subtype = "modifier_part" if opts.get("modifier") else "normal_part"
            extra = "".join(f'      <metadata key="{k}" value="{_x(v)}"/>\n' for k, v in (opts.get("settings") or {}).items())
            part_xml += (f'    <part id="{pid}" subtype="{subtype}" uuid="{uuid.uuid4()}">\n'
                         f'      <metadata key="name" value="{_x(name)}"/>\n'
                         f'      <metadata key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>\n'
                         f'      <metadata key="extruder" value="{slot}"/>\n{extra}'
                         f'      <mesh_stat face_count="{len(m.faces)}" edges_fixed="0" degenerate_facets="0" '
                         f'facets_removed="0" facets_reversed="0" backwards_edges="0"/>\n    </part>\n')
        obj_meta = "".join(f'    <metadata key="{k}" value="{_x(val)}"/>\n' for k, val in (ob.get("settings") or {}).items())
        # object-level filament = the first part's: a one-part object prints with the OBJECT's extruder (default 1),
        # whatever its part says — a blue knob beside a red piece came out red
        obj_meta = f'    <metadata key="extruder" value="{ob["parts"][0][2]}"/>\n' + obj_meta
        settings_objects += (f'  <object id="{obj_id}">\n    <metadata key="name" value="{_x(ob["name"])}"/>\n{obj_meta}'
                             f'    <metadata face_count="{sum(len(p[1].faces) for p in ob["parts"])}"/>\n{part_xml}  </object>\n')
        plate_instances += (f'    <model_instance>\n      <metadata key="object_id" value="{obj_id}"/>\n'
                            f'      <metadata key="instance_id" value="0"/>\n      <metadata key="identify_id" value="{obj_id * 100}"/>\n'
                            f'    </model_instance>\n')
        cut_objs += f' <object id="{obj_id}">\n  <cut_id id="0" check_sum="1" connectors_cnt="0"/>\n </object>\n'

    root_model = (f'<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" xml:lang="en-US" {NS}>\n'
                  f' <metadata name="Application">{APP}</metadata>\n <metadata name="BambuStudio:3mfVersion">1</metadata>\n'
                  f' <metadata name="Title">{_x(title)}</metadata>\n <resources>\n{root_objects} </resources>\n'
                  f' <build p:UUID="{uuid.uuid4()}">\n{build_items} </build>\n</model>\n')
    settings = (f'<?xml version="1.0" encoding="UTF-8"?>\n<config>\n{settings_objects}'
                f'  <plate>\n    <metadata key="plater_id" value="1"/>\n    <metadata key="plater_name" value=""/>\n'
                f'    <metadata key="locked" value="false"/>\n    <metadata key="filament_map_mode" value="Auto For Flush"/>\n'
                f'    <metadata key="gcode_file" value=""/>\n    <metadata key="thumbnail_file" value="Metadata/plate_1.png"/>\n'
                f'    <metadata key="thumbnail_no_light_file" value="Metadata/plate_no_light_1.png"/>\n'
                f'    <metadata key="top_file" value="Metadata/top_1.png"/>\n    <metadata key="pick_file" value="Metadata/pick_1.png"/>\n'
                f'{plate_instances}  </plate>\n  <assemble>\n  </assemble>\n</config>\n')
    cfg = dict(base) if base is not None else json.loads(BASE_SETTINGS.read_text())
    cfg.update(overrides)
    cfg["filament_colour"] = list(colours[:n_fil])
    for key in ("filament_settings_id", "filament_ids", "filament_is_support", "filament_type", "default_filament_colour"):
        if key in cfg and isinstance(cfg[key], list):
            cfg[key] = (cfg[key] + [cfg[key][0]] * n_fil)[:n_fil]
    cfg["filament_map"] = ["1"] * n_fil
    fm = flush_matrix(list(colours[:n_fil]))
    cfg["flush_volumes_matrix"] = [str(fm[i][j]) for i in range(n_fil) for j in range(n_fil)]
    cfg["flush_multiplier"] = ["1"]
    cfg["flush_volumes_vector"] = ["140"] * (2 * n_fil)
    cfg["filament_density"] = ["1.26"] * n_fil; cfg["filament_cost"] = ["19.99"] * n_fil
    cfg["filament_vendor"] = ["Bambu Lab"] * n_fil; cfg["filament_ids"] = ["GFA00"] * n_fil
    fix_filament_lists(cfg, n_fil)
    for key, vals in (per_filament or {}).items():
        cfg[key] = [str(v) for v in vals][:n_fil]
    # flag every process value we changed as edited against the system preset; with this list empty, Bambu Studio treats
    # the project as stock "0.20mm Standard" and swaps our profile back to the preset's values on open (285 g, not 159)
    ref = dict(base) if base is not None else json.loads(BASE_SETTINGS.read_text())
    changed = sorted(k for k, v in overrides.items() if ref.get(k) != v and not k.startswith(("filament_", "flush_")))
    # bed/nozzle temps and fans are FILAMENT-preset keys: flagged in the process slot, Bambu Studio sees the filament
    # as stock and re-applies the preset (or the AMS spool's preset) on open — the shadowbox asked for a 60/65 bed and
    # printed at 50 (Oct 20). Flag them in each filament's own slot so the GUI keeps them.
    fil = [k for k in changed if k.startswith(PER_FILAMENT_PREFIXES) and k not in NOT_PER_FILAMENT]
    proc = [k for k in changed if k not in fil]
    cfg["different_settings_to_system"] = [";".join(proc)] + [";".join(fil)] * n_fil + [""]

    content_types = ('<?xml version="1.0" encoding="UTF-8"?>\n<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
                     ' <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\n'
                     ' <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>\n'
                     ' <Default Extension="png" ContentType="image/png"/>\n <Default Extension="gcode" ContentType="text/x.gcode"/>\n</Types>\n')
    root_rels = ('<?xml version="1.0" encoding="UTF-8"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
                 ' <Relationship Target="/3D/3dmodel.model" Id="rel-1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>\n'
                 ' <Relationship Target="/Metadata/plate_1.png" Id="rel-2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/thumbnail"/>\n'
                 ' <Relationship Target="/Metadata/plate_1.png" Id="rel-4" Type="http://schemas.bambulab.com/package/2021/cover-thumbnail-middle"/>\n'
                 ' <Relationship Target="/Metadata/plate_1_small.png" Id="rel-5" Type="http://schemas.bambulab.com/package/2021/cover-thumbnail-small"/>\n'
                 '</Relationships>\n')
    model_rels = ('<?xml version="1.0" encoding="UTF-8"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
                  f'{rels}</Relationships>\n')
    slice_info = ('<?xml version="1.0" encoding="UTF-8"?>\n<config>\n  <header>\n    <header_item key="X-BBL-Client-Type" value="slicer"/>\n'
                  f'    <header_item key="X-BBL-Client-Version" value="{APP.split("-")[1]}"/>\n  </header>\n</config>\n')
    big, small = _thumbnail(objects, colours, 512), _thumbnail(objects, colours, 128)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as z:   # level 1: ~3x faster, ~10 % bigger
        z.writestr("[Content_Types].xml", content_types); z.writestr("_rels/.rels", root_rels)
        z.writestr("3D/3dmodel.model", root_model); z.writestr("3D/_rels/3dmodel.model.rels", model_rels)
        for sub_path, xml in object_files.items():
            z.writestr(sub_path.lstrip("/"), xml)
        z.writestr("Metadata/model_settings.config", settings)
        rx = _ranges_xml(objects)
        if rx:
            z.writestr("Metadata/layer_config_ranges.xml", rx)
        z.writestr("Metadata/project_settings.config", json.dumps(cfg, indent=4))
        z.writestr("Metadata/slice_info.config", slice_info)
        z.writestr("Metadata/cut_information.xml", f'<?xml version="1.0" encoding="utf-8"?>\n<objects>\n{cut_objs}</objects>\n')
        z.writestr("Metadata/filament_sequence.json", json.dumps({"plate_1": {"nozzle_sequence": [], "optimal_assignment": [], "sequence": []}}))
        for name in ("plate_1.png", "plate_no_light_1.png", "top_1.png", "pick_1.png"):
            z.writestr(f"Metadata/{name}", big)
        z.writestr("Metadata/plate_1_small.png", small)
    return path


BAMBU_APP = pathlib.Path("/Applications/BambuStudio.app/Contents/MacOS/BambuStudio")


def slicer_available():
    return BAMBU_APP.exists()


def slice_project(p3mf, workdir):
    """Slice a project 3MF with the Bambu Studio CLI -> {'time','minutes','grams','layers'} or {'error'}.
    The CLI ignores part->filament assignment, so these are single-colour numbers (add the AMS swaps).
    Run from the output dir with absolute paths; --outputdir breaks the export (Bambu Studio 2.8)."""
    import re, subprocess
    workdir = pathlib.Path(workdir); workdir.mkdir(parents=True, exist_ok=True)
    out = (workdir / "sliced.3mf").resolve()
    if not slicer_available():
        return {"error": "Bambu Studio not found in /Applications"}
    with open(workdir / "cli.log", "w") as log:
        subprocess.run([str(BAMBU_APP), "--slice", "0", "--export-3mf", str(out), str(pathlib.Path(p3mf).resolve())],
                       cwd=workdir, stdout=log, stderr=subprocess.STDOUT, timeout=1800)
    try:
        res = json.loads((workdir / "result.json").read_text())
    except Exception:
        return {"error": "slicer produced no result"}
    if res.get("return_code") != 0:
        warn = str((res.get("sliced_plates") or [{}])[0].get("warning_message", ""))
        return {"error": res.get("error_string", "slice failed"), "detail": warn[:300]}
    g = zipfile.ZipFile(out).read("Metadata/plate_1.gcode").decode(errors="ignore")
    t = re.search(r"; model printing time: ([^;]+);", g).group(1).strip()
    mins = sum(int(n) * {"d": 1440, "h": 60, "m": 1, "s": 1 / 60}[u] for n, u in re.findall(r"(\d+)([dhms])", t))
    return {"time": t, "minutes": round(mins, 1),
            "grams": round(sum(float(x) for x in re.search(r"; total filament weight \[g\] : ([\d.,]+)", g).group(1)
                                .split(",") if x), 2),      # one number per filament: the total is their sum
            "layers": int(re.search(r"; total layer number: (\d+)", g).group(1))}


def gcode_preview(sliced_3mf, out_png, colours=None, size=900):
    """What actually prints: the extrusion paths of the sliced G-code, seen from the front, each in its filament's
    colour, drawn back to front — layer lines, colour changes and halftone ribs as the printer lays them."""
    import re
    import zipfile
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    z = zipfile.ZipFile(sliced_3mf)
    g = z.read("Metadata/plate_1.gcode").decode(errors="ignore")
    if colours is None:
        try:
            cfg = json.loads(z.read("Metadata/project_settings.config"))
            colours = cfg.get("filament_colour") or ["#888888"]
        except Exception:
            colours = ["#888888"]
    tool = 0; x = y = zc = 0.0; segs = []; cols = []; ys = []
    rel_e = False; feature = ""; started = False
    for ln in g.splitlines():
        if ln.startswith("; FEATURE:"):
            feature = ln[10:].strip(); continue
        if ln.startswith("; CHANGE_LAYER"):
            started = True
        if ln.startswith("M620 S"):
            m = re.match(r"M620 S(\d+)A", ln)
            if m:
                tool = int(m.group(1))
            continue
        if ln.startswith("M83"):
            rel_e = True
        if not (ln.startswith("G1 ") or ln.startswith("G0 ") or ln.startswith("G2 ") or ln.startswith("G3 ")):
            continue
        p = dict(re.findall(r"([XYZEIJ])(-?[\d.]+)", ln.split(";")[0]))
        nx = float(p.get("X", x)); ny = float(p.get("Y", y)); nz_ = float(p.get("Z", zc))
        e = float(p.get("E", 0.0))
        if (e > 0 and (nx != x or ny != y) and nz_ > 0.05 and started
                and feature not in ("Prime tower", "Wipe tower", "Skirt", "Brim")):
            col = colours[tool % len(colours)]
            if ln[1] in "23" and ("I" in p or "J" in p):             # arcs: follow the curve, not the chord
                cx_, cy_ = x + float(p.get("I", 0)), y + float(p.get("J", 0))
                a0 = math.atan2(y - cy_, x - cx_); a1 = math.atan2(ny - cy_, nx - cx_); r_ = math.hypot(x - cx_, y - cy_)
                if ln[1] == "2":                                     # clockwise
                    while a1 >= a0:
                        a1 -= 2 * math.pi
                else:
                    while a1 <= a0:
                        a1 += 2 * math.pi
                k = max(2, int(abs(a1 - a0) * r_ / 1.5) + 1)
                aa = np.linspace(a0, a1, k + 1)
                px_, py_ = cx_ + r_ * np.cos(aa), cy_ + r_ * np.sin(aa)
                for i in range(k):
                    segs.append(((px_[i], zc), (px_[i + 1], nz_))); cols.append(col); ys.append((py_[i] + py_[i + 1]) / 2)
            else:
                segs.append(((x, zc), (nx, nz_))); cols.append(col); ys.append((y + ny) / 2)
        x, y, zc = nx, ny, nz_
    if not segs:
        raise ValueError("no extrusion found in the G-code")
    ys = np.asarray(ys); order = np.argsort(-ys)                     # back to front
    cy = float(np.median(ys))
    keep = order[ys[order] <= cy + 2.0]                                 # the front half: what you see
    segs = [segs[i] for i in keep]; cols = [cols[i] for i in keep]
    fig = plt.figure(figsize=(size / 100, size / 100), dpi=100); ax = fig.add_axes([0, 0, 1, 1])
    ax.add_collection(LineCollection(segs, colors=cols, linewidths=0.55, capstyle="round"))
    xs = [pt[0] for s in segs for pt in s]; zs = [pt[1] for s in segs for pt in s]
    w = max(max(xs) - min(xs), max(zs) - min(zs)) * 1.06; mx = (max(xs) + min(xs)) / 2; mz = (max(zs) + min(zs)) / 2
    ax.set_xlim(mx - w / 2, mx + w / 2); ax.set_ylim(mz - w / 2, mz + w / 2); ax.set_aspect("equal"); ax.axis("off")
    fig.patch.set_facecolor("#F7F5F0"); fig.savefig(out_png, dpi=100, facecolor="#F7F5F0"); plt.close(fig)
    return str(out_png)


if __name__ == "__main__":                                    # python -m text2print.bambu repair FILE.3mf ...
    import sys
    if len(sys.argv) > 2 and sys.argv[1] == "repair":
        for f in sys.argv[2:]:
            ch = repair_3mf(f)
            print(("fixed " + ", ".join(ch)) if ch else "ok", "-", f)


# ---------------------------------------------------------------------------------------------------------------
# Show-level 2-colour fine detail in PETG (verified Nov 6 2026 on the Drehregler inlets: three failed prints, then a
# full settings pass that printed). The rough, furry logo top was never a geometry problem — it was SPEED: tiny
# 2-colour layers finish in seconds and never cool. The cure is slow feeds plus a long minimum layer time.
#
# The headless CLI IGNORES these (set them and the gcode does not change): gap_fill_target, filter_out_gap_fill,
# infill_wall_overlap, detect_thin_wall, flush_multiplier, and a hand-written flush_volumes_matrix — Bambu recomputes
# the purge matrix from the colour pair (light->dark needs little, dark->light a lot), which is correct; leave it.
# Per-part {"settings": {...}} that DO work: wall_loops, seam_position.  ironing_type "topmost" irons only the
# object's highest surface (a logo floor under a dome crown needs "top"), and ironing a small logo made it worse.
SHOWROOM_PETG_DETAIL = {
    "layer_height": 0.12,                 # 0.08 PETG on a 0.4 nozzle under-extrudes and ropes; 0.12 flows consistently
    "initial_layer_print_height": 0.2,
    "top_surface_line_width": 0.3,        # the horizontal-line look comes from THIS, not layer height; 0.2 ropes in PETG
    "top_surface_pattern": "monotonicline",
    "top_shell_layers": 6, "bottom_shell_layers": 5, "sparse_infill_density": "100%", "wall_loops": 4,
    "ironing_type": "no ironing",
    "seam_position": "random",            # a round body: aligned seams stack into a vertical line (logo part: "back")
    "top_surface_speed": 25, "outer_wall_speed": 35, "inner_wall_speed": 60, "internal_solid_infill_speed": 60,
    "gap_infill_speed": 25, "bridge_speed": 30, "small_perimeter_speed": 15, "small_perimeter_threshold": 12,
    "slow_down_layer_time": 30, "slow_down_min_speed": 8,   # the tiny logo layers must crawl and cool
    "nozzle_temperature": 250, "nozzle_temperature_initial_layer": 255,
    "retraction_length": 1.0, "retract_before_wipe": "70%", "wipe": 1, "z_hop": 0.4, "retract_when_changing_layer": 1,
    "enable_prime_tower": 1, "flush_into_support": 0, "flush_into_infill": 0, "flush_into_objects": 0,
    "enable_pressure_advance": 1, "pressure_advance": 0.02,
    "brim_type": "outer_only", "brim_width": 5, "brim_object_gap": 0.1,
    "enable_support": 1, "support_type": "tree(auto)", "support_style": "default", "support_critical_regions_only": 1,
    "tree_support_branch_diameter": 4, "support_top_z_distance": 0.32, "support_interface_top_layers": 1,
    "elefant_foot_compensation": 0.1,
}
LOGO_PART = {"settings": {"wall_loops": "1", "seam_position": "back"}}   # ONE outline + lines; 0 walls printed furry


def apply_overrides(cfg, intents):
    """Set scalar intents onto a project config, keeping each key's existing list shape (per-extruder and
    per-filament keys are lists of differing lengths; a wrong length is the "no geometry" bug)."""
    for k, v in intents.items():
        cur = cfg.get(k)
        cfg[k] = [str(v)] * len(cur) if isinstance(cur, list) and cur else str(v)
    return cfg


# ---- G-code checks: trust the toolpath, not the settings panel ------------------------------------------------
_TOOL_RE, _Z_RE, _XY_RE, _F_RE = "^(T\\d)\\b", "G1 Z([\\d.]+)", "G[01] X([-\\d.]+) Y([-\\d.]+)", "\\bF([\\d.]+)"


def load_gcode(path):
    """Lines of a .gcode, or of Metadata/plate_1.gcode inside a sliced .3mf."""
    p = pathlib.Path(path)
    if p.suffix.lower() == ".3mf":
        return zipfile.ZipFile(p).read("Metadata/plate_1.gcode").decode(errors="ignore").splitlines()
    return p.read_text(errors="ignore").splitlines()


def gcode_setting(lines, key):
    import re
    m = re.search(rf"^; {re.escape(key)} = (.+)$", "\n".join(lines), re.M)
    return m.group(1) if m else None


def _walk(lines):
    """Yield (tool, z, feature, x, y, extruding, feed_mm_s, prev_xy) for every XY move. The filament printed before
    the first explicit T command is reported as tool 'T?' — label it, never sort on it."""
    import re
    tool, z, feat, F, prev = "T?", None, None, None, None
    for l in lines:
        mt = re.match(_TOOL_RE, l)
        if mt: tool = mt.group(1)
        mz = re.match(_Z_RE, l)
        if mz: z = float(mz.group(1))
        mf = re.search(_F_RE, l)
        if mf: F = float(mf.group(1)) / 60
        if l.startswith("; FEATURE:"):
            feat = l.split(":", 1)[1].strip(); continue
        m = re.match(_XY_RE, l)
        if not m: continue
        x, y = float(m.group(1)), float(m.group(2))
        ext = "E" in l and not re.search(r"E-", l)
        yield tool, z, feat, x, y, ext, F, prev
        prev = (x, y)


def top_surface_angles(lines, z, tool="T1", where=lambda x, y: True, tol=0.005):
    """-> (horizontal, vertical, n) segments of the Top surface at layer z for one tool. Bambu alternates top fill
    0/90 every layer (even index = 0 deg), so a flat inlay top must sit on an even layer to print horizontal lines."""
    h = v = n = 0
    for tool_, z_, feat, x, y, ext, F, prev in _walk(lines):
        if tool_ != tool or z_ is None or abs(z_ - z) > tol or feat != "Top surface" or not ext or prev is None: continue
        if not where(x, y) or abs(x - prev[0]) + abs(y - prev[1]) < 0.4: continue
        a = abs(math.degrees(math.atan2(y - prev[1], x - prev[0]))) % 180; n += 1
        h += a < 15 or a > 165; v += 75 < a < 105
    return h, v, n


def feature_speeds(lines, tool=None, zmin=-1e9, zmax=1e9, where=lambda x, y: True):
    """-> {feature: (min, max) mm/s} of the REAL feedrates used (F persists across lines; read it as state)."""
    out = {}
    for tool_, z, feat, x, y, ext, F, prev in _walk(lines):
        if not ext or z is None or not (zmin <= z <= zmax) or F is None or feat is None: continue
        if tool and tool_ != tool or not where(x, y): continue
        lo, hi = out.get(feat, (F, F)); out[feat] = (min(lo, F), max(hi, F))
    return out


def seam_scatter(lines, centre, tool=None, zmin=-1e9, zmax=1e9, sectors=12, where=lambda x, y: True):
    """Outer-wall seam starts around an object centre -> (n, sectors_used, biggest_sector_fraction).
    'random' seams spread over every sector (biggest ~0.1-0.2); 'aligned/back' cluster into one (= a visible line).
    Pass `where` to keep to ONE object — another object's starts measured about this centre all land in one sector."""
    import re
    cx, cy = centre; angles = []; armed = False; feat = None
    for tool_, z, f, x, y, ext, F, prev in _walk(lines):
        if f != feat: feat, armed = f, (f == "Outer wall")
        if armed and ext and prev is not None and z is not None and zmin <= z <= zmax and (tool is None or tool_ == tool) and where(x, y):
            dx, dy = prev[0] - cx, prev[1] - cy
            if math.hypot(dx, dy) > 3: angles.append(math.degrees(math.atan2(dy, dx)) % 360)
            armed = False
    if not angles: return 0, 0, 0.0
    hist = np.histogram(angles, bins=sectors, range=(0, 360))[0]
    return len(angles), int(np.count_nonzero(hist)), float(hist.max() / len(angles))


def tool_changes(lines):
    """-> [(z, tool)] — every AMS swap; with alternating colour bands this is also the purge/time cost."""
    import re
    z, out = None, []
    for l in lines:
        mz = re.match(_Z_RE, l)
        if mz: z = float(mz.group(1))
        mt = re.match(_TOOL_RE, l)
        if mt: out.append((z, mt.group(1)))
    return out


def support_grams(lines, density=1.27, d=1.75):
    """Support filament from E deltas (absolute or relative E). NOT path length x filament area — that formula
    counts the toolpath as if it were filament and overestimates ~9x."""
    import re
    feat, e_prev, sup, tot, absolute = None, None, 0.0, 0.0, True
    for l in lines:
        if l.startswith("M83"): absolute = False
        if l.startswith("M82"): absolute = True
        if l.startswith("; FEATURE:"): feat = l.split(":", 1)[1].strip(); continue
        if l.startswith("G92"):
            m = re.search(r"E([-\d.]+)", l); e_prev = float(m.group(1)) if m else e_prev; continue
        m = re.match(r"G1 .*E([-\d.]+)", l)
        if not m: continue
        e = float(m.group(1))
        dlt = (e - e_prev) if (absolute and e_prev is not None) else (e if not absolute else 0.0)
        if absolute: e_prev = e
        if dlt > 0:
            tot += dlt
            if feat and "upport" in feat: sup += dlt
    area = math.pi * (d / 2) ** 2
    return round(sup * area / 1000 * density, 2), round(tot * area / 1000 * density, 2)


def check_detail(path, logo_z, centre, logo_tool="T1", where=lambda x, y: True):
    """One-call report for a 2-colour detail part: is the logo top horizontal, how fast did it really print,
    is the body seam scattered, what swapped, how much support. Read the numbers; don't trust a render."""
    g = load_gcode(path)
    h, v, n = top_surface_angles(g, logo_z, logo_tool, where)
    ns, used, big = seam_scatter(g, centre, where=where)   # one object: a second object skews the angles
    sup, tot = support_grams(g)
    return {"logo_horizontal": f"{h}/{n}" + (" OK" if v == 0 and h else " FAIL"),
            "logo_speeds_mm_s": feature_speeds(g, logo_tool, where=where),
            "body_seam": f"{ns} starts, {used} sectors, biggest {big:.0%}" + (" (scattered)" if big < 0.35 else " (LINE)"),
            "tool_changes": len(tool_changes(g)), "support_g": sup, "total_g": tot,
            "ironing": any("ron" in l.lower() for l in g if l.startswith("; FEATURE:")),
            "time": gcode_setting(g, "model printing time") or next((l for l in g if "model printing time" in l), "")}
