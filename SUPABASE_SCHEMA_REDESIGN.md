# Supabase Schema Redesign for Callan Method

The current Supabase import in `seed_supabase.py` is an MVP search schema. It is not enough for a fine-grained Callan Method knowledge base.

Current tables implied by `seed_supabase.py`:

```text
lessons
vocab_clusters
vocab_words
qa_pairs
```

This is useful for basic lesson/vocab/Q&A search, but it cannot fully represent:

```text
Book -> Stage -> Lesson -> BookPage -> ContentBlock -> Items
```

## Current Problems

1. No `book_pages` layer.

```text
pdf_page != book_page
```

The internal page number printed on the left side of each content page is a major source anchor. The current schema mostly stores `page_index` and `y_coord`, but not a normalized `book_page`.

2. No `content_blocks` table.

Everything should attach to a semantic block:

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
front_matter
back_matter
vocabulary_index
```

3. Vocab clusters are not enough.

`vocab_clusters` is a partial concept. The real unit should be `content_blocks`, with lexical blocks as one block type.

4. Missing content types.

Current schema does not properly model:

```text
grammar notes
dictations
revision exercises
word-building exercises
phrase exercises
reading/cloze exercises
chart references
chart assets
front/back matter
```

5. Weak traceability.

The target lookup should be:

```text
term/question/answer/note/dictation -> block -> book_page -> pdf_page -> lesson -> stage -> source PDF
```

The current schema cannot guarantee that chain.

6. No vector/embedding layer.

The current `seed_supabase.py` does not create or seed embedding/vector fields. It is lexical search only.

## Recommended Schema

### books

```sql
create table books (
  id bigserial primary key,
  book_num int not null unique,
  stage int not null,
  cefr_level text,
  title text,
  source_pdf text not null,
  pdf_page_count int,
  created_at timestamptz default now()
);
```

### lessons

```sql
create table lessons (
  id bigserial primary key,
  book_id bigint not null references books(id) on delete cascade,
  book_num int not null,
  stage int not null,
  lesson_num int not null unique,
  pdf_page_start int,
  pdf_page_end int,
  book_page_start int,
  book_page_end int,
  created_at timestamptz default now()
);
```

### book_pages

```sql
create table book_pages (
  id bigserial primary key,
  book_id bigint not null references books(id) on delete cascade,
  lesson_id bigint references lessons(id) on delete set null,
  book_num int not null,
  stage int not null,
  lesson_num int,
  pdf_page int not null,
  book_page int,
  page_kind text not null default 'content',
  raw_text text,
  clean_text text,
  created_at timestamptz default now(),
  unique(book_num, pdf_page)
);
```

`page_kind` examples:

```text
front_matter
content
chart_page
vocabulary_index
back_matter
blank
```

### content_blocks

This is the core table.

```sql
create table content_blocks (
  id text primary key,
  book_id bigint not null references books(id) on delete cascade,
  lesson_id bigint references lessons(id) on delete set null,
  book_page_id bigint references book_pages(id) on delete set null,
  book_num int not null,
  stage int not null,
  lesson_num int,
  pdf_page int not null,
  book_page int,
  block_index int not null,
  block_type text not null,
  text text,
  metadata jsonb default '{}'::jsonb,
  created_at timestamptz default now()
);
```

Recommended `block_type` values:

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
front_matter
back_matter
vocabulary_index
```

### terms

```sql
create table terms (
  id bigserial primary key,
  block_id text not null references content_blocks(id) on delete cascade,
  book_id bigint not null references books(id) on delete cascade,
  lesson_id bigint references lessons(id) on delete set null,
  book_page_id bigint references book_pages(id) on delete set null,
  term text not null,
  normalized text not null,
  term_type text default 'vocabulary',
  book_num int not null,
  stage int not null,
  lesson_num int,
  pdf_page int not null,
  book_page int,
  position int,
  metadata jsonb default '{}'::jsonb,
  created_at timestamptz default now()
);
```

`term_type` examples:

```text
vocabulary
lexical_block_term
word_pool_term
word_family_member
writing_label
```

### qa_pairs

```sql
create table qa_pairs (
  id bigserial primary key,
  block_id text not null references content_blocks(id) on delete cascade,
  book_id bigint not null references books(id) on delete cascade,
  lesson_id bigint not null references lessons(id) on delete cascade,
  book_page_id bigint references book_pages(id) on delete set null,
  book_num int not null,
  stage int not null,
  lesson_num int not null,
  pdf_page int not null,
  book_page int,
  position int,
  question text not null,
  answer text,
  qa_type text default 'drill',
  metadata jsonb default '{}'::jsonb,
  created_at timestamptz default now()
);
```

`qa_type` examples:

```text
drill
reading_exercise
cloze_exercise
review
```

### notes

