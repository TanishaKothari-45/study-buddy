# Study Buddy AI - Complete System Architecture & Implementation Guide

> **Purpose**: This document serves as a comprehensive technical reference for an LLM to understand the entire system, suggest improvements, and guide next development steps.

---

## 1. PROJECT OVERVIEW

**Study Buddy AI** is an AI-powered UPSC (Union Public Service Commission) Geography study companion that helps students:
- Generate high-quality mock test questions (Prelims MCQs)
- Write and evaluate Mains answers with proper structure
- Get AI feedback on handwritten answers
- Access curated geography content with current affairs integration

### Core Value Proposition
1. **RAG-based Q&A**: Uses Pinecone vector store + SQLite content store for rich context retrieval
2. **Current Affairs Integration**: MCP server fetches real-time news for answer enhancement
3. **Map Generation**: D3.js microservice generates SVG maps (choropleth, markers, rivers)
4. **Answer Evaluation**: Gemini 2.5 Pro OCR reads handwritten answers and provides structured feedback

---

## 2. TECHNOLOGY STACK

### Backend (Python/FastAPI)
```
Framework: FastAPI
LLM Providers:
  - Google Gemini 2.5 Pro (mains answers, evaluation, OCR)
  - OpenAI GPT-4o-mini (embeddings, mock test generation)
Vector Store: Pinecone (primary) / ChromaDB (fallback)
Content Store: SQLite (full text storage)
Authentication: JWT + bcrypt
Database: SQLite (users, memory, content store)
```

### Frontend (Next.js 16)
```
Framework: Next.js 16 (App Router)
UI: Tailwind CSS + Radix UI components
Theme: Light (Oatmilk) / Dark (Charcoal + Gold)
State: React Context (Auth)
```

### Microservices
```
Map Service: Node.js + Express + D3.js (port 3001)
MCP Server: Python (Model Context Protocol for current affairs)
```

---

## 3. DIRECTORY STRUCTURE

```
study-buddy/
├── backend/                    # FastAPI application
│   ├── app/
│   │   ├── core/              # Config, database, security, env
│   │   ├── gemini_core/       # Gemini client wrapper
│   │   ├── models/            # SQLAlchemy models (User)
│   │   ├── prompts/           # Shared prompt templates
│   │   ├── routes/            # API endpoints
│   │   ├── schemas/           # Pydantic schemas
│   │   └── utils/             # Core utilities
│   ├── data/                  # SQLite databases, chunks
│   ├── mains_prompt.py        # Mains answer prompt assembly
│   └── mcp_current_affairs_server.py  # News fetcher
│
├── web/                       # Next.js frontend
│   └── src/
│       ├── app/               # Pages (App Router)
│       ├── components/        # UI components
│       ├── context/           # Auth context
│       └── lib/               # Utilities
│
├── map-service/               # D3.js map generation
│   ├── generate_map.js        # SVG generation logic
│   ├── server.js              # Express server
│   └── utils/                 # Projections, caching
│
└── frontend/                  # Legacy Streamlit app (deprecated)
```

---

## 4. BACKEND API ENDPOINTS

### Authentication (`/auth`)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/auth/signup` | POST | Create new user account |
| `/auth/login` | POST | Login and get JWT token |
| `/auth/me` | GET | Get current user info (protected) |

### Content Upload (`/upload`, `/upload-content-store`)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/upload/` | POST | Upload PDF → chunk → embed → store in Pinecone |
| `/upload-content-store/` | POST | Upload PDF → chunk → store full text in SQLite |

### Query & Chat (`/query`)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/query/` | POST | RAG query with streaming response |
| `/query/stream` | POST | Streaming Q&A with context |

### Mock Test (`/mock-test`)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/mock-test/generate` | POST | Generate Prelims MCQs with PYQ-style patterns |
| `/mock-test/feedback` | POST | Submit quality feedback on questions |

### Mains Answer (`/mains-answer`)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/mains-answer/generate` | POST | Generate structured Mains answer (IBC format) |

### Evaluate Answer (`/evaluate-answer`)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/evaluate-answer/` | POST | Upload handwritten answer → OCR → evaluate → improve |

### Training Data (`/training-data`)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/training-data/extract-answer` | POST | OCR extract from answer sheets |
| `/training-data/submit` | POST | Submit training example for feedback improvement |

---

## 5. CORE ARCHITECTURE FLOWS

### 5.1 Document Upload & Processing Flow
```
PDF Upload
    ↓
HierarchicalChunker
    → Font size analysis for structure detection
    → Chapter/Section extraction
    → Word-based chunking (500 words, 15% overlap)
    ↓
MetadataEnricher (LLM)
    → Extract: major_domain, sub_domain, micro_topic
    → Classify: source_type (static/current_affairs)
    ↓
Embedder (OpenAI text-embedding-3-small)
    → Generate 1536-dim embeddings
    ↓
Dual Storage:
    ├── Pinecone: chunk_id, embedding, content_preview, metadata
    └── SQLite ContentStore: chunk_id, full_content, metadata
```

