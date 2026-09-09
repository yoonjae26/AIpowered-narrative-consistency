"""
Consistency Engine v1 -- stage 5 of the pipeline.

Rules:
  R1. Dead character reappears without resurrection
  R2. Canon violation: resurrection in worlds where it is forbidden
  R3. Impossible location: same character in 2 places at same time
  R4. Timeline conflict: event order broken (delegated to TimelineEngine)
  R5. Orphan relationship: relationship references unknown character
  R6. Duplicate character names
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from backend.database.repositories.character_repository import CharacterRepository
from backend.database.repositories.relationship_repository import RelationshipRepository
from backend.narrative.mutation.models import (
    CharacterStatus,
    EventType,
    MutationResult,
    NarrativeEvent,
)
from backend.narrative.warnings.generator import NarrativeWarning, WarningSeverity, WarningGenerator

logger = logging.getLogger(__name__)

_warn_gen = WarningGenerator()


@dataclass
class ConsistencyReport:
    consistent: bool = True
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    structured_warnings: list[NarrativeWarning] = field(default_factory=list)

    def add_warning(self, msg: str, rule_id: str = "unknown",
                    entities: list[str] | None = None, scene: str | None = None) -> None:
        self.warnings.append(msg)
        self.structured_warnings.append(_warn_gen.make(
            rule_id, entities=entities, scene=scene))

    def add_error(self, msg: str, rule_id: str = "unknown",
                  entities: list[str] | None = None, scene: str | None = None) -> None:
        self.errors.append(msg)
        self.consistent = False
        self.structured_warnings.append(_warn_gen.make(
            rule_id, entities=entities, scene=scene))


class ConsistencyChecker:
    def __init__(
        self,
        character_repo: CharacterRepository,
        relationship_repo: RelationshipRepository,
        canon_rules: dict | None = None,
    ) -> None:
        self._characters    = character_repo
        self._relationships = relationship_repo
        # canon_rules: {"resurrection_forbidden": True, ...}
        self._canon         = canon_rules or {}

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def check(
        self,
        mutation_result: MutationResult,
        events: list[NarrativeEvent],
        scene_text: str = "",
        dry_run: bool = False,
    ) -> ConsistencyReport:
        report = ConsistencyReport()
        scene = next((e.source_scene for e in events if e.source_scene), None)

        # R1 relies on sequential DB state; skip in dry_run (isolation testing)
        # where DB may reflect future scenes not yet reached in story order.
        if not dry_run:
            self._r1_dead_reappears(events, report, scene)
        self._r2_canon_resurrection(events, report, scene)
        self._r3_impossible_location(events, report, scene)
        self._r5_orphan_relationships(events, report, scene)
        self._r6_duplicate_names(report, scene)

        # Propagate mutation-level warnings
        for w in mutation_result.consistency_warnings:
            report.warnings.append(f"[mutation] {w}")

        return report

    # ------------------------------------------------------------------
    # R1: Dead character reappears
    # ------------------------------------------------------------------

    def _r1_dead_reappears(
        self, events: list[NarrativeEvent], report: ConsistencyReport, scene: str | None
    ) -> None:
        all_chars = self._characters.list()

        # Names of living characters — used to suppress alias-confusion false positives.
        # e.g. '길동' stored as DEAD (short-name clone) should not block when '홍길동' is alive.
        alive_lowers: set[str] = {
            c.name.lower()
            for c in all_chars
            if (c.status or "").lower() != CharacterStatus.DEAD.value
        }

        dead_in_db = {
            c.name.lower(): c.name
            for c in all_chars
            if (c.status or "").lower() == CharacterStatus.DEAD.value
        }
        if not dead_in_db:
            return

        resurrection_in_events = {
            e.subject.lower()
            for e in events
            if e.event_type == EventType.RESURRECTION
        }

        for name_lower, canonical in dead_in_db.items():
            # Skip: this dead name is a suffix of an alive canonical name.
            # This prevents short-name alias deaths (e.g. '길동' from a clone arc)
            # from blocking scenes where the canonical character '홍길동' still lives.
            if any(
                alive.endswith(name_lower) and alive != name_lower and len(alive) > len(name_lower)
                for alive in alive_lowers
            ):
                continue

            appears = any(
                e.subject.lower() == name_lower and
                e.event_type in (EventType.CHARACTER_APPEARS, EventType.TRAVEL,
                                 EventType.CONFLICT, EventType.MURDER, EventType.DISCOVERY)
                for e in events
            )
            if appears and name_lower not in resurrection_in_events:
                report.add_error(
                    f"{canonical}은(는) ���미 사망한 인물로 기록되어 있으나 장면에 다시 등장합니다.",
                    rule_id="dead_character_reappears",
                    entities=[canonical],
                    scene=scene,
                )

    # ------------------------------------------------------------------
    # R2: Canon violation -- resurrection forbidden
    # ------------------------------------------------------------------

    def _r2_canon_resurrection(
        self, events: list[NarrativeEvent], report: ConsistencyReport, scene: str | None
    ) -> None:
        if not self._canon.get("resurrection_forbidden", False):
            return
        for event in events:
            if event.event_type == EventType.RESURRECTION:
                report.add_error(
                    f"{event.subject}의 부활은 세계관 규칙(부활 금지)에 위배될 수 있습니다.",
                    rule_id="canon_violation_resurrection",
                    entities=[event.subject],
                    scene=scene,
                )

    # ------------------------------------------------------------------
    # R3: Impossible location (same character in 2 places)
    # ------------------------------------------------------------------

    def _r3_impossible_location(
        self, events: list[NarrativeEvent], report: ConsistencyReport, scene: str | None
    ) -> None:
        # Only CHARACTER_APPEARS counts as the character being at a location.
        # TRAVEL = moving between locations (expected to have different from/to).
        # SCENE_OPENS = scene-level setting, not a character's specific position.
        PRESENCE_TYPES = (EventType.CHARACTER_APPEARS,)
        char_locations: dict[str, list[str]] = {}
        for event in events:
            if event.location and event.event_type in PRESENCE_TYPES:
                char_locations.setdefault(event.subject, [])
                if event.location not in char_locations[event.subject]:
                    char_locations[event.subject].append(event.location)

        for char, locs in char_locations.items():
            if len(locs) >= 2:
                report.add_error(
                    f"{char}이(가) 같은 시점에 두 장소({locs[0]}, {locs[1]})에 동시에 등장합니다.",
                    rule_id="impossible_location",
                    entities=[char],
                    scene=scene,
                )

    # ------------------------------------------------------------------
    # R5: Orphan relationships
    # ------------------------------------------------------------------

    def _r5_orphan_relationships(
        self, events: list[NarrativeEvent], report: ConsistencyReport, scene: str | None
    ) -> None:
        relationship_events = [
            e for e in events
            if e.event_type in {
                EventType.RELATIONSHIP_FORMS, EventType.RELATIONSHIP_CHANGES,
                EventType.MARRIAGE, EventType.BETRAYAL, EventType.ALLIANCE,
            }
        ]
        if not relationship_events:
            return

        known_names = {c.name.lower() for c in self._characters.list()}
        for event in relationship_events:
            for name in [event.subject, event.target]:
                if name and name.lower() not in known_names:
                    report.add_warning(
                        f"관계 이벤트가 캐릭터 데이터베이스에 존재하지 않는 인물 '{name}'을(를) 참조합니다.",
                        rule_id="orphan_relationship",
                        entities=[name],
                        scene=scene,
                    )

    # ------------------------------------------------------------------
    # R6: Duplicate names
    # ------------------------------------------------------------------

    def _r6_duplicate_names(
        self, report: ConsistencyReport, scene: str | None
    ) -> None:
        names: dict[str, list[str]] = {}
        for c in self._characters.list():
            names.setdefault(c.name.lower(), []).append(c.id)
        for name_lower, ids in names.items():
            if len(ids) > 1:
                report.add_warning(
                    f"동일한 이름 '{name_lower}'을(를) 가진 인물이 여럿 존재합니다. 일관성 오류가 발생할 수 있습니다.",
                    rule_id="duplicate_character_name",
                    entities=[name_lower],
                    scene=scene,
                )
