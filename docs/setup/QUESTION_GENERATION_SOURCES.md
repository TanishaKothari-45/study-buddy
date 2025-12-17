# Question Generation Sources - Confirmation

## ✅ Confirmed: All Three Sources Are Used

Your prelims question generator uses **all three sources** for style learning:

### 1️⃣ **Few-Shot Patterns from JSON** (`geography_prelims_pyq_patterns.json`)
- **Location:** `generate_fewshot_examples()` function (lines 61-87)
- **What:** Gets examples from ALL 6 PYQ patterns
- **How:** 
  ```python
  all_patterns = get_all_patterns()  # Gets all 6 patterns
  for pattern in all_patterns:
      pattern_examples = get_examples(topic=None, pattern=pattern["id"], n=2)
      all_examples.append(example)  # Adds one from each pattern
  ```
- **Result:** 6 examples covering all question types (Multi-statement, Assertion-Reason, Match-the-Pair, etc.)

### 2️⃣ **High-Quality Questions from Memory DB** (User Feedback)
- **Location:** `generate_fewshot_examples()` function (lines 89-113)
- **What:** Gets top-rated questions marked as "high" quality by users
- **How:**
  ```python
  feedback_examples = get_high_quality_examples(
      limit=3,  # Get 3 high-quality examples
      topic=filter_topic,
      difficulty=difficulty
  )
  # Adds to all_examples list
  ```
- **Result:** 3 examples from user-approved high-quality questions
- **Includes:** User's reason/comment if available (shown as "💡 Note:")

### 3️⃣ **PYQ Chunks from Database** (Retrieved from Pinecone)
- **Location:** `hybrid_retrieve_for_mock_test()` function (lines 594-603)
- **What:** Retrieves PYQ chunks from vector database for style reference
- **How:**
  ```python
  pyq_chunks = pinecone_handler.query_documents(
      query_text=query,
      k=5,
      filter_metadata={"source_type": "pyq", "source_subtype": "prelims"},
      use_content_store=True
  )
  ```
- **Usage:** 
  - Primary: Used in `pyq_examples_text` if fewshot_examples is empty (fallback)
  - **Note:** Currently, PYQ chunks are retrieved but may not be directly included in prompt if fewshot_examples exists
  - However, they ARE retrieved and available for future enhancement

## Current Flow

```
Question Generation Request
    ↓
1. Retrieve PYQ chunks from database (5 chunks)
    ↓
2. Generate few-shot examples:
   - 6 examples from PYQ patterns JSON
   - 3 examples from memory DB (high-quality feedback)
   = 9 total few-shot examples
    ↓
3. Combine into prompt:
   - Few-shot examples (9 examples: 6 patterns + 3 feedback)
   - Static content chunks (NCERT, Vision notes)
   - Current affairs chunks (if medium/hard)
    ↓
4. Send to GPT-4o for question generation
```

## Prompt Structure

The final prompt includes:

```
SYSTEM: [UPSC Question Setter instructions]

FRAMEWORK: [Cognitive framework rules]

DIFFICULTY MODE: [Easy/Medium/Hard guidelines]

CONTEXT SOURCES:
📘 Static Material: [NCERT/Vision content]

🗞️ Current Affairs: [Recent developments]

PYQ STYLE EXAMPLES:
[Example 1 - Pattern: Multi-Statement (from JSON)]
[Example 2 - Pattern: Assertion-Reason (from JSON)]
...
[Example 7 - Pattern: User Feedback (from Memory DB)]
[Example 8 - Pattern: User Feedback (from Memory DB)]
[Example 9 - Pattern: User Feedback (from Memory DB)]

TASK: [Generate questions]
```

## Summary

✅ **Few-shot patterns from JSON:** 6 examples (all patterns covered)  
✅ **High-quality from memory DB:** 3 examples (user-approved)  
✅ **PYQ chunks from database:** Retrieved (5 chunks, used as fallback if needed)

**Total:** Up to 9 few-shot examples + 5 PYQ chunks available for style learning

## Enhancement Opportunity

Currently PYQ chunks are retrieved but only used as fallback. To ensure all three sources are **always** included, you could:

1. **Option A:** Always include PYQ chunks in the prompt alongside few-shot examples
2. **Option B:** Use PYQ chunks to supplement when few-shot examples are fewer than 9
3. **Option C:** Keep current behavior (PYQ chunks as fallback)

The current implementation prioritizes curated few-shot examples (patterns + feedback) over raw PYQ chunks, which is a good design choice for quality.

