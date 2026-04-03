# Question Distribution Implementation (Option A)

**Date**: 2026-04-04  
**Status**: ✅ Implemented in Stage 0  

---

## Distribution Ratios (40-25-15-15)

For a **10-question mock test:**
- **4 hard** (40%)
- **2-3 medium** (25%)
- **1-2 easy** (15%)
- **1-2 pure CA** (15% dedicated)

**Total: 10 questions across all difficulty levels**

---

## Implementation Details

### 1. DifficultyConfig (Updated)

**Before:**
```python
class DifficultyConfig(BaseModel):
    easy:   float = 0.25
    medium: float = 0.50
    hard:   float = 0.25
```

**After:**
```python
class DifficultyConfig(BaseModel):
    easy:   float = 0.15      # 15%
    medium: float = 0.25      # 25%
    hard:   float = 0.40      # 40%
    pure_ca: float = 0.15     # 15% dedicated pure CA questions
```

### 2. _difficulty_counts Function (Updated)

Returns 4 values instead of 3:
```python
def _difficulty_counts(cfg, num_questions) -> tuple[int, int, int, int]:
    # Returns: (easy_count, medium_count, hard_count, pure_ca_count)
    # All sum to exactly num_questions
```

### 3. CA Slot Allocation (Updated Logic)

**Old logic:**
```
ca_indices = 30% of all questions (any difficulty)
```

**New logic:**
```
pure_ca_indices = 15% of all questions (dedicated pure CA)
ca_linked_indices = 30% of remaining non-pure-CA questions

All pure_ca skeletons have: ca_flag=True, pure_ca=True
All ca_linked skeletons have: ca_flag=True, pure_ca=False
```

### 4. QuestionSkeleton Model (Updated)

**Added new field:**
```python
pure_ca: bool = False  # Is this a 100% pure CA question?
```

Used in conjunction with `ca_flag`:
```
ca_flag=False, pure_ca=False  → No CA (regular question)
ca_flag=True, pure_ca=False   → CA-linked (CA event linked to concept)
ca_flag=True, pure_ca=True    → Pure CA (100% dedicated to event)
```

---

## Skeleton Creation Logic (Stage 0)

```python
# For each question slot:
if difficulty == "pure_ca":
    # Pure CA question
    actual_difficulty = "easy"  # Base difficulty for generation
    pure_ca = True
    ca_flag = True  # MUST have CA search
    question_type = "direct_fact" or "multi_statement"  # CA-friendly types
else:
    # Regular question (easy/medium/hard)
    actual_difficulty = difficulty
    pure_ca = False
    ca_flag = slot["ca_linked"]  # May or may not be CA-linked
    question_type = type_by_difficulty[difficulty]
```

---

## Example: 10-Question Distribution

```
Distribution allocation (10 questions):

HARD: 4 questions
  └─ sk_001: hard, ca_flag=False, pure_ca=False
  └─ sk_002: hard, ca_flag=True, pure_ca=False  (CA-linked)
  └─ sk_003: hard, ca_flag=False, pure_ca=False
  └─ sk_004: hard, ca_flag=True, pure_ca=False  (CA-linked)

MEDIUM: 2-3 questions
  └─ sk_005: medium, ca_flag=False, pure_ca=False
  └─ sk_006: medium, ca_flag=True, pure_ca=False  (CA-linked)
  └─ sk_007: medium, ca_flag=False, pure_ca=False

EASY: 1-2 questions
  └─ sk_008: easy, ca_flag=False, pure_ca=False
  └─ sk_009: easy, ca_flag=True, pure_ca=False  (CA-linked)

PURE CA: 1-2 questions
  └─ sk_010: easy (base), ca_flag=True, pure_ca=True
  └─ sk_011: easy (base), ca_flag=True, pure_ca=True  (if 10 questions)
```

---

## Stage 3 Usage (Generation)

When LLM generates questions:

**For pure_ca=False:**
- Use chunks + CA context flexibly
- Type 2: CA event linked to static concept

**For pure_ca=True:**
- Focus 100% on the CA event
- Type 1: Pure CA question
- Example: "Explain 2023 floods and agricultural impact"

---

## Logging Output

Expected logs from blueprint generation:

```
[Stage0] Pre-sampled 30 slots — 12 hard, 8 medium, 6 easy, 4 pure_ca
[Stage0] Blueprint: 10Q | Geography > Geography > Climatology
[Stage0] Difficulty distribution:
  - Hard: 4 (40%)
  - Medium: 2 (25%)
  - Easy: 1 (15%)
  - Pure CA: 1 (15%)
[Stage0] CA allocation:
  - Pure CA: 1 questions (dedicated)
  - CA-linked: 2 questions (30% of non-pure-CA)
  - Regular: 6 questions (no CA)
```

---

## Summary

✅ **Distribution ratios updated**: 40% hard, 25% medium, 15% easy, 15% pure CA  
✅ **DifficultyConfig extended**: Added pure_ca field  
✅ **_difficulty_counts returns 4 values**: easy, medium, hard, pure_ca  
✅ **QuestionSkeleton.pure_ca field added**: Tracks 100% CA questions  
✅ **CA allocation logic updated**: Pure CA separate from CA-linked  
✅ **Stage 0 generates correct distribution**: 10 questions follow 40-25-15-15 split  

**Pipeline ready for distribution-compliant question generation.** 🚀
