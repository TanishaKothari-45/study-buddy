# Study Buddy AI

> Production-grade, multi-agent RAG platform built for UPSC Civil Services preparation — serving real users.

Combines a Pinecone-backed retrieval pipeline with a LangGraph agent graph (Retriever → Mock Test → Evaluation) to deliver exam-accurate Q&A, Prelims MCQ generation, structured Mains answer writing, and handwritten answer evaluation — all in one platform.

### What makes this technically interesting
- **Custom MCP server** — built a Current Affairs MCP server that injects live news context into Mains answers at generation time
- **Async micro-batch MCQ pipeline** — generates 5–100 questions in parallel batches with semantic deduplication (embedding similarity at 88% threshold) and persistent job tracking so generation survives browser closes
- **Multi-model architecture** — Gemini 2.5 Pro for long-context answer generation and OCR; GPT-4o-mini for embeddings and MCQs
- **D3.js map microservice** — dedicated Node.js service generating SVG choropleth, marker, and river maps embedded directly in answers
- **LangSmith tracing** — full observability on every agent run for hallucination monitoring and eval
---

## 🚀 Quick Start

### Prerequisites
- Python 3.9+
- Node.js 20.9+ (required for Next.js 16)
- npm or yarn

### Starting All Services

```bash
# Terminal 1: Backend API (Port 8001)
cd backend
source venv/bin/activate  # or: python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload

# Terminal 2: Frontend (Port 3000)
cd web
npm install
npm run dev

# Terminal 3: Map Service (Port 3001)
cd map-service
npm install
npm start

# Terminal 4: Worker (Port 8002)
cd backend
source venv/bin/activate  # or: python -m venv venv && source venv/bin/activate
python -m app.worker
```

### Environment Variables

Create `.env` files in the respective directories:

**Backend (`backend/.env`):**
```env
# LLM APIs
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=...

# Vector Store
PINECONE_API_KEY=...
PINECONE_INDEX_NAME=study-buddy
USE_PINECONE=true

# News APIs (for current affairs)
GNEWS_API_KEY=...
NEWS_API_KEY=...
THENEWSAPI_KEY=...

# JWT (set in production)
JWT_SECRET_KEY=...
```

**Frontend (`web/.env.local`):**
```env
NEXT_PUBLIC_API_URL=http://localhost:8001
```

---

## 📁 Project Structure

```
study-buddy/
├── backend/                    # FastAPI application (Python)
│   ├── app/
│   │   ├── api/               # Versioned API routers
│   │   │   └── v1/            # API v1 endpoints
│   │   ├── core/              # Config, database, security, exceptions
│   │   ├── gemini_core/       # Gemini client wrapper
│   │   ├── middleware/        # Error handling middleware
│   │   ├── models/            # SQLAlchemy models
│   │   ├── prompts/           # Shared prompt templates
│   │   ├── routes/            # API endpoint implementations
│   │   ├── schemas/           # Pydantic schemas
│   │   └── utils/             # Core utilities
│   └── data/                  # SQLite databases
│
├── web/                       # Next.js 16 frontend
│   └── src/
│       ├── app/               # Pages (App Router)
│       ├── components/        # UI components (Radix UI)
│       ├── context/           # Auth context
│       ├── lib/               # API utilities
│       └── stores/            # Zustand state management
│
└── map-service/               # Node.js/D3.js map generation
    ├── generate_map.js        # SVG generation logic
    ├── server.js              # Express server
    └── utils/                 # Projections, caching
```

---

## 🔌 API Versioning

All API endpoints are versioned under `/api/v1/`:

| Endpoint | Description |
|----------|-------------|
| `POST /api/v1/upload/` | Upload PDF → chunk → embed → Pinecone |
| `POST /api/v1/upload-content-store/` | Upload PDF → SQLite content store |
| `POST /api/v1/query/` | RAG query with streaming |
| `POST /api/v1/mock-test/generate` | Generate Prelims MCQs (sync) |
| `POST /api/v1/mock-test/generate-async` | Generate MCQs (async batch) |
| `GET /api/v1/mock-test/status/{job_id}` | Poll async job status |
| `POST /api/v1/mains-answer/generate` | Generate structured Mains answer |
| `POST /api/v1/evaluate-answer/` | Evaluate handwritten answer |
| `POST /api/v1/auth/login` | JWT authentication |
| `POST /api/v1/auth/signup` | User registration |

---

## ✨ Features

### 1. Prelims Mock Test Generation (Batch Processing)

**New: Async batch processing for large question sets**

- Generate 5-100 questions with quality guarantees
- **Micro-batch architecture**: 5 questions per batch, parallel execution
- **Semantic deduplication**: Removes similar questions using embeddings (88% threshold)
- **Job tracking**: Resume generation if browser is closed
- **Progress polling**: Real-time progress updates via `/status/{job_id}`

