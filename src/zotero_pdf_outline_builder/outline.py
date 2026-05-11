from __future__ import annotations

import re
import shutil
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

try:
    import fitz
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "PyMuPDF is required. Install it with: pip install -r requirements.txt"
    ) from exc


RectTuple = Tuple[float, float, float, float]

TOC_LINE_RE = re.compile(
    r"^\s*(?P<title>.+?)\s*(?:\.{2,}|\s{2,})\s*(?P<page>[ivxlcdmIVXLCDM]+|\d{1,4})\s*$"
)

NUMBERED_HEADING_RE = re.compile(
    r"^\s*([1-9]\d?(?:\.\d{1,2}){0,5}\.?)\s+(.{2,140})$",
    re.IGNORECASE,
)

ROMAN_HEADING_RE = re.compile(r"^\s*([IVX]{1,6})\.\s+(.{2,140})$")

LETTERED_HEADING_RE = re.compile(r"^\s*[A-Z]\.\s+.{2,140}$")

COMMON_SECTION_RE = re.compile(
    r"^\s*(abstract|introduction|background|related work|literature review|"
    r"materials and methods|methods|methodology|model|approach|implementation|"
    r"experiment(?:s|al setup)?|evaluation|results|discussion|limitations|"
    r"conclusion|conclusions|references|bibliography|acknowledg(?:e)?ments?|"
    r"appendix)\s*$",
    re.IGNORECASE,
)

CAPTION_RE = re.compile(
    r"^\s*(fig(?:ure)?|table|algorithm|equation|eq\.?)\s*[\d:.]",
    re.IGNORECASE,
)

INLINE_ROMAN_HEADING_RE = re.compile(
    r"^\s*([IVX]{1,6}\.\s+[A-Z][A-Z0-9,()\- ]{8,}?)(?=\s+[A-Z][a-z]|\s*$)"
)

CONTENTS_MARKERS = ("contents", "table of contents", "目录", "目 录")


@dataclass
class BuildOptions:
    dry_run: bool = False
    force: bool = False
    max_toc_pages: int = 10
    min_confidence: float = 0.35


@dataclass
class TextLine:
    text: str
    page: int
    bbox: RectTuple
    max_size: float
    avg_size: float
    bold: bool
    order: int = 0
    column: int = 0

    @property
    def y0(self) -> float:
        return self.bbox[1]

    @property
    def x0(self) -> float:
        return self.bbox[0]

    @property
    def x1(self) -> float:
        return self.bbox[2]

    @property
    def y1(self) -> float:
        return self.bbox[3]


@dataclass
class OutlineEntry:
    level: int
    title: str
    page: int
    confidence: float
    source: str
    bbox: Optional[RectTuple] = None
    font_size: Optional[float] = None
    bold: bool = False
    order: Optional[int] = None

    def as_toc_item(self) -> List[object]:
        return [self.level, self.title, self.page]

    def as_dict(self) -> Dict[str, object]:
        return {
            "level": self.level,
            "title": self.title,
            "page": self.page,
            "confidence": round(self.confidence, 3),
            "source": self.source,
            "bbox": self.bbox,
            "font_size": round(self.font_size, 2) if self.font_size is not None else None,
            "bold": self.bold,
            "order": self.order,
        }


@dataclass
class BuildResult:
    input_path: Path
    output_path: Path
    entries: List[OutlineEntry]
    skipped_reason: Optional[str]
    dry_run: bool
    debug_pdf_path: Optional[Path] = None

    def format_summary(self) -> str:
        label = "dry-run" if self.dry_run else "written"
        if self.skipped_reason:
            return f"[skip] {self.input_path.name}: {self.skipped_reason}"
        lines = [f"[{label}] {self.input_path.name}: {len(self.entries)} outline entries"]
        for entry in self.entries[:30]:
            indent = "  " * max(0, entry.level - 1)
            font = f", {entry.font_size:.1f}pt" if entry.font_size else ""
            lines.append(
                f"  p.{entry.page:>3} L{entry.level} {indent}{entry.title} "
                f"({entry.source}, {entry.confidence:.2f}{font})"
            )
        if len(self.entries) > 30:
            lines.append(f"  ... {len(self.entries) - 30} more")
        if not self.dry_run:
            lines.append(f"  -> {self.output_path}")
        if self.debug_pdf_path:
            lines.append(f"  debug -> {self.debug_pdf_path}")
        return "\n".join(lines)


def build_outline_for_pdf(
    input_path: Path,
    output_path: Path,
    options: BuildOptions,
    debug_pdf_path: Optional[Path] = None,
) -> BuildResult:
    input_path = input_path.resolve()
    output_path = output_path.resolve()
    debug_pdf_path = debug_pdf_path.resolve() if debug_pdf_path else None

    if input_path.suffix.lower() != ".pdf":
        return BuildResult(input_path, output_path, [], "not a PDF file", options.dry_run)

    doc = fitz.open(str(input_path))
    try:
        existing = doc.get_toc(simple=True)
        if existing and not options.force:
            entries = entries_from_existing_toc(existing, input_path, output_path, options.dry_run)
            if not options.dry_run and input_path != output_path:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(str(input_path), str(output_path))
                if debug_pdf_path:
                    debug_pdf_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(str(input_path), str(debug_pdf_path))
            return BuildResult(input_path, output_path, entries, None, options.dry_run, debug_pdf_path)

        entries = extract_from_printed_toc(doc, max_pages=options.max_toc_pages)
        if len(entries) < 3:
            entries = extract_from_headings(doc, min_confidence=options.min_confidence)

        entries = normalize_entries(entries, page_count=doc.page_count)
        if not entries:
            return BuildResult(input_path, output_path, [], "no outline candidates found", options.dry_run)

        if debug_pdf_path:
            write_debug_pdf(doc, debug_pdf_path, entries)

        if not options.dry_run:
            if input_path == output_path:
                raise ValueError("refusing to overwrite input PDF; choose a different output path")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            doc.set_toc([entry.as_toc_item() for entry in entries])
            doc.save(str(output_path), garbage=4, deflate=True)

        return BuildResult(input_path, output_path, entries, None, options.dry_run, debug_pdf_path)
    finally:
        doc.close()


def extract_from_printed_toc(doc, max_pages: int) -> List[OutlineEntry]:
    raw_entries: List[Tuple[int, str, str]] = []
    scan_limit = min(max_pages, doc.page_count)

    for page_index in range(scan_limit):
        text = doc.load_page(page_index).get_text("text")
        lower = text.lower()
        marker_hit = any(marker in lower for marker in CONTENTS_MARKERS)
        page_entries = parse_toc_text(text)

        if marker_hit or len(page_entries) >= 3:
            raw_entries.extend(page_entries)

    if len(raw_entries) < 3:
        return []

    offset = estimate_page_offset(doc, raw_entries)
    entries: List[OutlineEntry] = []
    for level, title, printed_page in raw_entries:
        page_number = printed_page_to_int(printed_page)
        if page_number is None:
            continue
        pdf_page = max(1, min(doc.page_count, page_number + offset))
        bbox, font_size, bold, order = find_title_location(doc, pdf_page, title)
        entries.append(
            OutlineEntry(
                level=level,
                title=clean_title(title),
                page=pdf_page,
                confidence=0.78 if bbox else 0.68,
                source="toc",
                bbox=bbox,
                font_size=font_size,
                bold=bold,
                order=order,
            )
        )

    return entries


