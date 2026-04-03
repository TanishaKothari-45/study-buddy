# Analyze-PYQ-Discovery Agent Specification

## Overview

**Agent Name:** `analyze-pyq-discovery`

**Type:** Background research & analysis agent

**Purpose:** Autonomously analyze UPSC Preliminary year questions (PYQs) for a given subject/domain, discover embedded concepts, identify patterns, and generate structured recommendations for concept pool updates and trap pattern refinements.

**Model:** Sonnet 4.6 (reasoning-heavy task)

---

## Role & Responsibilities

### Primary Responsibility
Analyze a set of PYQs (typically 20-40 questions from a specific subject across 5-10 years) and produce:

1. **Concept Discovery** — Extract all concepts tested, sub-concepts, linked concepts, frequency, and priority
2. **Question Type Analysis** — Classify each question by type (assertion_reason, multi_statement, match_pair, etc.)
3. **Trap Pattern Identification** — Identify misconceptions exploited in wrong answers
4. **Cross-Domain Linking** — Detect which other domains (climatology, Indian geography, etc.) appear with this domain
5. **Current Affairs Triggers** — Identify which concepts are CA-connectable based on PYQ evidence
6. **Recommendations** — Suggest concept pool updates, new traps, question generation tweaks

### Secondary Responsibilities
- Validate existing concept pools against PYQ evidence
- Suggest priority adjustments based on frequency
- Identify gaps in concept coverage
- Recommend new difficulty types if patterns emerge

---

## Inputs (Required & Optional)

### Required Inputs
```json
{
  "subject": "Geography",
  "domain": "Climatology",
  "pyq_file_path": "/path/to/climatology_pyqs_2015_2024.json",
  "num_questions": 35,
  "years": [2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024]
}
```

- **subject** — UPSC subject (Geography, History, Polity, Economy, etc.)
- **domain** — Sub-domain (Climatology, Geomorphology, Indian Geography, etc.)
- **pyq_file_path** — Path to JSON file containing extracted PYQs
- **num_questions** — Expected count (for sanity checking)
- **years** — Span of analysis

### Optional Inputs
```json
{
  "existing_concept_pool_path": "/path/to/geography_climatology.json",
  "existing_trap_registry_path": "/path/to/traps_climatology.json",
  "focus_areas": ["Monsoon", "ENSO", "Cyclones"],
  "validation_mode": true,
  "depth": "thorough"
}
```

- **existing_concept_pool_path** — To validate/update (not overwrite) existing pool
- **existing_trap_registry_path** — To map discovered traps to existing patterns or suggest new ones
- **focus_areas** — If provided, agent prioritizes analysis of these concepts
- **validation_mode** — If true, agent compares findings against existing pool and flags discrepancies
- **depth** — "quick" (20 min), "standard" (45 min), "thorough" (2 hrs)

---

## Outputs

### Structured Output Files (auto-generated in `config/research/{timestamp}_{domain}/`)

#### 1. **concepts_discovered_{domain}_{timestamp}.json**
```json
[
  {
    "Primary Concept": "Monsoon",
    "Sub-Concepts": [
      "Monsoon Onset",
      "Monsoon Withdrawal",
      "Monsoon Branches"
    ],
    "Frequency in Question": "very_high (7/35)",
    "Question Types Tested": ["assertion_reason", "multi_statement", "pure_ca"],
    "Linked Concepts": [
      "Jet Streams",
      "ITCZ",
      "ENSO",
      "Indian Ocean Dipole"
    ],
    "Linking Pattern": "same_domain, cross_domain_oceanography",
    "Current Affairs Events": [
      "2023 monsoon failure",
      "2022 early onset",
      "2015 weak monsoon"
    ],
    "CA Connectable": true,
    "Concept Category": "Core/frequently-tested",
    "Priority Suggestion": "ultra_high",
    "Evidence": "Appeared in 7 of 35 questions (2015-2024)"
  }
]
```

