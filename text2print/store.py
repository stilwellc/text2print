"""Local app data in ~/.text2print: saved designs, uploaded images, slice results and the printer connection.
Nothing here leaves the machine except what you explicitly send to your own printer."""
import hashlib
import json
import os
import pathlib
import time
import uuid

HOME = pathlib.Path(os.environ.get("TEXT2PRINT_HOME", pathlib.Path.home() / ".text2print"))
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
    im = im.convert("L"); im.thumbnail((1600, 1600))
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


def save_design(entry: dict):
    data = designs()
    entry = dict(entry, id=entry.get("id") or uuid.uuid4().hex[:10], saved=time.time())
    data = [d for d in data if d["id"] != entry["id"]] + [entry]
    _write("designs.json", data[-200:])
    return entry


def delete_design(did):
    data = [d for d in designs() if d["id"] != did]; _write("designs.json", data)
    thumb = HOME / "thumbs" / f"{did}.png"
    thumb.unlink(missing_ok=True)


def save_thumb(did, png: bytes):
    (HOME / "thumbs").mkdir(parents=True, exist_ok=True)
    (HOME / "thumbs" / f"{did}.png").write_bytes(png[:2_000_000])


def thumb_path(did):
    p = HOME / "thumbs" / f"{did}.png"
    return p if p.exists() else None


# ── printer connection (typed in by the user in the studio) ───────────────────
def printer_config():
    return _read("printer.json", {})


def save_printer_config(cfg: dict):
    keep = {k: str(cfg.get(k, "")).strip() for k in ("ip", "serial", "access_code", "name")}
    _write("printer.json", keep)
    try:
        os.chmod(HOME / "printer.json", 0o600)
    except OSError:
        pass
    return keep