def parse_toc_text(text: str) -> List[Tuple[int, str, str]]:
    entries: List[Tuple[int, str, str]] = []
    for line in text.splitlines():
        line = collapse_spaces(line.strip().replace("…", "..."))
        if not line or len(line) < 6:
            continue
        match = TOC_LINE_RE.match(line)
        if not match:
            continue

        title = clean_title(match.group("title"))
        page = match.group("page")
        if is_noise_title(title):
            continue

        entries.append((level_from_title(title), title, page))

    return entries


def extract_from_headings(doc, min_confidence: float) -> List[OutlineEntry]:
    body_size = estimate_body_font_size(doc)
    raw: List[OutlineEntry] = []
    recovery_pool: List[OutlineEntry] = []
    seen: Dict[Tuple[str, int], bool] = {}

    for page_index in range(doc.page_count):
        page = doc.load_page(page_index)
        page_height = float(page.rect.height)
        page_width = float(page.rect.width)
        page_lines = list(iter_text_lines(page, page_index, merge_headings=False, body_size=body_size))
        recovery_pool.extend(extract_recovery_candidates(page_lines))
        for line in merge_heading_continuations(page_lines, page_width, body_size):
            line = split_inline_heading(line)
            title = canonicalize_heading_title(clean_title(line.text))
            if is_noise_title(title):
                continue
            if is_likely_paper_title(title, line, body_size, page_height):
                continue
            if is_likely_first_page_bio_or_note(title, line, page_height, page_width):
                continue

            confidence, reason = heading_confidence(title, line, body_size, page=page, page_lines=page_lines)
            if confidence < min_confidence:
                continue

            key = (normalize_text(title), line.page)
            if key in seen:
                continue
            seen[key] = True

            raw.append(
                OutlineEntry(
                    level=level_from_title(title),
                    title=title,
                    page=line.page + 1,
                    confidence=confidence,
                    source=reason,
                    bbox=line.bbox,
                    font_size=line.max_size,
                    bold=line.bold,
                    order=line.order,
                )
            )

    raw = recover_missing_sequence_entries(raw, recovery_pool)
    raw = suppress_lettered_entries_for_numeric_style(raw)
    raw = suppress_numbered_entries_for_lettered_style(raw)
    return infer_font_levels(raw, body_size)


def extract_recovery_candidates(lines: Sequence[TextLine]) -> List[OutlineEntry]:
    candidates: List[OutlineEntry] = []
    for line in lines:
        title = canonicalize_heading_title(clean_title(line.text))
        if not is_recoverable_lettered_title(title):
            continue
        if looks_like_person_name_sentence(title) or is_reference_line(title, line):
            continue
        candidates.append(
            OutlineEntry(
                level=2,
                title=title,
                page=line.page + 1,
                confidence=0.42,
                source="recovered",
                bbox=line.bbox,
                font_size=line.max_size,
                bold=line.bold,
                order=line.order,
            )
        )
    return candidates


def is_recoverable_lettered_title(title: str) -> bool:
    if not LETTERED_HEADING_RE.match(title) or is_roman_section_heading(title):
        return False
    content = re.sub(r"^[A-Z]\.\s+", "", clean_title(title))
    words = original_words(content)
    if not 1 <= len(words) <= 9:
        return False
    if looks_like_body_sentence(title):
        return False
    if re.search(r"\bet\s+al\b|\[\d+\]", content, re.IGNORECASE):
        return False
    return True


def recover_missing_sequence_entries(
    entries: Sequence[OutlineEntry],
    recovery_pool: Sequence[OutlineEntry],
) -> List[OutlineEntry]:
    existing_keys = {(normalize_text(entry.title), entry.page) for entry in entries}
    result = list(entries)
    cutoff = references_cutoff_key(entries)
    accepted_indices = {
        lettered_index(entry.title)
        for entry in entries
        if cutoff is None or entry_sort_key(entry) < cutoff
    }
    accepted_indices.discard(None)

    if not accepted_indices:
        return result

    pool_by_index: Dict[int, List[OutlineEntry]] = {}
    for candidate in recovery_pool:
        if cutoff is not None and entry_sort_key(candidate) >= cutoff:
            continue
        index = lettered_index(candidate.title)
        if index is None or index in accepted_indices:
            continue
        key = (normalize_text(candidate.title), candidate.page)
        if key in existing_keys:
            continue
        pool_by_index.setdefault(index, []).append(candidate)

    for missing in sorted(find_missing_letter_indices(accepted_indices)):
        candidates = pool_by_index.get(missing, [])
        if not candidates:
            continue
        recovered = min(candidates, key=lambda entry: (entry.page, entry.order or 0))
        result.append(recovered)
        accepted_indices.add(missing)
        existing_keys.add((normalize_text(recovered.title), recovered.page))

    result.sort(key=entry_sort_key)
    return result


def references_cutoff_key(entries: Sequence[OutlineEntry]) -> Optional[Tuple[int, int, float, int]]:
    keys = [
        entry_sort_key(entry)
        for entry in entries
        if normalize_text(entry.title) in {"references", "bibliography"}
    ]
    return min(keys) if keys else None


def find_missing_letter_indices(indices: set) -> List[int]:
    if not indices:
        return []
    lower = min(indices)
    upper = max(indices)
    return [index for index in range(lower, upper + 1) if index not in indices]


def entries_from_existing_toc(
    toc: Sequence[Sequence[object]],
    input_path: Path,
    output_path: Path,
    dry_run: bool,
) -> List[OutlineEntry]:
    entries: List[OutlineEntry] = []
    for item in toc:
        if len(item) < 3:
            continue
        level, title, page = item[:3]
        entries.append(
            OutlineEntry(
                level=max(1, min(6, int(level))),
                title=clean_title(str(title)),
                page=max(1, int(page)),
                confidence=1.0,
                source="existing",
            )
        )
    return entries


def iter_text_lines(
    page,
    page_index: int,
    merge_headings: bool = False,
    body_size: Optional[float] = None,
) -> Iterable[TextLine]:
    lines = list(_iter_raw_text_lines(page, page_index))
    lines = merge_same_visual_rows(lines, float(page.rect.width))
    lines = order_text_lines_for_reading(lines, float(page.rect.width))
    if merge_headings:
        lines = merge_heading_continuations(lines, float(page.rect.width), body_size or 10.0)
    yield from lines


