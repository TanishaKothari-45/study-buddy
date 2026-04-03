# Skill: /analyze-pyq-discovery

**Purpose**: Reverse-engineer question patterns from UPSC papers. Discovers concepts, traps, difficulty drivers, and patterns adaptively. Works across all subjects and domains.

**Type**: Prompt-based (Natural Language Analysis)

---

## Usage

```
/analyze-pyq-discovery --subject "Geography" --domain "Climatology" --years "2015-2024"
/analyze-pyq-discovery --subject "Polity" --domain "Constitutional Law" --papers "[paste data]"
/analyze-pyq-discovery --subject "History" --domain "Modern India" --years "2020-2024"
```

**Arguments:**
- `--subject`: Required (Geography, Polity, History, Economy, etc.)
- `--domain`: Optional (Climatology, Geomorphology, etc.). If omitted, analyzes entire subject.
- `--years`: Optional (default: "2015-2024"). Format: "2020-2024" or "2024"
- `--papers`: Optional. Paste actual question text. If omitted, skill searches web sources.
- `--output-format`: Optional (json, markdown, both). Default: both

---

## How It Works

### Step 1: Paper Collection

If `--papers` not provided, skill searches:
- superkalam.com
- clearias.com
- insightsonindia.com
- testbook.com
- iasnova.com

If `--papers` provided, skill uses that data directly.

### Step 2: Multi-Stage Analysis

Each stage uses a specialized prompt to discover patterns.

---

## Prompt 1: Concept & Sub-Concept Discovery

**Input**: Raw questions from papers

**Prompt**:
```
You are analyzing UPSC {subject} questions from {years}.

For EACH question provided, DO NOT classify into preset categories.
Instead, DISCOVER and extract:

1. **Primary Concept**: What is the main concept/topic being tested?
   (Examples: "Monsoon", "Atmospheric Radiation", "Land Reform", "British Economic Policy")

2. **Sub-Concepts**: Which specific sub-aspects of the concept are tested?
   (Examples for Monsoon: "Onset mechanism", "Withdrawal timing", "Forecasting models", "Below-normal rainfall")

3. **Concept Frequency in Question**: Is this concept mentioned once or multiple times?

4. **Linked Concepts**: Are other concepts mentioned/linked to the primary concept?
   (Examples: "Monsoon linked with Jet Streams")

5. **Linking Pattern**: How are concepts linked?
   - Same concept family (e.g., Monsoon + Rainfall Types = same domain)
   - Cross-domain (e.g., Monsoon + Agriculture)
   - Implicit (e.g., question assumes knowledge of linking)

6. **Current Affairs**: Is a recent event mentioned? What year?

7. **Concept Category**: Is this a:
   - Core/Frequently-tested concept
   - Niche/Rarely-tested concept
   - Supporting concept
   (You decide based on context)

Return as JSON array. Each object represents ONE question with all 7 fields.

IMPORTANT: Be conservative. Only extract what's explicitly stated in the question.

Questions:
{questions}
```

**Output**:
```json
[
  {
    "year": 2024,
    "primary_concept": "Atmospheric Radiation & Heat Transfer",
    "sub_concepts": ["Terrestrial radiation", "Greenhouse effect"],
    "frequency_in_question": 1,
    "linked_concepts": ["Temperature Distribution"],
    "linking_pattern": "same_domain",
    "ca_involved": false,
    "concept_category": "frequently_tested"
  }
]
```

---

## Prompt 2: Trap Pattern Reverse-Engineering

**Input**: Same questions + discovered concepts

