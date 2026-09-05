"""
Parses transcripts under backend/data/transcripts/, chunks them, generates
embeddings, and stores them in transcript_chunks. Re-runnable CLI script per
locked decision (no Celery/Redis background job).

Parsing: each file is YAML frontmatter (guest, title, publish_date,
youtube_url) + a Markdown body of `Speaker (HH:MM:SS):\ntext` turns. Only
frontmatter fields actually present are used — missing fields are left null
and logged, never fabricated (hard constraint).

Chunking: paragraph-aware recursive splitting — accumulate consecutive
transcript turns until the running token count reaches chunk_target_tokens,
then close the chunk and start the next one chunk_overlap_tokens back, so
each chunk keeps local context on both edges. Token counts are approximated
as whitespace-split word count * 1.3 (a standard words-to-tokens ratio for
English) rather than via a real tokenizer such as tiktoken — tiktoken's
encoding files are fetched from openaipublic.blob.core.windows.net at first
use, an external host outside this project's declared dependencies, which
would silently break ingestion in any offline/restricted-network deployment
(exactly the failure this script is supposed to be defensive against); the
word-count approximation has no such runtime dependency and is precise
enough for a chunk-sizing heuristic, which doesn't need exact token counts.

Embedding: sentence-transformers/all-MiniLM-L6-v2 (384-dim), confirmed at
the start of this tier, run fully locally/offline.

Dedupe / idempotency strategy: DELETE all existing rows for a given
source_file, then INSERT the freshly computed chunks for that file, in one
transaction per file. Chosen over an upsert-by-key because chunk boundaries
can change if chunking parameters change between runs (e.g. adjusting
chunk_target_tokens) — an upsert keyed on stale chunk_index would leave
orphaned old chunks behind, whereas delete+insert always leaves exactly the
current chunking for that file. Re-running ingest.py against unchanged files
therefore reproduces the same row count, not duplicates.

Defensive: a malformed/unparseable file is logged and skipped, never fatal.
"""
import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml
from sentence_transformers import SentenceTransformer
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("scripts.ingest")

WORDS_TO_TOKENS_RATIO = 1.3


def count_tokens(s: str) -> int:
    return int(len(s.split()) * WORDS_TO_TOKENS_RATIO)


@dataclass
class Turn:
    speaker: Optional[str]
    locator: Optional[str]
    text: str


@dataclass
class Chunk:
    text: str
    locator: Optional[str]
    n_tokens: int


def parse_transcript(path: Path) -> tuple[dict, list[Turn]]:
    """Returns (frontmatter_dict, turns). Raises ValueError on malformed input."""
    raw = path.read_text(encoding="utf-8")
    parts = raw.split("---")
    if len(parts) < 3:
        raise ValueError("missing YAML frontmatter delimiters")

    frontmatter = yaml.safe_load(parts[1]) or {}
    body = "---".join(parts[2:])

    turns: list[Turn] = []
    current_speaker = None
    current_locator = None
    buf: list[str] = []

    def flush():
        if buf:
            joined = " ".join(buf).strip()
            if joined:
                turns.append(Turn(speaker=current_speaker, locator=current_locator, text=joined))
            buf.clear()

    import re
    turn_header = re.compile(r"^(?P<speaker>[^(\n]+?)\s*\((?P<ts>\d{1,2}:\d{2}(?::\d{2})?)\):\s*$")

    for line in body.splitlines():
        m = turn_header.match(line.strip())
        if m:
            flush()
            current_speaker = m.group("speaker").strip()
            current_locator = m.group("ts").strip()
            continue
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            continue
        buf.append(stripped)
    flush()

    if not turns:
        raise ValueError("no speaker turns found in body")

    return frontmatter, turns


def chunk_turns(turns: list[Turn], target_tokens: int, overlap_tokens: int) -> list[Chunk]:
    chunks: list[Chunk] = []
    i = 0
    n = len(turns)
    while i < n:
        acc_text: list[str] = []
        acc_tokens = 0
        start_locator = turns[i].locator
        j = i
        while j < n:
            t_text = f"{turns[j].speaker}: {turns[j].text}" if turns[j].speaker else turns[j].text
            t_tokens = count_tokens(t_text)
            if acc_tokens + t_tokens > target_tokens and acc_text:
                break
            acc_text.append(t_text)
            acc_tokens += t_tokens
            j += 1

        chunk_text = "\n".join(acc_text)
        chunks.append(Chunk(text=chunk_text, locator=start_locator, n_tokens=acc_tokens))

        if j >= n:
            break

        # Step back roughly overlap_tokens worth of turns for the next chunk's start.
        back_tokens = 0
        k = j - 1
        while k > i and back_tokens < overlap_tokens:
            t_text = f"{turns[k].speaker}: {turns[k].text}" if turns[k].speaker else turns[k].text
            back_tokens += count_tokens(t_text)
            k -= 1
        i = max(k + 1, i + 1)  # always make forward progress

    return chunks


