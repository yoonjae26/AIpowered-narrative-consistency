# NarrativeOS — Project Context for AI Assistant

## What is this project?

**NarrativeOS** is an **AI-powered narrative development environment** — think of it as "VSCode for novelists."

The goal is NOT to replace writers. Instead, it helps writers manage the complexity of long-form storytelling (novels, worldbuilding, screenplays) by acting as an intelligent assistant that tracks lore, characters, timelines, and detects logical contradictions.

---

## Core Problem Being Solved

When writing long narratives, writers face:
- **Character collapse** — a character acts against their established personality
- **Lore conflicts** — a world rule is broken without explanation (e.g. dead character comes back with no reason)
- **Timeline errors** — events happen in wrong order, dead characters reappear
- **AI hallucination** — LLMs forget earlier context and invent contradicting facts
- **Memory overload** — writers can't remember every detail of a large universe

---

## Architecture Overview

```
Client (Web / Desktop)
        ↓
API Gateway (FastAPI) — Auth, Rate limit, WebSocket
        ↓
Core Services:
  - Narrative Engine     → manages Characters, World, Timeline, Scenes
  - Consistency Agent    → detects logic errors, canon violations, character drift
  - RAG Engine           → embeds and retrieves lore/scenes by semantic similarity
  - LLM Orchestrator     → agents and chains powered by Anthropic / OpenAI
        ↓
Support Services:
  - Auth Service         → JWT, OAuth, project ownership
  - Export Service       → PDF, DOCX, Markdown, EPUB
  - Notification Service → realtime warnings via WebSocket
  - Cache (Redis)        → embedding cache, session cache
        ↓
Data Layer:
  - PostgreSQL           → users, projects, events, structured data
  - Qdrant (Vector DB)   → embeddings for characters, scenes, lore
  - Redis                → cache + task queue
  - S3 / MinIO           → exported files, backups
        ↓
Infrastructure: Docker Compose (dev) → Kubernetes (prod)
Observability: Langfuse (LLM tracing), Prometheus, Grafana, Sentry
```

---

## Project Structure

```
NarrativeOS/
│
├── backend/
│   ├── api/                   # FastAPI routes, middleware, dependencies
│   │   ├── routes/            # auth, projects, narrative, consistency, export, ws
│   │   └── middleware/        # auth, rate_limiter, logging
│   ├── auth/                  # JWT, OAuth, session, password utils
│   ├── core/                  # config, constants, security, exceptions
│   ├── narrative/
│   │   ├── character/         # PBKD model (Personality/Belief/Knowledge/Desire)
│   │   ├── world/             # lore_manager, canon_registry, magic_system
│   │   ├── timeline/          # tracker, event_sequencer
│   │   ├── scenes/            # scene_manager, beat_sheet
│   │   ├── relationships/     # character graph
│   │   └── events/
│   ├── consistency/
│   │   ├── agents/            # logic_agent, character_agent, timeline_agent
│   │   ├── checkers/          # logic, canon, character, semantic validators
│   │   ├── warning_generator.py
│   │   └── conflict_resolver.py
│   ├── rag/
│   │   ├── embeddings/        # embedder, chunk_strategy
│   │   ├── retrieval/         # semantic_search, hybrid_search (BM25 + vector)
│   │   ├── indexing/
│   │   └── context_builder/
│   ├── llm/
│   │   ├── providers/         # anthropic, openai, base abstraction
│   │   ├── agents/            # story_advisor, consistency_agent, lore_agent
│   │   ├── prompts/           # system_prompts, templates/
│   │   └── chains/
│   ├── cache/                 # redis_client, embedding_cache, session_cache
│   ├── export/                # pdf, docx, markdown, epub exporters
│   ├── version_control/       # snapshot_manager, diff_engine, branch_manager
│   ├── collaboration/         # ws_manager, crdt_sync, permission_manager
│   ├── observability/         # langfuse_client, metrics, structured_logger
│   ├── database/
│   │   ├── models/            # SQLAlchemy ORM models
│   │   ├── schemas/           # Pydantic schemas
│   │   ├── repositories/      # data access layer
│   │   ├── migrations/        # Alembic migrations
│   │   └── vector_store.py    # Qdrant client wrapper
│   ├── services/              # business logic layer
│   ├── tests/
│   │   ├── unit/
│   │   ├── integration/
│   │   └── e2e/
│   └── main.py
│
├── frontend/                  # Next.js + Tiptap editor + D3 graph + Zustand
├── infrastructure/
│   ├── docker/                # docker-compose.dev.yml, docker-compose.prod.yml, nginx
│   ├── k8s/                   # Kubernetes manifests (Phase 4)
│   └── ci/                    # GitHub Actions workflows
├── docs/
│   ├── architecture.md
│   ├── api-spec.md
│   └── adr/                   # Architecture Decision Records
├── datasets/
├── experiments/
├── notebooks/
├── scripts/
│   ├── setup.sh
│   └── seed_db.py
├── .env.example
├── Makefile
├── pyproject.toml
└── README.md
```

