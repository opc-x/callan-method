#!/usr/bin/env python3
"""
Generate and seed embeddings for Callan content_blocks.

Required environment:
  OPENAI_API_KEY
  SUPABASE_URL
  SUPABASE_SEED_KEY

The database must temporarily expose RPC:
  public.temporary_seed_content_block_embeddings(payload jsonb)

The RPC is intentionally created and dropped outside this script so the
database-side privilege window is explicit and auditable.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Iterable

from openai import OpenAI
from supabase import create_client


ROOT = Path(__file__).resolve().parent
STRUCTURED = ROOT / "structured"
CACHE_PATH = STRUCTURED / "content-block-embeddings.jsonl"

MODEL = os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
DIMENSIONS = int(os.environ.get("OPENAI_EMBEDDING_DIMENSIONS", "1536"))
EMBED_BATCH = int(os.environ.get("EMBED_BATCH", "96"))
UPDATE_BATCH = int(os.environ.get("UPDATE_BATCH", "96"))


def load_blocks() -> list[dict]:
    blocks = json.loads((STRUCTURED / "block-index.json").read_text(encoding="utf-8"))
    rows: list[dict] = []
    for block_id, block in blocks.items():
        text = (block.get("text") or "").strip()
        if not text:
            continue
        prefix = (
            f"Book {block['book']}, Stage {block['stage']}, "
            f"Lesson {block.get('lesson')}, "
            f"Book page {block.get('book_page')}, "
            f"PDF page {block['pdf_page']}, "
            f"Type {block['type']}.\n"
        )
        rows.append({"id": block_id, "input": prefix + text})
    rows.sort(key=lambda r: r["id"])
    return rows


def read_cache() -> dict[str, list[float]]:
    out: dict[str, list[float]] = {}
    if not CACHE_PATH.exists():
        return out
    with CACHE_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            item = json.loads(line)
            out[item["id"]] = item["embedding"]
    return out


def append_cache(items: Iterable[dict]) -> None:
    with CACHE_PATH.open("a", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")


def chunks(items: list[dict], size: int) -> Iterable[list[dict]]:
    for i in range(0, len(items), size):
        yield items[i:i + size]


def vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{v:.8g}" for v in values) + "]"


def main() -> None:
    url = os.environ.get("SUPABASE_URL")
    seed_key = os.environ.get("SUPABASE_SEED_KEY")
    if not url or not seed_key:
        raise SystemExit("Set SUPABASE_URL and SUPABASE_SEED_KEY.")
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Set OPENAI_API_KEY.")

    blocks = load_blocks()
    cache = read_cache()
    missing = [row for row in blocks if row["id"] not in cache]

    print(f"Embedding model: {MODEL}, dimensions: {DIMENSIONS}")
    print(f"Content blocks with text: {len(blocks)}")
    print(f"Cached embeddings: {len(cache)}")
    print(f"Embeddings to generate: {len(missing)}")

    openai = OpenAI()
    generated = 0
    for batch in chunks(missing, EMBED_BATCH):
        response = openai.embeddings.create(
            model=MODEL,
            input=[row["input"] for row in batch],
            dimensions=DIMENSIONS,
        )
        items = [
            {"id": row["id"], "embedding": emb.embedding}
            for row, emb in zip(batch, response.data)
        ]
        append_cache(items)
        cache.update({item["id"]: item["embedding"] for item in items})
        generated += len(items)
        print(f"Generated {generated}/{len(missing)}")
        time.sleep(0.05)

    supabase = create_client(url, seed_key)
    seeded = 0
    rows = [{"id": row["id"], "embedding": cache[row["id"]]} for row in blocks if row["id"] in cache]
    for batch in chunks(rows, UPDATE_BATCH):
        payload = [
            {"id": row["id"], "embedding": vector_literal(row["embedding"])}
            for row in batch
        ]
        result = supabase.rpc("temporary_seed_content_block_embeddings", {"payload": payload}).execute()
        seeded += int(result.data or 0)
        print(f"Seeded {seeded}/{len(rows)}")

    print("Embedding seed complete.")


if __name__ == "__main__":
    main()
