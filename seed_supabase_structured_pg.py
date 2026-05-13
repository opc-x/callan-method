#!/usr/bin/env python3
"""
Seed the fine-grained Callan Method structured index through a direct Postgres URL.

Required environment:
  POSTGRES_URL or POSTGRES_URL_NON_POOLING

This is preferred for bulk imports because it does not depend on Supabase REST keys.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parent
STRUCTURED = ROOT / 'structured'


def load_json(name: str) -> Any:
    return json.loads((STRUCTURED / name).read_text(encoding='utf-8'))


def many(cur: psycopg.Cursor, sql: str, rows: list[tuple]):
    if rows:
        cur.executemany(sql, rows)


def main():
    url = os.environ.get('POSTGRES_URL_NON_POOLING') or os.environ.get('POSTGRES_URL')
    if not url:
        raise SystemExit('Set POSTGRES_URL_NON_POOLING or POSTGRES_URL before running.')

    course = load_json('course-index.json')
    lessons = load_json('lesson-index.json')
    pages = load_json('page-index.json')
    blocks = load_json('block-index.json')
    terms = load_json('term-index.json')
    qa = load_json('qa-index.json')
    charts = load_json('chart-index.json')

    with psycopg.connect(url, autocommit=False) as conn:
        with conn.cursor() as cur:
            print('Clearing static content tables...')
            cur.execute("""
                truncate table
                  public.chart_refs,
                  public.exercises,
                  public.notes,
                  public.qa_pairs,
                  public.terms,
                  public.content_blocks,
                  public.book_pages,
                  public.lessons,
                  public.books
                restart identity cascade
            """)

            print('Inserting books...')
            book_rows = []
            for b in course['books']:
                lr = b['lesson_range']
                book_rows.append((
                    b['book'],
                    b['stage'],
                    b['cefr'],
                    f'Callan Method Stage {b["stage"]}',
                    b['pdf'],
                    lr[0],
                    lr[1],
                ))
            many(cur, """
                insert into public.books
                  (book_num, stage, cefr_level, title, source_pdf, lesson_start, lesson_end)
                values (%s,%s,%s,%s,%s,%s,%s)
            """, book_rows)
            cur.execute('select id, book_num from public.books')
            book_id = {book_num: id_ for id_, book_num in cur.fetchall()}

            print('Inserting lessons...')
            lesson_rows = []
            book_cefr = {b['book']: b['cefr'] for b in course['books']}
            for ld in lessons.values():
                pdf_pages = ld.get('pdf_pages') or []
                book_pages = ld.get('book_pages') or []
                b = ld['book']
                lesson_rows.append((
                    book_id[b],
                    b,
                    ld['stage'],
                    ld['lesson'],
                    book_cefr[b],
                    min(pdf_pages) if pdf_pages else None,
                    max(pdf_pages) if pdf_pages else None,
                    min(book_pages) if book_pages else None,
                    max(book_pages) if book_pages else None,
                    len(ld.get('block_ids') or []),
                    ld.get('term_count', 0),
                    ld.get('qa_count', 0),
                ))
            many(cur, """
                insert into public.lessons
                  (book_id, book_num, stage, lesson_num, cefr_level,
                   pdf_page_start, pdf_page_end, book_page_start, book_page_end,
                   block_count, term_count, qa_count)
                values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, lesson_rows)
            cur.execute('select id, lesson_num from public.lessons')
            lesson_id = {lesson_num: id_ for id_, lesson_num in cur.fetchall()}

            print('Inserting book_pages...')
            page_rows = []
            for pg in pages.values():
                b = pg['book']
                lesson_num = pg.get('lesson')
                block_ids = pg.get('block_ids') or []
                page_kind = 'front_matter' if lesson_num is None else 'content'
                if any(blocks[bid]['type'] == 'chart_page' for bid in block_ids if bid in blocks):
                    page_kind = 'chart_page'
                page_rows.append((
                    book_id[b],
                    lesson_id.get(lesson_num),
                    b,
                    b,
                    lesson_num,
                    pg['pdf_page'],
                    pg.get('book_page'),
                    page_kind,
                    block_ids,
                ))
            many(cur, """
                insert into public.book_pages
                  (book_id, lesson_id, book_num, stage, lesson_num, pdf_page, book_page, page_kind, block_ids)
                values (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, page_rows)
            cur.execute('select id, book_num, pdf_page from public.book_pages')
            page_id = {(book_num, pdf_page): id_ for id_, book_num, pdf_page in cur.fetchall()}

            print('Inserting content_blocks...')
            block_rows = []
            for bid, blk in blocks.items():
                b = blk['book']
                lesson_num = blk.get('lesson')
                metadata = {k: blk[k] for k in ('items', 'terms', 'title', 'chart_label') if k in blk}
                block_rows.append((
                    bid,
                    book_id[b],
                    lesson_id.get(lesson_num),
                    page_id.get((b, blk['pdf_page'])),
                    b,
                    blk['stage'],
                    lesson_num,
                    blk['pdf_page'],
                    blk.get('book_page'),
                    blk['type'],
                    blk.get('text', ''),
                    Jsonb(blk.get('source') or {}),
                    Jsonb(metadata),
                ))
            many(cur, """
                insert into public.content_blocks
                  (id, book_id, lesson_id, book_page_id, book_num, stage, lesson_num,
                   pdf_page, book_page, block_type, text, source, metadata)
                values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, block_rows)

            print('Inserting terms...')
            term_rows = []
            for entries in terms.values():
                for pos, entry in enumerate(entries, 1):
                    b = entry['book']
                    lesson_num = entry.get('lesson')
                    term_rows.append((
                        entry['block_id'],
                        book_id[b],
                        lesson_id.get(lesson_num),
                        page_id.get((b, entry['pdf_page'])),
                        entry['term'],
                        entry['normalized'],
                        'vocabulary',
                        b,
                        entry['stage'],
                        lesson_num,
                        entry['pdf_page'],
                        entry.get('book_page'),
                        pos,
                        Jsonb({'block_type': entry.get('block_type')}),
                    ))
            many(cur, """
                insert into public.terms
                  (block_id, book_id, lesson_id, book_page_id, term, normalized, term_type,
                   book_num, stage, lesson_num, pdf_page, book_page, position, metadata)
                values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, term_rows)

            print('Inserting qa_pairs...')
            qa_rows = []
            for item in qa.get('items', []):
                b = item['book']
                lesson_num = item.get('lesson')
                qa_rows.append((
                    item['block_id'],
                    book_id[b],
                    lesson_id.get(lesson_num),
                    page_id.get((b, item['pdf_page'])),
                    b,
                    item['stage'],
                    lesson_num,
                    item['pdf_page'],
                    item.get('book_page'),
                    item['pair_index'],
                    item['question'],
                    item.get('answer'),
                    'drill',
                ))
            many(cur, """
                insert into public.qa_pairs
                  (block_id, book_id, lesson_id, book_page_id, book_num, stage, lesson_num,
                   pdf_page, book_page, pair_index, question, answer, qa_type)
                values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, qa_rows)

            print('Inserting notes and exercises...')
            note_rows = []
            exercise_rows = []
            exercise_types = {'dictation', 'revision_exercise', 'word_building_exercise', 'phrase_exercise', 'reading_exercise'}
            for bid, blk in blocks.items():
                b = blk['book']
                lesson_num = blk.get('lesson')
                common = (
                    bid,
                    book_id[b],
                    lesson_id.get(lesson_num),
                    page_id.get((b, blk['pdf_page'])),
                    b,
                    blk['stage'],
                    lesson_num,
                    blk['pdf_page'],
                    blk.get('book_page'),
                )
                if blk['type'] == 'grammar_note':
                    note_rows.append((*common, 'grammar', blk.get('text', '')))
                elif blk['type'] in exercise_types:
                    exercise_rows.append((
                        *common,
                        blk['type'].replace('_exercise', ''),
                        blk.get('title'),
                        blk.get('text', ''),
                        Jsonb({k: blk[k] for k in ('items', 'terms') if k in blk}),
                    ))
            many(cur, """
                insert into public.notes
                  (block_id, book_id, lesson_id, book_page_id, book_num, stage, lesson_num,
                   pdf_page, book_page, note_type, text)
                values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, note_rows)
            many(cur, """
                insert into public.exercises
                  (block_id, book_id, lesson_id, book_page_id, book_num, stage, lesson_num,
                   pdf_page, book_page, exercise_type, title, text, metadata)
                values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, exercise_rows)

            print('Inserting chart_refs...')
            chart_rows = []
            for item in charts.get('items', []):
                b = item['book']
                lesson_num = item.get('lesson')
                chart_rows.append((
                    item['block_id'],
                    book_id[b],
                    lesson_id.get(lesson_num),
                    page_id.get((b, item['pdf_page'])),
                    item.get('chart_label'),
                    item['type'],
                    item['text'],
                    b,
                    item['stage'],
                    lesson_num,
                    item['pdf_page'],
                    item.get('book_page'),
                ))
            many(cur, """
                insert into public.chart_refs
                  (block_id, book_id, lesson_id, book_page_id, chart_label, ref_type, text,
                   book_num, stage, lesson_num, pdf_page, book_page)
                values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, chart_rows)

        conn.commit()

    print('Seed complete.')


if __name__ == '__main__':
    main()
