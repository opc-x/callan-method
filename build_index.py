#!/opt/homebrew/bin/python3
"""
Build a self-contained search.html from all 12 Callan Method books.

Index structure (per entry):
  book, lesson, page, cefr   — location
  t = 'v'                    — vocab item  → text field
  t = 'q'                    — Q&A pair    → q, a fields

Output:
  html/search.html   — open in browser, type any word to find its location
  html/index.json    — raw JSON for external tools

Usage:
  python3 build_index.py
"""

import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from convert import parse_book, STAGE_CEFR

PDF_DIR = Path('/Users/cuijianchen/Downloads')
BASE    = Path('/Users/cuijianchen/gh-projects/kb-personal/callan-method')
OUT_DIR = BASE / 'html'

_LESSON_RE = re.compile(r'\bLESSON\s+(\d+)\b')

CEFR_SHORT = {
    1: 'A1', 2: 'A1–A2', 3: 'A2',
    4: 'A2–B1', 5: 'B1', 6: 'B1–B2',
    7: 'B2', 8: 'B2–C1', 9: 'C1',
    10: 'C1–C2', 11: 'C2', 12: 'C2',
}


# ── Data extraction ───────────────────────────────────────────────────────────

def extract_book(book_num):
    pdf = PDF_DIR / f'Callan Method {book_num}.pdf'
    if not pdf.exists():
        print(f'  Skipping Book {book_num}: not found')
        return []

    print(f'  Book {book_num}... ', end='', flush=True)

    result = subprocess.run(
        ['pdftotext', '-layout', str(pdf), '-'],
        capture_output=True, text=True, errors='replace',
    )
    raw = result.stdout

    # lesson → first page (1-indexed)
    lesson_pages = {}
    for i, pt in enumerate(raw.split('\x0c')):
        for m in _LESSON_RE.finditer(pt):
            ln = int(m.group(1))
            if ln not in lesson_pages:
                lesson_pages[ln] = i + 1

    sections = parse_book(raw, book_num)
    cefr     = CEFR_SHORT.get(book_num, '')
    entries  = []

    for sec in sections:
        ln   = sec['num']
        page = lesson_pages.get(ln, 0)
        base = {'b': book_num, 'l': ln, 'p': page, 'c': cefr}

        seen_vocab = set()
        for w in sec['vocab']:
            w = w.strip()
            if w and w not in seen_vocab:
                seen_vocab.add(w)
                entries.append({**base, 't': 'v', 'w': w})

        for q, a in sec['qa_pairs']:
            q, a = q.strip(), a.strip()
            if q:
                entries.append({**base, 't': 'q', 'q': q, 'a': a})

    v = sum(1 for e in entries if e['t'] == 'v')
    q = sum(1 for e in entries if e['t'] == 'q')
    print(f'{len(sections)} lessons · {v} vocab · {q} Q&A')
    return entries