### 5.2 Mains Answer Generation Flow
```
Question Input
    ↓
QuestionParser (Gemini)
    → Extract: main_topic, sub_topics, search_query
    → Remove filler words, optimize for embedding search
    ↓
ContextRetriever
    → Query Pinecone (MMR search, k=6)
    → Fetch full content from SQLite ContentStore
    → Deduplicate overlapping chunks
    ↓
CurrentAffairsFetcher (MCP Server)
    → Parse keywords from question
    → Fetch from GNews/NewsAPI/TheNewsAPI
    → Categorize: India initiatives, global issues, etc.
    → Format as concise bullet points
    ↓
PromptAssembler (mains_prompt.py)
    → System prompt: IBC format, directive interpretation
    → User prompt: question + context + current affairs
    ↓
GeminiClient (gemini-2.5-pro)
    → Generate structured answer
    → Include Mermaid diagrams
    ↓
MapProxy (if map-json blocks present)
    → Parse map configurations
    → Call map-service for SVG generation
    → Embed base64 images in response
```

### 5.3 Answer Evaluation Flow
```
Handwritten Answer (PDF/Image)
    ↓
GeminiClient OCR
    → Extract question (if not provided)
    → Extract answer text
    ↓
QuestionParser
    → Identify directive (discuss, evaluate, etc.)
    → Extract search terms
    ↓
ContextRetriever + CurrentAffairsFetcher
    → Get relevant reference material
    → Get current affairs bullets
    ↓
EvaluationPrompt
    → Compare student answer vs reference
    → Apply directive interpretation rules
    ↓
GeminiClient
    → Generate improved answer
    → Provide detailed feedback
    → Score on multiple dimensions
```

### 5.4 Mock Test Generation Flow
```
Configuration (topics, difficulty, num_questions)
    ↓
StyleLearning
    → 40% PYQ chunks from database
    → 40% Patterns from JSON
    → 20% High-quality feedback examples
    ↓
MemoryManager
    → Filter recently asked questions
    → Avoid topic repetition
    ↓
ContextRetrieval
    → Query Pinecone for topic-relevant chunks
    → Apply source diversity (enforce different files)
    ↓
UPSC Prompt Assembly
    → Style examples + context + constraints
    ↓
OpenAI GPT-4o
    → Generate MCQs with 4 options
    → Include detailed explanations
    ↓
Recency Recording
    → Store generated questions in memory
    → Prevent future repetition
```

---

## 6. KEY UTILITIES DEEP DIVE

### 6.1 HierarchicalChunker (`utils/hierarchical_chunker.py`)
**Purpose**: Intelligent document chunking that respects structure

**Key Features**:
- PDF font size analysis for chapter/section detection
- Word-based chunking (configurable: 500 words default)
- 15% overlap to maintain context continuity
- Hierarchy-aware metadata (chapter, section)

**Configuration** (in `config.py`):
```python
CHUNK_SIZE_WORDS: int = 500
CHUNK_OVERLAP_PERCENT: float = 0.15
MIN_WORDS_PER_CHUNK: int = 20
```

### 6.2 ContentStore (`utils/content_store.py`)
**Purpose**: SQLite storage for full chunk content (complements Pinecone)

**Why Needed**: Pinecone metadata has size limits; storing full text locally enables:
- RetrievalQA chains with complete context
- No truncation of long passages
- Fast local lookup by chunk_id

**Schema**:
```sql
chunks(
    chunk_id, filename, chapter, section,
    full_content, content_length, content_preview,
    major_domain, sub_domain, micro_topic,
    source_type, source_subtype
)
```

### 6.3 PineconeHandler (`utils/pinecone_handler.py`)
**Purpose**: Vector store operations with LangChain integration

**Key Features**:
- Dual embedding support (OpenAI primary, SentenceTransformers fallback)
- ContentStoreRetriever: Enriches Pinecone results with SQLite full content
- Mode-specific retrievers (mains, concept, mock_test)
- MMR (Maximal Marginal Relevance) for diversity

**Retrieval Modes**:
| Mode | search_type | k | Use Case |
|------|-------------|---|----------|
| mains | mmr | 6 | Mains answer generation |
| concept | similarity | 6 | Concept explanations |
| mock_test | mmr | 10 | Question generation (diverse sources) |

### 6.4 QuestionParser (`utils/question_parser.py`)
**Purpose**: LLM-powered extraction of search-friendly terms from verbose UPSC questions

