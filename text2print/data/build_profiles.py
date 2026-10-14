"""Dev script: resolve Bambu Studio's P2S system presets (machine + process + PLA Matte, following every
`inherits` link) on top of a known-good CLI-exported 0.4 project config, and write one resolved config per
nozzle into this folder. Run on a Mac with Bambu Studio installed:  python text2print/data/build_profiles.py"""
import json
import pathlib

SYS = pathlib.Path.home() / "Library/Application Support/BambuStudio/system/BBL"
HERE = pathlib.Path(__file__).parent
BASE = json.loads((HERE / "p2s_0.4_export.json").read_text())      # CLI --export-settings of a real 0.4 project
PRESETS = {
    "0.2": ("Bambu Lab P2S 0.2 nozzle", "0.10mm Standard @BBL P2S 0.2 nozzle", "Bambu PLA Matte @BBL P2S 0.2 nozzle"),
    "0.4": ("Bambu Lab P2S 0.4 nozzle", "0.20mm Standard @BBL P2S", "Bambu PLA Matte @BBL P2S"),
    "0.6": ("Bambu Lab P2S 0.6 nozzle", "0.30mm Standard @BBL P2S 0.6 nozzle", "Bambu PLA Matte @BBL P2S 0.6 nozzle"),
    "0.8": ("Bambu Lab P2S 0.8 nozzle", "0.40mm Standard @BBL P2S 0.8 nozzle", "Bambu PLA Matte @BBL P2S 0.8 nozzle"),
}
DROP = {"name", "inherits", "from", "instantiation", "setting_id", "type", "description", "filament_id"}


def chain(kind, name):
    out = {}
    while name:
        p = SYS / kind / f"{name}.json"
        if not p.exists():
            break
        d = json.loads(p.read_text())
        for k, v in d.items():
            out.setdefault(k, v)
        name = d.get("inherits")
    return {k: v for k, v in out.items() if k not in DROP}


for nozzle, (machine, process, filament) in PRESETS.items():
    cfg = dict(BASE)
    for kind, name in (("machine", machine), ("process", process), ("filament", filament)):
        resolved = chain(kind, name)
        for k, v in resolved.items():
            if k in cfg or k.endswith("_settings_id"):
                cfg[k] = v
        # presets store their compatibility as `compatible_printers`; a project stores it per kind
        if kind == "process" and "compatible_printers" in resolved:
            cfg["print_compatible_printers"] = resolved["compatible_printers"]
    cfg["printer_settings_id"], cfg["print_settings_id"] = machine, process
    cfg["filament_settings_id"] = [filament]
    (HERE / f"p2s_{nozzle}.json").write_text(json.dumps(cfg, indent=1, sort_keys=True))
    print(nozzle, cfg["nozzle_diameter"], cfg["layer_height"], cfg["line_width"], cfg["printable_area"],
          cfg.get("wipe_tower_x"), len(cfg))
