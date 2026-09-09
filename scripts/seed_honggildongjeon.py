#!/usr/bin/env python3
"""
홍길동전 scene seed script
Usage:
    python3 scripts/seed_honggildongjeon.py
    python3 scripts/seed_honggildongjeon.py --dry-run   (print only, no DB write)
    python3 scripts/seed_honggildongjeon.py --clear      (delete existing scenes first)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DATA_FILE = ROOT / "data" / "honggildongjeon_scenes.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed 홍길동전 scenes into NarrativeOS DB")
    parser.add_argument("--dry-run", action="store_true", help="Print scenes only, no DB write")
    parser.add_argument("--clear", action="store_true", help="Delete all existing scenes before seeding")
    args = parser.parse_args()

    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    scenes = data["scenes"]
    print(f"Loaded {len(scenes)} scenes from {DATA_FILE.name}")

    if args.dry_run:
        for s in scenes:
            print(f"  [{s['seq']:02d}] {s['title']}")
            print(f"       Characters: {', '.join(s['characters'])}")
            print(f"       Location  : {s['location']}")
            print(f"       Beats     : {len(s['beats'])} beats")
        return

    # DB setup
    from backend.database.session import get_db_session
    from backend.database.repositories.scene_repository import SceneRepository
    from sqlalchemy.orm import Session

    gen = get_db_session()
    db = next(gen)
    try:
        repo = SceneRepository(db, commit_on_write=False)

        if args.clear:
            from backend.database.models.scene import Scene
            deleted = db.query(Scene).delete()
            db.flush()
            print(f"Deleted {deleted} existing scenes.")

        created = 0
        skipped = 0
        for s in scenes:
            existing = repo.get_by_title(s["title"])
            if existing is not None:
                print(f"  SKIP [{s['seq']:02d}] {s['title']} (already exists)")
                skipped += 1
                continue
            repo.create(
                title=s["title"],
                summary=s["summary"],
                beats=s["beats"],
                characters=s["characters"],
            )
            print(f"  +    [{s['seq']:02d}] {s['title']}")
            created += 1

        db.commit()
        print(f"\nDone. Created: {created}, Skipped: {skipped}")
    finally:
        try:
            next(gen)
        except StopIteration:
            pass


if __name__ == "__main__":
    main()