def _iter_raw_text_lines(page, page_index: int) -> Iterable[TextLine]:
    data = page.get_text("dict")
    for block in data.get("blocks", []):
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            if not spans:
                continue
            text = text_from_spans(spans)
            if not text:
                continue

            sizes = [float(span.get("size", 0)) for span in spans if span.get("text", "").strip()]
            if not sizes:
                continue

            x0 = min(float(span.get("bbox", [0, 0, 0, 0])[0]) for span in spans)
            y0 = min(float(span.get("bbox", [0, 0, 0, 0])[1]) for span in spans)
            x1 = max(float(span.get("bbox", [0, 0, 0, 0])[2]) for span in spans)
            y1 = max(float(span.get("bbox", [0, 0, 0, 0])[3]) for span in spans)
            bold = any(
                "bold" in span.get("font", "").lower()
                or int(span.get("flags", 0)) & 16
                for span in spans
            )

            yield TextLine(
                text=text,
                page=page_index,
                bbox=(x0, y0, x1, y1),
                max_size=max(sizes),
                avg_size=sum(sizes) / len(sizes),
                bold=bold,
            )


def text_from_spans(spans: Sequence[dict]) -> str:
    pieces: List[str] = []
    previous_x1: Optional[float] = None
    previous_size = 10.0

    for span in spans:
        text = span.get("text", "")
        if not text.strip():
            continue
        bbox = span.get("bbox", [0, 0, 0, 0])
        x0 = float(bbox[0])
        size = float(span.get("size", previous_size) or previous_size)
        if previous_x1 is not None and x0 - previous_x1 > max(1.5, previous_size * 0.18):
            pieces.append(" ")
        pieces.append(text)
        previous_x1 = float(bbox[2])
        previous_size = size

    return collapse_spaces("".join(pieces))


def merge_same_visual_rows(lines: Sequence[TextLine], page_width: float) -> List[TextLine]:
    if not lines:
        return []

    sorted_lines = sorted(lines, key=lambda line: (line.page, line.y0, line.x0))
    merged: List[TextLine] = []

    for line in sorted_lines:
        if not merged:
            merged.append(line)
            continue

        previous = merged[-1]
        previous_column = column_for_line(previous, page_width)
        line_column = column_for_line(line, page_width)
        same_row = (
            previous.page == line.page
            and abs(previous.y0 - line.y0) <= 2.2
            and line.x0 >= previous.x1 - 1.0
            and line.x0 - previous.x1 <= 24.0
            and abs(previous.max_size - line.max_size) <= 1.0
            and previous_column == line_column
        )
        if not same_row:
            merged.append(line)
            continue

        merged[-1] = combine_text_lines(previous, line, same_row=True)

    return merged


def order_text_lines_for_reading(lines: Sequence[TextLine], page_width: float) -> List[TextLine]:
    if not lines:
        return []

    midpoint = page_width / 2.0

    def with_column(line: TextLine) -> TextLine:
        column = column_for_line(line, page_width)
        return replace_text_line(line, column=column)

    columned = [with_column(line) for line in lines]

    def sort_key(line: TextLine) -> Tuple[int, float, float]:
        if line.column == -1:
            return (0, line.y0, line.x0)
        if line.y0 < 170 and line.x0 < midpoint < line.x1:
            return (0, line.y0, line.x0)
        return (line.column + 1, line.y0, line.x0)

    ordered = sorted(columned, key=sort_key)
    return [replace_text_line(line, order=index) for index, line in enumerate(ordered)]


def merge_heading_continuations(
    lines: Sequence[TextLine],
    page_width: float,
    body_size: float,
) -> List[TextLine]:
    merged: List[TextLine] = []
    index = 0

    while index < len(lines):
        current = lines[index]
        title = clean_title(current.text)
        if not can_start_multiline_heading(title, current, page_width, body_size):
            merged.append(current)
            index += 1
            continue

        combined = current
        last_line = current
        index += 1
        while index < len(lines) and can_continue_heading(combined, last_line, lines[index], page_width, body_size):
            combined = combine_text_lines(combined, lines[index], same_row=False)
            last_line = lines[index]
            index += 1
        merged.append(combined)

    return [replace_text_line(line, order=index) for index, line in enumerate(merged)]


def can_start_multiline_heading(title: str, line: TextLine, page_width: float, body_size: float) -> bool:
    if is_noise_title(title):
        return False
    starts_like_heading = (
        NUMBERED_HEADING_RE.match(title)
        or is_roman_section_heading(title)
        or (LETTERED_HEADING_RE.match(title) and not is_roman_section_heading(title))
        or is_common_section_heading(title)
        or line.bold
        or line.max_size >= body_size + 0.8
    )
    if not starts_like_heading:
        return False
    if is_centered_heading_line(line, page_width) and line.max_size >= body_size - 0.2:
        return True
    return is_visually_wrapped_line(line, page_width) or title.endswith(("-", ":"))


def can_continue_heading(
    current: TextLine,
    last_line: TextLine,
    candidate: TextLine,
    page_width: float,
    body_size: float,
) -> bool:
    if current.page != candidate.page or current.column != candidate.column:
        return False
    if candidate.order != last_line.order + 1:
        return False
    if starts_new_heading(candidate.text) and not is_short_heading_continuation_text(candidate.text):
        return False
    if is_probable_math_line(candidate.text):
        return False
    if candidate.y0 - last_line.y1 > max(18.0, last_line.max_size * 1.7):
        return False
    both_centered = is_centered_heading_line(last_line, page_width) and is_centered_heading_line(candidate, page_width)
    if not both_centered and abs(candidate.x0 - last_line.x0) > 34.0:
        return False
    if candidate.max_size < body_size - 0.4:
        return False
    if candidate.max_size > current.max_size + 1.5:
        return False
    text = clean_title(candidate.text)
    if is_noise_title(text) or len(text) > 120:
        return False
    centered_section_continuation = both_centered and (
        NUMBERED_HEADING_RE.match(current.text)
        or is_roman_section_heading(current.text)
        or is_common_section_heading(current.text)
    )
    if (
        not centered_section_continuation
        and not is_visually_wrapped_line(last_line, page_width)
        and not last_line.text.endswith(("-", ":"))
    ):
        return False
    if is_short_all_caps_lettered_heading(current.text):
        return False
    if looks_like_author_affiliation_sentence(text):
        return False
    if LETTERED_HEADING_RE.match(current.text) and looks_like_prose_continuation(text):
        return looks_like_title_continuation(text)
    if text.endswith((".", ";")):
        return False
    if looks_like_body_sentence(text):
        return False
    if CAPTION_RE.match(text):
        return False
    return True


