# ChromaDB Chunk Analysis & Mock Test Foundation

## ✅ Changes Made

### 1. **Collection Standardization**
- ✅ Updated default collection in `config.py` to `geography_docs_enriched`
- ✅ Fixed `mock_test.py` route to use `geography_docs_enriched` collection
- ✅ All routes now consistently use the enriched collection:
  - `upload.py` → `geography_docs_enriched`
  - `query.py` → `geography_docs_enriched`
  - `mock_test.py` → `geography_docs_enriched` (FIXED)
  - `mains_answer.py` → `geography_docs_enriched`
  - `evaluate_answer.py` → `geography_docs_enriched`

### 2. **Chunk Inspection Tool**
- ✅ Created `inspect_chunks.py` script to analyze stored chunks
- ✅ Shows complete metadata structure
- ✅ Provides domain distribution analysis

---

## 📊 Current Database State

### **Total Chunks: 703**

### **Metadata Structure** (100% coverage on all chunks)
Each chunk contains:
- `subject`: "Geography"
- `chapter`: Chapter name from PDF structure
- `section`: Section name from PDF structure
- `chunk_id`: Unique identifier (e.g., "1_1_1")
- `filename`: Source PDF filename
- `major_domain`: One of 5 categories
- `sub_domain`: Specific topic within major domain
- `difficulty`: Basic / Moderate / Advanced
- `summary`: 40-word summary of chunk content

### **Domain Distribution**

#### Major Domains:
- **Indian Geography**: 247 chunks (35.1%) ⭐
- **Physical Geography**: 211 chunks (30.0%)
- **Human Geography**: 178 chunks (25.3%)
- **World Geography**: 53 chunks (7.5%)
- **Map-Based Questions**: 14 chunks (2.0%)

#### Top Sub-Domains:
1. **Natural Disasters**: 151 chunks (21.5%)
2. **Human Geography**: 96 chunks (13.7%)
3. **Climate**: 57 chunks (8.1%)
4. **Economic Geography**: 47 chunks (6.7%)
5. **Agriculture**: 42 chunks (6.0%)
6. **Major Physical Features**: 40 chunks (5.7%)
7. **Soils**: 17 chunks (2.4%)
8. **Drainage System**: 14 chunks (2.0%)
9. **Mineral Resources**: 14 chunks (2.0%)
10. **Continents and Countries**: 8 chunks (1.1%)

#### Difficulty Levels:
- **Moderate**: 659 chunks (93.7%) ⚠️
- **Advanced**: 27 chunks (3.8%)
- **Basic**: 17 chunks (2.4%)

---

## 🔍 How Chunks Are Stored

### Storage Process:
1. **PDF Upload** → `upload.py` route
2. **Text Extraction** → PyMuPDF extracts text with visual structure
3. **Hierarchical Chunking** → `hierarchical_chunker.py`:
   - Extracts index/table of contents
   - Uses font size to detect chapter/section hierarchy
   - Creates chunks preserving structure
   - Initial metadata: `subject`, `chapter`, `section`, `chunk_id`, `filename`
4. **Metadata Enrichment** → `metadata_enricher.py`:
   - Rule-based classification (keywords)
   - LLM fallback for uncertain chunks
   - Adds: `major_domain`, `sub_domain`, `difficulty`, `summary`
5. **Storage** → ChromaDB with embeddings:
   - Content: Full chunk text
   - Metadata: All 9 fields
   - Embeddings: `text-embedding-3-small` (1536 dimensions)

### Example Chunk Structure:
```json
{
  "id": "doc_0_6952650162621739449",
  "content": "Nature and Scope You have already studied...",
  "metadata": {
    "subject": "Geography",
    "chapter": "Human Geography",
    "section": "General",
    "chunk_id": "1_1_1",
    "filename": "NCERT-Class-12-Geography-Part-1.pdf",
    "major_domain": "Physical Geography",
    "sub_domain": "Natural Disasters",
    "difficulty": "Moderate",
    "summary": "Nature and Scope You have already studied..."
  }
}
```

---

## 🎯 Recommendations for Improving Mock Prelims Questions

### **Current Issues Identified:**

1. **Difficulty Imbalance** ⚠️
   - 93.7% chunks are "Moderate" difficulty
   - Only 3.8% Advanced, 2.4% Basic
   - **Impact**: Questions may lack variety in difficulty

2. **Domain Coverage** 📊
   - Good coverage: Indian Geography (35%), Physical (30%), Human (25%)
   - Weak coverage: World Geography (7.5%), Map-Based (2%)
   - **Impact**: Questions may be skewed toward certain domains

3. **Sub-Domain Concentration** 🎯
   - Natural Disasters dominates (21.5%)
   - Some important topics underrepresented
   - **Impact**: Question diversity may be limited

### **Improvement Strategies:**

#### 1. **Enhanced Query Strategy for Mock Tests**
```python
# Current: Simple query with k=10
chunks = chroma_handler.query_documents(query, k=10)

# Improved: Use metadata filtering
# - Filter by difficulty distribution (30% Basic, 50% Moderate, 20% Advanced)
# - Ensure domain diversity (at least 1 chunk from each major domain)
# - Use sub_domain to avoid topic concentration
```

#### 2. **Better Prompt Engineering**
- Use `major_domain` and `sub_domain` in prompts to guide question generation
- Reference `difficulty` to match question complexity
- Use `summary` for quick context understanding

#### 3. **Metadata-Based Question Generation**
- Generate questions that test specific domains
- Use difficulty metadata to create balanced question sets
- Leverage chapter/section metadata for topic-specific questions

#### 4. **Query Enhancement**
Instead of:
```python
query = " ".join(test_request.topics) if test_request.topics else "important geography topics for UPSC"
```

Use:
```python
# Build query with domain context
if test_request.topics:
    query = f"{' '.join(test_request.topics)} UPSC prelims geography"
else:
    # Query with balanced domain representation
    query = "UPSC prelims geography questions covering Indian Geography, Physical Geography, Human Geography"
```

#### 5. **Chunk Selection Strategy**
- **Diversity**: Ensure chunks from different major_domains
- **Difficulty Mix**: Select chunks with varied difficulty levels
- **Topic Balance**: Avoid over-representation of single sub_domains
- **Quality**: Prefer chunks with rich metadata

---

## 🛠️ Next Steps

1. **Update Mock Test Generation**:
   - Implement metadata-aware chunk selection
   - Add difficulty-based filtering
   - Ensure domain diversity in question generation

2. **Improve Metadata Quality**:
   - Review and refine difficulty classification
   - Expand sub_domain categories
   - Add more granular topic tags

3. **Enhanced Prompting**:
   - Use metadata fields in GPT prompts
   - Guide question generation with domain/difficulty info
   - Create domain-specific question templates

4. **Testing**:
   - Generate sample mock tests
   - Analyze question quality and diversity
   - Iterate based on results

---

## 📝 Usage

### Inspect Chunks:
```bash
python inspect_chunks.py --collection geography_docs_enriched --limit 10
```

### Export Sample:
The script automatically exports sample chunks to `chunk_inspection_sample.json` for detailed analysis.

---

**Last Updated**: Based on 703 chunks in `geography_docs_enriched` collection

