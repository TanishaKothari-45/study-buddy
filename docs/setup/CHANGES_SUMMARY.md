# Study Buddy AI - Development Changes Summary

## Date: Current Session

This document summarizes all the changes made during this development session.

---

## 1. OCR Processing Improvements

### 1.1 Google Vision API Integration
- **Changed**: Replaced `vision_blocks` with `vision_blocks_and_fulltext` function
- **Key Features**:
  - Iterates through `page → block → paragraph → words` to build text (preserves spatial structure)
  - Extracts bounding boxes in format: `[[x1,y1],[x2,y2],[x3,y3],[x4,y4]]`
  - Calculates confidence scores per paragraph
  - Returns `full_text`, `width`, `height`, and `blocks` with confidence
  - Filters noise blocks (length > 2 characters only)

### 1.2 Preprocessing Removal
- **Changed**: Removed all preprocessing before sending to Google Vision API
- **Before**: Applied grayscale, denoise, deskew, contrast enhancement, morphological operations
- **After**: Only margin cropping (no preprocessing)
- **Reason**: Google Vision API handles preprocessing internally, and our preprocessing was potentially degrading quality

### 1.3 ROI Cropping Adjustments
- **Changed**: Reduced top and bottom margins for ROI cropping
- **Top margin**: 10% → 5%
- **Bottom margin**: 3% → 10% (keeps 90% of height)
- **Reason**: Previous cropping was too aggressive and cutting off content near page borders

### 1.4 OCR Data Structure
- **New Fields Added**:
  - `full_text`: Raw text from Google Vision
  - `width`, `height`: Image dimensions
  - `conf`: Average confidence per block
  - `blocks`: Array with `text`, `bbox`, `conf` for each block

---

## 2. LLM Answer Reconstruction

### 2.1 Reconstruction System Prompt
- **Updated**: Stricter "faithful transcriber" prompt
- **Key Rules**:
  - Use only OCR text (no external knowledge)
  - Fix only spacing/case for readability
  - Insert placeholders for diagrams/tables: `[diagram: descriptor]`
  - Mark unclear text as `[unclear]`
  - Do NOT evaluate or correct factual content

### 2.2 Multi-Page Support
- **Changed**: `reconstruct_pages_blocks` now combines all pages before sending to LLM
- **Reason**: Ensures entire answer (even if spanning multiple pages) is reconstructed in one call
- **Parameters**: `combine_pages=True` (default), `temperature=0`, `top_p=0` for deterministic output

### 2.3 OCR Data Display
- **Added**: Display of raw OCR data sent to LLM (before reconstruction)
- **Location**: Temporary JSON file saved for inspection
- **Purpose**: Allows debugging and verification of OCR quality

---

## 3. LLM Evaluation System

### 3.1 Three-Task Evaluation Process
Implemented a comprehensive evaluation system with three tasks:

#### Task 1: Identify Question
- Detects and extracts question text from OCR blocks
- Looks for question markers and directive words

#### Task 2: Reconstruct Student Answer
- Reconstructs handwritten answer into clean paragraphs
- Uses only OCR text
- Inserts placeholders for diagrams/tables
- Marks unclear text as `[unclear]`

#### Task 3: Evaluate the Answer
- Evaluates based on UPSC Mains criteria:
  - Intro contextualness
  - Directive interpretation
  - IBC structure
  - Multi-dimensionality
  - India-specific examples
  - Inline diagram suggestions
  - Conclusion synthesis
- Scoring: Out of 20 with subsection scores and justifications

### 3.2 Evaluation Output Format
```
### QUESTION
<identified question text>

### RECONSTRUCTED ANSWER
<clean reconstructed answer>

### SCORE (out of 20)
x/20

### WHAT WAS DONE WELL
• Bullet points of strengths

### WHAT WAS MISSING / CAN BE IMPROVED
• Specific content gaps

### HIGH RETURN IMPROVEMENTS
• Actionable suggestions with location
```

