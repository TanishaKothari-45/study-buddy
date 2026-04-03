# Current Affairs & Question Distribution Clarification

**Date**: 2026-04-04  
**Status**: ✅ Clarified architecture, pending distribution config update

---

## Current Affairs Architecture (MANDATORY)

### Two Types of CA Questions:

**1. Pure CA Questions (Dedicated 10% slot)**
- Skeleton flagged: ca_flag=True, pure_ca=True
- Entire question focuses on the event
- Example: "Explain the 2023 monsoon floods and its impact on agriculture"
- **Difficulty**: Can be easy/medium/hard (TBD from distribution)

**2. CA-Linked Questions (Rest with ca_flag=True)**
- Skeleton flagged: ca_flag=True, pure_ca=False
- Current affairs event linked to static concept
- Usage:
  - As a statement: "Recent 2023 floods showed X pattern related to [concept]"
  - In match pair: "Floods 2023" ← "Policy Response"
  - Integrated into stem: "Following the 2023 floods, which statement about [concept] is correct?"
- **Difficulty**: Matches skeleton's difficulty (easy/medium/hard)

**Implementation:**
```python
# Stage 0 (Blueprint)
skeleton.ca_flag = True/False  # Does this Q need CA context?
skeleton.pure_ca = True/False  # Is it 100% CA question?

# Stage 1 (Retrieval)
if skeleton.ca_flag:
    ca_context = Google Search results (paired with THIS skeleton)

# Stage 3 (Generation)
if skeleton.ca_flag and skeleton.pure_ca:
    "Type 1: Pure CA Question"
else if skeleton.ca_flag:
    "Type 2: CA-Linked Question"
else:
    "No CA context"
```

---

## Question Distribution (40-25-15-15)

**Requested Distribution:**
- 40% hard questions
- 25% medium questions
- 15% easy questions
- 15% pure CA questions (dedicated)

**Clarification Needed:**

For a 10-question test:
- 4 hard
- 2-3 medium
- 1-2 easy
- 1-2 pure CA

**Question**: Are the percentages:

**Option A: 10 questions total**
```
Difficulty distribution across ALL 10:
- Hard: 4 questions (40%)
- Medium: 2.5 → 2 questions (25%)
- Easy: 1.5 → 2 questions (15%)
- Pure CA: 1.5 → 1 question (10%?)
Total: 10 questions

Within each difficulty, some are CA-linked + some are pure CA?
```

**Option B: 10 questions, 15% dedicated pure CA**
```
Non-CA questions: 8.5 → 8 or 9
- Hard: 40% of 8-9 = 3-4 questions
- Medium: 25% of 8-9 = 2 questions
- Easy: 15% of 8-9 = 1-2 questions

Pure CA questions: 15% of 10 = 1.5 → 1-2 questions
```

**Option C: Percentages apply within difficulty**
```
- Hard: 40% of questions are hard (some pure CA, some CA-linked)
- Medium: 25% are medium (some CA-linked)
- Easy: 15% are easy (some CA-linked)
- Remaining: 20% are ???
```

Please confirm which interpretation is correct.

---

## Current Implementation Status

**Stage 0 (Blueprint):**
- ✅ Allocates difficulty distribution (currently 25% easy, 50% medium, 25% hard)
- ✅ CA linkage rate: 30% of questions get ca_flag=True
- ❌ **Needs update**: New difficulty ratios + pure_ca flag implementation

**Stage 1 (Retrieval):**
- ✅ CA context retrieved separately per skeleton (paired correctly)

**Stage 3 (Generation):**
- ✅ CA block mandatory (just updated)
- ✅ Clarifies Type 1 (pure CA) vs Type 2 (CA-linked)
- ❌ **Needs implementation**: Tracking distribution metrics + enforcement

---

## Next Steps

1. **Confirm distribution interpretation** (Option A/B/C above)
2. **Update Stage 0** with:
   - New difficulty ratios
   - pure_ca flag allocation
3. **Update Stage 3** with:
   - Distribution metrics logging
   - Enforcement/validation (warn if off-target)

---

## Summary

✅ **CA is MANDATORY** for flagged questions  
✅ **Two types implemented**: Pure CA (Type 1) + CA-Linked (Type 2)  
✅ **CA paired per skeleton** (no bleeding across questions)  
⏳ **Distribution enforcement**: Pending clarification + implementation
