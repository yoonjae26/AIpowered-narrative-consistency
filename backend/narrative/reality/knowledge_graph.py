from __future__ import annotations

from dataclasses import dataclass, field
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
        if attributes:
            existing.attributes.update(attributes)
        self._history.append({
            "edge_id": edge_id,
            "source": source,
            "target": target,
            "edge_type": edge_type,
            "timestamp": timestamp,
        })
        self._persist()
        return existing

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
                    edge_id=f"evt:{event.get('event_id')}",
                    source=subject_id,
                    target=target_id,
                    edge_type=str(event.get("event_type") or "related_to"),
                    timestamp=str(event.get("happened_at") or ""),
                    attributes={"predicate": event.get("predicate")},
                )

            location = str(event.get("location") or "").strip()
            if location:
                loc_id = f"location:{location.lower()}"
                self.upsert_node(loc_id, "location", location)
                self.upsert_edge(
                    edge_id=f"loc:{event.get('event_id')}",
                    source=subject_id,
                    target=loc_id,
                    edge_type="located_at",
                    timestamp=str(event.get("happened_at") or ""),
                    attributes={"event_type": event.get("event_type")},
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
        self._history = list(payload.get("history", []))
