# Callan Method — AI-Powered Practice System

---

## The Problem

The Callan Method was built around one constraint: a human teacher who never pauses. Remove the teacher and the core mechanism — forced output under time pressure — collapses. Self-study with the markdown files gives you the content but not the drilling loop. The result is passive reading, which is the one thing Callan was designed to replace.

The gap is: **who asks the question?**

---

## Design Philosophy (inherited from the method)

Any product built on top of Callan must preserve its four engineering principles or it degrades into just another vocabulary app:

| Principle | Product requirement |
|---|---|
| **Lexical family binding** — words stored as networks, not lists | Always present the full cluster; never drill a word in isolation |
| **Immediate forced output** — 3–5 second response window | Enforce a visible countdown; do not accept "I need more time" |
| **Designed spaced repetition** — cluster revisits every 7–10 lessons | Track per-cluster exposure; schedule according to lesson distance, not time elapsed |
| **Example sentence distillation** — minimal, syntactically varied sentences | Use the original Q&A pairs verbatim; do not generate paraphrases |

Violating any of these principles produces a product that feels like Callan but doesn't work like Callan.

---

## Data Assets Available

Everything needed to build the product already exists:

| File | Contents | API surface |
|---|---|---|
| `html/index.json` | 19,698 entries: every vocab item and Q&A pair with book, lesson, page, Y-coordinate, CEFR level | Primary data source |
| `book-1.md` … `book-12.md` | Structured markdown: vocab clusters, grammar notes, Q&A, dictations | Secondary / display |
| `html/book-1.html` … `html/book-12.html` | Pixel-perfect PDF pages with per-line anchors | Visual reference, deep links |
| `html/search.html` | Full-text search across all 19,698 entries | Ready-made search UI |

**`index.json` entry schema:**

```json
{
  "b": 7,          // book number (1–12)
  "l": 104,        // lesson number (1–191)
  "p": 80,         // page index (0-based, PyMuPDF)
  "y": 316,        // Y coordinate in PDF points
  "c": "B2",       // CEFR level
  "t": "v",        // type: "v" = vocab, "q" = Q&A
  "w": "get a move on",  // vocab word (type=v)
  "q": "...",      // question text (type=q)
  "a": "..."       // answer text (type=q)
}
```

---

## MVP — Terminal Drill (2 days to build)

The fastest useful product: a command-line drill loop that replaces the teacher for a single session.

### What it does

1. Load `index.json`
2. Pick a lesson (or continue from last session stored in `~/.callan_progress.json`)
3. For each vocab cluster in the lesson:
   - Print the cluster words
   - For each Q&A pair in the cluster:
     - Print the question
     - Start a 5-second countdown (overwrite the same terminal line)
     - On Enter key: print the correct answer; prompt for self-assessment (1–3)
4. After lesson: print score, mark lesson done, schedule cluster for revision

### Implementation sketch

```python
# drill.py — minimal Callan terminal drill
import json, time, sys
from pathlib import Path

INDEX = json.loads(Path('html/index.json').read_text())
QA    = [e for e in INDEX if e['t'] == 'q']

def drill_lesson(lesson_num):
    pairs = [e for e in QA if e['l'] == lesson_num]
    for e in pairs:
        print(f"\n  Q: {e['q']}")
        input("  (press Enter for answer)")
        print(f"  A: {e['a']}")
        score = input("  Self-score 1-3: ")
```

**Time to build:** ~2 hours.
**Value:** Immediately usable. Enforces looking-up-then-checking. Does not enforce the time constraint (terminal input is slow to time accurately on all platforms).

---

## Standard — Claude API Drill (1 week to build)

Replace the passive answer-check with a live AI conversation partner that evaluates your spoken answer and gives the kind of correction a real Callan teacher gives.

### Architecture

```
User speaks → Whisper (STT) → Claude API → Evaluation + correction
                                          → Next question
```

### Claude API prompt design

```
System:
  You are a strict Callan Method teacher. You ask questions from the script,
  evaluate the student's answer, and correct mistakes in real time — mid-sentence
  if necessary. Rules:
  - The student must answer in a complete sentence. "Yes" alone = correction.
  - Correct grammar errors immediately, then ask them to repeat.
  - After a correct answer, proceed to the next question without praise.
  - Do not deviate from the Q&A script.

User turn:
  Current lesson: {lesson_num}
  Current question: {question}
  Correct answer: {answer}
  Student said: {transcription}
```

