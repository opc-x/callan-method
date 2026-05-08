#!/opt/homebrew/bin/python3
"""
Build a self-contained search.html from all 12 Callan Method books.

Strategy (two-pass):
  Pass 1 — parse_book() from convert.py: reliable extraction of every vocab
            word and Q&A pair, grouped by lesson.  (proven, no reimplementation)
  Pass 2 — page-location scan: for each entry, scan the raw PDF pages starting
            from the lesson's first page to find the exact page the text is on.

Every entry in the index records the exact 0-indexed PDF page it appears on,
so clicking a search result jumps to that precise page in the book HTML viewer.

Output:
  html/search.html   — self-contained browser search tool
  html/index.json    — raw JSON for other tools
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

CEFR_SHORT = {
    1:'A1', 2:'A1–A2', 3:'A2', 4:'A2–B1', 5:'B1', 6:'B1–B2',
    7:'B2', 8:'B2–C1', 9:'C1', 10:'C1–C2', 11:'C2', 12:'C2',
}

_LESSON_RE = re.compile(r'\bLESSON\s+(\d+)\b')


# ── Pass 2: page location ─────────────────────────────────────────────────────

def lesson_page_map(raw_pages):
    """Return {lesson_num: first_0indexed_page} from pdftotext pages."""
    mapping = {}
    for i, pt in enumerate(raw_pages):
        for m in _LESSON_RE.finditer(pt):
            ln = int(m.group(1))
            if ln not in mapping:
                mapping[ln] = i
    return mapping


def find_page(needle, lesson_num, raw_pages, lp_map, window=40):
    """
    Return the 0-indexed page where `needle` first appears at or after
    the lesson's start page.  Falls back to the lesson start page.
    """
    start  = lp_map.get(lesson_num, 0)
    needle = needle[:50].lower().strip()
    for i in range(start, min(start + window, len(raw_pages))):
        if needle in raw_pages[i].lower():
            return i
    return start


# ── Pass 1 + 2 combined ───────────────────────────────────────────────────────

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

    # Split into per-page strings for location scanning
    raw_pages = raw.split('\x0c')

    # Pass 1: reliable parse
    sections = parse_book(raw, book_num)

    # Lesson → first page map
    lp_map = lesson_page_map(raw_pages)
    cefr   = CEFR_SHORT.get(book_num, '')
    entries = []

    for sec in sections:
        ln = sec['num']

        # Vocab words (deduplicated within lesson)
        seen_vocab = set()
        for w in sec['vocab']:
            w = w.strip()
            if not w or w in seen_vocab:
                continue
            seen_vocab.add(w)
            page = find_page(w, ln, raw_pages, lp_map)
            entries.append({'b': book_num, 'l': ln, 'p': page, 'c': cefr,
                             't': 'v', 'w': w})

        # Q&A pairs
        for q, a in sec['qa_pairs']:
            q, a = q.strip(), a.strip()
            if not q:
                continue
            page = find_page(q, ln, raw_pages, lp_map)
            entries.append({'b': book_num, 'l': ln, 'p': page, 'c': cefr,
                             't': 'q', 'q': q, 'a': a})

    v = sum(1 for e in entries if e['t'] == 'v')
    q = sum(1 for e in entries if e['t'] == 'q')
    print(f'{len(sections)} lessons · {v} vocab · {q} Q&A')
    return entries


# ── HTML ──────────────────────────────────────────────────────────────────────

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
  header {
    background: #16181f; border-bottom: 1px solid #2a2d3a;
    padding: 18px 28px; display: flex; align-items: center; gap: 16px;
    position: sticky; top: 0; z-index: 100;
  }
  header h1 { font-size: 15px; font-weight: 600; color: #fff; white-space: nowrap; }
  .search-wrap { flex: 1; position: relative; max-width: 560px; }
  .search-wrap input {
    width: 100%; padding: 9px 16px 9px 40px;
    background: #1e2130; border: 1px solid #2a2d3a; border-radius: 8px;
    color: #e0e0e0; font-size: 15px; outline: none; transition: border-color .15s;
  }
  .search-wrap input:focus { border-color: #4a9eff; }
  .search-wrap::before {
    content: '⌕'; position: absolute; left: 13px; top: 50%;
    transform: translateY(-50%); color: #555; font-size: 17px; pointer-events: none;
  }
  .filters { display: flex; gap: 6px; }
  .filter-btn {
    padding: 5px 11px; border-radius: 6px; border: 1px solid #2a2d3a;
    background: #1e2130; color: #888; font-size: 12px; cursor: pointer;
    transition: all .15s;
  }
  .filter-btn.active { background: #4a9eff22; border-color: #4a9eff; color: #4a9eff; }
  #stats-bar { padding: 8px 28px; font-size: 12px; color: #444; border-bottom: 1px solid #1a1c26; }
  #results { padding: 14px 28px 40px; max-width: 960px; }
  .empty-state { text-align: center; padding: 80px 0; color: #3a3d4a; }
  .empty-state p { font-size: 15px; }
  .empty-state small { font-size: 12px; display: block; margin-top: 6px; color: #2a2d3a; }
  .result-card {
    background: #13151e; border: 1px solid #1e2130; border-radius: 8px;
    margin-bottom: 5px; transition: border-color .12s, background .12s;
  }
  .result-card:hover { border-color: #2a2d3a; background: #161824; }
  .result-card a {
    display: flex; align-items: flex-start; gap: 12px;
    padding: 11px 14px; text-decoration: none; color: inherit;
  }
  .loc {
    flex-shrink: 0; display: flex; flex-direction: column;
    align-items: flex-start; gap: 3px; min-width: 108px;
  }
  .loc-book {
    font-size: 11px; font-weight: 700; color: #c8d0e0;
    background: #1e2538; padding: 2px 7px; border-radius: 4px;
  }
  .loc-detail { font-size: 11px; color: #555; }
  .loc-detail b { color: #7a8aaa; font-weight: 500; }
  .cefr-tag {
    font-size: 9px; color: #4a9eff; background: #4a9eff18;
    padding: 1px 5px; border-radius: 3px; font-weight: 600;
  }
  .page-badge {
    flex-shrink: 0; display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    min-width: 44px; background: #1a1c26; border-radius: 6px;
    padding: 4px 6px; border: 1px solid #1e2130;
  }
  .page-badge .pg-label { font-size: 9px; color: #444; text-transform: uppercase; }
  .page-badge .pg-num   { font-size: 14px; font-weight: 700; color: #7a8aaa; line-height: 1; }
  .type-badge {
    flex-shrink: 0; font-size: 9px; font-weight: 700;
    padding: 2px 6px; border-radius: 4px; margin-top: 3px;
    text-transform: uppercase; align-self: flex-start;
  }
  .type-v { background: #1a3a28; color: #4ade80; }
  .type-q { background: #1a1a40; color: #818cf8; }
  .content { flex: 1; min-width: 0; }
  .vocab-word { font-size: 14px; font-weight: 600; color: #e2e8f0; }
  .qa-q { font-size: 13px; color: #c8d0e0; line-height: 1.45; }
  .qa-a { font-size: 12px; color: #5a6480; margin-top: 3px; line-height: 1.4; }
  mark { background: #4a9eff30; color: #93c5fd; border-radius: 2px; }
  #load-more {
    display: none; margin: 14px 0 0; padding: 9px 22px;
    background: #1e2130; border: 1px solid #2a2d3a; border-radius: 8px;
    color: #888; font-size: 13px; cursor: pointer;
  }
  #load-more:hover { background: #2a2d3a; color: #fff; }
</style>
</head>
<body>
<header>
  <h1>Callan Method</h1>
  <div class="search-wrap">
    <input type="text" id="search" placeholder="Search any word…" autofocus autocomplete="off">
  </div>
  <div class="filters">
    <button class="filter-btn active" data-type="all">All</button>
    <button class="filter-btn" data-type="v">Vocab</button>
    <button class="filter-btn" data-type="q">Q&amp;A</button>
  </div>
</header>
<div id="stats-bar">
  <span id="stats-text">__TOTAL__ entries · __VOCAB__ vocab · __QA__ Q&amp;A · 12 books</span>
</div>
<div id="results">
  <div class="empty-state">
    <p>Search across all 12 Callan Method stages</p>
    <small>Each result links to the exact page in the original book</small>
  </div>
</div>
<button id="load-more">Show more</button>
<script>
const INDEX = __INDEX_JSON__;
const PER_PAGE = 60;
let filtered = [], shown = 0, activeType = 'all';
const searchEl = document.getElementById('search');
const resultsEl = document.getElementById('results');
const loadMore  = document.getElementById('load-more');
const statsEl   = document.getElementById('stats-text');

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g,
    c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function hi(text, term) {
  if (!term) return esc(text);
  return esc(text).replace(
    new RegExp('('+term.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+')','gi'),
    '<mark>$1</mark>');
}
function card(e, term) {
  const href = `book-${e.b}.html#page-${e.p}`;
  const loc = `
    <div class="loc">
      <span class="loc-book">Book ${e.b}</span>
      <span class="cefr-tag">${esc(e.c)}</span>
      <span class="loc-detail">Lesson <b>${e.l}</b></span>
    </div>
    <div class="page-badge">
      <span class="pg-label">page</span>
      <span class="pg-num">${e.p + 1}</span>
    </div>
    <span class="type-badge type-${e.t}">${e.t==='v'?'vocab':'Q&amp;A'}</span>`;
  const content = e.t === 'v'
    ? `<div class="vocab-word">${hi(e.w, term)}</div>`
    : `<div class="qa-q">${hi(e.q, term)}</div>${e.a?`<div class="qa-a">${hi(e.a,term)}</div>`:''}`;
  return `<div class="result-card"><a href="${href}" target="_blank">${loc}<div class="content">${content}</div></a></div>`;
}
function doSearch() {
  const raw = searchEl.value.trim(), term = raw.toLowerCase();
  if (!term) {
    resultsEl.innerHTML = `<div class="empty-state"><p>Search across all 12 Callan Method stages</p><small>Each result links to the exact page in the original book</small></div>`;
    loadMore.style.display = 'none';
    statsEl.textContent = `__TOTAL__ entries · __VOCAB__ vocab · __QA__ Q&A · 12 books`;
    return;
  }
  filtered = INDEX.filter(e => {
    if (activeType !== 'all' && e.t !== activeType) return false;
    return e.t === 'v'
      ? e.w.toLowerCase().includes(term)
      : e.q.toLowerCase().includes(term) || (e.a && e.a.toLowerCase().includes(term));
  });
  shown = 0;
  render(raw, true);
}
function render(term, reset) {
  const slice = filtered.slice(shown, shown + PER_PAGE);
  const html  = slice.map(e => card(e, term)).join('');
  const total = filtered.length;
  if (reset)
    resultsEl.innerHTML = total === 0
      ? `<div class="empty-state"><p>No results for "${esc(term)}"</p></div>`
      : html;
  else
    resultsEl.insertAdjacentHTML('beforeend', html);
  shown += slice.length;
  loadMore.style.display = shown < total ? 'block' : 'none';
  const v = filtered.filter(e=>e.t==='v').length, q = filtered.filter(e=>e.t==='q').length;
  if (total > 0) statsEl.textContent = `${total.toLocaleString()} result${total!==1?'s':''} · ${v.toLocaleString()} vocab · ${q.toLocaleString()} Q&A`;
}
searchEl.addEventListener('input', doSearch);
document.querySelectorAll('.filter-btn').forEach(btn =>
  btn.addEventListener('click', () => {
    document.querySelectorAll('.filter-btn').forEach(b=>b.classList.remove('active'));
    btn.classList.add('active'); activeType = btn.dataset.type; doSearch();
  }));
loadMore.addEventListener('click', () => render(searchEl.value.trim(), false));
</script>
</body>
</html>
"""


