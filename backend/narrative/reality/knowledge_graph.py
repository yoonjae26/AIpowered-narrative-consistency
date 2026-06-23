from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class GraphNode:
    node_id: str
    node_type: str
    label: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class GraphEdge:
    edge_id: str
    source: str
    target: str
    edge_type: str
    timestamp: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


class NarrativeKnowledgeGraph:
    def __init__(self, file_path: str | Path | None = None) -> None:
        self._file_path = Path(file_path or ".cache/narrative_knowledge_graph.json")
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        self._nodes: dict[str, GraphNode] = {}
        self._edges: dict[str, GraphEdge] = {}
        self._edge_index: dict[tuple[str, str, str], str] = {}
        self._history: list[dict[str, Any]] = []
        self._load()

    def upsert_node(self, node_id: str, node_type: str, label: str, attributes: dict[str, Any] | None = None) -> GraphNode:
        existing = self._nodes.get(node_id)
        if existing is None:
            existing = GraphNode(node_id=node_id, node_type=node_type, label=label)
            self._nodes[node_id] = existing
        if attributes:
            existing.attributes.update(attributes)
        self._persist()
        return existing

    def upsert_edge(
        self,
        edge_id: str,
        source: str,
        target: str,
        edge_type: str,
        timestamp: str | None,
        attributes: dict[str, Any] | None = None,
    ) -> GraphEdge:
        existing = self._edges.get(edge_id)
        if existing is None:
            existing = GraphEdge(
                edge_id=edge_id,
                source=source,
                target=target,
                edge_type=edge_type,
                timestamp=timestamp,
            )
            self._edges[edge_id] = existing
            existing.attributes["weight"] = 0
        self._edge_index[(source, target, edge_type)] = edge_id

        existing.timestamp = timestamp or existing.timestamp
        existing.attributes["weight"] = int(existing.attributes.get("weight") or 0) + 1

        if attributes:
            existing.attributes.update(attributes)

        evidence_event_id = None
        if attributes:
            evidence_event_id = str(attributes.get("event_id") or "").strip() or None
        if evidence_event_id:
            event_ids = list(existing.attributes.get("event_ids") or [])
            if evidence_event_id not in event_ids:
                event_ids.append(evidence_event_id)
                # Keep a bounded history to avoid memory growth.
                existing.attributes["event_ids"] = event_ids[-20:]

        self._history.append({
            "edge_id": edge_id,
            "source": source,
            "target": target,
            "edge_type": edge_type,
            "timestamp": timestamp,
        })
        if len(self._history) > 5000:
            self._history = self._history[-5000:]
        self._persist()
        return existing

    def _stable_edge_id(self, source: str, target: str, edge_type: str) -> str:
        key = f"{source}|{edge_type}|{target}"
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
        return f"rel:{digest}"

    def integrate_scene(self, typed_events: list[dict[str, Any]], scene_title: str | None = None) -> None:
        if scene_title:
            self.upsert_node(
                node_id=f"scene:{scene_title.strip().lower()}",
                node_type="scene",
                label=scene_title,
            )

        for event in typed_events:
            subject = str(event.get("subject") or "").strip()
            if not subject:
                continue
            subject_type = str(event.get("subject_type") or "concept")
            subject_id = f"{subject_type}:{subject.lower()}"
            self.upsert_node(subject_id, subject_type, subject)

            target = str(event.get("target") or "").strip()
            if target:
                target_type = str(event.get("target_type") or "concept")
                target_id = f"{target_type}:{target.lower()}"
                self.upsert_node(target_id, target_type, target)
                self.upsert_edge(
                    edge_id=self._stable_edge_id(subject_id, target_id, str(event.get("event_type") or "related_to")),
                    source=subject_id,
                    target=target_id,
                    edge_type=str(event.get("event_type") or "related_to"),
                    timestamp=str(event.get("happened_at") or ""),
                    attributes={
                        "predicate": event.get("predicate"),
                        "event_id": event.get("event_id"),
                    },
                )

    def integrate_character_memory(self, character_name: str, memory: dict[str, Any], scene_title: str | None = None) -> None:
        if not character_name:
            return
        char_id = f"character:{character_name.lower()}"
        self.upsert_node(char_id, "character", character_name)

        for item in list(memory.get("trait_events") or []):
            trait = str(item.get("trait") or "").strip()
            if not trait:
                continue
            relation = str(item.get("relation") or "has_trait")
            node_type = "emotion" if relation == "has_emotion" else "trait"
            trait_id = f"{node_type}:{trait.lower()}"
            self.upsert_node(trait_id, node_type, trait)
            self.upsert_edge(
                edge_id=self._stable_edge_id(char_id, trait_id, relation),
                source=char_id,
                target=trait_id,
                edge_type=relation,
                timestamp=str(item.get("timestamp") or ""),
                attributes={
                    "confidence": float(item.get("confidence") or 0.5),
                    "source_scene": item.get("source_scene") or scene_title or "",
                },
            )

            location = str(event.get("location") or "").strip()
            if location:
                loc_id = f"location:{location.lower()}"
                self.upsert_node(loc_id, "location", location)
                self.upsert_edge(
                    edge_id=self._stable_edge_id(subject_id, loc_id, "located_at"),
                    source=subject_id,
                    target=loc_id,
                    edge_type="located_at",
                    timestamp=str(event.get("happened_at") or ""),
                    attributes={
                        "event_type": event.get("event_type"),
                        "event_id": event.get("event_id"),
                    },
                )

    def traverse(self, node_id: str, depth: int = 1) -> dict[str, Any]:
        seen_nodes = {node_id}
        frontier = {node_id}
        traversed_edges: list[GraphEdge] = []

        for _ in range(max(0, depth)):
            next_frontier: set[str] = set()
            for edge in self._edges.values():
                if edge.source in frontier:
                    traversed_edges.append(edge)
                    next_frontier.add(edge.target)
                elif edge.target in frontier:
                    traversed_edges.append(edge)
                    next_frontier.add(edge.source)
            next_frontier -= seen_nodes
            if not next_frontier:
                break
            seen_nodes |= next_frontier
            frontier = next_frontier

        nodes = [self._nodes[n] for n in sorted(seen_nodes) if n in self._nodes]
        return {
            "nodes": [
                {
                    "node_id": node.node_id,
                    "node_type": node.node_type,
                    "label": node.label,
                    "attributes": dict(node.attributes),
                }
                for node in nodes
            ],
            "edges": [
                {
                    "edge_id": edge.edge_id,
                    "source": edge.source,
                    "target": edge.target,
                    "edge_type": edge.edge_type,
                    "timestamp": edge.timestamp,
                    "attributes": dict(edge.attributes),
                }
                for edge in traversed_edges
            ],
        }

    def summary(self) -> dict[str, Any]:
        node_types: dict[str, int] = {}
        edge_types: dict[str, int] = {}
        for node in self._nodes.values():
            node_types[node.node_type] = node_types.get(node.node_type, 0) + 1
        for edge in self._edges.values():
            edge_types[edge.edge_type] = edge_types.get(edge.edge_type, 0) + 1
        return {
            "node_count": len(self._nodes),
            "edge_count": len(self._edges),
            "node_types": node_types,
            "edge_types": edge_types,
            "history_events": len(self._history),
        }

    def _persist(self) -> None:
        payload = {
            "nodes": [
                {
                    "node_id": node.node_id,
                    "node_type": node.node_type,
                    "label": node.label,
                    "attributes": node.attributes,
                }
                for node in self._nodes.values()
            ],
            "edges": [
                {
                    "edge_id": edge.edge_id,
                    "source": edge.source,
                    "target": edge.target,
                    "edge_type": edge.edge_type,
                    "timestamp": edge.timestamp,
                    "attributes": edge.attributes,
                }
                for edge in self._edges.values()
            ],
            "history": list(self._history),
        }
        self._file_path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")

    def _load(self) -> None:
        if not self._file_path.exists():
            return
        payload = json.loads(self._file_path.read_text(encoding="utf-8"))
        for item in payload.get("nodes", []):
            node = GraphNode(
                node_id=str(item["node_id"]),
                node_type=str(item.get("node_type") or "concept"),
                label=str(item.get("label") or item["node_id"]),
                attributes=dict(item.get("attributes") or {}),
            )
            self._nodes[node.node_id] = node
        for item in payload.get("edges", []):
            edge = GraphEdge(
                edge_id=str(item["edge_id"]),
                source=str(item["source"]),
                target=str(item["target"]),
                edge_type=str(item.get("edge_type") or "related_to"),
                timestamp=item.get("timestamp"),
                attributes=dict(item.get("attributes") or {}),
            )
            self._edges[edge.edge_id] = edge
            self._edge_index[(edge.source, edge.target, edge.edge_type)] = edge.edge_id
        self._history = list(payload.get("history", []))
        self._compact_loaded_edges()

    def _compact_loaded_edges(self) -> None:
        if not self._edges:
            return

        compacted: dict[tuple[str, str, str], GraphEdge] = {}
        for edge in self._edges.values():
            key = (edge.source, edge.target, edge.edge_type)
            existing = compacted.get(key)
            if existing is None:
                attrs = dict(edge.attributes)
                attrs["weight"] = int(attrs.get("weight") or 1)
                existing = GraphEdge(
                    edge_id=self._stable_edge_id(edge.source, edge.target, edge.edge_type),
                    source=edge.source,
                    target=edge.target,
                    edge_type=edge.edge_type,
                    timestamp=edge.timestamp,
                    attributes=attrs,
                )
                compacted[key] = existing
                continue

            existing.attributes["weight"] = int(existing.attributes.get("weight") or 1) + int(edge.attributes.get("weight") or 1)
            if edge.timestamp and (not existing.timestamp or edge.timestamp > existing.timestamp):
                existing.timestamp = edge.timestamp
            merged_ids = list(existing.attributes.get("event_ids") or [])
            for event_id in edge.attributes.get("event_ids") or []:
                value = str(event_id).strip()
                if value and value not in merged_ids:
                    merged_ids.append(value)
            if merged_ids:
                existing.attributes["event_ids"] = merged_ids[-20:]

        self._edges = {edge.edge_id: edge for edge in compacted.values()}
        self._edge_index = {
            (edge.source, edge.target, edge.edge_type): edge.edge_id
            for edge in self._edges.values()
        }
