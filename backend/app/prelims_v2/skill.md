# Prelims V2 Concept Pool Schema — Skill Definitions & Architecture

## Critical Distinction: Difficulty Types vs Traps

This document clarifies a **fundamental distinction** that was confused in earlier iterations.

### Difficulty Types (Question Structure Templates)

**Difficulty types** define **question structure and sampling strategy**. They answer: *"When I sample this concept, what kind of question should I generate?"*

Difficulty types are patterns in `difficulty_types_geography_base.json` and include:
- `easy_recall_static` — Pure memorized fact. Single concept. No inference.
- `easy_ca_trigger` — Recent CA event + basic concept recall
- `easy_reverse_mild` — Counterintuitive fact that's widely taught
- `medium_concept_linking_same_domain` — Two concepts from same domain linked
- `medium_adjacent_fact` — Correct concept + wrong adjacent detail (location, name, feature)
- `hard_cross_domain_linking` — Concept from Domain A linked to Domain B
- `hard_scenario_application` — Real-world scenario requiring synthesis
- etc.

**Used by:** Blueprint (Stage 0) to decide what question template to generate.

**NOT the same as:** Traps (which populate wrong answers).

### Traps (Misconception Injection)

**Traps** define **what goes wrong in the answer options**. They answer: *"What common misconception or error can we inject as a distractor?"*

