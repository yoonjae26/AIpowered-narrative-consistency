from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import Any

from backend.database.repositories.character_repository import CharacterRepository
from backend.narrative.mutation.models import EventType, NarrativeEvent


_TRAIT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(aggressive|violent)\b", re.IGNORECASE), "aggressive"),
    (re.compile(r"\b(tall|huge)\b", re.IGNORECASE), "tall"),
    (re.compile(r"\b(pretty|beautiful|attractive)\b", re.IGNORECASE), "pretty"),
    (re.compile(r"\b(funny|humorous)\b", re.IGNORECASE), "funny"),
    (re.compile(r"\b(cute)\b", re.IGNORECASE), "cute"),
    (re.compile(r"\b(lively|energetic|active)\b", re.IGNORECASE), "lively"),
    (re.compile(r"\b(handsome)\b", re.IGNORECASE), "handsome"),
    (re.compile(r"\b(proactive)\b", re.IGNORECASE), "proactive"),
    (re.compile(r"\b(bad|evil|mean)\b", re.IGNORECASE), "bad"),
    (re.compile(r"\b(kind|gentle|nice)\b", re.IGNORECASE), "kind"),
    (re.compile(r"\b(scary|frightening)\b", re.IGNORECASE), "scary"),
    (re.compile(r"\b(crazy|insane)\b", re.IGNORECASE), "unstable"),
    (re.compile(r"\b(angry|furious)\b", re.IGNORECASE), "angry"),
    (re.compile(r"\b미친\b"), "unstable"),
    (re.compile(r"\b성격이\s*이상한\b"), "eccentric"),
    (re.compile(r"\b난폭한\b"), "aggressive"),
    (re.compile(r"\b키가\s*큰\b"), "tall"),
    (re.compile(r"예쁘|아름답|매력적"), "pretty"),
    (re.compile(r"재밌|재미있|웃기"), "funny"),
    (re.compile(r"귀엽"), "cute"),
    (re.compile(r"활발"), "lively"),
    (re.compile(r"잘\s*생겼|잘생겼|훈훈"), "handsome"),
    (re.compile(r"적극적"), "proactive"),
    (re.compile(r"나쁘|악하|못되"), "bad"),
    (re.compile(r"착하|친절"), "kind"),
    (re.compile(r"무섭"), "scary"),
    (re.compile(r"화나|분노|격노"), "angry"),
]


@dataclass(slots=True)
class CharacterMemoryState:
    personality: list[str] = field(default_factory=list)
    beliefs: list[str] = field(default_factory=list)
    knowledge: list[str] = field(default_factory=list)
    desires: list[str] = field(default_factory=list)
    trait_events: list[dict[str, object]] = field(default_factory=list)
    pending_trait_events: list[dict[str, object]] = field(default_factory=list)

    def as_dict(self) -> dict[str, list[str]]:
        deduped_traits: list[dict[str, object]] = []
        seen = set()
        for item in self.trait_events:
            key = (str(item.get("trait")), str(item.get("source_scene")), str(item.get("timestamp")))
            if key in seen:
                continue
            seen.add(key)
            deduped_traits.append(item)

        deduped_pending: list[dict[str, object]] = []
        pending_seen = set()
        for item in self.pending_trait_events:
            key = (str(item.get("trait")), str(item.get("source_scene")), str(item.get("timestamp")))
            if key in pending_seen:
                continue
            pending_seen.add(key)
            deduped_pending.append(item)
        return {
            "personality": list(dict.fromkeys(self.personality)),
            "beliefs": list(dict.fromkeys(self.beliefs)),
            "knowledge": list(dict.fromkeys(self.knowledge)),
            "desires": list(dict.fromkeys(self.desires)),
            "trait_events": deduped_traits[-80:],
            "pending_trait_events": deduped_pending[-120:],
        }