### 3.3 Evaluation Modes
- **Mode 1 (Preferred)**: `question` + `reconstructed_answer` → Evaluation only
- **Mode 2 (Deprecated)**: `ocr_data_json` → All 3 tasks (identify, reconstruct, evaluate)
- **Mode 3 (Legacy)**: `question` + `answer_text` → Text-based evaluation

### 3.4 Single LLM Call Architecture
- **Changed**: Combined all 3 tasks into ONE LLM call
- **Function**: `reconstruct_and_evaluate_from_ocr_blocks()`
- **Benefits**: 
  - More efficient (single API call)
  - Better context preservation
  - Consistent evaluation

---

## 4. Frontend Restructuring

### 4.1 Tab Separation
- **"Upload PDFs" Tab**:
  - Radio buttons: "PDF" or "Handwritten"
  - PDF upload → chunk → enrich → embed
  - Handwritten upload → PDF to image → ROI → OCR → LLM → PDF → chunk → enrich → embed
  - Removed sample sheet upload from this tab

- **"Evaluate Answer" Tab**:
  - Sample sheet upload (for ROI detection)
  - Radio buttons: "Upload File (Handwritten)" or "Paste Text"
  - Full pipeline: Upload → ROI → OCR → LLM (reconstruct + evaluate) → Display results
  - Multiple file upload support
  - Question input is optional (LLM identifies from OCR)

### 4.2 Evaluation Display
- Shows identified question
- Shows reconstructed answer (expandable)
- Shows detailed evaluation breakdown
- Shows raw LLM evaluation response (removed per user request)
- Download link for reconstructed PDF

---

## 5. Prelims Test Generator - MMR Retriever

### 5.1 MMR (Maximum Marginal Relevance) Implementation
- **Purpose**: Better diversity in retrieved chunks for question generation
- **Parameters**:
  - `fetch_k=50`: Fetch 50 candidates before MMR
  - `k=10`: Return 10 diverse results after MMR
  - `lambda_mult=0.65`: Balance between relevance (65%) and diversity (35%)

### 5.2 Joint Retrieval Orchestration
- **Process**:
  1. Retrieve PYQ chunks separately
  2. Retrieve content chunks separately
  3. Tag chunks with source metadata (`source: "pyq"` or `source: "content"`)
  4. Combine: `combined_chunks = pyq_chunks + content_chunks`
  5. Apply MMR: `diverse_context = mmr_select(combined_chunks, k=10)`
  6. Separate back using source metadata

- **Benefits**:
  - Cross-source diversity (mix of PYQ style + factual content)
  - Avoids parallel similar subsets
  - Better question variety

### 5.3 Source Metadata Tagging (Recommendation #2)
- **Implementation**: Tag chunks before combining
  ```python
  for chunk in pyq_chunks:
      chunk["metadata"]["source"] = "pyq"
  for chunk in content_chunks:
      chunk["metadata"]["source"] = "content"
  ```
- **Separation**: Use metadata instead of filename checks
  ```python
  diverse_pyq_chunks = [c for c in diverse_context if c["metadata"]["source"] == "pyq"]
  diverse_content_chunks = [c for c in diverse_context if c["metadata"]["source"] == "content"]
  ```

### 5.4 Fallback for < k Results (Recommendation #4)
- **Implementation**: If MMR returns fewer than `k` chunks, use fallback
- **Fallback Strategy**:
  - Use MMR results + random sample from remaining chunks
  - If not enough chunks available, use all available
- **Prevents**: Empty context edge cases

### 5.5 FAISS vs ChromaDB for Temporary Vectorstore
- **Changed**: Use FAISS only for temporary vectorstore in `mmr_select_from_chunks`
- **Removed**: ChromaDB fallback (due to dimensionality compatibility issues)
- **Fallback**: Random sampling if FAISS fails or not available

---

## 6. Bug Fixes

