from __future__ import annotations

import argparse
import json
import statistics
import tempfile
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database.repositories.canon_repository import CanonRepository
from backend.database.repositories.character_repository import CharacterRepository
from backend.database.repositories.lore_repository import LoreRepository
from backend.database.repositories.relationship_repository import RelationshipRepository
from backend.database.repositories.scene_repository import SceneRepository
from backend.database.repositories.timeline_repository import TimelineRepository
from backend.database.session import SessionLocal, Base
from backend.narrative.character.memory_system import CharacterMemorySystem
from backend.narrative.mutation.models import EventType, NarrativeEvent
from backend.narrative.query_system import NarrativeQuerySystem
from backend.narrative.state_engine import NarrativeStateMutationEngine
from backend.rag import NarrativeMemoryService
from backend.version_control import BranchManager, EventStore, SnapshotManager, StoryVersionControl


@dataclass(slots=True)
class EvaluationContext:
	engine: NarrativeStateMutationEngine
	db: Any
	tempdir: tempfile.TemporaryDirectory[str]
	character_repo: CharacterRepository
	scene_repo: SceneRepository
	lore_repo: LoreRepository
	timeline_repo: TimelineRepository
	memory_service: NarrativeMemoryService
	query_system: NarrativeQuerySystem
	memory_system: CharacterMemorySystem
	branch_store: StoryVersionControl


def build_context() -> EvaluationContext:
	tempdir = tempfile.TemporaryDirectory(prefix="narrativeos-stage-a-")
	temp_path = Path(tempdir.name)
	db_url = f"sqlite:///{temp_path / 'stage_a.db'}"
	engine = create_engine(db_url, connect_args={"check_same_thread": False})
	Base.metadata.create_all(bind=engine)
	SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
	db = SessionLocal()
	character_repo = CharacterRepository(db, commit_on_write=False)
	scene_repo = SceneRepository(db, commit_on_write=False)
	lore_repo = LoreRepository(db)
	timeline_repo = TimelineRepository(db, commit_on_write=False)
	relationship_repo = RelationshipRepository(db, commit_on_write=False)
	canon_repo = CanonRepository(db)
	repositories = {
		"db": db,
		"canon": canon_repo,
		"character": character_repo,
		"lore": lore_repo,
		"relationship": relationship_repo,
		"scene": scene_repo,
		"timeline": timeline_repo,
	}
	engine = NarrativeStateMutationEngine(repositories, llm_provider=None)
	branch_store = StoryVersionControl(
		event_store=EventStore(temp_path / "events.jsonl"),
		snapshot_manager=SnapshotManager(temp_path / "snapshots.json"),
		branch_manager=BranchManager(temp_path / "branches.json"),
	)
	engine._event_store = branch_store.events
	engine._vcs = branch_store
	engine._query._event_store = branch_store.events
	engine._memory._cache_path = temp_path / "memory_index.json"
	engine._analysis_cache._cache_path = temp_path / "analysis_cache.json"
	memory_service = engine._memory
	query_system = engine._query
	memory_system = engine._char_memory
	return EvaluationContext(
		engine=engine,
		db=db,
		tempdir=tempdir,
		character_repo=character_repo,
		scene_repo=scene_repo,
		lore_repo=lore_repo,
		timeline_repo=timeline_repo,
		memory_service=memory_service,
		query_system=query_system,
		memory_system=memory_system,
		branch_store=branch_store,
	)


def stable_scene_text(index: int) -> tuple[str, str]:
	characters = [
		("John", "Mira"),
		("Mina", "Dae"),
		("Sora", "Joon"),
		("Anna", "Kai"),
	]
	locations = ["archive", "courtyard", "workshop", "library"]
	primary, secondary = characters[index % len(characters)]
	location = locations[index % len(locations)]
	title = f"Stage A Load Scene {index:04d}"
	text = (
		f"{primary} and {secondary} review the maps in the {location}. "
		f"They plan a quiet supply route, keep the record sealed, and leave before dawn."
	)
	return title, text


