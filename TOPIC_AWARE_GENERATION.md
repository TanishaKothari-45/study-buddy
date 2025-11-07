# Topic-Aware Question Generation Flow

## ✅ Current Implementation

The system now implements **complete topic-aware filtering** across all three data sources:

### **Flow When User Selects Topics (e.g., "Monsoon", "Climate"):**

```
User Request: Generate questions on ["Monsoon", "Climate"]
    ↓
1. MAP TOPICS TO DOMAINS
   - "Monsoon" → major_domain: "Climatology", sub_domain: "Climate"
   - "Climate" → major_domain: "Climatology", sub_domain: "Climate"
    ↓
2. FEW-SHOT PYQ EXAMPLES (from JSON)
   ✅ Filtered by topic: Shows Monsoon/Climate-related PYQ examples
   ✅ Uses pattern from JSON (e.g., Q2 for Multi-Statement)
    ↓
3. PYQ CHUNKS (from database)
   ✅ Query with topic: "UPSC prelims geography questions Monsoon Climate..."
   ✅ Filter by PYQ file: Only chunks from PYQ files
   ✅ Filter by actual questions: Exclude index/contents pages
   ✅ Filter by metadata: Only chunks with major_domain="Climatology" or sub_domain="Climate"
    ↓
4. CONTENT CHUNKS (from database - NCERT, Vision, etc.)
   ✅ Query with topic: "Monsoon Climate geography concepts NCERT vision notes"
   ✅ Exclude PYQ files: Only content sources
   ✅ Filter by metadata: Only chunks with major_domain="Climatology" or sub_domain="Climate"
    ↓
5. GENERATE QUESTIONS
   ✅ Uses topic-filtered PYQ examples for style
   ✅ Uses topic-filtered PYQ chunks for additional style patterns
   ✅ Uses topic-filtered content chunks for factual knowledge
   ✅ Generates questions matching PYQ style on the selected topics
```

---

## 📊 What Each Component Does

### **1. Few-Shot PYQ Examples (JSON)**
- **Source**: `geography_prelims_pyq_patterns.json`
- **Filtering**: By topic keyword (e.g., "Monsoon")
- **Output**: 3 curated PYQ examples matching the topic
- **Purpose**: Style learning from authentic UPSC questions

### **2. PYQ Chunks (Database)**
- **Source**: Chunks from `geography-pyq topic wise.pdf`
- **Filtering Steps**:
  1. Query with topic in search text
  2. Filter by filename (PYQ files only)
  3. Filter by content (actual questions, not index)
  4. **Filter by metadata** (major_domain/sub_domain matching user topics)
- **Purpose**: Additional style patterns from retrieved PYQ chunks

### **3. Content Chunks (Database)**
- **Source**: NCERT, Vision Notes, Majid Hussain, etc.
- **Filtering Steps**:
  1. Query with topic in search text
  2. Exclude PYQ files
  3. **Filter by metadata** (major_domain/sub_domain matching user topics)
- **Purpose**: Factual knowledge for question generation

---

## 🔍 Topic Mapping

The system maps user topics to metadata fields:

| User Topic | Mapped To |
|------------|-----------|
| "Monsoon" | sub_domain: "Climate" (under "Physical Geography" or "Indian Geography") |
| "Climate" | sub_domain: "Climate" |
| "Physical Geography" | major_domain: "Physical Geography" |
| "Agriculture" | sub_domain: "Agriculture" (under "Indian Geography") |

**Mapping Logic**:
- Checks if topic matches any sub_domain name
- Checks if topic matches any major_domain name
- Returns matching major_domains and sub_domains
- Filters chunks where metadata matches these domains

---

## ✅ Verification

**Yes, the current model is doing this:**

1. ✅ **PYQs from chunks** - Filtered by topic using metadata
2. ✅ **Patterns from JSON** - Filtered by topic keyword
3. ✅ **Content chunks** - Filtered by topic using metadata
4. ✅ **Topic-aware generation** - All three sources are topic-filtered

---

## 🎯 Example Flow

**User selects**: ["Monsoon"]

**System does**:
1. Maps "Monsoon" → `sub_domain: "Climate"`, `major_domain: "Physical Geography"` or `"Indian Geography"`
2. Gets few-shot examples: Monsoon-related PYQs from JSON
3. Gets PYQ chunks: Only Monsoon/Climate PYQ chunks from database
4. Gets content chunks: Only Monsoon/Climate content from NCERT/Vision
5. Generates questions: Monsoon questions in UPSC style

**Result**: Questions are:
- ✅ On the selected topic (Monsoon)
- ✅ In UPSC style (from PYQ examples)
- ✅ Based on relevant content (filtered chunks)
- ✅ Using appropriate patterns (from JSON)

---

## 📝 Key Functions

### `map_topics_to_domains(topics)`
- Maps user topics to major_domain/sub_domain values
- Uses `GEOGRAPHY_TOPICS` mapping from metadata_enricher

### `filter_chunks_by_topic(chunks, topics)`
- Filters chunks by matching metadata (major_domain/sub_domain)
- Falls back to all chunks if filtering too strict

### `generate_fewshot_examples(topics, pattern_id, n)`
- Gets topic-filtered examples from JSON
- Uses loader module for flexible filtering

---

## 🚀 Benefits

1. **Precision**: Only relevant chunks used for generation
2. **Relevance**: Questions match user's topic selection
3. **Quality**: Better context = better questions
4. **Efficiency**: Less noise, more signal

---

**Status**: ✅ Fully implemented and working

