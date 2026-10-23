# Callan Method Corpus & Clustering Pipeline

Python data-processing pipeline for parsing Callan Method textbooks (Stages 1–12), extracting Q&A structures, building vocabulary clusters, and generating vector embeddings.

## Key Scripts

- `extract_pymupdf.py` / `convert.py` — PDF-to-Markdown structural extraction
- `build_index.py` / `build_clusters_v2.py` — Fine-grained lesson & vocabulary cluster indexing
- `generate_content_block_embeddings.py` — Semantic vector embedding generation
- `audit_callan_structure.py` — Structural integrity verification
