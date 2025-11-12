# Memory & Self-Evaluator System Implementation

## Overview

This document describes the implementation of the **Memory and Self-Evaluator** system for the Study Buddy question generation loop. The system implements a complete feedback loop that learns from user ratings and avoids repeating recently generated questions.

**Design Philosophy:** Simple, lightweight, and effective. Uses a single SQLite database with text-based similarity matching (no heavy embeddings required).

## Architecture

```
[Question Generation Loop]

       ↓

(1) Retrieval → apply recency filter (last 7 days)

       ↓

(2) Prompt → include good question styles (few-shot from feedback DB)

       ↓

(3) Generation → produce new questions

       ↓

(4) Evaluation → user rating → feedback DB

       ↓

(5) Memory Update → store embeddings + topics → recency DB
```

## Components

### 1. Memory Database (`backend/app/utils/memory_manager.py`)

**Purpose:** Single SQLite database storing both recency and feedback data.

**Schema:**

**Recent Questions Table:**
```sql
CREATE TABLE recent_questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_hash TEXT UNIQUE,
    question_text TEXT,
    topic TEXT,
    subtopic TEXT,
    difficulty TEXT,
    timestamp TEXT
);
```

**Question Feedback Table:**
```sql
CREATE TABLE question_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_hash TEXT UNIQUE,
    question_text TEXT,
    topic TEXT,
    difficulty TEXT,
    quality TEXT,  -- 'high', 'medium', or 'low'
    reason TEXT,
    timestamp TEXT
);
```

**Key Features:**
- **Simple & Lightweight:** Single database file, no heavy dependencies
- **Text-Based Similarity:** Uses `difflib.SequenceMatcher` (no embeddings needed)
- **Hash-Based Deduplication:** SHA256 hashing for stable duplicate detection
- **Quality Ratings:** Simple 'high', 'medium', 'low' quality system
- **Topic Tracking:** Stores topic and subtopic for filtering

### 2. Core Functions (`backend/app/utils/memory_manager.py`)

**Recency Functions:**
- `record_recent_question()` - Save generated question to recency memory
- `get_recent_questions()` - Fetch recent questions (last N days)
- `filter_recency()` - Filter chunks similar to recent questions

**Feedback Functions:**
- `record_feedback()` - Store user feedback (quality rating)
- `get_high_quality_examples()` - Get high-quality examples for few-shot learning

### 4. Integration Points

#### A. Retrieval with Recency Filter (`backend/app/routes/mock_test.py`)

**Location:** `hybrid_retrieve_for_mock_test()` function

**Implementation:**
```python
# Step 1: Retrieve concept chunks
concept_chunks = pinecone_handler.query_documents(...)

# Step 1 (continued): Apply recency filter
recent_questions = get_recent_questions(days=7)
concept_chunks = filter_recency(concept_chunks, recent_questions)
```

**How it works:**
1. Retrieves chunks from Pinecone
2. Gets recent questions from last 7 days
3. Uses text similarity (SequenceMatcher) to compare chunk content with recent questions
4. Filters out chunks with similarity > 0.82 (first 250 chars)
5. Returns filtered chunks for question generation

**Advantages:**
- No embeddings needed (faster, simpler)
- Works with any text content
- Lightweight and efficient

#### B. Few-Shot Examples from Feedback DB (`backend/app/routes/mock_test.py`)

**Location:** `generate_fewshot_examples()` function

**Implementation:**
```python
# Get high-quality examples from feedback DB
filter_topic = topics[0] if topics else None
feedback_examples = get_high_quality_examples(
    limit=3,  # Get 3 examples
    topic=filter_topic,
    difficulty=difficulty
)

# Add to few-shot examples
for fb_ex in feedback_examples:
    all_examples.append({
        "question": fb_ex['text'],
        "topic": fb_ex['topic'],
        "reason": fb_ex.get('reason', '')
    })
```

**How it works:**
1. Retrieves high-quality questions ('high' quality) from feedback DB
2. Filters by topic and difficulty if specified
3. Adds to few-shot examples alongside PYQ patterns
4. Includes reason/comment if available for context
5. LLM learns from both historical PYQs and user-approved questions

#### C. Memory Update After Generation (`backend/app/routes/mock_test.py`)

**Location:** `generate_question_paper()` function

**Implementation:**
```python
# After generating each question
topic = request.topics[0] if request.topics else "Geography"
subtopic = request.topics[1] if len(request.topics) > 1 else topic

record_recent_question(
    question_text=question_text,
    topic=topic,
    subtopic=subtopic,
    difficulty=request.difficulty
)
```

**How it works:**
1. Extracts topic and subtopic from request
2. Stores question text, topic, subtopic, and difficulty
3. Generates hash for duplicate detection
4. Stores in recency DB with timestamp
5. Future retrievals will filter out similar questions using text similarity

#### D. Feedback API Endpoint (`backend/app/routes/feedback.py`)

**Endpoint:** `POST /feedback/`

**Request:**
```json
{
    "question_text": "What is the primary focus of Geography?",
    "topic": "Geography",
    "difficulty": "medium",
    "quality": "high",
    "reason": "Balanced interlinking and strong UPSC-style trap"
}
```

**Response:**
```json
{
    "success": true,
    "message": "Feedback stored successfully. Quality: high"
}
```

**How it works:**
1. User submits quality rating ('high', 'medium', or 'low')
2. Optional reason/comment for context
3. Feedback stored in memory DB
4. High-quality questions become few-shot examples
5. System learns from user preferences over time

## Database File

- **Memory DB:** `backend/data/chroma/memory.db`

Single SQLite database storing both recency and feedback data, located alongside ChromaDB data.

## Usage Flow

### 1. Generate Questions

