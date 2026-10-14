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
import pathlib
import uuid
import zipfile
import numpy as np

APP = "BambuStudio-02.08.02.61"
BASE_SETTINGS = pathlib.Path(__file__).with_name("data") / "p2s_0.4.json"   # P2S 0.4 nozzle + 0.20mm
#   Standard + Bambu PLA Basic x2, as exported by the Bambu Studio CLI (--export-settings)
DEFAULT_OVERRIDES = {
    "wall_loops": "3", "sparse_infill_density": "15%", "sparse_infill_pattern": "gyroid",
    "bottom_shell_layers": "4", "top_shell_layers": "5", "seam_position": "rear",
    "elefant_foot_compensation": "0.15", "enable_prime_tower": "1", "timelapse_type": "0",
}
NS = ('xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
      'xmlns:BambuStudio="http://schemas.bambulab.com/package/2021" '
      'xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06" '
      'requiredextensions="p"')
GROUND = "#2b2f33"


def _mesh_xml(obj_id, mesh):
    v = np.asarray(mesh.vertices, float); f = np.asarray(mesh.faces, int)
    vs = "\n".join(map('     <vertex x="{:.4f}" y="{:.4f}" z="{:.4f}"/>'.format, v[:, 0], v[:, 1], v[:, 2]))
    ts = "\n".join(map('     <triangle v1="{}" v2="{}" v3="{}"/>'.format, f[:, 0], f[:, 1], f[:, 2]))
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
        for (_, m, slot) in ob["parts"]:
            sec = m.section(plane_origin=[0, 0, 0.02], plane_normal=[0, 0, 1])
            if sec is None:
                continue
            p2, _ = sec.to_2D(to_2D=np.eye(4))   # identity: keep bed XY
            for poly in p2.polygons_full:
                xy = np.array(poly.exterior.coords) + [px, py]
                ax.add_patch(MplPoly(xy, closed=True, facecolor=colours[slot - 1], edgecolor="none"))
                for hole in poly.interiors:
                    ax.add_patch(MplPoly(np.array(hole.coords) + [px, py], closed=True, facecolor=GROUND, edgecolor="none"))
    ax.set_xlim(0, bed); ax.set_ylim(0, bed); ax.set_aspect("equal"); ax.axis("off")
    buf = io.BytesIO(); fig.savefig(buf, format="png", dpi=100); plt.close(fig)
    return buf.getvalue()


def write_3mf(path, objects, title="model", colours=("#1C1C1C", "#F2F2F2"), overrides=DEFAULT_OVERRIDES, base=None):
    n_fil = max(slot for ob in objects for _, _, slot in ob["parts"])
    ident = "1 0 0 0 1 0 0 0 1 0 0 0"
    next_id = 1
    object_files, root_objects, build_items, settings_objects, plate_instances, rels, cut_objs = {}, "", "", "", "", "", ""
    for ob in objects:
        part_ids = list(range(next_id, next_id + len(ob["parts"])))
        obj_id = next_id + len(ob["parts"]); next_id = obj_id + 1
        sub_path = f"/3D/Objects/object_{obj_id}.model"
        object_files[sub_path] = (f'<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" xml:lang="en-US" {NS}>\n'
                                  f' <metadata name="BambuStudio:3mfVersion">1</metadata>\n <resources>\n'
                                  + "".join(_mesh_xml(pid, m) for pid, (_, m, _) in zip(part_ids, ob["parts"]))
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
        for pid, (name, m, slot) in zip(part_ids, ob["parts"]):
            part_xml += (f'    <part id="{pid}" subtype="normal_part" uuid="{uuid.uuid4()}">\n'
                         f'      <metadata key="name" value="{name}"/>\n'
                         f'      <metadata key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>\n'
                         f'      <metadata key="extruder" value="{slot}"/>\n'
                         f'      <mesh_stat face_count="{len(m.faces)}" edges_fixed="0" degenerate_facets="0" '
                         f'facets_removed="0" facets_reversed="0" backwards_edges="0"/>\n    </part>\n')
        settings_objects += (f'  <object id="{obj_id}">\n    <metadata key="name" value="{ob["name"]}"/>\n'
                             f'    <metadata face_count="{sum(len(m.faces) for _, m, _ in ob["parts"])}"/>\n{part_xml}  </object>\n')
        plate_instances += (f'    <model_instance>\n      <metadata key="object_id" value="{obj_id}"/>\n'
                            f'      <metadata key="instance_id" value="0"/>\n      <metadata key="identify_id" value="{obj_id * 100}"/>\n'
                            f'    </model_instance>\n')
        cut_objs += f' <object id="{obj_id}">\n  <cut_id id="0" check_sum="1" connectors_cnt="0"/>\n </object>\n'

    root_model = (f'<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" xml:lang="en-US" {NS}>\n'
                  f' <metadata name="Application">{APP}</metadata>\n <metadata name="BambuStudio:3mfVersion">1</metadata>\n'
                  f' <metadata name="Title">{title}</metadata>\n <resources>\n{root_objects} </resources>\n'
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
    cfg["flush_volumes_matrix"] = ["0" if i == j else "280" for i in range(n_fil) for j in range(n_fil)]
    cfg["flush_volumes_vector"] = ["140"] * (2 * n_fil)
    cfg["filament_density"] = ["1.26"] * n_fil; cfg["filament_cost"] = ["19.99"] * n_fil
    cfg["filament_vendor"] = ["Bambu Lab"] * n_fil; cfg["filament_ids"] = ["GFA00"] * n_fil

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
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types); z.writestr("_rels/.rels", root_rels)
        z.writestr("3D/3dmodel.model", root_model); z.writestr("3D/_rels/3dmodel.model.rels", model_rels)
        for sub_path, xml in object_files.items():
            z.writestr(sub_path.lstrip("/"), xml)
        z.writestr("Metadata/model_settings.config", settings)
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
            "grams": float(re.search(r"; total filament weight \[g\] : ([\d.]+)", g).group(1)),
            "layers": int(re.search(r"; total layer number: (\d+)", g).group(1))}
