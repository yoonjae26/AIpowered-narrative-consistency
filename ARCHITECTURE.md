# NarrativeOS — Tài liệu Kiến trúc Hệ thống

> **Phạm vi:** Tài liệu này mô tả kiến trúc kỹ thuật chi tiết — module, luồng dữ liệu, sơ đồ tuần tự, và thiết kế cơ sở dữ liệu. Được tổng hợp trực tiếp từ mã nguồn.  
> **Phiên bản:** 0.1.0 | **Cập nhật:** 2026-07-03

---

## Mục lục

1. [Frontend Modules](#1-frontend-modules)
2. [Backend Modules](#2-backend-modules)
3. [Thiết kế Cơ sở Dữ liệu](#3-thiết-kế-cơ-sở-dữ-liệu)
4. [Luồng hoạt động của API](#4-luồng-hoạt-động-của-api)
5. [Luồng Xác thực người dùng (Authentication)](#5-luồng-xác-thực-người-dùng)
6. [Sơ đồ Tuần tự (Sequence Diagrams)](#6-sơ-đồ-tuần-tự)
7. [Sơ đồ Thành phần (Component Diagram)](#7-sơ-đồ-thành-phần)
8. [Luồng Dữ liệu Hệ thống (Data Flow)](#8-luồng-dữ-liệu-hệ-thống)

---

---

## 1. Frontend Modules

Frontend là **single-page vanilla JavaScript application** — không dùng React/Vue. Toàn bộ logic nằm trong 3 file:

```
frontend/demo/
  index.html   1,457 dòng   Cấu trúc HTML và DOM skeleton
  app.js       2,603 dòng   Toàn bộ logic JavaScript
  styles.css   2,940 dòng   Design system (CSS custom properties)
```

### 1.1 Sơ đồ module Frontend

```
frontend/demo/app.js
│
├── [INIT] DOM References Cache
│   └── elements = { sidebar, mainPanel, tabs, inputs, outputs... }
│
├── [STATE] Global State Object
│   └── state = { currentBranch, characters, lastAnalysis }
│
├── [HTTP] API Client
│   └── callJson(url, opts)
│       ├── fetch() với error handling
│       ├── 4xx/5xx → hiển thị error toast
│       └── return parsed JSON
│
├── [MODULE] Scene Editor
│   ├── #sceneInput          textarea nhập cảnh
│   ├── submitScene()        POST /narrative/process-scene
│   ├── renderAnalysisResult() hiển thị events + warnings
│   └── renderTimelineBeats()
│
├── [MODULE] Character Manager
│   ├── loadCharacters()     GET /narrative/characters
│   ├── renderCharacterList() sidebar với status badges
│   ├── createCharacter()    POST /narrative/characters
│   └── updateCharacter()    PUT /narrative/characters/:id
│
├── [MODULE] Query Tab
│   ├── #queryInput          textarea tiếng Hàn
│   ├── submitQuery()        POST /narrative/query
│   ├── renderQueryAnswer()  answer + evidence list
│   └── renderReasoningGraph() Reasoning Graph JSON → HTML
│
├── [MODULE] Rewrite Tab
│   ├── rewriteScene()       POST /narrative/rewrite
│   ├── structuredAutoEdit() POST /narrative/rewrite/structured
│   ├── reviewPatches()      POST /narrative/rewrite/structured/review
│   ├── renderDiffPreview()  before/after diff display
│   └── applyRewrite()       áp dụng patch vào scene text
│
├── [MODULE] Consistency Tab
│   ├── runConsistencyCheck() POST /consistency/check
│   ├── renderCanonBadge()   R1 status: ✓ / ✗ N
│   ├── renderRelsBadge()    R2 status: ✓ / ✗ N
│   ├── renderPBKDBadge()    R3 status: ✓ / ✗ N
│   └── renderIssueList()    severity-colored issue list
│
├── [MODULE] Graph Tab
│   ├── loadRelationshipGraph() GET /narrative/relationships
│   └── renderGraph()        JSON nodes/edges → HTML grid
│
├── [MODULE] Timeline Tab
│   ├── loadTimeline()       GET /narrative/timeline
│   └── renderTimeline()     events theo thứ tự thời gian
│
├── [MODULE] Branch Manager
│   ├── loadBranches()       GET /narrative/branches
│   ├── createBranch()       POST /narrative/branch
│   ├── checkoutBranch()     POST /narrative/checkout
│   └── renderBranchSelector() dropdown trong sidebar
│
├── [PATTERN] Badge Observer
│   ├── MutationObserver trên #consistencyOutput (hidden <pre>)
│   └── tự động cập nhật badge count trên Consistency tab
│
└── [MODULE] Ctrl+K Search Modal
    ├── fuzzy filter theo text
    ├── actions: Run Analysis, New Character, Query Story, Reset, Health Check
    └── arrow key navigation + Enter execute + Esc close
```

### 1.2 Layout IDE

```
┌────────────────────────────────────────────────────────────────────────┐
│  TOPBAR                                                                │
│  NarrativeOS  ·  Branch: main ▼  ·  [Ctrl+K Search]  ·  🟢 LLM Ready │
├────────────┬───────────────────────────────────────────────────────────┤
│            │                                                           │
│  SIDEBAR   │  MAIN EDITOR PANEL                                        │
│            │                                                           │
│  ● 카엘    │  ┌─────────────────────────────────────────────────────┐  │
│    alive   │  │ Scene Input Textarea                                │  │
│  ● 오린    │  │ (tiếng Hàn, multi-line)                             │  │
│    alive   │  └─────────────────────────────────────────────────────┘  │
│  ✖ 에르나  │                                                           │
│    dead    │  [▶ Submit Scene]  [Reset]  [Health Check]               │
│            │                                                           │
│  [+] New   │  ══ Analysis Results ══════════════════════════════════   │
│            │  Events: BETRAYAL, CONFLICT...                            │
│  Branch:   │  Warnings: R2 relationship_conflict                       │
│  main  ▼   │  Timeline: Beat 1 · Beat 2 · Beat 3                      │
│            │                                                           │
│            ├───────────────────────────────────────────────────────────┤
│            │  BOTTOM TABS                                              │
│            │  [Query] [Rewrite] [Consistency] [Graph] [Timeline]      │
│            │                                                           │
│            │  (tab content rendered here)                              │
└────────────┴───────────────────────────────────────────────────────────┘
```

### 1.3 Design System (CSS Custom Properties)

```css
/* Color tokens — defined in :root */
--bg        /* #0F1117 — dark navy background */
--card      /* #1A1E2E — surface / card */
--bdr-lo    /* subtle border */

--t1, --t2  /* Text: heading, body */
--t3, --t4  /* Text: muted, placeholder */

--ac        /* #4E9FFF — accent blue */
--ac-dim    /* accent with opacity */

--ok        /* #22C55E — success / pass */
--wn        /* #F59E0B — warning */
--er        /* #EF4444 — error */
--cd        /* deep / secondary accent */
--r         /* border-radius base */
```

---

---

## 2. Backend Modules

### 2.1 Cấu trúc module theo domain

```
backend/
│
├── main.py                          FastAPI application entry point
│
├── api/                             ─── HTTP Layer ───
│   ├── dependencies/
│   │   └── __init__.py              get_db(), get_token_payload(), get_bearer_token()
│   ├── middleware/
│   │   ├── logging_middleware.py    Request/response logging (outermost)
│   │   ├── auth_middleware.py       JWT decode → request.state.user
│   │   └── rate_limiter.py          120 req / 60s sliding window per IP
│   └── routes/
│       ├── auth.py                  POST /auth/register, /login, /logout | GET /auth/me
│       ├── projects.py              CRUD /api/projects/*
│       ├── narrative.py             /narrative/* (chars, scenes, query, rewrite, vcs)
│       ├── consistency.py           POST /consistency/check
│       ├── export.py                GET /export/pdf|docx|md|epub
│       └── ws.py                    WebSocket /ws/*
│
├── auth/                            ─── Authentication ───
│   ├── jwt_handler.py               issue_token_pair(), validate_token()
│   ├── password_utils.py            create_password_hash(), check_password()
│   ├── oauth_provider.py            Google, GitHub OAuth (thiết kế)
│   └── session_manager.py           In-memory session store, revoke_token()
│
├── core/                            ─── Shared Kernel ───
│   ├── config.py                    Settings (pydantic-settings, .env)
│   ├── constants.py                 CharacterRole, ConsistencySeverity enums
│   ├── exceptions.py                NarrativeError hierarchy
│   └── security.py                  create_access_token(), create_refresh_token(), decode_token()
│
├── database/                        ─── Data Access Layer ───
│   ├── session.py                   SQLAlchemy engine + SessionLocal + Base
│   ├── models/                      ORM models (11 tables)
│   ├── repositories/                Repository pattern (1 class per table)
│   ├── migrations/                  Alembic migrations (4 revisions)
│   └── vector_store.py              ChromaDB integration
│
├── narrative/                       ─── Core Domain ───
│   ├── state_engine.py              NarrativeStateMutationEngine (orchestrator)
│   ├── mutation/
│   │   ├── entity_extractor.py      Stage 1: trích xuất nhân vật, địa điểm, đồ vật
│   │   ├── event_generator.py       Stage 2: tạo NarrativeEvent list
│   │   ├── state_mutator.py         Stage 3: ghi DB (characters, scenes, timeline)
│   │   ├── consistency_checker.py   Stage 4: rule-based consistency check
│   │   └── models.py                EventType, CharacterStatus, MutationResult enums
│   ├── character/
│   │   ├── models.py                CharacterPBKD, CharacterState, CharacterUpdate
│   │   └── memory.py                CharacterMemorySystem, SemanticCharacterDriftDetector
│   ├── query_system.py              Intent classification + retrieval + Verifier
│   ├── reasoning/
│   │   ├── sentence_role_parser.py  Korean sentence roles + CharacterRelationMemory
│   │   └── pbkd_reasoner.py         PBKD inference chain
│   ├── reality/
│   │   ├── knowledge_graph.py       NarrativeKnowledgeGraph (nodes + edges)
│   │   └── explainable_reasoning.py ExplainableReasoningEngine + Reasoning Graph
│   ├── relationships/
│   │   └── graph.py                 RelationshipGraph (ally/enemy/family...)
│   ├── timeline/
│   │   └── timeline_engine.py       TimelineEngine + beat management
│   ├── world/
│   │   ├── canon_protection.py      CanonProtectionLayer
│   │   ├── canon_registry.py        CanonRegistry
│   │   └── lore_manager.py          LoreManager
│   ├── deterministic_analysis.py    DeterministicNarrativeAnalyzer (no-LLM)
│   ├── analysis_queue.py            SceneAnalysisQueue (async job queue)
│   ├── analysis_cache.py            SceneAnalysisCache
│   ├── analysis_worker.py           Background process: polls queue, runs LLM analysis
│   ├── korean_text.py               normalize_korean_text(), extract_character_query_name()
│   └── response_formatter.py        format_mutation_api_response()
│
├── consistency/                     ─── Consistency Subsystem ───
│   ├── checkers/
│   │   ├── symbolic_engine.py       SymbolicConsistencyEngine (R1/R2/R3, no LLM)
│   │   └── semantic_validator.py    SemanticValidator (LLM-backed)
│   └── agents/
│       ├── lore_agent.py            LoreAgent: world rules
│       ├── character_agent.py       CharacterAgent: behavior
│       ├── timeline_agent.py        TimelineAgent: causality
│       └── critic_agent.py          CriticAgent: overall quality
│
├── rag/                             ─── RAG System ───
│   ├── embeddings/
│   │   └── embedder.py              SentenceTransformerEmbedder + HashEmbedder
│   ├── retrieval/
│   │   └── hybrid_search.py         HybridSearch: semantic + keyword
│   └── context_builder/
│       └── narrative_memory.py      NarrativeMemoryService (index + search)
│
├── llm/                             ─── LLM Providers ───
│   ├── providers/
│   │   ├── base.py                  BaseLLMProvider interface
│   │   ├── qwen.py                  QwenProvider (Ollama OpenAI-compatible)
│   │   ├── openai_provider.py       OpenAIProvider
│   │   └── anthropic_provider.py    AnthropicProvider
│   └── healthcheck.py               run_startup_llm_healthcheck()
│
├── version_control/                 ─── Story VCS ───
│   ├── story_vcs.py                 StoryVersionControl (facade)
│   ├── event_store.py               EventStore (.jsonl append-only)
│   ├── snapshot_manager.py          SnapshotManager (full state JSON)
│   ├── branch_manager.py            BranchManager (branch head pointers)
│   └── diff_engine.py               DiffEngine (compare snapshots)
│
├── export/                          ─── Export ───
│   ├── pdf_exporter.py              reportlab
│   ├── docx_exporter.py             python-docx
│   ├── markdown_exporter.py
│   └── epub_exporter.py             EbookLib
│
├── observability/                   ─── Monitoring ───
│   ├── langfuse_client.py           LangFuse tracing
│   ├── metrics.py                   compute_consistency_metrics()
│   └── structured_logger.py         JSON-format logger với correlation IDs
│
└── cache/                           ─── Caching ───
    ├── redis_client.py              Redis connection
    ├── embedding_cache.py           Cache embedding vectors
    └── session_cache.py             Session cache
```

### 2.2 Middleware Stack (thứ tự xử lý request)

FastAPI middleware được áp dụng theo thứ tự **LIFO** (Last In, First Out) — middleware được `add_middleware` cuối cùng sẽ chạy đầu tiên khi request đến.

```
REQUEST  ──►  LoggingMiddleware  (outermost, add đầu tiên)
              ──►  AuthMiddleware
                   ──►  RateLimiterMiddleware
                        ──►  CORSMiddleware  (innermost, add cuối cùng)
                             ──►  FastAPI Router
                             ◄──  Route Handler
                        ◄──  CORSMiddleware
                   ◄──  RateLimiterMiddleware (429 nếu vượt limit)
              ◄──  AuthMiddleware (decode JWT, attach user)
RESPONSE ◄──  LoggingMiddleware (log status code + latency)
```

**LoggingMiddleware:** Log mọi request và response với correlation ID.  
**AuthMiddleware:** Trích xuất JWT từ `Authorization: Bearer <token>`, decode, gán vào `request.state.user`. Không reject — nếu invalid, user = None (từng route tự quyết định có cần auth không).  
**RateLimiterMiddleware:** Sliding window 120 requests / 60 giây per IP. Dùng `deque` in-memory, không cần Redis.  
**CORSMiddleware:** Standard FastAPI CORS headers.

### 2.3 NarrativeStateMutationEngine — 20 subsystems

```python
class NarrativeStateMutationEngine:
    _extractor:         EntityExtractor            # Stage 1
    _generator:         EventGenerator             # Stage 2
    _mutator:           StateMutator               # Stage 3 — ghi DB
    _checker:           ConsistencyChecker         # Stage 4 — rule check
    _timeline:          TimelineEngine             # Timeline beats
    _memory:            NarrativeMemoryService     # RAG vector memory
    _char_memory:       CharacterMemorySystem      # Semantic char memory
    _drift:             SemanticCharacterDriftDetector
    _event_store:       EventStore                 # Event sourcing
    _vcs:               StoryVersionControl        # Git-like VCS
    _graph:             RelationshipGraph          # Relationship graph
    _canon_layer:       CanonProtectionLayer       # Canon rules
    _semantic:          SemanticValidator          # LLM semantic check
    _pbkd_reasoner:     PBKDReasoner              # PBKD inference
    _agents:            MultiAgentNarrativeAnalyzer  # 4 agents
    _query:             NarrativeQuerySystem       # Query handling
    _reasoning:         ExplainableReasoningEngine
    _knowledge_graph:   NarrativeKnowledgeGraph   # KG nodes/edges
    _analysis_cache:    SceneAnalysisCache
    _analysis_queue:    SceneAnalysisQueue        # Async job queue
    _deterministic:     DeterministicNarrativeAnalyzer
    _langfuse:          LangfuseClient            # Observability
```

---

---

## 3. Thiết kế Cơ sở Dữ liệu

### 3.1 Entity-Relationship Overview

```
users ─────────────────────────── projects
  │                                   │
  │                          ┌────────┴────────┐
  │                       characters         scenes
  │                          │    │              │
  │                          │  relationships   │
  │                          │                  │
  │                    timeline_events ◄────────┘
  │
  ├── lore_facts
  ├── canon_entries
  ├── magic_rules
  ├── arc_progress
  └── pipeline_audit
```

### 3.2 Schema chi tiết từng bảng

#### Bảng `users`
```sql
CREATE TABLE users (
    id              TEXT PRIMARY KEY,       -- UUID
    username        TEXT UNIQUE NOT NULL,
    password_hash   TEXT NOT NULL,          -- bcrypt hash
    email           TEXT,
    display_name    TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### Bảng `projects`
```sql
CREATE TABLE projects (
    id          TEXT PRIMARY KEY,           -- UUID
    name        TEXT NOT NULL,
    description TEXT,
    owner_id    TEXT REFERENCES users(id),
    settings    JSON,                       -- project config
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### Bảng `characters`
```sql
CREATE TABLE characters (
    id            TEXT PRIMARY KEY,         -- UUID
    name          TEXT NOT NULL,
    role          TEXT NOT NULL             -- CHECK: protagonist|antagonist|supporting|extra
                  CHECK(role IN ('protagonist','antagonist','supporting','extra')),
    traits        JSON,                     -- P: ["내성적", "완고함"] (personality)
    goals         JSON,                     -- D: ["오린을 구하고 싶다"] (desires)
    background    TEXT,
    status        TEXT DEFAULT 'alive'      -- alive|dead|injured|absent|unknown
                  CHECK(status IN ('alive','dead','injured','absent','unknown')),
    metadata_json JSON                      -- { beliefs: [...], knowledge: [...], desires: [...] }
                                            -- B: beliefs, K: knowledge, D: desires
);

-- metadata_json structure (PBKD):
-- {
--   "beliefs": ["평화주의", "약자 보호"],      -- B
--   "knowledge": ["마법 시스템", "왕의 비밀"],  -- K
--   "desires": ["오린을 구하고 싶다"]            -- D
-- }
```

#### Bảng `relationships`
```sql
CREATE TABLE relationships (
    id                TEXT PRIMARY KEY,
    source_id         TEXT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    target_id         TEXT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    relationship_type TEXT NOT NULL
                      CHECK(relationship_type IN ('ally','enemy','family','romantic','mentor','rival')),
    strength          REAL DEFAULT 0.5
                      CHECK(strength >= 0.0 AND strength <= 1.0),
    note              TEXT,
    created_at        DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### Bảng `scenes`
```sql
CREATE TABLE scenes (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    summary     TEXT,
    content     TEXT,                       -- full scene text
    beats       JSON,                       -- list[str] narrative beats
    characters  JSON,                       -- list[str] character names present
    scene_order INTEGER DEFAULT 0,
    branch      TEXT DEFAULT 'main',
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### Bảng `timeline_events`
```sql
CREATE TABLE timeline_events (
    id           TEXT PRIMARY KEY,
    title        TEXT NOT NULL,
    description  TEXT,
    event_type   TEXT,                      -- EventType enum value
    characters   JSON,                     -- list[str] involved characters
    location     TEXT,
    happened_at  DATETIME,
    scene_id     TEXT REFERENCES scenes(id),
    branch       TEXT DEFAULT 'main',
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### Bảng `lore_facts`
```sql
CREATE TABLE lore_facts (
    id         TEXT PRIMARY KEY,
    key        TEXT NOT NULL,              -- e.g. "부활_금지"
    value      TEXT NOT NULL,             -- e.g. "이 세계에서 죽은 자를 되살리는 것은 불가능하다"
    source     TEXT,                       -- scene title / user input
    tags       JSON,                       -- list[str]
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### Bảng `canon_entries`
```sql
CREATE TABLE canon_entries (
    id          TEXT PRIMARY KEY,
    rule        TEXT NOT NULL,             -- rule description (Korean)
    description TEXT,
    severity    TEXT DEFAULT 'error',      -- error | warning
    active      BOOLEAN DEFAULT TRUE,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### Bảng `magic_rules`
```sql
CREATE TABLE magic_rules (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT,
    constraints JSON,                      -- list of rule strings
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### Bảng `arc_progress`
```sql
CREATE TABLE arc_progress (
    id           TEXT PRIMARY KEY,
    character_id TEXT REFERENCES characters(id),
    arc_name     TEXT NOT NULL,
    stage        TEXT,                     -- setup|rising|climax|falling|resolution
    notes        TEXT,
    updated_at   DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### Bảng `pipeline_audit`
```sql
CREATE TABLE pipeline_audit (
    id           TEXT PRIMARY KEY,
    scene_id     TEXT,
    pipeline_run JSON,                     -- full pipeline execution record
    duration_ms  REAL,
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 3.3 File-based Storage (bên ngoài SQL)

```
.cache/
  narrative_memory_index.json     Vector index (embeddings + metadata)
  narrative_event_store.jsonl     Append-only event log (Story VCS)
  narrative_snapshots.json        Named snapshots (Story VCS)
  narrative_branches.json         Branch head pointers (Story VCS)

narrativeos.db                    SQLite database (dev)
```

---

---

## 4. Luồng hoạt động của API

### 4.1 Vòng đời một HTTP Request

```
Client
  │
  ▼  POST /narrative/process-scene
  │
  ├── LoggingMiddleware.dispatch()
  │     → ghi log request: method, path, client IP, correlation_id
  │
  ├── AuthMiddleware.dispatch()
  │     → đọc header: Authorization: Bearer <token>
  │     → decode_token(token) → JWT payload
  │     → request.state.user = payload (None nếu invalid/absent)
  │
  ├── RateLimiterMiddleware.dispatch()
  │     → kiểm tra bucket[client_ip] — sliding window 60s
  │     → nếu > 120 requests → HTTP 429 (không đi tiếp)
  │
  ├── CORSMiddleware
  │     → thêm CORS headers vào response
  │
  └── Router: narrative_router
        │
        └── route handler: process_scene()
              │
              ├── Depends(get_db)
              │     → mở SQLAlchemy Session (context manager)
              │
              ├── Tạo NarrativeStateMutationEngine với repositories
              │
              ├── engine.process_scene(scene_text, scene_title, context)
              │     → chạy pipeline 8 stages
              │
              ├── format_mutation_api_response(result)
              │     → chuẩn hóa output JSON
              │
              └── return JSONResponse
                    │
  ◄── LoggingMiddleware ghi log response: status_code, duration_ms
  │
Client ◄── JSON response
```

### 4.2 Các nhóm API và route chính

#### `/auth/*` — Authentication
| Method | Path | Mô tả |
|--------|------|--------|
| POST | `/auth/register` | Đăng ký tài khoản |
| POST | `/auth/login` | Đăng nhập, nhận JWT pair |
| POST | `/auth/logout` | Thu hồi token |
| GET  | `/auth/me` | Thông tin user hiện tại |

#### `/api/projects/*` — Project Management
| Method | Path | Mô tả |
|--------|------|--------|
| GET  | `/api/projects` | Danh sách project |
| POST | `/api/projects` | Tạo project mới |
| GET  | `/api/projects/:id` | Chi tiết project |
| PUT  | `/api/projects/:id` | Cập nhật project |
| DELETE | `/api/projects/:id` | Xóa project |

#### `/narrative/*` — Core Narrative
| Method | Path | Mô tả |
|--------|------|--------|
| POST | `/narrative/process-scene` | Submit cảnh → chạy full pipeline |
| GET  | `/narrative/characters` | Danh sách nhân vật |
| POST | `/narrative/characters` | Tạo nhân vật mới (với PBKD) |
| PUT  | `/narrative/characters/:id` | Cập nhật nhân vật |
| DELETE | `/narrative/characters/:id` | Xóa nhân vật |
| GET  | `/narrative/scenes` | Danh sách cảnh |
| GET  | `/narrative/timeline` | Timeline events |
| GET  | `/narrative/relationships` | Đồ thị quan hệ |
| POST | `/narrative/relationships` | Tạo quan hệ |
| POST | `/narrative/query` | Truy vấn ngôn ngữ tự nhiên |
| GET  | `/narrative/lore` | Danh sách lore facts |
| POST | `/narrative/lore` | Thêm lore fact |
| POST | `/narrative/canon` | Thêm canon rule |
| GET  | `/narrative/snapshots` | Danh sách snapshots |
| POST | `/narrative/snapshot` | Tạo snapshot |
| GET  | `/narrative/branches` | Danh sách branches |
| POST | `/narrative/branch` | Tạo branch |
| POST | `/narrative/checkout` | Checkout branch |
| POST | `/narrative/merge` | Merge branches |
| POST | `/narrative/cherry-pick` | Cherry-pick events |
| POST | `/narrative/rollback` | Rollback to snapshot |
| GET  | `/narrative/diff` | Diff giữa snapshots |
| POST | `/narrative/rewrite` | AI viết lại cảnh |
| POST | `/narrative/rewrite/structured` | Structured patches |
| POST | `/narrative/rewrite/structured/review` | Review + apply patches |

#### `/consistency/*` — Consistency Checking
| Method | Path | Mô tả |
|--------|------|--------|
| POST | `/consistency/check` | Chạy Symbolic Engine (R1/R2/R3) |

#### `/export/*` — Export
| Method | Path | Mô tả |
|--------|------|--------|
| GET | `/export/pdf` | Xuất PDF |
| GET | `/export/docx` | Xuất DOCX |
| GET | `/export/markdown` | Xuất Markdown |
| GET | `/export/epub` | Xuất EPUB |

#### `/ws/*` — WebSocket
| Protocol | Path | Mô tả |
|----------|------|--------|
| WS | `/ws/story` | Real-time sync (thiết kế tương lai) |

---

---

## 5. Luồng Xác thực người dùng

### 5.1 Đăng ký tài khoản

```
Client                          AuthRouter             UserRepository    SessionManager
  │                                  │                       │                │
  │── POST /auth/register ──────────►│                       │                │
  │   {username, password, email}    │                       │                │
  │                                  │── get_by_username() ─►│                │
  │                                  │◄─ None (chưa tồn tại)─│                │
  │                                  │                       │                │
  │                                  │── create() ──────────►│                │
  │                                  │   password_hash =      │                │
  │                                  │   bcrypt.hashpw(pwd)   │                │
  │                                  │◄─ User object ─────────│                │
  │                                  │                       │                │
  │                                  │── issue_token_pair(user.id) → TokenPair
  │                                  │   access_token  = JWT HS256, exp=30min
  │                                  │   refresh_token = JWT HS256, exp=7days
  │                                  │                       │                │
  │                                  │── create_session() ──────────────────►│
  │                                  │   {user_id, token, username}          │
  │                                  │                                        │
  │◄─ 200 AuthResponse ─────────────│                       │                │
  │   {access_token, refresh_token,  │                       │                │
  │    token_type="bearer", user}    │                       │                │
```

### 5.2 Đăng nhập

```
Client                    AuthRouter           UserRepository    security.py
  │                           │                     │                │
  │── POST /auth/login ──────►│                     │                │
  │   {username, password}    │                     │                │
  │                           │── get_by_username() ►│                │
  │                           │◄─ User or None ──────│                │
  │                           │                     │                │
  │                           │  if user is None → HTTP 401          │
  │                           │                     │                │
  │                           │── check_password() ──────────────────►│
  │                           │   bcrypt.checkpw(password, hash)     │
  │                           │◄─ bool ──────────────────────────────│
  │                           │                     │                │
  │                           │  if False → HTTP 401                 │
  │                           │                     │                │
  │                           │── issue_token_pair(user.id)          │
  │                           │   → access_token + refresh_token     │
  │                           │                     │                │
  │◄─ 200 AuthResponse ───────│                     │                │
```

### 5.3 Xác thực mỗi request (Middleware)

```
Client                  AuthMiddleware           security.py
  │                          │                       │
  │── GET /auth/me ─────────►│                       │
  │   Authorization:          │                       │
  │   Bearer eyJ...           │                       │
  │                           │                       │
  │                           │── decode_token(token)►│
  │                           │   jwt.decode(token,   │
  │                           │   secret_key, HS256)  │
  │                           │                       │
  │                           │  if JWTError:         │
  │                           │    user = None        │
  │                           │  else:                │
  │                           │    user = payload     │
  │                           │    {sub, type, iat,   │
  │                           │     exp, scopes}      │
  │                           │                       │
  │                           │  request.state.user = payload
  │                           │                       │
  │                           │── call_next(request) ►│── Route Handler
  │                           │                           (có thể đọc
  │                           │                            request.state.user)
  │                           │◄── Response ──────────────────────────
  │◄─ Response ───────────────│
```

### 5.4 JWT Token Structure

```
Header:  { "alg": "HS256", "typ": "JWT" }

Payload (access token):
  {
    "sub":    "user-uuid",          -- user ID
    "type":   "access",             -- "access" | "refresh"
    "iat":    1720000000,            -- issued at (unix timestamp)
    "exp":    1720001800,            -- expires at (30 min sau iat)
    "scopes": []                    -- permission scopes (thiết kế tương lai)
  }

Payload (refresh token):
  {
    "sub":    "user-uuid",
    "type":   "refresh",
    "iat":    1720000000,
    "exp":    1720604800            -- expires at (7 days sau iat)
  }

Signature: HMAC-SHA256(base64url(header) + "." + base64url(payload), SECRET_KEY)
```

### 5.5 Demo Mode (Bypass)

Trong môi trường demo, `AuthMiddleware` vẫn chạy nhưng routes không enforce `get_token_payload()` dependency — nghĩa là request không có JWT vẫn được xử lý. `request.state.user = None` và handlers hoạt động trong anonymous mode.

---

---

## 6. Sơ đồ Tuần tự (Sequence Diagrams)

### 6.1 Scene Submission — Luồng xử lý chính

```
Frontend        API             NarrativeStateMutationEngine
(app.js)      (narrative.py)         (state_engine.py)
    │               │                       │
    │─ POST ────────►│                       │
    │  /narrative/   │── process_scene() ───►│
    │  process-scene │   (scene_text,        │
    │                │    scene_title,       │
    │                │    context)           │
    │                │                       │
    │                │                       │── EntityExtractor.extract()
    │                │                       │   Korean heuristic + LLM
    │                │                       │   → {characters, locations, objects}
    │                │                       │
    │                │                       │── EventGenerator.generate()
    │                │                       │   → [NarrativeEvent, ...]
    │                │                       │     (DEATH, BETRAYAL, ALLIANCE...)
    │                │                       │
    │                │                       │── StateMutator.mutate()
    │                │                       │   → UPDATE characters.status
    │                │                       │   → INSERT scenes, timeline_events
    │                │                       │   → UPDATE relationships
    │                │                       │
    │                │                       │── CanonProtectionLayer.check_event()
    │                │                       │   → violations? → append warnings
    │                │                       │
    │                │                       │── NarrativeKnowledgeGraph.upsert()
    │                │                       │   → nodes + edges từ events
    │                │                       │
    │                │                       │── NarrativeMemoryService.add()
    │                │                       │   → embed scene + index vào .cache/
    │                │                       │
    │                │                       │── ConsistencyChecker.check()
    │                │                       │   → SymbolicConsistencyEngine (R1/R2/R3)
    │                │                       │   → [ConsistencyIssue, ...]
    │                │                       │
    │                │                       │── StoryVersionControl.append_commit()
    │                │                       │   → EventStore.append()
    │                │                       │   → SnapshotManager.create()
    │                │                       │   → BranchManager.update_head()
    │                │                       │
    │                │                       │── SceneAnalysisQueue.push()  ← async
    │                │                       │   (semantic + PBKD + multi-agent
    │                │                       │    xử lý bởi analysis_worker.py)
    │                │                       │
    │                │◄─ MutationResult ──────│
    │                │   {events, warnings,   │
    │                │    consistency_issues, │
    │                │    snapshot_id, ...}   │
    │                │                       │
    │◄─ JSON ────────│
    │  {events,      │
    │   warnings,    │
    │   timeline...} │
    │               │
```

### 6.2 Query — Truy vấn ngôn ngữ tự nhiên

```
Frontend        API             NarrativeQuerySystem         NarrativeMemoryService
(app.js)     (narrative.py)      (query_system.py)           (narrative_memory.py)
    │               │                   │                           │
    │─ POST ────────►│                   │                           │
    │  /narrative/   │── query() ───────►│                           │
    │  query         │   "카엘이 왜      │                           │
    │                │    배신했을까?"    │                           │
    │                │                   │── classify_intent()       │
    │                │                   │   → MOTIVATION            │
    │                │                   │                           │
    │                │                   │── extract_korean_names()  │
    │                │                   │   strip particles (은/는)  │
    │                │                   │   → ["카엘"]              │
    │                │                   │                           │
    │                │                   │── search_hierarchy() ─────►│
    │                │                   │   Phase 1: scenes          │── embed query
    │                │                   │   Phase 2: characters      │── cosine similarity
    │                │                   │   Phase 3: lore            │── keyword match
    │                │                   │   Phase 4: events         ◄│── rank + dedup
    │                │                   │◄─ [Hit, ...]              │
    │                │                   │                           │
    │                │                   │── build_reasoning_graph()  │
    │                │                   │   nodes: 카엘, 오린, 충성...
    │                │                   │   edges: has_belief, leads_to...
    │                │                   │                           │
    │                │                   │── generate_answer() (LLM) │
    │                │                   │   context = hits + graph  │
    │                │                   │   → answer text           │
    │                │                   │                           │
    │                │                   │── Verifier.validate()     │
    │                │                   │   check hard contradictions
    │                │                   │   support_score ≥ 0.65?   │
    │                │                   │   → pass / warn / reject  │
    │                │                   │                           │
    │                │◄─ QueryAnswer ────│                           │
    │                │   {answer,         │                           │
    │                │    evidence[],     │                           │
    │                │    reasoning_graph}│                           │
    │◄─ JSON ────────│                   │                           │
```

### 6.3 Login — Xác thực

```
Browser         AuthRouter          UserRepository    security.py    SessionManager
   │                │                    │                │               │
   │─POST/login ───►│                    │                │               │
   │ {user, pass}   │                    │                │               │
   │                │─ get_by_username()►│                │               │
   │                │◄─ User ────────────│                │               │
   │                │                    │                │               │
   │                │─ verify_password() ────────────────►│               │
   │                │  bcrypt.checkpw()                   │               │
   │                │◄─ True ────────────────────────────│               │
   │                │                    │                │               │
   │                │─ create_access_token(user.id) ─────►│               │
   │                │  HS256, exp=30min                   │               │
   │                │◄─ access_token ────────────────────│               │
   │                │                    │                │               │
   │                │─ create_refresh_token(user.id) ────►│               │
   │                │  HS256, exp=7days                   │               │
   │                │◄─ refresh_token ───────────────────│               │
   │                │                    │                │               │
   │                │─ create_session() ─────────────────────────────────►│
   │                │  {user_id, token, username}                         │
   │                │                    │                │               │
   │◄─200 ─────────│                    │                │               │
   │ {access_token, │                    │                │               │
   │  refresh_token,│                    │                │               │
   │  user: {...}}  │                    │                │               │
```

### 6.4 Rewrite — AI viết lại cảnh

```
Frontend        API                 LLMProvider          ConsistencyEngine
(app.js)    (narrative.py)         (qwen.py)            (symbolic_engine.py)
    │               │                   │                       │
    │─POST ─────────►│                   │                       │
    │ /narrative/    │                   │                       │
    │ rewrite/       │                   │                       │
    │ structured     │                   │                       │
    │ {source_text,  │                   │                       │
    │  instructions} │                   │                       │
    │                │── _extract_kg_evidence()                  │
    │                │   regex patterns tiếng Hàn               │
    │                │   → [KG triples]                          │
    │                │                   │                       │
    │                │── _build_kg_reasoning_issues()            │
    │                │   detect conflicts trong triples          │
    │                │   → [issues]                              │
    │                │                   │                       │
    │                │── llm.complete() ─►│                       │
    │                │   prompt: JSON     │                       │
    │                │   schema yêu cầu   │                       │
    │                │   patches[]        │                       │
    │                │◄─ JSON response ───│                       │
    │                │   {patches: [      │                       │
    │                │     {issue,        │                       │
    │                │      replace,      │                       │
    │                │      with: "...",  │                       │
    │                │      rationale}    │                       │
    │                │   ]}               │                       │
    │                │                   │                       │
    │◄─ patches ─────│                   │                       │
    │                │                   │                       │
    │── user chọn patch, click Apply     │                       │
    │                │                   │                       │
    │─POST ─────────►│                   │                       │
    │ /rewrite/      │── check_text() ──────────────────────────►│
    │ structured/    │   với text đã apply │                     │
    │ review         │◄─ issues[] ───────────────────────────────│
    │                │                   │                       │
    │◄─ reviewed ────│                   │                       │
    │  {patches,     │                   │                       │
    │   accepted,    │                   │                       │
    │   final_text}  │                   │                       │
```

### 6.5 Consistency Check (Symbolic Engine)

```
Frontend       ConsistencyRouter     SymbolicConsistencyEngine    Database
(app.js)      (consistency.py)        (symbolic_engine.py)         (repos)
    │               │                         │                       │
    │─POST ─────────►│                         │                       │
    │ /consistency/  │                         │                       │
    │ check          │                         │                       │
    │ {text,         │                         │                       │
    │  project_id}   │── check(text) ─────────►│                       │
    │                │                         │── CharacterRepository.list()──►│
    │                │                         │◄─ [Character, ...] ────────────│
    │                │                         │── RelationshipRepository.list()►│
    │                │                         │◄─ [Relationship, ...] ─────────│
    │                │                         │                       │
    │                │                         │── R1: _r1_dead_characters()
    │                │                         │   for each char in chars:
    │                │                         │     if status=="dead" AND name in text:
    │                │                         │       if no resurrection_token:
    │                │                         │         → ERROR "dead_character_active"
    │                │                         │
    │                │                         │── R2: _r2_relationship_conflicts()
    │                │                         │   for each rel in relationships:
    │                │                         │     if both names in text:
    │                │                         │       match conflict verbs by rel_type
    │                │                         │       → ERROR/WARNING "relationship_conflict"
    │                │                         │
    │                │                         │── R3: _r3_pbkd_conflicts()
    │                │                         │   for each char in chars:
    │                │                         │     if name in text:
    │                │                         │       read beliefs from metadata_json
    │                │                         │       match belief → conflict_verbs
    │                │                         │       → WARNING "pbkd_conflict"
    │                │                         │
    │                │◄─ [ConsistencyIssue] ───│                       │
    │                │   {severity, code,       │                       │
    │                │    message, entities,    │                       │
    │                │    evidence, rule}        │                       │
    │◄─ JSON ────────│                         │                       │
    │ {issues, count}│                         │                       │
```

---

---

## 7. Sơ đồ Thành phần (Component Diagram)

### 7.1 Kiến trúc tổng thể

```
╔═══════════════════════════════════════════════════════════════════════╗
║                         NARRATIVEOS SYSTEM                           ║
╠═══════════════════════════════════════════════════════════════════════╣
║                                                                       ║
║  ┌─────────────────────────────────────────────────────────────────┐  ║
║  │                      FRONTEND LAYER                             │  ║
║  │                                                                 │  ║
║  │  ┌───────────┐  ┌──────────────┐  ┌────────────────────────┐   │  ║
║  │  │ Scene     │  │  Query Tab   │  │    Consistency Tab      │   │  ║
║  │  │ Editor    │  │  (NL Korean) │  │  Quick Validation UI    │   │  ║
║  │  └─────┬─────┘  └──────┬───────┘  └──────────┬─────────────┘   │  ║
║  │        │               │                      │                 │  ║
║  │  ┌─────┴───────────────┴──────────────────────┴─────────────┐   │  ║
║  │  │                    callJson() API Client                  │   │  ║
║  │  └───────────────────────────────────────────────────────────┘   │  ║
║  └─────────────────────────┬───────────────────────────────────────┘  ║
║                             │  HTTP REST (port 8001)                   ║
║  ┌──────────────────────────▼───────────────────────────────────────┐  ║
║  │                      BACKEND LAYER                                │  ║
║  │                                                                   │  ║
║  │  ┌─────────────────────────────────────────────────────────────┐ │  ║
║  │  │                   Middleware Stack                           │ │  ║
║  │  │  Logging → Auth (JWT decode) → RateLimiter → CORS           │ │  ║
║  │  └─────────────────────────────────────────────────────────────┘ │  ║
║  │                                                                   │  ║
║  │  ┌───────────────────────────────────────────────────────────┐   │  ║
║  │  │              NarrativeStateMutationEngine                  │   │  ║
║  │  │                                                            │   │  ║
║  │  │  ┌─────────────┐   ┌──────────────┐   ┌───────────────┐  │   │  ║
║  │  │  │EntityExtract│──►│EventGenerator│──►│StateMutator   │  │   │  ║
║  │  │  │(heuristic+  │   │(action patt  │   │(DB writes)    │  │   │  ║
║  │  │  │ LLM)        │   │ + LLM)       │   │               │  │   │  ║
║  │  │  └─────────────┘   └──────────────┘   └───────┬───────┘  │   │  ║
║  │  │                                                │           │   │  ║
║  │  │  ┌────────────┐    ┌─────────────┐   ┌────────▼────────┐  │   │  ║
║  │  │  │CanonProtect│    │KnowledgeGrap│   │ConsistencyCheck │  │   │  ║
║  │  │  │   Layer    │    │    upsert   │   │(Symbolic R1/R2/ │  │   │  ║
║  │  │  └────────────┘    └─────────────┘   │        R3)      │  │   │  ║
║  │  │                                       └─────────────────┘  │   │  ║
║  │  │  ┌────────────────────────────────────────────────────────┐ │   │  ║
║  │  │  │    StoryVersionControl (EventStore + Snapshot + Branch) │ │   │  ║
║  │  │  └────────────────────────────────────────────────────────┘ │   │  ║
║  │  │                                                              │   │  ║
║  │  │  ┌────────────────────┐   push async ┌────────────────────┐ │   │  ║
║  │  │  │ SceneAnalysisQueue │─────────────►│  Analysis Worker   │ │   │  ║
║  │  │  └────────────────────┘              │  (separate proc)   │ │   │  ║
║  │  │                                       │  SemanticValidator │ │   │  ║
║  │  │                                       │  PBKDReasoner     │ │   │  ║
║  │  │                                       │  MultiAgent(×4)   │ │   │  ║
║  │  │                                       └────────────────────┘ │   │  ║
║  │  └───────────────────────────────────────────────────────────┘   │  ║
║  │                                                                   │  ║
║  │  ┌──────────────────┐    ┌─────────────────┐                     │  ║
║  │  │   RAG System     │    │   Auth System    │                     │  ║
║  │  │  ┌────────────┐  │    │  JWT + bcrypt    │                     │  ║
║  │  │  │ Embedder   │  │    │  SessionManager  │                     │  ║
║  │  │  │ (Korean ST)│  │    └─────────────────┘                     │  ║
║  │  │  ├────────────┤  │                                             │  ║
║  │  │  │HybridSearch│  │                                             │  ║
║  │  │  ├────────────┤  │                                             │  ║
║  │  │  │MemoryService│ │                                             │  ║
║  │  │  └────────────┘  │                                             │  ║
║  │  └──────────────────┘                                             │  ║
║  │                                                                   │  ║
║  │  ┌──────────┐  ┌──────────┐  ┌──────────┐                       │  ║
║  │  │  Qwen    │  │  OpenAI  │  │Anthropic │  LLM Providers        │  ║
║  │  │(Ollama)  │  │(optional)│  │(optional)│                       │  ║
║  │  └──────────┘  └──────────┘  └──────────┘                       │  ║
║  └──────────────────────────────┬────────────────────────────────────┘  ║
║                                  │                                       ║
║  ┌───────────────────────────────▼──────────────────────────────────┐   ║
║  │                       DATA LAYER                                  │   ║
║  │                                                                   │   ║
║  │  ┌────────────┐  ┌────────────┐  ┌─────────────┐  ┌──────────┐  │   ║
║  │  │SQLite/     │  │  ChromaDB  │  │ .cache/     │  │  Redis   │  │   ║
║  │  │PostgreSQL  │  │ (vectors)  │  │ (JSON VCS)  │  │(optional)│  │   ║
║  │  │(11 tables) │  │            │  │ event store │  │          │  │   ║
║  │  └────────────┘  └────────────┘  └─────────────┘  └──────────┘  │   ║
║  └───────────────────────────────────────────────────────────────────┘   ║
║                                                                       ║
╚═══════════════════════════════════════════════════════════════════════╝
```

### 7.2 Dependency Graph giữa các module Backend

```
main.py
  ├── api/routes/auth.py
  │     ├── auth/jwt_handler.py ──► core/security.py
  │     ├── auth/password_utils.py
  │     ├── auth/session_manager.py
  │     └── database/repositories/user_repository.py
  │
  ├── api/routes/narrative.py
  │     ├── narrative/state_engine.py ◄── tất cả subsystem
  │     │     ├── narrative/mutation/entity_extractor.py
  │     │     ├── narrative/mutation/event_generator.py
  │     │     ├── narrative/mutation/state_mutator.py
  │     │     ├── narrative/mutation/consistency_checker.py
  │     │     ├── narrative/query_system.py
  │     │     │     └── rag/context_builder/narrative_memory.py
  │     │     │           └── rag/embeddings/embedder.py
  │     │     ├── narrative/reasoning/pbkd_reasoner.py
  │     │     ├── narrative/reality/knowledge_graph.py
  │     │     ├── narrative/relationships/graph.py
  │     │     ├── narrative/timeline/timeline_engine.py
  │     │     ├── narrative/world/canon_protection.py
  │     │     ├── version_control/story_vcs.py
  │     │     │     ├── version_control/event_store.py
  │     │     │     ├── version_control/snapshot_manager.py
  │     │     │     └── version_control/branch_manager.py
  │     │     ├── consistency/checkers/symbolic_engine.py
  │     │     ├── consistency/checkers/semantic_validator.py
  │     │     ├── consistency/agents/ (×4)
  │     │     ├── llm/providers/qwen.py (hoặc openai/anthropic)
  │     │     └── observability/langfuse_client.py
  │     └── narrative/response_formatter.py
  │
  ├── api/routes/consistency.py
  │     └── consistency/checkers/symbolic_engine.py
  │           └── database/repositories/ (character, relationship)
  │
  └── api/middleware/
        ├── logging_middleware.py
        ├── auth_middleware.py ──► core/security.py
        └── rate_limiter.py ──► core/config.py
```

---

---

## 8. Luồng Dữ liệu Hệ thống (Data Flow)

### 8.1 Data Flow: Scene Submission

```
┌─────────────────────────────────────────────────────────────────────┐
│  INPUT: Scene Text (tiếng Hàn)                                      │
│  "카엘은 어둠 속에서 오린을 향해 칼을 들었다. 두 사람의 시선이 교차했다." │
└────────────────────────┬────────────────────────────────────────────┘
                          │
              ┌───────────▼───────────┐
              │   EntityExtractor     │  TRANSFORM
              │   Input:  raw text    │  → heuristic Korean name matching
              │   Output: entity map  │  → LLM fallback (if enabled)
              └───────────┬───────────┘
                          │
              entity_map = {
                "characters": ["카엘", "오린"],
                "locations":  [],
                "objects":    ["칼"]
              }
                          │
              ┌───────────▼───────────┐
              │   EventGenerator      │  TRANSFORM
              │   Input:  entity_map  │  → Korean verb pattern matching
              │   Output: events[]    │  → action classification
              └───────────┬───────────┘
                          │
              events = [
                NarrativeEvent(
                  type=CONFLICT,
                  subject="카엘",
                  target="오린",
                  predicate="공격",
                  location=None
                )
              ]
                          │
              ┌───────────▼───────────┐
              │    StateMutator       │  WRITE → Database
              │    Input:  events[]   │
              │    Output: mutations  │
              └───────────┬───────────┘
                          │
              DB Writes:
                INSERT scenes (title, content, characters, branch)
                INSERT timeline_events (type=CONFLICT, ...)
                — NOT UPDATE character.status (CONFLICT ≠ DEATH)
                          │
              ┌───────────▼───────────┐
              │  KnowledgeGraph       │  WRITE → in-memory graph
              │  Input:  events[]     │
              │  Output: edges        │
              └───────────┬───────────┘
                          │
              graph.upsert:
                node("카엘"), node("오린")
                edge("카엘" ──[attacks]──► "오린")
                          │
              ┌───────────▼───────────┐
              │  NarrativeMemoryService│ WRITE → .cache/
              │  Input:  scene_text   │  → embed(scene_text) → vector
              │          entity_map   │  → add to index
              │  Output: indexed      │
              └───────────┬───────────┘
                          │
              memory_index updated:
                {id: "scene_N", vector: [...384 dims...],
                 metadata: {type: "scene", characters: [...]}}
                          │
              ┌───────────▼───────────┐
              │  SymbolicEngine       │  READ → Database
              │  Input:  scene_text   │  → CharacterRepository.list()
              │  Output: issues[]     │  → RelationshipRepository.list()
              └───────────┬───────────┘
                          │
              Check results:
                R1: 오린 alive → PASS
                R2: 관계 없음 (rel chưa được lưu) → PASS
                R3: 카엘 beliefs=[] → PASS (no conflict)
                issues = []
                          │
              ┌───────────▼───────────┐
              │  StoryVersionControl  │  WRITE → .cache/
              │  Input:  events[]     │
              │  Output: commit       │
              └───────────┬───────────┘
                          │
              VCS commit:
                event_store.append(events)  → .jsonl
                snapshot.create(state_hash) → .json
                branch.update_head("main")  → .json
                          │
              ┌───────────▼───────────┐
              │  AnalysisQueue.push() │  WRITE → in-memory queue
              │  (async — non-block)  │  → analysis_worker.py polls
              └───────────┬───────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│  OUTPUT: MutationResult                                             │
│  {                                                                  │
│    "events":            [{"type": "CONFLICT", "subject": "카엘"}],  │
│    "warnings":          [],                                          │
│    "consistency_issues": [],                                         │
│    "snapshot_id":       "snap_20260703_001",                        │
│    "branch":            "main",                                      │
│    "timeline_beats":    ["카엘과 오린의 대치"]                        │
│  }                                                                  │
└─────────────────────────────────────────────────────────────────────┘
```

### 8.2 Data Flow: Query System

```
INPUT: "카엘이 왜 배신했을까?"
          │
          ▼
┌─────────────────────────────────────────────────────┐
│  IntentClassifier                                   │
│  Pattern matching trên query text                   │
│  → 왜/이유/동기 keywords → MOTIVATION               │
└──────────────────────────┬──────────────────────────┘
                            │ intent = MOTIVATION
                            ▼
┌─────────────────────────────────────────────────────┐
│  NameExtractor                                      │
│  Korean particle stripping                          │
│  "카엘이" → strip "이" → "카엘"                      │
└──────────────────────────┬──────────────────────────┘
                            │ names = ["카엘"]
                            ▼
┌─────────────────────────────────────────────────────┐
│  Retrieval Hierarchy (4 phases)                     │
│                                                     │
│  Phase 1: Scene sources                             │
│    embed("카엘이 왜 배신했을까?") → query_vector    │
│    cosine_similarity(query_vector, scene_vectors)   │
│    → top-K scene hits                               │
│                                                     │
│  Phase 2: Character sources                         │
│    PBKD lookup: 카엘.metadata_json.beliefs          │
│    → ["충성", "헌신"]                               │
│    → hit: {text: "카엘은 오린에게 충성을 맹세...",  │
│            source: "character", score: 0.91}       │
│                                                     │
│  Phase 3: Lore sources                              │
│    lore_facts matching "카엘"                       │
│    → []  (lore không liên quan)                     │
│                                                     │
│  Phase 4: Event sources                             │
│    events where subject="카엘" type=BETRAYAL        │
│    → hit: {event_type: "BETRAYAL", target: "오린"}  │
│                                                     │
│  Dedup: bigram Jaccard (threshold 0.55)             │
│  → 4 unique hits                                    │
└──────────────────────────┬──────────────────────────┘
                            │ hits[]
                            ▼
┌─────────────────────────────────────────────────────┐
│  ReasoningGraph Builder                             │
│  nodes: 카엘, 오린, 충성_신념, 보호_욕망            │
│  edges:                                             │
│    카엘 ──[has_belief]──► 충성_신념                  │
│    카엘 ──[has_desire]──► 오린_보호                  │
│    충성_신념 ──[conflicts]──► 배신_행동              │
│    오린_보호 ──[explains]──► 배신_행동               │
└──────────────────────────┬──────────────────────────┘
                            │ reasoning_graph
                            ▼
┌─────────────────────────────────────────────────────┐
│  AnswerGenerator (LLM)                              │
│  context = hits + reasoning_graph                   │
│  prompt: "다음 근거를 바탕으로 카엘의 배신 이유를..."  │
│  → answer: "카엘은 충성을 중시했지만..."             │
└──────────────────────────┬──────────────────────────┘
                            │ answer_text
                            ▼
┌─────────────────────────────────────────────────────┐
│  Verifier                                           │
│  Hard check: 카엘 alive? YES → OK                   │
│  Soft check: answer contradicts KG? NO → OK         │
│  Support score: 0.87 ≥ 0.65 → PASS                  │
└──────────────────────────┬──────────────────────────┘
                            │ verified
                            ▼
OUTPUT: QueryAnswer {
  answer: "카엘은 충성(신념)보다 오린 보호(욕망)를 선택했기에...",
  evidence: [
    {source: "character", text: "카엘 PBKD: desires=['오린 보호']", score: 0.99},
    {source: "scene",     text: "카엘은 오린을 지키기로 맹세했다", score: 0.85}
  ],
  reasoning_graph: {nodes: [...], edges: [...]},
  confidence: 0.87
}
```

### 8.3 Data Flow: Async Analysis Pipeline

```
Main Process (FastAPI)              Analysis Worker (separate process)
        │                                         │
        │  Scene submit complete                  │
        │                                         │
        │── SceneAnalysisQueue.push({             │
        │     scene_id,                           │
        │     scene_text,                         │
        │     policy_signature                    │
        │   }) ─────────────────────────────────► queue (in-memory)
        │                                         │
        │  return MutationResult to user          │
        │  (không đợi LLM analysis)              │
        │                                         │── poll() mỗi 1 giây
        │                                         │
        │                                         │  job = queue.get()
        │                                         │
        │                                         │── SemanticValidator.validate(text)
        │                                         │   LLM: kiểm tra ngữ nghĩa sâu
        │                                         │   → SemanticValidationResult
        │                                         │
        │                                         │── PBKDReasoner.reason(chars, events)
        │                                         │   LLM: chuỗi suy luận PBKD
        │                                         │   → PBKDInferenceChain
        │                                         │
        │                                         │── MultiAgentNarrativeAnalyzer.analyze()
        │                                         │   parallel: LoreAgent + CharacterAgent
        │                                         │           + TimelineAgent + CriticAgent
        │                                         │   → MultiAgentAnalysisReport
        │                                         │
        │                                         │── SceneAnalysisCache.store(
        │                                         │     scene_id, result
        │                                         │   )
        │                                         │
Frontend polls (nếu cần):          ◄──────────────│  (cached result sẵn sàng)
GET /narrative/analysis/:scene_id
```

### 8.4 Data Flow: Knowledge Graph

```
Scene Events ──► NarrativeKnowledgeGraph
                        │
                        │── upsert_node(name, type, properties)
                        │   node_types: CHARACTER, LOCATION, OBJECT, CONCEPT
                        │
                        │── upsert_edge(source, target, relation, weight)
                        │   relation types (từ EventType → edge):
                        │     DEATH        → died_at (location edge)
                        │     MURDER       → killed (character→character)
                        │     BETRAYAL     → betrayed
                        │     ALLIANCE     → allied_with
                        │     LOVE_REVEAL  → loves
                        │     RESCUE       → rescued
                        │
                        ▼
              In-memory graph (adjacency dict)
              {
                "카엘": {
                  "오린": [
                    {relation: "attacks", weight: 0.9, scene: "scene_3"},
                    {relation: "loves",   weight: 0.7, scene: "scene_1"}
                  ]
                }
              }
                        │
                        │── traverse(node, depth=2)
                        │   BFS/DFS tìm kết nối
                        │
                        ▼
              API: GET /narrative/graph
              Response: {
                nodes: [{id, label, type, properties}],
                edges: [{source, target, relation, weight}]
              }
```

### 8.5 Data Flow: Version Control (Story VCS)

```
Scene Submit
      │
      ▼
StoryVersionControl.append_commit(events, branch)
      │
      ├── EventStore.append(events)
      │   .cache/narrative_event_store.jsonl
      │   [APPEND]
      │   {"id": "evt_001", "type": "BETRAYAL", "subject": "카엘",
      │    "timestamp": "...", "branch": "main"}
      │   {"id": "evt_002", "type": "CONFLICT", ...}
      │
      ├── SnapshotManager.create(state_hash)
      │   .cache/narrative_snapshots.json
      │   [UPSERT]
      │   {"snap_001": {
      │     "hash": "sha256:abc...",
      │     "character_states": {"카엘": "alive", "오린": "alive"},
      │     "event_count": 5,
      │     "branch": "main",
      │     "timestamp": "..."
      │   }}
      │
      └── BranchManager.update_head("main", "snap_001")
          .cache/narrative_branches.json
          [UPDATE]
          {"main": {"head": "snap_001", "created_at": "..."}}


Rollback flow:
  POST /narrative/rollback {snapshot_id: "snap_001"}
    → SnapshotManager.load("snap_001")
    → StateMutator.restore(snapshot.character_states)
    → BranchManager.update_head("main", "snap_001")


Branch flow:
  POST /narrative/branch {name: "alternative", from_branch: "main"}
    → BranchManager.create("alternative", from="snap_001")
    → {"alternative": {"head": "snap_001", "parent": "main"}}

  POST /narrative/checkout {branch: "alternative"}
    → load character_states from alternative.head snapshot
    → all subsequent commits go to "alternative" branch
```

---

*Tài liệu được tổng hợp từ phân tích mã nguồn trực tiếp: `backend/main.py`, `backend/api/routes/`, `backend/narrative/state_engine.py`, `backend/consistency/checkers/symbolic_engine.py`, `backend/auth/`, `backend/core/security.py`, `backend/rag/`, `backend/version_control/`, `frontend/demo/app.js`.*