```bash
POST /mock-test/generate
{
    "num_questions": 5,
    "topics": ["Climatology", "Monsoon"],
    "difficulty": "medium"
}
```

**What happens:**
1. Retrieval applies recency filter (avoids last 7 days)
2. Prompt includes top-rated examples from feedback DB
3. Questions generated with unique IDs
4. Each question stored in recency DB

### 2. User Rates Questions

```bash
POST /feedback/
{
    "question_text": "...",
    "topic": "Climatology",
    "difficulty": "medium",
    "quality": "high",
    "reason": "Great question!"
}
```

**What happens:**
1. Feedback stored in memory DB
2. Question becomes candidate for few-shot learning
3. Future generations will include this question if quality = 'high'

### 3. Next Generation

**What happens:**
1. Retrieval filters out chunks similar to recent questions (text similarity > 0.82)
2. Prompt includes the high-quality question as few-shot example (with reason if available)
3. System generates new questions learning from user feedback

## Recommendations

### 1. **Feedback Collection Strategy**

**Current:** User manually submits ratings via API

**Recommendations:**
- **Frontend Integration:** Add rating UI (1-5 stars) after each question
- **Automatic Collection:** Track user behavior (time spent, attempts, correctness)
- **Batch Feedback:** Allow users to rate multiple questions at once
- **Incentivize:** Show users how their feedback improves the system

### 2. **Recency Filter Tuning**

**Current:** 7 days, 0.82 similarity threshold (SequenceMatcher)

**Recommendations:**
- **Adaptive Window:** Adjust days based on question volume (more questions = shorter window)
- **Topic-Aware:** Different recency windows per topic (e.g., 3 days for popular topics)
- **Threshold Tuning:** Adjust SequenceMatcher threshold (0.80-0.85 range)
- **Text Length:** Compare longer text snippets (500 chars instead of 250) for better accuracy
- **User Preferences:** Allow users to set recency preferences

### 3. **Few-Shot Example Selection**

**Current:** Top 3 examples, quality='high', filtered by topics/difficulty

**Recommendations:**
- **Diversity:** Ensure examples cover different question patterns
- **Recency Balance:** Mix recent high-quality questions with historical PYQs
- **Pattern Matching:** Match examples to requested question types
- **Reason Integration:** Use reason/comment field to provide context to LLM
- **Quality Distribution:** Consider including some 'medium' quality examples for variety

### 4. **Memory Management**

**Current:** Stores all questions indefinitely

**Recommendations:**
- **Cleanup Policy:** Archive old questions (>30 days) to separate table
- **Compression:** Store only top N questions per topic/difficulty combination
- **Analytics:** Track which topics generate most questions
- **Export:** Allow users to export their feedback history

### 5. **Self-Evaluation Enhancement**

**Current:** User provides explicit ratings

**Recommendations:**
- **Implicit Feedback:** Track user behavior (skip rate, time spent, retry attempts)
- **Question Difficulty Calibration:** Compare user ratings with actual difficulty
- **A/B Testing:** Test different question styles and measure user engagement
- **Adaptive Learning:** Adjust question generation based on user performance patterns

### 6. **Performance Optimization**

**Current:** Text-based similarity using SequenceMatcher (lightweight)

**Recommendations:**
- **Caching:** Cache recent questions list to avoid repeated DB queries
- **Batch Processing:** Process multiple chunks in parallel
- **Indexing:** Already has indexes on timestamp, quality, topic for fast queries
- **Async Storage:** Store questions asynchronously to avoid blocking generation
- **Hash Lookup:** Use question_hash for faster duplicate detection

### 7. **Monitoring & Analytics**

**Recommendations:**
- **Dashboard:** Show feedback statistics (average rating, top topics, trends)
- **Question Quality Metrics:** Track question diversity, difficulty distribution
- **User Engagement:** Monitor how feedback affects question generation quality
- **Alerts:** Notify when feedback quality drops or recency filter is too aggressive

## Testing

### Test Feedback Storage

```python
from backend.app.utils.memory_manager import record_feedback

record_feedback(
    question_text="Test question?",
    topic="Test",
    difficulty="medium",
    quality="high",
    reason="Great test question"
)
```

### Test Recency Filter

```python
from backend.app.utils.memory_manager import get_recent_questions, filter_recency

recent_questions = get_recent_questions(days=7)
chunks = [{"content": "Some content", "metadata": {}}]
filtered = filter_recency(chunks, recent_questions)
```

### Test High-Quality Examples

```python
from backend.app.utils.memory_manager import get_high_quality_examples

examples = get_high_quality_examples(limit=5, topic="Climatology", difficulty="medium")
```

## Future Enhancements

1. **Multi-User Support:** Track feedback per user, personalized question generation
2. **Question Clustering:** Group similar questions, avoid generating duplicates
3. **Adaptive Difficulty:** Adjust difficulty based on user performance
4. **Question Templates:** Learn question patterns from highly-rated examples
5. **Collaborative Filtering:** Recommend questions based on similar users' preferences
6. **Real-Time Learning:** Update few-shot examples immediately after high ratings

## Conclusion

The Memory & Self-Evaluator system creates a complete feedback loop that:
- ✅ Learns from user feedback (few-shot examples)
- ✅ Avoids repetition (recency filtering with text similarity)
- ✅ Improves over time (memory accumulation)
- ✅ Adapts to user preferences (topic/difficulty filtering)
- ✅ Simple & lightweight (single DB, no heavy dependencies)

**Key Advantages:**
- **Simplicity:** Single database, straightforward API
- **Performance:** Text-based similarity (no embeddings needed)
- **Effectiveness:** Proven approach with SequenceMatcher
- **Maintainability:** Easy to understand and modify

The system is production-ready and can be enhanced with the recommendations above.

