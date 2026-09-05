# Tier 2 — Ingestion

**Ask:** populate `transcript_chunks` from Lenny's Podcast transcripts —
download a curated episode subset, parse, chunk, embed, store, and make
the whole thing idempotent and traceable back to source.

## What was actually built

- `backend/scripts/download_transcripts.py`: pulls a single tarball of
  the [ChatPRD Lenny's Podcast transcripts repo](https://github.com/ChatPRD/lennys-podcast-transcripts),
  extracts a frozen 30-episode `SELECTED_SLUGS` subset chosen for coverage
  across growth-strategy/product-led-growth/product-management/
  product-market-fit/retention/startup-growth topic files in that repo's
  own index, writes each to `backend/data/transcripts/<guest-slug>/
  transcript.md`, idempotent (skips existing files unless `--force`).
- `backend/scripts/ingest.py`: parses each file's YAML frontmatter and
  `Speaker (HH:MM:SS):` turns (missing fields stored `NULL` and logged,
  never fabricated), chunks by accumulating turns to a ~650-token target
  (500–800 range, ~100-token overlap), embeds with
  `sentence-transformers/all-MiniLM-L6-v2` (384-dim), deletes+re-inserts
  per `source_file` inside one transaction so re-running is safe, and
  prints a real ingestion report (files processed/skipped with reasons,
  chunks inserted, 3 random sample rows actually queried from the table).

**Verified:** both scripts re-viewed on disk immediately after writing —
the discipline applied throughout this project, and explicitly required
by this project's own working practice; ingestion run against a live
Postgres with Tier 1's migration applied; the printed sample rows
cross-checked against the actual `transcript_chunks` table via a direct
`SELECT`, not trusted from the script's own stdout alone.

**Not eventful.**