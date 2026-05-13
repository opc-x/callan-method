#!/usr/bin/env python3
"""
Seed the fine-grained Callan Method structured index through Supabase REST.

Required environment:
  SUPABASE_URL
  SUPABASE_SEED_KEY

The target database must already have temporary anon seed policies if
SUPABASE_SEED_KEY is an anon/publishable key. Use only for controlled imports.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from supabase import create_client

ROOT = Path(__file__).resolve().parent
STRUCTURED = ROOT / 'structured'
BATCH = 500


def load_json(name: str) -> Any:
    return json.loads((STRUCTURED / name).read_text(encoding='utf-8'))


def chunks(rows: list[dict], size: int = BATCH):
    for i in range(0, len(rows), size):
        yield rows[i:i + size]


def insert_many(client, table: str, rows: list[dict]):
    for chunk in chunks(rows):
        client.table(table).insert(chunk).execute()


def select_all(client, table: str, columns: str) -> list[dict]:
    out: list[dict] = []
    start = 0
    size = 1000
    while True:
        rows = client.table(table).select(columns).range(start, start + size - 1).execute().data or []
        out.extend(rows)
        if len(rows) < size:
            return out
        start += size


def main():
    url = os.environ.get('SUPABASE_URL')
    key = os.environ.get('SUPABASE_SEED_KEY')
    if not url or not key:
        raise SystemExit('Set SUPABASE_URL and SUPABASE_SEED_KEY before running.')

    client = create_client(url, key)

    course = load_json('course-index.json')
    lessons = load_json('lesson-index.json')
    pages = load_json('page-index.json')
    blocks = load_json('block-index.json')
    terms = load_json('term-index.json')
    qa = load_json('qa-index.json')
    charts = load_json('chart-index.json')

    print('Seeding books...')
    book_rows = []
    for b in course['books']:
        lr = b['lesson_range']
        book_rows.append({
            'book_num': b['book'],
            'stage': b['stage'],
            'cefr_level': b['cefr'],
            'title': f'Callan Method Stage {b["stage"]}',
            'source_pdf': b['pdf'],
            'lesson_start': lr[0],
            'lesson_end': lr[1],
        })
    insert_many(client, 'books', book_rows)
    book_id = {r['book_num']: r['id'] for r in select_all(client, 'books', 'id,book_num')}

    print('Seeding lessons...')
    book_cefr = {b['book']: b['cefr'] for b in course['books']}
    lesson_rows = []
    for ld in lessons.values():
        pdf_pages = ld.get('pdf_pages') or []
        book_pages = ld.get('book_pages') or []
        b = ld['book']
        lesson_rows.append({
            'book_id': book_id[b],
            'book_num': b,
            'stage': ld['stage'],
            'lesson_num': ld['lesson'],
            'cefr_level': book_cefr[b],
            'pdf_page_start': min(pdf_pages) if pdf_pages else None,
            'pdf_page_end': max(pdf_pages) if pdf_pages else None,
            'book_page_start': min(book_pages) if book_pages else None,
            'book_page_end': max(book_pages) if book_pages else None,
            'block_count': len(ld.get('block_ids') or []),
            'term_count': ld.get('term_count', 0),
            'qa_count': ld.get('qa_count', 0),
        })
    insert_many(client, 'lessons', lesson_rows)
    lesson_id = {r['lesson_num']: r['id'] for r in select_all(client, 'lessons', 'id,lesson_num')}

    print('Seeding book_pages...')
    page_rows = []
    for pg in pages.values():
        b = pg['book']
        lesson_num = pg.get('lesson')
        block_ids = pg.get('block_ids') or []
        page_kind = 'front_matter' if lesson_num is None else 'content'
        if any(blocks[bid]['type'] == 'chart_page' for bid in block_ids if bid in blocks):
            page_kind = 'chart_page'
        page_rows.append({
            'book_id': book_id[b],
            'lesson_id': lesson_id.get(lesson_num),
            'book_num': b,
            'stage': b,
            'lesson_num': lesson_num,
            'pdf_page': pg['pdf_page'],
            'book_page': pg.get('book_page'),
            'page_kind': page_kind,
            'block_ids': block_ids,
        })
    insert_many(client, 'book_pages', page_rows)
    page_id = {(r['book_num'], r['pdf_page']): r['id'] for r in select_all(client, 'book_pages', 'id,book_num,pdf_page')}

    print('Seeding content_blocks...')
    block_rows = []
    for bid, blk in blocks.items():
        b = blk['book']
        lesson_num = blk.get('lesson')
        metadata = {k: blk[k] for k in ('items', 'terms', 'title', 'chart_label') if k in blk}
        block_rows.append({
            'id': bid,
            'book_id': book_id[b],
            'lesson_id': lesson_id.get(lesson_num),
            'book_page_id': page_id.get((b, blk['pdf_page'])),
            'book_num': b,
            'stage': blk['stage'],
            'lesson_num': lesson_num,
            'pdf_page': blk['pdf_page'],
            'book_page': blk.get('book_page'),
            'block_type': blk['type'],
            'text': blk.get('text', ''),
            'source': blk.get('source') or {},
            'metadata': metadata,
        })
    insert_many(client, 'content_blocks', block_rows)

    print('Seeding terms...')
    term_rows = []
    for entries in terms.values():
        for pos, entry in enumerate(entries, 1):
            b = entry['book']
            lesson_num = entry.get('lesson')
            term_rows.append({
                'block_id': entry['block_id'],
                'book_id': book_id[b],
                'lesson_id': lesson_id.get(lesson_num),
                'book_page_id': page_id.get((b, entry['pdf_page'])),
                'term': entry['term'],
                'normalized': entry['normalized'],
                'term_type': 'vocabulary',
                'book_num': b,
                'stage': entry['stage'],
                'lesson_num': lesson_num,
                'pdf_page': entry['pdf_page'],
                'book_page': entry.get('book_page'),
                'position': pos,
                'metadata': {'block_type': entry.get('block_type')},
            })
    insert_many(client, 'terms', term_rows)

    print('Seeding qa_pairs...')
    qa_rows = []
    for item in qa.get('items', []):
        b = item['book']
        lesson_num = item.get('lesson')
        qa_rows.append({
            'block_id': item['block_id'],
            'book_id': book_id[b],
            'lesson_id': lesson_id.get(lesson_num),
            'book_page_id': page_id.get((b, item['pdf_page'])),
            'book_num': b,
            'stage': item['stage'],
            'lesson_num': lesson_num,
            'pdf_page': item['pdf_page'],
            'book_page': item.get('book_page'),
            'pair_index': item['pair_index'],
            'question': item['question'],
            'answer': item.get('answer'),
            'qa_type': 'drill',
        })
    insert_many(client, 'qa_pairs', qa_rows)

    print('Seeding notes/exercises/chart_refs...')
    note_rows = []
    exercise_rows = []
    exercise_types = {'dictation', 'revision_exercise', 'word_building_exercise', 'phrase_exercise', 'reading_exercise'}
    for bid, blk in blocks.items():
        b = blk['book']
        lesson_num = blk.get('lesson')
        common = {
            'block_id': bid,
            'book_id': book_id[b],
            'lesson_id': lesson_id.get(lesson_num),
            'book_page_id': page_id.get((b, blk['pdf_page'])),
            'book_num': b,
            'stage': blk['stage'],
            'lesson_num': lesson_num,
            'pdf_page': blk['pdf_page'],
            'book_page': blk.get('book_page'),
        }
        if blk['type'] == 'grammar_note':
            note_rows.append({**common, 'note_type': 'grammar', 'text': blk.get('text', '')})
        elif blk['type'] in exercise_types:
            exercise_rows.append({
                **common,
                'exercise_type': blk['type'].replace('_exercise', ''),
                'title': blk.get('title'),
                'text': blk.get('text', ''),
                'metadata': {k: blk[k] for k in ('items', 'terms') if k in blk},
            })
    insert_many(client, 'notes', note_rows)
    insert_many(client, 'exercises', exercise_rows)

    chart_rows = []
    for item in charts.get('items', []):
        b = item['book']
        lesson_num = item.get('lesson')
        chart_rows.append({
            'block_id': item['block_id'],
            'book_id': book_id[b],
            'lesson_id': lesson_id.get(lesson_num),
            'book_page_id': page_id.get((b, item['pdf_page'])),
            'chart_label': item.get('chart_label'),
            'ref_type': item['type'],
            'text': item['text'],
            'book_num': b,
            'stage': item['stage'],
            'lesson_num': lesson_num,
            'pdf_page': item['pdf_page'],
            'book_page': item.get('book_page'),
        })
    insert_many(client, 'chart_refs', chart_rows)

    print('Seed complete.')


if __name__ == '__main__':
    main()
