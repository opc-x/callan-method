#!/usr/bin/env python3
"""
Validation script for the fine-grained Callan Method structured index.

Checks all 12 acceptance requirements from FINE_GRAINED_INDEX_ACCEPTANCE.md.
Run: /opt/homebrew/bin/python3 structured/validate_fine_index.py
Expected: PASS as last line.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

STRUCTURED_DIR = Path(__file__).resolve().parent

# ── Expected structure ────────────────────────────────────────────────────────

EXPECTED_LESSONS = {
    1: (1, 9), 2: (10, 24), 3: (25, 40), 4: (41, 60), 5: (61, 77),
    6: (78, 94), 7: (95, 111), 8: (112, 126), 9: (127, 145), 10: (146, 163),
    11: (164, 177), 12: (178, 191),
}
ALL_LESSONS = set(range(1, 192))  # 1..191

_RAW_ARTIFACT_RE = re.compile(r'[\x01-\x08\x0b\x0e-\x1f]|[ǽǿʝʒ]')
_VOCAB_IDX_RE = re.compile(
    r'(?:Chinese|Japanese|French|Spanish|German|Portuguese|Polish|Turkish|'
    r'Arabic|Korean|Italian|Russian|Czech|Slovak|Hungarian)\s+[Vv]ocabulary',
    re.I,
)
_VOCAB_INDEX_DOTS_RE = re.compile(r'M{5,}|\.{5,}')

# ── Load indexes ──────────────────────────────────────────────────────────────

def load_json(fname: str):
    path = STRUCTURED_DIR / fname
    if not path.exists():
        print(f'ERROR: {fname} not found at {path}')
        sys.exit(1)
    with open(path, encoding='utf-8') as f:
        return json.load(f)

def main():
    print('Loading indexes...', flush=True)
    course_index = load_json('course-index.json')
    lesson_index = load_json('lesson-index.json')
    page_index = load_json('page-index.json')
    block_index = load_json('block-index.json')
    term_index = load_json('term-index.json')
    qa_index = load_json('qa-index.json')
    dictation_index = load_json('dictation-index.json')
    chart_index = load_json('chart-index.json')
    print('All index files loaded.\n')

    results: list[tuple[str, str, str]] = []  # (check_num, status, message)

    def record(num: str, status: str, msg: str):
        results.append((num, status, msg))
        symbol = {'PASS': '✓', 'WARNING': '⚠', 'FAIL': '✗'}.get(status, '?')
        print(f'  [{symbol}] Check {num}: {status} — {msg}')

    # ── Check 1: All 12 books present ─────────────────────────────────────────
    books_in_index = {b['book'] for b in course_index.get('books', [])}
    missing_books = set(range(1, 13)) - books_in_index
    if missing_books:
        record('1', 'FAIL', f'Missing books: {sorted(missing_books)}')
    else:
        record('1', 'PASS', 'All 12 books present in course-index.json')

    # ── Check 2: Stages 1-12 present ─────────────────────────────────────────
    stages_in_index = {b['stage'] for b in course_index.get('books', [])}
    missing_stages = set(range(1, 13)) - stages_in_index
    if missing_stages:
        record('2', 'FAIL', f'Missing stages: {sorted(missing_stages)}')
    else:
        record('2', 'PASS', 'Stages 1-12 all present')

    # ── Check 3: Lessons 1-191 present in lesson-index ───────────────────────
    lessons_present = {int(k) for k in lesson_index.keys()}
    missing_lessons = ALL_LESSONS - lessons_present
    if missing_lessons:
        record('3', 'FAIL', f'Missing {len(missing_lessons)} lessons: {sorted(missing_lessons)[:20]}...')
    else:
        record('3', 'PASS', f'All 191 lessons present in lesson-index.json')

    # ── Check 4: Every lesson has at least one BookPage ───────────────────────
    lessons_no_pages = []
    for k, ld in lesson_index.items():
        if not ld.get('pdf_pages') and not ld.get('book_pages'):
            lessons_no_pages.append(int(k))
    # Also check pdf_pages non-empty
    lessons_no_pdf_pages = []
    for k, ld in lesson_index.items():
        if not ld.get('pdf_pages'):
            lessons_no_pdf_pages.append(int(k))

    if lessons_no_pdf_pages:
        record('4', 'FAIL', f'{len(lessons_no_pdf_pages)} lessons have no pdf_pages: {sorted(lessons_no_pdf_pages)[:10]}')
    else:
        record('4', 'PASS', 'Every lesson has at least one pdf_page')

    # ── Check 5: Every BookPage has book_page and pdf_page ────────────────────
    pages_missing_fields = []
    for pg_key, pg in page_index.items():
        if pg.get('pdf_page') is None:
            pages_missing_fields.append((pg_key, 'pdf_page'))
        # book_page can be None for front matter — only check content pages
        # We check that lessons have book_pages below via lesson_index
    # Count lesson pages without book_page
    lesson_pages_no_book_page = 0
    lesson_pages_total = 0
    for pg_key, pg in page_index.items():
        if pg.get('lesson') is not None:
            lesson_pages_total += 1
            if pg.get('book_page') is None:
                lesson_pages_no_book_page += 1

    if pages_missing_fields:
        record('5', 'FAIL', f'{len(pages_missing_fields)} pages missing pdf_page')
    elif lesson_pages_no_book_page > lesson_pages_total * 0.2:
        record('5', 'WARNING', f'{lesson_pages_no_book_page}/{lesson_pages_total} lesson pages missing book_page (>{20}%)')
    else:
        record('5', 'PASS', f'Pages have pdf_page; {lesson_pages_no_book_page}/{lesson_pages_total} missing book_page (<20% threshold)')

    # ── Check 6: Every ContentBlock has required fields ───────────────────────
    required_fields = ['block_id', 'type', 'book', 'stage', 'lesson', 'book_page', 'pdf_page']
    blocks_missing = []
    blocks_none_pdf = []
    blocks_none_lesson = 0

    for bid, blk in block_index.items():
        missing = [f for f in required_fields if f not in blk]
        if missing:
            blocks_missing.append((bid, missing))
        if blk.get('pdf_page') is None:
            blocks_none_pdf.append(bid)
        if blk.get('lesson') is None:
            blocks_none_lesson += 1

    if blocks_missing:
        record('6', 'FAIL', f'{len(blocks_missing)} blocks missing required fields (first: {blocks_missing[0]})')
    elif blocks_none_pdf:
        record('6', 'FAIL', f'{len(blocks_none_pdf)} blocks have None pdf_page')
    elif blocks_none_lesson > len(block_index) * 0.05:
        record('6', 'WARNING', f'{blocks_none_lesson} blocks have None lesson (front_matter expected)')
    else:
        record('6', 'PASS', f'All {len(block_index)} blocks have required fields ({blocks_none_lesson} front_matter with None lesson)')

    # ── Check 7: Every term points to existing block_id ──────────────────────
    bad_term_refs = 0
    total_term_entries = 0
    for norm_term, entries in term_index.items():
        for entry in entries:
            total_term_entries += 1
            bid = entry.get('block_id')
            if bid not in block_index:
                bad_term_refs += 1

    if bad_term_refs:
        record('7', 'FAIL', f'{bad_term_refs}/{total_term_entries} term entries point to non-existent block_id')
    else:
        record('7', 'PASS', f'All {total_term_entries} term entries point to valid block_ids')

    # ── Check 8: Every Q&A item points to existing block_id ──────────────────
    bad_qa_refs = 0
    qa_items = qa_index.get('items', [])
    for item in qa_items:
        bid = item.get('block_id')
        if bid not in block_index:
            bad_qa_refs += 1

    if bad_qa_refs:
        record('8', 'FAIL', f'{bad_qa_refs}/{len(qa_items)} Q&A items point to non-existent block_id')
    else:
        record('8', 'PASS', f'All {len(qa_items)} Q&A items point to valid block_ids')

    # ── Check 9: No raw artifacts in indexed text ─────────────────────────────
    artifact_count = 0
    artifact_examples = []

    def check_text_artifacts(text: str, context: str) -> bool:
        if _RAW_ARTIFACT_RE.search(text):
            return True
        return False

    # Check blocks
    for bid, blk in block_index.items():
        text = blk.get('text', '')
        if text and check_text_artifacts(text, bid):
            artifact_count += 1
            if len(artifact_examples) < 3:
                artifact_examples.append((bid, repr(text[:80])))
        # Check items
        for item in blk.get('items', []):
            for field in ('question', 'answer'):
                t = item.get(field, '')
                if t and check_text_artifacts(t, f'{bid}.{field}'):
                    artifact_count += 1
                    if len(artifact_examples) < 3:
                        artifact_examples.append((bid, field, repr(t[:80])))
        # Check terms
        for term in blk.get('terms', []):
            if term and check_text_artifacts(term, f'{bid}.term'):
                artifact_count += 1
                if len(artifact_examples) < 3:
                    artifact_examples.append((bid, 'term', repr(term[:80])))

    # Check term-index
    for norm, entries in term_index.items():
        for e in entries:
            t = e.get('term', '')
            if t and check_text_artifacts(t, f'term:{norm}'):
                artifact_count += 1
                if len(artifact_examples) < 3:
                    artifact_examples.append(('term', norm, repr(t[:80])))

    if artifact_count:
        record('9', 'FAIL', f'{artifact_count} raw artifacts found. Examples: {artifact_examples[:2]}')
    else:
        record('9', 'PASS', 'No raw artifacts found in indexed text')

    # ── Check 10: No vocabulary-index content in lesson blocks ────────────────
    vocab_idx_contamination = []
    for bid, blk in block_index.items():
        if blk.get('type') in ('front_matter', 'back_matter', 'vocabulary_index'):
            continue
        text = blk.get('text', '')
        if text and (_VOCAB_IDX_RE.search(text) or _VOCAB_INDEX_DOTS_RE.search(text)):
            vocab_idx_contamination.append(bid)
        for item in blk.get('items', []):
            for field in ('question', 'answer'):
                t = item.get(field, '')
                if t and (_VOCAB_IDX_RE.search(t) or _VOCAB_INDEX_DOTS_RE.search(t)):
                    vocab_idx_contamination.append(f'{bid}.{field}')
        for term in blk.get('terms', []):
            if term and (_VOCAB_IDX_RE.search(term) or _VOCAB_INDEX_DOTS_RE.search(term)):
                vocab_idx_contamination.append(f'{bid}.term:{term[:30]}')

    if vocab_idx_contamination:
        record('10', 'FAIL', f'{len(vocab_idx_contamination)} blocks have vocab-index contamination: {vocab_idx_contamination[:3]}')
    else:
        record('10', 'PASS', 'No vocabulary-index contamination in lesson blocks')

    # ── Check 11: BookPage numbers mostly monotonic within each book ──────────
    violations_by_book: dict[int, int] = {}
    totals_by_book: dict[int, int] = {}

    for book_num in range(1, 13):
        # Collect (pdf_page, book_page) pairs for this book, sorted by pdf_page
        pairs = []
        for pg_key, pg in page_index.items():
            if pg.get('book') == book_num and pg.get('book_page') is not None and pg.get('lesson') is not None:
                pairs.append((pg['pdf_page'], pg['book_page']))
        pairs.sort(key=lambda x: x[0])  # sort by pdf_page

        violations = 0
        for i in range(1, len(pairs)):
            if pairs[i][1] < pairs[i-1][1]:
                violations += 1

        violations_by_book[book_num] = violations
        totals_by_book[book_num] = max(len(pairs) - 1, 1)

    total_violations = sum(violations_by_book.values())
    total_transitions = sum(totals_by_book.values())
    violation_pct = total_violations / max(total_transitions, 1) * 100

    bad_books = [b for b in range(1, 13) if violations_by_book[b] / totals_by_book[b] > 0.1]
    if bad_books:
        record('11', 'WARNING', f'Books {bad_books} have >10% book_page monotonicity violations '
               f'({total_violations}/{total_transitions} = {violation_pct:.1f}% overall)')
    else:
        record('11', 'PASS', f'BookPage numbers mostly monotonic ({total_violations}/{total_transitions} = {violation_pct:.1f}% violations)')

    # ── Check 12: PDF page numbers monotonic within each book ─────────────────
    pdf_violations_by_book: dict[int, list] = {}

    for book_num in range(1, 13):
        pages_for_book = sorted(
            [pg['pdf_page'] for pg in page_index.values() if pg.get('book') == book_num],
        )
        violations = []
        for i in range(1, len(pages_for_book)):
            if pages_for_book[i] <= pages_for_book[i-1]:
                violations.append((pages_for_book[i-1], pages_for_book[i]))
        # pdf pages should be strictly increasing (unique)
        if len(pages_for_book) != len(set(pages_for_book)):
            # duplicates = non-monotonic
            pass
        pdf_violations_by_book[book_num] = violations

    books_with_pdf_violations = [b for b, v in pdf_violations_by_book.items() if v]
    if books_with_pdf_violations:
        details = {b: pdf_violations_by_book[b][:3] for b in books_with_pdf_violations}
        record('12', 'FAIL', f'PDF page non-monotonicity in books {books_with_pdf_violations}: {details}')
    else:
        record('12', 'PASS', 'PDF page numbers are monotonic within each book')

    # ── Check 13: Block IDs are unique and course totals match ──────────────
    declared_blocks = course_index.get('total_blocks')
    if declared_blocks != len(block_index):
        record('13', 'FAIL', f'course-index total_blocks={declared_blocks}, but block-index has {len(block_index)} blocks; possible block_id overwrite')
    else:
        record('13', 'PASS', f'course-index total_blocks matches block-index ({len(block_index)} blocks)')

    # ── Check 14: Dictations are explicitly modeled ─────────────────────────
    dictation_items = dictation_index.get('items', [])
    dictation_blocks = [bid for bid, blk in block_index.items() if blk.get('type') == 'dictation']
    bad_dict_refs = [d.get('block_id') for d in dictation_items if d.get('block_id') not in block_index]
    empty_dictations = [d.get('block_id') for d in dictation_items if not d.get('text', '').strip()]

    if not dictation_items or not dictation_blocks:
        record('14', 'FAIL', 'Dictations are present in source books but dictation-index/block type is empty')
    elif bad_dict_refs:
        record('14', 'FAIL', f'{len(bad_dict_refs)} dictations point to missing block_id')
    elif empty_dictations:
        record('14', 'FAIL', f'{len(empty_dictations)} dictation entries have empty text')
    elif len(dictation_items) < 120:
        record('14', 'WARNING', f'Only {len(dictation_items)} dictations modeled; expected roughly 130')
    else:
        record('14', 'PASS', f'{len(dictation_items)} dictations explicitly modeled')

    # ── Check 15: Chart references/pages are explicitly modeled ─────────────
    chart_items = chart_index.get('items', [])
    chart_ref_blocks = [bid for bid, blk in block_index.items() if blk.get('type') == 'chart_reference']
    chart_page_blocks = [bid for bid, blk in block_index.items() if blk.get('type') == 'chart_page']
    bad_chart_refs = [c.get('block_id') for c in chart_items if c.get('block_id') not in block_index]

    if bad_chart_refs:
        record('15', 'FAIL', f'{len(bad_chart_refs)} chart items point to missing block_id')
    elif not chart_ref_blocks:
        record('15', 'FAIL', 'Chart references are present in source books but no chart_reference blocks were created')
    elif not chart_page_blocks:
        record('15', 'WARNING', f'{len(chart_ref_blocks)} chart references modeled, but chart pages are not modeled')
    else:
        record('15', 'PASS', f'{len(chart_ref_blocks)} chart references and {len(chart_page_blocks)} chart pages modeled')

    # ── Summary ───────────────────────────────────────────────────────────────
    print()
    fail_count = sum(1 for _, s, _ in results if s == 'FAIL')
    warn_count = sum(1 for _, s, _ in results if s == 'WARNING')
    pass_count = sum(1 for _, s, _ in results if s == 'PASS')

    print(f'Results: {pass_count} PASS, {warn_count} WARNING, {fail_count} FAIL')
    print()

    # Additional stats
    print('Index statistics:')
    print(f'  course-index: {len(course_index.get("books", []))} books')
    print(f'  lesson-index: {len(lesson_index)} lessons')
    print(f'  page-index:   {len(page_index)} pages')
    print(f'  block-index:  {len(block_index)} blocks')
    print(f'  term-index:   {sum(len(v) for v in term_index.values())} term entries, {len(term_index)} unique terms')
    print(f'  qa-index:     {len(qa_items)} Q&A pairs')
    print(f'  dictation-index: {len(dictation_index.get("items", []))} dictations')
    print(f'  chart-index:  {len(chart_index.get("items", []))} chart refs/pages')
    print()

    # 36-lesson cross-check (first/middle/last from each book)
    print('36-lesson cross-check (first/middle/last per book):')
    sample_issues = 0
    for book_num in range(1, 13):
        lr = EXPECTED_LESSONS[book_num]
        mid = (lr[0] + lr[1]) // 2
        sample_lessons = [lr[0], mid, lr[1]]
        for lesson_num in sample_lessons:
            k = str(lesson_num)
            if k not in lesson_index:
                print(f'  MISSING: Book {book_num} Lesson {lesson_num}')
                sample_issues += 1
                continue
            ld = lesson_index[k]
            ok = True
            issues = []
            if not ld.get('pdf_pages'):
                issues.append('no pdf_pages')
                ok = False
            if not ld.get('book_pages'):
                issues.append('no book_pages')
            if not ld.get('block_ids'):
                issues.append('no block_ids')
                ok = False
            has_qa = ld.get('qa_count', 0) > 0
            has_terms = ld.get('term_count', 0) > 0
            if not has_qa:
                issues.append('no QA')
            if issues:
                status_str = 'WARNING' if ok else 'FAIL'
                print(f'  {status_str}: Book {book_num} Lesson {lesson_num}: {", ".join(issues)}')
                if not ok:
                    sample_issues += 1
            # else silent pass

    if sample_issues == 0:
        print('  All 36 sampled lessons OK')
    print()

    if fail_count == 0:
        print('PASS')
    else:
        print(f'FAIL ({fail_count} checks failed)')


if __name__ == '__main__':
    main()
