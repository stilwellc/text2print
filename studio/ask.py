"""Claude as the designer, from the studio.

A thread is a conversation with one Claude Code session (claude -p, resumed with --resume): the first message
composes a design (or several: variations, a matching set), follow-ups refine it in the same session, and a print
review compares a photo of a finished print with the design and records what it learned. Runs stream their steps
(stream-json) so the studio shows progress and interim previews. One run at a time."""
import json
import os
import pathlib
import shutil
import subprocess
import threading
import time
import uuid

ROOT = pathlib.Path(__file__).resolve().parent.parent
HOME = pathlib.Path(os.environ.get("T2P_HOME", pathlib.Path.home() / ".text2print"))
THREADS = {}            # thread id -> dict(session, turns: [...], state, steps, result, error, started, work)
_LOCK = threading.Lock()
TIMEOUT = 900

RULES = """How to work (SKILL.md, sections "Custom pictures and patterns from a prompt" and "Designing with Claude"):
- `{py} -m text2print catalogue` lists every shape, texture, option, blend, picture, font, plugin, palette colour and
  saved design. Build on saved designs and plugins when the request points at them.
- A design is JSON: shape, texture, params, nozzle, colours, options. Layered looks use texture "mix" + options.bands
  with a "blend" on every band above the first (fade | dither | wave | zigzag | scallop | drip | noise, size mm).
- Photos: decide whether the photo is the PICTURE to print (a pet, a face, a logo) or a REFERENCE to design from
  ("make something like this"). Picture: `{py} -m text2print picture prepare PHOTO --out NAME [...]`, look at the
  PNG, use picture "lib:NAME". Reference: Read it, infer shape, texture and colours; `{py} -m text2print palette
  match PHOTO` gives the nearest filament colours.
- Anything to draw, or a new weave / stitch / shape: ONE plugin per thing in {plugins}, checked with
  `{py} -m text2print plugin check FILE --out {plugins}/previews` (look at the preview). Give every plugin a
  PARAMS dict of 2-4 sliders (see SKILL.md) so the person can tune it without you.
- Check every design: write it to {work}/<name>.json, run `{py} -m text2print design check {work}/<name>.json`, LOOK
  at the preview PNG (halftone previews use raking light — judge the picture there). For budgets on time, colour
  changes or grams, confirm with `{py} -m text2print design slice {work}/<name>.json` (real Bambu Studio numbers
  and a sliced-layer preview PNG) and adjust until the design fits.
- Their taste and what prints well on their printer are below — respect them. When they state a lasting preference
  ("never…", "I love…"), append one line to {home}/taste.md.
{memory}"""

DESIGN = """You are the designer inside text2print (repo: {root}), a studio for textured 3D prints on a Bambu Lab P2S.
The person typed:

    "{request}"

Their current design (change it or start fresh, whatever the request means):
{current}
{photo}{budget}{want}
{rules}
Reply with ONLY one JSON object on the last line, no code fence:
{{"designs": [{{"label": "<short name>", "design": <design JSON>, "summary": "<what it is + any trade-off>",
               "preview": "<the preview PNG file name design check wrote in {work}>"}}, ...],
  "summary": "<one or two sentences for the person>"}}
"""

FOLLOW = """The person replied in the studio:

    "{request}"

The design currently loaded in the studio (they may have changed it since your last answer):
{current}
{photo}{budget}{want}
Same rules as before. Check what you change. Reply with ONLY the same kind of JSON object on the last line."""