def is_short_heading_continuation_text(text: str) -> bool:
    title = clean_title(text)
    words = normalize_text(title).split()
    if not 1 <= len(words) <= 4:
        return False
    if title.endswith((".", ";", ",")):
        return False
    return bool(re.match(r"^[A-Z][A-Za-z0-9\- ]+$", title))


def is_short_all_caps_lettered_heading(text: str) -> bool:
    title = clean_title(text)
    if not LETTERED_HEADING_RE.match(title):
        return False
    content = re.sub(r"^[A-Z]\.\s+", "", title)
    words = original_words(content)
    if not 1 <= len(words) <= 4:
        return False
    letters = [char for char in content if char.isalpha()]
    return bool(letters) and sum(1 for char in letters if char.isupper()) / len(letters) >= 0.75


def looks_like_prose_continuation(text: str) -> bool:
    words = original_words(text)
    if len(words) >= 6:
        return True
    if words and words[0][:1].isupper() and any(word[:1].islower() for word in words[1:]):
        return True
    return False


def looks_like_title_continuation(text: str) -> bool:
    words = original_words(text)
    if not words:
        return False
    lowered = {word.lower() for word in words}
    prose_cues = {
        "objective",
        "developed",
        "proposed",
        "presented",
        "introduced",
        "advantage",
        "disadvantage",
        "prototype",
        "people",
        "vision",
        "after",
        "using",
        "from",
    }
    if lowered & prose_cues:
        return False
    small_words = {"and", "or", "of", "the", "a", "an", "in", "on", "for", "to", "via", "with"}
    content_words = [word for word in words if word.lower() not in small_words]
    if not content_words:
        return False
    title_like = sum(1 for word in content_words if word[:1].isupper() or word.isupper())
    return title_like / len(content_words) >= 0.75


def looks_like_author_affiliation_sentence(text: str) -> bool:
    stripped = clean_title(text)
    if re.match(r"^[A-Z][a-z]+(?:\s+and\s+[A-Z][a-z]+)+\s+from\b", stripped):
        return True
    if re.match(r"^[A-Z][a-z]+\s+from\b", stripped):
        return True
    if re.search(r"\bfrom\s+[A-Z][A-Za-z\-]*(?:\s+[A-Z][A-Za-z\-]*){1,5}\s+(University|Institute|College)\b", stripped):
        return True
    return False


def starts_new_heading(text: str) -> bool:
    title = clean_title(text)
    return bool(
        NUMBERED_HEADING_RE.match(title)
        or is_roman_section_heading(title)
        or (LETTERED_HEADING_RE.match(title) and not is_roman_section_heading(title))
        or is_common_section_heading(title)
    )


def is_near_column_end(line: TextLine, page_width: float) -> bool:
    midpoint = page_width / 2.0
    if line.column == 0:
        return line.x1 >= midpoint - 18.0
    if line.column == 1:
        return line.x1 >= page_width - 72.0
    return line.x1 >= page_width - 72.0


def is_visually_wrapped_line(line: TextLine, page_width: float) -> bool:
    left, right = column_bounds(line, page_width)
    column_width = max(1.0, right - left)
    line_width = max(0.0, line.x1 - line.x0)
    trailing_space = max(0.0, right - line.x1)
    fill_ratio = line_width / column_width
    return fill_ratio >= 0.84 and trailing_space <= max(24.0, column_width * 0.10)


def column_bounds(line: TextLine, page_width: float) -> Tuple[float, float]:
    midpoint = page_width / 2.0
    if line.column == 0:
        return 36.0, midpoint - 8.0
    if line.column == 1:
        return midpoint + 8.0, page_width - 36.0
    return 36.0, page_width - 36.0


def is_centered_heading_line(line: TextLine, page_width: float) -> bool:
    line_center = (line.x0 + line.x1) / 2.0
    page_center = page_width / 2.0
    return abs(line_center - page_center) <= page_width * 0.16


def column_for_line(line: TextLine, page_width: float) -> int:
    midpoint = page_width / 2.0
    width = line.x1 - line.x0
    if width >= page_width * 0.68 or (line.x0 < midpoint - 35 and line.x1 > midpoint + 35):
        return -1
    center = (line.x0 + line.x1) / 2.0
    return 0 if center < midpoint else 1


def combine_text_lines(first: TextLine, second: TextLine, same_row: bool) -> TextLine:
    separator = " " if same_row or not first.text.endswith("-") else ""
    text = clean_title(first.text.rstrip("-") + separator + second.text)
    bbox = union_rect(first.bbox, second.bbox)
    first_weight = max(1, len(first.text))
    second_weight = max(1, len(second.text))
    total = first_weight + second_weight
    avg_size = ((first.avg_size * first_weight) + (second.avg_size * second_weight)) / total
    return TextLine(
        text=text,
        page=first.page,
        bbox=bbox,
        max_size=max(first.max_size, second.max_size),
        avg_size=avg_size,
        bold=first.bold or second.bold,
        order=first.order,
        column=first.column,
    )


def split_inline_heading(line: TextLine) -> TextLine:
    text = clean_title(line.text)
    match = INLINE_ROMAN_HEADING_RE.match(text)
    if not match:
        return line

    heading = clean_title(match.group(1))
    if heading == text:
        return line

    ratio = len(heading) / max(1, len(text))
    x1 = line.x0 + (line.x1 - line.x0) * min(0.98, max(0.25, ratio))
    return TextLine(
        text=heading,
        page=line.page,
        bbox=(line.x0, line.y0, x1, line.y1),
        max_size=line.max_size,
        avg_size=line.avg_size,
        bold=line.bold,
        order=line.order,
        column=line.column,
    )


def replace_text_line(
    line: TextLine,
    order: Optional[int] = None,
    column: Optional[int] = None,
) -> TextLine:
    return TextLine(
        text=line.text,
        page=line.page,
        bbox=line.bbox,
        max_size=line.max_size,
        avg_size=line.avg_size,
        bold=line.bold,
        order=line.order if order is None else order,
        column=line.column if column is None else column,
    )


def union_rect(first: RectTuple, second: RectTuple) -> RectTuple:
    return (
        min(first[0], second[0]),
        min(first[1], second[1]),
        max(first[2], second[2]),
        max(first[3], second[3]),
    )


def estimate_body_font_size(doc) -> float:
    sizes: List[float] = []
    for page_index in range(min(doc.page_count, 10)):
        page = doc.load_page(page_index)
        for line in iter_text_lines(page, page_index):
            if len(line.text) >= 35 and not CAPTION_RE.match(line.text):
                sizes.append(round(line.avg_size, 1))
    if not sizes:
        return 10.0
    return statistics.median(sizes)


