#!/usr/bin/env python3
"""
Convert Callan Method PDFs → Markdown using PyMuPDF (font-aware).

Font roles (confirmed from PDF inspection):
  FreeSet-Bold        → headings: LESSON N, STAGE N, Dictation
  FreeSet-DemiBold    → vocabulary terms
  FreeSet-Book        → questions (FreeSet-Book private encoding: chr+31, \x01=space)
  FreeSet-Light       → answers / body text
  FreeSet-LightOblique→ grammar notes / chart references
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import fitz  # PyMuPDF

# ── Decoder ───────────────────────────────────────────────────────────────────

_GLYPH = {
    '\x01':   ' ',      # inter-word space in FreeSet-Book encoding
    'ǽ': "'",      # ǽ
    'ǿ': "'",      # ǿ
    '‘': "'",      # LEFT SINGLE QUOTATION MARK
    '’': "'",      # RIGHT SINGLE QUOTATION MARK
    'ʝ': 'fi',     # ʝ
    'ʒ': 'fl',     # ʒ
    'ﬁ': 'fi',     # ﬁ ligature
    'ﬂ': 'fl',     # ﬂ ligature
    '“': '"',      # LEFT DOUBLE QUOTATION MARK
    '”': '"',      # RIGHT DOUBLE QUOTATION MARK
    '–': '-',      # EN DASH
    '—': '-',      # EM DASH
    # NOTE: do NOT include '"' (ord 34 = 0x22) here — it's the bottom of the
    # encoding range and decodes to 'A'.
}

_NUMBER_RE = re.compile(r'^[\d,.()£$€%+\-/: ]+$')
# These chars look lowercase to Python but are FreeSet-Book encoding artifacts, not real letters
_ENCODE_ARTIFACTS = frozenset('ǽǿʝʒ')

def _decode_char(c: str) -> str:
    if c in _GLYPH:
        return _GLYPH[c]
    o = ord(c)
    if 0x02 <= o <= 0x5B:
        decoded = chr(o + 31)
        return decoded if decoded.isprintable() else c
    return c

def _needs_decode(text: str) -> bool:
    """True if FreeSet-Book span has raw private encoding (not already mapped by PyMuPDF)."""
    if '\x01' in text:
        return True
    # Lowercase letters (excluding encoding artifacts like ʝ/ʒ which Python sees as lowercase)
    # mean PyMuPDF already decoded via ToUnicode. Return False BEFORE the control-char check
    # so that PyMuPDF artifacts like \x08 in decoded spans never trigger a re-decode.
    if any(c.islower() and c not in _ENCODE_ARTIFACTS for c in text):
        return False
    # '?' literal = span already decoded: raw FreeSet-Book encodes '?' as 0x20 (space), not 0x3F
    if '?' in text:
        return False
    # Control chars 0x02–0x1F indicate raw-encoded digits/punctuation (e.g. \x0e→'-')
    if any(0x02 <= ord(c) <= 0x1f for c in text):
        return True
    s = text.strip()
    if not s or len(s) < 3:
        return False
    # Digit/punctuation-only spans (number drills) stored as-is, not shift-encoded
    if _NUMBER_RE.match(s):
        return False
    in_range = sum(1 for c in s if 0x22 <= ord(c) <= 0x5B)
    return in_range / len(s) > 0.5

def decode_book_span(text: str) -> str:
    if _needs_decode(text):
        result = ''.join(_decode_char(c) for c in text)
        result = result.replace('\t', ' ').replace('\n', ' ')
    else:
        # Still apply GLYPH substitutions (ligatures, smart quotes) even in decoded spans
        result = ''.join(_GLYPH.get(c, c) for c in text)
        # Strip all control chars — they are PDF layout artifacts in already-decoded spans
        result = re.sub(r'[\x00-\x1f]', '', result)
    return re.sub(r'  +', ' ', result).strip()

# ── Span classifier ───────────────────────────────────────────────────────────

def span_role(font: str) -> str:
    # Books 11-12 use Arial-BoldMT for vocabulary terms (must check before 'Bold' HEAD branch)
    if font == 'Arial-BoldMT':
        return 'VOCAB'
    if 'DemiBold' in font:
        return 'VOCAB'
    if 'Bold' in font:          # FreeSet-Bold (not DemiBold/Arial-BoldMT)
        return 'HEAD'
    if 'Book' in font:
        return 'Q'
    if 'Oblique' in font or 'Italic' in font:
        return 'NOTE'
    if 'Light' in font or 'Regular' in font:
        return 'A'
    return 'OTHER'

# ── Page-number detector ──────────────────────────────────────────────────────

_PAGE_NUM_RE = re.compile(r'^\d{1,3}$')

def is_page_number(span: dict) -> bool:
    return span['bbox'][0] < 25 and _PAGE_NUM_RE.match(span['text'].strip())

# ── Regex helpers ─────────────────────────────────────────────────────────────

_LESSON_RE    = re.compile(r'^\s*LESSON\s*(\d+)\s*$', re.I)
_STAGE_RE     = re.compile(r'^\s*STAGE\s+\d+\s*$', re.I)
_DICTATION_RE = re.compile(r'^\s*Dictation\s*\d*\s*$', re.I)
_REVISION_RE  = re.compile(r'^\s*(?:Do\s+)?Revision\b', re.I)
_WORD_BUILD_RE= re.compile(r'^\s*Word-building', re.I)
# Internal vocabulary index lines: dots decoded via ToUnicode to 'M', page numbers to letters
_VOCAB_INDEX_DOTS_RE = re.compile(r'M{5,}|\.{5,}')

_VOCAB_IDX_RE = re.compile(
    r'(?:Chinese|Japanese|French|Spanish|German|Portuguese|Polish|Turkish|'
    r'Arabic|Korean|Italian|Russian|Czech|Slovak|Hungarian)\s+[Vv]ocabulary',
    re.I,
)

# ── Per-line extraction ───────────────────────────────────────────────────────

def process_line(line: dict) -> dict:
    """
    Return a dict describing one PDF line:
      type  : HEAD | Q | A | VOCAB | NOTE | SKIP
      text  : cleaned string
      inline_a : answer text on the same line as a Q (may be empty)
    """
    spans = [s for s in line['spans'] if not is_page_number(s) and s['text'].strip()]
    if not spans:
        return {'type': 'SKIP', 'text': '', 'inline_a': ''}

    by_role: dict[str, list] = {}
    for s in spans:
        r = span_role(s['font'])
        by_role.setdefault(r, []).append(s)

    # Headings override everything
    if 'HEAD' in by_role:
        text = ''.join(s['text'] for s in by_role['HEAD']).strip()
        return {'type': 'HEAD', 'text': text, 'inline_a': ''}

    # Q row (may have inline A)
    if 'Q' in by_role:
        # Decode each span individually — a line may mix raw-encoded and ToUnicode spans
        q_text = ''.join(decode_book_span(s['text']) for s in by_role['Q'])
        q_text = re.sub(r'  +', ' ', q_text).strip()
        # Inline A = Light spans on same line, to the right of the Q
        a_text = ''
        if 'A' in by_role:
            raw = ' '.join(s['text'].strip() for s in by_role['A'] if s['text'].strip())
            a_text = re.sub(r'[\x00-\x1f]', '', raw).strip()
        return {'type': 'Q', 'text': q_text, 'inline_a': a_text}

    # Grammar note (check before pure-A to avoid misclassifying mixed Oblique+Light lines)
    if 'NOTE' in by_role:
        parts = []
        for role in ('A', 'NOTE'):
            parts += [re.sub(r'[\x00-\x1f]', '', s['text']).strip()
                      for s in by_role.get(role, []) if s['text'].strip()]
        return {'type': 'NOTE', 'text': ' '.join(parts), 'inline_a': ''}

    # Pure answer / continuation
    if 'A' in by_role and 'VOCAB' not in by_role:
        raw  = ' '.join(s['text'].strip() for s in by_role['A'] if s['text'].strip())
        text = re.sub(r'[\x00-\x1f]', '', raw).strip()
        if text:
            return {'type': 'A', 'text': text, 'inline_a': ''}

    # Vocabulary
    if 'VOCAB' in by_role:
        terms = [re.sub(r'[\x00-\x1f]', '', s['text']).strip()
                 for s in by_role['VOCAB'] if s['text'].strip()]
        return {'type': 'VOCAB', 'text': '\t'.join(terms), 'inline_a': ''}

    return {'type': 'SKIP', 'text': '', 'inline_a': ''}

# ── Book parser ───────────────────────────────────────────────────────────────

def parse_pdf(pdf_path: Path) -> list[dict]:
    """
    Returns a list of lesson dicts:
      num        : int
      vocab      : list[str]
      qa_pairs   : list[(q_str, a_str)]
      notes      : list[str]
      dictations : list[str]
    """
    doc  = fitz.open(str(pdf_path))
    lessons: list[dict] = []
    cur: dict | None = None
    cur_q: str | None = None
    cur_a: list[str]  = []
    in_dictation = False
    dict_lines: list[str] = []
    finished = False

    def new_lesson(n: int):
        nonlocal cur, cur_q, cur_a, in_dictation, dict_lines
        _flush_qa(); _flush_dict()
        cur = {'num': n, 'vocab': [], 'qa_pairs': [], 'notes': [], 'dictations': []}
        lessons.append(cur)
        cur_q = None; cur_a = []
        in_dictation = False; dict_lines = []

    def _flush_qa():
        nonlocal cur_q, cur_a
        if cur_q and cur:
            q = cur_q.strip()
            a = ' '.join(cur_a).strip()
            if q:
                cur['qa_pairs'].append((q, a))
        cur_q = None; cur_a = []

    def _flush_dict():
        nonlocal dict_lines, in_dictation
        if dict_lines and cur:
            cur['dictations'].append(' '.join(dict_lines).strip())
        dict_lines = []; in_dictation = False

    for page in doc:
        if finished:
            break
        page_dict = page.get_text('dict', sort=True)

        for block in page_dict['blocks']:
            if finished or block['type'] != 0:
                continue

            for line in block['lines']:
                if finished:
                    break

                info = process_line(line)
                t    = info['type']
                text = info['text']

                if not text and t != 'Q':
                    continue

                # Stop at multilingual vocab index or internal vocabulary index (dots→M)
                if _VOCAB_IDX_RE.search(text) or _VOCAB_INDEX_DOTS_RE.search(text):
                    _flush_qa(); _flush_dict()
                    finished = True
                    break

                if t == 'HEAD':
                    m = _LESSON_RE.match(text)
                    if m:
                        new_lesson(int(m.group(1)))
                        continue
                    if _STAGE_RE.match(text) or _REVISION_RE.match(text) or _WORD_BUILD_RE.match(text):
                        _flush_qa()
                        continue
                    if _DICTATION_RE.match(text):
                        _flush_qa(); _flush_dict()
                        in_dictation = True
                        continue
                    # Other headings → treat as note
                    if cur:
                        _flush_qa()
                        cur['notes'].append(text)
                    continue

                if cur is None:
                    continue

                if in_dictation:
                    # End dictation when a Q line or structural marker appears
                    if t == 'Q' or _LESSON_RE.match(text) or _REVISION_RE.match(text):
                        _flush_dict()
                        if t == 'Q':
                            q_text = text
                            if q_text:
                                _flush_qa()
                                cur_q = q_text
                                cur_a = [info['inline_a']] if info['inline_a'] else []
                            elif info['inline_a'] and cur_q is not None:
                                cur_a.append(info['inline_a'])
                        elif _LESSON_RE.match(text):
                            m = _LESSON_RE.match(text)
                            new_lesson(int(m.group(1)))
                        # REVISION → just end dictation, continue
                    else:
                        if text:
                            dict_lines.append(text)
                    continue

                if t == 'Q':
                    q_text = text
                    if q_text:
                        # Continuation heuristic: genuine new Q's always start uppercase in English
                        is_cont = cur_q is not None and q_text[0].islower()
                        if is_cont:
                            cur_q = cur_q.rstrip().rstrip('?') + ' ' + q_text
                            if info['inline_a']:
                                cur_a.append(info['inline_a'])
                        else:
                            _flush_qa()
                            cur_q = q_text
                            cur_a = [info['inline_a']] if info['inline_a'] else []
                    elif info['inline_a'] and cur_q is not None:
                        # Empty Q span (just a \x01 spacer) followed by A on same visual row
                        cur_a.append(info['inline_a'])
                    continue

                if t == 'A':
                    if cur_q is not None:
                        cur_a.append(text)
                    elif cur['qa_pairs']:
                        lq, la = cur['qa_pairs'][-1]
                        cur['qa_pairs'][-1] = (lq, (la + ' ' + text).strip())
                    continue

                if t == 'VOCAB':
                    for term in text.split('\t'):
                        term = term.strip()
                        if not term:
                            continue
                        # FreeSet-DemiBold grammar explanation boxes in Books 11-12 are long
                        # sentences — route them to notes rather than vocabulary
                        if len(term) > 60 and (' ' in term[:30]):
                            cur['notes'].append(term)
                        elif len(term) < 80:
                            cur['vocab'].append(term)
                    continue

                if t == 'NOTE':
                    if _DICTATION_RE.match(text):
                        _flush_qa(); _flush_dict()
                        in_dictation = True
                    elif _REVISION_RE.match(text) or _WORD_BUILD_RE.match(text):
                        _flush_qa()
                    else:
                        _flush_qa()
                        if text:
                            cur['notes'].append(text)
                    continue

    _flush_qa(); _flush_dict()
    return lessons

# ── Markdown renderer ─────────────────────────────────────────────────────────

_CEFR = {
    1: 'A1 (beginner)',    2: 'A1–A2',
    3: 'A2',              4: 'A2–B1',
    5: 'B1',              6: 'B1–B2',
    7: 'B2',              8: 'B2–C1',
    9: 'C1',              10: 'C1–C2',
    11: 'C2',             12: 'C2',
}

def render_markdown(lessons: list[dict], book_num: int) -> str:
    cefr = _CEFR.get(book_num, '')
    out  = [
        f'# Callan Method — Book {book_num} (Stage {book_num})',
        '',
        f'> **CEFR level:** {cefr}',
        '> Each lesson introduces vocabulary through intensive Q&A drilling.',
        '',
        '---', '',
    ]

    for lesson in lessons:
        out += [f'## Lesson {lesson["num"]}', '']

        # Vocabulary (deduplicated)
        seen: set[str] = set()
        uniq: list[str] = []
        for v in lesson['vocab']:
            v = v.strip()
            if v and v not in seen:
                seen.add(v); uniq.append(v)
        if uniq:
            out.append('### Vocabulary')
            out += [f'- **{v}**' for v in uniq]
            out.append('')

        # Grammar notes
        note_seen: set[str] = set()
        good_notes = []
        for n in lesson['notes']:
            n = n.strip()
            if n and n not in note_seen and len(n) > 4:
                note_seen.add(n); good_notes.append(n)
        if good_notes:
            out.append('### Notes')
            _ctrl = re.compile('[\x00-\x1f]')
            out += [f'> {_ctrl.sub("", n)}' for n in good_notes]
            out.append('')

        # Q&A
        if lesson['qa_pairs']:
            out.append('### Q&A Drill')
            for q, a in lesson['qa_pairs']:
                q = q.strip()
                if not re.search(r'[a-zA-Z0-9]', q):  # skip artifact-only fragments
                    continue
                if not q.endswith('?'):
                    q += '?'
                a = re.sub(r'[\x00-\x1f]', '', a)
                a = re.sub(r'\s+', ' ', a).strip()
                out.append(f'**Q:** {q}')
                if a:
                    out.append(f'**A:** {a}')
                out.append('')

        # Dictations
        for d in lesson['dictations']:
            out.append('### Dictation')
            d = re.sub(r'[\x00-\x1f]', '', d).strip()
            out.append(f'> {d}')
            out.append('')

        out += ['---', '']

    return '\n'.join(out)

# ── Entry point ───────────────────────────────────────────────────────────────

PDF_DIR = Path('/Users/cuijianchen/gh-projects/kb-personal/callan-method-origin')
OUT_DIR = Path('/Users/cuijianchen/gh-projects/kb-personal/callan-method')

def convert_book(n: int, verbose: bool = True) -> list[dict]:
    pdf = PDF_DIR / f'Callan Method {n}.pdf'
    out = OUT_DIR  / f'book-{n}.md'

    if verbose:
        print(f'  Book {n} ({pdf.name})... ', end='', flush=True)

    lessons = parse_pdf(pdf)
    md      = render_markdown(lessons, n)
    out.write_text(md, encoding='utf-8')

    if verbose:
        total_q    = sum(len(l['qa_pairs'])   for l in lessons)
        total_v    = sum(len(l['vocab'])       for l in lessons)
        total_d    = sum(len(l['dictations'])  for l in lessons)
        print(f'{len(lessons)} lessons | {total_q} Q&A | {total_v} vocab | {total_d} dicts')

    return lessons

if __name__ == '__main__':
    books = [int(x) for x in sys.argv[1:]] if sys.argv[1:] else list(range(1, 13))
    print('Callan Method PDF → Markdown (PyMuPDF font-aware)\n')
    for n in books:
        convert_book(n)
    print('\nDone.')
