#!/usr/bin/env python3
"""
Verify the converted Callan Method Markdown files.

Checks per-book:
  - Lesson count and range
  - Q&A pair count and % with answers
  - Vocab count
  - Dictation count
  - No garbled text (encoded chars in output)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

BASE = Path('/Users/cuijianchen/gh-projects/kb-personal/callan-method')

EXPECTED_LESSONS = {
    1: (1, 9),    2: (10, 24),  3: (25, 40),  4: (41, 60),
    5: (61, 77),  6: (78, 94),  7: (95, 111), 8: (112, 126),
    9: (127, 145),10: (146, 163),11:(164, 177),12:(178, 191),
}

_ENCODE_RESIDUE_RE = re.compile(r'[\x01-\x08\x0b\x0e-\x1f]|[ǽǿʝʒ]')
_GLYPH_LEAK_RE    = re.compile(r'\^')  # ^ means '?' was incorrectly decoded (space→'?')

def check_book(n: int) -> dict:
    path = BASE / f'book-{n}.md'
    text = path.read_text(encoding='utf-8')

    lessons_found = re.findall(r'^## Lesson (\d+)', text, re.M)
    lessons_found = [int(x) for x in lessons_found]
    lesson_set    = set(lessons_found)

    expected_start, expected_end = EXPECTED_LESSONS[n]
    expected_set = set(range(expected_start, expected_end + 1))

    missing  = sorted(expected_set - lesson_set)
    extra    = sorted(lesson_set - expected_set)

    q_lines = re.findall(r'^\*\*Q:\*\* (.+)$', text, re.M)
    a_lines = re.findall(r'^\*\*A:\*\* (.+)$', text, re.M)
    dicts   = re.findall(r'^### Dictation', text, re.M)
    vocabs  = re.findall(r'^- \*\*(.+?)\*\*', text, re.M)

    total_q = len(q_lines)
    total_a = len(a_lines)
    pct_with_a = round(100 * total_a / total_q, 1) if total_q else 0

    # Check for garbled text in Q lines
    garbled_q = [q for q in q_lines if _ENCODE_RESIDUE_RE.search(q) or _GLYPH_LEAK_RE.search(q)]

    ok = not missing and not extra and not garbled_q

    return {
        'book':        n,
        'lessons':     len(lessons_found),
        'missing':     missing,
        'extra':       extra,
        'qa_total':    total_q,
        'a_count':     total_a,
        'pct_with_a':  pct_with_a,
        'vocab':       len(vocabs),
        'dicts':       len(dicts),
        'garbled_q':   len(garbled_q),
        'garbled_ex':  garbled_q[:3],
        'ok':          ok,
    }

if __name__ == '__main__':
    books = [int(x) for x in sys.argv[1:]] if sys.argv[1:] else list(range(1, 13))
    all_ok = True

    print(f"{'Book':>4} {'Lessons':>7} {'Missing':>10} {'Q&A':>6} {'%A':>5} {'Vocab':>5} {'Dicts':>5} {'Garbled':>7} {'Status':>6}")
    print('-' * 70)

    for n in books:
        r = check_book(n)
        miss_str = str(r['missing'])[:20] if r['missing'] else '-'
        status   = 'OK' if r['ok'] else 'WARN'
        print(f"{r['book']:>4} {r['lessons']:>7} {miss_str:>10} {r['qa_total']:>6} {r['pct_with_a']:>5} {r['vocab']:>5} {r['dicts']:>5} {r['garbled_q']:>7} {status:>6}")

        if r['garbled_ex']:
            for ex in r['garbled_ex']:
                print(f"       GARBLED: {ex[:80]}")

        if not r['ok']:
            all_ok = False

    print('-' * 70)
    print(f"Overall: {'PASS' if all_ok else 'FAIL'}")