REVIEW = """You are the designer inside text2print (repo: {root}). The person printed this design on their Bambu Lab P2S and
photographed the result:

    photo of the print: {photo_path}
    their notes: "{request}"

The design (JSON):
{current}

1. Read the photo. Build the design with `{py} -m text2print design check {work}/printed.json` (write it there first)
   and compare the photo with the preview: what came out as intended, what didn't (stringing, failed droop, colour
   bleed, layer gaps, sag, warping, a picture that doesn't read…), and why.
2. Record it: append a dated, specific bullet to {home}/knowledge.md (texture, nozzle, settings, what happened, what
   to do differently) and run `{py} -m text2print verify <texture> 0.4 ok|fail --note "<short>"` — "fail" only when
   the TEXTURE itself didn't print (droop didn't droop, rods collapsed, the picture doesn't read); a tight lid,
   stringing or a setting to tweak is "ok" with the issue in the note.
3. Propose a corrected design if something failed (or the same one if it printed well), checked as usual.
{rules}
Reply with ONLY one JSON object on the last line:
{{"designs": [{{"label": "Adjusted", "design": <JSON>, "summary": "<what to change and why>", "preview": "<png name>"}}],
  "summary": "<what printed well, what didn't, and what you recorded>"}}
"""


def available():
    return shutil.which("claude") is not None


def _memory():
    out = []
    for name, title in (("taste.md", "Their taste"), ("knowledge.md", "What prints well on their P2S")):
        p = HOME / name
        if p.exists() and p.read_text().strip():
            out.append(f"{title} ({p}):\n" + p.read_text()[-4000:])
    return "\n\n".join(out) if out else "(no taste or print notes recorded yet)"


def _tools(py):
    cmds = ["catalogue", "design check", "design slice", "picture prepare", "picture text", "palette match",
            "plugin check", "plugin list", "verify"]
    return ["Read", "Write", "Edit", "Glob", "Grep"] + [f"Bash({py} -m text2print {c}:*)" for c in cmds]


def start(request, current, py, plugins_dir, photo=None, thread=None, mode="design", variations=0, budget=None):
    with _LOCK:
        if any(t["state"] == "running" for t in THREADS.values()):
            return None, "Claude is already working — wait for it to finish."
        if thread and thread in THREADS:
            T = THREADS[thread]
        else:
            thread = uuid.uuid4().hex[:10]
            T = THREADS[thread] = dict(session=None, turns=[], work=HOME / "agent" / thread)
        T.update(state="running", steps=[], result=None, error=None, started=time.time(), preview=None)
        T["turns"].append(dict(role="you", text=request))
    T["work"].mkdir(parents=True, exist_ok=True)
    args = (thread, request, current, py, pathlib.Path(plugins_dir), photo, mode, variations, budget)
    threading.Thread(target=_run, args=args, daemon=True).start()
    return thread, None


def _prompt(T, request, current, py, plugins, photo, mode, variations, budget):
    fmt = dict(root=ROOT, request=request.replace('"', "'"), current=json.dumps(current, indent=1), py=py,
               plugins=plugins, work=T["work"], home=HOME)
    fmt["rules"] = RULES.format(memory=_memory(), **fmt)
    fmt["photo"] = (f"\nThey added a photo: {photo}  (Read it).\n" if photo and mode != "review" else "")
    b = {k: v for k, v in (budget or {}).items() if v}
    fmt["budget"] = ("\nBudget — the design must fit: " + ", ".join(
        f"{ {'hours': 'print time ≤ ', 'changes': 'colour changes ≤ ', 'grams': 'filament ≤ '}[k]}{v}"
        + ({"hours": " h", "changes": "", "grams": " g"}[k]) for k, v in b.items()) + " (confirm with design slice).\n") if b else ""
    fmt["want"] = (f"\nGive {variations} clearly different directions (different textures, blends or colour stories), "
                   f"each its own checked design.\n" if variations > 1 else
                   "\nIf they ask for a set or several pieces, return one design per piece with a consistent motif, "
                   "colours and scale.\n")
    if mode == "review":
        return REVIEW.format(photo_path=photo, **fmt)
    if T["session"]:
        return FOLLOW.format(**fmt)
    return DESIGN.format(**fmt)


STEP_WORDS = [("catalogue", "Reading what it can use"), ("design check", "Building and checking the design"),
              ("design slice", "Slicing in Bambu Studio"), ("picture prepare", "Preparing the photo"),
              ("palette match", "Matching colours to filaments"), ("plugin check", "Checking the new pattern"),
              ("plugin list", "Listing plugins"), ("verify", "Recording the print result")]