### 6.1 ChromaDB Telemetry Error
- **Error**: `Failed to send telemetry event ClientStartEvent: capture() takes 1 positional argument but 3 were given`
- **Fix**: Set environment variables before initializing ChromaDB client:
  ```python
  os.environ["ANONYMIZED_TELEMETRY"] = "False"
  os.environ["CHROMA_TELEMETRY_DISABLED"] = "True"
  ```

### 6.2 LangChain Dimensionality Error
- **Error**: `'dict' object has no attribute 'dimensionality'`
- **Cause**: LangChain Chroma expects embedding function to have `dimensionality` attribute
- **Fix**: 
  - Added `dimensionality` property to `ChromaEmbeddings` wrapper class
  - Dynamic detection: 1536 for OpenAI, 384 for Sentence Transformers
  - Added comprehensive error handling with fallbacks

### 6.3 EasyOCR Import Error
- **Error**: `ModuleNotFoundError: No module named 'easyocr'`
- **Fix**: Commented out `easyocr` import and related code
- **Reason**: Not using EasyOCR (using Google Vision API instead)

### 6.4 PDF2Image Import Error
- **Error**: `ModuleNotFoundError: No module named 'pdf2image'`
- **Fix**: Commented out `pdf2image` import and related code
- **Reason**: Only used for EasyOCR path, which is disabled

---

## 7. Code Quality Improvements

### 7.1 Error Handling
- Added comprehensive try-catch blocks around MMR operations
- Graceful fallbacks to random sampling if MMR fails
- Better error messages with actionable solutions

### 7.2 Logging
- Added extensive logging for:
  - OCR processing steps
  - LLM reconstruction output
  - MMR selection process
  - Error conditions and fallbacks

### 7.3 Code Organization
- Separated concerns: reconstruction vs evaluation
- Clear function naming and documentation
- Consistent error handling patterns

---

## 8. API Response Changes

### 8.1 Upload PDFs Endpoint
- **Added Fields**:
  - `full_text`: Raw OCR text
  - `full_text_length`: Character count
  - `width`, `height`: Image dimensions
  - `conf`: Confidence scores per block
  - `identified_question`: Question extracted from OCR

### 8.2 Evaluate Answer Endpoint
- **Added Fields**:
  - `reconstructed_answer`: Clean reconstructed answer
  - `raw_evaluation_response`: Exact LLM response (removed from frontend display)
  - `evaluation_details`: Structured evaluation data

---

## 9. Files Modified

### Backend
- `backend/app/utils/ocr_processor_v2.py`: Google Vision integration
- `backend/app/utils/answer_reconstructor.py`: LLM reconstruction
- `backend/app/utils/answer_evaluator.py`: Evaluation system
- `backend/app/utils/handwritten_processor.py`: Removed preprocessing
- `backend/app/utils/roi_detector.py`: Adjusted margins
- `backend/app/utils/chroma_handler.py`: MMR retriever implementation
- `backend/app/routes/upload.py`: Updated response format
- `backend/app/routes/evaluate_answer.py`: New evaluation modes
- `backend/app/utils/ocr_processor.py`: Commented out EasyOCR

### Frontend
- Frontend (migrated from Streamlit to Next.js): Restructured UI, added evaluation flow

---

## 10. Key Design Decisions

### 10.1 Why Single LLM Call for Evaluation?
- **Efficiency**: One API call instead of two
- **Context**: LLM sees full picture (question + answer) in one go
- **Consistency**: Better evaluation when question and answer are processed together

### 10.2 Why MMR Instead of Simple Similarity Search?
- **Diversity**: Avoids repetitive questions from similar chunks
- **Balance**: `lambda_mult=0.65` balances relevance and variety
- **Cross-Source**: Joint orchestration ensures mix of PYQ style + content

### 10.3 Why Remove Preprocessing?
- **Google Vision**: Handles preprocessing internally
- **Quality**: Our preprocessing was potentially degrading image quality
- **Simplicity**: Less code, fewer failure points

