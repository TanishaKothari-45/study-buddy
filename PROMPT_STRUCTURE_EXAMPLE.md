# How Content (70%) + Style Learning (30%) Are Sent to LLM

## Complete Prompt Structure

Here's exactly how the prompt is assembled and sent to GPT-4o:

### Prompt Assembly Flow

```python
# 1. Content Preparation (70% of prompt)
static_text = deduplicated_chunks_from_ncert_vision  # ~3000 chars
current_affairs_text = current_affairs_chunks  # ~1200 chars
# Total Content: ~4200 chars (70%)

# 2. Style Learning Preparation (30% of prompt)
style_examples = generate_fewshot_examples(
    pyq_chunks=pyq_chunks,  # 40% of style
    patterns_json,           # 40% of style
    feedback_db              # 30% of style
)
# Total Style: ~1800 chars (30%)

# 3. Assemble Prompt
user_prompt = assemble_upsc_prompt(
    topic=topic,
    difficulty=difficulty,
    num_questions=num_questions,
    retrieved_static_text=static_text,        # 70% - Content
    retrieved_current_affairs=current_affairs_text,  # Part of 70%
    pyq_examples=style_examples              # 30% - Style Learning
)

# 4. Send to LLM
completion = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": user_prompt}]
)
```

## Actual Prompt Structure Sent to LLM

```
SYSTEM:

You are a senior UPSC Prelims Question Setter specializing in Geography.

Your goal: generate original, authentic UPSC-quality MCQs from retrieved materials and PYQ examples.

Questions must sound indistinguishable from actual UPSC papers.

---

FRAMEWORK:

COGNITIVE FRAMEWORK (Apply to all difficulties)

1️⃣ Concept Focus
   - Base each question on ONE clear concept or mechanism per chunk group.

2️⃣ Context Variation
   - Vary spatial (India/global), temporal (historic/current), and domain (physical/human/environmental) perspectives.

3️⃣ Question Type Diversity
   - Include these formats across a test: Multi-statement, Assertion–Reason, Match-the-Pair, Concept Definition, and one Current-Affairs-Linked.

4️⃣ Option Engineering
   - Provide 3–4 plausible distractors.
   - Use authentic UPSC phrasing: "1 and 2 only", "All of the above", "Which of the following is/are NOT correct".

5️⃣ Explanation Discipline
   - Give concise explanations for why the correct option is right and why others are wrong, using the Vision IAS tone.

---

DIFFICULTY MODE:

MEDIUM MODE

• Blend two related subtopics (e.g., Monsoon + Agriculture).
• May include one "NOT correct" or Assertion–Reason question.
• Use elimination reasoning; moderate option confusion.
• Explanation: 2 concise lines covering concept and reasoning.

---

CONTEXT SOURCES:

📘 Static Material:

[~3000 characters of NCERT/Vision content - 70% of factual content]
Example:
"The monsoon is a seasonal wind system that brings heavy rainfall to the Indian subcontinent. 
It is characterized by the reversal of wind direction between summer and winter. 
The southwest monsoon arrives in India around June and brings about 75% of the annual rainfall..."

🗞️ Current Affairs (if any):

[~1200 characters of current affairs - part of 70% factual content]
Example:
"Recent IMD reports indicate that the 2024 monsoon season showed above-normal rainfall patterns 
in most parts of India. The La Niña conditions in the Pacific Ocean contributed to enhanced 
monsoon activity. Government initiatives like the Pradhan Mantri Krishi Sinchayee Yojana..."

PYQ STYLE EXAMPLES:

[~1800 characters of style learning examples - 30% of prompt]

Example 1 - Pattern: Multi-Statement (ID: Q1)
Consider the following statements regarding the Indian Monsoon:
1. The monsoon arrives in Kerala around June 1st
2. It advances northward in stages
3. The withdrawal begins in September
Which of the following is correct?
✅ Correct Answer: (A)
📘 Topic: Climatology (Year: 2020)

---

Example 2 - Pattern: Assertion-Reason (ID: Q2)
Assertion (A): The monsoon trough shifts northward during July-August.
Reason (R): The ITCZ moves northward during summer months.
Which of the following is correct?
✅ Correct Answer: (A)
📘 Topic: Climatology (Year: 2019)

---

Example 3 - Pattern: PYQ Database (ID: pyq_chunk)
[Actual PYQ question from database - retrieved from Pinecone]
Which of the following factors influence the onset of monsoon in India?
(a) Position of ITCZ
(b) Tibetan Plateau heating
(c) Mascarene High
(d) All of the above
📘 Topic: Climatology (Year: PYQ Database)

---

Example 4 - Pattern: User Feedback (ID: feedback)
[High-quality question marked by user]
Consider the following statements regarding El Niño:
1. It causes warming of Pacific Ocean
2. It weakens the Indian monsoon
3. It occurs every 2-7 years
Which of the following is correct?
📘 Topic: Climatology (Year: User Feedback)
💡 Note: Balanced interlinking and strong UPSC-style trap

[More examples... up to 10 total]

---

TASK:

Generate 5 UPSC-style MCQs on the topic: Climatology.

Each question must follow this structure:

{
  "questions": [
    {
      "question": "...",
      "options": ["(a)...", "(b)...", "(c)...", "(d)..."],
      "correct_answer": "A" | "B" | "C" | "D",
      "explanation": "...",
      "source": {"topic": "...", "sub_domain": "..."}
    },
    ...
  ]
}

Ensure:

• 4–5 distinct question types across the test.
• 1–2 questions combine static + current info (if current affairs available).
• Avoid keyword or fact repetition.
• Tone and conciseness must match authentic UPSC.
• Each explanation justifies correct and incorrect options.

CRITICAL FORMATTING RULES:

1. For Multi-Statement questions ("Consider the following statements"):
   - The "question" field MUST include ALL statements WITHIN it.
   ...

2. For Assertion-Reason questions:
   ...

3. For Match-the-Pair questions:
   ...
```

