#!/opt/homebrew/bin/python3
"""
精准词族匹配 v2

核心改进：
  Q&A 条目不再靠"最近前一个vocab位置"继承词族，
  而是扫描 Q+A 文本，找哪个词族的词汇在其中出现最多，
  用词汇匹配代替位置继承。

匹配优先级：
  1. 词汇文本匹配（同课 → 相邻课）—— 最精准
  2. 位置回退（同页最近蓝框）        —— 备用
  3. 空字符串                        —— 实在匹配不上
"""

import json, re, fitz
from pathlib import Path
from collections import defaultdict

PDF_DIR = Path('/Users/cuijianchen/Downloads')
BASE    = Path('/Users/cuijianchen/gh-projects/kb-personal/callan-method')
OUT_DIR = BASE / 'html'

EXERCISE_KEYWORDS = ['exercise', 'word pool', 'phrase exercise', 'dictation', 'stage', 'callan']

# ── Callan 字体解码（Book 4/8 的私有编码）─────────────────────────────────────

GLYPH_MAP = {
    '\x01': ' ', 'ǽ': "'", 'ǿ': "'", 'ʝ': 'fi', 'ʒ': 'fl',
    'ﬁ': 'fi', 'ﬂ': 'fl', '‘': "'", '’': "'",
    '“': '"', '”': '"', '–': '-', '—': '-',
}

def decode_callan(text):
    result = []
    for c in text:
        if c in GLYPH_MAP:
            result.append(GLYPH_MAP[c])
            continue
        o = ord(c)
        if 0x22 <= o <= 0x5B:
            decoded = chr(o + 31)
            if decoded.isprintable():
                result.append(decoded)
                continue
        result.append(c)
    return re.sub(r'  +', ' ', ''.join(result)).strip()

def normalize_ligatures(text):
    """统一连字符，确保 ﬂoor == floor，ﬁnd == find"""
    return (text
        .replace('ﬂ', 'fl').replace('ﬁ', 'fi')
        .replace('ﬀ', 'ff').replace('ﬃ', 'ffi').replace('ﬄ', 'ffl')
    )

