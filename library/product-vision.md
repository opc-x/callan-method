# Callan App — Product Vision

> One-person company. Build while selling. Every action oriented toward getting paid.

---

## Core Idea in One Sentence

**Show a picture → student speaks English to describe it → AI corrects in real time → Callan Q&A reveals as the reference answer.**

图是产品的脸，Callan 是产品的骨头。

---

## The Insight Stack

**Insight 1 — The content is world-class, and it's done.**

191 lessons · 9,515 vocab items · 8,794 Q&A pairs · 3,256 vocabulary clusters · complete A1–C2 progression. 60 years of iteration. The hardest part of any language learning product — building a curriculum — is already solved. This is the 葵花宝典 of spoken English, and it's the foundation nobody else has.

**Insight 2 — The method's fatal UX flaw is the entry point.**

Callan's content is engineering-grade but its first impression is a wall of dense Q&A text. New users don't see the structure — they see intimidation. The image layer solves exactly this: the user's first experience is a vivid scene, not a textbook page.

**Insight 3 — 看图说话 is the right interaction for Chinese learners.**

It's a format every Chinese person learned in elementary school. Zero transfer cost. The user already knows what to do: look at the picture, open your mouth, describe what you see. The AI takes the teacher's role from there.

**Insight 4 — The gap in the market is AI evaluation of spoken output.**

Duolingo: gamification, doesn't produce real speakers.
Callan official app: a page-flipper, no AI, no voice.
ChatGPT as tutor: unstructured, no curriculum.
This product: engineered curriculum + AI real-time correction + visual entry point. This combination does not exist.

---

## Core UX Loop

```
1. User sees an image (scene from the current lesson)
        ↓
2. User speaks freely in English describing the scene
        ↓
3. Whisper transcribes → Claude evaluates:
   - Grammar errors corrected mid-sentence
   - Missing vocabulary flagged
   - Full sentence required (Callan rule: never just "yes" or "no")
        ↓
4. Correct answer revealed: the original Callan Q&A pair
        ↓
5. User repeats the corrected sentence
        ↓
6. Next cluster / next image
```

---

## Content Architecture

```
Image (visual entry)          ← DALL-E 3 generated, ~400 for MVP
    │
    └── Vocabulary Cluster    ← extracted from PDF blue boxes (3,256 total)
              │
              ├── Vocab words (9,515)
              └── Q&A pairs   (8,794 complete pairs)
                      │
                      └── Exact page location in original book
                                (book-N.html#p{page}-y{line})
```

**Image strategy:**
- MVP: 2 images per lesson × 191 lessons = ~400 images
- Cost: ~$16–32 via DALL-E 3 API
- Human review required: first pass especially for Stage 1–4 (beginner scenes must be unambiguous)
- Full version: 1 image per cluster × 3,256 clusters

**Content rule: never modify the Q&A pairs.**
The Q&A pairs are precisely engineered. Every sentence was designed to drill a specific syntactic slot for a specific cluster. Paraphrasing or regenerating them with AI destroys the spaced repetition architecture. Images are additive; Callan content is immutable.

---

## Two-Version Strategy

| | Personal version | Commercial version |
|---|---|---|
| Purpose | Daily self-study, real QA environment | Paying users |
| Auth | None | Supabase Auth + subscription |
| Progress sync | Local SQLite | Supabase PostgreSQL |
| Price | Free (you own it) | TBD |
| Value | You are the target user — every friction you feel is a bug to fix | |

**The personal version is the best product testing environment that exists.**
You are learning English with this app. Every time you feel friction, that's a real bug. Every feature you use daily is a feature worth shipping. Every feature you skip is a feature to deprioritize.

Risk: you are a B1+ learner. You will naturally polish Stage 5–12 and under-invest in Stage 1–4 onboarding. Fix: find 1–2 absolute beginners to use the personal version. Their stuck points are the commercial version's priority list.

---

## Go-to-Market Philosophy

> 边做边卖。每个做的动作都围绕着能不能卖出去。

Not: build → then sell.
Not: plan how to sell → then build.
**Every build action is oriented toward a real person paying or refusing to pay.**

The fastest signal is getting rejected with real money on the table. That tells you more in one conversation than six months of feature planning.

**Sequence:**
```
Week 1–2:  Terminal drill MVP — does the core loop work for you personally?
Week 3–4:  Add Claude API + Whisper — does AI correction feel like a real teacher?
Month 2:   Add images — does 看图说话 feel natural as the entry point?
Month 2:   Find 3 real users — charge them or get rejected
Month 3:   Build what the paying users actually needed
```

---

## Technical Stack

| Layer | Technology | Why |
|---|---|---|
| Content (static) | SQLite, imported from index.json | Offline, zero infra, built-in to iOS/Android |
| Speech input | Whisper (local via whisper.cpp) | Offline-first, low latency |
| AI evaluation | Claude API (claude-sonnet-4-6) | Best instruction-following for correction tasks |
| Image generation | DALL-E 3 (one-time batch) | High quality, affordable at ~400 images |
| User accounts | Supabase Auth | Handles auth so you don't have to |
| Progress sync | Supabase PostgreSQL | Multi-device, minimal ops |
| Visual book reader | Existing book-N.html (WebView) | Already built, pixel-perfect, deep-link ready |

**Do not use Supabase for content.** Content is static, 19k rows, never changes. SQLite handles it locally with zero cost and zero latency.

---

## What NOT to Build

| Temptation | Why not |
|---|---|
| Regenerate Q&A with AI | Destroys spaced repetition architecture |
| Gamification (streaks, badges) | Softens the time-pressure constraint that makes Callan work |
| Flashcard mode | Isolates words from clusters; contradicts lexical family binding |
| Translation mode | Reintroduces L1 mediation loop the method was designed to eliminate |
| Build everything before finding users | Classic one-person company failure mode |

---

## Scores

| Dimension | Score | Basis |
|---|---|---|
| Content quality (Callan itself) | 92 / 100 | 60-year engineered curriculum |
| Product concept (image + AI + Callan) | 88 / 100 | Unique combination, strong differentiation |
| Market gap | 90 / 100 | This combination does not exist |
| Execution risk | — | Depends entirely on shipping discipline |