def heading_confidence(
    title: str,
    line: TextLine,
    body_size: float,
    page=None,
    page_lines: Optional[Sequence[TextLine]] = None,
) -> Tuple[float, str]:
    title = canonicalize_heading_title(title)
    if is_probable_math_line(title) or is_reference_line(title, line):
        return 0.0, "noise"
    if is_encoded_text_noise(title):
        return 0.0, "noise"
    if page is not None and is_probable_table_cell(title, line, page, body_size, page_lines=page_lines):
        return 0.0, "table"
    if page is not None and is_probable_figure_text(title, line, page, body_size, page_lines=page_lines):
        return 0.0, "figure"
    if looks_like_person_name_sentence(title):
        return 0.0, "body"
    if looks_like_author_list_heading(title):
        return 0.0, "body"

    confidence = 0.0
    reason = "heading"

    numbered = NUMBERED_HEADING_RE.match(title)
    roman = is_roman_section_heading(title, line=line, body_size=body_size)
    lettered = LETTERED_HEADING_RE.match(title) and not roman
    common = is_common_section_heading(title)
    short_line = 3 <= len(title) <= 95
    no_sentence_end = not title.endswith((".", ",", ";", ":"))
    typography = line.max_size >= body_size + 0.8
    strong_typography = line.max_size >= body_size + 1.7
    bold_heading = line.bold and short_line and no_sentence_end

    if common:
        if not has_section_visual_signal(title, line, body_size):
            return 0.0, "table"
        confidence += 0.58
        reason = "section"
    if numbered or roman:
        if numbered and not roman and is_top_arabic_heading(title) and line.max_size < body_size - 0.6:
            return 0.0, "noise"
        if numbered and not roman and numbered.group(2)[:1].islower():
            return 0.0, "noise"
        if numbered and not roman and is_unlikely_decimal_heading(numbered.group(1), numbered.group(2)):
            return 0.0, "noise"
        confidence += 0.50
        reason = "numbered"
    if lettered:
        if looks_like_body_sentence(title):
            return 0.0, "body"
        confidence += 0.50
        reason = "lettered"
    if typography:
        confidence += 0.22
        reason = reason if reason != "heading" else "font"
    if strong_typography:
        confidence += 0.16
    if bold_heading:
        confidence += 0.24
        reason = reason if reason != "heading" else "bold"
    if title.isupper() and 4 <= len(title) <= 60:
        confidence += 0.08
    if line.y0 < 120 and not numbered and not roman and not lettered and not common:
        confidence -= 0.10
    if len(title) > 110 and not numbered:
        confidence -= 0.20
    if numbered and not roman and has_math_signal(title):
        confidence -= 0.55

    return min(max(confidence, 0.0), 0.97), reason


def infer_font_levels(entries: Sequence[OutlineEntry], body_size: float) -> List[OutlineEntry]:
    if not entries:
        return []

    font_sizes = sorted(
        {
            round(entry.font_size or body_size, 1)
            for entry in entries
            if (entry.font_size or 0) >= body_size + 0.4
        },
        reverse=True,
    )
    font_size_to_level: Dict[float, int] = {}
    for index, size in enumerate(font_sizes[:4]):
        font_size_to_level[size] = index + 1

    inferred: List[OutlineEntry] = []
    seen_lettered_indices = set()
    for entry in entries:
        numbered_level = level_from_title(entry.title)
        level = numbered_level
        source = entry.source
        if is_lettered_subsection_by_sequence(entry.title, seen_lettered_indices):
            level = 2
            source = "lettered"
        elif LETTERED_HEADING_RE.match(entry.title) and not is_roman_section_heading(entry.title):
            level = 2
        elif numbered_level == 1 and not NUMBERED_HEADING_RE.match(entry.title):
            size_key = round(entry.font_size or body_size, 1)
            if is_common_section_heading(entry.title):
                level = 1
            elif size_key in font_size_to_level:
                level = max(1, min(4, font_size_to_level[size_key]))
            elif entry.bold and (entry.font_size or body_size) >= body_size - 0.2:
                level = 2

        inferred.append(
            OutlineEntry(
                level=level,
                title=entry.title,
                page=entry.page,
                confidence=entry.confidence,
                source=source,
                bbox=entry.bbox,
                font_size=entry.font_size,
                bold=entry.bold,
                order=entry.order,
            )
        )
        letter_index = lettered_index(entry.title)
        if letter_index is not None and level == 2:
            seen_lettered_indices.add(letter_index)

    return inferred


def suppress_lettered_entries_for_numeric_style(entries: Sequence[OutlineEntry]) -> List[OutlineEntry]:
    decimal_count = sum(1 for entry in entries if is_decimal_numbered_heading(entry.title))
    top_arabic_count = sum(1 for entry in entries if is_top_arabic_heading(entry.title))
    roman_count = sum(1 for entry in entries if is_roman_section_heading(entry.title))

    if decimal_count < 2 or top_arabic_count < 2 or roman_count:
        return list(entries)

    return [
        entry
        for entry in entries
        if not (LETTERED_HEADING_RE.match(entry.title) and not is_roman_section_heading(entry.title))
    ]


def suppress_numbered_entries_for_lettered_style(entries: Sequence[OutlineEntry]) -> List[OutlineEntry]:
    letter_indices = [
        index
        for entry in entries
        if (index := lettered_index(entry.title)) is not None
        and not is_roman_section_heading(entry.title)
    ]
    if len(letter_indices) < 3:
        return list(entries)

    decimal_count = sum(1 for entry in entries if is_decimal_numbered_heading(entry.title))
    top_arabic_count = sum(1 for entry in entries if is_top_arabic_heading(entry.title))
    roman_count = sum(1 for entry in entries if is_roman_section_heading(entry.title))
    common_count = sum(1 for entry in entries if is_common_section_heading(entry.title))

    numeric_style = (decimal_count >= 2 and top_arabic_count >= 2) or (
        top_arabic_count >= 3 and roman_count == 0 and decimal_count == 0
    )
    if numeric_style:
        return list(entries)

    ordered = sorted(set(letter_indices))
    coherent_lettered_style = max(ordered) - min(ordered) <= len(ordered) + 2
    if not coherent_lettered_style:
        return list(entries)
    if roman_count == 0 and common_count == 0 and top_arabic_count >= 3:
        return list(entries)

    return [
        entry
        for entry in entries
        if not is_non_roman_numbered_heading(entry.title)
    ]


def is_non_roman_numbered_heading(title: str) -> bool:
    title = clean_title(title)
    return bool(NUMBERED_HEADING_RE.match(title) and not is_roman_section_heading(title))


def is_decimal_numbered_heading(title: str) -> bool:
    match = NUMBERED_HEADING_RE.match(clean_title(title))
    return bool(match and "." in match.group(1).strip().rstrip("."))


def is_top_arabic_heading(title: str) -> bool:
    match = NUMBERED_HEADING_RE.match(clean_title(title))
    if not match:
        return False
    prefix = match.group(1).strip().rstrip(".")
    return prefix.isdigit()