---

## Key Data Models

### Character — PBKD State
Each character has 4 tracked states:
```python
{
  "name": "John",
  "P": "Honest, protective",          # Personality
  "B": "Believes killing is wrong",   # Belief
  "K": "Thinks dragons are extinct",  # Knowledge
  "D": "Wants to protect his family"  # Desire
}
```

### World Entry
```python
{
  "category": "magic_system" | "history" | "faction" | "rule" | "canon_event",
  "title": "No resurrection rule",
  "content": "The dead cannot return to life under any circumstance.",
  "tags": ["death", "magic", "canon"]
}
```

### Consistency Warning
```python
{
  "severity": "error" | "warning" | "info",
  "type": "canon_violation" | "character_drift" | "timeline_error",
  "description": "Character John kills without hesitation — contradicts Belief: 'killing is wrong'",
  "references": ["character:john", "world:no-kill-belief"],
  "suggested_fix": "Add internal conflict or prior belief-changing event"
}
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend framework | FastAPI (Python 3.11+) |
| ORM | SQLAlchemy + Alembic |
| Relational DB | PostgreSQL 16 |
| Vector DB | Qdrant |
| Cache / Queue | Redis 7 |
| Embeddings | sentence-transformers |
| LLM Orchestration | LangChain (abstracted behind base.py) |
| LLM Providers | Anthropic Claude, OpenAI (swappable) |
| LLM Tracing | Langfuse |
| Auth | JWT (python-jose) + bcrypt |
| Frontend | Next.js + Tiptap + D3.js + Zustand |
| Containerization | Docker Compose (dev), Kubernetes (prod) |
| CI/CD | GitHub Actions |
| Monitoring | Prometheus + Grafana + Sentry |
| File storage | S3 / MinIO |

---

## Development Phases

| Phase | Focus | Duration |
|-------|-------|----------|
| **Phase 1** | Foundation: schema, auth, CRUD API, Docker | Weeks 1–6 |
| **Phase 2** | AI Core: RAG, embeddings, consistency agent, cache | Weeks 7–14 |
| **Phase 3** | Polish: frontend editor, export, version control, UI | Weeks 15–22 |
| **Phase 4** | Scale: collaboration, Kubernetes, fine-tuning, plugins | Week 23+ |

---

## Current Status

> **Phase 1 — just started.**
> Setting up project skeleton, Git, pyproject.toml, Docker Compose, and PostgreSQL schema.

---

## How to Help (Instructions for Copilot)

- This is a **Python / FastAPI** backend project.
- Always follow the **repository pattern** — routes → services → repositories → models.
- Every new feature should have a corresponding **pytest test**.
- LLM calls must always be wrapped with **Langfuse tracing**.
- All LLM providers go through `llm/providers/base.py` — **never call Anthropic/OpenAI directly** from business logic.
- Character state always uses the **PBKD structure** (`personality`, `belief`, `knowledge`, `desire`).
- When adding a new lore entry or character, **auto-embed and store in Qdrant**.
- Consistency checks follow the pipeline: **RAG retrieve → rule-based check → LLM check → generate warning**.
- Use **conventional commits**: `feat:`, `fix:`, `chore:`, `docs:`, `test:`.
- Environment variables come from `.env` via `core/config.py` using `pydantic-settings`. **Never hardcode secrets.**