**Generation Pipeline:**
```
Request (num_questions, topics, difficulty)
    ↓
Job Tracker (SQLite-backed, persistent)
    ↓
Micro-batch Generation (5 questions × N batches)
    ↓ (parallel with semaphore)
Batch Validation (schema + quality checks)
    ↓
Semantic Deduplication (embedding similarity)
    ↓
Final Quality Score + Response
```

### 2. Mains Answer Generation

- **IBC Format**: Introduction → Body → Conclusion
- **Directive Interpretation**: Discuss, Evaluate, Critically Examine, etc.
- **Mermaid Diagrams**: Auto-enforced (minimum 1 per answer)
- **Current Affairs Integration**: Real-time news via MCP server
- **Map Generation**: SVG maps embedded in answers

### 3. Map Generation (D3.js Microservice)

**Supported Map Types:**
- `choropleth`: Color-coded regions by value
- `markers`: Point markers with labels
- `rivers`: Major river paths
- `arrows`: Flow/migration indicators
- `combined`: Multiple types together

**Example map-json block:**
```json
{
    "mapType": "combined",
    "region": "india",
    "choropleth": {
        "values": {"Punjab": 12, "Haryana": 8},
        "unit": "million tonnes"
    },
    "markers": [
        {"name": "Delhi", "lat": 28.6, "lon": 77.2, "type": "capital"}
    ],
    "title": "Wheat Production in India"
}
```

### 4. Mermaid Diagram Rendering

Frontend renders Mermaid diagrams in answers with:
- Base theme with custom colors
- Compact sizing (max-width: 400px)
- Flowcharts, mindmaps, sequence diagrams supported

### 5. Answer Evaluation (OCR + AI Feedback)

- Upload handwritten PDF/image
- Gemini 2.5 Pro OCR extracts text
- AI evaluates against ideal answer structure
- Provides improved version with proper IBC format

---

## 🏗️ Architecture

### Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | Next.js 16, Tailwind CSS, Radix UI, Zustand |
| Backend | FastAPI (Python), SQLite, Pydantic |
| LLM | Gemini 2.5 Pro (answers, OCR), GPT-4o-mini (embeddings, MCQs) |
| Vector Store | Pinecone (primary), ChromaDB (fallback) |
| Content Store | SQLite (full text storage) |
| Map Service | Node.js, Express, D3.js |
| Auth | JWT + bcrypt |

### State Management (Frontend)

**Zustand stores with persistence:**

| Store | Purpose |
|-------|---------|
| `mockTestStore` | Test data, answers, job tracking |
| `mainsAnswerStore` | Generated answers |
| `chatStore` | Chat history, session management |

### Error Handling

**Centralized exception handling middleware:**

```python
# Custom exceptions (backend/app/core/exceptions.py)
- AppException (base)
- ValidationException (400)
- NotFoundException (404)
- AuthenticationException (401)
- AuthorizationException (403)
- ExternalServiceException (503)
- RateLimitException (429)
```

All errors return consistent JSON:
```json
{
    "error": "Message",
    "error_code": "ERROR_CODE",
    "details": {},
    "timestamp": "ISO-8601",
    "path": "/api/v1/..."
}
```

---

## 🗄️ Database Locations

```
backend/data/databases/
├── content_store.db    # Full text chunks (SQLite)
├── memory.db           # Question recency + feedback
├── sql_app.db          # User authentication
└── chroma.sqlite3      # ChromaDB (fallback vector store)
```

---

## 🎨 Theme System

**Light Theme (Oatmilk):**
- Background: Warm off-white (#FAF8F5)
- Text: Soft brown
- Accent: Coral/Copper

**Dark Theme (Charcoal + Gold):**
- Background: Deep charcoal (#1a1a1f)
- Text: Warm off-white
- Accent: Gold/Amber

---

## 📝 Key Utilities

| Utility | Purpose |
|---------|---------|
| `hierarchical_chunker.py` | PDF chunking with structure detection |
| `content_store.py` | SQLite storage for full chunk content |
| `pinecone_handler.py` | Vector store operations |
| `question_parser.py` | Extract search terms from UPSC questions |
| `current_affairs_fetcher.py` | News API integration |
| `memory_manager.py` | Question recency tracking |
| `job_tracker.py` | Async job management |
| `batch_validator.py` | MCQ quality validation |
| `semantic_dedup.py` | Embedding-based deduplication |
| `map_proxy.py` | Map service integration |

---

## 🔧 Development

### Running Tests
```bash
cd backend
pytest tests/
```

### Code Quality
```bash
# Backend
pip install ruff
ruff check backend/

# Frontend
cd web
npm run lint
```

---

## 📊 Ports Reference

| Service | Port | URL |
|---------|------|-----|
| Backend API | 8001 | http://localhost:8001 |
| Frontend | 3000 | http://localhost:3000 |
| Map Service | 3001 | http://localhost:3001 |

---

## 🚧 Known Limitations

1. Map service must be running for maps to work in answers
2. ChromaDB fallback less tested than Pinecone
3. JWT secret falls back to OpenAI key if not set (fix for production)

---

## 📜 License

Private - All rights reserved.

---

*Last Updated: December 2024*