#### 2. **trap_patterns_discovered_{domain}_{timestamp}.json**
```json
{
  "discovered_patterns": [
    {
      "pattern_name": "Seasonal reversal in monsoon timing",
      "frequency_in_pyq": "15% (5/35 questions)",
      "mechanism": "Student assumes monsoon onset is same across India; actually varies by region",
      "affected_concepts": ["Monsoon", "Indian Geography"],
      "question_types": ["assertion_reason", "scenario"],
      "mapping_to_existing": "GEO_C_T02 (Seasonal reversal)",
      "evidence": ["2018 Q12", "2021 Q8", "2020 Q15"]
    }
  ]
}
```

#### 3. **recommendations_{domain}_{timestamp}.md**
```markdown
# Recommendations for {Domain}

## Pool Updates
- **Add Concepts:** List new concepts not in existing pool
- **Adjust Priority:** Which concepts should be ultra_high vs high
- **Missing Sub-Concepts:** Gaps between PYQ evidence and pool

## Trap Registry Updates
- **New/Unique Patterns:** Traps discovered in PYQs not covered in trap file
- **Variants of Existing Patterns:** How existing patterns manifest for this domain
- **Frequency Adjustments:** If a trap is rarer/more common than previously documented

## Question Generation Pipeline Changes
- **Difficulty Calculation:** Suggests adjustments based on observed difficulty distribution
- **Linking Strategy:** Which cross-domain links actually appear in PYQs
- **Trap Injection:** Recommendations on trap placement

## Architecture Implications
- **Recipe for Easy/Medium/Hard:** Suggests specific difficulty structures based on PYQ patterns
- **CA Integration:** How to weight CA-triggered questions

## Synthesis
- Actionable summary of changes
```

#### 4. **validation_report_{domain}_{timestamp}.json** (if validation_mode=true)
```json
{
  "comparison": {
    "concepts_in_pool_not_in_pyq": ["Concept A"],
    "concepts_in_pyq_not_in_pool": ["Concept B"],
    "priority_mismatches": [
      {
        "concept": "ENSO",
        "current_priority": "high",
        "suggested_priority": "ultra_high",
        "evidence": "Appeared in 6/35 questions"
      }
    ],
    "question_type_mismatches": [
      {
        "concept": "Jet Streams",
        "pool_claims": ["assertion_reason", "match_pair"],
        "actual_in_pyq": ["assertion_reason", "multi_statement", "direct_fact"],
        "missing_in_pool": ["multi_statement", "direct_fact"]
      }
    ]
  }
}
```

---

## When to Use This Agent

### ✅ Perfect Use Cases
1. **New subject/domain analysis** — First time analyzing a subject for question generation
2. **Periodic validation** — Every 1-2 years, re-analyze PYQs to catch trends and update pools
3. **Pattern discovery** — When existing concept pools feel outdated or incomplete
4. **Parallel batch analysis** — Launch agents for multiple domains simultaneously (e.g., Climatology + Geomorphology + Indian Geography in parallel)
5. **Gap analysis** — Identify concepts tested in PYQs but missing from pools

### ❌ Not Ideal For
1. **Single question analysis** — Use manual review instead
2. **Real-time question generation** — Agent is for offline analysis, not streaming
3. **Simple fact-checking** — Overkill; use grep/read tools instead
4. **Exploratory coding** — Use general-purpose agent instead

---

## Invocation Pattern

### Single Domain Analysis
```
User: "Analyze climatology PYQs (2015-2024) and update concept pool"

Claude Code:
Agent(
  subagent_type="analyze-pyq-discovery",
  description="Analyze Climatology PYQs and generate concept/trap recommendations",
  prompt="""
  Analyze UPSC Preliminary year questions for Geography > Climatology (2015-2024).

  Input:
  - PYQ file: backend/app/prelims_v2/pyqs_climatology_2015_2024.json
  - Existing pool: backend/app/prelims_v2/concept_pools/geography_climatology.json
  - Existing traps: backend/app/prelims_v2/traps_climatology.json

  Tasks:
  1. Extract all concepts tested in climatology questions
  2. Classify by frequency, priority, question type
  3. Identify trap patterns in wrong answers
  4. Compare against existing pool and suggest updates
  5. Generate recommendations markdown
  6. Output: 4 JSON files + markdown recommendations
  """
)
```

