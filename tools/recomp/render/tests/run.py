"""Run authored GS transfer and palette fixtures against production sources.

Example (from the repository root):
  python tools/recomp/render/tests/run.py --cxx <C++17 compiler> --out <private output>
No game inputs, generated translation, graphics context, or existing build are needed.
"""
import argparse
import json
import pathlib
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", required=True, help="C++17 compiler executable")
    parser.add_argument("--out", type=pathlib.Path,
                        help="Build outputs (default: ignored local/gs-transfer-tests)")
    args = parser.parse_args()
    here = pathlib.Path(__file__).resolve().parent
    repo = here.parents[3]
    out = (args.out or repo / "local/gs-transfer-tests").resolve()
    try:
        relative = out.relative_to(repo)
    except ValueError:
        pass
    else:
        if not relative.parts or relative.parts[0] != "local":
            parser.error("--out inside the repository must be under ignored local/")
    out.mkdir(parents=True, exist_ok=True)
    source = here.parent
    flags = ["-std=c++17", "-O2", "-fno-strict-aliasing", "-ffp-contract=off",
             "-frounding-math", "-I", str(source)]
    if sys.platform == "win32":
        flags += ["-DNOMINMAX", "-static"]
    records = []
    for test_name in ("gs_transfer_test", "uniform_palette_gif_test", "display_extent_test"):
        program = out / (test_name + (".exe" if sys.platform == "win32" else ""))
        command = [args.cxx] + flags + [str(source / "gs.cpp"),
                   str(source / "worldfill.cpp"), str(here / (test_name + ".cpp"))]
        command += ["-o", str(program)]
        if sys.platform == "win32":
            command += ["-lpthread"]
        for label, argv, timeout in [("compile", command, 120),
                                     ("test", [str(program)], 15)]:
            completed = subprocess.run(argv, cwd=repo, text=True, capture_output=True,
                                       timeout=timeout)
            record = {"phase": label, "fixture": test_name, "argv": argv, "exit": completed.returncode,
                      "stdout": completed.stdout, "stderr": completed.stderr}
            records.append(record)
            (out / "results.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
            print(completed.stdout, end="")
            print(completed.stderr, end="", file=sys.stderr)
            if completed.returncode:
                return completed.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