# ── Entry point ───────────────────────────────────────────────────────────────

def build():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print('Building Callan Method search index\n')

    all_entries = []
    for n in range(1, 13):
        all_entries.extend(extract_book(n))

    vocab = sum(1 for e in all_entries if e['t'] == 'v')
    qa    = sum(1 for e in all_entries if e['t'] == 'q')
    total = len(all_entries)
    print(f'\nTotal: {total:,} entries · {vocab:,} vocab · {qa:,} Q&A\n')

    json_path = OUT_DIR / 'index.json'
    json_path.write_text(json.dumps(all_entries, ensure_ascii=False), encoding='utf-8')
    print(f'Wrote {json_path}  ({json_path.stat().st_size/1_048_576:.1f} MB)')

    idx_json = json.dumps(all_entries, ensure_ascii=False, separators=(',', ':'))
    html = (HTML
        .replace('__INDEX_JSON__', idx_json)
        .replace('__TOTAL__', f'{total:,}')
        .replace('__VOCAB__', f'{vocab:,}')
        .replace('__QA__', f'{qa:,}')
    )
    html_path = OUT_DIR / 'search.html'
    html_path.write_text(html, encoding='utf-8')
    print(f'Wrote {html_path}  ({html_path.stat().st_size/1_048_576:.1f} MB)')
    print('\nDone. Open html/search.html in your browser.')


if __name__ == '__main__':
    build()
