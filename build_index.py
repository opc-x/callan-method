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

import fitz  # PyMuPDF — for exact Y-coordinate location

sys.path.insert(0, str(Path(__file__).parent))
from convert import parse_book, STAGE_CEFR

PDF_DIR = Path('/Users/cuijianchen/Downloads')
BASE    = Path('/Users/cuijianchen/gh-projects/kb-personal/callan-method')
OUT_DIR = BASE / 'html'

CEFR_SHORT = {
    1:'A1', 2:'A1–A2', 3:'A2', 4:'A2–B1', 5:'B1', 6:'B1–B2',
    7:'B2', 8:'B2–C1', 9:'C1', 10:'C1–C2', 11:'C2', 12:'C2',
}

_LESSON_RE = re.compile(r'\bLESSON\s+(\d+)\b', re.I)


# ── Pass 2: exact page + line location via PyMuPDF ───────────────────────────

def build_page_index(doc):
    """
    For each page, extract all text lines with their Y coordinates.
    Returns: list of {page_idx → [(line_text_lower, y_int), ...]}
    Uses PyMuPDF so page indices match the HTML book exactly.
    """
    pages = []
    for i in range(len(doc)):
        lines = []
        for block in doc[i].get_text("dict")["blocks"]:
            if block.get("type") != 0:
                continue
            for line in block["lines"]:
                text = "".join(s["text"] for s in line["spans"]).strip().lower()
                if text:
                    lines.append((text, int(line["bbox"][1])))
        pages.append(lines)
    return pages


def lesson_page_map(page_index):
    """Return {lesson_num: first_0indexed_page} from PyMuPDF page index."""
    mapping = {}
    for i, lines in enumerate(page_index):
        for text, _ in lines:
            for m in _LESSON_RE.finditer(text):
                ln = int(m.group(1))
                if ln not in mapping:
                    mapping[ln] = i
    return mapping


def find_location(needle, lesson_num, page_index, lp_map, window=40):
    """
    Return (page_idx, y_int) for the first line containing needle,
    searching from the lesson's start page forward.
    Falls back to (lesson_start_page, 0) if not found.
    """
    start  = lp_map.get(lesson_num, 0)
    needle = needle[:40].lower().strip()
    for i in range(start, min(start + window, len(page_index))):
        for text, y in page_index[i]:
            if needle in text or (len(needle) > 8 and text in needle):
                return i, y
    return start, 0


# ── Pass 1 + 2 combined ───────────────────────────────────────────────────────

def extract_book(book_num):
    pdf = PDF_DIR / f'Callan Method {book_num}.pdf'
    if not pdf.exists():
        print(f'  Skipping Book {book_num}: not found')
        return []

    print(f'  Book {book_num}... ', end='', flush=True)

    # pdftotext for parsing (preserves two-column layout)
    result = subprocess.run(
        ['pdftotext', '-layout', str(pdf), '-'],
        capture_output=True, text=True, errors='replace',
    )
    raw = result.stdout

    # Pass 1: reliable parse
    sections = parse_book(raw, book_num)

    # Pass 2: PyMuPDF for exact page + line location (matches HTML indices)
    doc        = fitz.open(str(pdf))
    page_index = build_page_index(doc)
    doc.close()
    lp_map     = lesson_page_map(page_index)
    cefr       = CEFR_SHORT.get(book_num, '')
    entries    = []

    for sec in sections:
        ln = sec['num']

        # Vocab words (deduplicated within lesson)
        seen_vocab = set()
        for w in sec['vocab']:
            w = w.strip()
            if not w or w in seen_vocab:
                continue
            seen_vocab.add(w)
            page, y = find_location(w, ln, page_index, lp_map)
            entries.append({'b': book_num, 'l': ln, 'p': page, 'y': y, 'c': cefr,
                             't': 'v', 'w': w})

        # Q&A pairs
        for q, a in sec['qa_pairs']:
            q, a = q.strip(), a.strip()
            if not q:
                continue
            page, y = find_location(q, ln, page_index, lp_map)
            entries.append({'b': book_num, 'l': ln, 'p': page, 'y': y, 'c': cefr,
                             't': 'q', 'q': q, 'a': a})

    v = sum(1 for e in entries if e['t'] == 'v')
    q = sum(1 for e in entries if e['t'] == 'q')
    print(f'{len(sections)} lessons · {v} vocab · {q} Q&A')
    return entries


# ── HTML ──────────────────────────────────────────────────────────────────────

