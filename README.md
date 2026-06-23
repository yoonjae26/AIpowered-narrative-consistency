# NarrativeOS

A comprehensive narrative writing and consistency management system with AI-powered assistance.

## Project Structure

```
├── backend/          # Python backend (FastAPI)
├── frontend/         # React/Next.js frontend
├── infrastructure/   # K8s, CI/CD, server deployment notes
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

# Start backend API on server
make dev

# Run tests
make test
```

## Demo (One Command)

Run the full demo stack (LLM + backend + frontend) with GPU 3:

```bash
./scripts/start_demo.sh
```

Stop the full demo stack:

```bash
./scripts/stop_demo.sh
```

Endpoints:
- Demo UI: http://127.0.0.1:4173
- Backend API: http://127.0.0.1:8001
- LLM API: http://127.0.0.1:11434/v1

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
- Server-based deployment (no Docker in this repo workflow)
- Kubernetes (Production)
- GitHub Actions (CI/CD)
- Nginx (Reverse Proxy)

## License

MIT