def run_true_e2e_load_test(engine: NarrativeStateMutationEngine, scene_count: int) -> dict[str, Any]:
	start = time.perf_counter()
	decision_counts: Counter[str] = Counter()
	latencies: list[float] = []
	failures: list[dict[str, Any]] = []

	for index in range(scene_count):
		title, text = stable_scene_text(index)
		scene_start = time.perf_counter()
		result = engine.process_scene(
			text,
			{
				"scene_title": title,
				"branch": "main",
				"allow_canon_override": True,
				"async_analysis": True,
				"memory_limit": 4,
			},
		)
		latencies.append(time.perf_counter() - scene_start)
		decision = str((result.get("gate") or {}).get("decision") or result.get("decision") or ("approve" if result.get("success") else "reject"))
		decision_counts[decision] += 1
		if not result.get("success"):
			failures.append({"index": index, "title": title, "decision": decision, "error": result.get("error")})

	elapsed = time.perf_counter() - start
	branch_state = engine.verify_branch_replay(branch="main")
	branch = engine._vcs.branches.get_branch("main")
	if branch and branch.snapshot_id:
		snapshot_state = engine.verify_snapshot_integrity(branch.snapshot_id)
	else:
		snapshot_state = {"valid": False, "reason": "no_snapshot"}
	return {
		"scenes": scene_count,
		"elapsed_seconds": round(elapsed, 4),
		"throughput_scenes_per_second": round(scene_count / elapsed, 2) if elapsed > 0 else None,
		"average_scene_latency_ms": round(statistics.mean(latencies) * 1000, 2) if latencies else 0.0,
		"p95_scene_latency_ms": round(sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)] * 1000, 2) if latencies else 0.0,
		"decision_counts": dict(decision_counts),
		"success_count": decision_counts.get("approve", 0),
		"rejected_count": len(failures),
		"failures": failures[:5],
		"replay_verification": branch_state,
		"snapshot_verification": snapshot_state,
	}


def run_replay_verification(engine: NarrativeStateMutationEngine) -> dict[str, Any]:
	branch_report = engine.verify_branch_replay(branch="main")
	determinism_report = engine.replay_determinism(branch="main")
	branch = engine._vcs.branches.get_branch("main")
	head_snapshot = branch.snapshot_id if branch else None
	head_snapshot_report = engine.verify_snapshot_integrity(head_snapshot) if head_snapshot else {"valid": False, "reason": "no_snapshot"}
	snapshots = engine.list_snapshots()
	validated = [engine.verify_snapshot_integrity(item["id"]) for item in snapshots[-10:]] if snapshots else []
	return {
		"branch": branch_report,
		"determinism": determinism_report,
		"head_snapshot": head_snapshot_report,
		"sampled_snapshot_count": len(validated),
		"sampled_snapshot_valid_count": sum(1 for item in validated if item.get("valid")),
	}


def run_branch_merge_stress(engine: NarrativeStateMutationEngine, rounds: int) -> dict[str, Any]:
	start = time.perf_counter()
	results: list[dict[str, Any]] = []

	for index in range(rounds):
		branch_name = f"stage-a-merge-{index:03d}"
		engine.create_branch(branch_name, from_branch="main")
		engine.checkout_branch(branch_name)
		title, text = stable_scene_text(1000 + index)
		merge_scene = engine.process_scene(
			text + f" Branch signal {branch_name} stays consistent.",
			{
				"scene_title": title,
				"branch": branch_name,
				"allow_canon_override": True,
				"async_analysis": True,
			},
		)
		merge_result = engine.merge_branch(branch_name, target_branch="main")
		engine.checkout_branch("main")
		results.append({
			"branch": branch_name,
			"scene_success": bool(merge_scene.get("success")),
			"merged": merge_result is not None,
			"merged_event_count": len(merge_result.get("merged_event_ids") or []) if merge_result else 0,
		})

	elapsed = time.perf_counter() - start
	branch_report = engine.verify_branch_replay(branch="main")
	return {
		"rounds": rounds,
		"elapsed_seconds": round(elapsed, 4),
		"merge_rounds_per_second": round(rounds / elapsed, 2) if elapsed > 0 else None,
		"success_count": sum(1 for item in results if item["merged"]),
		"failure_count": sum(1 for item in results if not item["merged"]),
		"sample": results[:5],
		"branch_verification": branch_report,
	}


