#!/usr/bin/env python3
"""
Convert Callan Method raw text (pdftotext -layout) to clean Markdown.

Column structure:
  Cols 0–52   : question / vocabulary (left column)
  Cols 53+    : answer text (right column)

Callan font (books 4 and parts of 8):
  Every printable ASCII char shifted +31.
  Encode range: 0x22–0x5B (34–91) → decoded 0x41–0x7A (A–z).
  \x01 (SOH) is used as the inter-word SPACE character in encoded questions.
  Special glyphs: ǽ→' ǿ→' ʝ→fi ﬁ→fi
"""

import re
from pathlib import Path

# ── Callan font decoder ───────────────────────────────────────────────────────

GLYPH_MAP = {
    '\x01': ' ',   # SOH = inter-word space in Callan font
    'ǽ': "'",
    'ǿ': "'",
    'ʝ': 'fi',
    'ʒ': 'fl',
    'ﬁ': 'fi',
    'ﬂ': 'fl',
    '‘': "'",  # LEFT SINGLE QUOTATION MARK
    '’': "'",  # RIGHT SINGLE QUOTATION MARK
    '“': '"',
    '”': '"',
    '–': '-',  # EN DASH
    '—': '-',  # EM DASH
}

ENCODE_LOW  = 0x22   # 34  = '"'
ENCODE_HIGH = 0x5B   # 91  = '['

def decode_char(c):
    if c in GLYPH_MAP:
        return GLYPH_MAP[c]
    o = ord(c)
    if ENCODE_LOW <= o <= ENCODE_HIGH:
        decoded = chr(o + 31)
        if decoded.isprintable():
            return decoded
    return c

def decode_callan(text):
    result = ''.join(decode_char(c) for c in text)
    # Collapse multiple spaces that may arise from consecutive \x01 or glyph expansions
    return re.sub(r'  +', ' ', result).strip()

def _encoded_score(text):
    """Return fraction of chars that belong to the Callan +31 font encoding."""
    s = text.strip()
    if not s:
        return 0.0
    ctrl   = sum(1 for c in s if c == '\x01')
    upper  = sum(1 for c in s if c.isupper())
    lower  = sum(1 for c in s if c.islower())
    glyphs = sum(1 for c in s if c in GLYPH_MAP and c != '\x01')
    total  = len(s)
    return (ctrl + upper + glyphs) / total, lower / total

def is_encoded_text(text):
    """True if this text is written in the Callan +31 custom font."""
    s = text.strip()
    if not s:
        return False
    # Short all-uppercase fragments or fragments with \x01
    if len(s) <= 4:
        if all(c.isupper() or c.isdigit() or c in GLYPH_MAP for c in s):
            return True
    if len(s) < 3:
        return False
    score, lower_frac = _encoded_score(s)
    return score > 0.55 and lower_frac < 0.15

def is_encoded_continuation(text, prev_q):
    """
    True if this encoded text is a continuation word appended to a multi-line
    question, rather than the start of a new question.

    In the Callan font:
      0x22–0x40 → A–Z (uppercase original → question starters)
      0x42–0x5B → a–z (lowercase original → continuation words like 'it', 'you')
    """
    if not prev_q:
        return False
    s = text.strip()
    if not s or not is_encoded_text(s):
        return False
    first = ord(s[0])
    # Starts with uppercase-decoded char (0x22–0x41 range) → new question
    if ENCODE_LOW <= first <= 0x41:
        return False
    # Starts with lowercase-decoded char (0x42–0x5B) → continuation
    if 0x42 <= first <= ENCODE_HIGH:
        return True
    return False

# ── Column splitter ───────────────────────────────────────────────────────────

_COL_RE = re.compile(r'(?<=\S)(\s{3,})(?=\S)')

def split_columns(text):
    """Return (left_stripped, right_stripped_or_None)."""
    m = _COL_RE.search(text)
    if m:
        left  = text[:m.start() + 1].strip()
        right = text[m.end():].strip()
        if right:
            return left, right
    return text.strip(), None