async def ingest_file(session, model: SentenceTransformer, path: Path, settings) -> tuple[int, Optional[str]]:
    """Returns (chunks_inserted, error). error is None on success."""
    try:
        frontmatter, turns = parse_transcript(path)
    except Exception as exc:  # noqa: BLE001 — defensive per hard constraint
        return 0, str(exc)

    guest_name = frontmatter.get("guest")
    episode_title = frontmatter.get("title")
    if not episode_title:
        return 0, "missing required 'title' in frontmatter"
    if not guest_name:
        logger.warning("guest name missing in frontmatter, storing null", extra={"file": str(path)})

    chunks = chunk_turns(turns, settings.chunk_target_tokens, settings.chunk_overlap_tokens)
    if not chunks:
        return 0, "chunking produced zero chunks"

    texts = [c.text for c in chunks]
    embeddings = model.encode(texts, show_progress_bar=False, normalize_embeddings=True)

    source_file = str(path.relative_to(path.parents[2]))  # e.g. data/transcripts/<slug>/transcript.md

    async with session.begin():
        await session.execute(
            text("DELETE FROM transcript_chunks WHERE source_file = :source_file"),
            {"source_file": source_file},
        )
        for chunk, emb in zip(chunks, embeddings):
            await session.execute(
                text(
                    """
                    INSERT INTO transcript_chunks
                        (episode_title, guest_name, chunk_text, locator, embedding, source_file)
                    VALUES
                        (:episode_title, :guest_name, :chunk_text, :locator, :embedding, :source_file)
                    """
                ),
                {
                    "episode_title": episode_title,
                    "guest_name": guest_name,
                    "chunk_text": chunk.text,
                    "locator": chunk.locator,
                    "embedding": "[" + ",".join(f"{x:.8f}" for x in emb.tolist()) + "]",
                    "source_file": source_file,
                },
            )

    return len(chunks), None


async def run() -> None:
    settings = get_settings()
    transcripts_root = Path(__file__).resolve().parent.parent / settings.transcripts_dir
    files = sorted(transcripts_root.glob("*/transcript.md"))

    if not files:
        logger.error(
            "no transcript files found — run download_transcripts.py first",
            extra={"expected_dir": str(transcripts_root)},
        )
        return

    logger.info("loading embedding model", extra={"model": settings.embedding_model})
    model = SentenceTransformer(settings.embedding_model)

    processed, skipped, total_chunks = 0, 0, 0
    skip_reasons: list[tuple[str, str]] = []
    sample_rows: list[dict] = []

    async with AsyncSessionLocal() as session:
        for path in files:
            n_chunks, error = await ingest_file(session, model, path, settings)
            if error:
                skipped += 1
                skip_reasons.append((str(path), error))
                logger.warning("skipped file", extra={"file": str(path), "reason": error})
                continue
            processed += 1
            total_chunks += n_chunks
            logger.info("ingested file", extra={"file": str(path), "chunks": n_chunks})

        # Spot-check sample for the verification report.
        result = await session.execute(
            text(
                "SELECT episode_title, guest_name, locator, chunk_text, "
                "array_length(embedding::real[], 1) AS emb_len "
                "FROM transcript_chunks ORDER BY random() LIMIT 3"
            )
        )
        for row in result.fetchall():
            sample_rows.append(
                {
                    "episode": row.episode_title,
                    "guest": row.guest_name,
                    "locator": row.locator,
                    "snippet": row.chunk_text[:160],
                    "embedding_len": row.emb_len,
                }
            )

    logger.info(
        "ingestion complete",
        extra={
            "files_processed": processed,
            "files_skipped": skipped,
            "chunks_inserted": total_chunks,
        },
    )
    print("\n=== INGESTION REPORT ===")
    print(f"files processed: {processed}")
    print(f"files skipped:   {skipped}")
    for f, reason in skip_reasons:
        print(f"  - {f}: {reason}")
    print(f"chunks inserted: {total_chunks}")
    print("sample rows:")
    for row in sample_rows:
        print(f"  - episode={row['episode']!r} guest={row['guest']!r} locator={row['locator']!r} "
              f"embedding_len={row['embedding_len']}")
        print(f"    snippet: {row['snippet']!r}")


if __name__ == "__main__":
    asyncio.run(run())