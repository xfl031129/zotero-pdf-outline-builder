from __future__ import annotations

import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: build_xpi.py PLUGIN_ROOT OUT_XPI", file=sys.stderr)
        return 2

    plugin = Path(argv[1]).resolve()
    out = Path(argv[2]).resolve()
    include_roots = ["manifest.json", "chrome.manifest", "bootstrap.js", "chrome", "native"]

    out.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(out, "w", ZIP_DEFLATED) as zf:
        for root in include_roots:
            path = plugin / root
            if path.is_file():
                zf.write(path, path.relative_to(plugin).as_posix())
                continue
            for child in path.rglob("*"):
                if "__pycache__" in child.parts:
                    continue
                if child.suffix in {".pyc", ".pyo"}:
                    continue
                if child.is_file():
                    zf.write(child, child.relative_to(plugin).as_posix())

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