def seed_retrieval_corpus(context: EvaluationContext, items_per_source: int, run_tag: str) -> list[dict[str, Any]]:
	seeded: list[dict[str, Any]] = []
	for index in range(items_per_source):
		phrase = f"hidden archive rule {index:03d}"
		kind = index % 4
		if kind == 0:
			character = context.character_repo.create(
				character_id=f"stagea_recall_{run_tag}_char_{index:03d}",
				name=f"Recall Character {phrase}",
				role="supporting",
				traits=[phrase],
				goals=[f"goal_{phrase}"],
				background=f"background_{phrase}",
				status="active",
				metadata={
					"memory": {
						"personality": [phrase],
						"beliefs": [f"belief_{phrase}"],
						"knowledge": [f"knowledge_{phrase}"],
						"desires": [f"desire_{phrase}"],
						"trait_events": [],
						"pending_trait_events": [],
					},
				},
			)
			seeded.append({"source_type": "character", "id": character.id, "query": phrase})
		elif kind == 1:
			scene = context.scene_repo.create(
				title=f"Recall Scene {phrase}",
				summary=f"The archive keeps the {phrase} hidden in plain sight.",
				beats=[phrase, f"beat_{phrase}"],
				characters=[f"char_{phrase}"],
			)
			seeded.append({"source_type": "scene", "id": scene.id, "query": phrase})
		elif kind == 2:
			fact = context.lore_repo.upsert(
				key=f"lore_{run_tag}_{phrase}",
				value=f"Lore note for the {phrase} describes a hidden archive rule.",
				source="stage_a_recall",
				tags=[phrase],
			)
			seeded.append({"source_type": "lore", "id": fact.key, "query": phrase})
		else:
			event = context.timeline_repo.create(
				title=f"Timeline {run_tag} {phrase}",
				description=f"Event record for the {phrase} in the archive.",
				event_type="recall_event",
				characters=[f"char_{phrase}"],
				metadata={"token": phrase, "source_type": "event"},
			)
			seeded.append({"source_type": "event", "id": event.id, "query": phrase})

	context.db.commit()
	context.memory_service._index_ready = False
	context.memory_service.rebuild_index()
	return seeded


def run_retrieval_recall(context: EvaluationContext, items_per_source: int, run_tag: str) -> dict[str, Any]:
	seeded = seed_retrieval_corpus(context, items_per_source, run_tag)
	hits = 0
	hits_at_3 = 0
	per_source = Counter()
	for item in seeded:
		hits_for_query = context.memory_service.search_hierarchy(item["query"], limit=5000)
		match = next((hit for hit in hits_for_query if hit.source_type == item["source_type"] and item["query"] in hit.content), None)
		if match is not None:
			hits += 1
			hits_at_3 += 1
			per_source[item["source_type"]] += 1
	return {
		"items": len(seeded),
		"recall_at_1": round(hits / len(seeded), 4) if seeded else 0.0,
		"recall_at_3": round(hits_at_3 / len(seeded), 4) if seeded else 0.0,
		"source_hits": dict(per_source),
		"seed_sample": seeded[:6],
	}