**Input**: "Discuss the causes and impacts of increasing forest fires in India"
**Output**:
```json
{
    "main_topic": "forest fires India",
    "sub_topics": ["causes", "impacts", "mitigation measures"],
    "search_query": "forest fires India causes impacts mitigation"
}
```

**Why Needed**: Direct embedding of UPSC questions performs poorly because:
- Questions contain filler words (discuss, critically, elaborate)
- Verbose phrasing doesn't match document language
- Key concepts buried in question structure

### 6.5 CurrentAffairsFetcher (`utils/current_affairs_fetcher.py`)
**Purpose**: Fetch and format recent news for answer enhancement

**Data Sources**:
- GNews API (primary)
- NewsAPI (fallback)
- TheNewsAPI (fallback)

**Categorization**:
- India Initiatives
- Global Initiatives
- India Issues
- Global Issues
- Recent Developments

**Output Format**: 5 concise bullet points (40-50 words each)

### 6.6 MemoryManager (`utils/memory_manager.py`)
**Purpose**: Track generated questions to prevent repetition

**Tables**:
- `recent_questions`: Hash, text, topic, subtopic, timestamp
- `question_feedback`: Quality ratings for style learning

**Features**:
- 7-day recency window
- Topic-level filtering
- Quality-based example selection for few-shot prompting

---

## 7. PROMPT ENGINEERING

### 7.1 Mains Answer System Prompt
Located in `app/prompts/shared_mains_prompts.py`

**Key Elements**:
1. **IBC Format**: Introduction → Body (with sub-headings) → Conclusion
2. **Directive Interpretation**:
   - Discuss = broad overview → positives/negatives/causes/consequences
   - Critically examine = strengths + weaknesses + implications
   - Evaluate = assess worthiness → positives/negatives → verdict
   - Substantiate = assert then support with evidence
3. **Cognitive Framework**:
   - Single concept focus per answer
   - Named indices/reports/data for each point
   - Mandatory human angle for physical geography
   - At least one Mermaid diagram

### 7.2 Mock Test Prompts
Located in `utils/mock_test_prompting.py`

**Style Learning**:
- PYQ pattern recognition (statement-based, assertion-reason, match-the-following)
- Few-shot examples from high-quality feedback
- Topic-specific knowledge integration

---

## 8. MAP GENERATION SERVICE

### 8.1 Architecture
```
LLM Output (with ```map-json blocks)
    ↓
MapProxy (Python)
    → Parse JSON configuration
    → Call Node.js service
    ↓
Map Service (Node.js/D3.js)
    → Load TopoJSON data
    → Apply projection (Mercator, Albers, etc.)
    → Render choropleth/markers/rivers
    → Return base64 SVG
    ↓
MapProxy
    → Embed as markdown image
```

### 8.2 Supported Map Types
- **choropleth**: Color-coded regions by value
- **markers**: Point markers with labels
- **rivers**: Major river paths
- **arrows**: Flow/migration indicators
- **combined**: Multiple types together

### 8.3 Example Configuration
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

---

## 9. FRONTEND ARCHITECTURE

### 9.1 Pages (App Router)
| Route | Purpose |
|-------|---------|
| `/` | Dashboard with quick actions |
| `/upload` | PDF upload interface |
| `/evaluate` | Handwritten answer evaluation |
| `/chat` | Q&A chat interface |
| `/mock-test` | Prelims mock test generation |
| `/mains-answer` | Mains answer writer |
| `/training-data` | Training data collection |
| `/login`, `/signup` | Authentication pages |

### 9.2 Key Components
- **Sidebar**: Navigation with theme-aware styling
- **Header**: Theme toggle + Auth modal trigger
- **AuthModal**: Login/Signup modal with state switching
- **Dialog**: Radix UI-based modal with theme support

### 9.3 Theme System
**Light Theme (Oatmilk)**:
```css
--bg: 40 33% 98%          /* Warm off-white */
--text: 24 16% 32%         /* Soft brown */
--accent: 18 70% 55%       /* Coral/Copper */
--sidebar-bg: 40 30% 96%   /* Slightly darker oat */
```

**Dark Theme (Charcoal + Gold)**:
```css
--bg: 220 15% 10%          /* Deep charcoal */
--text: 40 20% 90%         /* Warm off-white */
--accent: 35 75% 55%       /* Gold/Amber */
--sidebar-bg: 220 12% 12%  /* Darker charcoal */
```

---

## 10. AUTHENTICATION SYSTEM

### 10.1 Flow
```
Signup → Hash password (bcrypt) → Store in SQLite
Login → Verify password → Generate JWT (30min expiry)
Protected Routes → Verify JWT → Extract user email
```

### 10.2 Security Notes
- JWT secret should be moved to `.env` (currently uses fallback)
- Token expiry: 30 minutes
- Password hashing: bcrypt

---

## 11. DATABASE SCHEMAS

### 11.1 Users (`users` table)
```sql
id INTEGER PRIMARY KEY
email TEXT UNIQUE
full_name TEXT
hashed_password TEXT
is_active BOOLEAN
```

### 11.2 Content Store (`chunks` table)
```sql
chunk_id TEXT
filename TEXT
chapter TEXT
section TEXT
full_content TEXT
content_preview TEXT
major_domain TEXT
sub_domain TEXT
micro_topic TEXT
source_type TEXT
```

### 11.3 Memory (`recent_questions`, `question_feedback`)
```sql
-- Recent questions
question_hash TEXT UNIQUE
question_text TEXT
topic TEXT, subtopic TEXT
difficulty TEXT, timestamp TEXT

