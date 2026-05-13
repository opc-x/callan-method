#!/usr/bin/env python3
"""
Audit the structure of the 12 Callan Method source PDFs.

This does not trust the generated Markdown. It reads the original PDFs, extracts
page text, decodes the Callan private font where needed, and reports whether the
book/stage/lesson/page structure is suitable for an AI knowledge base.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections import Counter
from dataclasses import dataclass, asdict
from pathlib import Path

import fitz

from convert import decode_callan, is_encoded_text


BASE = Path("/Users/cuijianchen/gh-projects/kb-personal/callan-method")
PDF_DIR = Path("/Users/cuijianchen/gh-projects/kb-personal/callan-method-origin")
OUT_DIR = BASE / "audit"

EXPECTED = {
    1: (1, 1, 9),
    2: (2, 10, 24),
    3: (3, 25, 40),
    4: (4, 41, 60),
    5: (5, 61, 77),
    6: (6, 78, 94),
    7: (7, 95, 111),
    8: (8, 112, 126),
    9: (9, 127, 145),
    10: (10, 146, 163),
    11: (11, 164, 177),
    12: (12, 178, 191),
}

CEFR = {
    1: "A1",
    2: "A1-A2",
    3: "A2",
    4: "A2-B1",
    5: "B1",
    6: "B1-B2",
    7: "B2",
    8: "B2-C1",
    9: "C1",
    10: "C1-C2",
    11: "C2",
    12: "C2",
}

SUSPICIOUS_PATTERNS = [
    r"\b8IBU\b",
    r"\bUIF\b",
    r"\bXJUI\b",
    r"\bIBWF\b",
    r"\bJT\b",
    r"\bBSF\b",
    r"\bEP\b",
    r"\bZPV\b",
    r"[\x00-\x08\x0b\x0e-\x1f]",
    r"[ǽǿʝʒ]",
]

LESSON_RE = re.compile(r"(?m)^\s*LESSON\s*(\d+)\s*$", re.I)
STAGE_RE = re.compile(r"\b(?:Student[’']s Book\s*[–-]\s*)?Stage\s+(\d+)\b", re.I)
DICTATION_RE = re.compile(r"(?im)^\s*Dictation\b")
REVISION_RE = re.compile(r"(?im)^\s*(?:Revision exercise|Do revision exercise)\b")
WORD_BUILDING_RE = re.compile(r"(?im)^\s*Word-building exercise\s*(\d*)\b")
CHART_RE = re.compile(r"\bSee Chart\s+\d+\b", re.I)
QUESTION_RE = re.compile(r"\?")
VOCAB_INDEX_RE = re.compile(
    r"\b(Chinese|Japanese|French|Spanish|German|Portuguese|Polish|Turkish|"
    r"Arabic|Korean|Italian|Russian|Czech|Slovak|Hungarian)\s+vocabulary\b",
    re.I,
)


@dataclass
class PageAudit:
    pdf_page: int
    book_page_guess: int | None
    raw_chars: int
    decoded_chars: int
    nonempty_lines: int
    low_text: bool
    lessons_started: list[int]
    suspicious_hits: int
    suspicious_ratio: float
    dictation_headings: int
    revision_headings: int
    word_building_headings: int
    chart_refs: int
    question_marks: int
    vocab_cluster_count: int


@dataclass
class LessonAudit:
    lesson: int
    pdf_page_start: int
    pdf_page_end: int
    book_page_start_guess: int | None
    book_page_end_guess: int | None
    decoded_chars: int
    nonempty_lines: int
    question_marks: int
    dictation_headings: int
    revision_headings: int
    word_building_headings: int
    chart_refs: int
    vocab_cluster_count: int
    suspicious_hits: int
    suspicious_ratio: float
    status: str
    warnings: list[str]


def run_pdftotext_pages(pdf: Path) -> list[str]:
    result = subprocess.run(
        ["pdftotext", "-layout", str(pdf), "-"],
        capture_output=True,
        text=True,
        errors="replace",
        check=True,
    )
    pages = result.stdout.split("\f")
    if pages and pages[-1] == "":
        pages.pop()
    return pages


def count_suspicious(text: str) -> int:
    return sum(len(re.findall(pattern, text)) for pattern in SUSPICIOUS_PATTERNS)


def decode_page_text(text: str) -> str:
    """Decode only lines that look like Callan private-font text."""
    decoded_lines = []
    for line in text.splitlines():
        s = line.strip()
        if re.match(r"^LESSON\s*\d+\s*$", s, re.I) or re.match(r"^STAGE\s+\d+\s*$", s, re.I):
            decoded_lines.append(line)
        elif re.match(r"^(?:Dictation|Revision exercise|Do revision exercise|Word-building exercise)\b", s, re.I):
            decoded_lines.append(line)
        elif is_encoded_text(line):
            decoded_lines.append(decode_callan(line))
        else:
            decoded_lines.append(decode_callan(line) if "\x01" in line else line)
    return "\n".join(decoded_lines)


def book_page_guess(text: str) -> int | None:
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        m = re.match(r"^(\d{1,4})(?:\s+\S|$)", s)
        if m:
            value = int(m.group(1))
            if value > 0:
                return value
        return None
    return None


def extract_vocab_clusters(pdf: Path) -> dict[int, int]:
    """Count colored vocabulary/word-family boxes per 1-based PDF page."""
    counts: dict[int, int] = {}
    doc = fitz.open(str(pdf))
    try:
        for page_index, page in enumerate(doc, start=1):
            total = 0
            for drawing in page.get_drawings():
                fill = drawing.get("fill")
                if not fill or fill in [(1, 1, 1), (0, 0, 0)]:
                    continue
                rect = drawing["rect"]
                if rect.height < 12 or rect.height > 120:
                    continue
                text = " ".join(w[4] for w in page.get_text("words", clip=rect)).strip()
                if not text:
                    continue
                low = text.lower()
                if any(k in low for k in ("exercise", "stage", "callan")):
                    continue
                total += 1
            counts[page_index] = total
    finally:
        doc.close()
    return counts


def audit_page(pdf_page: int, raw: str, cluster_count: int) -> PageAudit:
    decoded = decode_page_text(raw)
    nonempty = sum(1 for line in decoded.splitlines() if line.strip())
    suspicious = count_suspicious(decoded)
    ratio = suspicious / max(len(decoded), 1)
    lessons = sorted({int(x) for x in LESSON_RE.findall(raw)} | {int(x) for x in LESSON_RE.findall(decoded)})
    return PageAudit(
        pdf_page=pdf_page,
        book_page_guess=book_page_guess(decoded),
        raw_chars=len(raw),
        decoded_chars=len(decoded.strip()),
        nonempty_lines=nonempty,
        low_text=len(decoded.strip()) < 80,
        lessons_started=lessons,
        suspicious_hits=suspicious,
        suspicious_ratio=round(ratio, 6),
        dictation_headings=len(DICTATION_RE.findall(decoded)),
        revision_headings=len(REVISION_RE.findall(decoded)),
        word_building_headings=len(WORD_BUILDING_RE.findall(decoded)),
        chart_refs=len(CHART_RE.findall(decoded)),
        question_marks=len(QUESTION_RE.findall(decoded)),
        vocab_cluster_count=cluster_count,
    )


def lesson_status(lesson: LessonAudit) -> tuple[str, list[str]]:
    warnings: list[str] = []
    status = "PASS"
    if lesson.decoded_chars < 400:
        warnings.append("very_low_lesson_text")
        status = "WARNING"
    if lesson.question_marks == 0:
        warnings.append("no_question_marks")
        status = "WARNING"
    if lesson.suspicious_ratio > 0.01:
        warnings.append("high_suspicious_ratio")
        status = "FAIL"
    elif lesson.suspicious_ratio > 0.003:
        warnings.append("medium_suspicious_ratio")
        if status != "FAIL":
            status = "WARNING"
    return status, warnings


def build_lessons(pages: list[PageAudit], content_end_page: int | None = None) -> list[LessonAudit]:
    first_start_by_lesson: dict[int, int] = {}
    for page in pages:
        if content_end_page is not None and page.pdf_page > content_end_page:
            continue
        for lesson in page.lessons_started:
            first_start_by_lesson.setdefault(lesson, page.pdf_page)
    starts = sorted(first_start_by_lesson.items())

    lessons: list[LessonAudit] = []
    for idx, (lesson_num, start_page) in enumerate(starts):
        end_page = starts[idx + 1][1] - 1 if idx + 1 < len(starts) else (content_end_page or pages[-1].pdf_page)
        if end_page < start_page:
            end_page = start_page
        segment = [p for p in pages if start_page <= p.pdf_page <= end_page]
        decoded_chars = sum(p.decoded_chars for p in segment)
        suspicious_hits = sum(p.suspicious_hits for p in segment)
        ratio = suspicious_hits / max(decoded_chars, 1)
        first_book_page = next((p.book_page_guess for p in segment if p.book_page_guess), None)
        last_book_page = next((p.book_page_guess for p in reversed(segment) if p.book_page_guess), None)
        item = LessonAudit(
            lesson=lesson_num,
            pdf_page_start=start_page,
            pdf_page_end=end_page,
            book_page_start_guess=first_book_page,
            book_page_end_guess=last_book_page,
            decoded_chars=decoded_chars,
            nonempty_lines=sum(p.nonempty_lines for p in segment),
            question_marks=sum(p.question_marks for p in segment),
            dictation_headings=sum(p.dictation_headings for p in segment),
            revision_headings=sum(p.revision_headings for p in segment),
            word_building_headings=sum(p.word_building_headings for p in segment),
            chart_refs=sum(p.chart_refs for p in segment),
            vocab_cluster_count=sum(p.vocab_cluster_count for p in segment),
            suspicious_hits=suspicious_hits,
            suspicious_ratio=round(ratio, 6),
            status="PASS",
            warnings=[],
        )
        item.status, item.warnings = lesson_status(item)
        lessons.append(item)
    return lessons


def summarize_book(book: int) -> dict:
    pdf = PDF_DIR / f"Callan Method {book}.pdf"
    if not pdf.exists():
        return {"book": book, "status": "FAIL", "warnings": ["missing_pdf"]}

    raw_pages = run_pdftotext_pages(pdf)
    cluster_counts = extract_vocab_clusters(pdf)
    pages = [
        audit_page(i, raw, cluster_counts.get(i, 0))
        for i, raw in enumerate(raw_pages, start=1)
    ]
    vocab_index_pages = [
        i
        for i, raw in enumerate(raw_pages, start=1)
        if VOCAB_INDEX_RE.search(raw) or VOCAB_INDEX_RE.search(decode_page_text(raw))
    ]
    content_end_page = min(vocab_index_pages) - 1 if vocab_index_pages else len(raw_pages)
    raw_full = "\n".join(raw_pages)
    decoded_full = "\n".join(decode_page_text(raw) for raw in raw_pages)
    stages = sorted(Counter(int(x) for x in STAGE_RE.findall(raw_full + "\n" + decoded_full)).items())
    lessons = build_lessons(pages, content_end_page)

    expected_stage, expected_start, expected_end = EXPECTED[book]
    lesson_nums = [lesson.lesson for lesson in lessons]
    expected_lessons = list(range(expected_start, expected_end + 1))
    missing = [n for n in expected_lessons if n not in lesson_nums]
    extra = [n for n in lesson_nums if n not in expected_lessons]
    out_of_order = lesson_nums != sorted(lesson_nums)
    low_text_pages = [p.pdf_page for p in pages if p.low_text]
    risky_pages = [p.pdf_page for p in pages if p.suspicious_ratio > 0.003]

    warnings: list[str] = []
    status = "PASS"
    if not any(stage == expected_stage for stage, _ in stages):
        warnings.append("expected_stage_not_found")
        status = "FAIL"
    if missing:
        warnings.append("missing_lessons")
        status = "FAIL"
    if extra:
        warnings.append("extra_lessons")
        status = "WARNING" if status != "FAIL" else status
    if out_of_order:
        warnings.append("lesson_order_not_monotonic")
        status = "FAIL"
    if risky_pages:
        warnings.append("suspicious_pages")
        status = "WARNING" if status != "FAIL" else status

    markdown_path = BASE / f"book-{book}.md"
    markdown_chars = len(markdown_path.read_text(encoding="utf-8")) if markdown_path.exists() else None
    reference_chars = sum(p.decoded_chars for p in pages)
    char_ratio = round(markdown_chars / reference_chars, 4) if markdown_chars else None

    return {
        "book": book,
        "stage_expected": expected_stage,
        "stage_hits": [{"stage": s, "count": c} for s, c in stages],
        "cefr": CEFR[book],
        "source_pdf": str(pdf),
        "pdf_pages": len(raw_pages),
        "reference_decoded_chars": reference_chars,
        "reference_nonempty_lines": sum(p.nonempty_lines for p in pages),
        "existing_markdown_file": str(markdown_path) if markdown_path.exists() else None,
        "existing_markdown_chars": markdown_chars,
        "existing_markdown_to_reference_ratio": char_ratio,
        "expected_lesson_start": expected_start,
        "expected_lesson_end": expected_end,
        "detected_lesson_start": min(lesson_nums) if lesson_nums else None,
        "detected_lesson_end": max(lesson_nums) if lesson_nums else None,
        "detected_lesson_count": len(set(lesson_nums)),
        "missing_lessons": missing,
        "extra_lessons": extra,
        "low_text_pages": low_text_pages,
        "suspicious_pages": risky_pages,
        "vocabulary_index_pages": vocab_index_pages,
        "content_end_page": content_end_page,
        "page_totals": {
            "question_marks": sum(p.question_marks for p in pages),
            "dictation_headings": sum(p.dictation_headings for p in pages),
            "revision_headings": sum(p.revision_headings for p in pages),
            "word_building_headings": sum(p.word_building_headings for p in pages),
            "chart_refs": sum(p.chart_refs for p in pages),
            "vocab_clusters": sum(p.vocab_cluster_count for p in pages),
        },
        "status": status,
        "warnings": warnings,
        "lessons": [asdict(lesson) for lesson in lessons],
        "pages": [asdict(page) for page in pages],
    }


def render_markdown(data: dict) -> str:
    books = data["books"]
    lines = [
        "# Callan Method Structure Audit",
        "",
        "Source PDFs: `/Users/cuijianchen/gh-projects/kb-personal/callan-method-origin`",
        "",
        "## Overall Verdict",
        "",
        f"- Overall status: **{data['overall_status']}**",
        f"- Books audited: {len(books)}",
        f"- Lesson coverage: {data['lesson_coverage']['detected_start']}-{data['lesson_coverage']['detected_end']} "
        f"({data['lesson_coverage']['detected_count']} lessons)",
        f"- Missing lessons: {data['lesson_coverage']['missing_lessons'] or 'none'}",
        "",
        "## Book Summary",
        "",
        "| Book | Stage | CEFR | PDF pages | Lessons | Missing | Low text pages | Suspicious pages | Vocab clusters | Dictations | Word-building | Existing MD ratio | Status |",
        "|---:|---:|---|---:|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for book in books:
        lessons = f"{book['detected_lesson_start']}-{book['detected_lesson_end']} ({book['detected_lesson_count']})"
        ratio = book["existing_markdown_to_reference_ratio"]
        ratio_text = f"{ratio:.2f}" if isinstance(ratio, float) else "-"
        lines.append(
            f"| {book['book']} | {book['stage_expected']} | {book['cefr']} | {book['pdf_pages']} | "
            f"{lessons} | {len(book['missing_lessons'])} | {len(book['low_text_pages'])} | "
            f"{len(book['suspicious_pages'])} | {book['page_totals']['vocab_clusters']} | "
            f"{book['page_totals']['dictation_headings']} | {book['page_totals']['word_building_headings']} | "
            f"{ratio_text} | {book['status']} |"
        )

    lines.extend([
        "",
        "## Structure Notes",
        "",
        "- The reliable top-level structure is `Book -> Stage -> Lesson`.",
        "- The full course should cover `Stage 1-12` and `Lesson 1-191` without gaps.",
        "- The most reliable source anchors are detected `LESSON N` headings and 1-based PDF pages.",
        "- `vocab_clusters` are colored vocabulary/word-family boxes detected from PDF drawings.",
        "- `existing_md_ratio` compares the current `book-N.md` size with decoded source text size; it is only a drift signal, not a final quality score.",
        "",
        "## Pages Requiring Manual/Visual Review",
        "",
    ])
    for book in books:
        review = sorted(set(book["low_text_pages"]) | set(book["suspicious_pages"]))
        review_preview = ", ".join(map(str, review[:40]))
        if len(review) > 40:
            review_preview += f", ... (+{len(review) - 40})"
        lines.append(f"- Book {book['book']}: {review_preview or 'none'}")

    lines.extend([
        "",
        "## Lesson Ranges",
        "",
        "| Book | Lesson | PDF pages | Book pages guess | chars | Q marks | Vocab clusters | Dictation | Revision | Word-building | Chart refs | Status | Warnings |",
        "|---:|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|",
    ])
    for book in books:
        for lesson in book["lessons"]:
            bp_start = lesson["book_page_start_guess"] or "-"
            bp_end = lesson["book_page_end_guess"] or "-"
            warnings = ",".join(lesson["warnings"]) if lesson["warnings"] else "-"
            lines.append(
                f"| {book['book']} | {lesson['lesson']} | {lesson['pdf_page_start']}-{lesson['pdf_page_end']} | "
                f"{bp_start}-{bp_end} | {lesson['decoded_chars']} | {lesson['question_marks']} | "
                f"{lesson['vocab_cluster_count']} | {lesson['dictation_headings']} | "
                f"{lesson['revision_headings']} | {lesson['word_building_headings']} | "
                f"{lesson['chart_refs']} | {lesson['status']} | {warnings} |"
            )

    return "\n".join(lines) + "\n"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    books = [summarize_book(book) for book in range(1, 13)]
    detected_lessons = sorted({lesson["lesson"] for book in books for lesson in book.get("lessons", [])})
    expected_all = list(range(1, 192))
    missing_all = [n for n in expected_all if n not in detected_lessons]
    overall_status = "PASS"
    if missing_all or any(book["status"] == "FAIL" for book in books):
        overall_status = "FAIL"
    elif any(book["status"] == "WARNING" for book in books):
        overall_status = "WARNING"

    data = {
        "overall_status": overall_status,
        "lesson_coverage": {
            "expected_start": 1,
            "expected_end": 191,
            "detected_start": detected_lessons[0] if detected_lessons else None,
            "detected_end": detected_lessons[-1] if detected_lessons else None,
            "detected_count": len(detected_lessons),
            "missing_lessons": missing_all,
        },
        "books": books,
    }
    (OUT_DIR / "callan-structure-audit.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (OUT_DIR / "callan-structure-audit.md").write_text(
        render_markdown(data),
        encoding="utf-8",
    )
    print(f"Wrote {OUT_DIR / 'callan-structure-audit.json'}")
    print(f"Wrote {OUT_DIR / 'callan-structure-audit.md'}")
    print(f"Overall status: {overall_status}")


if __name__ == "__main__":
    main()