# ── Classifiers ───────────────────────────────────────────────────────────────

_QWORDS = (
    'what ', 'do ', 'does ', 'did ', 'is ', 'are ', 'was ', 'were ',
    'would ', 'will ', "won't ", "wouldn't ", 'can ', 'could ', 'should ',
    'have ', 'has ', 'had ', 'how ', 'when ', 'where ', 'who ', 'why ',
    'which ', 'if ', 'suppose', 'imagine ', 'tell me', 'name ',
    'give me', 'say ',
)

def is_question(text):
    s = text.strip()
    if not s:
        return False
    if s.endswith('?'):
        return True
    lo = s.lower()
    return any(lo.startswith(w) for w in _QWORDS)

_ANSWER_STARTS = (
    'yes,', 'no,', 'yes.', 'no.', 'yes!', 'no!',
    "i've", "i'd", "i'll", "i'm", "i was", "i have",
    "i don'", "i can'", "i won'", "i shouldn'",
    "i already", "i think", "i never", "i always",
    'we ', 'they ', 'he ', 'she ', 'it ', 'the ',
)

def is_vocab_word(text):
    s = text.strip()
    if not s or len(s) > 100:
        return False
    if len(s) <= 1:  # skip single chars
        return False
    if is_encoded_text(s):
        return False
    if is_question(s):
        return False
    if s.endswith(('.', '!', ',')):
        return False
    lo = s.lower()
    # Skip Dictation/Revision section markers
    if lo.startswith('dictation') or lo.startswith('do revision') or lo.startswith('revision'):
        return False
    if any(lo.startswith(a) for a in _ANSWER_STARTS):
        return False
    # Reject multi-word lines (unless they contain dashes = verb forms)
    if '–' not in s and ' - ' not in s and ' – ' not in s:
        words = s.split()
        if len(words) > 7:
            return False
    return True

def leading_spaces(line):
    return len(line) - len(line.lstrip(' '))

# ── Parser ────────────────────────────────────────────────────────────────────