def is_lettered_subsection_by_sequence(title: str, seen_indices: set) -> bool:
    index = lettered_index(title)
    if index is None:
        return False
    if index == 1:
        return True
    return any(previous in seen_indices for previous in range(max(1, index - 2), index))


def lettered_index(title: str) -> Optional[int]:
    match = re.match(r"^\s*([A-Z])\.\s+", clean_title(title))
    if not match:
        return None
    return ord(match.group(1)) - ord("A") + 1


def is_likely_paper_title(title: str, line: TextLine, body_size: float, page_height: float) -> bool:
    if line.page != 0:
        return False
    if (
        NUMBERED_HEADING_RE.match(title)
        or is_roman_section_heading(title)
        or LETTERED_HEADING_RE.match(title)
        or is_common_section_heading(title)
    ):
        return False
    if line.y0 > page_height * 0.42:
        return False
    if line.max_size < body_size + 1.6:
        return False
    words = normalize_text(title).split()
    if len(words) < 3:
        return False
    return True


def is_likely_first_page_bio_or_note(title: str, line: TextLine, page_height: float, page_width: float) -> bool:
    if line.page != 0:
        return False
    if line.y0 < page_height * 0.56:
        return False
    if line.x0 > page_width * 0.58:
        return False
    if starts_new_heading(title) or is_common_section_heading(title):
        return False

    lowered = title.lower()
    bio_cues = {
        "received",
        "degree",
        "currently",
        "student member",
        "member, ieee",
        "senior member",
        "corresponding author",
        "author",
        "supported by",
        "support provided",
        "funded by",
        "foundation",
        "grant",
        "university",
        "college",
        "institute",
        "department",
    }
    if "@" in title or any(cue in lowered for cue in bio_cues):
        return True
    if re.match(r"^[A-Z][A-Za-z.\- ]{2,35}\s+(received|is|was)\b", title):
        return True
    return False


def is_common_section_heading(title: str) -> bool:
    stripped = clean_title(title)
    if not COMMON_SECTION_RE.match(stripped):
        return False
    first_alpha = next((char for char in stripped if char.isalpha()), "")
    return bool(first_alpha and first_alpha.isupper())


def has_section_visual_signal(title: str, line: TextLine, body_size: float) -> bool:
    stripped = clean_title(title)
    if stripped.isupper():
        return True
    if line.bold:
        return True
    if line.max_size >= body_size + 0.6:
        return True
    if is_numbered_or_marked_section_context(stripped):
        return True
    return False


def is_numbered_or_marked_section_context(title: str) -> bool:
    return bool(
        NUMBERED_HEADING_RE.match(title)
        or is_roman_section_heading(title)
        or (LETTERED_HEADING_RE.match(title) and not is_roman_section_heading(title))
    )


def is_probable_table_cell(
    title: str,
    line: TextLine,
    page,
    body_size: float,
    page_lines: Optional[Sequence[TextLine]] = None,
) -> bool:
    stripped = clean_title(title)
    if not is_common_section_heading(stripped):
        return False
    if has_section_visual_signal(stripped, line, body_size):
        return False
    if line.max_size <= body_size - 0.4:
        return True

    same_band = 0
    different_columns = 0
    candidates = page_lines if page_lines is not None else list(iter_text_lines(page, line.page, merge_headings=False))
    for other in candidates:
        if other is line:
            continue
        if abs(other.y0 - line.y0) > max(4.0, line.max_size * 0.45):
            continue
        if normalize_text(other.text) == normalize_text(stripped):
            continue
        same_band += 1
        if abs(other.x0 - line.x0) > 35.0:
            different_columns += 1

    if same_band >= 2 and different_columns >= 2:
        return True
    return False


def is_probable_figure_text(
    title: str,
    line: TextLine,
    page,
    body_size: float,
    page_lines: Optional[Sequence[TextLine]] = None,
) -> bool:
    stripped = clean_title(title)
    if starts_new_heading(stripped):
        return False
    if not (line.bold or line.max_size >= body_size + 0.5 or stripped.isupper()):
        return False

    words = original_words(stripped)
    if not 1 <= len(words) <= 8:
        return False

    candidates = page_lines if page_lines is not None else list(iter_text_lines(page, line.page, merge_headings=False))
    for other in candidates:
        caption = clean_title(other.text)
        if not CAPTION_RE.match(caption):
            continue
        if other.y0 >= line.y1:
            vertical_gap = other.y0 - line.y1
            if 0 <= vertical_gap <= 260 and horizontally_related(line, other):
                return True
        elif line.y0 >= other.y1:
            vertical_gap = line.y0 - other.y1
            if 0 <= vertical_gap <= 90 and horizontally_related(line, other):
                return True

    return False


def horizontally_related(first: TextLine, second: TextLine) -> bool:
    overlap = max(0.0, min(first.x1, second.x1) - max(first.x0, second.x0))
    first_width = max(1.0, first.x1 - first.x0)
    second_width = max(1.0, second.x1 - second.x0)
    if overlap >= min(first_width, second_width) * 0.35:
        return True
    first_center = (first.x0 + first.x1) / 2.0
    second_center = (second.x0 + second.x1) / 2.0
    return abs(first_center - second_center) <= max(first_width, second_width) * 0.55


def is_unlikely_decimal_heading(prefix: str, rest: str) -> bool:
    prefix = prefix.strip().rstrip(".")
    parts = prefix.split(".")
    try:
        first = int(parts[0])
    except ValueError:
        return False
    words = normalize_text(rest).split()
    if first > 20:
        return True
    if is_numbered_measurement_label(rest):
        return True
    if re.match(r"^\s*\(", rest) or re.search(r"\bet\s+al\b|\b\d{4}\b", rest, re.IGNORECASE):
        return True
    if len(parts) <= 1:
        body_openers = {
            "we",
            "can",
            "how",
            "what",
            "do",
            "does",
            "this",
            "that",
            "these",
            "those",
            "it",
            "there",
            "where",
            "when",
            "if",
            "let",
            "given",
            "based",
            "assume",
        }
        return len(words) >= 2 and words[0] in body_openers
    if first > 12:
        return True
    if len(words) >= 8:
        return True
    return False


def is_numbered_measurement_label(rest: str) -> bool:
    words = normalize_text(rest).split()
    if not words:
        return False
    units = {
        "b",
        "kb",
        "mb",
        "gb",
        "tb",
        "hz",
        "khz",
        "mhz",
        "ghz",
        "ms",
        "s",
        "sec",
        "min",
        "fps",
        "cpu",
        "cpus",
        "gpu",
        "gpus",
    }
    return len(words) <= 3 and words[0] in units


