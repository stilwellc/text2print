"""Local app data in ~/.text2print: saved designs, uploaded images, slice results and the printer connection.
Nothing here leaves the machine except what you explicitly send to your own printer."""
import hashlib
import json
import os
import pathlib
import time
import uuid

HOME = pathlib.Path(os.environ.get("T2P_HOME") or os.environ.get("TEXT2PRINT_HOME") or pathlib.Path.home() / ".text2print")
IMAGES = HOME / "images"
MAX_IMAGE = 8 * 1024 * 1024


def _read(name, default):
    try:
        return json.loads((HOME / name).read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _write(name, data):
    HOME.mkdir(parents=True, exist_ok=True)
    tmp = HOME / f".{name}.tmp"; tmp.write_text(json.dumps(data, indent=1)); tmp.replace(HOME / name)


# ── images (halftone pictures) ────────────────────────────────────────────────
def save_image(raw: bytes) -> str:
    from PIL import Image
    import io
    if len(raw) > MAX_IMAGE:
        raise ValueError("image is larger than 8 MB")
    im = Image.open(io.BytesIO(raw)); im.load()
    im = im.convert("RGB"); im.thumbnail((1600, 1600))          # keep colour: CMYK lithophanes need it
    buf = io.BytesIO(); im.save(buf, format="PNG")
    key = hashlib.sha1(buf.getvalue()).hexdigest()[:16]
    IMAGES.mkdir(parents=True, exist_ok=True); (IMAGES / f"{key}.png").write_bytes(buf.getvalue())
    return key


def image_path(key):
    if not key or not all(c in "0123456789abcdef" for c in str(key)):
        return None
    p = IMAGES / f"{key}.png"
    return str(p) if p.exists() else None


# ── slice cache ───────────────────────────────────────────────────────────────
def design_key(d: dict) -> str:
    return hashlib.sha1(json.dumps(d, sort_keys=True, default=str).encode()).hexdigest()[:20]


def get_slice(key):
    return _read("slices.json", {}).get(key)


def put_slice(key, result):
    data = _read("slices.json", {}); data[key] = dict(result, at=time.time())
    if len(data) > 400:                                         # keep the newest 400
        data = dict(sorted(data.items(), key=lambda kv: kv[1].get("at", 0))[-400:])
    _write("slices.json", data)


# ── saved designs ─────────────────────────────────────────────────────────────
def designs():
    return _read("designs.json", [])


def _id(did):
    """A design id is short hex. Anything else (a path, say) is replaced, never used as a file name."""
    did = str(did or "")
    return did if 0 < len(did) <= 32 and all(c in "0123456789abcdef" for c in did) else None


def save_design(entry: dict):
    data = designs()
    entry = dict(entry, id=_id(entry.get("id")) or uuid.uuid4().hex[:10], saved=time.time())
    data = [d for d in data if d["id"] != entry["id"]] + [entry]
    _write("designs.json", data[-200:])
    return entry


def delete_design(did):
    data = [d for d in designs() if d["id"] != did]; _write("designs.json", data)
    if _id(did):
        (HOME / "thumbs" / f"{did}.png").unlink(missing_ok=True)


def save_thumb(did, png: bytes):
    if not _id(did) or not png.startswith(b"\x89PNG"):
        return
    (HOME / "thumbs").mkdir(parents=True, exist_ok=True)
    (HOME / "thumbs" / f"{did}.png").write_bytes(png[:2_000_000])


def thumb_path(did):
    if not _id(did):
        return None
    p = HOME / "thumbs" / f"{did}.png"
    return p if p.exists() else None


# ── printer connection (typed in by the user in the studio) ───────────────────
def printer_config():
    return _read("printer.json", {})


def save_printer_config(cfg: dict):
    keep = {k: str(cfg.get(k, "")).strip() for k in ("ip", "serial", "access_code", "name")}
    if not keep["access_code"]:                                 # the dialog leaves the code blank to mean "unchanged"
        keep["access_code"] = str(printer_config().get("access_code", ""))
    _write("printer.json", keep)
    try:
        os.chmod(HOME / "printer.json", 0o600)
    except OSError:
        pass
    return keep