def clean_text(text):
    """清洗文本：解码 + 连字符 + 压缩空格 + 去控制符"""
    text = decode_callan(text)
    text = normalize_ligatures(text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

# ── 词族提取（蓝色矩形框）────────────────────────────────────────────────────

def extract_page_clusters(page):
    clusters = []
    for d in page.get_drawings():
        fc = d.get('fill')
        if not fc or fc in [(1,1,1), (0,0,0)]:
            continue
        r = d['rect']
        if r.height < 12 or r.height > 100:
            continue
        words = page.get_text('words', clip=r)
        text = ' '.join(w[4] for w in words).strip()
        if not text or len(text) <= 2:
            continue
        tl = text.lower()
        if any(x in tl for x in EXERCISE_KEYWORDS):
            continue
        clean = normalize_ligatures(re.sub(r'\s+', ' ', text).strip())
        clusters.append({
            'y0': round(r.y0), 'y1': round(r.y1),
            'text': clean,
            'words': set(re.findall(r"[a-zA-Z']+", clean.lower()))
        })
    return sorted(clusters, key=lambda c: c['y0'])

def build_book_cluster_map(book_num):
    """返回 {page_idx: [cluster, ...]}"""
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

# ── 词汇匹配得分──────────────────────────────────────────────────────────────

def cluster_match_score(qa_text_words: set, cluster_words: set) -> int:
    """计算 Q&A 文本与词族的词汇重叠数（短词过滤）"""
    # 过滤掉太短的功能词（a, is, the, it, of...）
    meaningful = {w for w in cluster_words if len(w) >= 3}
    if not meaningful:
        return 0
    return len(qa_text_words & meaningful)

# ── 主匹配逻辑──────────────────────────────────────────────────────────────

def find_cluster_for_qa(q: str, a: str, lesson_num: int,
                        book_lesson_clusters: dict,
                        page: int, y: int,
                        cluster_map: dict) -> str:
    """
    为一条 Q&A 找最匹配的词族。

    book_lesson_clusters: {lesson_num: [cluster_text, ...]}
    cluster_map: {page_idx: [cluster_dict, ...]}
    """
    # 合并 Q+A 文本，提取词汇集
    combined = clean_text(q) + ' ' + clean_text(a)
    qa_words = set(re.findall(r"[a-zA-Z']+", combined.lower()))

    # 1. 优先在同课内做词汇匹配
    best_text = ''
    best_score = 0

    for ln in [lesson_num, lesson_num - 1, lesson_num + 1]:
        clusters = book_lesson_clusters.get(ln, [])
        for cl in clusters:
            score = cluster_match_score(qa_words, cl['words'])
            if score > best_score:
                best_score = score
                best_text = cl['text']

    if best_score >= 1:
        return best_text

    # 2. 位置回退：同页最近蓝框（y 坐标最近的位于上方的框）
    page_clusters = cluster_map.get(page, [])
    if page_clusters:
        # 同页包含该 y 的框
        for c in page_clusters:
            if c['y0'] - 5 <= y <= c['y1'] + 10:
                return c['text']
        # 同页 y 上方最近的框
        above = [c for c in page_clusters if c['y1'] <= y + 40]
        if above:
            return max(above, key=lambda c: c['y1'])['text']

    return ''

# ── 主函数────────────────────────────────────────────────────────────────────

def main():
    print('Loading index.json ...')
    entries = json.loads((OUT_DIR / 'index.json').read_text(encoding='utf-8'))
    print(f'  {len(entries):,} entries')

    # 过滤掉无效 Q（单字母 PDF 标记）
    valid_entries = []
    skipped = 0
    for e in entries:
        if e['t'] == 'q' and len(e.get('q', '').strip()) <= 2:
            skipped += 1
            continue
        valid_entries.append(e)
    print(f'  过滤无效Q&A: {skipped} 条 → 保留 {len(valid_entries):,} 条')

    # 逐书处理
    result = []
    for b in range(1, 13):
        print(f'\nBook {b} ...', end=' ', flush=True)
        pdf = PDF_DIR / f'Callan Method {b}.pdf'
        if not pdf.exists():
            print('跳过（PDF不存在）')
            continue

        book_entries = [e for e in valid_entries if e['b'] == b]
        cmap = build_book_cluster_map(b)

        # 构建 lesson → [cluster_dict] 映射（用于文本匹配）
        book_lesson_clusters = defaultdict(list)
        for page_clusters in cmap.values():
            pass  # 先收集全书词族

        # 更精准：按 entry 的 lesson 建索引
        # 用vocab条目的页码找到同课词族
        lesson_pages = defaultdict(set)
        for e in book_entries:
            if e['t'] == 'v':
                lesson_pages[e['l']].add(e['p'])

        lesson_clusters = defaultdict(list)
        for ln, pages in lesson_pages.items():
            seen = set()
            for pg in sorted(pages):
                for c in cmap.get(pg, []):
                    key = c['text']
                    if key not in seen:
                        seen.add(key)
                        lesson_clusters[ln].append(c)
            # 也加上相邻页
            for pg in sorted(pages):
                for adj in [pg-1, pg+1]:
                    for c in cmap.get(adj, []):
                        key = c['text']
                        if key not in seen:
                            seen.add(key)
                            lesson_clusters[ln].append(c)

        # 处理词汇条目：直接文本匹配蓝框
        vocab_matched = 0
        for e in book_entries:
            if e['t'] != 'v':
                continue
            w = clean_text(e.get('w', ''))
            if not w:
                continue

            # 同页 + 相邻页文本匹配
            found = ''
            for pg in [e['p'], e['p']-1, e['p']+1]:
                for c in cmap.get(pg, []):
                    w_lower = w.lower()
                    if re.search(r'(?<!\w)' + re.escape(w_lower) + r'(?!\w)', c['text'].lower()):
                        found = c['text']
                        break
                if found:
                    break

            # 没找到则用位置回退
            if not found:
                for c in cmap.get(e['p'], []):
                    if c['y0'] - 5 <= e['y'] <= c['y1'] + 10:
                        found = c['text']
                        break
                if not found:
                    above = [c for c in cmap.get(e['p'], []) if c['y1'] <= e['y'] + 40]
                    if above:
                        found = max(above, key=lambda c: c['y1'])['text']

            if found:
                e['cl'] = found
                vocab_matched += 1
            else:
                e.pop('cl', None)

        # 处理 Q&A 条目：词汇文本匹配
        qa_text_matched = 0
        qa_pos_matched  = 0
        qa_unmatched    = 0
        for e in book_entries:
            if e['t'] != 'q':
                continue
            cl = find_cluster_for_qa(
                e.get('q', ''), e.get('a', ''),
                e['l'], lesson_clusters,
                e['p'], e['y'], cmap
            )
            if cl:
                e['cl'] = cl
                # 判断是文本匹配还是位置匹配（通过得分判断）
                combined = clean_text(e.get('q','')) + ' ' + clean_text(e.get('a',''))
                qa_words = set(re.findall(r"[a-zA-Z']+", combined.lower()))
                cl_words = set(re.findall(r"[a-zA-Z']+", cl.lower()))
                if cluster_match_score(qa_words, cl_words) >= 1:
                    qa_text_matched += 1
                else:
                    qa_pos_matched += 1
            else:
                e.pop('cl', None)
                qa_unmatched += 1

        v_total  = sum(1 for e in book_entries if e['t'] == 'v')
        qa_total = sum(1 for e in book_entries if e['t'] == 'q')
        print(f'vocab {vocab_matched}/{v_total} | '
              f'Q&A 文本匹配={qa_text_matched} 位置回退={qa_pos_matched} 未匹配={qa_unmatched} / {qa_total}')

        result.extend(book_entries)

    # 清洗答案文本（\x01 和多余空格）
    print('\n清洗答案文本 ...')
    cleaned = 0
    for e in result:
        if e['t'] == 'q':
            orig_a = e.get('a', '')
            new_a = clean_text(orig_a)
            if new_a != orig_a:
                e['a'] = new_a
                cleaned += 1
    print(f'  清洗了 {cleaned} 条答案')

    # 写出新 index
    out_path = OUT_DIR / 'index_v2.json'
    out_path.write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
    total   = len(result)
    vocab   = sum(1 for e in result if e['t'] == 'v')
    qa      = sum(1 for e in result if e['t'] == 'q')
    cl_v    = sum(1 for e in result if e['t'] == 'v' and e.get('cl'))
    cl_q    = sum(1 for e in result if e['t'] == 'q' and e.get('cl'))
    print(f'\n完成写出 {out_path}')
    print(f'总计: {total:,} 条 | vocab={vocab:,}(词族覆盖={cl_v/vocab*100:.1f}%) '
          f'| Q&A={qa:,}(词族覆盖={cl_q/qa*100:.1f}%)')


if __name__ == '__main__':
    main()
