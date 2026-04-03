# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Study Buddy AI — Project Instructions

AI-powered UPSC study companion with RAG-based Q&A, prelims test generation, mains answer writing, and handwritten answer evaluation.

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | FastAPI (Python 3.11.14), SQLAlchemy, SQLite, Pydantic |
| Frontend | Next.js 16 (App Router), React 19, Tailwind CSS 4, Radix UI, Zustand |
| LLM | Gemini 2.5 Pro (answers, OCR), GPT-4o-mini (embeddings, MCQs) |
| Vector Store | Pinecone (primary), ChromaDB (fallback) |
| Map Service | Node.js 22 (nvm), Express, D3.js (port 3001) |
| Auth | Supabase Auth + JWT + bcrypt |
| Testing | pytest (backend), Vitest + Testing Library (frontend) |
| Job Queue | arq (async task queue, worker in separate process) |

## Project Structure

```
backend/                    # FastAPI application
  app/
    api/v1/                 # Versioned API routers
    core/                   # Config, database, security, exceptions
    gemini_core/            # Gemini client wrapper
    models/                 # SQLAlchemy models (user, evaluation, mains)
    prompts/                # Shared prompt templates
    routes/                 # Endpoint implementations
    schemas/                # Pydantic request/response schemas
    services/               # Business logic (retrieval_graph for RAG)
    utils/                  # Core utilities (chunker, pinecone, OCR, job tracking, etc.)
    worker.py               # Background job worker (arq) — runs separately
  data/databases/           # SQLite databases (initialized on first run)
  tests/                    # pytest tests

web/                        # Next.js 16 frontend
  src/
    app/                    # Pages: chat, mock-test, mains-answer, evaluate, auth
    components/             # UI components (chat, evaluate, layout, ui)
    context/                # Auth context
    lib/                    # API client, Supabase client, utilities
    stores/                 # Zustand stores (mockTest, mainsAnswer, chat)

map-service/                # D3.js SVG map generation microservice
```

## Services & Ports

| Service | Port | Start Command |
|---------|------|---------------|
| Backend API | 8001 | `cd backend && uvicorn app.main:app --port 8001 --reload` |
| Frontend | 3000 | `cd web && npm run dev` |
| Map Service | 3001 | `cd map-service && npm start` |
| Worker (async jobs) | N/A | `source venv/bin/activate && cd backend && python -m app.worker` |

**Setup**: Activate venv before running Python: `source venv/bin/activate` and set Node to v22: `nvm use 22`

## API Endpoints

All endpoints versioned under `/api/v1/`:

- `POST /upload/` — Upload PDF, chunk, embed to Pinecone
- `POST /upload-content-store/` — Upload PDF to SQLite content store
- `POST /query/` — RAG query with streaming
- `POST /mock-test/generate` — Sync MCQ generation
- `POST /mock-test/generate-async` — Async batch MCQ generation (uses worker process)
- `GET /mock-test/status/{job_id}` — Poll async job status
- `POST /mains-answer/generate` — Structured Mains answer (IBC format)
- `POST /evaluate-answer/` — Evaluate handwritten answer via OCR
- `POST /auth/login`, `POST /auth/signup` — Authentication

## Development Setup

### First Time Setup
```bash
# Backend
python3.11 -m venv venv
source venv/bin/activate
cd backend && pip install -r requirements.txt

# Frontend
nvm use 22
cd web && npm install

# Map Service
cd map-service && npm install
```

### Create `.env` files
Copy `.env.example` to backend, frontend, and fill in API keys:
- Backend: `GEMINI_API_KEY`, `OPENAI_API_KEY`, `PINECONE_API_KEY`, `JWT_SECRET_KEY`, `SUPABASE_URL`
- Frontend: `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`

### Run All Services
Open 4 terminals:
```bash
# Terminal 1: Backend
source venv/bin/activate && cd backend && uvicorn app.main:app --reload

# Terminal 2: Frontend
nvm use 22 && cd web && npm run dev

# Terminal 3: Map Service
nvm use 22 && cd map-service && npm start

# Terminal 4: Worker (for async MCQ generation)
source venv/bin/activate && cd backend && python -m app.worker
```