STAGE_META = [
    (1,  'A1',     'L 1–9',    'Beginner'),
    (2,  'A1–A2',  'L 10–24',  'Elementary'),
    (3,  'A2',     'L 25–40',  'Pre-Int'),
    (4,  'A2–B1',  'L 41–60',  'KET'),
    (5,  'B1',     'L 61–77',  'PET'),
    (6,  'B1–B2',  'L 78–94',  'Upper-Int'),
    (7,  'B2',     'L 95–111', 'FCE'),
    (8,  'B2–C1',  'L 112–126','FCE+'),
    (9,  'C1',     'L 127–145','Advanced'),
    (10, 'C1–C2',  'L 146–163','Advanced+'),
    (11, 'C2',     'L 164–177','CPE'),
    (12, 'C2',     'L 178–191','CPE Master'),
]

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
  .filters { display: flex; gap: 6px; flex-shrink: 0; }
  .filter-btn {
    padding: 5px 11px; border-radius: 6px; border: 1px solid #2a2d3a;
    background: #1e2130; color: #888; font-size: 12px; cursor: pointer;
    transition: all .15s;
  }
  .filter-btn.active { background: #4a9eff22; border-color: #4a9eff; color: #4a9eff; }

  /* Stage directory strip */
  #stage-nav {
    background: #0d0f16; border-bottom: 1px solid #1e2130;
    padding: 10px 28px; overflow-x: auto; white-space: nowrap;
    display: flex; gap: 6px; align-items: stretch;
  }

  /* Lesson navigation strip */
  #lesson-nav {
    background: #0b0d13; border-bottom: 1px solid #1a1c26;
    padding: 7px 28px; overflow-x: auto; white-space: nowrap;
    display: none; gap: 4px; align-items: center;
  }
  #lesson-nav.visible { display: flex; }
  #lesson-nav .ln-label {
    font-size: 10px; color: #444; text-transform: uppercase;
    letter-spacing: .5px; margin-right: 6px; flex-shrink: 0;
  }
  .lesson-chip {
    padding: 3px 9px; border-radius: 5px; border: 1px solid #1e2130;
    background: #13151e; color: #666; font-size: 11px; cursor: pointer;
    transition: all .12s; flex-shrink: 0;
  }
  .lesson-chip:hover { border-color: #4a9eff88; color: #aac; }
  .lesson-chip.active-lesson { background: #1a2440; border-color: #4a9eff; color: #4a9eff; font-weight: 600; }
  .stage-card {
    display: inline-flex; flex-direction: column; align-items: center;
    padding: 7px 10px; border-radius: 7px; border: 1px solid #1e2130;
    background: #13151e; text-decoration: none; color: inherit;
    min-width: 72px; cursor: pointer; transition: all .15s; flex-shrink: 0;
  }
  .stage-card:hover { border-color: #4a9eff; background: #161e30; }
  .stage-card.active-book { border-color: #4a9eff; background: #1a2440; }
  .stage-card .s-num  { font-size: 11px; font-weight: 700; color: #7a8aaa; }
  .stage-card .s-cefr { font-size: 10px; color: #4a9eff; font-weight: 600; margin-top: 2px; }
  .stage-card .s-lessons { font-size: 9px; color: #444; margin-top: 1px; }
  .stage-card .s-label { font-size: 9px; color: #555; margin-top: 2px; }
  .stage-sep { width: 1px; background: #1e2130; flex-shrink: 0; margin: 4px 0; }

  /* Per-book stats shown on hover / in directory */
  #book-stats {
    background: #0d0f16; border-bottom: 1px solid #1a1c26;
    padding: 6px 28px; font-size: 11px; color: #445; min-height: 24px;
    transition: color .15s;
  }
  #book-stats span { color: #556; }
  #book-stats b { color: #7a8aaa; }

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

  /* Split-pane viewer */
  #app { display: flex; height: 100vh; overflow: hidden; }
  #left-pane {
    display: flex; flex-direction: column;
    width: 100%; min-width: 340px; max-width: 100%;
    transition: max-width .2s ease; overflow: hidden; flex-shrink: 0;
  }
  #app.viewer-open #left-pane { max-width: 440px; }
  #left-pane header { flex-shrink: 0; }
  #left-pane #stage-nav  { flex-shrink: 0; }
  #left-pane #lesson-nav { flex-shrink: 0; }
  #left-pane #book-stats { flex-shrink: 0; }
  #left-pane #stats-bar  { flex-shrink: 0; }
  #left-scroll { flex: 1; overflow-y: auto; }
  #left-scroll #results { padding: 10px 16px 40px; }
  #left-scroll #load-more { margin: 0 16px 16px; }

  #right-pane {
    flex: 1; display: none; flex-direction: column;
    border-left: 1px solid #1e2130; background: #fff; min-width: 0;
  }
  #app.viewer-open #right-pane { display: flex; }
  #viewer-bar {
    display: flex; align-items: center; gap: 10px;
    background: #16181f; border-bottom: 1px solid #2a2d3a;
    padding: 7px 14px; flex-shrink: 0;
  }
  #viewer-title { flex: 1; font-size: 12px; color: #888; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  #viewer-open-tab {
    padding: 4px 10px; border-radius: 5px; border: 1px solid #2a2d3a;
    background: #1e2130; color: #888; font-size: 11px; cursor: pointer; text-decoration: none;
    white-space: nowrap;
  }
  #viewer-open-tab:hover { color: #fff; border-color: #4a9eff; }
  #viewer-close {
    width: 26px; height: 26px; border-radius: 5px; border: 1px solid #2a2d3a;
    background: #1e2130; color: #888; font-size: 14px; cursor: pointer;
    display: flex; align-items: center; justify-content: center; flex-shrink: 0;
  }
  #viewer-close:hover { color: #fff; border-color: #ff4a4a; }
  #viewer-frame { flex: 1; border: none; width: 100%; }
</style>
</head>
<body>
<div id="app">
<div id="left-pane">
<header>
  <h1>Callan Method</h1>
  <div class="search-wrap">
    <input type="text" id="search" placeholder="Search any word, phrase, or Q&A…" autofocus autocomplete="off">
  </div>
  <div class="filters">
    <button class="filter-btn active" data-type="all">All</button>
    <button class="filter-btn" data-type="v">Vocab</button>
    <button class="filter-btn" data-type="q">Q&amp;A</button>
  </div>
</header>

<div id="stage-nav">__STAGE_CARDS__</div>
<div id="lesson-nav"><span class="ln-label">Lesson</span></div>
<div id="book-stats"><span>__CORPUS_SUMMARY__</span></div>
<div id="stats-bar">
  <span id="stats-text">__TOTAL__ entries · __VOCAB__ vocab · __QA__ complete Q&amp;A pairs · 12 stages</span>
</div>
<div id="left-scroll">
<div id="results">
  <div class="empty-state">
    <p>Search across all 12 Callan Method stages (L1–L191)</p>
    <small>Click any result to view the original book page</small>
  </div>
</div>
<button id="load-more">Show more</button>
</div><!-- /left-scroll -->
</div><!-- /left-pane -->

<div id="right-pane">
  <div id="viewer-bar">
    <span id="viewer-title">—</span>
    <a id="viewer-open-tab" href="#" target="_blank">Open tab ↗</a>
    <div id="viewer-close">✕</div>
  </div>
  <iframe id="viewer-frame" src="about:blank"></iframe>
</div>
</div><!-- /app -->
<script>
const INDEX = __INDEX_JSON__;
const BOOK_STATS = __BOOK_STATS_JSON__;
const PER_PAGE = 60;
let filtered = [], shown = 0, activeType = 'all', activeBook = 0, activeLesson = 0;
const searchEl   = document.getElementById('search');
const resultsEl  = document.getElementById('results');
const loadMore   = document.getElementById('load-more');
const statsEl    = document.getElementById('stats-text');
const bookStats  = document.getElementById('book-stats');
const lessonNav  = document.getElementById('lesson-nav');

// Build lesson index: book → sorted lesson numbers
const BOOK_LESSONS = {};
INDEX.forEach(e => {
  if (!BOOK_LESSONS[e.b]) BOOK_LESSONS[e.b] = new Set();
  BOOK_LESSONS[e.b].add(e.l);
});
Object.keys(BOOK_LESSONS).forEach(b => {
  BOOK_LESSONS[b] = [...BOOK_LESSONS[b]].sort((a,b)=>a-b);
});

function renderLessonNav(book) {
  // Remove old chips (keep the label)
  lessonNav.querySelectorAll('.lesson-chip').forEach(c => c.remove());
  if (!book) { lessonNav.classList.remove('visible'); return; }
  lessonNav.classList.add('visible');
  (BOOK_LESSONS[book] || []).forEach(ln => {
    const chip = document.createElement('div');
    chip.className = 'lesson-chip' + (ln === activeLesson ? ' active-lesson' : '');
    chip.textContent = `L${ln}`;
    chip.dataset.lesson = ln;
    chip.addEventListener('click', () => {
      if (activeLesson === ln) {
        activeLesson = 0;
        chip.classList.remove('active-lesson');
      } else {
        activeLesson = ln;
        lessonNav.querySelectorAll('.lesson-chip').forEach(c => c.classList.remove('active-lesson'));
        chip.classList.add('active-lesson');
      }
      doSearch();
    });
    lessonNav.appendChild(chip);
  });
}

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
  const anchor = e.y ? `p${e.p}-y${e.y}` : `page-${e.p}`;
  const href = `book-${e.b}.html#${anchor}`;
  const label = e.t === 'v' ? esc(e.w) : esc((e.q||'').slice(0,40));
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
  return `<div class="result-card"><a href="${href}" data-href="${href}" data-label="Book ${e.b} · L${e.l} · ${label}">${loc}<div class="content">${content}</div></a></div>`;
}

// Viewer
const app        = document.getElementById('app');
const frame      = document.getElementById('viewer-frame');
const viewerTitle = document.getElementById('viewer-title');
const openTabBtn  = document.getElementById('viewer-open-tab');
const closeBtn    = document.getElementById('viewer-close');

function openViewer(href, label) {
  frame.src = href;
  viewerTitle.textContent = label;
  openTabBtn.href = href;
  app.classList.add('viewer-open');
}
document.getElementById('results').addEventListener('click', e => {
  const a = e.target.closest('a[data-href]');
  if (!a) return;
  e.preventDefault();
  openViewer(a.dataset.href, a.dataset.label);
  document.querySelectorAll('.result-card a').forEach(x => x.style.background='');
  a.style.background = '#1a2440';
});
closeBtn.addEventListener('click', () => {
  app.classList.remove('viewer-open');
  frame.src = 'about:blank';
  document.querySelectorAll('.result-card a').forEach(x => x.style.background='');
});
function showBookStats(b) {
  if (!b) {
    bookStats.innerHTML = '<span>__CORPUS_SUMMARY__</span>';
    return;
  }
  const s = BOOK_STATS[b];
  if (!s) return;
  bookStats.innerHTML = `<b>Book ${b}</b> &nbsp;·&nbsp; ${s.cefr} &nbsp;·&nbsp; ${s.lessons} lessons (L${s.l1}–L${s.l2}) &nbsp;·&nbsp; <b>${s.vocab}</b> vocab &nbsp;·&nbsp; <b>${s.qa}</b> Q&amp;A pairs`;
}
function doSearch() {
  const raw = searchEl.value.trim(), term = raw.toLowerCase();
  if (!term && !activeBook && !activeLesson) {
    resultsEl.innerHTML = `<div class="empty-state"><p>Search across all 12 Callan Method stages (L1–L191)</p><small>Each result deep-links to the exact line in the original book</small></div>`;
    loadMore.style.display = 'none';
    statsEl.textContent = `__TOTAL__ entries · __VOCAB__ vocab · __QA__ complete Q&A pairs · 12 stages`;
    return;
  }
  filtered = INDEX.filter(e => {
    if (activeBook   && e.b !== activeBook)   return false;
    if (activeLesson && e.l !== activeLesson) return false;
    if (activeType !== 'all' && e.t !== activeType) return false;
    if (!term) return true;
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
      ? `<div class="empty-state"><p>No results${term ? ` for "${esc(term)}"` : ''}</p></div>`
      : html;
  else
    resultsEl.insertAdjacentHTML('beforeend', html);
  shown += slice.length;
  loadMore.style.display = shown < total ? 'block' : 'none';
  const v = filtered.filter(e=>e.t==='v').length;
  const q = filtered.filter(e=>e.t==='q' && e.a).length;
  if (total > 0) statsEl.textContent = `${total.toLocaleString()} result${total!==1?'s':''} · ${v.toLocaleString()} vocab · ${q.toLocaleString()} Q&A`;
}
// Stage card clicks — filter by book, reveal lesson nav
document.querySelectorAll('.stage-card[data-book]').forEach(card => {
  card.addEventListener('click', e => {
    if (e.ctrlKey || e.metaKey) { window.open(`book-${card.dataset.book}.html`, '_blank'); return; }
    e.preventDefault();
    const b = parseInt(card.dataset.book);
    activeLesson = 0;
    if (activeBook === b) {
      activeBook = 0;
      document.querySelectorAll('.stage-card').forEach(c => c.classList.remove('active-book'));
      showBookStats(0);
      renderLessonNav(0);
    } else {
      activeBook = b;
      document.querySelectorAll('.stage-card').forEach(c => c.classList.remove('active-book'));
      card.classList.add('active-book');
      showBookStats(b);
      renderLessonNav(b);
    }
    doSearch();
  });
  card.addEventListener('mouseenter', () => showBookStats(parseInt(card.dataset.book)));
  card.addEventListener('mouseleave', () => showBookStats(activeBook));
});
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

def build_html(all_entries, out_dir):
    """Generate search.html from entries (can be called without re-extracting PDFs)."""
    vocab    = sum(1 for e in all_entries if e['t'] == 'v')
    qa_total = sum(1 for e in all_entries if e['t'] == 'q')
    qa_full  = sum(1 for e in all_entries if e['t'] == 'q' and e.get('a', '').strip())
    total    = len(all_entries)

    # Per-book stats for the directory hover panel
    book_stats = {}
    for b in range(1, 13):
        bv = [e for e in all_entries if e['b'] == b and e['t'] == 'v']
        bq = [e for e in all_entries if e['b'] == b and e['t'] == 'q' and e.get('a','').strip()]
        ls = sorted(set(e['l'] for e in all_entries if e['b'] == b))
        cefr = CEFR_SHORT.get(b, '')
        book_stats[b] = {
            'cefr': cefr, 'vocab': len(bv), 'qa': len(bq),
            'lessons': len(ls), 'l1': ls[0] if ls else 0, 'l2': ls[-1] if ls else 0,
        }

    # Stage directory cards HTML
    cards_html = []
    for b, cefr, lessons, label in STAGE_META:
        cards_html.append(
            f'<div class="stage-card" data-book="{b}" title="Cmd+click to open Book {b}">'
            f'<span class="s-num">Book {b}</span>'
            f'<span class="s-cefr">{cefr}</span>'
            f'<span class="s-lessons">{lessons}</span>'
            f'<span class="s-label">{label}</span>'
            f'</div>'
        )
    stage_cards = '\n'.join(cards_html)

    corpus_summary = (
        f'12 stages · L1–L191 · {vocab:,} vocab items · '
        f'{qa_full:,} Q&amp;A pairs · hover a stage to see details · click to filter'
    )

    idx_json       = json.dumps(all_entries,  ensure_ascii=False, separators=(',', ':'))
    book_stats_json = json.dumps(book_stats,  ensure_ascii=False, separators=(',', ':'))

    html = (HTML
        .replace('__INDEX_JSON__',    idx_json)
        .replace('__BOOK_STATS_JSON__', book_stats_json)
        .replace('__STAGE_CARDS__',   stage_cards)
        .replace('__CORPUS_SUMMARY__', corpus_summary)
        .replace('__TOTAL__',  f'{total:,}')
        .replace('__VOCAB__',  f'{vocab:,}')
        .replace('__QA__',     f'{qa_full:,}')
    )
    html_path = out_dir / 'search.html'
    html_path.write_text(html, encoding='utf-8')
    print(f'Wrote {html_path}  ({html_path.stat().st_size/1_048_576:.1f} MB)')
    print(f'Stats: {total:,} total · {vocab:,} vocab · {qa_full:,} complete Q&A ({qa_total - qa_full} fragments excluded)')


def build():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print('Building Callan Method search index\n')

    all_entries = []
    for n in range(1, 13):
        all_entries.extend(extract_book(n))

    vocab = sum(1 for e in all_entries if e['t'] == 'v')
    qa    = sum(1 for e in all_entries if e['t'] == 'q')
    print(f'\nTotal: {len(all_entries):,} entries · {vocab:,} vocab · {qa:,} Q&A\n')

    json_path = OUT_DIR / 'index.json'
    json_path.write_text(json.dumps(all_entries, ensure_ascii=False), encoding='utf-8')
    print(f'Wrote {json_path}  ({json_path.stat().st_size/1_048_576:.1f} MB)')

    build_html(all_entries, OUT_DIR)
    print('\nDone. Open html/search.html in your browser.')


def rebuild_html_only():
    """Regenerate search.html from existing index.json without re-extracting PDFs."""
    json_path = OUT_DIR / 'index.json'
    if not json_path.exists():
        print(f'index.json not found at {json_path}. Run build() first.')
        return
    print(f'Loading {json_path}...')
    all_entries = json.loads(json_path.read_text(encoding='utf-8'))
    print(f'Loaded {len(all_entries):,} entries')
    build_html(all_entries, OUT_DIR)
    print('\nDone.')


if __name__ == '__main__':
    import sys
    if '--html-only' in sys.argv:
        rebuild_html_only()
    else:
        build()
