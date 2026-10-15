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

PROMPT = """You are the designer inside text2print (repo: {root}), a studio for textured 3D prints on a Bambu Lab P2S.
The person typed:

    "{request}"

Their current design (JSON — change it or start fresh, whatever the request means):
{current}
{photo}
How to work (read SKILL.md, sections "Custom pictures and patterns from a prompt" and "Designing with Claude"):
1. Run  {python} -m text2print catalogue  — every shape, texture, option, blend, picture, font, plugin, palette
   colour and saved design you can use. Build on their saved designs and plugins when the request points at them.
2. Compose a design JSON: shape, texture, params, nozzle, colours, options. For anything layered ("woven at the
   base turning into fringe", "fading from blue to cream") use texture "mix" with options.bands, and give every
   band above the first a "blend" ({{"style": fade|dither|wave|zigzag|scallop|drip|noise, "size": mm}}) so the
   textures flow into each other — never stack hard lines unless asked. Two different colours across a blend become
   a stripe gradient automatically. Pick colours from the palette that suit the request.
3. Pictures: words -> picture "text" with a fitting font/layout/placement. A photo -> prepare it first:
   {python} -m text2print picture prepare PHOTO --out NAME [--subject --crop x0,y0,x1,y1 --equalize --contrast 1.4
   --posterize 3 --edges --threshold 0.5]  then LOOK at the PNG it wrote and iterate; use picture "lib:NAME".
   Something to draw ("a koi pond", "art deco sunburst"), a new weave, stitch or shape -> write ONE plugin in
   {plugins} and run  {python} -m text2print plugin check FILE --out {plugins}/previews  (look at the preview).
4. Write the design to {work}/design.json and run  {python} -m text2print design check {work}/design.json
   Look at the preview PNG. Iterate until it is what they asked for (at most 4 checks). Mind the numbers it reports:
   keep colour changes sensible (course_group, fewer halftone layers, or a blend instead of a stripe band).

Reply with ONLY one JSON object on the last line, no code fence:
{{"design": <the final design JSON>, "summary": "<one or two sentences: what you made and any trade-off>"}}
"""


def available():
    return shutil.which("claude") is not None


def start(request, shape, texture, python, plugins_dir, current=None, photo=None):
    with _LOCK:
        if any(j["state"] == "running" for j in JOBS.values()):
            return None, "Claude is already working on a request — wait for it to finish."
        jid = uuid.uuid4().hex[:10]
        JOBS[jid] = dict(state="running", request=request, started=time.time(), result=None, error=None)
    t = threading.Thread(target=_run, args=(jid, request, current or {"shape": shape, "texture": texture}, python,
                                             plugins_dir, photo), daemon=True)
    t.start()
    return jid, None


def _run(jid, request, current, python, plugins_dir, photo):
    plugins_dir = pathlib.Path(plugins_dir); plugins_dir.mkdir(parents=True, exist_ok=True)
    home = plugins_dir.parent; work = home / "agent" / jid; work.mkdir(parents=True, exist_ok=True)
    photo_txt = (f"\nThey uploaded a photo for this design: {photo}  (open it with Read to see it).\n" if photo else "")
    prompt = PROMPT.format(root=ROOT, request=request.replace('"', "'"), current=json.dumps(current, indent=1),
                           photo=photo_txt, plugins=plugins_dir, python=python, work=work)
    cmd = ["claude", "-p", prompt, "--output-format", "json", "--permission-mode", "acceptEdits",
           "--add-dir", str(home),
           "--allowedTools", "Read", "Write", "Edit", "Glob", "Grep",
           f"Bash({python} -m text2print catalogue:*)", f"Bash({python} -m text2print design check:*)",
           f"Bash({python} -m text2print picture prepare:*)", f"Bash({python} -m text2print picture text:*)",
           f"Bash({python} -m text2print plugin check:*)", f"Bash({python} -m text2print plugin list:*)"]
    try:
        r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=TIMEOUT)
        out = r.stdout.strip()
        try:
            text = json.loads(out).get("result", "") if out.startswith("{") else out
        except json.JSONDecodeError:
            text = out
        res = _last_json(text or "")
        if not res or "design" not in res:
            raise RuntimeError((r.stderr or text or "no answer")[-400:])
        JOBS[jid].update(state="done", result=res)
    except subprocess.TimeoutExpired:
        JOBS[jid].update(state="error", error="Claude took longer than 10 minutes — try a simpler request.")
    except Exception as e:
        JOBS[jid].update(state="error", error=f"{type(e).__name__}: {e}"[:500])


def _last_json(text):
    """The last top-level {...} in the text that parses as JSON (the reply ends with it)."""
    depth, start, found = 0, None, None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    found = json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    pass
    return found


def status(jid):
    j = JOBS.get(jid)
    if not j:
        return None
    return dict(state=j["state"], result=j["result"], error=j["error"], seconds=round(time.time() - j["started"]))