Traps are patterns documented in `trap_registry.json` and registered per-concept via `trap_affinity` arrays. Examples:
- `pattern_1` — Reverse the obvious (correct answer contradicts intuition)
- `pattern_3` — Statistical reversal (use a number/metric that's close but wrong)
- `pattern_4` — Adjacent fact (related but different concept)
- `pattern_5` — CA trigger on static fact (current event confuses with unrelated knowledge)

**Used by:** Question Generator (Stage 1-2) to craft distractors.

**NOT the same as:** Difficulty types (which define overall question structure).

---

## Key Change: Introduction of `tested_as_question_types`

### What It Is

Each concept in the pool now carries `tested_as_question_types`: an array of **question types** that historically test that concept in PYQs.

**Example** (from `geography_geomorphology.json`):
```json
"Fluvial Processes & Landforms": {
  "priority": "ultra_high",
  "frequency_in_pyq": 7,
  "tested_as_question_types": ["assertion_reason", "multi_statement", "match_pair"],
  ...
}
```

### What Question Types Are

Question types describe the **format** of the question:
- `direct_fact` — "What is X?" / "Which defines X?" (pure recall)
- `multi_statement` — "Which of the following is true?" (multiple independent statements to evaluate)
- `assertion_reason` — "A: [assertion]. R: [reason]. Correct relationship?" (A/R format)
- `match_pair` — "Match X to Y" (linking task)
- `pure_ca` — Current affairs event + what concept does it test?
- `scenario` — Real-world scenario requiring application
- `comparison` — "Compare X vs Y"
- `interpretation` — Given a graph/diagram, infer the process
- `cross_domain_linking` — Links to concepts in different domains

### Why Add This

**Blueprint (Stage 0) uses this to:**
1. Sample a concept (e.g., "Monsoon")
2. **Check `tested_as_question_types`** to see which formats are appropriate
3. Preferentially pick one of those formats (e.g., "assertion_reason" is common for Monsoon)
4. This **reduces mismatch** between concept and question structure
5. For **practice generation**, expand to include multiple types even if not all tested in PYQs (e.g., add "scenario" even if rare, since students need practice with synthesis)

### How It Differs from Difficulty Types

- **`tested_as_question_types`** = What question **format** do students see for this concept?
  - Narrower, empirical, **format-specific**
- **`difficulty_types_geography_base.json`** = What **reasoning structure** makes a question hard or easy?
  - Broader, **template-based**, describes reasoning depth

**Example:**
- Concept: "Monsoon"
- `tested_as_question_types`: ["assertion_reason", "multi_statement", "match_pair", "pure_ca"]
- If Blueprint picks **"assertion_reason"**: looks up difficulty_types → `medium_concept_linking_same_domain` or `hard_cross_domain_linking` → generates question with that structure
- If Blueprint picks **"pure_ca"**: looks up difficulty_types → `easy_ca_trigger` → generates CA-triggered question

---

## Sampling Strategy vs Difficulty Type Confusion (RESOLVED)

Earlier versions confused "sampling strategy" (borrowed, current affairs, interlinked) with "difficulty type."

**Corrected understanding:**

### Sampling Strategy (in Blueprint)

Determines **which concept to sample** based on question distribution:
- **Borrowed Concept** — Pick a concept from this domain, generate standalone
- **Current Affairs Linked** — Sample a CA-triggered concept
- **Interlinked** — Sample a concept, also sample a linked concept from same/different domain
- **Pure Concept** — Single concept, no linking

### Difficulty Type (in Generator)

Once a concept (or pair of concepts) is sampled, determines **what question structure to use**:
- Sampling strategy → selects **which concepts**
- Difficulty type → selects **what question template**

**Example workflow:**
```
Sampling: "Interlinked from same domain"
  ↓
Concepts selected: Monsoon + Jet Streams
  ↓
Check tested_as_question_types: Monsoon → assertion_reason (common)
  ↓
Look up difficulty_type for interlinked pair: medium_concept_linking_same_domain
  ↓
Generate: "A: Monsoon onset is associated with jet stream southward shift. R: Because..."
```

---

## Interlink_Domains Structure (CORRECTED)

### Previous (Flat)
```json
"interlink_domains": ["Climatology", "Indian Geography"]
```

### Current (Structured)
```json
"interlink_domains": [
  {
    "domain": "Climatology",
    "concepts": ["Monsoon", "Rainfall Types", "Temperature Distribution"]
  },
  {
    "domain": "Indian Geography",
    "concepts": ["Major Rivers", "Flood Plains", "Monsoon Regions"]
  }
]
```

**Why:** Enables **cross-domain retrieval** in the blueprint. When sampling "Fluvial Processes," we can now pull not just "Climatology" but specifically "Rainfall Types" for linking, making questions more semantically coherent.

---

## Sub-Concepts: `linked_to` Field

### Previous (Sparse)
```json
"linked_to": ["Temperature Distribution"]
```

### Current (Expanded)
```json
"linked_to": ["Temperature Distribution", "Heat Budget", "Climate Classification", "Pressure Belts"]
```

**Why:** Each sub-concept's `linked_to` field should point to **3-5 related concepts** for richer linking in questions. Sparse lists (1-2) limit question diversity.

---

## Updated Concept Pool Schema (Summary)

```json
{
  "concepts": {
    "Primary Concept": {
      "priority": "high|medium|low|ultra_high",
      "frequency_in_pyq": 5,
      "tested_as_question_types": [
        "direct_fact",
        "assertion_reason",
        "multi_statement",
        "match_pair"
      ],
      "sub_concepts": [
        {
          "topic": "Specific topic",
          "aspects": ["aspect1", "aspect2"],
          "ca_connectable": true,
          "linked_to": [
            "Related Concept 1",
            "Related Concept 2",
            "Related Concept 3"
          ]
        }
      ],
      "links_to": [
        "Concept A",
        "Concept B",
        "Concept C",
        "Concept D"
      ],
      "interlink_domains": [
        {
          "domain": "Climatology",
          "concepts": [
            "Specific concept from climatology",
            "Another related concept"
          ]
        },
        {
          "domain": "Indian Geography",
          "concepts": [
            "Regional application"
          ]
        }
      ],
      "trap_affinity": [
        "GEO_T01",
        "GEO_T03",
        "GEO_T04"
      ]
    }
  }
}
```

---

## Pipeline Integration

### Stage 0: Blueprint (Concept Sampling)
1. Decide sampling strategy (borrowed, CA-linked, interlinked, pure)
2. Sample concept(s) based on target distribution
3. For each sampled concept, **check `tested_as_question_types`** to pick appropriate question format
4. Log the sampling decision and chosen format

### Stage 1-2: Generator (Question Creation)
1. Receive sampled concept + chosen question type
2. Look up `tested_as_question_types` again as **fallback** if format needs adjustment
3. Look up difficulty_type from `difficulty_types_geography_base.json`
4. Generate question following that template
5. Pull `trap_affinity` to select misconceptions for distractors

### Stage 3: Quality Gate (Validation)
1. Verify question structure matches difficulty_type blueprint
2. Verify traps are semantically sound (from trap_registry)
3. Check cross-domain linking coherence (if applicable)

---

## Future Improvements

1. **Track question type distribution:** Store actual distribution of question types tested per concept in recent PYQs, not just pre-defined.

2. **Trap effectiveness:** Tag each trap with effectiveness score (how often students fall for it) from assessment data.

3. **Cross-domain coherence score:** Rate how well interlinked concepts work together in questions (e.g., "Monsoon + IOD" = high coherence, "Monsoon + Periglacial" = low coherence).

4. **Sub-concept-level question types:** `tested_as_question_types` can also go at sub-concept level for finer-grained control.

5. **Difficulty type versioning:** If assessment data shows question structure preferences shift, version the difficulty types and weight by year.
