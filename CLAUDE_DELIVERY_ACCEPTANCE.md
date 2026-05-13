# Callan Method Delivery Acceptance

Do not claim completion until the conversion passes the checks below.

The existing `audit_callan_structure.py` is only a first-layer structure audit. It proves the lesson skeleton is present. It does not prove that Q&A, vocabulary, answers, dictations, or page-level content are accurate.

## Required Commands

Run from:

```bash
cd /Users/cuijianchen/gh-projects/kb-personal/callan-method
```

Run:

```bash
/opt/homebrew/bin/python3 audit_callan_structure.py
/opt/homebrew/bin/python3 verify_qa.py
```

## Layer 1: Structure Audit

Required output:

```text
Lesson coverage = 1-191
Missing lessons = none
Book 1-12 status table
low_text_pages count per book
suspicious_pages count per book
```

Hard fail:

```text
Any missing lesson
Any wrong lesson range
Any broken Stage/Book mapping
```

## Layer 2: Q&A / Vocabulary Audit

Required output table:

```text
Book | Lessons | Missing | Q&A | %A | Vocab | Dicts | Garbled | Status
```

Hard requirements:

```text
Missing must be "-"
Garbled must be 0
Q&A count must not be abnormally low
%A must not be abnormally low
Vocab must not include vocabulary-index garbage
Vocab must not include MMMMM/dotted-line artifacts
```

Important: checking only Q lines is not sufficient. The audit must scan the entire Markdown document, including:

```text
Q lines
A lines
Vocabulary sections
Notes sections
Dictation sections
Revision / Word-building sections
```

Hard fail if any final `book-*.md` contains raw PDF/control artifacts such as:

```text
\x01-\x08
\x0b
\x0e-\x1f
ǽ
ǿ
ʝ
ʒ
8IBU
UIF
XJUI
MMMMM dotted-line artifacts
```

If phonetic/IPA text is intentionally retained, it must be rendered as readable text, not wrapped in raw control characters. For example, raw `\x12...` delimiters are not acceptable in final Markdown.

Run an explicit whole-document grep/scan and report the result:

```bash
rg -n "8IBU|UIF|XJUI|ǽ|ǿ|ʝ|ʒ|MMMM|[\x01-\x08\x0b\x0e-\x1f]" book-*.md
```

Expected result:

```text
no matches
```

Do not use vague phrases like:

```text
Good progress
Looks clean
Mostly fixed
Should be fine
```

Use measurable PASS/WARNING/FAIL only.

## Layer 3: PDF Cross-Check

For each of the 12 books, manually or programmatically inspect at least 3 lessons:

```text
first lesson in the book
middle lesson in the book
last lesson in the book
```

That is at least 36 checked lessons total.

For every checked lesson, report:

```text
Book
Lesson
PDF page range
Markdown section location
Q missing? yes/no
A missing? yes/no
Vocab missing? yes/no
Dictation/revision missing? yes/no/not applicable
Garbled text? yes/no
Vocabulary index mixed into lesson? yes/no
Verdict: PASS/WARNING/FAIL
```

Hard fail:

```text
Question text is garbled
Answer text is missing or attached to the wrong question
Vocabulary block is missing
Vocabulary index is mixed into lesson body
Lesson body contains large missing chunks
```

## Layer 4: Semantic Section Audit

The converter must not merely produce "some Markdown". It must place content in the right semantic section.

Check at least Books 1, 6, 11, and 12 manually, and report whether the section classification is correct:

```text
Vocabulary = actual vocabulary/word-family terms
Notes = grammar/explanation text
Q&A Drill = questions and answers
Dictation = dictation text
Revision / Word-building = exercises
```

Hard fail examples:

```text
Grammar paragraphs placed under Vocabulary
Vocabulary/word-pool terms placed under Notes
Pronunciation artifacts left inside answers as raw control-character text
Vocabulary index entries mixed into lessons
```

## Required Final Report

Final answer must include:

```text
1. Structure audit result
2. verify_qa.py result table
3. Whole-document artifact scan result
4. Semantic section audit result
5. 36-lesson PDF cross-check summary
6. Known remaining warnings
7. Exact files changed
8. Final verdict: PASS / WARNING / FAIL
```

## Completion Standard

PASS means:

```text
Stage 1-12 present
Lesson 1-191 complete
Missing lessons = none
Garbled = 0
No vocabulary-index contamination
Q&A pairs are structurally valid
No raw control/PDF artifacts anywhere in book-*.md
Vocabulary/Notes/Q&A/Dictation sections are semantically correct
36 sampled lessons pass PDF-vs-Markdown review
```

WARNING means:

```text
Lesson structure is complete, but minor formatting or low-risk page issues remain.
No known missing Q&A content.
No severe garbled text.
No raw control-character artifacts.
```

FAIL means:

```text
Any missing lesson
Any severe garbled text
Any confirmed Q&A loss
Any confirmed answer/question mismatch
Any vocabulary-index contamination in lesson body
Any raw control-character artifact in final Markdown
Any systematic semantic section misclassification
```

## Important

The goal is not "parser seems better".

The goal is:

```text
prove the Markdown is safe to use as an AI knowledge base.
```
