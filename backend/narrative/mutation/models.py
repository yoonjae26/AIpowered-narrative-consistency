"""Data models shared across the Narrative State Mutation pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, UTC
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Character lifecycle status
# ---------------------------------------------------------------------------

class CharacterStatus(str, Enum):
    ALIVE   = "alive"
    DEAD    = "dead"
    INJURED = "injured"
    ABSENT  = "absent"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Event taxonomy
# ---------------------------------------------------------------------------

class EventType(str, Enum):
    # Presence
    CHARACTER_APPEARS   = "character_appears"
    CHARACTER_EXITS     = "character_exits"
    CHARACTER_CHANGES   = "character_changes"
    # Vital events
    DEATH               = "death"
    MURDER              = "murder"
    INJURY              = "injury"
    BIRTH               = "birth"
    RESURRECTION        = "resurrection"
    # Social events
    MARRIAGE            = "marriage"
    BETRAYAL            = "betrayal"
    ALLIANCE            = "alliance"
    CONFLICT            = "conflict"
    # Narrative events
    DISCOVERY           = "discovery"
    TRAVEL              = "travel"
    CAPTURE             = "capture"
    ESCAPE              = "escape"
    # World / scene
    SCENE_OPENS         = "scene_opens"
    SCENE_CLOSES        = "scene_closes"
    TIMELINE_BEAT       = "timeline_beat"
    WORLD_STATE_CHANGE  = "world_state_change"
    # Relationships
    RELATIONSHIP_FORMS  = "relationship_forms"
    RELATIONSHIP_CHANGES = "relationship_changes"
    # Dialogue
    DIALOGUE            = "dialogue"
    # KG / extractor outputs — NOT indexed in RAG memory
    CHAR_TRAIT          = "char_trait"
    CHAR_EMOTION        = "char_emotion"


# ---------------------------------------------------------------------------
# Content classification — one layer above EventType
# ---------------------------------------------------------------------------

class EventCategory(str, Enum):
    SCENE_ACTION        = "scene_action"       # narrative events worth RAG indexing
    DIALOGUE            = "dialogue"           # character speech
    RELATIONSHIP        = "relationship"       # social bonds
    TRAIT               = "trait"              # KG trait extractions (internal)
    EXTRACTOR_METADATA  = "extractor_metadata" # pipeline artifacts (internal)
    TIMELINE            = "timeline"           # scene open/close markers
    DEBUG               = "debug"              # developer / debug events


EVENT_CATEGORY: dict[EventType, EventCategory] = {
    # ── Indexable ────────────────────────────────────────────────────────────
    EventType.CHARACTER_APPEARS:    EventCategory.SCENE_ACTION,
    EventType.CHARACTER_EXITS:      EventCategory.SCENE_ACTION,
    EventType.CHARACTER_CHANGES:    EventCategory.SCENE_ACTION,
    EventType.DEATH:                EventCategory.SCENE_ACTION,
    EventType.MURDER:               EventCategory.SCENE_ACTION,
    EventType.INJURY:               EventCategory.SCENE_ACTION,
    EventType.BIRTH:                EventCategory.SCENE_ACTION,
    EventType.RESURRECTION:         EventCategory.SCENE_ACTION,
    EventType.MARRIAGE:             EventCategory.SCENE_ACTION,
    EventType.BETRAYAL:             EventCategory.SCENE_ACTION,
    EventType.ALLIANCE:             EventCategory.SCENE_ACTION,
    EventType.CONFLICT:             EventCategory.SCENE_ACTION,
    EventType.DISCOVERY:            EventCategory.SCENE_ACTION,
    EventType.TRAVEL:               EventCategory.SCENE_ACTION,
    EventType.CAPTURE:              EventCategory.SCENE_ACTION,
    EventType.ESCAPE:               EventCategory.SCENE_ACTION,
    EventType.DIALOGUE:             EventCategory.DIALOGUE,
    EventType.RELATIONSHIP_FORMS:   EventCategory.RELATIONSHIP,
    EventType.RELATIONSHIP_CHANGES: EventCategory.RELATIONSHIP,
    # ── Not indexed ──────────────────────────────────────────────────────────
    EventType.CHAR_TRAIT:           EventCategory.TRAIT,
    EventType.CHAR_EMOTION:         EventCategory.EXTRACTOR_METADATA,
    EventType.SCENE_OPENS:          EventCategory.TIMELINE,
    EventType.SCENE_CLOSES:         EventCategory.TIMELINE,
    EventType.TIMELINE_BEAT:        EventCategory.TIMELINE,
    EventType.WORLD_STATE_CHANGE:   EventCategory.TIMELINE,
}

INDEXABLE_CATEGORIES: frozenset[EventCategory] = frozenset({
    EventCategory.SCENE_ACTION,
    EventCategory.DIALOGUE,
    EventCategory.RELATIONSHIP,
})


# ---------------------------------------------------------------------------
# Retrieval profiles — named presets that control what sources + categories
# the retriever pulls for a given query intent.
# ---------------------------------------------------------------------------

from dataclasses import dataclass as _dataclass


@_dataclass(frozen=True)
class RetrievalProfileSpec:
    """Declares which source_types and event_categories to include.

    source_types: HybridSearch document sources to allow ("scene", "character", "lore", "event").
                  None means all source types pass through.
    event_categories: for source_type="event" docs, only these categories are returned.
                      None means all indexed event categories are returned.
    """
    source_types: frozenset[str] | None
    event_categories: frozenset[EventCategory] | None


class RetrievalProfile(str, Enum):
    NARRATIVE  = "narrative"   # story events + dialogue — 서사 흐름 파악용
    CHARACTER  = "character"   # character profiles + relationships — 인물 상태 파악용
    REASONING  = "reasoning"   # broad context — 추론·설명 생성용
    WORLD      = "world"       # scene + lore — 세계관 질문용


PROFILE_SPEC: dict[RetrievalProfile, RetrievalProfileSpec] = {
    RetrievalProfile.NARRATIVE: RetrievalProfileSpec(
        source_types=frozenset({"scene", "event"}),
        event_categories=frozenset({EventCategory.SCENE_ACTION, EventCategory.DIALOGUE}),
    ),
    RetrievalProfile.CHARACTER: RetrievalProfileSpec(
        source_types=frozenset({"character", "event"}),
        event_categories=frozenset({EventCategory.RELATIONSHIP}),
        # NOTE: TRAIT events are not indexed (per INDEXABLE_CATEGORIES).
        # Character documents naturally contain trait text (background, traits list).
    ),
    RetrievalProfile.REASONING: RetrievalProfileSpec(
        source_types=None,  # all sources
        event_categories=frozenset({
            EventCategory.RELATIONSHIP,
            EventCategory.SCENE_ACTION,
            EventCategory.DIALOGUE,
        }),
    ),
    RetrievalProfile.WORLD: RetrievalProfileSpec(
        source_types=frozenset({"scene", "lore"}),
        event_categories=None,
    ),
}


# ---------------------------------------------------------------------------
# Action taxonomy: verb patterns → EventType mapping
# ---------------------------------------------------------------------------

# Each entry: (compiled regex pattern, EventType it maps to, is_target_required)
ACTION_PATTERNS: list[tuple[str, EventType, bool]] = [
    # Vital
    (r"\b(kill(?:ed|s)?|murder(?:ed|s)?|slay|slew|slain|assassinat(?:ed|es)?|execut(?:ed|es)?)\b",
     EventType.MURDER, True),
    (r"\b(di(?:ed?|es)|dea(?:d|th)|perish(?:ed)?|pass(?:ed)?\s+away|fell?\s+dead)\b",
     EventType.DEATH, False),
    (r"\b(wound(?:ed|s)?|injur(?:ed|es)?|hurt|stab(?:bed|s)?|shot|slash(?:ed|es)?)\b",
     EventType.INJURY, True),
    (r"\b(born?|giv(?:e|ing|es|en)\s+birth|arriv(?:ed|es)?\s+in\s+the\s+world)\b",
     EventType.BIRTH, False),
    (r"\b(resurrect(?:ed|s)?|reviv(?:ed|es)?|came?\s+back\s+(?:to\s+life|alive)|rose?\s+from\s+(?:the\s+)?dead)\b",
     EventType.RESURRECTION, False),
    # Social
    (r"\b(marri(?:ed|es)?|wed(?:ded)?|betroth(?:ed)?)\b",
     EventType.MARRIAGE, True),
    (r"\b(betray(?:ed|s)?|backstab(?:bed)?|defect(?:ed|s)?|turn(?:ed)?\s+against)\b",
     EventType.BETRAYAL, True),
    (r"\b(alli(?:ed|es)?|form(?:ed|s)?\s+alliance|join(?:ed|s)?\s+forces?|partner(?:ed|s)?)\b",
     EventType.ALLIANCE, True),
    (r"\b(fight|fought|attack(?:ed|s)?|battl(?:ed|es)?|clash(?:ed|es)?|confront(?:ed|s)?)\b",
     EventType.CONFLICT, True),
    # Narrative
    (r"\b(discover(?:ed|s)?|found?|uncov(?:er(?:ed|s)?)?|reveal(?:ed|s)?|learn(?:ed|s|t)?)\b",
     EventType.DISCOVERY, False),
    (r"\b(travel(?:led|s)?|arriv(?:ed|es)?|enter(?:ed|s)?|reach(?:ed|es)?|left|depart(?:ed|s)?|fled?|escap(?:ed|es)?(?!\s+from\s+capture))\b",
     EventType.TRAVEL, False),
    (r"\b(captur(?:ed|es)?|arrest(?:ed|s)?|imprison(?:ed|s)?|detain(?:ed|s)?)\b",
     EventType.CAPTURE, True),
    (r"\b(escap(?:ed|es)?\s+from|broke?\s+free|freed?|liberat(?:ed|es)?)\b",
     EventType.ESCAPE, False),
]


# ---------------------------------------------------------------------------
# Extracted data models
# ---------------------------------------------------------------------------

@dataclass
class ExtractedEntity:
    name: str
    entity_type: str          # "character" | "location" | "object" | "concept"
    attributes: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    canonical_name: str | None = None   # normalised name (e.g. "John" for "John Smith")
    db_id: str | None = None            # set when matched to an existing DB record


@dataclass
class ExtractedAction:
    verb: str                           # raw verb form found in text ("killed")
    actor: str                          # subject entity name
    target: str | None                  # object entity name if any
    location: str | None                # location context
    event_type: EventType               # mapped event type
    confidence: float = 0.8


@dataclass
class ExtractedEntities:
    characters: list[ExtractedEntity] = field(default_factory=list)
    locations:  list[ExtractedEntity] = field(default_factory=list)
    objects:    list[ExtractedEntity] = field(default_factory=list)
    concepts:   list[ExtractedEntity] = field(default_factory=list)
    actions:    list[ExtractedAction] = field(default_factory=list)

    def all_entities(self) -> list[ExtractedEntity]:
        return self.characters + self.locations + self.objects + self.concepts


@dataclass
class NarrativeEvent:
    event_type: EventType
    subject: str                       # primary actor
    predicate: str                     # human-readable description
    target: str | None = None          # secondary entity
    action: str | None = None          # raw verb (e.g. "killed")
    location: str | None = None        # scene location
    attributes: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(
    default_factory=lambda: datetime.now(UTC)
)
    source_scene: str | None = None
    is_flashback: bool = False


@dataclass
class MutationResult:
    scene_id: str | None
    events_applied: list[NarrativeEvent]
    characters_upserted: list[str]    # list of IDs
    timeline_events_created: list[str]
    consistency_warnings: list[str]
    upserted_entities: list[dict[str, str]] = field(default_factory=list)
    character_upsert_attempts: int = 0
    success: bool = True
    error: str | None = None