def is_probable_math_line(title: str) -> bool:
    text = title.strip()
    if not text:
        return True
    normalized = normalize_text(text)
    words = normalized.split()
    letters = [char for char in text if char.isalpha()]
    strong_operators = sum(1 for char in text if char in "=+−-*/∂⊤∗|¨˙")
    bracket_operators = sum(1 for char in text if char in "()[]{}")
    non_ascii_math = sum(1 for char in text if ord(char) > 127 and not char.isalpha())
    if strong_operators >= 2 and len(words) <= 6:
        return True
    if non_ascii_math >= 2 and len(words) <= 6:
        return True
    if letters and len(letters) <= 4 and strong_operators >= 1:
        return True
    if re.search(r"[=∂⊤∗¨˙]", text) and not re.search(r"[a-zA-Z]{4,}", text):
        return True
    if bracket_operators >= 4 and strong_operators >= 1 and len(words) <= 8:
        return True
    return False


def has_math_signal(title: str) -> bool:
    return bool(re.search(r"[=∂⊤∗¨˙|]|[α-ωΑ-Ωφητ]", title))


def looks_like_body_sentence(title: str) -> bool:
    words = original_words(title)
    if not words:
        return False

    content = re.sub(r"^[A-Z]\.\s+", "", clean_title(title))
    content_words = original_words(content)
    lowered = {word.lower() for word in content_words}
    sentence_cues = {
        "and",
        "or",
        "the",
        "a",
        "an",
        "of",
        "in",
        "to",
        "for",
        "this",
        "that",
        "these",
        "those",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "from",
        "with",
        "using",
        "developed",
        "proposed",
        "presented",
        "introduced",
        "via",
    }
    lowercase_starts = sum(1 for word in content_words if word[:1].islower())

    if LETTERED_HEADING_RE.match(title):
        return len(content_words) >= 9 and bool(lowered & sentence_cues) and lowercase_starts >= 3

    if len(words) >= 10 and not starts_new_heading(title):
        return True
    if len(words) >= 6 and lowercase_starts >= 3 and bool(lowered & sentence_cues):
        return True
    return False


def original_words(title: str) -> List[str]:
    return re.findall(r"[A-Za-z][A-Za-z0-9'\-]*", clean_title(title))


def looks_like_person_name_sentence(title: str) -> bool:
    stripped = clean_title(title)
    words = normalize_text(stripped).split()
    if len(words) < 6:
        return False
    if re.match(r"^[A-Z]\.\s*[A-Z][a-z]+(?:\s+and\s+[A-Z]\.\s*[A-Z][a-z]+|\s*,)", stripped):
        return True
    if re.match(r"^[A-Z]\.\s*(?:[A-Z]\.\s*)+[A-Z][a-z]+", stripped):
        return True
    if re.match(r"^[A-Z]\.\s*[A-Z][a-z]+\s+from\b", stripped):
        return True
    return False


def looks_like_author_list_heading(title: str) -> bool:
    stripped = clean_title(title)
    if re.match(r"^[A-Z]\.\s+(?:[A-Z]\.\s+)+[A-Z][A-Za-z'’.\-]+(?:\s+et\s+al\.?\*?)?$", stripped):
        return True
    if re.match(r"^[A-Z]\.\s+[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’.\-]+,\s+[A-Z]\.", stripped):
        return True
    return False


def is_reference_line(title: str, line: TextLine) -> bool:
    if line.max_size >= 9.0:
        return False
    if LETTERED_HEADING_RE.match(title) and re.search(r"[“\"].{20,}", title):
        return True
    if re.match(r"^[A-Z]\.\s+[A-Z][a-z]+,\s", title):
        return True
    return False


def estimate_page_offset(doc, raw_entries: Sequence[Tuple[int, str, str]]) -> int:
    arabic_entries = [
        (title, printed_page_to_int(page_text))
        for _, title, page_text in raw_entries[:15]
        if printed_page_to_int(page_text) is not None
    ]
    if not arabic_entries:
        return 0

    best_offset = 0
    best_score = -1
    for offset in range(-20, 31):
        score = 0
        for title, printed_page in arabic_entries:
            assert printed_page is not None
            page_index = printed_page + offset - 1
            if page_index < 0 or page_index >= doc.page_count:
                continue
            text = normalize_text(doc.load_page(page_index).get_text("text"))
            needle = significant_heading_text(title)
            if needle and needle in text:
                score += 3
            elif any(word in text for word in needle.split()[:3] if len(word) > 4):
                score += 1
        if score > best_score:
            best_score = score
            best_offset = offset

    return best_offset if best_score > 0 else 0


def normalize_entries(entries: Sequence[OutlineEntry], page_count: int) -> List[OutlineEntry]:
    normalized: List[OutlineEntry] = []
    seen = set()
    previous_page = 0
    previous_level = 1

    for entry in prune_front_matter(sorted(entries, key=entry_sort_key)):
        title = clean_title(entry.title)
        if is_noise_title(title):
            continue
        page = max(1, min(page_count, int(entry.page)))
        key = (normalize_text(title), page)
        if key in seen:
            continue
        seen.add(key)

        level = max(1, min(6, int(entry.level)))
        if normalized and page >= previous_page and level > previous_level + 1:
            level = previous_level + 1

        normalized.append(
            OutlineEntry(
                level=level,
                title=title,
                page=page,
                confidence=entry.confidence,
                source=entry.source,
                bbox=entry.bbox,
                font_size=entry.font_size,
                bold=entry.bold,
                order=entry.order,
            )
        )
        previous_page = page
        previous_level = level

    return repair_outline_hierarchy(truncate_after_references(normalized))


def truncate_after_references(entries: Sequence[OutlineEntry]) -> List[OutlineEntry]:
    kept: List[OutlineEntry] = []
    for entry in entries:
        kept.append(entry)
        if normalize_text(entry.title) in {"references", "bibliography"}:
            break
    return kept


def prune_front_matter(entries: Sequence[OutlineEntry]) -> List[OutlineEntry]:
    entries = drop_font_only_entries_when_structured(entries)
    first_structural_index: Optional[int] = None
    for index, entry in enumerate(entries):
        if is_structural_heading(entry):
            first_structural_index = index
            break

    if first_structural_index is None:
        return list(entries)

    pruned: List[OutlineEntry] = []
    for index, entry in enumerate(entries):
        if index < first_structural_index and is_front_matter_entry(entry):
            continue
        pruned.append(entry)
    return pruned


def drop_font_only_entries_when_structured(entries: Sequence[OutlineEntry]) -> List[OutlineEntry]:
    structural_count = sum(1 for entry in entries if is_structural_heading(entry))
    if structural_count < 3:
        return list(entries)
    return [entry for entry in entries if entry.source not in {"font", "bold"}]


def is_structural_heading(entry: OutlineEntry) -> bool:
    title = clean_title(entry.title)
    if is_date_title(title):
        return False
    return bool(
        entry.source in {"toc", "numbered", "lettered", "section"}
        or NUMBERED_HEADING_RE.match(title)
        or is_roman_section_heading(title)
        or (LETTERED_HEADING_RE.match(title) and not is_roman_section_heading(title))
        or is_common_section_heading(title)
    )


