#!/usr/bin/env python3
"""
seed_supabase.py  —  将 index_v2.json 导入 Supabase

用法（一次性）：
  /tmp/talkflow_venv/bin/python3 seed_supabase.py

需要事先：
  1. 在 Supabase 执行 migration（建表 + RLS）
  2. 临时打开 INSERT 策略（见下方 SQL 注释），运行完毕后再关

依赖：
  /tmp/talkflow_venv/bin/pip install supabase
"""

import json
from collections import defaultdict, OrderedDict
from pathlib import Path

from supabase import create_client

SUPABASE_URL = "https://frhtkmpsfyyidqijuijp.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZyaHRrbXBzZnl5aWRxaWp1aWpwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzg0NzE2MzksImV4cCI6MjA5NDA0NzYzOX0.WftUP6oiSzkbH8NVDL65W1BMlYAsFXFVcY6I2fPk2Ow"

INDEX = Path(__file__).parent / 'html' / 'index_v2.json'
BATCH = 400  # rows per upsert call


def chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def main():
    client = create_client(SUPABASE_URL, SUPABASE_KEY)

    print("Reading index_v2.json ...")
    data = json.loads(INDEX.read_text(encoding='utf-8'))
    print(f"  {len(data):,} entries")

    # ── lesson_id map ──────────────────────────────────────────────────────
    seen_lessons: dict = {}
    for e in data:
        k = (e['b'], e['l'])
        if k not in seen_lessons:
            seen_lessons[k] = e['c']
    lesson_rows = [
        {'book': b, 'lesson_num': l, 'stage': b, 'cefr_level': c}
        for (b, l), c in sorted(seen_lessons.items())
    ]
    lesson_id_map = {(r['book'], r['lesson_num']): i + 1
                     for i, r in enumerate(lesson_rows)}

    print(f"Inserting {len(lesson_rows)} lessons ...")
    for chunk in chunks(lesson_rows, BATCH):
        client.table('lessons').insert(chunk).execute()

    # 回查真实 ID（不依赖本地计算的序号）
    all_lessons = client.table('lessons').select('id,book,lesson_num').execute().data
    lesson_id_map = {(r['book'], r['lesson_num']): r['id'] for r in all_lessons}
    print(f"  lesson_id_map: {len(lesson_id_map)} entries")

    # ── cluster map ────────────────────────────────────────────────────────
    # Collect all unique (lesson_id, cluster_text) from BOTH vocab + qa
    cluster_order: dict[int, list] = defaultdict(list)
    cluster_seen: dict[int, set]   = defaultdict(set)
    cluster_words: dict[tuple, list] = defaultdict(list)
    cluster_words_seen: dict[tuple, set] = defaultdict(set)

    for e in data:
        cl  = e.get('cl') or ''
        lid = lesson_id_map[(e['b'], e['l'])]
        if cl not in cluster_seen[lid]:
            cluster_seen[lid].add(cl)
            cluster_order[lid].append(cl)
        if e['t'] == 'v':
            w = e.get('w', '')
            key = (lid, cl)
            if w and w not in cluster_words_seen[key]:
                cluster_words_seen[key].add(w)
                cluster_words[key].append(w)

    cluster_rows = []
    for lid in sorted(cluster_order):
        for pos, ct in enumerate(cluster_order[lid], 1):
            words = cluster_words.get((lid, ct)) or ['']
            cluster_rows.append({
                'lesson_id':    lid,
                'position':     pos,
                'cluster_text': ct,
                'words':        words,
            })

    print(f"Inserting {len(cluster_rows)} vocab_clusters ...")
    for i, chunk in enumerate(chunks(cluster_rows, BATCH)):
        client.table('vocab_clusters').upsert(chunk).execute()
        print(f"  {(i+1)*BATCH}/{len(cluster_rows)}", end='\r')
    print()

    # ── cluster_id map (query back) ────────────────────────────────────────
    print("Fetching cluster IDs ...")
    cluster_id_map: dict[tuple, int] = {}
    page, page_size = 0, 1000
    while True:
        rows = (client.table('vocab_clusters')
                .select('id,lesson_id,cluster_text')
                .range(page * page_size, (page + 1) * page_size - 1)
                .execute()).data
        if not rows:
            break
        for r in rows:
            cluster_id_map[(r['lesson_id'], r['cluster_text'])] = r['id']
        if len(rows) < page_size:
            break
        page += 1
    print(f"  {len(cluster_id_map)} clusters mapped")

    # ── vocab_words ────────────────────────────────────────────────────────
    pos_ctr: dict[int | None, int] = defaultdict(int)
    vocab_rows = []
    for e in data:
        if e['t'] != 'v':
            continue
        cl  = e.get('cl') or ''
        lid = lesson_id_map[(e['b'], e['l'])]
        cid = cluster_id_map.get((lid, cl))
        pos_ctr[cid] += 1
        vocab_rows.append({
            'cluster_id': cid,
            'lesson_id':  lid,
            'word':       e.get('w', ''),
            'position':   pos_ctr[cid],
            'page_index': e.get('p'),
            'y_coord':    e.get('y'),
        })

    print(f"Inserting {len(vocab_rows)} vocab_words ...")
    for i, chunk in enumerate(chunks(vocab_rows, BATCH)):
        client.table('vocab_words').insert(chunk).execute()
        print(f"  {min((i+1)*BATCH, len(vocab_rows))}/{len(vocab_rows)}", end='\r')
    print()

    # ── qa_pairs ───────────────────────────────────────────────────────────
    qa_pos_ctr: dict[int | None, int] = defaultdict(int)
    qa_rows = []
    for e in data:
        if e['t'] != 'q':
            continue
        cl  = e.get('cl') or ''
        lid = lesson_id_map[(e['b'], e['l'])]
        cid = cluster_id_map.get((lid, cl))
        qa_pos_ctr[cid] += 1
        qa_rows.append({
            'cluster_id': cid,
            'lesson_id':  lid,
            'position':   qa_pos_ctr[cid],
            'question':   e.get('q', ''),
            'answer':     e.get('a', ''),
            'audio_url':  None,
            'book':       e['b'],
            'lesson_num': e['l'],
            'page_index': e.get('p'),
            'y_coord':    e.get('y'),
        })

    print(f"Inserting {len(qa_rows)} qa_pairs ...")
    for i, chunk in enumerate(chunks(qa_rows, BATCH)):
        client.table('qa_pairs').insert(chunk).execute()
        print(f"  {min((i+1)*BATCH, len(qa_rows))}/{len(qa_rows)}", end='\r')
    print()

    # ── verify ─────────────────────────────────────────────────────────────
    print("\n=== 导入完成 ===")
    for tbl, expected in [('lessons', 191), ('vocab_clusters', 3751),
                          ('vocab_words', 9558), ('qa_pairs', 9012)]:
        cnt = client.table(tbl).select('id', count='exact').execute().count
        status = '✓' if cnt == expected else f'!= {expected}'
        print(f"  {tbl:<20} {cnt:>6}  {status}")


if __name__ == '__main__':
    main()