**Prompt**:
```
You are a UPSC question design expert. Analyze how questions TRICK students.

For EACH question provided, reverse-engineer HOW the trap works.
DO NOT classify into preset trap names. Instead, DESCRIBE the mechanism.

For each question, extract:

1. **Question Type**: What is the format of this question?
   (Examples: "How many of the following...", "Consider the statements...",
   "Which one of the following...", "Match the pairs...", "Assertion-Reason")

   IMPORTANT: You are discovering question types, not matching preset ones.
   If you see a type not listed above, name it descriptively.

2. **Trap Mechanism**: HOW does this question trick students?
   (Describe the actual mechanism, not a pattern name)

   Examples:
   - "Student's prior belief is inverted: they think low clouds cool the atmosphere, but the correct answer is they warm it"
   - "Two metrics favor India (arable land, irrigation), one favors China (productivity). Student assumes India wins on all three."
   - "Correct concept (Alps are fold mountains), wrong detail (statement says 'block mountains'). Student knows the detail but paired with wrong concept."
   - "Recent news (greenfield airport) makes student focus on that, forgetting to verify the static geography fact."

3. **Error Type**: What kind of cognitive error does this induce?
   (Examples: counterintuitive_fact, metric_reversal, detail_mismatch, recency_bias,
   direction_reversal, location_confusion, causation_reversal)

4. **Distractor Strategy**: How are wrong answers made plausible?
   (Examples: "uses the student's intuitive but wrong answer",
   "uses a real geographic feature but paired with wrong concept",
   "uses a recent news event to create recency bias")

5. **Difficulty Level**: easy | medium | hard

6. **Difficulty Type** (CRITICAL - specific category for diverse question generation):

   **EASY types:**
   - `easy_recall_static`: Pure fact recall (e.g., "Longest river in India?")
   - `easy_ca_trigger`: Recent event triggers a well-known static fact
   - `easy_reverse_mild`: Counterintuitive but widely taught (e.g., "Canada-US is longest border")

   **MEDIUM types:**
   - `medium_concept_linking_same_domain`: 2 concepts from same domain linked (e.g., Monsoon + Jet Streams)
   - `medium_statistical_reversal`: 2 metrics favor A, 1 favors B; reversed metric is the trap
   - `medium_adjacent_fact`: Correct concept, wrong detail (location, name, pairing)
   - `medium_ca_integration`: CA event + static geography tested together
   - `medium_precision_location`: Requires knowledge of specific boundaries/locations

   **HARD types:**
   - `hard_counterintuitive_single_concept`: Single concept tested in counterintuitive direction
   - `hard_cross_domain_linking`: 2-3 concepts from different domains; linking is answer
   - `hard_all_of_above_precision`: 3-4 statements; one has subtle error (direction/metric/name)
   - `hard_strong_concept_depth`: Concept requires deep understanding, not definition
   - `hard_spatial_sequence`: West-to-east, latitude gradients; map-level knowledge
   - `hard_reverse_extreme`: Correct answer strongly violates intuition

   **PURE_CA types:**
   - `pure_ca_news_tracking`: Tests news following (easy-medium)
   - `pure_ca_recent_event`: Recent event is the question itself (easy-medium)

7. **Difficulty Explanation**: Why this specific difficulty type?

Return as JSON array. One object per question.

Questions:
{questions}
```

**Output**:
```json
[
  {
    "year": 2024,
    "question_type": "multi_statement",
    "trap_mechanism": "Student's intuition: low clouds cool the atmosphere. Correct answer: they warm it.",
    "error_type": "counterintuitive_fact",
    "distractor_strategy": "makes student's wrong intuition available as option",
    "difficulty": "hard",
    "difficulty_type": "hard_counterintuitive_single_concept",
    "difficulty_explanation": "Single concept (cloud radiation), counterintuitive property (warming not cooling), violates strong student assumption"
  },
  {
    "year": 2023,
    "question_type": "match_pair",
    "trap_mechanism": "Correct concept, but adjacent wrong detail in one pair",
    "error_type": "adjacent_fact_confusion",
    "distractor_strategy": "related but incorrect geographic pairing",
    "difficulty": "medium",
    "difficulty_type": "medium_adjacent_fact",
    "difficulty_explanation": "Requires precise knowledge of pairings; one nearly-correct detail"
  }
]
```

---

## Prompt 3: Synthesis - Aggregate & Flag New Patterns

**Input**: Output from Prompts 1 & 2

