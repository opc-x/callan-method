#!/opt/homebrew/bin/python3
"""
Convert Callan Method PDFs to self-contained HTML files.

Each HTML file:
  - Embeds every PDF page as a high-res PNG (base64-encoded, no external files)
  - Detects LESSON N headers via pdftotext and creates anchor links
  - Has a sticky sidebar for lesson navigation
  - Is 100% visually faithful to the original PDF

Usage:
    python3 convert_html.py            # convert all 12 books
    python3 convert_html.py 1 4 7      # convert specific books
"""

import base64
import io
import re
import subprocess
import sys
from pathlib import Path

import fitz  # PyMuPDF

# ── Configuration ─────────────────────────────────────────────────────────────

PDF_DIR = Path('/Users/cuijianchen/Downloads')
OUT_DIR = Path('/Users/cuijianchen/gh-projects/kb-personal/callan-method/html')

DPI      = 150          # 150dpi = sharp on screen, reasonable file size
COLORSPACE = fitz.csRGB

STAGE_CEFR = {
    1: 'A1 — Beginner',          2: 'A1–A2',              3: 'A2',
    4: 'A2–B1 (KET)',            5: 'B1 (PET)',           6: 'B1–B2',
    7: 'B2 (FCE)',               8: 'B2–C1',              9: 'C1',
    10: 'C1–C2',                 11: 'C2 (CPE)',          12: 'C2 (CPE)',
}

# ── Lesson detection ──────────────────────────────────────────────────────────

_LESSON_RE = re.compile(r'\bLESSON\s+(\d+)\b')

def detect_lessons(pdf_path):
    """Return {page_index: [lesson_numbers]} by running pdftotext per page."""
    result = subprocess.run(
        ['pdftotext', '-layout', str(pdf_path), '-'],
        capture_output=True, text=True, errors='replace',
    )
    pages = result.stdout.split('\x0c')  # form-feed = page break
    mapping = {}
    for i, page_text in enumerate(pages):
        lessons = [int(m.group(1)) for m in _LESSON_RE.finditer(page_text)]
        if lessons:
            mapping[i] = lessons
    return mapping


# ── HTML template ─────────────────────────────────────────────────────────────