### Parallel Multi-Domain Analysis
```
User: "Analyze geography PYQs for all three subdomains in parallel"

Claude Code:
Agent(
  subagent_type="analyze-pyq-discovery",
  description="Analyze Climatology PYQs",
  prompt="[prompt for climatology]",
  run_in_background=true
)

Agent(
  subagent_type="analyze-pyq-discovery",
  description="Analyze Geomorphology PYQs",
  prompt="[prompt for geomorphology]",
  run_in_background=true
)

Agent(
  subagent_type="analyze-pyq-discovery",
  description="Analyze Indian Geography PYQs",
  prompt="[prompt for Indian geography]",
  run_in_background=true
)

# All run in parallel; results returned as separate files
```

---

## Agent Skill.md

See `skill_analyze_pyq_discovery.md` for detailed technical skill guide.

---

## Output Directory Structure

```
config/research/
├── 2026-04-03_1246_Geography_Climatology/
│   ├── concepts_discovered_Geography_Climatology_2026-04-03_1246.json
│   ├── trap_patterns_discovered_Geography_Climatology_2026-04-03_1246.json
│   ├── recommendations_Geography_Climatology_2026-04-03_1246.md
│   ├── validation_report_Geography_Climatology_2026-04-03_1246.json
│   └── pyq_input_summary.json (meta: how many Q's analyzed, year range, etc.)
├── 2026-04-03_1247_Geography_Geomorphology/
│   ├── [same 4 output files]
└── 2026-04-03_1248_Geography_Indian_Geography/
    ├── [same 4 output files]
```

---

## Example Workflow: 3-Domain Parallel Analysis

```
1. User runs: analyze_pyqs("geography", ["climatology", "geomorphology", "indian_geography"])

2. Claude launches 3 agents in parallel:
   - Agent 1: climatology (PYQ analysis)
   - Agent 2: geomorphology (PYQ analysis)
   - Agent 3: indian_geography (PYQ analysis)

3. Each agent independently:
   - Reads PYQ file
   - Extracts concepts, traps, patterns
   - Compares against existing pools
   - Generates outputs in dated directory

4. All complete (in ~45 mins standard depth):
   - config/research/2026-04-03_1246_*/ (climatology results)
   - config/research/2026-04-03_1247_*/ (geomorphology results)
   - config/research/2026-04-03_1248_*/ (indian_geography results)

5. User reviews all 3 recommendations in parallel
   - Decide which updates to apply
   - Integrate learnings across domains
```

---

## Key Advantages of This Agent Architecture

1. **Parallelizable** — Run 3+ domain analyses simultaneously without blocking
2. **Autonomous** — No intermediate prompts; agent works to completion
3. **Reproducible** — Dated outputs + metadata allow audit trail
4. **Integrable** — Output JSON directly feeds into concept pool + trap registry updates
5. **Validation-Aware** — Can compare against existing pools to catch drift
6. **Reasoning-Heavy** — Uses Sonnet 4.6 for complex pattern discovery

---

## Success Criteria

Agent has succeeded if:
- ✅ All 4 output files generated and well-formed JSON/Markdown
- ✅ Concepts extracted match manual spot-check of 5 random questions
- ✅ Trap patterns map to existing GEO_C_T* patterns or propose new ones
- ✅ Recommendations are actionable (e.g., "Add Concept X with priority high")
- ✅ Validation report identifies any priority/question-type mismatches

---

## Failure Modes & Mitigations

| Failure | Symptom | Mitigation |
|---------|---------|-----------|
| PYQ file malformed | JSON parse error | Agent validates input structure before analysis |
| Incomplete concept extraction | Recommendations miss >2 concepts | Manual spot-check against 10 PYQs; re-run if gap >10% |
| Trap pattern hallucination | Suggests trap pattern not in PYQs | Requires evidence citations (e.g., "Q12, Q18, Q25") |
| Validation mismatch | Pool & PYQ data diverged significantly | Flag for human review; do not auto-update pool |
