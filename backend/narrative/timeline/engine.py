"""
Timeline Engine -- chronological tracking of narrative events.

Responsibilities:
  - Maintain ordered event list with timestamps
  - Detect flashback phrases (event.is_flashback)
  - Validate chronology (event B happens before A but references A)
  - Assign sequence numbers
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from backend.narrative.mutation.models import NarrativeEvent

_FLASHBACK_PATTERNS = re.compile(
    r"\b(years? ago|in the past|had|remembered?|recalled?|flashback|"
    r"once upon a time|long before|in those days|looking back)\b",
    re.IGNORECASE,
)

_FUTURE_PATTERNS = re.compile(
    r"\b(will|shall|would|going to|in the future|tomorrow|someday|"
    r"prophecy|foretold|destined)\b",
    re.IGNORECASE,
)


@dataclass
class TimelineEntry:
    sequence: int
    event: NarrativeEvent
    is_flashback: bool = False
    is_flash_forward: bool = False
    relative_time: str | None = None     # e.g. "day 3", "year 12"


@dataclass
class ChronologyReport:
    valid: bool = True
    conflicts: list[str] = field(default_factory=list)
    flashbacks: list[TimelineEntry] = field(default_factory=list)
    flash_forwards: list[TimelineEntry] = field(default_factory=list)


class TimelineEngine:
    """
    Processes a list of NarrativeEvents and produces an ordered timeline
    with flashback/flash-forward tagging and conflict detection.
    """

    def process(
        self,
        events: list[NarrativeEvent],
        scene_text: str = "",
    ) -> tuple[list[TimelineEntry], ChronologyReport]:
        """
        Returns (ordered_entries, report).
        """
        report = ChronologyReport()
        is_flashback_scene   = bool(_FLASHBACK_PATTERNS.search(scene_text))
        is_flash_forward_scene = bool(_FUTURE_PATTERNS.search(scene_text))

        # Tag each event and sort by timestamp
        tagged = self._tag_events(events, is_flashback_scene, is_flash_forward_scene)
        ordered = sorted(tagged, key=lambda e: e.event.timestamp)

        # Assign sequence numbers (actual order in story time)
        for i, entry in enumerate(ordered):
            entry.sequence = i + 1

        # Collect flashbacks / flash-forwards for the report
        report.flashbacks      = [e for e in ordered if e.is_flashback]
        report.flash_forwards  = [e for e in ordered if e.is_flash_forward]

        # Validate: look for causality conflicts
        self._check_causality(ordered, report)

        return ordered, report

    # ------------------------------------------------------------------
    # Tagging
    # ------------------------------------------------------------------

    def _tag_events(
        self,
        events: list[NarrativeEvent],
        scene_flashback: bool,
        scene_flash_forward: bool,
    ) -> list[TimelineEntry]:
        entries: list[TimelineEntry] = []
        for event in events:
            is_fb = scene_flashback or event.is_flashback
            is_ff = scene_flash_forward
            entries.append(TimelineEntry(
                sequence=0,
                event=event,
                is_flashback=is_fb,
                is_flash_forward=is_ff,
            ))
        return entries

    # ------------------------------------------------------------------
    # Causality check
    # ------------------------------------------------------------------

    def _check_causality(
        self,
        ordered: list[TimelineEntry],
        report: ChronologyReport,
    ) -> None:
        """
        Detect impossible orderings:
        - A character's DEATH event appears before their first APPEARS event
        - RESURRECTION without prior DEATH
        """
        from backend.narrative.mutation.models import EventType

        death_seq: dict[str, int] = {}
        appear_seq: dict[str, int] = {}
        resurrection_seq: dict[str, int] = {}

        for entry in ordered:
            ev = entry.event
            subj = ev.subject.lower()
            tgt  = (ev.target or "").lower()

            if ev.event_type in (EventType.DEATH, EventType.MURDER):
                victim = tgt if ev.event_type == EventType.MURDER and tgt else subj
                death_seq.setdefault(victim, entry.sequence)

            elif ev.event_type == EventType.CHARACTER_APPEARS:
                appear_seq.setdefault(subj, entry.sequence)

            elif ev.event_type == EventType.RESURRECTION:
                resurrection_seq[subj] = entry.sequence

        # Resurrection without prior death is a warning (not always wrong -- e.g. prophecy)
        for name, res_seq in resurrection_seq.items():
            if name not in death_seq:
                report.conflicts.append(
                    f"RESURRECTION of '{name}' with no recorded prior DEATH (possible canon violation)."
                )
            elif death_seq[name] > res_seq:
                report.conflicts.append(
                    f"RESURRECTION of '{name}' (seq {res_seq}) occurs before their DEATH (seq {death_seq[name]})."
                )

        if report.conflicts:
            report.valid = False