**Prompt**:
```
You have analyzed {total_questions} UPSC {subject} questions across {years}.

Aggregate the data into insights. Focus on:

1. **Concept Frequency & Gaps**
   - Which concepts appear most? How often?
   - Which sub-concepts are tested within each concept?
   - Are there concepts in the subject but never tested?
   - What sub-concepts appear but might not be in a standard pool?

2. **Question Type Distribution**
   - List all question types found (not preset ones, but what you observed)
   - Frequency of each type
   - Which types appear in which difficulty levels?
   - NEW types not typically seen in other subjects?

3. **Trap Pattern Aggregation**
   - Group similar trap mechanisms under pattern names
   - Frequency of each pattern
   - Which patterns appear by question type? By difficulty?
   - NEW patterns never seen before in this subject?

4. **Difficulty Type Distribution**
   - Which difficulty types appear most? (easy_recall_static, medium_concept_linking, hard_counterintuitive, etc.)
   - Frequency of each type by question type and concept
   - Are there new difficulty types unique to this domain/subject?
   - How does diversity of hard/medium/easy types compare to Climatology?

5. **Difficulty Drivers** (Meta-analysis)
   - What makes questions easy in this subject? (Pure recall? CA triggers? Mild reversals?)
   - What makes questions medium? (Linking? Precision errors? CA integration?)
   - What makes questions hard? (Counterintuitive facts? Cross-domain? Precision in all-of-above?)
   - Are the drivers different from Climatology or other subjects?

6. **Concept Linking Patterns**
   - % of questions testing single concept only
   - % testing 2 concepts (same domain vs cross-domain)
   - % testing 3+ concepts
   - How does this vary by difficulty type?

7. **NEW DISCOVERIES**
   - Patterns never seen before?
   - Question types unique to this subject/domain?
   - Difficulty drivers that are domain-specific?
   - Concepts that should be in the pool but are missing?
   - Traps that need to be added to the registry?

Return as structured JSON with all 6 sections.

Analyzed Data:
{aggregated_data}
```

**Output**: Comprehensive JSON with all findings

---

## Prompt 4: Recommendations & Context

**Input**: Output from Prompt 3

**Prompt**:
```
Based on the analysis, provide recommendations for:

1. **Pool Updates** (for climatology.json equivalent)
   - Which concepts should be added?
   - Which should have priority adjusted?
   - Which sub-concepts are missing?

2. **Trap Registry Updates** (for traps_geography.json equivalent)
   - Which trap patterns should be added/clarified?
   - Which are new and unique to this subject?
   - Which are variants of existing traps?

3. **Question Generation Pipeline Changes**
   - Should difficulty be calculated differently?
   - Should linking strategy change?
   - Should trap injection strategy change?

4. **Architecture Implications**
   - Does hard = complex linking? Or something else?
   - What's the actual recipe for easy/medium/hard?
   - How should CA be integrated?

Provide bullet-point recommendations with rationale.

Analysis:
{synthesis_output}
```

---

## Output Files (Timestamped)

Skill saves to: `config/research/{timestamp}/`

**Files generated:**
1. `concepts_discovered_{subject}_{timestamp}.json`
   - Concept frequency, sub-concepts, gaps

2. `question_types_discovered_{subject}_{timestamp}.json`
   - Question type distribution, by difficulty/concept

3. `trap_patterns_discovered_{subject}_{timestamp}.json`
   - Trap patterns, frequency, by question type/difficulty

4. `difficulty_drivers_{subject}_{timestamp}.json`
   - What makes easy/medium/hard questions

5. `complete_research_{subject}_{domain}_{timestamp}.json`
   - All findings consolidated

6. `recommendations_{subject}_{timestamp}.md`
   - Actionable recommendations in readable format

---

## How to Use Results

**For Pool Updates** (geomorphology.json, etc.):
- Read `concepts_discovered_*.json`
- Add missing sub-concepts
- Adjust priorities based on frequency

**For Trap Updates** (traps_geography.json):
- Read `trap_patterns_discovered_*.json`
- Add new patterns with examples
- Consolidate variants

**For Difficulty Type Registry** (NEW):
- Read `difficulty_drivers_*.json`
- Extract difficulty types used in domain
- Create registry: `geomorphology_difficulty_types.json` with:
  ```json
  {
    "hard": [
      "hard_counterintuitive_single_concept",
      "hard_reverse_extreme",
      "hard_strong_concept_depth"
    ],
    "medium": [
      "medium_concept_linking_same_domain",
      "medium_adjacent_fact",
      "medium_precision_location"
    ],
    "easy": [
      "easy_recall_static",
      "easy_reverse_mild"
    ]
  }
  ```

