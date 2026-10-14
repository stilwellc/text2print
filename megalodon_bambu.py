"""Write a Bambu Studio project 3MF: one object made of several parts, each pre-assigned to a
filament slot — so a two-colour stem opens in Bambu Studio ready to slice, with no painting or
manual part assignment. The layout mirrors what Bambu Studio 2.8 writes itself (verified against
a CLI export): component references into 3D/Objects/, part extruders in
Metadata/model_settings.config, and a full project_settings.config so the printer, process and
filament presets travel with the file."""
import io
import json
import pathlib
import uuid
import zipfile
import numpy as np

APP = "BambuStudio-02.08.02.61"
BED_CENTRE = (128.0, 128.0)     # P2S / X1 / P1 bed is 256 x 256, origin at the front-left corner
BASE_SETTINGS = pathlib.Path(__file__).with_name("megalodon_bambu_p2s.json")   # P2S 0.4 nozzle +
#   0.20mm Standard + Bambu PLA Basic x2, exported by the Bambu Studio CLI (--export-settings)
PRINT_OVERRIDES = {            # the stand's PrusaSlicer profile, in Bambu's names
    "wall_loops": "4", "sparse_infill_density": "12%", "sparse_infill_pattern": "gyroid",
    "bottom_shell_layers": "7", "top_shell_layers": "5", "seam_position": "rear",
    "elefant_foot_compensation": "0.15", "enable_prime_tower": "1", "timelapse_type": "0",
}