def parse_book(raw_text, book_num):
    lines = raw_text.replace('\x0c', '\n').split('\n')

    sections         = []
    current          = None
    current_q        = None
    current_a        = []
    in_dictation     = False
    dict_lines       = []
    in_intro         = True
    saw_cefr_end     = False  # True after standalone 'A1' (end of CEFR table)
    finished         = False  # True once we hit the multilingual vocab index

    def new_lesson(num):
        nonlocal current, current_q, current_a, in_dictation, dict_lines
        flush_qa(); flush_dict()
        current = {'num': num, 'vocab': [], 'qa_pairs': [],
                   'grammar_notes': [], 'dictations': []}
        sections.append(current)
        current_q = None; current_a = []
        in_dictation = False; dict_lines = []

    def flush_qa():
        nonlocal current_q, current_a
        if current_q and current is not None:
            q = current_q.strip()
            a = ' '.join(current_a).strip()
            if q:
                current['qa_pairs'].append((q, a))
        current_q = None; current_a = []

    def flush_dict():
        nonlocal dict_lines, in_dictation
        if dict_lines and current is not None:
            current['dictations'].append(' '.join(dict_lines).strip())
        dict_lines = []; in_dictation = False

    def add_vocab_parts(text):
        """Extract vocab terms from a column-split text block."""
        # Split on long whitespace first, then on dashes
        for col_part in re.split(r'\s{3,}', text):
            for w in re.split(r'\s*[–\-]{1,2}\s*', col_part):
                w = w.strip()
                if w and len(w) < 70 and not is_encoded_text(w) and is_vocab_word(w):
                    current['vocab'].append(w)

    # Regex to detect the start of the multilingual vocabulary index
    _VOCAB_INDEX_RE = re.compile(
        r'\b(Chinese|Japanese|French|Spanish|German|Portuguese|Polish|Turkish|'
        r'Arabic|Korean|Italian|Russian|Czech|Slovak|Hungarian)\s+vocabulary\b',
        re.I,
    )

    for line in lines:
        if finished:
            break

        s    = line.strip()
        lead = leading_spaces(line)

        if not s:
            continue
        if re.match(r'^\s*\d{3}\s*$', line):  # bare page number
            continue

        # Detect multilingual vocabulary index → stop parsing
        if _VOCAB_INDEX_RE.search(s):
            flush_qa(); flush_dict()
            finished = True
            break

        # ── Structural / intro detection ──
        if re.match(r'^\s*STAGE\s+\d+\s*$', s):
            in_intro = False; continue

        if in_intro:
            # Detect end of CEFR comparison table (standalone 'A1' is the last row)
            if re.match(r'^\s*A1\s*$', s):
                saw_cefr_end = True
            # For books with no STAGE header before lessons (Books 1-3 etc.),
            # the first LESSON line after the CEFR table is real content.
            elif saw_cefr_end:
                m_lesson = re.match(r'^\s*LESSON\s+(\d+)\s*$', s)
                if m_lesson:
                    in_intro = False
                    new_lesson(int(m_lesson.group(1)))
                    continue
            continue

        m = re.match(r'^\s*LESSON\s+(\d+)\s*$', s)
        if m:
            new_lesson(int(m.group(1))); continue
        if current is None:
            continue

        # ── Dictation ──
        if re.match(r'^\s*Dictation\s+\d+\s*$', s):
            flush_qa(); flush_dict(); in_dictation = True; continue

        if in_dictation:
            if re.match(r'^\s*Do Revision Exercise', s):
                flush_dict(); continue
            m2 = re.match(r'LESSON\s+(\d+)', s)
            if m2:
                flush_dict(); new_lesson(int(m2.group(1))); continue
            if lead < 20:
                dict_lines.append(s)
            continue

        if re.match(r'^\s*Do Revision Exercise', s):
            flush_qa(); continue

        # ── Split into columns ──
        left, right = split_columns(line)

        # ── Lines starting with 3-digit page number ──
        if re.match(r'^\d{3}[\s\x01]', s):
            content       = re.sub(r'^\d{3}\s+', '', s)
            cleft, cright = split_columns(content)
            if is_encoded_text(cleft):
                # Q+A line with page-number prefix
                if is_encoded_continuation(cleft, current_q):
                    # Continuation of previous multi-line question
                    current_q = (current_q or '') + decode_callan(cleft)
                    if cright:
                        current_a.append(cright)
                else:
                    flush_qa()
                    current_q = decode_callan(cleft)
                    current_a = [cright] if cright else []
            else:
                flush_qa()
                add_vocab_parts(content)
            continue

        # ── Encoded left column ──
        if is_encoded_text(left):
            if is_encoded_continuation(left, current_q):
                # Append continuation word to ongoing question
                current_q = (current_q or '') + ' ' + decode_callan(left)
                if right:
                    current_a.append(right)
            else:
                flush_qa()
                current_q = decode_callan(left)
                current_a  = [right] if right else []
            continue

        # ── Pure answer continuation (deeply indented) ──
        if lead >= 25:
            if current_q is not None:
                current_a.append(s)
            elif current and current['qa_pairs']:
                lq, la = current['qa_pairs'][-1]
                current['qa_pairs'][-1] = (lq, (la + ' ' + s).strip())
            continue

        # ── Vocabulary (short, left-aligned, not a question) ──
        if lead < 15 and not is_question(left) and is_vocab_word(left):
            flush_qa()
            add_vocab_parts(left)
            if right and is_vocab_word(right):
                add_vocab_parts(right)
            continue

        # ── Plain English question ──
        if lead < 20 and is_question(left):
            flush_qa()
            current_q = left
            current_a  = [right] if right else []
            continue

        # ── Multi-line question continuation ──
        if current_q is not None and lead < 20:
            if not current_q.rstrip().endswith('?'):
                # Question still open → append
                current_q += ' ' + left
                if right:
                    current_a.append(right)
            else:
                # Question already closed → answer continuation
                current_a.append(s)
            continue

        # ── Mid-indentation answer ──
        if lead >= 15 and current_q is not None:
            current_a.append(s)
            continue

        # ── Fallthrough: grammar note ──
        flush_qa()
        if not is_encoded_text(s):
            current['grammar_notes'].append(s)

    flush_qa(); flush_dict()
    return sections