## Character Distribution

### Content Section (70% = ~4200 chars)
```
📘 Static Material:        ~3000 chars (50% of total prompt)
🗞️ Current Affairs:        ~1200 chars (20% of total prompt)
─────────────────────────────────────────────
Total Content:             ~4200 chars (70% of total prompt)
```

### Style Learning Section (30% = ~1800 chars)
```
PYQ STYLE EXAMPLES:
- PYQ chunks (40% of style)    ~720 chars
- Patterns JSON (40% of style)  ~720 chars  
- Feedback (30% of style)      ~360 chars
─────────────────────────────────────────────
Total Style:                    ~1800 chars (30% of total prompt)
```

### Total Prompt
```
Total Characters: ~6000 chars
├─ Content (70%): ~4200 chars
│  ├─ Static: ~3000 chars
│  └─ Current Affairs: ~1200 chars
│
└─ Style Learning (30%): ~1800 chars
   ├─ PYQ chunks: ~720 chars (40% of style)
   ├─ Patterns JSON: ~720 chars (40% of style)
   └─ Feedback: ~360 chars (30% of style)
```

## How LLM Uses This

1. **Content Section (70%):**
   - LLM reads factual information from NCERT/Vision notes
   - Uses this to generate questions based on actual concepts
   - Ensures questions are factually accurate

2. **Style Learning Section (30%):**
   - LLM learns question formats and patterns
   - Mimics UPSC style from examples
   - Ensures questions sound authentic

3. **Combined Effect:**
   - **Content** provides: "What to ask about" (facts, concepts)
   - **Style** provides: "How to ask" (format, phrasing, structure)
   - Result: Factually accurate questions in authentic UPSC style

## Code Location

**Prompt Assembly:** `backend/app/utils/mock_test_prompting.py` - `assemble_upsc_prompt()`

**Content Preparation:** `backend/app/routes/mock_test.py` - `generate_question_paper()`

**Style Learning:** `backend/app/routes/mock_test.py` - `generate_fewshot_examples()`

**LLM Call:** `backend/app/routes/mock_test.py` - Lines 260-268

```python
completion = client.chat.completions.create(
    model=settings.LLM_MODEL_LARGE,  # gpt-4o
    messages=[
        {"role": "user", "content": user_prompt}  # Contains 70% content + 30% style
    ],
    temperature=0.7,
    max_tokens=4000,
    response_format={"type": "json_object"}
)
```

## Summary

✅ **Content (70%):** Sent in "CONTEXT SOURCES" section  
✅ **Style Learning (30%):** Sent in "PYQ STYLE EXAMPLES" section  
✅ **Both combined:** Single prompt sent to GPT-4o  
✅ **LLM receives:** Complete prompt with clear separation between facts and style

The LLM sees both sections clearly labeled, allowing it to:
- Extract facts from content section
- Learn style from examples section
- Generate questions that are both accurate and authentic