**For Blueprint Stage 0 Changes** (KEY):
- Instead of: `difficulty = "hard"` → pick random trap
- Now: `difficulty_type = random_choice(["hard_counterintuitive_single_concept", "hard_spatial_sequence"])`
  - Then select traps + linking + retrieval queries specific to that type
- This generates **diverse hard questions** (not all the same structure)
- Result: Questions closer to actual UPSC variety

**For Question Generation Diversity**:
- Hard questions should mix:
  - 40% `hard_counterintuitive_single_concept`
  - 30% `hard_spatial_sequence` or `hard_reverse_extreme`
  - 20% `hard_cross_domain_linking`
  - 10% `hard_all_of_above_precision`
- Medium questions should mix:
  - 40% `medium_concept_linking_same_domain`
  - 30% `medium_adjacent_fact` or `medium_precision_location`
  - 30% `medium_statistical_reversal` or `medium_ca_integration`
- Easy questions should mix:
  - 60% `easy_recall_static`
  - 30% `easy_ca_trigger`
  - 10% `easy_reverse_mild`

---

## Key Principles

✅ **Discovery-based**: Opens-ended analysis, not classification into presets
✅ **Subject-adaptive**: Works for Geography, Polity, History, etc.
✅ **Domain-specific**: Can identify patterns unique to subdomains
✅ **New pattern detection**: Flags patterns never seen before
✅ **Consolidated output**: Single subject-level trap registry with examples from multiple domains
✅ **Timestamped history**: Keeps record of all analyses for comparison

---

## Example Workflow

```
User: /analyze-pyq-discovery --subject "Geography" --domain "Climatology" --years "2015-2024"

Skill:
1. Fetches 10 years of Climatology questions from 5 sources
2. Runs Concept Discovery prompt → extracts concepts/sub-concepts
3. Runs Trap Pattern prompt → reverse-engineers mechanisms
4. Runs Synthesis prompt → aggregates findings
5. Runs Recommendations prompt → provides actionable insights
6. Saves 6 timestamped JSON/MD files
7. Returns summary to user

Output: "Analysis complete. Found 15 core concepts, 6 trap patterns,
new pattern discovered: 'Latitudinal Confusion'. Files saved to config/research/2026-04-03_1530/"
```

---

## Running on Geomorphology: What to Expect

When we run: `/analyze-pyq-discovery --subject "Geography" --domain "Geomorphology" --years "2015-2024"`

We'll get insights like:

**Concepts:**
- Which concepts are tested in Geomorphology (Rivers, Valleys, Mountains, Plateaus, etc.)
- Sub-concepts (river patterns, drainage, erosion, etc.)
- Frequency vs Climatology

**Traps:**
- Will "Reverse obvious" appear (probably yes, like "river flows NORTH not south")
- New traps unique to Geomorphology? (e.g., "spatial location confusion", "geologic time scale misunderstanding")
- Different trap frequencies than Climatology

**Question Types:**
- Will Geomorphology have more "match_pair" (geography location questions)?
- Fewer "how_many"?
- New question types?

**Difficulty Types:**
- Will hard = "spatial_sequence" more than "counterintuitive"?
- Will CA be less involved (lower ca_trigger rate)?
- What makes Geomorphology hard vs medium?

**Quality Check:**
- Do concepts_discovered + traps_discovered + difficulty_types form a coherent system?
- Can we generate diverse Geomorphology questions using these?

---

## Testing Checklist

- [ ] Works with Geography Climatology (known domain)
- [ ] Discovers new patterns not in traps_geography.json
- [ ] Identifies missing sub-concepts vs current pool
- [ ] Recommends pool/trap updates
- [ ] Outputs match expected structure
- [ ] Works with manual `--papers` input
- [ ] Works with web fetching
- [ ] **RUN ON GEOMORPHOLOGY** (next test) ← 🎯 NEXT STEP
- [ ] Compares Geomorphology vs Climatology findings
- [ ] Difficulty types are distinct and meaningful
- [ ] Can generate diverse questions from difficulty type registry
- [ ] Replicable across other Geography sub-domains
- [ ] Replicable across other subjects (Polity, History, Economy)
