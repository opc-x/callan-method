#!/usr/bin/env python3
"""
Fine-grained structured JSON index for Callan Method 12-book course.

Produces:
  structured/course-index.json
  structured/lesson-index.json
  structured/page-index.json
  structured/block-index.json
  structured/term-index.json
  structured/qa-index.json
  structured/dictation-index.json
  structured/chart-index.json
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import fitz  # PyMuPDF

# ── Import shared helpers from extract_pymupdf ────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from extract_pymupdf import (
    decode_book_span,
    span_role,
    _VOCAB_IDX_RE,
    _VOCAB_INDEX_DOTS_RE,
)

# ── Constants ─────────────────────────────────────────────────────────────────

PDF_DIR = Path('/Users/cuijianchen/gh-projects/kb-personal/callan-method-origin')
OUT_DIR = Path('/Users/cuijianchen/gh-projects/kb-personal/callan-method/structured')

EXPECTED_LESSONS = {
    1: (1, 9), 2: (10, 24), 3: (25, 40), 4: (41, 60), 5: (61, 77),
    6: (78, 94), 7: (95, 111), 8: (112, 126), 9: (127, 145), 10: (146, 163),
    11: (164, 177), 12: (178, 191),
}

CEFR = {
    1: 'A1 (beginner)', 2: 'A1-A2', 3: 'A2', 4: 'A2-B1', 5: 'B1',
    6: 'B1-B2', 7: 'B2', 8: 'B2-C1', 9: 'C1', 10: 'C1-C2',
    11: 'C2', 12: 'C2',
}

STAGE_CEFR = CEFR  # same mapping

_LESSON_RE = re.compile(r'^\s*LESSON\s*(\d+)\s*$', re.I)
_STAGE_RE = re.compile(r'^\s*STAGE\s+\d+\s*$', re.I)
_DICTATION_RE = re.compile(r'^\s*Dictation\s*\d*\s*$', re.I)
_REVISION_RE = re.compile(r'^\s*(?:Do\s+)?Revision\b', re.I)
_WORD_BUILD_RE = re.compile(r'^\s*Word-building', re.I)
_CHART_TITLE_RE = re.compile(r'^\s*Chart\s+\d+\s*$', re.I)
_CHART_REF_RE = re.compile(r'\bSee\s+Chart\s+(\d+)\b', re.I)
_BOOK_PAGE_RE = re.compile(r'^\d{1,4}$')

# ── Utility ───────────────────────────────────────────────────────────────────

def normalize_term(term: str) -> str:
    """Lowercase and strip punctuation."""
    t = term.lower()
    t = re.sub(r"[^\w\s'-]", '', t)
    t = t.strip(" '-")
    return t

def clean_text(text: str) -> str:
    """Remove raw control characters (artifact check)."""
    # Allow tab and newline as they may appear; strip other control chars
    return re.sub(r'[\x00-\x08\x0b\x0e-\x1f]', '', text).strip()

# ── Core extraction ───────────────────────────────────────────────────────────

def extract_book_page_nums(page_dict: dict) -> list[int]:
    """
    Find all printed book page numbers on the page.
    These are FreeSet-Light spans at x0 < 30 matching 1-4 digit integers.
    Returns a list (often 2 per PDF page).
    """
    nums = []
    for block in page_dict.get('blocks', []):
        if block['type'] != 0:
            continue
        for line in block.get('lines', []):
            for span in line.get('spans', []):
                if span['bbox'][0] < 30 and 'Light' in span.get('font', ''):
                    txt = span['text'].strip()
                    if _BOOK_PAGE_RE.match(txt):
                        n = int(txt)
                        if n not in nums:
                            nums.append(n)
    return nums


def extract_book_page_num(page_dict: dict) -> int | None:
    """
    Find the first printed book page number on the page (for backward compat).
    """
    nums = extract_book_page_nums(page_dict)
    return nums[0] if nums else None


def process_page_spans(page_dict: dict) -> list[dict]:
    """
    Return a flat list of span events with role annotations.
    Each event: {role, text, inline_a, x0, y0}
    """
    events = []
    for block in page_dict.get('blocks', []):
        if block['type'] != 0:
            continue
        for line in block.get('lines', []):
            spans = line.get('spans', [])
            if not spans:
                continue

            # Gather non-empty spans excluding margin page numbers
            valid_spans = []
            for s in spans:
                if s['bbox'][0] < 30 and _BOOK_PAGE_RE.match(s['text'].strip()):
                    continue  # skip margin page numbers
                if s['text'].strip():
                    valid_spans.append(s)

            if not valid_spans:
                continue

            # Group by role
            by_role: dict[str, list] = {}
            for s in valid_spans:
                r = span_role(s['font'])
                by_role.setdefault(r, []).append(s)

            x0 = valid_spans[0]['bbox'][0]
            y0 = valid_spans[0]['bbox'][1]

            # HEAD overrides everything
            if 'HEAD' in by_role:
                text = ''.join(s['text'] for s in by_role['HEAD']).strip()
                events.append({'role': 'HEAD', 'text': text, 'inline_a': '', 'x0': x0, 'y0': y0})
                continue

            # Q row (may have inline A)
            if 'Q' in by_role:
                q_text = ''.join(decode_book_span(s['text']) for s in by_role['Q'])
                q_text = re.sub(r'  +', ' ', q_text).strip()
                a_text = ''
                if 'A' in by_role:
                    raw = ' '.join(s['text'].strip() for s in by_role['A'] if s['text'].strip())
                    a_text = clean_text(raw)
                events.append({'role': 'Q', 'text': q_text, 'inline_a': a_text, 'x0': x0, 'y0': y0})
                continue

            # NOTE
            if 'NOTE' in by_role:
                parts = []
                for role in ('A', 'NOTE'):
                    parts += [clean_text(s['text']) for s in by_role.get(role, []) if s['text'].strip()]
                text = ' '.join(parts)
                events.append({'role': 'NOTE', 'text': text, 'inline_a': '', 'x0': x0, 'y0': y0})
                continue

            # Pure A
            if 'A' in by_role and 'VOCAB' not in by_role:
                raw = ' '.join(s['text'].strip() for s in by_role['A'] if s['text'].strip())
                text = clean_text(raw)
                if text:
                    events.append({'role': 'A', 'text': text, 'inline_a': '', 'x0': x0, 'y0': y0})
                continue

            # VOCAB
            if 'VOCAB' in by_role:
                for s in by_role['VOCAB']:
                    txt = clean_text(s['text'])
                    if txt:
                        events.append({'role': 'VOCAB', 'text': txt, 'inline_a': '', 'x0': x0, 'y0': y0})
                continue

    return events


def build_page_blocks(
    events: list[dict],
    book: int,
    lesson: int,
    book_page: int | None,
    pdf_page: int,
    stage: int,
    pdf_name: str,
    seq_start: int = 1,
) -> tuple[list[dict], int]:
    """
    Convert a list of span events into ContentBlocks.
    Returns (blocks, next_seq).
    """
    blocks: list[dict] = []
    seq = seq_start

    def make_block_id(s: int) -> str:
        if book_page is not None:
            return f'book{book}_lesson{lesson}_pdf{pdf_page}_page{book_page}_block{s}'
        else:
            return f'book{book}_pdf{pdf_page}_block{s}'

    def new_block(btype: str) -> dict:
        nonlocal seq
        bid = make_block_id(seq)
        seq += 1
        b = {
            'block_id': bid,
            'type': btype,
            'book': book,
            'stage': stage,
            'lesson': lesson,
            'book_page': book_page,
            'pdf_page': pdf_page,
            'text': '',
            'source': {
                'pdf': pdf_name,
                'pdf_page': pdf_page,
                'book_page': book_page,
            },
        }
        return b

    def append_special_text(text_part: str):
        if cur_special is None:
            return
        t = clean_text(text_part)
        if not t:
            return
        if cur_special['text']:
            cur_special['text'] += ' | ' + t
        else:
            cur_special['text'] = t

    def chart_label(text_part: str) -> str | None:
        m = _CHART_TITLE_RE.match(text_part.strip())
        if m:
            return m.group(0).strip()
        m = _CHART_REF_RE.search(text_part)
        if m:
            return f'Chart {m.group(1)}'
        return None

    # State machine
    cur_lexical: dict | None = None   # accumulating lexical_block
    cur_qa: dict | None = None        # accumulating qa_block
    cur_q: str | None = None
    cur_a_parts: list[str] = []
    cur_note: dict | None = None      # accumulating grammar_note
    cur_special: dict | None = None   # dictation/revision/word_building
    special_type: str | None = None
    in_special = False

    def flush_lexical():
        nonlocal cur_lexical
        if cur_lexical and cur_lexical.get('terms'):
            cur_lexical['text'] = ' | '.join(cur_lexical['terms'])
            blocks.append(cur_lexical)
        cur_lexical = None

    def flush_qa_pair():
        nonlocal cur_q, cur_a_parts
        if cur_q is not None and cur_qa is not None:
            q = cur_q.strip()
            a = ' '.join(cur_a_parts).strip()
            a = clean_text(a)
            if q:
                cur_qa.setdefault('items', []).append({'question': q, 'answer': a})
        cur_q = None
        cur_a_parts = []

    def flush_qa():
        nonlocal cur_qa
        flush_qa_pair()
        if cur_qa and cur_qa.get('items'):
            # build text summary
            cur_qa['text'] = ' | '.join(
                f"Q: {it['question']} A: {it['answer']}" for it in cur_qa['items']
            )
            blocks.append(cur_qa)
        cur_qa = None

    def flush_note():
        nonlocal cur_note
        if cur_note and cur_note.get('text', '').strip():
            blocks.append(cur_note)
        cur_note = None

    def flush_special():
        nonlocal cur_special, in_special, special_type
        if cur_special and cur_special.get('text', '').strip():
            blocks.append(cur_special)
        cur_special = None
        in_special = False
        special_type = None

    for ev in events:
        role = ev['role']
        text = ev['text']
        inline_a = ev.get('inline_a', '')

        if role == 'HEAD':
            m = _LESSON_RE.match(text)
            if m:
                # lesson boundary — caller handles lesson tracking; just flush
                flush_lexical(); flush_qa(); flush_note(); flush_special()
                continue

            if _DICTATION_RE.match(text):
                flush_lexical(); flush_qa(); flush_note(); flush_special()
                b = new_block('dictation')
                b['text'] = ''
                cur_special = b
                special_type = 'dictation'
                in_special = True
                continue

            if _REVISION_RE.match(text):
                flush_lexical(); flush_qa(); flush_note(); flush_special()
                b = new_block('revision_exercise')
                b['text'] = ''
                cur_special = b
                special_type = 'revision_exercise'
                in_special = True
                continue

            if _WORD_BUILD_RE.match(text):
                flush_lexical(); flush_qa(); flush_note(); flush_special()
                b = new_block('word_building_exercise')
                b['text'] = ''
                cur_special = b
                special_type = 'word_building_exercise'
                in_special = True
                continue

            if _STAGE_RE.match(text):
                flush_lexical(); flush_qa(); flush_note(); flush_special()
                continue

            # Other HEAD (e.g. front matter title)
            flush_lexical(); flush_qa(); flush_note(); flush_special()
            continue

        if in_special:
            if special_type == 'chart_page':
                # Chart pages contain mixed font roles and Q-like glyph rows.
                # Keep them together until a new heading/chart starts.
                if role == 'VOCAB' and _CHART_TITLE_RE.match(text):
                    flush_special()
                    b = new_block('chart_page')
                    b['text'] = text
                    b['chart_label'] = chart_label(text)
                    cur_special = b
                    special_type = 'chart_page'
                    in_special = True
                    continue
                append_special_text(text)
                if inline_a:
                    append_special_text(inline_a)
                continue

            if role == 'Q':
                # Q line ends special block
                flush_special()
                # Fall through to Q handling
            elif role in ('A', 'NOTE', 'VOCAB', 'HEAD'):
                if role == 'VOCAB':
                    # vocab in special section treated as text
                    if cur_special is not None:
                        if cur_special['text']:
                            cur_special['text'] += ' ' + text
                        else:
                            cur_special['text'] = text
                    continue
                elif role == 'A':
                    if cur_special is not None:
                        t = clean_text(text)
                        if t:
                            if cur_special['text']:
                                cur_special['text'] += ' ' + t
                            else:
                                cur_special['text'] = t
                    continue
                elif role == 'NOTE':
                    if cur_special is not None:
                        t = clean_text(text)
                        if t:
                            if cur_special['text']:
                                cur_special['text'] += ' ' + t
                            else:
                                cur_special['text'] = t
                    continue
                # HEAD already handled above
                continue
            # if Q: fall through below

        if role == 'VOCAB':
            if _CHART_TITLE_RE.match(text):
                flush_lexical(); flush_qa(); flush_note(); flush_special()
                b = new_block('chart_page')
                b['text'] = text
                b['chart_label'] = chart_label(text)
                cur_special = b
                special_type = 'chart_page'
                in_special = True
                continue

            # Long VOCAB spans → grammar_note
            if len(text) > 60 and (' ' in text[:30]):
                flush_lexical()
                flush_qa()
                flush_note()
                b = new_block('grammar_note')
                b['text'] = text
                blocks.append(b)
                continue
            # Short VOCAB → accumulate lexical_block
            flush_qa()
            flush_note()
            if in_special:
                flush_special()
            if cur_lexical is None:
                cur_lexical = new_block('lexical_block')
                cur_lexical['terms'] = []
            cur_lexical['terms'].append(text)
            continue

        if role == 'NOTE':
            if _DICTATION_RE.match(text):
                flush_lexical(); flush_qa(); flush_note(); flush_special()
                b = new_block('dictation')
                b['title'] = text
                b['text'] = text
                cur_special = b
                special_type = 'dictation'
                in_special = True
                continue

            if _CHART_REF_RE.search(text):
                flush_lexical()
                flush_qa()
                if in_special:
                    flush_special()
                b = new_block('chart_reference')
                b['text'] = clean_text(text)
                b['chart_label'] = chart_label(text)
                blocks.append(b)
                continue

            # grammar note
            flush_lexical()
            flush_qa()
            if in_special:
                flush_special()
            t = clean_text(text)
            if not t:
                continue
            if cur_note is None:
                cur_note = new_block('grammar_note')
                cur_note['text'] = t
            else:
                cur_note['text'] += ' ' + t
            continue

        if role == 'Q':
            flush_lexical()
            flush_note()
            if in_special:
                flush_special()
            q_text = text
            if q_text:
                # Continuation heuristic
                is_cont = cur_q is not None and q_text[0].islower()
                if is_cont:
                    cur_q = cur_q.rstrip().rstrip('?') + ' ' + q_text
                    if inline_a:
                        cur_a_parts.append(inline_a)
                else:
                    flush_qa_pair()
                    if cur_qa is None:
                        cur_qa = new_block('qa_block')
                        cur_qa['items'] = []
                    cur_q = q_text
                    cur_a_parts = [inline_a] if inline_a else []
            elif inline_a and cur_q is not None:
                cur_a_parts.append(inline_a)
            continue

        if role == 'A':
            flush_lexical()
            flush_note()
            if in_special:
                flush_special()
            t = clean_text(text)
            if not t:
                continue
            if cur_q is not None:
                cur_a_parts.append(t)
            elif cur_qa and cur_qa.get('items'):
                # Append to last answer
                last = cur_qa['items'][-1]
                last['answer'] = (last['answer'] + ' ' + t).strip()
            continue

    # Flush everything at end of page
    flush_lexical()
    flush_qa()
    flush_note()
    flush_special()

    return blocks, seq


def build_book_page_lookup(doc: fitz.Document) -> dict[int, int]:
    """
    Two-pass: scan all pages to build a map from pdf_page -> book_page.
    For pages with no explicit book page number, interpolate from neighbors.
    """
    # First pass: collect explicit book_page numbers per pdf_page
    # A PDF page may have 2+ book pages shown (first one is the page_start)
    explicit: dict[int, int] = {}  # pdf_page (1-indexed) -> first book_page on that pdf page

    for pdf_page_0 in range(len(doc)):
        pdf_page = pdf_page_0 + 1
        page = doc[pdf_page_0]
        page_dict = page.get_text('dict', sort=True)
        nums = extract_book_page_nums(page_dict)
        if nums:
            explicit[pdf_page] = nums[0]

    # Second pass: fill in gaps using forward-fill from previous known value
    # For pages with no number, use the last known book_page + offset
    result: dict[int, int] = {}
    last_known_pdf = None
    last_known_bp = None

    for pdf_page in range(1, len(doc) + 1):
        if pdf_page in explicit:
            result[pdf_page] = explicit[pdf_page]
            last_known_pdf = pdf_page
            last_known_bp = explicit[pdf_page]
        elif last_known_bp is not None:
            # Forward fill: use last known value (same book page section continues)
            result[pdf_page] = last_known_bp
        # else: still in front matter, leave as None (will be handled separately)

    return result


def process_book(book_num: int) -> dict:
    """
    Process one book PDF page by page.
    Returns a dict with all collected data.
    """
    pdf_name = f'Callan Method {book_num}.pdf'
    pdf_path = PDF_DIR / pdf_name
    doc = fitz.open(str(pdf_path))

    stage = book_num
    lesson_range = EXPECTED_LESSONS[book_num]

    # Build book_page lookup (with interpolation for missing pages)
    book_page_lookup = build_book_page_lookup(doc)

    # Result containers
    all_blocks: list[dict] = []
    page_entries: list[dict] = []  # one per pdf page

    current_lesson = None
    finished = False

    for pdf_page_0 in range(len(doc)):
        if finished:
            break

        pdf_page = pdf_page_0 + 1  # 1-indexed
        page = doc[pdf_page_0]
        page_dict = page.get_text('dict', sort=True)

        # Use pre-computed book_page (with interpolation for missing pages)
        book_page = book_page_lookup.get(pdf_page)

        # Get all span events
        events = process_page_spans(page_dict)

        # Check for vocab index stop signal
        stop_page = False
        filtered_events = []
        for ev in events:
            text = ev['text']
            if _VOCAB_IDX_RE.search(text) or _VOCAB_INDEX_DOTS_RE.search(text):
                stop_page = True
                finished = True
                break
            filtered_events.append(ev)
        events = filtered_events

        # Detect lesson changes on this page (update current_lesson before building blocks)
        # We scan events to find lesson headers first
        page_lesson_changes = []
        for ev in events:
            if ev['role'] == 'HEAD':
                m = _LESSON_RE.match(ev['text'])
                if m:
                    page_lesson_changes.append(int(m.group(1)))

        # The lesson at the START of this page is current_lesson (before changes)
        # but we need the lesson that applies to EACH block. We'll do single-pass
        # through events tracking lesson transitions.

        # Determine lesson at page start
        page_start_lesson = current_lesson

        # If no lesson detected yet, check if page has front matter
        if current_lesson is None and not page_lesson_changes:
            # Front matter
            b = {
                'block_id': f'book{book_num}_pdf{pdf_page}_block1',
                'type': 'front_matter',
                'book': book_num,
                'stage': stage,
                'lesson': None,
                'book_page': book_page,
                'pdf_page': pdf_page,
                'text': '',
                'source': {'pdf': pdf_name, 'pdf_page': pdf_page, 'book_page': book_page},
            }
            # Collect some text for front matter
            fm_texts = [ev['text'] for ev in events if ev['text'].strip()]
            b['text'] = ' | '.join(fm_texts[:5])
            all_blocks.append(b)
            page_entries.append({
                'pdf_page': pdf_page,
                'book_page': book_page,
                'lesson': None,
                'block_ids': [b['block_id']],
            })
            # update lesson if found
            if page_lesson_changes:
                current_lesson = page_lesson_changes[-1]
            continue

        # Update current_lesson to last lesson heading seen before (or during) this page
        if page_lesson_changes:
            # Process normally but update lesson at each heading
            # We'll build blocks in segments per lesson-change
            pass

        # Build blocks for this page, passing through lesson changes
        lesson_for_page = current_lesson if current_lesson is not None else (lesson_range[0] if page_lesson_changes else None)

        # Split events at lesson heading boundaries for proper lesson attribution
        segments: list[tuple[int | None, list[dict]]] = []
        seg_lesson = current_lesson
        seg_events: list[dict] = []

        for ev in events:
            if ev['role'] == 'HEAD':
                m = _LESSON_RE.match(ev['text'])
                if m:
                    # flush current segment
                    if seg_events or seg_lesson != current_lesson:
                        segments.append((seg_lesson, seg_events))
                    seg_events = []
                    seg_lesson = int(m.group(1))
                    current_lesson = seg_lesson
                    continue
            seg_events.append(ev)

        if seg_events:
            segments.append((seg_lesson, seg_events))

        if not segments and not page_lesson_changes:
            segments = [(current_lesson, [])]

        # Build blocks per segment
        page_block_ids: list[str] = []
        seg_seq = 1
        for seg_l, seg_evs in segments:
            if seg_l is None:
                continue
            blks, next_seq = build_page_blocks(
                events=seg_evs,
                book=book_num,
                lesson=seg_l,
                book_page=book_page,
                pdf_page=pdf_page,
                stage=stage,
                pdf_name=pdf_name,
                seq_start=seg_seq,
            )
            seg_seq = next_seq
            for blk in blks:
                all_blocks.append(blk)
                page_block_ids.append(blk['block_id'])

        page_entries.append({
            'pdf_page': pdf_page,
            'book_page': book_page,
            'lesson': current_lesson,
            'block_ids': page_block_ids,
        })

    doc.close()
    return {
        'book': book_num,
        'stage': stage,
        'pdf_name': pdf_name,
        'blocks': all_blocks,
        'pages': page_entries,
    }


# ── Build indexes ─────────────────────────────────────────────────────────────

def build_indexes(all_book_data: list[dict]) -> dict:
    """
    Build all required index structures from collected book data.
    """
    # course-index
    course_books = []
    total_blocks = 0
    total_terms = 0
    total_qa_pairs = 0

    # lesson-index: lesson_num -> data
    lesson_index: dict[str, dict] = {}
    # page-index: book{N}_pdf{P} -> data
    page_index: dict[str, dict] = {}
    # block-index: block_id -> block
    block_index: dict[str, dict] = {}
    # term-index: normalized_term -> list of entries
    term_index: dict[str, list] = defaultdict(list)
    # qa-index: list of items
    qa_items: list[dict] = []
    # dictation-index: list of items
    dictation_items: list[dict] = []
    # chart-index: chart references and chart pages
    chart_items: list[dict] = []

    for bd in all_book_data:
        book_num = bd['book']
        stage = bd['stage']
        pdf_name = bd['pdf_name']
        lr = EXPECTED_LESSONS[book_num]
        lesson_count = lr[1] - lr[0] + 1

        course_books.append({
            'book': book_num,
            'stage': stage,
            'cefr': CEFR[book_num],
            'lesson_range': list(lr),
            'lesson_count': lesson_count,
            'pdf': pdf_name,
        })

        # Build lesson/page/block indexes
        # First, gather lesson data from pages
        lesson_data: dict[int, dict] = {}

        for pg in bd['pages']:
            pdf_page = pg['pdf_page']
            book_page = pg['book_page']
            lesson_num = pg['lesson']
            block_ids = pg['block_ids']

            # page-index
            page_key = f'book{book_num}_pdf{pdf_page}'
            page_index[page_key] = {
                'book': book_num,
                'pdf_page': pdf_page,
                'book_page': book_page,
                'lesson': lesson_num,
                'block_ids': block_ids,
            }

            # lesson-index accumulation
            if lesson_num is not None:
                if lesson_num not in lesson_data:
                    lesson_data[lesson_num] = {
                        'lesson': lesson_num,
                        'book': book_num,
                        'stage': stage,
                        'pdf_pages': [],
                        'book_pages': [],
                        'block_ids': [],
                        'qa_count': 0,
                        'term_count': 0,
                    }
                ld = lesson_data[lesson_num]
                if pdf_page not in ld['pdf_pages']:
                    ld['pdf_pages'].append(pdf_page)
                if book_page is not None and book_page not in ld['book_pages']:
                    ld['book_pages'].append(book_page)
                for bid in block_ids:
                    if bid not in ld['block_ids']:
                        ld['block_ids'].append(bid)

        # Process blocks
        for blk in bd['blocks']:
            bid = blk['block_id']
            btype = blk['type']
            lesson_num = blk['lesson']
            book_page = blk['book_page']
            pdf_page = blk['pdf_page']

            # Add to block-index
            block_index[bid] = blk
            total_blocks += 1

            # term-index
            if btype == 'lexical_block':
                terms = blk.get('terms', [])
                for term in terms:
                    term_clean = term.strip()
                    if not term_clean:
                        continue
                    norm = normalize_term(term_clean)
                    if not norm:
                        continue
                    entry = {
                        'term': term_clean,
                        'normalized': norm,
                        'book': book_num,
                        'stage': stage,
                        'lesson': lesson_num,
                        'book_page': book_page,
                        'pdf_page': pdf_page,
                        'block_id': bid,
                        'block_type': btype,
                    }
                    term_index[norm].append(entry)
                    total_terms += 1
                    if lesson_num is not None and lesson_num in lesson_data:
                        lesson_data[lesson_num]['term_count'] += 1

            # qa-index
            if btype == 'qa_block':
                for idx, item in enumerate(blk.get('items', [])):
                    qa_entry = {
                        'question': item['question'],
                        'answer': item['answer'],
                        'book': book_num,
                        'stage': stage,
                        'lesson': lesson_num,
                        'book_page': book_page,
                        'pdf_page': pdf_page,
                        'block_id': bid,
                        'pair_index': idx,
                    }
                    qa_items.append(qa_entry)
                    total_qa_pairs += 1
                    if lesson_num is not None and lesson_num in lesson_data:
                        lesson_data[lesson_num]['qa_count'] += 1

            # dictation-index
            if btype == 'dictation':
                text = blk.get('text', '').strip()
                if text:
                    dictation_items.append({
                        'text': text,
                        'book': book_num,
                        'stage': stage,
                        'lesson': lesson_num,
                        'book_page': book_page,
                        'pdf_page': pdf_page,
                        'block_id': bid,
                    })

            # chart-index
            if btype in ('chart_reference', 'chart_page'):
                text = blk.get('text', '').strip()
                if text:
                    chart_items.append({
                        'type': btype,
                        'chart_label': blk.get('chart_label'),
                        'text': text,
                        'book': book_num,
                        'stage': stage,
                        'lesson': lesson_num,
                        'book_page': book_page,
                        'pdf_page': pdf_page,
                        'block_id': bid,
                    })

        # Merge lesson data into global lesson_index
        for ln, ld in lesson_data.items():
            lesson_index[str(ln)] = ld

    # Count total_terms from term_index
    total_terms_actual = sum(len(v) for v in term_index.values())

    course_index = {
        'total_books': 12,
        'total_lessons': 191,
        'total_blocks': total_blocks,
        'total_terms': total_terms_actual,
        'total_qa_pairs': total_qa_pairs,
        'books': sorted(course_books, key=lambda x: x['book']),
    }

    return {
        'course_index': course_index,
        'lesson_index': lesson_index,
        'page_index': page_index,
        'block_index': block_index,
        'term_index': dict(term_index),
        'qa_index': {'items': qa_items},
        'dictation_index': {'items': dictation_items},
        'chart_index': {'items': chart_items},
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    books_to_process = list(range(1, 13))

    all_book_data = []
    for n in books_to_process:
        print(f'Processing Book {n}...', flush=True)
        bd = process_book(n)
        n_blocks = len(bd['blocks'])
        n_pages = len(bd['pages'])
        # Count QA and terms
        qa_count = sum(len(b.get('items', [])) for b in bd['blocks'] if b['type'] == 'qa_block')
        term_count = sum(len(b.get('terms', [])) for b in bd['blocks'] if b['type'] == 'lexical_block')
        print(f'  -> {n_pages} pages, {n_blocks} blocks, {qa_count} QA pairs, {term_count} terms')
        all_book_data.append(bd)

    print('\nBuilding indexes...', flush=True)
    indexes = build_indexes(all_book_data)

    # Write output files
    files = {
        'course-index.json': indexes['course_index'],
        'lesson-index.json': indexes['lesson_index'],
        'page-index.json': indexes['page_index'],
        'block-index.json': indexes['block_index'],
        'term-index.json': indexes['term_index'],
        'qa-index.json': indexes['qa_index'],
        'dictation-index.json': indexes['dictation_index'],
        'chart-index.json': indexes['chart_index'],
    }

    for fname, data in files.items():
        out_path = OUT_DIR / fname
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        size_kb = out_path.stat().st_size // 1024
        print(f'  Wrote {fname} ({size_kb} KB)')

    ci = indexes['course_index']
    print(f'\nDone. {ci["total_books"]} books, {ci["total_lessons"]} lessons, '
          f'{ci["total_blocks"]} blocks, {ci["total_terms"]} terms, '
          f'{ci["total_qa_pairs"]} Q&A pairs.')


if __name__ == '__main__':
    main()
