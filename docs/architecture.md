# NarrativeOS Architecture

## System Overview

NarrativeOS is a comprehensive narrative writing and consistency management system that leverages AI to help writers maintain consistency across complex storylines, characters, and world-building elements.

## Architecture Diagram

```
┌─────────────┐
│   Frontend  │ (React/Next.js)
└──────┬──────┘
       │ HTTP/WebSocket
┌──────▼──────┐
│   API       │ (FastAPI)
│   Gateway   │
└──────┬──────┘
       │
┌──────▼────────────────────────────┐
│        Backend Services            │
│ ┌──────┐  ┌──────┐  ┌──────┐     │
│ │Narrative│ │Consis-│ │ RAG  │    │
│ │Manager │ │tency │ │System│     │
│ └──────┘  └──────┘  └──────┘     │
└───────────────┬───────────────────┘
                │
┌───────────────▼───────────────────┐
│        Data Layer                 │
│ ┌────────┐ ┌──────┐ ┌──────┐    │
│ │Postgres│ │Vector│ │Redis │    │
│ │+ pgvec │ │  DB  │ │Cache │    │
│ └────────┘ └──────┘ └──────┘    │
└───────────────────────────────────┘
```

## Core Components

### 1. API Layer (Phase 1)
- FastAPI-based REST API
- WebSocket support for real-time collaboration
- Authentication & authorization
- Rate limiting & middleware

### 2. Narrative Management (Phase 1)
- **Character System**: P·B·K·D state tracking, character arcs
- **World Building**: Lore management, canon registry, magic systems
- **Timeline**: Event sequencing, temporal consistency
- **Scenes**: Scene management, beat sheets
- **Relationships**: Character relationship graphs

### 3. Consistency Engine (Phase 2)
- Logic consistency checking
- Canon compliance validation
- Character behavior analysis
- Timeline conflict detection
- Semantic validation

### 4. RAG System (Phase 2)
- Document embeddings & chunking
- Semantic & hybrid search
- Context building for LLM prompts
- Vector indexing with pgvector/ChromaDB

### 5. LLM Integration (Phase 2)
- Multi-provider support (OpenAI, Anthropic)
- Specialized agents (story advisor, consistency checker, lore agent)
- Prompt templates & chains
- LangFuse observability

### 6. Export System (Phase 3)
- PDF, DOCX, Markdown, EPUB export
- Formatting & styling
- Metadata management

### 7. Version Control (Phase 3)
- Snapshot management
- Diff engine
- Branch management for alternative storylines

### 8. Collaboration (Phase 4)
- Real-time WebSocket sync
- CRDT-based conflict resolution
- Permission management

## Data Models

### Character Model (P·B·K·D)
- **Physical**: Appearance, abilities, limitations
- **Behavioral**: Patterns, habits, speech
- **Knowledge**: What they know, when they learned it
- **Desires**: Goals, motivations, conflicts

### World Model
- Canon facts & rules
- Magic/technology systems
- Geography & locations
- Historical events

### Timeline Model
- Events with timestamps
- Dependencies & causality
- Multiple timeline support

## Technology Stack

### Backend
- **Framework**: FastAPI (async Python)
- **Database**: PostgreSQL with pgvector extension
- **Cache**: Redis
- **Vector DB**: ChromaDB
- **AI/ML**: LangChain, OpenAI, Anthropic
- **Observability**: LangFuse

### Frontend
- **Framework**: Next.js 14 (React)
- **State**: Zustand
- **Editor**: TipTap or Slate
- **Visualization**: D3.js

### Infrastructure
- **Containers**: Docker & Docker Compose
- **Orchestration**: Kubernetes (production)
- **CI/CD**: GitHub Actions
- **Reverse Proxy**: Nginx

## Security

- JWT-based authentication
- Role-based access control (RBAC)
- Rate limiting
- Input validation
- API key encryption

## Scalability Considerations

- Async processing for LLM calls
- Redis caching for embeddings
- Database connection pooling
- Horizontal scaling via K8s
- CDN for static assets

## Development Phases

1. **Phase 1**: Foundation (API, Auth, Core Models)
2. **Phase 2**: AI Integration (RAG, LLM, Consistency)
3. **Phase 3**: User Features (Export, Version Control, Frontend)
4. **Phase 4**: Collaboration (Real-time, Multi-user)