## Key Architecture Patterns

### Backend

- **Centralized exceptions** in `core/exceptions.py` — AppException base with typed subclasses (Validation, NotFound, Auth, RateLimit, ExternalService)
- **Consistent error response** envelope: `{error, error_code, details, timestamp, path}`
- **Async batch processing** for MCQ generation: micro-batches of 5, semaphore-controlled parallelism, SQLite-backed job tracking via arq worker
- **Semantic deduplication** using embedding similarity (88% threshold) in `utils/semantic_dedup.py`
- **RAG pipeline**: question parsing → Pinecone retrieval → context enrichment → LLM generation (LangGraph in `services/retrieval_graph/`)
- **Content store**: SQLite for full chunk text, Pinecone for vectors only
- **Job tracking**: MCQ async jobs tracked in SQLite memory.db, polled via `/mock-test/status/{job_id}`

### Frontend

- **Zustand stores** with persistence for mockTest, mainsAnswer, chat state
- **Streaming responses** for RAG queries via fetch ReadableStream API
- **Mermaid diagram** rendering in answers (flowcharts, mindmaps, sequence diagrams)
- **Map rendering** via map-service HTTP proxy (choropleth, markers, rivers, arrows, combined types)
- **Theme system**: Light (Oatmilk warm off-white) / Dark (Charcoal + Gold)

## Coding Standards

### Python (Backend)

- Use Pydantic schemas for all request/response validation
- Parameterized queries only — no string interpolation in SQL
- Async endpoints where I/O-bound (httpx, aiohttp)
- Handle errors with custom exception classes, not bare try/except (see `core/exceptions.py`)
- Type hints on all function signatures
- Keep route handlers thin — business logic goes in utils/services
- Use Python 3.11.14 (enforced via `python3.11` command)

### TypeScript (Frontend)

- Use TypeScript strict mode
- Components: functional with hooks, no class components
- State: Zustand stores, not prop drilling
- Styling: Tailwind utility classes, Radix UI primitives for accessible components
- API calls go through `lib/apiClient.ts`
- Use Node 22 via nvm (enforced via `nvm use 22`)

### General

- Never hardcode secrets — use `.env` files and environment variables
- All user inputs validated at system boundaries
- Error messages should be user-friendly in UI, detailed in server logs
- Files under 800 lines; functions under 50 lines
- Conventional commits: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`

## Testing & Code Quality

### Common Commands

```bash
# Backend tests
cd backend && pytest tests/                    # Run all tests
cd backend && pytest tests/test_file.py        # Run specific test file
cd backend && pytest tests/test_file.py::test_func  # Run specific test function
cd backend && pytest -v                        # Verbose output
cd backend && pytest --tb=short                # Short traceback

# Frontend tests
cd web && npm run test:run                     # Run all tests once
cd web && npm run test                         # Watch mode

# Linting
ruff check backend/                            # Check all Python files
ruff check backend/app/utils/                  # Lint specific directory
cd web && npm run lint                         # ESLint check
```

### Code Quality Checks
```bash
# Before committing
ruff check backend/ && cd web && npm run lint  # Check both
```

## Environment Variables

### Backend (`backend/.env`)
```env
GEMINI_API_KEY=...              # For OCR, answer generation
OPENAI_API_KEY=...              # For embeddings, MCQ generation
PINECONE_API_KEY=...            # Vector store
PINECONE_INDEX_NAME=study-buddy
USE_PINECONE=true
JWT_SECRET_KEY=...              # For authentication
SUPABASE_URL=...                # Auth service
SUPABASE_ANON_KEY=...           # Auth service public key
```

### Frontend (`web/.env.local`)
```env
NEXT_PUBLIC_API_URL=http://localhost:8001
NEXT_PUBLIC_SUPABASE_URL=...
NEXT_PUBLIC_SUPABASE_ANON_KEY=...
```

## Database

SQLite databases auto-created in `backend/data/databases/`:
- `content_store.db` — Full text chunks from PDFs
- `memory.db` — Question recency, feedback tracking, job tracking
- `sql_app.db` — User authentication (SQLAlchemy)
- `chroma.sqlite3` — ChromaDB fallback vector store (if Pinecone unavailable)

Databases are created on first API call. No manual migration needed.

## Common Development Tasks

### Adding a New API Endpoint
1. Create schema in `backend/app/schemas/`
2. Create route in `backend/app/routes/` or `api/v1/`
3. Implement business logic in `backend/app/utils/` or `services/`
4. Add to `backend/app/main.py` routers
5. Test with `pytest` and check error responses match `core/exceptions.py`

### Modifying MCQ Generation
- Prompt: `backend/app/prompts/mcq_generation.py`
- Batch logic: `backend/app/utils/batch_validator.py`
- Job tracking: `backend/app/utils/job_tracker.py`
- Worker process: `backend/app/worker.py` — must be running for `/generate-async`

### Testing Streaming Responses
```python
# Test with curl
curl -N http://localhost:8001/api/v1/query/ \
  -H "Content-Type: application/json" \
  -d '{"question": "What is...?"}'
