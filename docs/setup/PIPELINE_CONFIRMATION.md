# Pipeline Confirmation ✅

## Current Pipeline Flow

### ✅ Step 1: ROI per page
**Location:** `backend/app/utils/handwritten_processor.py`

- **PDFs:** ROI detected once from first page/sample sheet, then applied to all pages
- **Images:** ROI detected per image
- **Result:** Each page has its own ROI image (cropped margins)

```python
# process_pdf_with_roi() - line 100-124
for i, pil_image in enumerate(images):
    roi_rgb = apply_roi_to_image(img_bgr, roi_coords)  # ROI per page
    pages_data.append({
        "page_number": i + 1,
        "roi_image_preprocessed": roi_rgb  # ROI per page
    })
```

### ✅ Step 2: Combine ROI images into list
**Location:** `backend/app/routes/upload.py` & `backend/app/utils/handwritten_processor.py`

- ROI images from all pages are collected into `pages_data` list
- Each entry contains: `page_number`, `roi_image_preprocessed`

```python
# upload.py - line 390-394 (for images) or 305-310 (for PDFs)
page_data = [{
    "page_number": 1,
    "roi_image_preprocessed": roi_result["roi_image_preprocessed"]
}]
```

### ✅ Step 3: OCR (Google Vision) ONCE per page
**Location:** `backend/app/utils/ocr_processor_v2.py`

- Each page's ROI is sent to Google Vision API separately
- Uses `document_text_detection` (not `text_detection`)
- Returns blocks + full_text per page

```python
# process_pages_parallel_google_vision() - line 231-263
def run_single(page: Dict[str, Any]) -> Dict[str, Any]:
    roi = page.get("roi_image_preprocessed")
    ocr_result = vision_blocks_and_fulltext(roi)  # ONE call per page ROI
    return {
        "page_number": page_no,
        "blocks": blocks,  # Blocks from this page
        "full_text": full_text,  # Full text from this page
        ...
    }
```

### ✅ Step 4: Collect ALL blocks from ALL pages
**Location:** `backend/app/utils/answer_reconstructor.py` & `web/src/` (Next.js frontend)

**For Upload PDFs:**
```python
# answer_reconstructor.py - line 216-240
combined_blocks = []
combined_full_texts = []
for result in ocr_results:
    combined_blocks.extend(blocks)  # Collect ALL blocks
    combined_full_texts.append(full_text)  # Collect ALL full_text
```

**For Evaluate Answer:**
```python
# Frontend (now in web/src/ - Next.js implementation)
combined_blocks = []
for r in all_ocr_results:
    combined_blocks.extend(blocks)  # Collect ALL blocks from ALL pages/files
```

### ✅ Step 5: Reconstruct + Evaluate (ONE LLM CALL)

**For Upload PDFs (Reconstruction only):**
```python
# answer_reconstructor.py - line 246-250
reconstruction_result = reconstruct_with_question_identification(
    ocr_data=combined_ocr_data,  # ALL pages combined
    llm_client=llm_client,
    model=model
)
# ✅ ONE LLM call for all pages
```

**For Evaluate Answer (Reconstruct + Evaluate):**
```python
# evaluate_answer.py - line 283-287
evaluation_result = evaluate_from_ocr_blocks(
    ocr_data=ocr_data,  # ALL pages combined
    llm_client=openai_client,
    model=settings.LLM_MODEL
)
# ✅ ONE LLM call does: Identify Question + Reconstruct + Evaluate
```

## Pipeline Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    INPUT: PDF/Images                        │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 1: ROI per page                                      │
│  • Detect ROI (once or per page)                          │
│  • Crop margins (5% top, 10% bottom)                       │
│  • Result: List of ROI images                              │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 2: Combine ROI images into list                      │
│  • pages_data = [                                           │
│      {page_number: 1, roi_image: ...},                    │
│      {page_number: 2, roi_image: ...},                    │
│      ...                                                    │
│    ]                                                        │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 3: OCR (Google Vision) ONCE per page                │
│  • For each page ROI:                                       │
│    vision_client.document_text_detection(roi_image)        │
│  • Result: [                                                │
│      {page: 1, blocks: [...], full_text: "..."},          │
│      {page: 2, blocks: [...], full_text: "..."},          │
│      ...                                                    │
│    ]                                                        │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 4: Collect ALL blocks from ALL pages                 │
│  • combined_blocks = []                                     │
│  • combined_full_texts = []                                 │
│  • for page in ocr_results:                                 │
│      combined_blocks.extend(page.blocks)                  │
│      combined_full_texts.append(page.full_text)            │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 5: Reconstruct + Evaluate (ONE LLM CALL)            │
│  • Upload PDFs:                                             │
│    reconstruct_with_question_identification(               │
│      {blocks: ALL_BLOCKS, full_text: ALL_TEXT}            │
│    )                                                        │
│  • Evaluate Answer:                                         │
│    evaluate_from_ocr_blocks(                               │
│      {blocks: ALL_BLOCKS, full_text: ALL_TEXT}            │
│    )  # Does: Identify Question + Reconstruct + Evaluate  │
└─────────────────────────────────────────────────────────────┘
```

## ✅ Confirmation

**YES, we are following the correct pipeline:**

1. ✅ **ROI per page** - Each page gets its own ROI detection/crop
2. ✅ **Combine ROI images into list** - All ROI images collected in `pages_data`
3. ✅ **OCR ONCE per page** - Each ROI sent to Google Vision separately
4. ✅ **Collect ALL blocks from ALL pages** - Blocks combined before LLM
5. ✅ **Reconstruct + Evaluate (ONE LLM CALL)** - Single LLM call with all pages combined

## Key Points

- **No per-page reconstruction** - All pages are combined before LLM call
- **No per-page evaluation** - All pages evaluated together
- **Proper block collection** - All blocks from all pages are combined
- **Single LLM call** - More efficient and preserves context across pages

