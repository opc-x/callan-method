# Callan Method — Knowledge Base

A personal knowledge base extracted from Callan Method Books 4–8.
Each markdown file contains the vocabulary, grammar notes, Q&A drill pairs, and
dictation texts for one book (stage), ready for study and quick reference.

---

## What is the Callan Method?

The **Callan Method** is an intensive English teaching method created by Robin Callan
in 1960. It focuses on:

- **Fast-paced Q&A drilling** — teacher asks questions non-stop, student answers immediately
- **Systematic revision** — new vocabulary is recycled across multiple lessons
- **Correction in real time** — grammar and pronunciation mistakes are corrected on the spot
- **Reading & dictation** — embedded in every lesson to reinforce written forms

It claims to teach English in a **quarter of the time** of conventional methods, with only
~80 hours needed to reach KET level and ~160 hours for FCE.

---

## Books in this Knowledge Base

| Book | Stage | CEFR Level | Lessons | Vocab items | Q&A pairs | Dictations | File |
|------|-------|------------|---------|-------------|-----------|------------|------|
| 4 | 4 | A2–B1 (KET) | 41–59 | 3,081 | 1,217 | 11 | [book-4.md](book-4.md) |
| 5 | 5 | B1 (PET) | 61–76 | 4,124 | 843 | 11 | [book-5.md](book-5.md) |
| 6 | 6 | B1–B2 | 78–93 | 3,356 | 1,232 | 11 | [book-6.md](book-6.md) |
| 7 | 7 | B2 (FCE) | 95–111 | 3,253 | 869 | 12 | [book-7.md](book-7.md) |
| 8 | 8 | B2–C1 | 112–117 | 4,086 | 1,144 | 9 | [book-8.md](book-8.md) |

> **Totals:** 5 books · 76 lessons · ~17,900 vocab items · ~5,305 Q&A pairs · 54 dictations

---

## How to Use This Knowledge Base

### Study a Lesson
Open any book file and navigate to a specific lesson.
Each lesson contains:

1. **Vocabulary** — all new words introduced in that lesson
2. **Grammar Notes** — explicit grammar rules (irregular verbs, usage rules, etc.)
3. **Q&A Drill** — the Q&A pairs used for drilling; answers show typical correct responses
4. **Dictation** — a short dictation text for writing practice

### Quick Vocabulary Reference
Use your editor's search to find any word across all books:

```
grep -ri "ambitious" ./*.md
```

### Lesson Flow (CEFR progression)

```
Book 4  A2–B1  ──►  Book 5  B1  ──►  Book 6  B1–B2  ──►  Book 7  B2  ──►  Book 8  B2–C1
Lessons 41–59       Lessons 61–76     Lessons 78–93        Lessons 95–111    Lessons 112–117
```

---

## Book Summaries

### Book 4 — Stage 4 (A2–B1, KET level)
**Lessons 41–59** · Covers core intermediate vocabulary and grammar including:
- **Irregular verbs** (speak/spoke, come/came, break/broke, know/knew, etc.)
- **Comparatives & superlatives** (bigger, the biggest)
- **Present perfect** (I have been, have you ever…?)
- **Modal verbs** (must/should, can/could)
- **Key vocabulary**: army, castle, hungry, notice, comfortable, career, crossroads, colleague

### Book 5 — Stage 5 (B1, PET level)
**Lessons 61–76** · Builds on B1 topics:
- **"Should" vs "Must"** (obligation vs strong obligation)
- **Reported speech** (he said that…)
- **Conditional sentences** (if I were…)
- **Key vocabulary**: chat, online, career, freedom, justice, boss, ambulance, scissors, jungle

### Book 6 — Stage 6 (B1–B2)
**Lessons 78–93** · Upper-intermediate focus:
- **Passive voice** (it was built, has been done)
- **Complex conditionals** (would have been)
- **Relative clauses** (the man who…, the thing that…)
- **Key vocabulary**: inherit, magnificent, ashamed, fluent, enormous, revenge, permanent

### Book 7 — Stage 7 (B2, FCE level)
**Lessons 95–111** · FCE preparation:
- **Advanced modals** (might have, should have, could have)
- **Reported questions**
- **Complex tense usage**
- **Key vocabulary**: prejudice, controversial, interpret, sophisticated, inevitable, mediocre

### Book 8 — Stage 8 (B2–C1, FCE and above)
**Lessons 112–117** · Advanced fluency:
- **Idiomatic expressions** (to look forward to, let me see, take a chance)
- **Complex grammar structures**
- **Rich vocabulary for essays and discussion**
- **Key vocabulary**: dismiss, deed, grease, scissors, due to, mostly, whistle, hunt

---

## Source Files

The markdown files were generated from the original Callan Method PDF textbooks using
a Python converter (`convert.py`). The PDFs use a custom font where characters are
shifted by +31 in ASCII (e.g. Books 4 & 8 encoded questions). The converter:

1. Extracts text with `pdftotext -layout` (poppler)
2. Detects and decodes the Callan +31 font encoding
3. Separates left-column questions from right-column answers using whitespace analysis
4. Identifies vocabulary lines, grammar notes, and dictation sections

> **Note on encoded questions (Books 4 & 8):** Questions in these books used a
> custom font. The decoded text is accurate but occasionally a comma or question mark
> may be missing from multi-line questions.

---

## Files

```
callan-method/
├── index.md        ← this file
├── book-4.md       ← Stage 4 lessons 41–59
├── book-5.md       ← Stage 5 lessons 61–76
├── book-6.md       ← Stage 6 lessons 78–93
├── book-7.md       ← Stage 7 lessons 95–111
├── book-8.md       ← Stage 8 lessons 112–117
└── convert.py      ← PDF-to-Markdown conversion script
```
