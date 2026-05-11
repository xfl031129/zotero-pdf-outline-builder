from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable, List, Optional

from .outline import BuildOptions, build_outline_for_pdf


def _pdf_inputs(path: Path, recursive: bool) -> Iterable[Path]:
    if path.is_file():
        yield path
        return

    pattern = "**/*.pdf" if recursive else "*.pdf"
    for candidate in sorted(path.glob(pattern)):
        if candidate.is_file():
            yield candidate


def _default_output_path(input_path: Path, output_dir: Optional[Path]) -> Path:
    name = f"{input_path.stem}.outlined{input_path.suffix}"
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir / name
    return input_path.with_name(name)


def _default_debug_path(input_path: Path, output_dir: Optional[Path]) -> Path:
    name = f"{input_path.stem}.debug{input_path.suffix}"
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir / name
    return input_path.with_name(name)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="zotero-pdf-outline-builder",
        description="Generate PDF outlines/bookmarks for papers that lack them.",
    )
    parser.add_argument("input", type=Path, help="PDF file or folder containing PDFs.")
    parser.add_argument("-o", "--output", type=Path, help="Output PDF path for single-file mode.")
    parser.add_argument("--output-dir", type=Path, help="Output directory for batch mode.")
    parser.add_argument("--recursive", action="store_true", help="Recursively scan a folder for PDFs.")
    parser.add_argument("--dry-run", action="store_true", help="Print detected outline without writing a PDF.")
    parser.add_argument("--debug-pdf", type=Path, help="Write a copy of the PDF with detected headings boxed.")
    parser.add_argument(
        "--debug-dir",
        type=Path,
        help="Output directory for debug PDFs in batch mode.",
    )
    parser.add_argument("--force", action="store_true", help="Replace existing PDF outline if one is present.")
    parser.add_argument(
        "--max-toc-pages",
        type=int,
        default=10,
        help="How many early pages to scan for a printed table of contents.",
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.35,
        help="Minimum confidence required for fallback heading candidates.",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    input_path = args.input.expanduser().resolve()
    if not input_path.exists():
        parser.error(f"Input does not exist: {input_path}")

    if input_path.is_dir() and args.output:
        parser.error("--output can only be used with a single PDF file.")

    options = BuildOptions(
        dry_run=args.dry_run,
        force=args.force,
        max_toc_pages=args.max_toc_pages,
        min_confidence=args.min_confidence,
    )

    exit_code = 0
    inputs = list(_pdf_inputs(input_path, args.recursive))
    if not inputs:
        print(f"No PDF files found in {input_path}", file=sys.stderr)
        return 1

    for pdf_path in inputs:
        output_path = args.output if args.output else _default_output_path(pdf_path, args.output_dir)
        debug_path = args.debug_pdf
        if args.debug_dir:
            debug_path = _default_debug_path(pdf_path, args.debug_dir)
        try:
            result = build_outline_for_pdf(pdf_path, output_path, options, debug_pdf_path=debug_path)
        except Exception as exc:
            exit_code = 1
            print(f"[error] {pdf_path}: {exc}", file=sys.stderr)
            continue

        print(result.format_summary())

    return exit_code