def is_front_matter_entry(entry: OutlineEntry) -> bool:
    title = clean_title(entry.title)
    lowered = title.lower()
    if entry.source == "font":
        return True
    if re.search(r"\b(inc\.?|university|college|institute|beijing|china|support provided)\b", lowered):
        return True
    if is_date_title(title):
        return True
    return False


def is_date_title(title: str) -> bool:
    return bool(re.fullmatch(r"\d{1,2}\s+[A-Za-z]+\s+\d{4}", clean_title(title)))


def repair_outline_hierarchy(entries: Sequence[OutlineEntry]) -> List[OutlineEntry]:
    repaired: List[OutlineEntry] = []
    previous_level = 1

    for index, entry in enumerate(entries):
        level = max(1, min(6, int(entry.level)))
        if index == 0:
            level = 1
        elif level > previous_level + 1:
            level = previous_level + 1

        repaired.append(
            OutlineEntry(
                level=level,
                title=entry.title,
                page=entry.page,
                confidence=entry.confidence,
                source=entry.source,
                bbox=entry.bbox,
                font_size=entry.font_size,
                bold=entry.bold,
                order=entry.order,
            )
        )
        previous_level = level

    return repaired


def write_debug_pdf(doc, output_path: Path, entries: Sequence[OutlineEntry]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    debug_doc = fitz.open()
    debug_doc.insert_pdf(doc)

    colors = {
        1: (0.90, 0.10, 0.10),
        2: (0.10, 0.40, 0.95),
        3: (0.10, 0.60, 0.25),
        4: (0.55, 0.25, 0.85),
    }

    for index, entry in enumerate(entries, start=1):
        if not entry.bbox:
            continue
        page = debug_doc.load_page(entry.page - 1)
        rect = fitz.Rect(entry.bbox)
        color = colors.get(entry.level, (0.20, 0.20, 0.20))
        page.draw_rect(rect + (-2, -2, 2, 2), color=color, width=1.4)
        label = f"#{index} L{entry.level} {entry.confidence:.2f}"
        label_point = fitz.Point(rect.x0, max(10, rect.y0 - 5))
        page.insert_text(label_point, label, fontsize=7, color=color)

    debug_doc.save(str(output_path), garbage=4, deflate=True)
    debug_doc.close()


def entry_sort_key(entry: OutlineEntry) -> Tuple[int, int, float, int]:
    fallback_y = entry.bbox[1] if entry.bbox else 0.0
    order = entry.order if entry.order is not None else 100000
    return (entry.page, order, fallback_y, entry.level)


def find_title_location(
    doc,
    pdf_page: int,
    title: str,
) -> Tuple[Optional[RectTuple], Optional[float], bool, Optional[int]]:
    if pdf_page < 1 or pdf_page > doc.page_count:
        return None, None, False, None

    page = doc.load_page(pdf_page - 1)
    target = normalize_text(significant_heading_text(title))
    if not target:
        return None, None, False, None

    for line in iter_text_lines(page, pdf_page - 1, merge_headings=True):
        line_text = normalize_text(line.text)
        if target in line_text or line_text in target:
            return line.bbox, line.max_size, line.bold, line.order

    return None, None, False, None


def printed_page_to_int(page_text: str) -> Optional[int]:
    page_text = page_text.strip()
    if page_text.isdigit():
        return int(page_text)
    return roman_to_int(page_text)


def roman_to_int(value: str) -> Optional[int]:
    numerals = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}
    value = value.lower()
    if not value or any(char not in numerals for char in value):
        return None
    total = 0
    previous = 0
    for char in reversed(value):
        current = numerals[char]
        if current < previous:
            total -= current
        else:
            total += current
            previous = current
    return total


def level_from_title(title: str) -> int:
    match = NUMBERED_HEADING_RE.match(title)
    if match:
        prefix = match.group(1).strip().rstrip(".")
        if re.match(r"^\d+(?:\.\d+)+$", prefix):
            return min(6, prefix.count(".") + 1)
        return 1
    if is_roman_section_heading(title):
        return 1
    if LETTERED_HEADING_RE.match(title):
        return 2
    return 1


def is_roman_section_heading(
    title: str,
    line: Optional[TextLine] = None,
    body_size: Optional[float] = None,
) -> bool:
    match = ROMAN_HEADING_RE.match(title)
    if not match:
        return False
    body = match.group(2).strip()
    letters = [char for char in body if char.isalpha()]
    if not letters:
        return False
    uppercase_ratio = sum(1 for char in letters if char.isupper()) / len(letters)
    if uppercase_ratio >= 0.75:
        return True
    if match.group(1) not in {"I", "V", "X"}:
        return False
    if line is None or body_size is None:
        return False
    return line.bold or line.max_size >= body_size + 0.6


def clean_title(title: str) -> str:
    title = re.sub(r"\s+", " ", title).strip()
    title = re.sub(r"^[.\-\s]+", "", title)
    title = re.sub(r"\s*[.\-]+\s*$", "", title)
    return title[:180]


def canonicalize_heading_title(title: str) -> str:
    title = clean_title(title)
    match = re.match(r"^(?:IL|I1|L1|Ⅱ)\s+([A-Z][A-Z0-9,()\- ]{8,})$", title)
    if match:
        return f"II. {clean_title(match.group(1))}"
    return title


def is_encoded_text_noise(title: str) -> bool:
    if starts_new_heading(title) or is_common_section_heading(title):
        return False
    if re.search(r"[\x00-\x1f\x7f]|[²¶]", title):
        return True
    words = original_words(title)
    if len(words) < 4:
        return False
    encoded_words = 0
    for word in words:
        if len(word) < 5:
            continue
        vowels = sum(1 for char in word.lower() if char in "aeiou")
        if vowels <= 1 and re.search(r"[A-Z]", word) and re.search(r"[a-z]", word):
            encoded_words += 1
    return encoded_words >= 3


def collapse_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def normalize_text(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def significant_heading_text(title: str) -> str:
    normalized = normalize_text(re.sub(r"^\d+(?:\.\d+)*\.?\s+", "", title))
    words = [word for word in normalized.split() if len(word) > 2]
    return " ".join(words[:8])


def is_noise_title(title: str) -> bool:
    lowered = title.lower().strip()
    if len(title) < 3 or len(title) > 180:
        return True
    if lowered in {"contents", "table of contents", "page", "pages"}:
        return True
    if CAPTION_RE.match(title):
        return True
    if is_date_title(title):
        return True
    if re.fullmatch(r"[\d\s.\-]+", title):
        return True
    if title.count(",") > 4 or title.count("@") > 0:
        return True
    if lowered.startswith(("doi:", "http://", "https://", "arxiv:")):
        return True
    return False
