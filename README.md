# NarrativeOS

A comprehensive narrative writing and consistency management system with AI-powered assistance.

## Project Structure

```
├── backend/          # Python backend (FastAPI)
├── frontend/         # React/Next.js frontend
├── infrastructure/   # Docker, K8s, CI/CD
├── docs/            # Documentation
├── datasets/        # Training and reference data
├── experiments/     # ML experiments
├── notebooks/       # Jupyter notebooks
└── scripts/         # Utility scripts
```

## Development Phases

- **Phase 1**: Core API, Auth, Database, Narrative Models
- **Phase 2**: RAG, LLM Integration, Consistency Checking, Observability
- **Phase 3**: Export, Version Control, Frontend
- **Phase 4**: Collaboration, Real-time features

## Setup

```bash
# Run setup script
./scripts/setup.sh

# Start development environment
make dev

# Run tests
make test
```

## Tech Stack

### Backend
- FastAPI
- PostgreSQL + pgvector
- Redis
- LangChain/LangFuse
- Anthropic/OpenAI APIs

### Frontend
- React/Next.js
- Zustand (State Management)
- TipTap/Slate (Rich Text Editor)
- D3.js (Relationship Graph)

### Infrastructure
- Docker & Docker Compose
- Kubernetes (Production)
- GitHub Actions (CI/CD)
- Nginx (Reverse Proxy)

## License

MIT
