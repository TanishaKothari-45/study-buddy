"""
prelims_v2 — Question-First Prelims Pipeline

Stage 0  blueprint_generator    → LLM decides 20 question skeletons before retrieval
Stage 1  skeleton_retrieval      → Per-skeleton Pinecone + CA queries (parallel)
Stage 2  difficulty_injector     → Attach trap rules from trap registry (no LLM)
Stage 3  skeleton_generator      → One focused Gemini call per skeleton (parallel)
Stage 4  quality_gate            → Validate trap presence, CA in stem, diversity
Stage 5  gap_filler              → Re-run & shuffle; fallback to v1 if needed
"""