# ── HTML template ─────────────────────────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Callan Method — Search</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #0f1117; color: #e0e0e0; min-height: 100vh;
  }

  /* ── Header ── */
  header {
    background: #16181f; border-bottom: 1px solid #2a2d3a;
    padding: 20px 32px; display: flex; align-items: center; gap: 20px;
    position: sticky; top: 0; z-index: 100;
  }
  header h1 { font-size: 16px; font-weight: 600; color: #fff; white-space: nowrap; }
  .search-wrap {
    flex: 1; position: relative; max-width: 600px;
  }
  .search-wrap input {
    width: 100%; padding: 10px 16px 10px 42px;
    background: #1e2130; border: 1px solid #2a2d3a; border-radius: 8px;
    color: #e0e0e0; font-size: 15px; outline: none;
    transition: border-color .15s;
  }
  .search-wrap input:focus { border-color: #4a9eff; }
  .search-wrap::before {
    content: '⌕'; position: absolute; left: 14px; top: 50%;
    transform: translateY(-50%); color: #555; font-size: 18px; pointer-events: none;
  }
  .filters { display: flex; gap: 8px; align-items: center; }
  .filter-btn {
    padding: 6px 12px; border-radius: 6px; border: 1px solid #2a2d3a;
    background: #1e2130; color: #999; font-size: 12px; cursor: pointer;
    transition: all .15s;
  }
  .filter-btn.active { background: #4a9eff22; border-color: #4a9eff; color: #4a9eff; }

  /* ── Stats bar ── */
  #stats-bar {
    padding: 10px 32px; font-size: 12px; color: #555;
    border-bottom: 1px solid #1e2130; background: #0f1117;
  }

  /* ── Results ── */
  #results { padding: 16px 32px 40px; max-width: 1000px; }

  .empty-state {
    text-align: center; padding: 80px 0; color: #444; font-size: 15px;
  }
  .empty-state .hint { font-size: 13px; color: #333; margin-top: 8px; }

  .result-group { margin-bottom: 8px; }
  .result-group-header {
    font-size: 11px; text-transform: uppercase; letter-spacing: 1px;
    color: #555; margin-bottom: 4px; padding-left: 4px;
  }

  .result-card {
    background: #16181f; border: 1px solid #1e2130; border-radius: 8px;
    padding: 12px 16px; margin-bottom: 6px; display: flex;
    align-items: flex-start; gap: 14px;
    transition: border-color .15s, background .15s;
  }
  .result-card:hover { border-color: #2a2d3a; background: #1a1c26; }
  .result-card a {
    text-decoration: none; color: inherit; display: flex;
    align-items: flex-start; gap: 14px; width: 100%;
  }

  /* Location badge */
  .loc {
    flex-shrink: 0; display: flex; flex-direction: column;
    align-items: center; gap: 2px; min-width: 64px;
  }
  .loc-book {
    font-size: 11px; font-weight: 700; color: #fff;
    background: #2a2d3a; padding: 2px 8px; border-radius: 4px;
  }
  .loc-lesson { font-size: 11px; color: #888; }
  .loc-page   { font-size: 10px; color: #555; }
  .cefr-badge {
    font-size: 9px; color: #4a9eff; background: #4a9eff18;
    padding: 1px 5px; border-radius: 3px; font-weight: 600;
  }

  /* Type badge */
  .type-badge {
    flex-shrink: 0; font-size: 10px; font-weight: 700;
    padding: 2px 6px; border-radius: 4px; margin-top: 2px;
    text-transform: uppercase; letter-spacing: .5px;
  }
  .type-v { background: #22543d; color: #68d391; }
  .type-q { background: #2a2068; color: #7f9cf5; }

  /* Content */
  .content { flex: 1; min-width: 0; }
  .vocab-word { font-size: 15px; font-weight: 600; color: #fff; }
  .vocab-word mark { background: #4a9eff33; color: #7ec8ff; border-radius: 2px; }
  .qa-q { font-size: 14px; color: #d0d0d0; line-height: 1.4; }
  .qa-q mark { background: #4a9eff33; color: #7ec8ff; border-radius: 2px; }
  .qa-a { font-size: 13px; color: #888; margin-top: 3px; line-height: 1.4; }
  .qa-a mark { background: #4a9eff22; color: #7ec8ff; border-radius: 2px; }

  /* Load more */
  #load-more {
    display: none; margin: 16px auto 0; padding: 10px 24px;
    background: #1e2130; border: 1px solid #2a2d3a; border-radius: 8px;
    color: #999; font-size: 13px; cursor: pointer;
  }
  #load-more:hover { background: #2a2d3a; color: #fff; }
</style>
</head>
<body>

<header>
  <h1>Callan Method</h1>
  <div class="search-wrap">
    <input type="text" id="search" placeholder="Type a word…" autofocus autocomplete="off">
  </div>
  <div class="filters">
    <button class="filter-btn active" data-type="all">All</button>
    <button class="filter-btn" data-type="v">Vocab</button>
    <button class="filter-btn" data-type="q">Q&amp;A</button>
  </div>
</header>

<div id="stats-bar">
  <span id="stats-text">__TOTAL_ENTRIES__ entries across 12 books · __VOCAB_COUNT__ vocab · __QA_COUNT__ Q&amp;A pairs</span>
</div>

<div id="results">
  <div class="empty-state">
    <div>Search across all 12 Callan Method stages</div>
    <div class="hint">Stage → Lesson → Page → Content</div>
  </div>
</div>
<button id="load-more">Show more results</button>

<script>
const INDEX = __INDEX_JSON__;

const BOOK_NAMES = {
  1:'Book 1',2:'Book 2',3:'Book 3',4:'Book 4',5:'Book 5',6:'Book 6',
  7:'Book 7',8:'Book 8',9:'Book 9',10:'Book 10',11:'Book 11',12:'Book 12'
};

let filtered = [];
let shown    = 0;
const PAGE   = 50;
let activeType = 'all';

const searchEl  = document.getElementById('search');
const resultsEl = document.getElementById('results');
const loadMore  = document.getElementById('load-more');
const statsText = document.getElementById('stats-text');

function esc(s) {
  return String(s).replace(/[&<>"']/g, c =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function highlight(text, term) {
  if (!term) return esc(text);
  const re = new RegExp('(' + term.replace(/[.*+?^${}()|[\]\\]/g,'\\$&') + ')', 'gi');
  return esc(text).replace(re, '<mark>$1</mark>');
}

function renderCard(entry, term) {
  const book    = entry.b;
  const lesson  = entry.l;
  const page    = entry.p;
  const cefr    = entry.c;
  const href    = `book-${book}.html#lesson-${lesson}`;

  const loc = `
    <div class="loc">
      <span class="loc-book">${BOOK_NAMES[book]}</span>
      <span class="cefr-badge">${esc(cefr)}</span>
      <span class="loc-lesson">Lesson ${lesson}</span>
      ${page ? `<span class="loc-page">p.${page}</span>` : ''}
    </div>`;

  if (entry.t === 'v') {
    return `
    <div class="result-card">
      <a href="${href}" target="_blank">
        ${loc}
        <span class="type-badge type-v">vocab</span>
        <div class="content">
          <div class="vocab-word">${highlight(entry.w, term)}</div>
        </div>
      </a>
    </div>`;
  } else {
    return `
    <div class="result-card">
      <a href="${href}" target="_blank">
        ${loc}
        <span class="type-badge type-q">Q&amp;A</span>
        <div class="content">
          <div class="qa-q">${highlight(entry.q, term)}</div>
          ${entry.a ? `<div class="qa-a">${highlight(entry.a, term)}</div>` : ''}
        </div>
      </a>
    </div>`;
  }
}

function doSearch() {
  const raw  = searchEl.value.trim();
  const term = raw.toLowerCase();

  if (!term) {
    resultsEl.innerHTML = `
      <div class="empty-state">
        <div>Search across all 12 Callan Method stages</div>
        <div class="hint">Stage → Lesson → Page → Content</div>
      </div>`;
    loadMore.style.display = 'none';
    statsText.textContent = `__TOTAL_ENTRIES__ entries across 12 books · __VOCAB_COUNT__ vocab · __QA_COUNT__ Q&A pairs`;
    return;
  }

  filtered = INDEX.filter(e => {
    if (activeType !== 'all' && e.t !== activeType) return false;
    if (e.t === 'v') return e.w.toLowerCase().includes(term);
    return e.q.toLowerCase().includes(term) || (e.a && e.a.toLowerCase().includes(term));
  });

  shown = 0;
  renderPage(raw, true);
}

function renderPage(term, reset) {
  const slice  = filtered.slice(shown, shown + PAGE);
  const html   = slice.map(e => renderCard(e, term)).join('');
  const count  = filtered.length;
  const vCount = filtered.filter(e => e.t === 'v').length;
  const qCount = filtered.filter(e => e.t === 'q').length;

  if (reset) {
    resultsEl.innerHTML = count === 0
      ? `<div class="empty-state"><div>No results for "${esc(term)}"</div></div>`
      : html;
  } else {
    resultsEl.insertAdjacentHTML('beforeend', html);
  }

  shown += slice.length;
  loadMore.style.display = (shown < count) ? 'block' : 'none';

  if (count > 0) {
    statsText.textContent = `${count} result${count!==1?'s':''} · ${vCount} vocab · ${qCount} Q&A`;
  }
}

searchEl.addEventListener('input', doSearch);

document.querySelectorAll('.filter-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    activeType = btn.dataset.type;
    doSearch();
  });
});

loadMore.addEventListener('click', () => {
  renderPage(searchEl.value.trim(), false);
});
</script>
</body>
</html>
"""


# ── Builder ───────────────────────────────────────────────────────────────────

def build():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print('Building Callan Method search index\n')
    all_entries = []
    for n in range(1, 13):
        all_entries.extend(extract_book(n))

    vocab_count = sum(1 for e in all_entries if e['t'] == 'v')
    qa_count    = sum(1 for e in all_entries if e['t'] == 'q')
    total       = len(all_entries)
    print(f'\nTotal: {total} entries · {vocab_count} vocab · {qa_count} Q&A\n')

    # Write raw JSON index
    json_path = OUT_DIR / 'index.json'
    json_path.write_text(json.dumps(all_entries, ensure_ascii=False), encoding='utf-8')
    print(f'Wrote {json_path}  ({json_path.stat().st_size/1_048_576:.1f} MB)')

    # Write self-contained search.html
    index_json = json.dumps(all_entries, ensure_ascii=False, separators=(',', ':'))
    html = (HTML
        .replace('__INDEX_JSON__', index_json)
        .replace('__TOTAL_ENTRIES__', f'{total:,}')
        .replace('__VOCAB_COUNT__', f'{vocab_count:,}')
        .replace('__QA_COUNT__', f'{qa_count:,}')
    )
    html_path = OUT_DIR / 'search.html'
    html_path.write_text(html, encoding='utf-8')
    print(f'Wrote {html_path}  ({html_path.stat().st_size/1_048_576:.1f} MB)')
    print('\nDone. Open html/search.html in your browser.')


if __name__ == '__main__':
    build()