# ── Markdown renderer ─────────────────────────────────────────────────────────

STAGE_CEFR = {
    1:  'A1 (beginner)',
    2:  'A1–A2',
    3:  'A2',
    4:  'A2–B1 (approx. KET level)',
    5:  'B1 (approx. PET level)',
    6:  'B1–B2',
    7:  'B2 (approx. FCE level)',
    8:  'B2–C1 (FCE and above)',
    9:  'C1',
    10: 'C1–C2',
    11: 'C2 (approx. CPE level)',
    12: 'C2 (CPE)',
}

def render_markdown(sections, book_num):
    cefr = STAGE_CEFR.get(book_num, '')
    out = [
        f'# Callan Method — Book {book_num} (Stage {book_num})',
        '',
        f'> **CEFR level:** {cefr}',
        '> Each lesson introduces vocabulary through intensive Q&A drilling.',
        '',
        '---', '',
    ]

    for lesson in sections:
        out += [f'## Lesson {lesson["num"]}', '']

        if lesson['vocab']:
            seen, uniq = set(), []
            for v in lesson['vocab']:
                v = v.strip()
                if v and v not in seen and not is_encoded_text(v) and len(v) < 70:
                    seen.add(v); uniq.append(v)
            if uniq:
                out.append('### Vocabulary')
                out += [f'- **{v}**' for v in uniq]
                out.append('')

        if lesson['grammar_notes']:
            notes, seen = [], set()
            for n in lesson['grammar_notes']:
                n = n.strip()
                if n and n not in seen and not is_encoded_text(n) and len(n) > 8:
                    seen.add(n); notes.append(n)
            if notes:
                out.append('### Grammar Notes')
                out += notes
                out.append('')

        if lesson['qa_pairs']:
            out.append('### Q&A Drill')
            for q, a in lesson['qa_pairs']:
                q = q.strip()
                if is_encoded_text(q):
                    q = decode_callan(q)
                if not q.endswith('?'):
                    q += '?'
                # Collapse internal whitespace in answers (layout artefacts)
                a = re.sub(r'\s+', ' ', a).strip()
                out.append(f'**Q:** {q}')
                if a:
                    out.append(f'**A:** {a}')
                out.append('')

        if lesson['dictations']:
            out.append('### Dictation')
            out += [f'> {d}' for d in lesson['dictations']]
            out.append('')

        out += ['---', '']

    return '\n'.join(out)


# ── Entry point ───────────────────────────────────────────────────────────────

def convert_book(raw_path, out_path, book_num):
    print(f'  Book {book_num}... ', end='', flush=True)
    raw  = raw_path.read_text(encoding='utf-8', errors='replace')
    secs = parse_book(raw, book_num)
    md   = render_markdown(secs, book_num)
    out_path.write_text(md, encoding='utf-8')
    lessons = len(secs)
    vocab   = sum(len(s['vocab'])      for s in secs)
    qa      = sum(len(s['qa_pairs'])   for s in secs)
    dicts   = sum(len(s['dictations']) for s in secs)
    print(f'{lessons} lessons | {vocab} vocab | {qa} Q&A | {dicts} dictations')
    return secs

if __name__ == '__main__':
    base  = Path('/Users/cuijianchen/gh-projects/kb-personal/callan-method')
    books = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
    print('Converting Callan Method PDFs → Markdown\n')
    for n in books:
        raw = base / f'book{n}_raw.txt'
        out = base / f'book-{n}.md'
        if raw.exists():
            convert_book(raw, out, n)
        else:
            print(f'  Skipping Book {n}: raw file not found')
    print('\nDone.')
