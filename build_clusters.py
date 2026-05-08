#!/opt/homebrew/bin/python3
"""
Extract vocabulary clusters from all 12 PDFs and inject cluster IDs
into index.json. Each vocab/QA entry gets a 'cl' field pointing to
its cluster (a string like "bump | bumpy | bump into (run into)").

Strategy:
  - Cluster = blue highlighted rectangle on the page (PyMuPDF drawings)
  - For each vocab entry: find which cluster box on the same page
    contains or is nearest-above its Y coordinate
  - QA entries inherit the cluster of the vocab words they drill
    (same lesson, nearest cluster by page/Y)
"""

import json, re, fitz
from pathlib import Path

PDF_DIR = Path('/Users/cuijianchen/Downloads')
BASE    = Path('/Users/cuijianchen/gh-projects/kb-personal/callan-method')
OUT_DIR = BASE / 'html'

EXERCISE_KEYWORDS = ['exercise', 'word pool', 'phrase exercise', 'dictation', 'stage', 'callan']

# ── Cluster extraction ────────────────────────────────────────────────────────

def extract_page_clusters(page):
    """Return list of {y0, y1, text} for every vocab cluster box on the page."""
    clusters = []
    for d in page.get_drawings():
        fc = d.get('fill')
        if not fc or fc in [(1,1,1), (0,0,0)]:
            continue
        r = d['rect']
        if r.height < 12 or r.height > 100:   # skip hairlines and huge exercise boxes
            continue
        words = page.get_text('words', clip=r)
        text = ' '.join(w[4] for w in words).strip()
        if not text or len(text) <= 2:
            continue
        tl = text.lower()
        if any(x in tl for x in EXERCISE_KEYWORDS):
            continue
        # Normalise: collapse whitespace, keep pipes as separators
        clean = re.sub(r'\s+', ' ', text).strip()
        clusters.append({'y0': round(r.y0), 'y1': round(r.y1), 'text': clean})
    return sorted(clusters, key=lambda c: c['y0'])


def build_book_cluster_map(book_num):
    """Return {page_idx: [cluster, ...]} for one book."""
    pdf = PDF_DIR / f'Callan Method {book_num}.pdf'
    if not pdf.exists():
        return {}
    doc  = fitz.open(str(pdf))
    cmap = {}
    for i in range(len(doc)):
        cs = extract_page_clusters(doc[i])
        if cs:
            cmap[i] = cs
    doc.close()
    return cmap


# ── Matching logic ────────────────────────────────────────────────────────────

def word_in_cluster(word, cluster_text):
    w = word.lower().strip()
    if not w or len(w) <= 1:
        return False
    return bool(re.search(r'(?<!\w)' + re.escape(w) + r'(?!\w)', cluster_text.lower()))


def find_cluster(word, page, y, cluster_map):
    """
    1. Text match on same page (word appears in cluster text) — closest by Y
    2. Text match on adjacent page
    3. Position fallback: box containing y, then nearest-above
    """
    # 1 & 2: text match
    for pg in [page, page - 1, page + 1]:
        clusters = cluster_map.get(pg, [])
        matches = [c for c in clusters if word_in_cluster(word, c['text'])]
        if matches:
            return min(matches, key=lambda c: abs(c['y0'] - y))['text']

    # 3: position fallback on same page
    clusters = cluster_map.get(page, [])
    if not clusters:
        return ''
    for c in clusters:
        if c['y0'] - 5 <= y <= c['y1'] + 10:
            return c['text']
    above = [c for c in clusters if c['y1'] <= y + 40]
    if above:
        return max(above, key=lambda c: c['y1'])['text']
    return ''


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print('Loading index.json...')
    index_path = OUT_DIR / 'index.json'
    entries = json.loads(index_path.read_text(encoding='utf-8'))
    print(f'  {len(entries):,} entries loaded')

    # Build cluster maps for all books
    book_cmaps = {}
    for b in range(1, 13):
        print(f'  Extracting clusters — Book {b}...', end=' ', flush=True)
        book_cmaps[b] = build_book_cluster_map(b)
        total = sum(len(v) for v in book_cmaps[b].values())
        print(f'{total} clusters on {len(book_cmaps[b])} pages')

    # Assign cluster to each vocab entry
    print('\nMatching entries to clusters...')
    matched = 0
    for e in entries:
        if e['t'] != 'v':
            continue
        cmap = book_cmaps.get(e['b'], {})
        cl = find_cluster(e.get('w', ''), e['p'], e['y'], cmap)
        if cl:
            e['cl'] = cl
            matched += 1

    # QA entries: inherit cluster from the nearest preceding vocab entry in same lesson
    # Build lesson→sorted vocab list
    lesson_vocabs = {}
    for e in entries:
        if e['t'] == 'v' and e.get('cl'):
            key = (e['b'], e['l'])
            lesson_vocabs.setdefault(key, []).append(e)
    for key in lesson_vocabs:
        lesson_vocabs[key].sort(key=lambda e: (e['p'], e['y']))

    qa_matched = 0
    for e in entries:
        if e['t'] != 'q':
            continue
        key = (e['b'], e['l'])
        vocabs = lesson_vocabs.get(key, [])
        if not vocabs:
            continue
        # Find vocab entry on same or earlier page, closest Y above
        candidates = [v for v in vocabs if v['p'] < e['p'] or
                      (v['p'] == e['p'] and v['y'] <= e['y'])]
        if candidates:
            e['cl'] = candidates[-1]['cl']
            qa_matched += 1

    vocab_total = sum(1 for e in entries if e['t'] == 'v')
    qa_total    = sum(1 for e in entries if e['t'] == 'q')
    print(f'  Vocab matched: {matched:,} / {vocab_total:,}  ({matched/vocab_total*100:.1f}%)')
    print(f'  Q&A  matched: {qa_matched:,} / {qa_total:,}  ({qa_matched/qa_total*100:.1f}%)')

    # Save updated index
    index_path.write_text(json.dumps(entries, ensure_ascii=False), encoding='utf-8')
    print(f'\nWrote {index_path}  ({index_path.stat().st_size/1_048_576:.1f} MB)')

    # Sample output
    print('\nSample cluster assignments:')
    samples = [e for e in entries if e.get('cl') and e['b'] == 11][:6]
    for e in samples:
        label = e.get('w') or e.get('q','')[:40]
        print(f'  [{e["cl"]}]  →  {label}')


if __name__ == '__main__':
    main()