class CharacterMemorySystem:
    """Persistent PKBD memory stored in Character.metadata_json['memory']."""

    def __init__(
        self,
        character_repo: CharacterRepository,
        confidence_threshold: float = 0.72,
        pending_threshold: float = 0.35,
        promotion_min_occurrences: int = 2,
        promotion_min_distinct_scenes: int = 2,
        promotion_min_average_confidence: float = 0.45,
    ) -> None:
        self._characters = character_repo
        self._confidence_threshold = confidence_threshold
        self._pending_threshold = pending_threshold
        self._promotion_min_occurrences = promotion_min_occurrences
        self._promotion_min_distinct_scenes = promotion_min_distinct_scenes
        self._promotion_min_average_confidence = promotion_min_average_confidence

    def get_memory(self, character_name: str) -> CharacterMemoryState:
        character = self._find_character(character_name)
        if character is None:
            return CharacterMemoryState()
        metadata = character.metadata_json or {}
        memory = metadata.get("memory", {}) if isinstance(metadata, dict) else {}
        return CharacterMemoryState(
            personality=list(memory.get("personality", [])),
            beliefs=list(memory.get("beliefs", [])),
            knowledge=list(memory.get("knowledge", [])),
            desires=list(memory.get("desires", [])),
            trait_events=list(memory.get("trait_events", [])),
            pending_trait_events=list(memory.get("pending_trait_events", [])),
        )

    def update_from_events(self, events: list[NarrativeEvent]) -> dict[str, CharacterMemoryState]:
        updated: dict[str, CharacterMemoryState] = {}
        for event in events:
            if self._find_character(event.subject) is None:
                continue
            memory = self.get_memory(event.subject)
            self._apply_subject_event(memory, event)
            self._persist(event.subject, memory)
            updated[event.subject] = memory
            if event.target and self._find_character(event.target) is not None:
                target_memory = self.get_memory(event.target)
                self._apply_target_event(target_memory, event)
                self._persist(event.target, target_memory)
                updated[event.target] = target_memory
        return updated

    def _apply_subject_event(self, memory: CharacterMemoryState, event: NarrativeEvent) -> None:
        if event.event_type == EventType.MURDER:
            memory.knowledge.append(f"committed murder of {event.target}")
        elif event.event_type == EventType.DISCOVERY:
            memory.knowledge.append(event.predicate)
        elif event.event_type == EventType.TRAVEL and event.location:
            memory.knowledge.append(f"visited {event.location}")
        elif event.event_type == EventType.ALLIANCE and event.target:
            memory.beliefs.append(f"trusts {event.target}")
        elif event.event_type == EventType.BETRAYAL and event.target:
            memory.beliefs.append(f"betrayed {event.target}")
        elif event.event_type == EventType.CONFLICT and event.target:
            memory.beliefs.append(f"in conflict with {event.target}")
        self._append_from_attributes(memory, event.attributes)
        self._append_trait_events(memory, event.subject, event)

    def _apply_target_event(self, memory: CharacterMemoryState, event: NarrativeEvent) -> None:
        if event.event_type == EventType.MURDER and event.subject:
            memory.knowledge.append(f"was murdered by {event.subject}")
        elif event.event_type == EventType.INJURY and event.subject:
            memory.knowledge.append(f"was injured by {event.subject}")
        elif event.event_type == EventType.MARRIAGE and event.subject:
            memory.beliefs.append(f"married to {event.subject}")
        elif event.event_type == EventType.ALLIANCE and event.subject:
            memory.beliefs.append(f"allied with {event.subject}")

    def _append_from_attributes(self, memory: CharacterMemoryState, attributes: dict[str, Any]) -> None:
        if not isinstance(attributes, dict):
            return
        role = attributes.get("role")
        emotion = attributes.get("emotion")
        action = attributes.get("action")
        desire = attributes.get("desire")
        belief = attributes.get("belief")
        if isinstance(role, str) and role:
            memory.personality.append(role)
        if isinstance(emotion, str) and emotion:
            memory.personality.append(f"emotion:{emotion}")
        if isinstance(action, str) and action:
            memory.knowledge.append(action)
        if isinstance(desire, str) and desire:
            memory.desires.append(desire)
        if isinstance(belief, str) and belief:
            memory.beliefs.append(belief)
        trait = attributes.get("trait")
        relation_type = attributes.get("relation_type")
        confidence = float(attributes.get("semantic_confidence") or attributes.get("confidence") or 0.65)
        if isinstance(trait, str) and trait and confidence >= self._confidence_threshold:
            memory.personality.append(trait)
        if relation_type == "has_emotion" and isinstance(emotion, str) and emotion and confidence >= self._confidence_threshold:
            memory.personality.append(f"emotion:{emotion}")

    def _append_trait_events(self, memory: CharacterMemoryState, subject: str, event: NarrativeEvent) -> None:
        direct_trait = str(event.attributes.get("trait") or "").strip()
        direct_emotion = str(event.attributes.get("emotion") or "").strip()
        relation_type = str(event.attributes.get("relation_type") or "").strip() or "has_trait"
        confidence = float(event.attributes.get("semantic_confidence") or event.attributes.get("confidence") or 0.65)
        if direct_trait:
            self._append_semantic_payload(
                memory,
                {
                    "trait": direct_trait,
                    "surface": str(event.attributes.get("surface_descriptor") or event.predicate),
                    "confidence": confidence,
                    "source_scene": event.source_scene or "",
                    "timestamp": event.timestamp.isoformat() if hasattr(event.timestamp, "isoformat") else datetime.now(timezone.utc).isoformat(),
                    "character": subject,
                    "relation": relation_type,
                    "provisional": bool(event.attributes.get("provisional") or False),
                },
                confidence,
            )
        if direct_emotion:
            self._append_semantic_payload(
                memory,
                {
                    "trait": direct_emotion,
                    "surface": str(event.attributes.get("surface_descriptor") or event.predicate),
                    "confidence": confidence,
                    "source_scene": event.source_scene or "",
                    "timestamp": event.timestamp.isoformat() if hasattr(event.timestamp, "isoformat") else datetime.now(timezone.utc).isoformat(),
                    "character": subject,
                    "relation": "has_emotion",
                    "provisional": bool(event.attributes.get("provisional") or False),
                },
                confidence,
            )

        text_sources = [
            event.predicate,
            str(event.attributes.get("trait") or ""),
            str(event.attributes.get("personality") or ""),
            str(event.attributes.get("emotion") or ""),
        ]
        for text in text_sources:
            if not text:
                continue
            for pattern, canonical_trait in _TRAIT_PATTERNS:
                if not pattern.search(text):
                    continue
                inferred_confidence = float(event.attributes.get("confidence") or 0.65)
                self._append_semantic_payload(
                    memory,
                    {
                        "trait": canonical_trait,
                        "surface": text,
                        "confidence": inferred_confidence,
                        "source_scene": event.source_scene or "",
                        "timestamp": event.timestamp.isoformat() if hasattr(event.timestamp, "isoformat") else datetime.now(timezone.utc).isoformat(),
                        "character": subject,
                        "relation": relation_type,
                        "provisional": bool(event.attributes.get("provisional") or False),
                    },
                    inferred_confidence,
                )

    def _append_semantic_payload(
        self,
        memory: CharacterMemoryState,
        payload: dict[str, object],
        confidence: float,
    ) -> None:
        if confidence >= self._confidence_threshold:
            memory.trait_events.append(payload)
            return
        if confidence >= self._pending_threshold:
            memory.pending_trait_events.append(payload)

    def _persist(self, character_name: str, memory: CharacterMemoryState) -> None:
        character = self._find_character(character_name)
        if character is None:
            return
        metadata = dict(character.metadata_json or {})
        metadata["memory"] = memory.as_dict()
        self._characters.upsert(character.id, {"metadata": metadata})

    def promote_pending_traits(self) -> dict[str, object]:
        promoted_entries = 0
        promoted_characters = 0

        for character in self._characters.list():
            memory = self.get_memory(character.name)
            grouped: dict[tuple[str, str], list[dict[str, object]]] = {}
            for item in memory.pending_trait_events:
                trait = str(item.get("trait") or "").strip()
                relation = str(item.get("relation") or "has_trait").strip() or "has_trait"
                if not trait:
                    continue
                grouped.setdefault((relation, trait), []).append(item)

            if not grouped:
                continue

            keep_pending: list[dict[str, object]] = []
            promoted_for_character = 0

            for (relation, trait), items in grouped.items():
                scenes = {
                    str(item.get("source_scene") or "").strip().lower()
                    for item in items
                    if str(item.get("source_scene") or "").strip()
                }
                avg_conf = sum(float(item.get("confidence") or 0.0) for item in items) / max(len(items), 1)
                should_promote = (
                    len(items) >= self._promotion_min_occurrences
                    and len(scenes) >= self._promotion_min_distinct_scenes
                    and avg_conf >= self._promotion_min_average_confidence
                )

                if should_promote:
                    promoted_for_character += len(items)
                    for item in items:
                        promoted_payload = dict(item)
                        promoted_payload["promoted"] = True
                        promoted_payload["promotion_reason"] = (
                            f"occurrences>={self._promotion_min_occurrences}, "
                            f"scenes>={self._promotion_min_distinct_scenes}, "
                            f"avg_conf={avg_conf:.2f}"
                        )
                        memory.trait_events.append(promoted_payload)
                    if relation == "has_emotion":
                        memory.personality.append(f"emotion:{trait}")
                    else:
                        memory.personality.append(trait)
                else:
                    keep_pending.extend(items)

            if promoted_for_character == 0:
                continue

            memory.pending_trait_events = keep_pending
            self._persist(character.name, memory)
            promoted_entries += promoted_for_character
            promoted_characters += 1

        return {
            "promoted_entries": promoted_entries,
            "promoted_characters": promoted_characters,
            "rules": {
                "min_occurrences": self._promotion_min_occurrences,
                "min_distinct_scenes": self._promotion_min_distinct_scenes,
                "min_average_confidence": self._promotion_min_average_confidence,
            },
        }

    def confidence_histogram(
        self,
        character_name: str | None = None,
        bucket_size: float = 0.1,
    ) -> dict[str, object]:
        if bucket_size <= 0:
            bucket_size = 0.1

        characters = [
            character
            for character in self._characters.list()
            if character_name is None or character.name.lower() == character_name.lower()
        ]

        by_character: dict[str, dict[str, object]] = {}
        for character in characters:
            memory = self.get_memory(character.name)
            permanent = list(memory.trait_events)
            pending = list(memory.pending_trait_events)

            by_character[character.name] = {
                "permanent": self._histogram_for_items(permanent, bucket_size),
                "pending": self._histogram_for_items(pending, bucket_size),
                "counts": {
                    "permanent": len(permanent),
                    "pending": len(pending),
                },
            }

        return {
            "bucket_size": bucket_size,
            "character_count": len(by_character),
            "characters": by_character,
        }

    def _histogram_for_items(self, items: list[dict[str, object]], bucket_size: float) -> list[dict[str, object]]:
        buckets: dict[str, int] = {}
        for item in items:
            confidence = float(item.get("confidence") or 0.0)
            confidence = max(0.0, min(1.0, confidence))
            start = (int(confidence / bucket_size) * bucket_size)
            end = min(1.0, start + bucket_size)
            label = f"{start:.2f}-{end:.2f}"
            buckets[label] = buckets.get(label, 0) + 1

        return [
            {"bucket": bucket, "count": count}
            for bucket, count in sorted(buckets.items(), key=lambda item: float(item[0].split("-")[0]))
        ]

    def _find_character(self, character_name: str):
        for character in self._characters.list():
            if character.name.lower() == character_name.lower():
                return character
        return None