HTML_HEAD = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ display: flex; font-family: system-ui, sans-serif; background: #1a1a1a; color: #eee; }}

  /* Sidebar */
  #nav {{
    position: fixed; top: 0; left: 0; width: 200px; height: 100vh;
    overflow-y: auto; background: #111; padding: 12px 0;
    border-right: 1px solid #333; z-index: 10;
  }}
  #nav h2 {{ font-size: 11px; text-transform: uppercase; letter-spacing: 1px;
             color: #888; padding: 0 14px 8px; }}
  #nav a {{
    display: block; padding: 5px 14px; font-size: 13px; color: #ccc;
    text-decoration: none; border-left: 2px solid transparent;
  }}
  #nav a:hover, #nav a.active {{ color: #fff; border-left-color: #4a9eff; background: #1e1e1e; }}
  #nav .section {{ margin-top: 8px; }}
  #nav .section-title {{ font-size: 10px; color: #555; padding: 4px 14px;
                          text-transform: uppercase; letter-spacing: 1px; }}

  /* Page area */
  #pages {{ margin-left: 200px; padding: 20px; flex: 1; }}
  .book-title {{ font-size: 18px; font-weight: 600; color: #fff; margin-bottom: 4px; }}
  .book-cefr  {{ font-size: 13px; color: #888; margin-bottom: 20px; }}

  .page-wrap {{
    max-width: 900px; margin: 0 auto 6px;
    background: #fff; border-radius: 2px;
    box-shadow: 0 2px 12px rgba(0,0,0,.5);
    position: relative;
  }}
  .page-wrap img {{ width: 100%; display: block; }}
  .page-anchor {{ display: block; height: 0; }}
  .line-anchor {{
    position: absolute; left: 0; width: 100%; height: 1px;
    pointer-events: none;
  }}
</style>
</head>
<body>
<nav id="nav">
  <h2>Book {book_num}</h2>
  {nav_items}
</nav>
<div id="pages">
  <p class="book-title">Callan Method — Book {book_num} (Stage {book_num})</p>
  <p class="book-cefr">{cefr}</p>
"""

HTML_FOOT = """\
</div>
<script>
// Highlight active nav link on scroll
const anchors = document.querySelectorAll('.page-anchor');
const navLinks = document.querySelectorAll('#nav a[href^="#"]');
const observer = new IntersectionObserver(entries => {
  entries.forEach(e => {
    if (e.isIntersecting) {
      const id = e.target.id;
      navLinks.forEach(a => a.classList.toggle('active', a.getAttribute('href') === '#' + id));
    }
  });
}, { rootMargin: '-20% 0px -70% 0px' });
anchors.forEach(a => observer.observe(a));
</script>
</body>
</html>
"""


# ── Converter ─────────────────────────────────────────────────────────────────

def page_to_b64_png(page, dpi):
    mat  = fitz.Matrix(dpi / 72, dpi / 72)
    pix  = page.get_pixmap(matrix=mat, colorspace=COLORSPACE, alpha=False)
    buf  = io.BytesIO()
    buf.write(pix.tobytes('png'))
    return base64.b64encode(buf.getvalue()).decode()


def convert_book(book_num, pdf_path, out_path):
    print(f'  Book {book_num}... ', end='', flush=True)

    doc            = fitz.open(str(pdf_path))
    lesson_map     = detect_lessons(pdf_path)   # {page_idx: [lesson_nums]}
    total_pages    = len(doc)

    # Build reverse map: lesson_num → first page_idx it appears
    lesson_first_page = {}
    for page_idx, lessons in sorted(lesson_map.items()):
        for ln in lessons:
            if ln not in lesson_first_page:
                lesson_first_page[ln] = page_idx

    # Build sidebar nav HTML
    nav_parts = []
    nav_parts.append('<div class="section"><p class="section-title">Pages</p>')
    nav_parts.append(f'<a href="#page-0">Page 1</a>')
    nav_parts.append('</div>')
    if lesson_first_page:
        nav_parts.append('<div class="section"><p class="section-title">Lessons</p>')
        for ln in sorted(lesson_first_page):
            nav_parts.append(f'<a href="#lesson-{ln}">Lesson {ln}</a>')
        nav_parts.append('</div>')

    nav_html = '\n  '.join(nav_parts)
    cefr     = STAGE_CEFR.get(book_num, '')
    title    = f'Callan Method Book {book_num}'

    html_parts = [HTML_HEAD.format(
        title=title, book_num=book_num, cefr=cefr, nav_items=nav_html,
    )]

    for page_idx in range(total_pages):
        page      = doc[page_idx]
        b64       = page_to_b64_png(page, DPI)
        page_h    = page.rect.height  # PDF points

        # Collect all text-line Y positions for exact-line anchors
        line_ys = set()
        for block in page.get_text("dict")["blocks"]:
            if block.get("type") == 0:
                for line in block["lines"]:
                    line_ys.add(int(line["bbox"][1]))

        # Page-level and lesson-level anchors (position: top of image)
        anchors = [f'<span id="page-{page_idx}" class="page-anchor"></span>']
        if page_idx in lesson_map:
            for ln in lesson_map[page_idx]:
                if lesson_first_page.get(ln) == page_idx:
                    anchors.append(f'<span id="lesson-{ln}" class="page-anchor"></span>')

        # Per-line anchors overlaid on the image at exact Y%
        line_spans = [
            f'<span id="p{page_idx}-y{y}" class="line-anchor"'
            f' style="top:{y/page_h*100:.2f}%"></span>'
            for y in sorted(line_ys)
        ]

        html_parts.append('<div class="page-wrap">')
        html_parts += anchors
        html_parts.append(f'  <img src="data:image/png;base64,{b64}" alt="Page {page_idx+1}">')
        html_parts += line_spans
        html_parts.append('</div>')

        if (page_idx + 1) % 10 == 0:
            print(f'{page_idx+1}/{total_pages}..', end=' ', flush=True)

    html_parts.append(HTML_FOOT)
    out_path.write_text('\n'.join(html_parts), encoding='utf-8')

    size_mb = out_path.stat().st_size / 1_048_576
    lessons = len(lesson_first_page)
    print(f'done — {total_pages} pages, {lessons} lessons, {size_mb:.1f} MB')
    doc.close()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    books = [int(x) for x in sys.argv[1:]] if sys.argv[1:] else list(range(1, 13))

    print('Converting Callan Method PDFs → self-contained HTML\n')
    for n in books:
        pdf = PDF_DIR / f'Callan Method {n}.pdf'
        out = OUT_DIR / f'book-{n}.html'
        if pdf.exists():
            convert_book(n, pdf, out)
        else:
            print(f'  Skipping Book {n}: PDF not found at {pdf}')

    print(f'\nDone. Output: {OUT_DIR}')
