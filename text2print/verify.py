"""What has actually been printed. data/verified.json maps "texture@nozzle" to a record:
{"result": "ok" | "fail", "date": "YYYY-MM-DD", "note": "..."}. The studio and the builder read it, so warnings and
badges come from real prints, not guesses. Record a print with:
    python -m text2print verify twill 0.4 ok --note "117 mm tray, PLA Matte, perfect"
"""
import datetime
import json
import os
import pathlib

FILE = pathlib.Path(os.environ.get("T2P_VERIFIED", pathlib.Path(__file__).parent / "data" / "verified.json"))
PUBLISHED = {"halftone@0.4": "kowafatcompany's published 0.4 recipe", "halftone@0.8": "kowafatcompany's published 0.8 recipe"}


def load():
    try:
        return json.loads(FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def status(texture, nozzle):
    """-> ("printed" | "failed" | "published" | "untested", note)."""
    key = f"{texture}@{float(nozzle):g}"
    r = load().get(key)
    if r:
        return ("printed" if r.get("result") == "ok" else "failed"), r.get("note", "")
    if key in PUBLISHED:
        return "published", PUBLISHED[key]
    return "untested", ""


def record(texture, nozzle, result, note=""):
    data = load()
    data[f"{texture}@{float(nozzle):g}"] = {"result": result, "date": datetime.date.today().isoformat(), "note": note}
    FILE.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")
    return data