```sql
create table notes (
  id bigserial primary key,
  block_id text not null references content_blocks(id) on delete cascade,
  book_id bigint not null references books(id) on delete cascade,
  lesson_id bigint references lessons(id) on delete set null,
  book_page_id bigint references book_pages(id) on delete set null,
  note_type text default 'grammar',
  text text not null,
  book_num int not null,
  stage int not null,
  lesson_num int,
  pdf_page int not null,
  book_page int,
  created_at timestamptz default now()
);
```

### exercises

```sql
create table exercises (
  id bigserial primary key,
  block_id text not null references content_blocks(id) on delete cascade,
  book_id bigint not null references books(id) on delete cascade,
  lesson_id bigint references lessons(id) on delete set null,
  book_page_id bigint references book_pages(id) on delete set null,
  exercise_type text not null,
  text text not null,
  book_num int not null,
  stage int not null,
  lesson_num int,
  pdf_page int not null,
  book_page int,
  metadata jsonb default '{}'::jsonb,
  created_at timestamptz default now()
);
```

`exercise_type` examples:

```text
dictation
revision
word_building
phrase
reading
cloze
writing
```

### chart_refs

```sql
create table chart_refs (
  id bigserial primary key,
  block_id text references content_blocks(id) on delete cascade,
  book_id bigint not null references books(id) on delete cascade,
  lesson_id bigint references lessons(id) on delete set null,
  book_page_id bigint references book_pages(id) on delete set null,
  chart_label text not null,
  chart_asset_path text,
  book_num int not null,
  stage int not null,
  lesson_num int,
  pdf_page int not null,
  book_page int,
  created_at timestamptz default now()
);
```

## Vector / Embedding Fields

Yes, add vector fields.

The previous Supabase seed script does not appear to use embeddings or `pgvector`.

Use vectors for semantic lookup, not as a replacement for structured anchors.

Recommended:

```sql
create extension if not exists vector;
```

Add embeddings at block level first:

```sql
alter table content_blocks add column embedding vector(1536);
```

Optional embeddings:

```sql
alter table qa_pairs add column question_embedding vector(1536);
alter table qa_pairs add column answer_embedding vector(1536);
alter table terms add column embedding vector(1536);
alter table notes add column embedding vector(1536);
```

Recommended priority:

```text
1. content_blocks.embedding
2. qa_pairs.question_embedding
3. notes.embedding
4. terms.embedding only if needed
```

Why not only term embeddings?

```text
Single terms are often too short for useful semantic retrieval.
Blocks provide context and are better retrieval units.
```

## Search Strategy

Use hybrid retrieval:

```text
1. exact term search via terms.normalized
2. full-text search over content_blocks.text / qa_pairs.question / qa_pairs.answer
3. vector search over content_blocks.embedding
4. always return source anchors: book, stage, lesson, book_page, pdf_page, block_id
```

## Indexes

```sql
create index idx_lessons_book_lesson on lessons(book_num, lesson_num);
create index idx_book_pages_book_pdf on book_pages(book_num, pdf_page);
create index idx_book_pages_book_page on book_pages(book_num, book_page);
create index idx_blocks_lesson on content_blocks(lesson_id);
create index idx_blocks_page on content_blocks(book_page_id);
create index idx_blocks_type on content_blocks(block_type);
create index idx_terms_normalized on terms(normalized);
create index idx_terms_location on terms(book_num, lesson_num, book_page);
create index idx_qa_location on qa_pairs(book_num, lesson_num, book_page);
```

For vector search:

```sql
create index idx_blocks_embedding
on content_blocks
using ivfflat (embedding vector_cosine_ops)
with (lists = 100);
```

## Migration Plan

1. Treat current `seed_supabase.py` schema as legacy.
2. Use `structured/*.json` as the new source of truth.
3. Fix structured index gaps first:

```text
dictation-index.json is currently empty
book_page coverage must remain a hard gate
term cleanup still has some noisy raw forms like pen“. / etc.
chart_reference and chart_page must remain explicitly modeled
block_id uniqueness must be validated to prevent silent overwrites
```

4. Create new Supabase migration for the schema above.
5. Write `seed_supabase_structured.py`.
6. Validate counts against structured JSON.
7. Add embeddings after relational data is clean.

## Acceptance Criteria

PASS:

```text
All 12 books inserted
All 191 lessons inserted
Every content block has book/stage/lesson/pdf_page/book_page where applicable
Every term maps to a valid content block
Every Q&A maps to a valid content block
Dictations/exercises are not empty if present in source
No raw artifacts
No vocabulary-index contamination
Hybrid search returns source anchors
```

WARNING:

```text
Main blocks are indexed but optional chart assets are incomplete
Some front/back matter lacks book_page
Some non-core labels remain coarse-grained
```

FAIL:

```text
No book_pages table
No content_blocks table
No source anchors
No dictation/exercise modeling
Term/Q&A records cannot trace back to block/page/lesson/stage
```

## Verdict on Current Schema

Current `seed_supabase.py` schema score:

```text
45 / 100
```

Current `structured/*.json` direction score:

```text
90 / 100
```

Target redesigned Supabase schema:

```text
90+ / 100 after Supabase import validation
```
