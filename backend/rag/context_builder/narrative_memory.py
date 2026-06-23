from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from backend.database.repositories.character_repository import CharacterRepository
from backend.database.repositories.lore_repository import LoreRepository
from backend.database.repositories.scene_repository import SceneRepository
from backend.database.repositories.timeline_repository import TimelineRepository
from backend.narrative.korean_text import normalize_korean_text
from backend.rag.embeddings.chunk_strategy import ChunkStrategy
from backend.rag.embeddings.embedder import BaseEmbedder, HashEmbedder
from backend.rag.retrieval.hybrid_search import HybridSearch
from backend.rag.retrieval.semantic_search import SearchHit


@dataclass(slots=True)
class NarrativeMemoryHit:
    id: str
    content: str
    score: float
    source_type: str
    metadata: dict[str, object] = field(default_factory=dict)


class NarrativeMemoryService:
    """Builds an in-memory semantic memory over scenes, lore, characters, and events."""

    def __init__(
        self,
        scene_repo: SceneRepository | None = None,
        lore_repo: LoreRepository | None = None,
        character_repo: CharacterRepository | None = None,
        timeline_repo: TimelineRepository | None = None,
        embedder: BaseEmbedder | None = None,
        chunk_strategy: ChunkStrategy | None = None,
        cache_path: str | Path | None = None,
    ) -> None:
        self._scenes = scene_repo
        self._lore = lore_repo
        self._characters = character_repo
        self._timeline = timeline_repo
        self._search = HybridSearch(chunk_strategy=chunk_strategy)
        self._search.semantic_search.embedder = embedder or HashEmbedder()
        self._index_ready = False
        self._cache_path = Path(cache_path or ".cache/narrative_memory_index.json")

    def ensure_ready(self) -> None:
        if self._index_ready:
            return
        if self._load_cache():
            self._index_ready = True
            return
        self.rebuild_index()

    def rebuild_index(self) -> None:
        embedder = self._search.semantic_search.embedder
        self._search = HybridSearch(chunk_strategy=self._search.chunk_strategy)
        self._search.semantic_search.embedder = embedder
        self._index_scenes()
        self._index_lore()
        self._index_characters()
        self._index_timeline()
        self._persist_cache()
        self._index_ready = True

    def sync_after_mutation(
        self,
        scene_title: str | None,
        character_names: list[str],
        events: list[dict[str, Any]] | list[Any],
    ) -> None:
        self.ensure_ready()
        if scene_title:
            self._upsert_scene_by_title(scene_title)
        for name in sorted({name for name in character_names if name}):
            self._upsert_character_by_name(name)
        for event in events:
            self._upsert_runtime_event(event)
        self._persist_cache()

    def search(
        self,
        query: str,
        limit: int = 5,
        source_types: set[str] | None = None,
    ) -> list[NarrativeMemoryHit]:
        self.ensure_ready()
        hits = self._search.search(normalize_korean_text(query), limit=max(limit * 3, 10))
        ranked = [self._convert_hit(hit) for hit in hits]
        if source_types:
            ranked = [hit for hit in ranked if hit.source_type in source_types]
        ranked.sort(key=self._rank_key, reverse=True)
        return ranked[:limit]

    def search_hierarchy(
        self,
        query: str,
        character_name: str | None = None,
        limit: int = 6,
    ) -> list[NarrativeMemoryHit]:
        collected: list[NarrativeMemoryHit] = []
        phases = [
            {"scene"},
            {"character"},
            {"lore"},
            {"event"},
        ]

        for source_types in phases:
            hits = self.search(query, limit=max(limit, 6), source_types=source_types)
            if character_name and "character" in source_types:
                hits = [
                    hit
                    for hit in hits
                    if str(hit.metadata.get("name") or "").lower() == character_name.lower()
                    or character_name.lower() in hit.content.lower()
                ]
            for hit in hits:
                if any(existing.id == hit.id for existing in collected):
                    continue
                collected.append(hit)
                if len(collected) >= limit:
                    return collected

        fallback = self.search(query, limit=max(limit, 6))
        for hit in fallback:
            if any(existing.id == hit.id for existing in collected):
                continue
            collected.append(hit)
            if len(collected) >= limit:
                break
        return collected

    def build_context(
        self,
        query: str,
        limit: int = 8,
    ) -> dict[str, list[dict[str, object]]]:
        hits = self.search(query, limit=limit)
        grouped: dict[str, list[dict[str, object]]] = {
            "scenes": [],
            "lore": [],
            "characters": [],
            "events": [],
        }
        for hit in hits:
            bucket = {
                "id": hit.id,
                "content": hit.content,
                "score": round(hit.score, 4),
                "metadata": hit.metadata,
            }
            if hit.source_type == "scene":
                grouped["scenes"].append(bucket)
            elif hit.source_type == "lore":
                grouped["lore"].append(bucket)
            elif hit.source_type == "character":
                grouped["characters"].append(bucket)
            elif hit.source_type == "event":
                grouped["events"].append(bucket)
        return grouped

    def _rank_key(self, hit: NarrativeMemoryHit) -> tuple[float, int]:
        boosts = {
            "character": 4,
            "scene": 3,
            "lore": 2,
            "event": 1,
        }
        return (hit.score, boosts.get(hit.source_type, 0))

    def _convert_hit(self, hit: SearchHit) -> NarrativeMemoryHit:
        source_type = str(hit.metadata.get("source_type") or "unknown")
        return NarrativeMemoryHit(
            id=hit.id,
            content=hit.content,
            score=hit.score,
            source_type=source_type,
            metadata=dict(hit.metadata),
        )

    def _load_cache(self) -> bool:
        if not self._cache_path.exists():
            return False
        payload = json.loads(self._cache_path.read_text(encoding="utf-8"))
        documents = payload.get("documents", []) if isinstance(payload, dict) else []
        if not documents:
            return False
        self._search.semantic_search.load_documents(documents)
        return True

    def _persist_cache(self) -> None:
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "documents": self._search.semantic_search.dump_documents(),
        }
        self._cache_path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")

    def _upsert_scene_by_title(self, scene_title: str) -> None:
        if self._scenes is None:
            return
        matches = [scene for scene in self._scenes.list() if scene.title == scene_title]
        if not matches:
            return
        scene = matches[-1]
        content = " ".join(
            filter(None, [scene.title, scene.summary or "", " ".join(scene.beats), " ".join(scene.characters)])
        )
        self._search.index(
            f"scene:{scene.id}",
            normalize_korean_text(content),
            source_type="scene",
            title=scene.title,
            characters=scene.characters,
        )

    def _upsert_character_by_name(self, character_name: str) -> None:
        if self._characters is None:
            return
        matches = [character for character in self._characters.list() if character.name.lower() == character_name.lower()]
        if not matches:
            return
        character = matches[-1]
        metadata = character.metadata_json or {}
        memory = metadata.get("memory", {}) if isinstance(metadata, dict) else {}
        content = " ".join(
            filter(None, [
                character.name,
                character.role,
                character.background or "",
                " ".join(character.traits or []),
                " ".join(character.goals or []),
                " ".join(memory.get("personality", [])),
                " ".join(memory.get("beliefs", [])),
                " ".join(memory.get("knowledge", [])),
                " ".join(memory.get("desires", [])),
            ])
        )
        self._search.index(
            f"character:{character.id}",
            normalize_korean_text(content),
            source_type="character",
            name=character.name,
            status=character.status,
        )

    def _upsert_runtime_event(self, event: Any) -> None:
        event_id = getattr(event, "timestamp", None)
        stable_id = f"event:{getattr(event, 'event_type').value}:{getattr(event, 'subject', '')}:{getattr(event, 'target', '')}:{event_id.isoformat() if event_id else ''}"
        content = " ".join(
            filter(None, [
                getattr(event, "predicate", ""),
                getattr(event, "subject", ""),
                getattr(event, "target", "") or "",
                getattr(event, "location", "") or "",
                getattr(event, "action", "") or "",
            ])
        )
        self._search.index(
            stable_id,
            normalize_korean_text(content),
            source_type="event",
            subject=getattr(event, "subject", None),
            target=getattr(event, "target", None),
            location=getattr(event, "location", None),
            event_type=getattr(event, "event_type").value,
        )

    def _index_scenes(self) -> None:
        if self._scenes is None:
            return
        for scene in self._scenes.list():
            content = " ".join(
                filter(None, [scene.title, scene.summary or "", " ".join(scene.beats), " ".join(scene.characters)])
            )
            self._search.index(
                f"scene:{scene.id}",
                normalize_korean_text(content),
                source_type="scene",
                title=scene.title,
                characters=scene.characters,
            )

    def _index_lore(self) -> None:
        if self._lore is None:
            return
        for fact in self._lore.list():
            content = " ".join(filter(None, [fact.key, fact.value, fact.source or "", " ".join(fact.tags or [])]))
            self._search.index(
                f"lore:{fact.key}",
                normalize_korean_text(content),
                source_type="lore",
                key=fact.key,
                source=fact.source,
                tags=fact.tags,
            )

    def _index_characters(self) -> None:
        if self._characters is None:
            return
        for character in self._characters.list():
            metadata = character.metadata_json or {}
            memory = metadata.get("memory", {}) if isinstance(metadata, dict) else {}
            content = " ".join(
                filter(None, [
                    character.name,
                    character.role,
                    character.background or "",
                    " ".join(character.traits or []),
                    " ".join(character.goals or []),
                    " ".join(memory.get("personality", [])),
                    " ".join(memory.get("beliefs", [])),
                    " ".join(memory.get("knowledge", [])),
                    " ".join(memory.get("desires", [])),
                ])
            )
            self._search.index(
                f"character:{character.id}",
                normalize_korean_text(content),
                source_type="character",
                name=character.name,
                status=character.status,
            )

    def _index_timeline(self) -> None:
        if self._timeline is None:
            return
        for event in self._timeline.list():
            meta = event.metadata_json or {}
            content = " ".join(filter(None, [event.title, event.description or "", str(meta.get("location") or ""), str(meta)]))
            self._search.index(
                f"event:{event.id}",
                normalize_korean_text(content),
                source_type="event",
                happened_at=event.happened_at.isoformat() if event.happened_at else None,
            )
NarrativeMemory = NarrativeMemoryService