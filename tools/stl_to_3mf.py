"""STL -> 3MF conversion for Bambu Studio / PrusaSlicer.

Usage:
    python3 tools/stl_to_3mf.py model.stl [model.3mf]

Headless-safe: mesh loading is deferred to mesh_io (trimesh only),
so importing or running this never touches pyrender / OpenGL.
"""
import argparse
import pathlib
import sys


def convert(stl_path, out_path=None):
    """Convert one STL to 3MF; returns the output path."""
    import mesh_io   # deferred: keeps module import cheap

    stl_path = pathlib.Path(stl_path)
    out = pathlib.Path(out_path) if out_path else stl_path.with_suffix(".3mf")
    mesh = mesh_io.load_mesh(stl_path)
    mesh.export(str(out))
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description="Convert an STL to 3MF.")
    parser.add_argument("stl", help="input .stl file")
    parser.add_argument("out", nargs="?", default=None,
                        help="output .3mf path (default: alongside input)")
    args = parser.parse_args(argv)
    try:
        out = convert(args.stl, args.out)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
