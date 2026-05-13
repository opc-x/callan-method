# Fine-Grained Callan Index Acceptance

The current Markdown conversion is not enough. The next delivery must build a fine-grained structure/index so every meaningful piece of content can be traced back to its exact location in the 12-book course.

## Goal

Create a structure that can answer:

```text
Given any term, question, answer, grammar note, dictation, revision item, word-building item, or chart reference:
Which Book?
Which Stage?
Which Lesson?
Which internal book page?
Which PDF physical page?
Which content block?
Where is the source text?
```

## Required Structural Model

Use this hierarchy:

```text
Course
  -> Book / Stage
    -> Lesson
      -> BookPage
        -> ContentBlock
          -> Items
```

Do not treat `Lesson -> Vocabulary / Notes / Q&A` as the final structure. It loses the page-level and block-level organization of the books.

## Required Concepts

### BookPage

Each content page must have:

```json
{
  "book": 9,
  "stage": 9,
  "lesson": 136,
  "book_page": 754,
  "pdf_page": 62
}
```

Important:

```text
pdf_page != book_page
```

The number printed on the left side of each content page is the internal `book_page`. PDF viewer page number is `pdf_page`.

### ContentBlock

A page must be split into semantic blocks where possible:

```text
lexical_block
grammar_note
qa_block
dictation
revision_exercise
word_building_exercise
phrase_exercise
reading_exercise
chart_reference
chart_page
vocabulary_index
front_matter
back_matter
```

### LexicalBlock

Do not call this a "word family" unless the words are morphologically related.

Preferred term:

```text
LexicalBlock / VocabularyBlock
```

A LexicalBlock is a small teaching vocabulary block on the page. It may contain unrelated vocabulary terms that are introduced together for drilling.

Example:

```json
{
  "type": "lexical_block",
  "block_id": "book9_lesson136_page754_block2",
  "terms": ["slight", "upside down", "right way up"],
  "book_page": 754,
  "pdf_page": 62,
  "lesson": 136
}
```

### WordFamily

Only use `word_family` for true related forms:

```text
economy / economic / economical
suspect / suspicion / suspicious
publish / publisher / publication
compare / comparison / comparable
```

If the source does not explicitly define a word family, infer it only when the relationship is clear.

## Required Output Files

Produce at least:

```text
structured/course-index.json
structured/term-index.json
structured/block-index.json
structured/lesson-index.json
structured/page-index.json
structured/acceptance-report.md
```

Optional but recommended:

```text
structured/qa-index.json
structured/dictation-index.json
structured/chart-index.json
```

## Required JSON Fields

Every ContentBlock must include:

```json
{
  "block_id": "stable_unique_id",
  "type": "lexical_block | grammar_note | qa_block | dictation | ...",
  "book": 12,
  "stage": 12,
  "lesson": 178,
  "book_page": 1076,
  "pdf_page": 14,
  "text": "...",
  "items": [],
  "source": {
    "pdf": "Callan Method 12.pdf",
    "pdf_page": 14,
    "book_page": 1076
  }
}
```

Every vocabulary/term item must include:

```json
{
  "term": "economic",
  "normalized": "economic",
  "book": 12,
  "stage": 12,
  "lesson": 178,
  "book_page": 1076,
  "pdf_page": 14,
  "block_id": "book12_lesson178_page1076_block3",
  "block_type": "lexical_block"
}
```

Every Q&A item must include:

```json
{
  "question": "...",
  "answer": "...",
  "book": 12,
  "stage": 12,
  "lesson": 178,
  "book_page": 1077,
  "pdf_page": 15,
  "block_id": "book12_lesson178_page1077_block8"
}
```

## Hard Requirements

The final structure must support these lookups:

```text
term -> block -> book_page -> pdf_page -> lesson -> stage
question -> block -> book_page -> pdf_page -> lesson -> stage
answer -> block -> book_page -> pdf_page -> lesson -> stage
lesson -> all book_pages -> all blocks
book_page -> all blocks on that page
chart reference -> chart page/asset if available
```

## Validation Commands

Create a validation script:

```text
structured/validate_fine_index.py
```

It must check:

```text
1. All 12 books present
2. Stage 1-12 present
3. Lesson 1-191 present
4. Every lesson has at least one BookPage
5. Every BookPage has book_page and pdf_page
6. Every ContentBlock has block_id, type, book, stage, lesson, book_page, pdf_page
7. Every term in term-index.json points to an existing block_id
8. Every Q&A item points to an existing block_id
9. No raw artifacts in any indexed text
10. No vocabulary-index content mixed into lesson body blocks
11. BookPage numbers are mostly monotonic within each book
12. PDF page numbers are monotonic within each book
```

Run:

```bash
/opt/homebrew/bin/python3 structured/validate_fine_index.py
```

Expected result:

```text
PASS
```

## Cross-Check Sample

Validate at least 36 lessons:

```text
first / middle / last lesson from each book
```

For each sampled lesson, check:

```text
Lesson exists
BookPage range exists
LexicalBlocks exist when vocabulary appears on the PDF page
Q&A blocks exist
Dictation/revision/word-building blocks exist if present
No vocabulary index contamination
No raw artifacts
Source PDF page mapping is plausible
```

## Acceptance Levels

PASS:

```text
All required JSON files exist
Validation script returns PASS
Lesson 1-191 complete
Every meaningful item has source location
Term lookup works
Q&A lookup works
BookPage lookup works
No raw artifacts
No vocabulary-index contamination
36 sampled lessons pass
```

WARNING:

```text
Main structure is complete, but a small number of optional block types are coarse-grained.
No missing lessons.
No missing source location for terms/Q&A.
No raw artifacts.
```

FAIL:

```text
Missing lesson
Missing book_page or pdf_page anchors
Term without block_id
Q&A without block_id
Vocabulary index mixed into lesson blocks
Raw artifacts remain
No validation script
```

## Important

The purpose is not only readable Markdown.

The purpose is a traceable knowledge base:

```text
keyword -> exact content block -> book_page -> pdf_page -> lesson -> stage
```