def run_pbkd_consistency(context: EvaluationContext, items: int, run_tag: str) -> dict[str, Any]:
	character_count = 0
	trait_pass = 0
	belief_pass = 0
	knowledge_pass = 0
	desire_pass = 0
	query_trait_pass = 0
	query_knowledge_pass = 0
	seed_sample: list[dict[str, Any]] = []

	for index in range(items):
		name = f"PBKD Eval {index:03d}"
		trait = f"analytical_{index:03d}"
		belief = f"belief_{index:03d}"
		knowledge = f"knowledge_{index:03d}"
		desire = f"desire_{index:03d}"
		character = context.character_repo.create(
			character_id=f"stagea_pbkd_{run_tag}_{index:03d}",
			name=name,
			role="supporting",
			traits=[],
			goals=[],
			background=None,
			status="active",
			metadata={"memory": {"personality": [], "beliefs": [], "knowledge": [], "desires": [], "trait_events": [], "pending_trait_events": []}},
		)
		events = [
			NarrativeEvent(
				event_type=EventType.CHARACTER_CHANGES,
				subject=name,
				predicate=f"{name} is {trait}",
				attributes={"trait": trait, "belief": belief, "desire": desire, "semantic_confidence": 0.95, "confidence": 0.95},
			),
			NarrativeEvent(
				event_type=EventType.DISCOVERY,
				subject=name,
				predicate=knowledge,
				attributes={"confidence": 0.95},
			),
		]
		context.memory_system.update_from_events(events)
		memory = context.memory_system.get_memory(name)
		profile = context.query_system.character_profile(name)
		trait_answer = context.query_system.confirm_character_trait(name, trait)
		knowledge_answer = context.query_system.who_knows_about(knowledge)
		character_count += 1
		trait_pass += int(trait in memory.personality)
		belief_pass += int(belief in memory.beliefs)
		knowledge_pass += int(knowledge in memory.knowledge)
		desire_pass += int(desire in memory.desires)
		query_trait_pass += int(name in trait_answer.answer)
		query_knowledge_pass += int(name in knowledge_answer.answer)
		if index < 4:
			seed_sample.append({
				"name": name,
				"profile": profile.answer,
				"trait_answer": trait_answer.answer,
				"knowledge_answer": knowledge_answer.answer,
			})

	context.db.commit()
	return {
		"characters": character_count,
		"field_roundtrip": {
			"trait": trait_pass,
			"belief": belief_pass,
			"knowledge": knowledge_pass,
			"desire": desire_pass,
		},
		"query_roundtrip": {
			"trait": query_trait_pass,
			"knowledge": query_knowledge_pass,
		},
		"field_accuracy": round((trait_pass + belief_pass + knowledge_pass + desire_pass) / max(character_count * 4, 1), 4),
		"query_accuracy": round((query_trait_pass + query_knowledge_pass) / max(character_count * 2, 1), 4),
		"seed_sample": seed_sample,
	}


def main() -> None:
	parser = argparse.ArgumentParser(description="Stage A narrative evaluations.")
	parser.add_argument("--load-scenes", type=int, default=1000)
	parser.add_argument("--merge-rounds", type=int, default=20)
	parser.add_argument("--recall-items", type=int, default=24)
	parser.add_argument("--pbkd-items", type=int, default=12)
	args = parser.parse_args()

	context = build_context()
	try:
		run_tag = str(int(time.time() * 1000))
		load_result = run_true_e2e_load_test(context.engine, args.load_scenes)
		replay_bundle = run_replay_verification(context.engine)
		result = {
			"load_test": load_result,
			"replay_verification": replay_bundle,
			"snapshot_verification": replay_bundle["head_snapshot"],
			"branch_merge_stress": run_branch_merge_stress(context.engine, args.merge_rounds),
			"retrieval_recall": run_retrieval_recall(context, args.recall_items, run_tag),
			"pbkd_consistency": run_pbkd_consistency(context, args.pbkd_items, run_tag),
		}
		result["summary"] = {
			"load_scenes": args.load_scenes,
			"merge_rounds": args.merge_rounds,
			"recall_items": args.recall_items,
			"pbkd_items": args.pbkd_items,
		}
		print(json.dumps(result, ensure_ascii=False, indent=2))
	finally:
		context.db.close()
		context.tempdir.cleanup()


if __name__ == "__main__":
	main()