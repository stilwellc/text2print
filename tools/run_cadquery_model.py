"""Run a model script and report what it produced, as JSON.

Usage:
    python3 tools/run_cadquery_model.py model.py [--preview] [--strict]
                                        [--views iso|multi] [--timeout N]

The script is executed in its own directory in a subprocess. Any .stl
files it creates or updates are collected, loaded, and checked; with
--preview each one gets a rendered sheet. One JSON object goes to
stdout so a caller (Claude's self-correct loop) can branch on it:

    {
      "success": true,
      "stdout": "...", "stderr": "...",
      "stls": ["bowl.stl"], "stl": "bowl.stl",
      "previews": ["bowl_preview.png"], "preview": "bowl_preview.png",
      "watertight": {"bowl.stl": true},
      "error": null
    }

success is false when the script fails, produces no STL, a mesh cannot
be loaded, a preview fails, or --strict finds a non-watertight mesh.
Exit code mirrors success (0/1).
"""
import argparse
import json
import pathlib
import subprocess
import sys


def _stl_mtimes(folder):
    return {p.name: p.stat().st_mtime for p in folder.glob("*.stl")}


def run(script, want_preview=False, strict=False, views="multi", timeout=300):
    script = pathlib.Path(script).resolve()
    folder = script.parent
    result = {
        "success": False, "stdout": "", "stderr": "",
        "stls": [], "stl": None,
        "previews": [], "preview": None,
        "watertight": {}, "error": None,
    }

    if not script.is_file():
        result["error"] = f"script not found: {script}"
        return result

    before = _stl_mtimes(folder)
    try:
        proc = subprocess.run(
            [sys.executable, str(script)], cwd=str(folder),
            capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        result["stdout"] = exc.stdout or ""
        result["stderr"] = exc.stderr or ""
        result["error"] = f"script timed out after {timeout}s"
        return result

    result["stdout"] = proc.stdout
    result["stderr"] = proc.stderr
    if proc.returncode != 0:
        result["error"] = f"script exited {proc.returncode}"
        return result

    after = _stl_mtimes(folder)
    fresh = sorted(
        (name for name, mt in after.items() if mt > before.get(name, -1)),
        key=lambda n: after[n], reverse=True)
    if not fresh:
        result["error"] = "script succeeded but exported no STL"
        return result
    result["stls"] = fresh
    result["stl"] = fresh[0]

    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    import mesh_io

    for name in fresh:
        try:
            tm = mesh_io.load_mesh(folder / name)
        except ValueError as exc:
            result["error"] = str(exc)
            return result
        result["watertight"][name] = bool(tm.is_watertight)

        if want_preview:
            import preview   # heavy (pyrender) — only when asked
            out = folder / (pathlib.Path(name).stem + "_preview.png")
            try:
                if views == "multi":
                    preview.render_multi_view(tm, str(out), src_path=name)
                else:
                    preview.render_single(tm, str(out), src_path=name)
            except Exception as exc:
                result["error"] = f"preview failed for {name}: {exc}"
                return result
            result["previews"].append(out.name)

    if result["previews"]:
        result["preview"] = result["previews"][0]

    if strict and not all(result["watertight"].values()):
        bad = [n for n, ok in result["watertight"].items() if not ok]
        result["error"] = f"strict: not watertight: {', '.join(bad)}"
        return result

    result["success"] = True
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Run a model script; report produced STLs as JSON.")
    parser.add_argument("script", help="python script that exports STL(s)")
    parser.add_argument("--preview", action="store_true",
                        help="render a preview sheet per STL")
    parser.add_argument("--strict", action="store_true",
                        help="fail if any produced mesh is not watertight")
    parser.add_argument("--views", choices=("iso", "multi"), default="multi")
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args(argv)

    result = run(args.script, want_preview=args.preview,
                 strict=args.strict, views=args.views, timeout=args.timeout)
    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
