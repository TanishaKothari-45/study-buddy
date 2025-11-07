# Dual Retrieval Strategy Implementation

## ✅ Implementation Complete

### **What Was Implemented:**

1. **PYQ Detection Function** (`is_pyq_chunk()`)
   - Detects PYQ chunks by filename patterns:
     - `"geography-pyq topic wise"`
     - `"geography_questions_in_upsc_prelims"`
     - `"pyq"`, `"prelims"`, `"previous year"`
   - Case-insensitive matching

2. **Enhanced Query Function** (`query_documents()`)
   - Added optional `filter_metadata` parameter
   - Supports post-filtering by metadata fields
   - Queries more results when filtering to ensure enough matches

3. **Dual Retrieval in Mock Test Generation**
   - **Step 1**: Query PYQ chunks for style learning
   - **Step 2**: Query content chunks (excluding PYQs) for knowledge
   - **Step 3**: Combine both contexts in enhanced prompt

4. **Enhanced Prompt Engineering**
   - Separates style context (PYQs) from knowledge context (content)
   - Explicitly instructs GPT to learn from PYQ patterns
   - Uses content material for factual question generation

---

## 🔍 How It Works

### **Flow:**

```
User Request (topic: "Monsoon")
    ↓
1. Query PYQ chunks: "UPSC prelims geography question patterns for Monsoon"
   → Filter: Keep only chunks from PYQ files
   → Result: 5 PYQ chunks (style examples)
    ↓
2. Query Content chunks: "Monsoon geography concepts NCERT vision notes"
   → Filter: Exclude PYQ files
   → Result: 8 content chunks (knowledge base)
    ↓
3. Build Dual Context:
   - context_style = PYQ chunks (for pattern learning)
   - context_knowledge = Content chunks (for question material)
    ↓
4. Enhanced Prompt:
   - System: Instructions to learn style from PYQs
   - User: PYQ examples + Content material + Generation instructions
    ↓
5. Generate Questions:
   - Follows UPSC style from PYQs
   - Uses facts from content material
   - Creates new, authentic questions
```

---

## 📊 Current Database State

### **PYQ Files Detected:**
- ✅ `geography-pyq topic wise.pdf` (found in database)

### **Content Files (Non-PYQ):**
- `Certificate Physical and Human Geography[www.UPSCPDF.com].pdf`
- `Copy of our environmemnt class 7 - Copy.pdf`
- `NCERT-Class-10-Geography.pdf`
- `NCERT-Class-11-Geography-Practical.pdf`
- `NCERT-Class-12-Geography-Part-1.pdf`
- `NCERT-Class-12-Geography-Part-2.pdf`
- `geography - mains notes.pdf`
- `geography-majid-hussian.pdf`
- `social science class 8.pdf`

---

## ⚠️ Potential Issues & Solutions

### **Issue 1: No PYQ Chunks Found**
**Scenario**: Query doesn't return any PYQ chunks
**Solution**: 
- Fallback to using content chunks for both style and knowledge
- Warning logged: "⚠️ No PYQ chunks found. Questions may lack UPSC style patterns."
- System still generates questions but may lack authentic UPSC style

### **Issue 2: PYQ Chunks Not Topic-Relevant**
**Scenario**: PYQ chunks retrieved don't match the requested topic
**Solution**:
- Query is topic-aware: `"UPSC prelims geography question patterns for {topic}"`
- Retrieves top 15 candidates, filters for PYQs, uses top 5
- Even if topic doesn't match exactly, style patterns are still learned

### **Issue 3: Insufficient Content Chunks**
**Scenario**: Not enough content chunks after filtering PYQs
**Solution**:
- Queries 12 candidates, filters out PYQs
- If < 8 content chunks, uses all available
- Error raised only if zero content chunks found

### **Issue 4: Filename Pattern Mismatch**
**Scenario**: PYQ file has different naming pattern
**Solution**:
- `is_pyq_chunk()` checks multiple patterns
- Easy to extend: just add pattern to `pyq_patterns` list
- Currently checks: `pyq`, `prelims`, `previous year` (case-insensitive)

---

## 🎯 Recommendations

### **1. Monitor PYQ Detection**
- Check logs to see how many PYQ chunks are retrieved
- If consistently low, consider:
  - Adding more PYQ files
  - Adjusting query strategy
  - Expanding filename patterns

### **2. Quality Metrics**
- Track question quality feedback
- Compare questions generated with/without PYQ chunks
- Adjust prompt if style learning isn't effective

### **3. Topic-Specific PYQ Retrieval**
- Current: General PYQ style learning
- Future: Could filter PYQs by `major_domain`/`sub_domain` for topic-specific style

### **4. Metadata Enhancement**
- Consider adding `source_type` field during upload (future enhancement)
- Would make filtering more explicit and reliable

---

## 🧪 Testing

### **Test Cases:**

1. **With PYQ File Present:**
   ```python
   # Should retrieve PYQ chunks and content chunks separately
   # Questions should follow UPSC style
   ```

2. **Without PYQ File:**
   ```python
   # Should fallback to content chunks
   # Warning logged, questions still generated
   ```

3. **Topic-Specific Query:**
   ```python
   # Should retrieve topic-relevant PYQs and content
   # Questions should be on-topic
   ```

4. **Edge Case - All Chunks are PYQs:**
   ```python
   # Should use PYQs for both style and content
   # May generate questions too similar to existing PYQs
   ```

---

## 📝 Code Changes Summary

### **Files Modified:**

1. **`backend/app/utils/chroma_handler.py`**
   - Added `filter_metadata` parameter to `query_documents()`
   - Implemented post-filtering logic
   - Added `Optional` import

2. **`backend/app/routes/mock_test.py`**
   - Added `is_pyq_chunk()` helper function
   - Updated `generate_mock_test()` with dual retrieval
   - Updated `generate_question_paper()` signature
   - Enhanced prompts with dual context
   - Separated style and knowledge contexts

---

## ✅ Status: Ready for Testing

The implementation is complete and ready for testing. The system will:
- ✅ Detect PYQ chunks by filename
- ✅ Retrieve PYQ chunks for style learning
- ✅ Retrieve content chunks for knowledge
- ✅ Combine both in enhanced prompt
- ✅ Handle edge cases gracefully

**Next Steps:**
1. Test with existing database
2. Monitor logs for PYQ detection
3. Evaluate question quality
4. Iterate based on results

