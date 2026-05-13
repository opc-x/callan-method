# Callan Fine-Grained Index Acceptance Report

Generated: 2026-05-12

## Verdict

```text
PASS
15 PASS, 0 WARNING, 0 FAIL
```

## Source

```text
/Users/cuijianchen/gh-projects/kb-personal/callan-method-origin
```

## Outputs

```text
structured/course-index.json
structured/lesson-index.json
structured/page-index.json
structured/block-index.json
structured/term-index.json
structured/qa-index.json
structured/dictation-index.json
structured/chart-index.json
```

## Final Counts

```text
12 books
191 lessons
1327 PDF pages
9160 content blocks
7250 term entries
6503 unique normalized terms
11412 Q&A pairs
130 dictations
69 chart references/pages
```

## Block Types Covered

```text
front_matter
lexical_block
grammar_note
qa_block
dictation
word_building_exercise
chart_reference
chart_page
```

## Validation Command

```bash
/opt/homebrew/bin/python3 structured/validate_fine_index.py
```

Expected final line:

```text
PASS
```

## Key Fixes After Claude Code Stopped

1. Modeled dictations explicitly.
   - `dictation-index.json` is no longer empty.
   - 130 dictations are indexed with source anchors.

2. Modeled chart references and chart pages explicitly.
   - `chart_reference` blocks are created for "See Chart N".
   - `chart_page` blocks are created for chart pages.
   - `chart-index.json` is generated.

3. Fixed hidden block-id overwrite risk.
   - Block IDs now include `pdf_page` where needed.
   - Validator checks `course-index.total_blocks == len(block-index)`.

4. Strengthened validation.
   - Validator now has 15 checks.
   - Dictation, chart modeling, and block count consistency are hard gates.

## Supabase Follow-Up

Schema design:

```text
/Users/cuijianchen/gh-projects/kb-personal/callan-method/SUPABASE_SCHEMA_REDESIGN.md
/Users/cuijianchen/gh-projects/talkflow/docs/database/schema-design.md
```

Migration draft:

```text
/Users/cuijianchen/gh-projects/talkflow/supabase/migrations/202605120001_callan_kb_schema.sql
```

Seed script:

```text
/Users/cuijianchen/gh-projects/kb-personal/callan-method/seed_supabase_structured.py
/Users/cuijianchen/gh-projects/kb-personal/callan-method/seed_supabase_structured_pg.py
```

Vector fields are reserved in the schema. Embeddings should be generated after relational import passes validation.

## Online Supabase Verification

Target verified through TalkFlow production Postgres connection:

```text
project ref: lqhddodpwidknzuwkgbt
public tables: 16
```

Online counts:

```text
books: 12
lessons: 191
book_pages: 1327
content_blocks: 9160
terms: 7250
qa_pairs: 11412
notes: 1803
exercises: 138
chart_refs: 69
scenes: 0
```

Online block types:

```text
chart_page: 28
chart_reference: 41
dictation: 130
front_matter: 146
grammar_note: 1803
lexical_block: 3484
qa_block: 3520
revision_exercise: 1
word_building_exercise: 7
```

Online relationship checks:

```text
term_bad_block_refs: 0
qa_bad_block_refs: 0
notes_bad_block_refs: 0
exercises_bad_block_refs: 0
charts_bad_block_refs: 0
blocks_without_pdf: 0
lesson_pages_without_book_page: 0
```

Vector columns verified:

```text
content_blocks.embedding
terms.embedding
qa_pairs.question_embedding
qa_pairs.answer_embedding
notes.embedding
exercises.embedding
```

Important environment note:

```text
TalkFlow production Postgres/Supabase credentials point to lqhddodpwidknzuwkgbt.
The local talkflow .env.local currently points to frhtkmpsfyyidqijuijp.
Unify app env vars before expecting local and production app reads to hit the same database.
```