def _mesh_xml(obj_id, mesh):
    v = np.asarray(mesh.vertices, float)
    f = np.asarray(mesh.faces, int)
    vs = "\n".join(f'     <vertex x="{x:.6f}" y="{y:.6f}" z="{z:.6f}"/>' for x, y, z in v)
    ts = "\n".join(f'     <triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in f)
    return (f'  <object id="{obj_id}" p:UUID="{uuid.uuid4()}" type="model">\n   <mesh>\n'
            f'    <vertices>\n{vs}\n    </vertices>\n    <triangles>\n{ts}\n    </triangles>\n'
            f'   </mesh>\n  </object>\n')


def _thumbnail(parts, colours, size):
    """Bed-face view as read with the part turned over (x mirrored): each part's z=0 footprint
    in its filament colour, on Bambu's dark ground."""
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon as MplPoly
    fig = plt.figure(figsize=(size / 100, size / 100), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_facecolor("#2b2f33"); fig.patch.set_facecolor("#2b2f33")
    lim = 0
    for (_, m, slot) in parts:
        sec = m.section(plane_origin=[0, 0, 0.02], plane_normal=[0, 0, 1])
        if sec is None:
            continue
        p2, _ = sec.to_2D(to_2D=np.diag([-1.0, 1.0, 1.0, 1.0]))   # x mirrored: reads correctly from below
        for poly in p2.polygons_full:
            ax.add_patch(MplPoly(np.array(poly.exterior.coords), closed=True,
                                 facecolor=colours[slot - 1], edgecolor="none"))
            for hole in poly.interiors:
                ax.add_patch(MplPoly(np.array(hole.coords), closed=True, facecolor="#2b2f33", edgecolor="none"))
        lim = max(lim, np.abs(p2.bounds).max())
    ax.set_xlim(-lim * 1.08, lim * 1.08); ax.set_ylim(-lim * 1.08, lim * 1.08)
    ax.set_aspect("equal"); ax.axis("off")
    buf = io.BytesIO(); fig.savefig(buf, format="png", dpi=100); plt.close(fig)
    return buf.getvalue()


def write_3mf(path, parts, title="model", object_name=None,
              colours=("#1C1C1C", "#C9A227"), overrides=PRINT_OVERRIDES):
    """parts: [(name, trimesh.Trimesh, filament_slot_1_based), ...] all in one shared frame
    (XY centred on the object, Z >= 0). The object is placed at the bed centre."""
    obj_name = object_name or title
    part_ids = list(range(1, len(parts) + 1))
    obj_id = len(parts) + 1
    n_fil = max(slot for _, _, slot in parts)
    NS = ('xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
          'xmlns:BambuStudio="http://schemas.bambulab.com/package/2021" '
          'xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06" '
          'requiredextensions="p"')
    sub_path = f"/3D/Objects/object_{obj_id}.model"
    ident = "1 0 0 0 1 0 0 0 1 0 0 0"
    place = f"1 0 0 0 1 0 0 0 1 {BED_CENTRE[0]} {BED_CENTRE[1]} 0"

    objects_model = (f'<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" xml:lang="en-US" {NS}>\n'
                     f' <metadata name="BambuStudio:3mfVersion">1</metadata>\n <resources>\n'
                     + "".join(_mesh_xml(pid, m) for pid, (_, m, _) in zip(part_ids, parts))
                     + ' </resources>\n <build/>\n</model>\n')
    comps = "".join(f'    <component p:path="{sub_path}" objectid="{pid}" p:UUID="{uuid.uuid4()}" transform="{ident}"/>\n'
                    for pid in part_ids)
    root_model = (f'<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" xml:lang="en-US" {NS}>\n'
                  f' <metadata name="Application">{APP}</metadata>\n'
                  f' <metadata name="BambuStudio:3mfVersion">1</metadata>\n'
                  f' <metadata name="Title">{title}</metadata>\n'
                  f' <resources>\n  <object id="{obj_id}" p:UUID="{uuid.uuid4()}" type="model">\n'
                  f'   <components>\n{comps}   </components>\n  </object>\n </resources>\n'
                  f' <build p:UUID="{uuid.uuid4()}">\n'
                  f'  <item objectid="{obj_id}" p:UUID="{uuid.uuid4()}" transform="{place}" printable="1"/>\n'
                  f' </build>\n</model>\n')

    part_xml = ""
    for pid, (name, m, slot) in zip(part_ids, parts):
        part_xml += (f'    <part id="{pid}" subtype="normal_part" uuid="{uuid.uuid4()}">\n'
                     f'      <metadata key="name" value="{name}"/>\n'
                     f'      <metadata key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>\n'
                     f'      <metadata key="extruder" value="{slot}"/>\n'
                     f'      <mesh_stat face_count="{len(m.faces)}" edges_fixed="0" degenerate_facets="0" '
                     f'facets_removed="0" facets_reversed="0" backwards_edges="0"/>\n    </part>\n')
    settings = (f'<?xml version="1.0" encoding="UTF-8"?>\n<config>\n  <object id="{obj_id}">\n'
                f'    <metadata key="name" value="{obj_name}"/>\n'
                f'    <metadata face_count="{sum(len(m.faces) for _, m, _ in parts)}"/>\n{part_xml}  </object>\n'
                f'  <plate>\n    <metadata key="plater_id" value="1"/>\n    <metadata key="plater_name" value=""/>\n'
                f'    <metadata key="locked" value="false"/>\n'
                f'    <metadata key="filament_map_mode" value="Auto For Flush"/>\n'
                f'    <metadata key="gcode_file" value=""/>\n'
                f'    <metadata key="thumbnail_file" value="Metadata/plate_1.png"/>\n'
                f'    <metadata key="thumbnail_no_light_file" value="Metadata/plate_no_light_1.png"/>\n'
                f'    <metadata key="top_file" value="Metadata/top_1.png"/>\n'
                f'    <metadata key="pick_file" value="Metadata/pick_1.png"/>\n'
                f'    <model_instance>\n      <metadata key="object_id" value="{obj_id}"/>\n'
                f'      <metadata key="instance_id" value="0"/>\n      <metadata key="identify_id" value="{obj_id * 100}"/>\n'
                f'    </model_instance>\n  </plate>\n  <assemble>\n  </assemble>\n</config>\n')

    cfg = json.loads(BASE_SETTINGS.read_text())
    cfg.update(overrides)
    cfg["filament_colour"] = list(colours[:n_fil])
    for key in ("filament_settings_id", "filament_ids", "filament_map", "filament_is_support", "filament_type",
                "default_filament_colour"):
        if key in cfg and isinstance(cfg[key], list):
            cfg[key] = (cfg[key] + [cfg[key][0]] * n_fil)[:n_fil]
    cfg["filament_map"] = ["1"] * n_fil
    # the CLI-exported base lacks the filament's physical data, so weights/cost would read 0
    cfg["filament_density"] = ['1.26'] * n_fil
    cfg["filament_cost"] = ['19.99'] * n_fil
    cfg["filament_vendor"] = ['Bambu Lab'] * n_fil
    cfg["filament_ids"] = ['GFA00'] * n_fil
    # per-filament-pair tables must be sized for exactly n_fil filaments (single-nozzle machine)
    cfg["flush_volumes_matrix"] = ["0" if i == j else "280" for i in range(n_fil) for j in range(n_fil)]
    cfg["flush_volumes_vector"] = ["140"] * (2 * n_fil)

    content_types = ('<?xml version="1.0" encoding="UTF-8"?>\n'
                     '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
                     ' <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\n'
                     ' <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>\n'
                     ' <Default Extension="png" ContentType="image/png"/>\n'
                     ' <Default Extension="gcode" ContentType="text/x.gcode"/>\n</Types>\n')
    rels = ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
            ' <Relationship Target="/3D/3dmodel.model" Id="rel-1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>\n'
            ' <Relationship Target="/Metadata/plate_1.png" Id="rel-2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/thumbnail"/>\n'
            ' <Relationship Target="/Metadata/plate_1.png" Id="rel-4" Type="http://schemas.bambulab.com/package/2021/cover-thumbnail-middle"/>\n'
            ' <Relationship Target="/Metadata/plate_1_small.png" Id="rel-5" Type="http://schemas.bambulab.com/package/2021/cover-thumbnail-small"/>\n'
            '</Relationships>\n')
    model_rels = ('<?xml version="1.0" encoding="UTF-8"?>\n'
                  '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
                  f' <Relationship Target="{sub_path}" Id="rel-1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>\n'
                  '</Relationships>\n')
    slice_info = ('<?xml version="1.0" encoding="UTF-8"?>\n<config>\n  <header>\n'
                  '    <header_item key="X-BBL-Client-Type" value="slicer"/>\n'
                  f'    <header_item key="X-BBL-Client-Version" value="{APP.split("-")[1]}"/>\n'
                  '  </header>\n</config>\n')
    cut_info = ('<?xml version="1.0" encoding="utf-8"?>\n<objects>\n <object id="1">\n'
                '  <cut_id id="0" check_sum="1" connectors_cnt="0"/>\n </object>\n</objects>\n')
    big = _thumbnail(parts, colours, 512)
    small = _thumbnail(parts, colours, 128)

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("3D/3dmodel.model", root_model)
        z.writestr("3D/_rels/3dmodel.model.rels", model_rels)
        z.writestr(sub_path.lstrip("/"), objects_model)
        z.writestr("Metadata/model_settings.config", settings)
        z.writestr("Metadata/project_settings.config", json.dumps(cfg, indent=4))
        z.writestr("Metadata/slice_info.config", slice_info)
        z.writestr("Metadata/cut_information.xml", cut_info)
        z.writestr("Metadata/filament_sequence.json",
                   json.dumps({"plate_1": {"nozzle_sequence": [], "optimal_assignment": [], "sequence": []}}))
        for name in ("plate_1.png", "plate_no_light_1.png", "top_1.png", "pick_1.png"):
            z.writestr(f"Metadata/{name}", big)
        z.writestr("Metadata/plate_1_small.png", small)
    return path
