from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import traceback
import uuid
from pathlib import Path


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Zotero helper for PDF outline generation.")
    parser.add_argument("--job", type=Path, help="JSON job file with all arguments.")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--project-src", type=Path)
    parser.add_argument("--min-confidence", type=float, default=0.30)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--debug-pdf", type=Path)
    args = parser.parse_args(argv)

    if args.job:
        job = json.loads(args.job.read_text(encoding="utf-8-sig"))
        args.input = Path(job["input"])
        args.json_out = Path(job["json_out"])
        args.project_src = Path(job["project_src"]) if job.get("project_src") else None
        args.min_confidence = float(job.get("min_confidence", args.min_confidence))
        args.force = bool(job.get("force", args.force))
        args.debug_pdf = Path(job["debug_pdf"]) if job.get("debug_pdf") else None

    if not args.input or not args.json_out:
        parser.error("--input and --json-out are required unless --job is used")

    try:
        os.environ["PYTHONIOENCODING"] = "utf-8"
        if args.project_src:
            sys.path.insert(0, str(args.project_src.resolve()))
        from zotero_pdf_outline_builder.outline import BuildOptions, build_outline_for_pdf

        input_path = args.input.resolve()
        if not input_path.exists():
            raise FileNotFoundError(f"PDF does not exist: {input_path}")

        token = uuid.uuid4().hex
        temp_output = input_path.with_name(f"{input_path.stem}.outline-tmp-{token}{input_path.suffix}")
        backup_path = input_path.with_name(f"{input_path.stem}.outline-backup-{token}{input_path.suffix}")

        options = BuildOptions(
            dry_run=False,
            force=args.force,
            min_confidence=args.min_confidence,
        )
        result = build_outline_for_pdf(input_path, temp_output, options, debug_pdf_path=args.debug_pdf)
        if result.skipped_reason or not result.entries:
            if temp_output.exists():
                temp_output.unlink()
            write_json(
                args.json_out,
                {
                    "ok": False,
                    "input": str(input_path),
                    "error": result.skipped_reason or "No outline entries were generated.",
                    "entries": [],
                },
            )
            return 2

        shutil.move(str(input_path), str(backup_path))
        try:
            shutil.move(str(temp_output), str(input_path))
        except Exception:
            if input_path.exists():
                input_path.unlink()
            shutil.move(str(backup_path), str(input_path))
            raise

        if backup_path.exists():
            backup_path.unlink()

        write_json(
            args.json_out,
            {
                "ok": True,
                "input": str(input_path),
                "count": len(result.entries),
                "entries": [entry.as_dict() for entry in result.entries],
            },
        )
        return 0
    except Exception as exc:
        write_json(
            args.json_out,
            {
                "ok": False,
                "input": str(args.input),
                "error": str(exc),
                "traceback": traceback.format_exc(),
            },
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
