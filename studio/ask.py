"""'Ask Claude' from the studio: a request in words becomes a plugin (picture, weave or stitch), written and
checked by a headless Claude Code run that follows SKILL.md. One request at a time; results land in the plugin
folder the studio already watches, so the new pattern appears on the next catalogue load."""
import json
import pathlib
import re
import shutil
import subprocess
import threading
import time
import uuid

ROOT = pathlib.Path(__file__).resolve().parent.parent
JOBS = {}
_LOCK = threading.Lock()
TIMEOUT = 600

PROMPT = """You are adding a custom pattern to text2print (repo: {root}). The person asked, in the studio:

    "{request}"

Their current design: shape "{shape}", texture "{texture}".

Read SKILL.md, section "Custom pictures and patterns from a prompt", and the example plugins in plugin_examples/.
Decide what fits the request best:
  - a PICTURE (shown by halftone walls, lithophanes, CMYK tiles, or as a mask for knit/zigzag/wave), or
  - a WOVEN pattern (rods, lattice API), or
  - a fabric STITCH (wall displacement), or
  - a SHAPE (a new piece to texture: a round silhouette via radius(v, z), or a plan outline via outline(v) -> sdf).
If they asked for words only, don't write a plugin: answer with kind "text" and the words.

Write exactly ONE file: {plugins}/<short_snake_name>.py (don't overwrite an existing file: pick a new name).
Then run:   {python} -m text2print plugin check {plugins}/<short_snake_name>.py --out {plugins}/previews
Open the preview PNG it prints and look at it. Iterate (edit the file, check again) until the verdict is "ok" and
the preview clearly shows what they asked for. Keep it to at most 4 checks.

Reply with ONLY one JSON object on the last line, no code fence:
{{"kind": "picture|woven|stitch|shape|text", "key": "lib:<stem>, x_<stem> or s_<stem> (empty for text)", "name": "<display name>",
  "text": "<words, for kind text>", "summary": "<one sentence on what you made>"}}
"""


def available():
    return shutil.which("claude") is not None


def start(request, shape, texture, python, plugins_dir):
    with _LOCK:
        if any(j["state"] == "running" for j in JOBS.values()):
            return None, "Claude is already working on a request — wait for it to finish."
        jid = uuid.uuid4().hex[:10]
        JOBS[jid] = dict(state="running", request=request, started=time.time(), result=None, error=None)
    t = threading.Thread(target=_run, args=(jid, request, shape, texture, python, plugins_dir), daemon=True)
    t.start()
    return jid, None


def _run(jid, request, shape, texture, python, plugins_dir):
    plugins_dir = pathlib.Path(plugins_dir); plugins_dir.mkdir(parents=True, exist_ok=True)
    prompt = PROMPT.format(root=ROOT, request=request.replace('"', "'"), shape=shape, texture=texture,
                           plugins=plugins_dir, python=python)
    cmd = ["claude", "-p", prompt, "--output-format", "json", "--permission-mode", "acceptEdits",
           "--add-dir", str(plugins_dir),
           "--allowedTools", "Read", "Write", "Edit", "Glob", "Grep",
           f"Bash({python} -m text2print plugin check:*)", f"Bash({python} -m text2print plugin list:*)"]
    try:
        r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=TIMEOUT)
        out = r.stdout.strip()
        try:
            text = json.loads(out).get("result", "") if out.startswith("{") else out
        except json.JSONDecodeError:
            text = out
        found = re.findall(r"\{[^{}]*\"kind\"[^{}]*\}", text or "")
        if not found:
            raise RuntimeError((r.stderr or text or "no answer")[-400:])
        res = json.loads(found[-1])
        JOBS[jid].update(state="done", result=res)
    except subprocess.TimeoutExpired:
        JOBS[jid].update(state="error", error="Claude took longer than 10 minutes — try a simpler request.")
    except Exception as e:
        JOBS[jid].update(state="error", error=f"{type(e).__name__}: {e}"[:500])


def status(jid):
    j = JOBS.get(jid)
    if not j:
        return None
    return dict(state=j["state"], result=j["result"], error=j["error"], seconds=round(time.time() - j["started"]))
