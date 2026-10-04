"""
repo_intel — Repository Intelligence Engine: a commit → a queryable knowledge graph + code chunks.

    from engines.repo_intel.indexer import index_repository
    result = index_repository(root, all_paths=tree_paths)   # RepoIndex: graph, chunks, repo_model

Deterministic (no LLM). Python is parsed with the stdlib `ast` (exact); JS/TS/HTML/Vue/Svelte with
framework-aware patterns (routes, pages, fetch calls, forms, env vars, LLM SDK calls, tests); every other
source language (Java, Kotlin, Go, Rust, Ruby, PHP, C#, Swift, Dart, C/C++ …) with generic_parser.
files.py is the single definition of what is fetched/indexed/skipped (shared with tools/agent_eval/repo_scan.py).
"""

# Bump whenever graph semantics change (cached snapshots are keyed by it).
# 2.0: every source language indexed, NestJS / React-Router / SPA pages, JS tests, add_url_rule / add_api_route /
#      Django urls / Streamlit / Gradio entry points, server-only JS routes, repo_model["coverage"].
INDEXER_VERSION = "ri-2.0"