```

### Debugging Frontend State
- Zustand stores persist to localStorage with key `store-name`
- Open DevTools → Application → Local Storage to inspect
- Clear with: `localStorage.clear()` in console

### Debugging Async Jobs
- Check job status: `backend/data/databases/memory.db` table `job_status`
- Worker logs: output from `python -m app.worker` terminal
- If worker crashes, async endpoints will timeout

## Model Selection (Claude)

**Default allocation to optimize cost & speed:**

| Task | Model | Why |
|------|-------|-----|
| Read files, debugging, simple edits | Haiku 4.5 | Fast I/O, no reasoning needed |
| Agent creation, planning, complex code | Sonnet 4.6 | Balanced reasoning (use by default) |
| Mission-critical decisions (rare) | Opus 4.6 | Maximum reasoning (use sparingly) |

**Examples:**
- Reading CLAUDE.md → Haiku
- Creating PYQ Analysis Agent → Sonnet
- Finalizing pipeline architecture → Sonnet (or Opus if very high-stakes)
- Debugging test failure → Haiku

---

## Troubleshooting

### Backend won't start: "Address already in use"
```bash
# Find process using port 8001
lsof -i :8001
# Kill it
kill -9 <PID>
```

### Worker not processing jobs
- Ensure worker is running in separate terminal: `python -m app.worker`
- Check for errors in worker output
- Verify Redis/arq config (if applicable)

### Map service returning 500 errors
- Ensure map-service is running: `npm start` in `map-service/`
- Check map-service logs for errors
- Verify request format matches map-proxy expectations in backend

### Tests failing with "database is locked"
- Ensure venv is activated: `source venv/bin/activate`
- Check for other pytest processes: `ps aux | grep pytest`
- SQLite may be locked if another process holds connection; restart Python interpreter

### Frontend showing "Failed to fetch"
- Verify backend is running and `NEXT_PUBLIC_API_URL` is correct
- Check browser DevTools Network tab for actual error
- Ensure CORS is enabled in backend (should be by default in FastAPI setup)

### Pinecone query returning wrong results
- Check embedding consistency: ensure same model used for indexing and querying
- Verify index name in `PINECONE_INDEX_NAME` env var
- Check deduplication threshold (88%) in `utils/semantic_dedup.py`

## Important Patterns

- **Map service dependency**: Maps only render if map-service is running. Graceful fallback needed in frontend.
- **Async MCQ generation**: Uses arq worker (separate process). Job status polled via `/mock-test/status/{job_id}`.
- **IBC format enforcement**: Mains answers require Introduction-Body-Conclusion + min 1 Mermaid diagram.
- **OCR evaluation**: Uses Gemini 2.5 Pro. Handles skewed/handwritten PDFs.
- **RAG pipeline**: LangGraph state graph in `services/retrieval_graph/` orchestrates retrieval, context enrichment, and generation.
- **Error handling**: All errors routed through `core/exceptions.py` → consistent response envelope with `error_code` for client-side handling.
