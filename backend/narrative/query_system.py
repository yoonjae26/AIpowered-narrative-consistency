from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

from backend.database.repositories.character_repository import CharacterRepository
from backend.database.repositories.lore_repository import LoreRepository
from backend.database.repositories.scene_repository import SceneRepository
from backend.narrative.character.memory_system import CharacterMemorySystem
from backend.narrative.relationships.graph import RelationshipGraph
from backend.rag import NarrativeMemoryService
from backend.version_control.event_store import EventStore


@dataclass(slots=True)
class QueryAnswer:
    query: str
    answer: str
    evidence: list[dict[str, Any]] = field(default_factory=list)


class NarrativeQuerySystem:
    """Structured query layer over story state, memory, graph, and event history."""

    def __init__(
        self,
        character_repo: CharacterRepository,
        lore_repo: LoreRepository,
        scene_repo: SceneRepository,
        relationship_graph: RelationshipGraph,
        memory_service: NarrativeMemoryService,
        event_store: EventStore,
    ) -> None:
        self._characters = character_repo
        self._lore = lore_repo
        self._scenes = scene_repo
        self._graph = relationship_graph
        self._memory = CharacterMemorySystem(character_repo)
        self._memory_service = memory_service
        self._event_store = event_store

    def query(self, query_text: str) -> QueryAnswer:
        q = query_text.strip()
        lower = q.lower()
        if topic := self._extract_known_topic(q):
            return self.who_knows_about(topic)
        if pair := self._extract_relationship_pair(q):
            return self.relationship_between(pair[0], pair[1])
        if name := self._extract_status_target(q):
            return self.status_of(name)
        if name := self._extract_location_target(q):
            return self.where_is(name)
        if name := self._extract_event_target(q):
            return self.what_happened_to(name)
        if relation_query := self._extract_dimension_query(q):
            return self.relationship_dimension_query(relation_query[0], relation_query[1])
        return self.semantic_query(q)

    def who_knows_about(self, topic: str) -> QueryAnswer:
        matches: list[dict[str, Any]] = []
        lowered = topic.lower()
        for character in self._characters.list():
            memory = self._memory.get_memory(character.name)
            corpus = memory.knowledge + memory.beliefs
            if any(lowered in item.lower() for item in corpus):
                matches.append({
                    "character": character.name,
                    "knowledge": [item for item in corpus if lowered in item.lower()],
                })
        if matches:
            names = ", ".join(item["character"] for item in matches)
            return QueryAnswer(query=f"Who knows about {topic}?", answer=names, evidence=matches)
        return QueryAnswer(query=f"Who knows about {topic}?", answer="No explicit knowledge found.", evidence=[])

    def relationship_between(self, source: str, target: str) -> QueryAnswer:
        edge = self._graph.relationship_between(source, target)
        if edge is None:
            return QueryAnswer(query=f"relationship between {source} and {target}", answer="No direct relationship found.")
        answer = f"{source} -> {target}: {edge.relationship_type.value} (strength {edge.strength:.2f})"
        return QueryAnswer(query=f"relationship between {source} and {target}", answer=answer, evidence=[{
            "source": edge.source,
            "target": edge.target,
            "relationship_type": edge.relationship_type.value,
            "strength": edge.strength,
            "dimensions": edge.dimensions,
        }])

    def status_of(self, name: str) -> QueryAnswer:
        for character in self._characters.list():
            if character.name.lower() == name.lower():
                metadata = character.metadata_json or {}
                return QueryAnswer(
                    query=f"status of {name}",
                    answer=f"{character.name} is {character.status}",
                    evidence=[{"status": character.status, "metadata": metadata}],
                )
        return QueryAnswer(query=f"status of {name}", answer="Character not found.")

    def semantic_query(self, query_text: str) -> QueryAnswer:
        hits = self._memory_service.search(query_text, limit=5)
        if hits:
            answer = hits[0].content
            return QueryAnswer(
                query=query_text,
                answer=answer,
                evidence=[{
                    "id": hit.id,
                    "source_type": hit.source_type,
                    "score": hit.score,
                    "content": hit.content,
                } for hit in hits],
            )
        replay = self._event_store.replay_state()
        return QueryAnswer(query=query_text, answer="No direct semantic hit; returning replay summary.", evidence=[replay])

    def where_is(self, name: str) -> QueryAnswer:
        replay = self._event_store.replay_state()
        characters = replay.get("characters", {})
        if name in characters:
            location = characters[name].get("last_location")
            if location:
                return QueryAnswer(query=f"where is {name}", answer=f"{name} is at {location}.", evidence=[characters[name]])
            inferred = self._infer_location_from_memory(name)
            if inferred is not None:
                return QueryAnswer(
                    query=f"where is {name}",
                    answer=f"Best semantic match places {name} at {inferred['location']}.",
                    evidence=[characters[name], inferred],
                )
            return QueryAnswer(query=f"where is {name}", answer=f"No known location for {name}.", evidence=[characters[name]])
        return QueryAnswer(query=f"where is {name}", answer="Character not found.")

    def what_happened_to(self, name: str) -> QueryAnswer:
        events = [event for event in self._event_store.list_events() if event.subject.lower() == name.lower() or (event.target or "").lower() == name.lower()]
        if not events:
            return QueryAnswer(query=f"what happened to {name}", answer="No event history found.")
        answer = "; ".join(event.predicate for event in events[-5:])
        return QueryAnswer(
            query=f"what happened to {name}",
            answer=answer,
            evidence=[{"id": event.id, "predicate": event.predicate, "branch": event.branch} for event in events[-5:]],
        )

    def relationship_dimension_query(self, dimension: str, name: str | None = None) -> QueryAnswer:
        edges = self._graph.query_by_dimension(dimension, minimum=0.5)
        if name:
            edges = [edge for edge in edges if edge.source.lower() == name.lower() or edge.target.lower() == name.lower()]
        if not edges:
            return QueryAnswer(query=f"{dimension} query", answer=f"No relationships found for dimension '{dimension}'.")
        summary = "; ".join(
            f"{edge.source}->{edge.target} {dimension}={edge.dimensions.get(dimension, 0.0):.2f}"
            for edge in edges[:10]
        )
        return QueryAnswer(
            query=f"{dimension} query",
            answer=summary,
            evidence=[
                {
                    "source": edge.source,
                    "target": edge.target,
                    "relationship_type": edge.relationship_type.value,
                    "dimensions": edge.dimensions,
                }
                for edge in edges[:10]
            ],
        )

    def _extract_known_topic(self, query: str) -> str | None:
        patterns = [
            r"who knows about (?P<topic>.+)$",
            r"who is aware of (?P<topic>.+)$",
            r"which characters know about (?P<topic>.+)$",
            r"who has knowledge of (?P<topic>.+)$",
        ]
        for pattern in patterns:
            match = re.search(pattern, query.strip(), re.IGNORECASE)
            if match:
                return match.group("topic").strip(" ?")
        return None

    def _extract_relationship_pair(self, query: str) -> tuple[str, str] | None:
        patterns = [
            r"relationship between (?P<a>.+?) and (?P<b>.+)$",
            r"how does (?P<a>.+?) relate to (?P<b>.+)$",
            r"what is the relationship of (?P<a>.+?) with (?P<b>.+)$",
        ]
        for pattern in patterns:
            match = re.search(pattern, query.strip(), re.IGNORECASE)
            if match:
                return match.group("a").strip(" ?"), match.group("b").strip(" ?")
        return None

    def _extract_status_target(self, query: str) -> str | None:
        patterns = [
            r"status of (?P<name>.+)$",
            r"is (?P<name>.+?) alive$",
            r"what is (?P<name>.+?)'s status$",
        ]
        for pattern in patterns:
            match = re.search(pattern, query.strip(), re.IGNORECASE)
            if match:
                return match.group("name").strip(" ?")
        return None

    def _extract_location_target(self, query: str) -> str | None:
        patterns = [
            r"where is (?P<name>.+)$",
            r"where was (?P<name>.+) last seen$",
            r"what is (?P<name>.+?)'s location$",
        ]
        for pattern in patterns:
            match = re.search(pattern, query.strip(), re.IGNORECASE)
            if match:
                return match.group("name").strip(" ?")
        return None

    def _extract_event_target(self, query: str) -> str | None:
        patterns = [
            r"what happened to (?P<name>.+)$",
            r"tell me what happened to (?P<name>.+)$",
            r"summarize (?P<name>.+?)'s events$",
        ]
        for pattern in patterns:
            match = re.search(pattern, query.strip(), re.IGNORECASE)
            if match:
                return match.group("name").strip(" ?")
        return None

    def _extract_dimension_query(self, query: str) -> tuple[str, str | None] | None:
        lower = query.lower().strip()
        dimension_map = {
            "trust": ["who trusts", "trusted by", "trust relationships"],
            "friendship": ["who is friends with", "friendships of", "friendship relationships"],
            "hatred": ["who hates", "hatred toward", "hate relationships"],
            "alliance": ["who is allied with", "alliances of", "alliance relationships"],
        }
        for dimension, phrases in dimension_map.items():
            for phrase in phrases:
                if lower.startswith(phrase):
                    tail = query[len(phrase):].strip(" ?")
                    return dimension, tail or None
        return None

    def _infer_location_from_memory(self, name: str) -> dict[str, Any] | None:
        hits = self._memory_service.search(name, limit=10)
        explicit_patterns = [
            r"Location ['\"](?P<location>[^'\"]+)['\"] is established",
            r"\b(?P<name>[A-Z][a-zA-Z\- ]+)\b[^.?!]*\b(?:traveled|travelled|went|moved|arrived|returned)\b[^.?!]*\bto\b[^.?!]*\b(?:the )?(?P<location>[a-zA-Z][a-zA-Z\- ]+)\b",
        ]
        patterns = [
            r"\b(?:in|at|to|into|inside|within) the ([a-zA-Z][a-zA-Z\- ]+)\b",
            r"\b(?:in|at|to|into|inside|within) ([A-Z][a-zA-Z\- ]+)\b",
        ]
        for hit in hits:
            content = hit.content
            for pattern in explicit_patterns:
                match = re.search(pattern, content)
                if match and (location := match.groupdict().get("location")):
                    return {
                        "location": location.strip().rstrip("."),
                        "source_type": hit.source_type,
                        "content": hit.content,
                        "score": hit.score,
                    }
            for pattern in patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    return {
                        "location": match.group(1).strip().rstrip("."),
                        "source_type": hit.source_type,
                        "content": hit.content,
                        "score": hit.score,
                    }
        return None
