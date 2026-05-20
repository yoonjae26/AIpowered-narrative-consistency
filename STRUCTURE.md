# NarrativeOS Project Structure

## 📊 Project Statistics
- **Total Files**: 119 Python/Config files
- **Total Directories**: 67
- **Development Phases**: 4

## 📁 Directory Structure

```
NarrativeOS/
│
├── 📂 backend/                    # Python Backend (FastAPI)
│   │
│   ├── 📂 api/                   # [Phase 1] API Layer
│   │   ├── routes/               # API route handlers
│   │   │   ├── auth.py          # Authentication endpoints
│   │   │   ├── projects.py      # Project management
│   │   │   ├── narrative.py     # Narrative elements
│   │   │   ├── consistency.py   # Consistency checking
│   │   │   ├── export.py        # Export functionality
│   │   │   └── ws.py            # WebSocket endpoints
│   │   ├── middleware/          # HTTP middleware
│   │   │   ├── auth_middleware.py
│   │   │   ├── rate_limiter.py
│   │   │   └── logging_middleware.py
│   │   └── dependencies/        # FastAPI dependencies
│   │
│   ├── 📂 auth/                  # [Phase 1] Authentication
│   │   ├── jwt_handler.py       # JWT token management
│   │   ├── oauth_provider.py    # OAuth integration
│   │   ├── password_utils.py    # Password hashing
│   │   └── session_manager.py   # Session handling
│   │
│   ├── 📂 core/                  # [Phase 1] Core Utilities
│   │   ├── config.py            # App configuration
│   │   ├── constants.py         # Global constants
│   │   ├── security.py          # Security utilities
│   │   └── exceptions.py        # Custom exceptions
│   │
│   ├── 📂 narrative/             # [Phase 1] Narrative System
│   │   ├── character/           # Character management
│   │   │   ├── models.py        # P·B·K·D state models
│   │   │   ├── manager.py       # Character CRUD
│   │   │   └── arc_tracker.py   # Character arc tracking
│   │   ├── world/              # World building
│   │   │   ├── lore_manager.py
│   │   │   ├── canon_registry.py
│   │   │   └── magic_system.py
│   │   ├── timeline/           # Timeline management
│   │   │   ├── tracker.py
│   │   │   └── event_sequencer.py
│   │   ├── scenes/             # Scene management
│   │   │   ├── scene_manager.py
│   │   │   └── beat_sheet.py
│   │   ├── relationships/      # Character relationships
│   │   │   ├── graph.py
│   │   │   └── relationship_types.py
│   │   └── events/             # Event system
│   │
│   ├── 📂 consistency/           # [Phase 2] Consistency Engine
│   │   ├── agents/              # AI consistency agents
│   │   │   ├── logic_agent.py
│   │   │   ├── character_agent.py
│   │   │   └── timeline_agent.py
│   │   ├── checkers/            # Consistency checkers
│   │   │   ├── logic_checker.py
│   │   │   ├── canon_checker.py
│   │   │   ├── character_checker.py
│   │   │   └── semantic_validator.py
│   │   ├── warning_generator.py
│   │   └── conflict_resolver.py
│   │
│   ├── 📂 rag/                   # [Phase 2] RAG System
│   │   ├── embeddings/          # Text embeddings
│   │   │   ├── embedder.py
│   │   │   └── chunk_strategy.py
│   │   ├── retrieval/           # Document retrieval
│   │   │   ├── semantic_search.py
│   │   │   └── hybrid_search.py
│   │   ├── indexing/            # Vector indexing
│   │   └── context_builder/     # Context for LLMs
│   │
│   ├── 📂 llm/                   # [Phase 2] LLM Integration
│   │   ├── providers/           # LLM provider adapters
│   │   │   ├── anthropic.py
│   │   │   ├── openai.py
│   │   │   └── base.py
│   │   ├── agents/              # Specialized AI agents
│   │   │   ├── story_advisor.py
│   │   │   ├── consistency_agent.py
│   │   │   └── lore_agent.py
│   │   ├── prompts/             # Prompt templates
│   │   │   ├── system_prompts.py
│   │   │   └── templates/
│   │   └── chains/              # LangChain workflows
│   │
│   ├── 📂 cache/                 # [Phase 2] Caching Layer
│   │   ├── redis_client.py
│   │   ├── embedding_cache.py
│   │   └── session_cache.py
│   │
│   ├── 📂 export/                # [Phase 3] Export System
│   │   ├── pdf_exporter.py
│   │   ├── docx_exporter.py
│   │   ├── markdown_exporter.py
│   │   └── epub_exporter.py
│   │
│   ├── 📂 version_control/       # [Phase 3] Version Control
│   │   ├── snapshot_manager.py
│   │   ├── diff_engine.py
│   │   └── branch_manager.py
│   │
│   ├── 📂 collaboration/         # [Phase 4] Collaboration
│   │   ├── ws_manager.py
│   │   ├── crdt_sync.py
│   │   └── permission_manager.py
│   │
│   ├── 📂 observability/         # [Phase 2] Monitoring
│   │   ├── langfuse_client.py
│   │   ├── metrics.py
│   │   └── structured_logger.py
│   │
│   ├── 📂 database/              # [Phase 1] Database Layer
│   │   ├── models/              # SQLAlchemy models
│   │   ├── schemas/             # Pydantic schemas
│   │   ├── repositories/        # Data access layer
│   │   ├── migrations/          # Alembic migrations
│   │   └── vector_store.py      # Vector database
│   │
│   ├── 📂 services/              # [Phase 1] Business Logic
│   ├── 📂 tests/                 # Test Suite
│   │   ├── unit/
│   │   ├── integration/
│   │   └── e2e/
│   └── main.py                  # Application entry point
│
├── 📂 frontend/                  # [Phase 3] React Frontend
│   └── src/
│       ├── components/
│       │   ├── editor/          # Rich text editor
│       │   ├── character-panel/
│       │   ├── world-panel/
│       │   ├── timeline-view/
│       │   ├── relationship-graph/
│       │   └── consistency-sidebar/
│       ├── stores/              # Zustand state management
│       ├── hooks/               # React hooks
│       └── lib/                 # Utility functions
│
├── 📂 infrastructure/            # [Phase 1] DevOps
│   ├── docker/
│   │   ├── docker-compose.dev.yml
│   │   ├── docker-compose.prod.yml
│   │   ├── Dockerfile.backend
│   │   └── nginx/
│   ├── k8s/                     # [Phase 4] Kubernetes
│   └── ci/                      # GitHub Actions
│
├── 📂 docs/                      # Documentation
│   ├── architecture.md          # System architecture
│   ├── api-spec.md             # API specification
│   └── adr/                    # Architecture decisions
│
├── 📂 datasets/                  # Training data
├── 📂 experiments/               # ML experiments
├── 📂 notebooks/                 # Jupyter notebooks
├── 📂 scripts/                   # Utility scripts
│   ├── setup.sh                # Setup automation
│   └── seed_db.py              # Database seeding
│
├── .env.example                 # Environment template
├── .gitignore                   # Git ignore rules
├── Makefile                     # Build automation
├── pyproject.toml              # Python dependencies
└── README.md                    # Project overview
```

