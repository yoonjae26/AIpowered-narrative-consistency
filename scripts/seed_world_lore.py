#!/usr/bin/env python3
"""
홍길동전 세계관 설정 lore seed script

Parses data/documents/files/101eb334_세계관_설정.txt into structured
(key, value, source, tags) lore facts and writes them via LoreRepository,
so GET /narrative/world/lore (and the 세계관 view in the demo UI) is no
longer empty.

Usage:
    python3 scripts/seed_world_lore.py             (print only, no DB write)
    python3 scripts/seed_world_lore.py --write      (write to DB)
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SOURCE_FILE = ROOT / "data" / "documents" / "files" / "101eb334_세계관_설정.txt"
SOURCE_LABEL = "세계관_설정.txt"

_KEY_TERM = re.compile(r"^([가-힣A-Za-z0-9]+(?:\([^)]*\))?)")


def _derive_key(item: str) -> str:
    match = _KEY_TERM.match(item)
    return match.group(1) if match else item[:16]


def parse_lore_facts(text: str) -> list[dict]:
    """Parse the world-setting document into lore facts.

    Format handled:
      - top-level "라벨: 값" lines -> one fact tagged with the document title
      - a bare line -> starts a new section (used as a tag)
      - "- 항목" lines under a section -> "용어: 설명" split on ':'/'：' when
        present, otherwise the item text itself becomes both key and value
    """
    lines = [line.rstrip() for line in text.strip("\n").split("\n")]
    if not lines:
        return []

    title = lines[0].strip()
    facts: list[dict] = []
    current_section: str | None = None

    for raw in lines[1:]:
        line = raw.strip()
        if not line:
            continue

        if line.startswith("- "):
            item = line[2:].strip()
            sep = "：" if "：" in item else (":" if ":" in item else None)
            if sep:
                key, _, value = item.partition(sep)
                key, value = key.strip(), value.strip()
            else:
                key, value = _derive_key(item), item
            facts.append({
                "key": key,
                "value": value,
                "source": SOURCE_LABEL,
                "tags": [current_section] if current_section else [],
            })
            continue

        sep = "：" if "：" in line else (":" if ":" in line else None)
        if sep:
            key, _, value = line.partition(sep)
            facts.append({
                "key": key.strip(),
                "value": value.strip(),
                "source": SOURCE_LABEL,
                "tags": [title],
            })
            continue

        # bare line with no ':' and no leading '- ' -> section header
        current_section = line

    return facts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Write facts to the DB (default: dry-run print only)")
    args = parser.parse_args()

    if not SOURCE_FILE.exists():
        print(f"Source file not found: {SOURCE_FILE}")
        sys.exit(1)

    text = SOURCE_FILE.read_text(encoding="utf-8")
    facts = parse_lore_facts(text)

    print(f"Parsed {len(facts)} lore facts from {SOURCE_FILE.name}")
    for f in facts:
        tag_str = f"[{', '.join(f['tags'])}]" if f["tags"] else ""
        print(f"  {f['key']!r:28s} = {f['value']!r} {tag_str}")

    if not args.write:
        print("\n(dry-run; pass --write to save to the database)")
        return

    from backend.database.session import get_db_session
    from backend.database.repositories.lore_repository import LoreRepository

    gen = get_db_session()
    db = next(gen)
    try:
        repo = LoreRepository(db)
        for f in facts:
            repo.upsert(f["key"], f["value"], source=f["source"], tags=f["tags"])
        print(f"\nWrote {len(facts)} lore facts to the database.")
    finally:
        gen.close()


if __name__ == "__main__":
    main()