-- Feedback
question_hash TEXT UNIQUE
quality TEXT  -- 'good', 'bad', 'excellent'
reason TEXT
```

---

## 12. ENVIRONMENT VARIABLES

```env
# LLM APIs
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=...

# Vector Store
PINECONE_API_KEY=...
PINECONE_INDEX_NAME=study-buddy

# News APIs (for current affairs)
GNEWS_API_KEY=...
NEWS_API_KEY=...
THENEWSAPI_KEY=...

# Email (optional, for notifications)
EMAIL_ENABLED=false
GMAIL_APP_PASSWORD=...

# JWT (should be set in production)
JWT_SECRET_KEY=...
```

---

## 13. CURRENT LIMITATIONS & KNOWN ISSUES

1. **JWT Secret**: Currently falls back to OpenAI key if not set
2. **Node.js Version**: Frontend requires Node.js >= 20.9.0 (Next.js 16)
3. **Map Service**: Must be running on port 3001 for maps to work
4. **ChromaDB Fallback**: Less tested than Pinecone path
5. **Training Data Router**: Registered twice in main.py (duplicate)

---

## 14. RECOMMENDED IMPROVEMENTS

### 14.1 High Priority
1. **Proper JWT Secret**: Add `JWT_SECRET_KEY` to `.env` and use it
2. **Rate Limiting**: Add rate limits to prevent API abuse
3. **Error Handling**: Centralized error handling middleware
4. **Logging**: Structured logging with log levels
5. **Testing**: Unit tests for core utilities

### 14.2 Medium Priority
1. **Caching**: Redis for session management and API response caching
2. **User Progress Tracking**: Store quiz scores, answer history
3. **Spaced Repetition**: Implement SRS for topic review
4. **Multi-Subject Support**: Extend beyond Geography
5. **PDF Annotation**: Highlight source chunks in original PDFs

### 14.3 Future Features
1. **Study Plans**: AI-generated personalized study schedules
2. **Peer Comparison**: Anonymous benchmarking
3. **Voice Input**: Speech-to-text for answer dictation
4. **Mobile App**: React Native version
5. **Offline Mode**: Download content for offline study

---

## 15. DEVELOPMENT WORKFLOW

### Running the System
```bash
# Backend (port 8001)
cd backend
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload

# Frontend (port 3000)
cd web
npm run dev

# Map Service (port 3001)
cd map-service
npm start
```

### Database Locations
```
backend/data/chroma/
├── content_store.db    # SQLite content store
├── memory.db          # Recency & feedback memory
└── sql_app.db         # User authentication
```

---

## 16. QUICK REFERENCE: KEY FILES

| Purpose | File |
|---------|------|
| Main FastAPI app | `backend/app/main.py` |
| Configuration | `backend/app/core/config.py` |
| Mains answer generation | `backend/app/routes/mains_answer.py` |
| Answer evaluation | `backend/app/routes/evaluate_answer.py` |
| Mock test generation | `backend/app/routes/mock_test.py` |
| Vector store handler | `backend/app/utils/pinecone_handler.py` |
| Content store | `backend/app/utils/content_store.py` |
| Document chunker | `backend/app/utils/hierarchical_chunker.py` |
| Question parser | `backend/app/utils/question_parser.py` |
| Current affairs | `backend/mcp_current_affairs_server.py` |
| Gemini client | `backend/app/gemini_core/gemini_client.py` |
| Mains prompts | `backend/mains_prompt.py` |
| Frontend layout | `web/src/app/layout.tsx` |
| Auth context | `web/src/context/AuthContext.tsx` |
| Theme CSS | `web/src/app/globals.css` |
| Map generation | `map-service/generate_map.js` |

---

*Document Version: 1.0*  
*Last Updated: December 2024*  
*Generated for: Study Buddy AI v1.0*