## 🚀 Quick Start

```bash
# 1. Run setup script
./scripts/setup.sh

# 2. Update environment variables
cp .env.example .env
# Edit .env with your API keys

# 3. Start development environment
make dev

# 4. Run tests
make test
```

## 📝 Development Phases

### Phase 1: Foundation ✨
- Core API structure (FastAPI)
- Authentication & Authorization
- Database models (PostgreSQL)
- Basic narrative management
- Character system (P·B·K·D model)
- World building foundations

### Phase 2: AI Integration 🤖
- RAG system implementation
- LLM provider integration
- Consistency checking agents
- Semantic search
- Observability (LangFuse)
- Caching layer (Redis)

### Phase 3: User Features 📱
- Export to multiple formats
- Version control system
- Frontend development
- Rich text editor
- Visualization components

### Phase 4: Collaboration 👥
- Real-time WebSocket sync
- CRDT conflict resolution
- Multi-user permissions
- Kubernetes deployment

## 🛠 Technology Stack

**Backend**: FastAPI, SQLAlchemy, PostgreSQL, Redis, LangChain
**AI/ML**: OpenAI, Anthropic, ChromaDB, Sentence Transformers
**Frontend**: Next.js, React, Zustand, TipTap, D3.js
**DevOps**: Docker, Kubernetes, GitHub Actions, Nginx
**Observability**: LangFuse, Structured Logging

## 📦 Key Features

- **P·B·K·D Character System**: Physical, Behavioral, Knowledge, Desires
- **AI-Powered Consistency**: Automated logic and canon checking
- **RAG Integration**: Semantic search across narrative elements
- **Timeline Management**: Event sequencing and conflict detection
- **Relationship Graphs**: Character connection visualization
- **Multi-format Export**: PDF, DOCX, Markdown, EPUB
- **Version Control**: Snapshot and branch management
- **Real-time Collaboration**: CRDT-based synchronization

---

**Created**: 2026-05-20
**Status**: Structure Complete ✅
