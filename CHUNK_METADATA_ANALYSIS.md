# ChromaDB Chunk Metadata Analysis

## Summary

**Total Chunks:** 869  
**Collection:** `geography_docs_enriched`

---

## Metadata Structure Comparison

### ✅ Enriched Chunks (703 chunks - 80.9%)
**Example:** NCERT, Majid Hussain, Vision Notes

**Full Metadata (9 fields):**
```json
{
  "chunk_id": "1_1_1",
  "filename": "NCERT-Class-12-Geography-Part-1.pdf",
  "subject": "Geography",
  "chapter": "Human Geography",
  "section": "General",
  "major_domain": "Physical Geography",      // ✅ Enriched
  "sub_domain": "Natural Disasters",          // ✅ Enriched
  "difficulty": "Moderate",                   // ✅ Enriched
  "summary": "Nature and Scope You have..."   // ✅ Enriched
}
```

**Fields:**
- ✅ `chunk_id` - Unique identifier
- ✅ `filename` - Source file name
- ✅ `subject` - Always "Geography"
- ✅ `chapter` - Chapter/topic name
- ✅ `section` - Section name
- ✅ `major_domain` - **ENRICHED** (e.g., "Physical Geography", "Human Geography")
- ✅ `sub_domain` - **ENRICHED** (e.g., "Natural Disasters", "Climatology")
- ✅ `difficulty` - **ENRICHED** (e.g., "Moderate", "Advanced")
- ✅ `summary` - **ENRICHED** (content summary)

---

### ⚠️ Current Affairs Chunks (166 chunks - 19.1%)
**Example:** `current affairs 2025.pdf`, `current affairs_1.pdf`, `current affairs_2.pdf`

**Basic Metadata (5 fields only):**
```json
{
  "chunk_id": "1_1_1",
  "filename": "current affairs 2025.pdf",
  "subject": "Geography",
  "chapter": "I",
  "section": "CLIMATOLOGY"
}
```

**Missing Enriched Fields:**
- ❌ `major_domain` - **NOT ENRICHED** (shows as "Unknown")
- ❌ `sub_domain` - **NOT ENRICHED** (shows as "Unknown")
- ❌ `difficulty` - **NOT ENRICHED**
- ❌ `summary` - **NOT ENRICHED**

---

## Filename Distribution

| Filename | Chunks | Percentage |
|----------|--------|------------|
| `geography-majid-hussian.pdf` | 242 | 27.8% |
| `geography - mains notes.pdf` | 126 | 14.5% |
| `NCERT-Class-12-Geography-Part-2.pdf` | 113 | 13.0% |
| `NCERT-Class-12-Geography-Part-1.pdf` | 73 | 8.4% |
| `current affairs_1.pdf` | 65 | 7.5% |
| `current affairs 2025.pdf` | 64 | 7.4% |
| `geography-pyq topic wise.pdf` | 52 | 6.0% |
| `NCERT-Class-11-Geography-Practical.pdf` | 48 | 5.5% |
| `current affairs_2.pdf` | 37 | 4.3% |
| Other files | 129 | 14.8% |

**Current Affairs Files Total:** 166 chunks (19.1%)

---

## Current Affairs Chunks Analysis

### Content Topics (from content analysis):
- Cyclones (formation, types, regions)
- Monsoon (mechanism, impact, onset)
- Bay of Bengal vs Arabian Sea
- Sundarbans
- Climate change impacts
- Weather systems

### Section Distribution:
- All chunks have `section: "CLIMATOLOGY"`
- All chunks have `chapter: "I"`

### Issue:
**All 166 Current Affairs chunks are missing enriched metadata:**
- `major_domain` = Missing → Shows as "Unknown" in queries
- `sub_domain` = Missing → Shows as "Unknown" in queries
- `difficulty` = Missing
- `summary` = Missing

---

## Impact on Mock Test Generation

### Current Behavior:
1. **Topic Filtering:** Current Affairs chunks won't be filtered by `major_domain`/`sub_domain` because they're "Unknown"
2. **Retrieval:** They may still be retrieved by content similarity, but won't match topic filters
3. **Question Quality:** Questions generated from Current Affairs may lack proper domain classification

### Recommendation:
**Run metadata enrichment on Current Affairs chunks** to add:
- `major_domain` (likely "Physical Geography" → "Climatology")
- `sub_domain` (e.g., "Cyclones", "Monsoon", "Weather Systems")
- `difficulty` (based on content complexity)
- `summary` (concise content summary)

---

## Metadata Field Frequency

| Field | Chunks | Percentage |
|-------|--------|------------|
| `chunk_id` | 869 | 100.0% |
| `filename` | 869 | 100.0% |
| `subject` | 869 | 100.0% |
| `chapter` | 869 | 100.0% |
| `section` | 869 | 100.0% |
| `major_domain` | 703 | 80.9% ⚠️ |
| `sub_domain` | 703 | 80.9% ⚠️ |
| `difficulty` | 703 | 80.9% ⚠️ |
| `summary` | 703 | 80.9% ⚠️ |

**166 chunks (19.1%) are missing enriched metadata** - all are Current Affairs files.

---

## Sample Current Affairs Chunk Structure

```json
{
  "id": "doc_0_-4769086425061511362",
  "content": "CYCLONE Building Basics (Cyclones) About Cyclones...",
  "metadata": {
    "chunk_id": "1_1_1",
    "filename": "current affairs 2025.pdf",
    "section": "CLIMATOLOGY",
    "chapter": "I",
    "subject": "Geography"
  }
}
```

**Content:** ~3,200 characters about cyclones, formation, regions, etc.  
**Topic:** Climatology → Cyclones  
**Should have:** `major_domain: "Physical Geography"`, `sub_domain: "Cyclones"`

---

## Next Steps

1. **Identify unenriched chunks:**
   ```python
   unenriched = handler.get_unenriched_documents(key="major_domain")
   ```

2. **Run metadata enrichment** on Current Affairs chunks using `metadata_enricher.py`

3. **Update chunks** in ChromaDB with enriched metadata

4. **Verify** topic filtering works correctly for Current Affairs content