def _describe(tool, inp):
    if tool == "Bash":
        cmd = inp.get("command", "")
        return next((w for k, w in STEP_WORDS if k in cmd), "Running a tool")
    if tool in ("Write", "Edit"):
        name = pathlib.Path(inp.get("file_path", "")).name
        if name.endswith(".py"):
            return f"Writing {name}"
        if name in ("taste.md", "knowledge.md"):
            return f"Remembering ({name})"
        return f"Writing {name}"
    if tool == "Read":
        name = pathlib.Path(inp.get("file_path", "")).name
        return f"Looking at {name}" if name.lower().endswith((".png", ".jpg", ".jpeg", ".webp")) else f"Reading {name}"
    return tool


def _run(thread, request, current, py, plugins, photo, mode, variations, budget):
    T = THREADS[thread]
    plugins.mkdir(parents=True, exist_ok=True)
    prompt = _prompt(T, request, current, py, plugins, photo, mode, variations, budget)
    cmd = ["claude", "-p", prompt, "--output-format", "stream-json", "--verbose", "--permission-mode", "acceptEdits",
           "--add-dir", str(HOME)]
    if T["session"]:
        cmd += ["--resume", T["session"]]
    cmd += ["--allowedTools"] + _tools(py)
    final = ""
    try:
        proc = subprocess.Popen(cmd, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
        t0 = time.time()
        for line in proc.stdout:
            if time.time() - t0 > TIMEOUT:
                proc.kill(); raise TimeoutError
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e.get("session_id"):
                T["session"] = e["session_id"]
            if e.get("type") == "assistant":
                for c in e["message"].get("content", []):
                    if c.get("type") == "tool_use":
                        T["steps"].append(dict(t=round(time.time() - T["started"]), text=_describe(c["name"], c.get("input") or {})))
            elif e.get("type") == "user":                         # a tool finished: maybe a new preview exists
                pngs = sorted(T["work"].glob("*.png"), key=lambda p: p.stat().st_mtime)
                if pngs:
                    T["preview"] = pngs[-1].name
            elif e.get("type") == "result":
                final = e.get("result") or ""
        proc.wait(timeout=30)
        res = _last_json(final)
        if res and "design" in res and "designs" not in res:     # the one-design shape, accepted too
            res = {"designs": [dict(label="Design", design=res["design"], summary=res.get("summary", ""))],
                   "summary": res.get("summary", "")}
        if not res or not res.get("designs"):
            raise RuntimeError((final or proc.stderr.read() or "no answer")[-500:])
        T.update(state="done", result=res)
        T["turns"].append(dict(role="claude", text=res.get("summary", ""), designs=len(res["designs"])))
    except TimeoutError:
        T.update(state="error", error="Claude took longer than 15 minutes — try a simpler request.")
    except Exception as ex:
        T.update(state="error", error=f"{type(ex).__name__}: {ex}"[:600])


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


def status(thread):
    T = THREADS.get(thread)
    if not T:
        return None
    return dict(state=T["state"], result=T["result"], error=T["error"], seconds=round(time.time() - T["started"]),
                steps=T["steps"][-12:], preview=T.get("preview"), turns=T["turns"])


def note_taste(verdict, design, note=""):
    """Thumbs up / down from the studio -> a line in taste.md that every future design reads."""
    HOME.mkdir(parents=True, exist_ok=True)
    d = design or {}
    o = d.get("options") or {}
    what = f"{d.get('shape')} / {d.get('texture')}"
    if o.get("bands"):
        what += " [" + " → ".join(f"{b.get('texture')}{'~' + b['blend']['style'] if b.get('blend') else ''}"
                                  for b in o["bands"]) + "]"
    if d.get("colours"):
        what += " in " + ", ".join(d["colours"])
    line = f"- {time.strftime('%Y-%m-%d')} {'LIKED' if verdict == 'like' else 'DISLIKED'}: {what}" + (f" — {note}" if note else "")
    p = HOME / "taste.md"
    if not p.exists():
        p.write_text("# Taste — read by Claude before every design\n\n")
    with p.open("a") as f:
        f.write(line + "\n")
    return line
