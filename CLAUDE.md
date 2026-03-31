# Study Buddy AI — Project Instructions

AI-powered UPSC study companion with RAG-based Q&A, prelims test generation, mains answer writing, and handwritten answer evaluation.

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | FastAPI (Python 3.9+), SQLAlchemy, SQLite, Pydantic |
| Frontend | Next.js 16 (App Router), React 19, Tailwind CSS 4, Radix UI, Zustand |
| LLM | Gemini 2.5 Pro (answers, OCR), GPT-4o-mini (embeddings, MCQs) |
| Vector Store | Pinecone (primary), ChromaDB (fallback) |
| Map Service | Node.js, Express, D3.js (port 3001) |
| Auth | Supabase Auth + JWT + bcrypt |
| Testing | pytest (backend), Vitest + Testing Library (frontend) |

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
    services/               # Business logic (retrieval_graph)
    utils/                  # Core utilities (chunker, pinecone, OCR, etc.)
    worker.py               # Background job worker (arq)
  data/databases/           # SQLite databases

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
| Worker | 8002 | `cd backend && python -m app.worker` |

Activate venv before running Python: `source venv/bin/activate`

## API Endpoints

All endpoints versioned under `/api/v1/`:

- `POST /upload/` — Upload PDF, chunk, embed to Pinecone
- `POST /upload-content-store/` — Upload PDF to SQLite content store
- `POST /query/` — RAG query with streaming
- `POST /mock-test/generate` — Sync MCQ generation
- `POST /mock-test/generate-async` — Async batch MCQ generation
- `GET /mock-test/status/{job_id}` — Poll async job status
- `POST /mains-answer/generate` — Structured Mains answer (IBC format)
- `POST /evaluate-answer/` — Evaluate handwritten answer via OCR
- `POST /auth/login`, `POST /auth/signup` — Authentication

## Key Architecture Patterns

### Backend

- **Centralized exceptions** in `core/exceptions.py` — AppException base with typed subclasses (Validation, NotFound, Auth, RateLimit, ExternalService)
- **Consistent error response** envelope: `{error, error_code, details, timestamp, path}`
- **Async batch processing** for MCQ generation: micro-batches of 5, semaphore-controlled parallelism, SQLite-backed job tracking
- **Semantic deduplication** using embedding similarity (88% threshold)
- **RAG pipeline**: question parsing → Pinecone retrieval → context enrichment → LLM generation
- **Content store**: SQLite for full chunk text, Pinecone for vectors only

### Frontend

- **Zustand stores** with persistence for mockTest, mainsAnswer, chat state
- **Streaming responses** for RAG queries via fetch ReadableStream
- **Mermaid diagram** rendering in answers (flowcharts, mindmaps, sequence diagrams)
- **Map rendering** via map-service proxy (choropleth, markers, rivers, arrows, combined)
- **Theme system**: Light (Oatmilk warm off-white) / Dark (Charcoal + Gold)

## Coding Standards

### Python (Backend)

- Use Pydantic schemas for all request/response validation
- Parameterized queries only — no string interpolation in SQL
- Async endpoints where I/O-bound (httpx, aiohttp)
- Handle errors with custom exception classes, not bare try/except
- Type hints on all function signatures
- Keep route handlers thin — business logic goes in utils/services
- always use python version 3.11.14

### TypeScript (Frontend)

- Use TypeScript strict mode
- Components: functional with hooks, no class components
- State: Zustand stores, not prop drilling
- Styling: Tailwind utility classes, Radix UI primitives for accessible components
- API calls go through `lib/apiClient.ts`

### General

- Never hardcode secrets — use `.env` files and environment variables
- All user inputs validated at system boundaries
- Error messages should be user-friendly in UI, detailed in server logs
- Files under 800 lines; functions under 50 lines
- Conventional commits: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`

## Testing
- always set node ie nvm use 22
```bash
# Backend
cd backend && pytest tests/

# Frontend
cd web && npm run test:run

# Linting
ruff check backend/
cd web && npm run lint
```

## Environment Variables

Backend needs: `GEMINI_API_KEY`, `OPENAI_API_KEY`, `PINECONE_API_KEY`, `PINECONE_INDEX_NAME`, `JWT_SECRET_KEY`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`

Frontend needs: `NEXT_PUBLIC_API_URL=http://localhost:8001`, `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`

## Database

SQLite databases in `backend/data/databases/`:
- `content_store.db` — Full text chunks
- `memory.db` — Question recency + feedback tracking
- `sql_app.db` — User authentication
- `chroma.sqlite3` — ChromaDB fallback vector store

## Important Notes

- Map service must be running for map generation in Mains answers
- MCQ generation uses micro-batch architecture (5 per batch) with quality validation
- Mains answers enforce IBC format (Introduction → Body → Conclusion) with minimum 1 Mermaid diagram
- OCR evaluation uses Gemini 2.5 Pro for handwritten text extraction
- LangGraph retrieval graph in `backend/app/services/retrieval_graph/` for advanced RAG
