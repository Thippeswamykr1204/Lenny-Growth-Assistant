"""
Fetches the curated Tier 2 transcript subset into backend/data/transcripts/.

Source: https://github.com/ChatPRD/lennys-podcast-transcripts (public archive of
Lenny's Podcast transcripts, YAML frontmatter + Markdown body per episode).

Subset selection (traceable, not arbitrary): the repo ships an AI-generated
topic index (index/*.md). We selected the 30 episodes with the highest
combined appearance count across six growth/PM-relevant topic files —
growth-strategy, product-led-growth, product-management, product-market-fit,
retention, startup-growth — i.e. episodes that show up in the most
growth-relevant topics, not a random or alphabetical sample. That selection
is frozen below as SELECTED_SLUGS so re-running this script is deterministic.

Idempotent: episodes already present under transcripts_dir are skipped unless
--force is passed. Downloads the whole repo tarball once (single HTTP call)
and extracts only the selected episode files, rather than 30 separate
requests.
"""
import argparse
import logging
import shutil
import tarfile
import tempfile
from pathlib import Path

import httpx

from app.core.config import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("scripts.download_transcripts")

# Frozen selection — see module docstring for how this was derived.
SELECTED_SLUGS = [
    "sean-ellis", "nilan-peiris", "naomi-gleit", "merci-grace", "hila-qu",
    "emily-kramer", "crystal-w", "christopher-miller", "casey-winters",
    "zoelle-egner", "yamashata", "varun-parmar", "tim-holley",
    "shishir-mehrotra", "shaun-clowes", "sarah-tavel", "sachin-monga",
    "pete-kazanjy", "oji-udezue", "noam-lovinsky", "noah-weiss",
    "nikita-bier", "melissa-tan", "lauryn-isford", "laura-modi",
    "krithika-shankarraman", "karri-saarinen", "julian-shapiro",
    "jiaona-zhang", "jeanne-grosser",
]

TARBALL_URL = "https://codeload.github.com/ChatPRD/lennys-podcast-transcripts/tar.gz/refs/heads/main"
ARCHIVE_PREFIX = "lennys-podcast-transcripts-main/episodes"


def main(force: bool = False) -> None:
    settings = get_settings()
    dest_root = Path(__file__).resolve().parent.parent / settings.transcripts_dir
    dest_root.mkdir(parents=True, exist_ok=True)

    missing = [
        slug for slug in SELECTED_SLUGS
        if force or not (dest_root / slug / "transcript.md").exists()
    ]
    if not missing:
        logger.info(
            "all selected episodes already present, nothing to download",
            extra={"count": len(SELECTED_SLUGS), "dest": str(dest_root)},
        )
        return

    logger.info("downloading transcript archive", extra={"url": TARBALL_URL, "missing": len(missing)})
    with tempfile.TemporaryDirectory() as tmp:
        tarball_path = Path(tmp) / "archive.tar.gz"
        with httpx.stream("GET", TARBALL_URL, follow_redirects=True, timeout=60.0) as resp:
            resp.raise_for_status()
            with open(tarball_path, "wb") as f:
                for chunk in resp.iter_bytes():
                    f.write(chunk)

        with tarfile.open(tarball_path, "r:gz") as tar:
            for slug in missing:
                member_name = f"{ARCHIVE_PREFIX}/{slug}/transcript.md"
                try:
                    member = tar.getmember(member_name)
                except KeyError:
                    logger.warning("episode not found in archive, skipping", extra={"slug": slug})
                    continue

                extracted = tar.extractfile(member)
                if extracted is None:
                    logger.warning("could not read archive member, skipping", extra={"slug": slug})
                    continue

                target_dir = dest_root / slug
                target_dir.mkdir(parents=True, exist_ok=True)
                with open(target_dir / "transcript.md", "wb") as out:
                    shutil.copyfileobj(extracted, out)
                logger.info("downloaded episode", extra={"slug": slug})

    present = sum(1 for slug in SELECTED_SLUGS if (dest_root / slug / "transcript.md").exists())
    logger.info(
        "download complete",
        extra={"present": present, "expected": len(SELECTED_SLUGS), "dest": str(dest_root)},
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="re-download even if files already exist")
    args = parser.parse_args()
    main(force=args.force)