**Key design decision:** Pass `answer` in the system context so Claude can evaluate correctness and identify the specific error. Do not let Claude generate new questions — use only the original Q&A pairs from `index.json`.

### STT options

| Option | Latency | Cost | Notes |
|---|---|---|---|
| OpenAI Whisper API | ~1s | $0.006/min | Easiest; best for prototype |
| Whisper local (whisper.cpp) | ~0.5s | Free | Best for offline / low-cost |
| Apple Speech (macOS) | ~0.3s | Free | macOS only; less accurate |

### Session state

```json
{
  "current_lesson": 23,
  "completed_lessons": [1, 2, ..., 22],
  "cluster_due": {
    "book1-cluster47": "2026-05-15",
    "book2-cluster12": "2026-05-10"
  },
  "weak_items": ["treatment", "allowance"]
}
```

Store in `~/.callan_session.json`. Persist across sessions.

### Cost estimate (Claude API)

| Usage | API calls/session | Approximate cost |
|---|---|---|
| 20 min session, 1 lesson | ~40 evaluations | ~$0.05–0.10 |
| Daily study (5 lessons/week) | ~200 calls/week | ~$0.25–0.50/week |

At this rate, a full 9-month course (L1–L191) costs approximately **$10–20 in API calls**.

---

## Advanced — Full Practice System (3–4 weeks to build)

### Additional capabilities on top of Standard

**1. Pronunciation feedback**
Use Whisper's word-level timestamps to detect which words are mispronounced (high confidence gap between expected and transcribed word). Flag them for re-drill.

**2. Cluster revision scheduler**
Track which clusters were drilled when. Re-queue a cluster if:
- Student scored < 2 on any pair in the cluster, OR
- 7+ lessons have passed since last drill (mirrors Callan's built-in spaced repetition window)

**3. Visual page link**
After each lesson, display a deep link to the exact page and line in the HTML book:
```
html/book-7.html#p80-y316
```
Student can click to see the original PDF context for any word they struggled with.

**4. Progress dashboard**
Simple HTML page reading `~/.callan_session.json`:
- CEFR level progress bar (computed from lesson completion)
- Weak item heatmap (vocabulary items scored 1 repeatedly)
- Streak calendar

**5. Mock interview mode** (programmer-specific)
Pull only Q&A pairs that map to the programmer interview gap analysis from `learning-system.md`. Add a supplemental deck of ~50 technical phrases not in Callan. Evaluate answers with a Claude prompt tuned for technical English register.

---

## Ultimate — Native App (2–3 months)

For a fully polished product:

| Component | Technology |
|---|---|
| Mobile app (offline-first) | React Native or Swift (iOS) |
| Local STT | whisper.cpp via native binding |
| Local LLM for evaluation | Ollama + small model (3B) for basic correction; Claude API for nuanced feedback |
| Sync | iCloud / local file |
| Visual reader | WKWebView loading the existing `book-N.html` files |

**Offline-first is non-negotiable** for a language learning app used on commutes and without guaranteed connectivity.

The `book-N.html` files (23–47 MB each) are the visual reader. They already work in any browser. A WKWebView in Swift or a WebView in React Native loads them directly.

---

## What NOT to Build

| Temptation | Why to avoid |
|---|---|
| Regenerate Q&A with AI | Destroys the designed spaced repetition; AI paraphrases miss the exact syntactic variety that makes the original pairs work |
| Gamification (points, badges) | Callan's power comes from pressure and correction, not reward loops; gamification softens the constraint |
| Vocabulary flashcards | Isolates words from their clusters; directly contradicts lexical family binding principle |
| Translation mode | Reintroduces the L1 mediation loop the method was designed to eliminate |

---

## Build Sequence Recommendation

```
Week 1:  Terminal drill (MVP) — validate the core loop works for you personally
Week 2:  Add Claude API evaluation — test if AI correction feels like a real teacher
Week 3:  Add Whisper STT — test if spoken input is practical
Week 4:  Session persistence + revision scheduler — make it a daily habit tool
Month 2: Progress dashboard + mock interview mode
Month 3: Mobile if you want it on your phone
```

Ship the terminal version first. The most common failure mode in personal tools is over-engineering before validating that you actually use the thing.