### 10.4 Why Source Metadata Instead of Filename Checks?
- **Reliability**: More robust than string matching
- **Debugging**: Clear traceability
- **Future-Proof**: Easier to extend with more source types

---

## 11. Testing Recommendations

### 11.1 OCR Quality
- Test with various handwriting styles
- Verify bounding boxes are accurate
- Check confidence scores are reasonable

### 11.2 LLM Reconstruction
- Verify placeholders are inserted correctly
- Check unclear text is marked properly
- Ensure no external knowledge is added

### 11.3 Evaluation System
- Test with various answer qualities
- Verify scoring is consistent
- Check improvements are actionable

### 11.4 MMR Retriever
- Test with different topic combinations
- Verify diversity in retrieved chunks
- Check fallback works when FAISS unavailable

---

## 12. Known Limitations

### 12.1 FAISS Dependency
- MMR requires FAISS for temporary vectorstore
- Falls back to random sampling if FAISS unavailable
- ChromaDB has compatibility issues with LangChain embedding functions

### 12.2 ChromaDB Collection Compatibility
- Existing collections may have embedding function stored as dict
- May need to recreate collection if dimensionality errors persist
- Workaround: Use FAISS for temporary vectorstores

### 12.3 EasyOCR Disabled
- EasyOCR code is commented out but not removed
- Functions will raise `NotImplementedError` if called
- Use Google Vision API instead

---

## 13. Future Improvements

### 13.1 Potential Enhancements
1. Install FAISS properly to enable MMR
2. Add deduplication step after MMR (if needed)
3. Weight PYQ embeddings (if MMR over-diversifies)
4. Add async cleanup for temporary collections
5. Implement L2 normalization for embeddings

### 13.2 Code Cleanup
1. Remove commented EasyOCR code entirely
2. Add FAISS to requirements.txt
3. Add unit tests for MMR retriever
4. Add integration tests for evaluation flow

---

## 14. Configuration

### 14.1 MMR Parameters
- `fetch_k=50`: Number of candidates to fetch
- `k=10`: Final diverse selection
- `lambda_mult=0.65`: Relevance/diversity balance (0.5-0.7 optimal)

### 14.2 LLM Parameters
- `temperature=0`: Maximum accuracy
- `top_p=0`: Deterministic output
- `max_tokens=3000`: For reconstruction + evaluation

### 14.3 ROI Cropping
- Top margin: 5%
- Bottom margin: 10% (keeps 90% of height)
- Left/Right: Existing margins maintained

---

## 15. Migration Notes

### 15.1 For Existing Users
- No breaking changes to API (backward compatible)
- New fields added to responses (optional)
- Evaluation endpoint supports multiple modes

### 15.2 For Developers
- EasyOCR code commented out (not removed)
- MMR retriever requires FAISS or falls back to random sampling
- Source metadata tagging is now standard practice

---

## 16. Performance Considerations

### 16.1 OCR Processing
- Google Vision API handles preprocessing (faster)
- Parallel processing maintained for multiple pages
- ROI cropping reduces image size (faster API calls)

### 16.2 LLM Calls
- Single call for reconstruction + evaluation (more efficient)
- Combined pages reduce number of API calls
- Deterministic parameters reduce retries

### 16.3 MMR Retrieval
- FAISS is fast for temporary vectorstores
- Falls back to random sampling if MMR unavailable (still fast)
- Joint orchestration reduces redundant processing

---

## Summary

This session focused on:
1. ✅ Improving OCR accuracy by removing preprocessing and using proper Google Vision API structure
2. ✅ Implementing comprehensive LLM evaluation system with single-call architecture
3. ✅ Restructuring frontend for better UX separation
4. ✅ Adding MMR retriever for better question diversity
5. ✅ Fixing various bugs (telemetry, dimensionality, imports)
6. ✅ Implementing best practices (source metadata, fallbacks, error handling)

All changes maintain backward compatibility while adding new features and improvements.


