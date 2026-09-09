"""Remove leftover ad-hoc test data (카엘/세라핀/오린) from the database.

These three characters, their scenes, timeline events, and relationships were
created by manually exercising the pipeline during development (they do not
appear anywhere in data/honggildongjeon_scenes.json or the canonical dataset).
Before publishing the project, this data should not be mixed in with the real
홍길동전 seed data shown in the demo UI.

Usage:
    python3 scripts/cleanup_test_characters.py --dry-run   # report only, no changes
    python3 scripts/cleanup_test_characters.py             # back up + delete

A JSON backup of every row removed is written to data/backups/ before any
deletion, so the operation can be reversed by hand if needed.

Run this with the backend server stopped (it writes directly to narrativeos.db).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, UTC
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.database.session import SessionLocal  # noqa: E402
from backend.database.models.character import Character  # noqa: E402
from backend.database.models.scene import Scene  # noqa: E402
from backend.database.models.timeline_event import TimelineEvent  # noqa: E402
from backend.database.models.relationship import Relationship  # noqa: E402

TEST_NAMES = ["카엘", "세라핀", "오린"]


def _row_to_dict(obj) -> dict:
    d = {}
    for col in obj.__table__.columns:
        val = getattr(obj, col.name)
        if isinstance(val, datetime):
            val = val.isoformat()
        d[col.name] = val
    return d


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Report what would be deleted, without changing anything")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        characters = db.query(Character).filter(Character.name.in_(TEST_NAMES)).all()
        char_ids = [c.id for c in characters]

        scenes = db.query(Scene).filter(Scene.title == "카엘의 결심").all()

        def event_matches(ev: TimelineEvent) -> bool:
            blob = (ev.title or "") + " " + (ev.description or "") + " " + json.dumps(ev.metadata_json or {}, ensure_ascii=False)
            return any(n in blob for n in TEST_NAMES)

        events = [e for e in db.query(TimelineEvent).all() if event_matches(e)]

        relationships = []
        if char_ids:
            relationships = db.query(Relationship).filter(
                (Relationship.source.in_(char_ids)) | (Relationship.target.in_(char_ids))
            ).all()

        print(f"characters : {len(characters)}  ({[c.name for c in characters]})")
        print(f"scenes     : {len(scenes)}")
        print(f"timeline   : {len(events)}")
        print(f"relations  : {len(relationships)}")

        if args.dry_run:
            print("\n--dry-run: no changes made.")
            return

        if not (characters or scenes or events or relationships):
            print("\nNothing to clean up.")
            return

        backup = {
            "removed_at": datetime.now(UTC).isoformat(),
            "characters": [_row_to_dict(c) for c in characters],
            "scenes": [_row_to_dict(s) for s in scenes],
            "timeline_events": [_row_to_dict(e) for e in events],
            "relationships": [_row_to_dict(r) for r in relationships],
        }
        backup_dir = ROOT / "data" / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = backup_dir / f"test_character_cleanup_{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}.json"
        backup_path.write_text(json.dumps(backup, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(f"\nBackup written to {backup_path}")

        for r in relationships:
            db.delete(r)
        for e in events:
            db.delete(e)
        for s in scenes:
            db.delete(s)
        for c in characters:
            db.delete(c)
        db.commit()

        print("Deleted.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
