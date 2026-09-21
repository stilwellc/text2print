"""Flatten ElegooSlicer system presets (which chain through `inherits`) into
standalone user presets the CLI will accept. Usage: elegoo_profiles.py <cat> "<name>" out.json"""
import json, sys, pathlib
AS = pathlib.Path.home() / "Library/Application Support/ElegooSlicer/system"
CAT_DIRS = {"machine": ["Elegoo/machine"], "process": ["Elegoo/process"], "filament": ["Elegoo/filament", "OrcaFilamentLibrary/filament"]}

def find(cat, name):
    for d in CAT_DIRS[cat]:
        for p in (AS / d).rglob("*.json"):
            try: j = json.loads(p.read_text())
            except Exception: continue
            if j.get("name") == name or p.stem == name: return j
    raise SystemExit(f"preset not found: {cat} / {name}")

def resolve(cat, name):
    j = find(cat, name); parent = j.pop("inherits", None)
    base = resolve(cat, parent) if parent else {}
    base.update(j); return base

cat, name, out = sys.argv[1], sys.argv[2], sys.argv[3]
j = resolve(cat, name); j["from"] = "User"; j["is_custom_defined"] = "0"
pathlib.Path(out).write_text(json.dumps(j, indent=1)); print(f"{cat}: {name} → {out} ({len(j)} keys)")
