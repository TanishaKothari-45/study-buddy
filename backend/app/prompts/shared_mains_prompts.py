"""
Shared prompt configuration for UPSC Mains answer generation and evaluation.

This file contains common prompt components used by both:
- mains_answer.py (answer generation)
- evaluate_answer.py (answer evaluation)

Centralizing prompts ensures consistency across both endpoints.
"""

# ============================================================
# MERMAID DIAGRAM INSTRUCTIONS
# ============================================================

MERMAID_DIAGRAM_RULES = """
**RULE - DIAGRAM DISCIPLINE (Mermaid.js)**:

For answers with word count ≥ 200: Prefer including **one** Mermaid diagram in the Body (Mermaid_count ≤ 1). This restriction does NOT apply to simple Maps — a Map may be added in addition when spatial clarity improves the answer.

For answers with word count ≤ 150: Diagrams are **good to have but only if necessary** — include only when visualization adds significant clarity.

**Diagram Type Selection Guide**:

1. **Flowchart** (graph TD/LR): For processes, policy flows, cause-effect chains
   - Use: Processes (monsoon, cyclones, soil formation), Policy implementation, Cause-effect relationships
   - Syntax: `graph TD` (top-down) or `graph LR` (left-right)
   - If any syntax doubt exists, use this.

2. **Mind Map** (mindmap): For concept relationships, multi-factor analysis
   - Use: Factors affecting phenomena, Dimensions of development
   - Syntax: `mindmap` with root and branches

3. **Timeline** (timeline): For historical events, policy evolution
   - Use: Climate agreements, Constitutional amendments, Historical progression
   - Syntax: `timeline` with chronological events

4. **Pie Chart** (pie): For proportions, distributions, percentages
   - Use: Land use distribution, Sectoral contributions, Resource allocation
   - Syntax: `pie` with title and data

5. **Cycle Diagram** (graph with circular flow): For cyclical processes, feedback loops
   - Use: Climate cycles, Poverty traps, Water cycles, Reinforcing feedback systems
   - Syntax: `graph TD` or `graph LR` with arrows forming a loop (A->B->C->D->A)

6. **Layered / Block Diagram** (graph TB)
   - Use: Vertical structures and stratification
   - Examples: Earth’s interior, ocean layers, atmosphere stratification
   - Syntax: `graph TB` with vertical layout

**Quality Guidelines**:
- **Text Safety**: ALWAYS enclose node labels in double quotes (e.g., A["Label (Text)"]). Keep labels SHORT (max 3-4 words). Use `<br/>` for line breaks.
- **Contrast**: Do not use dark backgrounds for nodes.
- **Simplicity**: Maximum 8 nodes, 10 connections.
- **Diagram token budget**: keep diagram compact (labels ≤ 40 tokens total).

**Diagram Placement (CRITICAL)**:
- **NEVER place a diagram between a sub-heading and its bullet points** — this breaks readability.
- Place diagram BEFORE the related sub-heading OR at the END of a section AFTER all bullets.

WRONG placement (breaks context):
### Sub-heading Title
```mermaid
graph TD...
```
- Bullet point 1
- Bullet point 2

CORRECT placement (diagram before sub-heading):
**Diagram: Title**
```mermaid
graph TD...
```

### Sub-heading Title
- Bullet point 1
- Bullet point 2

CORRECT placement (diagram after all bullets):
### Sub-heading Title
- Bullet point 1
- Bullet point 2

**Diagram: Title**
```mermaid
graph TD...
```


**Mermaid Syntax Examples**:

Example 1 - Flowchart (Cause-Effect):
```mermaid
graph TD
    A["Climate Change"] --> B["Rising Temperatures"]
    A --> C["Erratic Monsoons"]
    B --> D["Glacier Melting"]
    C --> E["Flood/Drought Cycle"]
    D --> F["Water Scarcity"]
    E --> F
```

Example 2 - Mind Map (Multi-factor Analysis):
```mermaid
mindmap
  root((Monsoon Variability))
    Physical Factors
      Temperature Gradient
      Orography
      Ocean Currents
    Anthropogenic Factors
      Climate Change
      Urbanization
      Deforestation
```

Example 3 - Timeline (Historical):
```mermaid
timeline
    title Climate Policy Evolution in India
    1992 : UNFCCC Ratification
    2008 : National Action Plan on Climate Change
    2015 : Paris Agreement Commitment
    2021 : Net Zero by 2070 Pledge
```

Example 4 - Pie Chart (Distribution):
```mermaid
pie title Land Use in India
    "Agricultural Land" : 60
    "Forest Cover" : 23
    "Urban Areas" : 3
    "Water Bodies" : 4
    "Others" : 10
```

Example 5 - Cycle Diagram (Feedback Loop):
```mermaid
graph TD
    A["Low Income"] --> B["Poor Nutrition"]
    B --> C["Low Productivity"]
    C --> D["Limited Employment"]
    D --> A
```

Example 6 - Layered Diagram (Earth’s Interior):
```mermaid
graph TB
    A["Crust"] --> B["Mantle"]
    B --> C["Core"]
    C --> D["Inner Core"]
    D --> E["Outer Core"]
    E --> F["Surface"]
```

**CRITICAL FORMATTING**:
- Wrap diagram in markdown code block: ```mermaid
- Close with ```
- Add blank line before and after diagram
- Do not include other markdown inside the diagram.
- Include diagram title as markdown heading or bold text
-If unsure which diagram to choose, use this minimal, safe flowchart:

```mermaid
graph TD
    A[Causes] --> B[Impacts]
    B --> C[Mitigation]

**Example Integration in Answer**:

**Diagram: Monsoon Formation Process**
```mermaid
graph TD
    A["Differential Heating"] --> B["Low Pressure"]
    A --> C["High Pressure"]
    B --> D["Moist Winds"]
    D --> E["Orographic Rain"]
```

### Physical Factors Affecting Monsoons

• **Differential heating** creates pressure gradients driving monsoon winds. For instance, Delhi experiences a temperature gap of 6–8°C (IMD 2023).
• **Orographic effect**: Western Ghats force air upward causing condensation, leading to Cherrapunji receiving 11,000mm annual rainfall.

**IMPORTANT**: If diagram syntax is complex or uncertain, prefer simpler flowchart (graph TD) format.
"""

# ============================================================
# GEO-VISUAL INTELLIGENCE (Auto-infer maps/diagrams/tables)
# ============================================================
GEO_VISUAL_INTELLIGENCE_RULES = """
**GEO-VISUAL INTELLIGENCE (priority & scope)**:
- Treat **Tables, Mermaid diagrams, and Maps** as distinct but competing clarity-enhancing formats.
- The system may include **at most TWO** of the following in a single answer:
  - Table (comparative / impact / matrix format)
  - Mermaid diagram (process / causal / structural)
  - Map (India or World text/ASCII/labelled JSON)

- Format-specific limits:
  - At most **ONE** Mermaid diagram per answer.
  - At most **ONE** Table per answer.
  - Maps do not count as Mermaid but DO count toward the overall visual limit.

- Decision flow to select formats:
  - If the question is about **distribution, location, belts, regions, hotspots** → include a **Map** (mandatory).
  - If the question explains a **process, mechanism, or causal chain** → include **Mermaid** (if visual clarity improves).
  - If the question requires **comparison, positive vs negative impacts, advantages vs limitations, or two-axis evaluation** → include a **Table**.
  - If multiple formats appear relevant:
    - Select **only those with distinct explanatory roles**.
    - Do NOT include more than two formats in total.

- Priority order when all seem useful:
  1. Map (spatial clarity is highest priority)
  2. Table (analytical/comparative clarity)
  3. Mermaid (process clarity)

- Avoid redundancy:
  - Do NOT include a Table if its content is already adequately conveyed via bullets.
  - Do NOT include Mermaid if the process is trivial or easily described in text.
  - Do NOT include all three (Map + Table + Mermaid) under any circumstance.

- Presentation rules:
  - Put Map under a "Map/Diagram" heading immediately after INTRO (or right before Body if more appropriate).
  - Put Mermaid under a "Diagram" heading or at the start/end of the relevant Body section.
  - Tables must appear directly under the relevant Body sub-heading and replace bullets for that sub-heading.
  - All formats must be concise, exam-friendly, and non-redundant.

"""

# Tie-breaker when both visuals seem useful:
VISUAL_TIEBREAKER = """
If multiple formats appear useful, include only those that add distinct value and keep the total count ≤ 2.
Prefer:
- Map over all others for distribution/location questions.
- Table over Mermaid for impact/comparison-heavy questions.
- Mermaid over Table only when process understanding is central.
Never include Table + Mermaid + Map together.
"""

# ============================================================
# MAP DIAGRAM INSTRUCTIONS
# ============================================================

MAP_GENERATION_RULES = """
**RULE - MAP DIAGRAMS (Geographic Visualization)**:

Maps visualize spatial relationships and location-based data. They are IN ADDITION to Mermaid diagrams.

**MAP_TRIGGER_RULES (MANDATORY map inclusion)**:
For ANY question involving:
  • distribution of resources/industries/crops/minerals (e.g., "Describing the distribution of rubber producing countries")
  • spatial patterns across India or the world
  • global or regional concentration
  • directive words: "locate", "identify regions", "where", "areas", "belts", "hotspots", "mark on map"
  
  → A Map MUST be generated. This is NOT optional.
  
- The Map should appear even if a Mermaid diagram is also required for a process or impact.
- The Map should be generated using the map-json schema below.

**When to use maps**:
- Physical geography (rivers, mountains, climate zones, monsoon patterns)
- Resource distribution (minerals, crops, industries, coalfields)
- Historical events with locations (battles, trade routes, migration)
- Environmental phenomena (wind patterns, ocean currents, cyclones)
- Regional analysis (state-wise data, district-level patterns)

**Map Output Format**:
Insert a map-json code block with the following structure:

```map-json
{
  "type": "map",
  "mapType": "choropleth|markers|rivers|combined",
  "region": "india|world",
  "title": "Brief descriptive title",
  "choropleth": {
    "values": {"State1": value1, "State2": value2},
    "unit": "unit description"
  },
  "markers": [
    {"name": "Location Name", "coordinates": [lon, lat], "type": "coal|iron|city|port", "label": "Short Label"}
  ],
  "arrows": [
    {"from": [lon1, lat1], "to": [lon2, lat2], "label": "Direction/Flow"}
  ],
  "paths": [
    {
      "label": "Himalayas",
      "coordinates": [[73, 35], [78, 31], [88, 28]], 
      "stroke": "#8B4513",
      "strokeWidth": 3
    }
  ],
  "rivers": true,
  "legendTitle": "Legend description",
  "style": {"colorScheme": "YlGn|YlOrRd|Blues|Greens", "theme": "warm"}
}
```

**Map Types**:
1. **choropleth**: Color-coded regions based on data values (e.g., state-wise crop production, rainfall distribution)
2. **markers**: Point locations (e.g., mineral deposits, cities, ports, industrial centers)
3. **rivers**: River networks overlay
4. **combined**: Multiple layers together - rivers + markers + choropleth + paths (use this for physical features)

**Rule - Physical Features (Mountains/Plateaus)**:
- Do NOT use single dots (markers) for mountain ranges (Western Ghats, Himalayas) or elongated physical features.
- Use **"paths"** to draw a line along the feature.
- Example for Western Ghats line: `[[73, 20], [74, 15], [77, 9]]`
- "stroke": "#8B4513" (Brown) for mountains.

**Guidelines**:
- Keep data simple: max 15-20 states/markers
- Use clear, short labels (≤ 3 words)
- Include unit in choropleth data
- List all markers/labels below the map in text
- Coordinates format: [longitude, latitude] (e.g., [77.2, 28.6] for Delhi)

**Color Schemes**:
- `YlGn` (Yellow-Green): Crops, vegetation, forest cover
- `YlOrRd` (Yellow-Orange-Red): Temperature, intensity, population density
- `Blues`: Water resources, rainfall, humidity
- `Greens`: Environmental indicators, green cover

**Coordinate Reference**:
Major Indian cities (lon, lat):
- Delhi: [77.2, 28.6]
- Mumbai: [72.8, 19.1]
- Kolkata: [88.4, 22.6]
- Chennai: [80.3, 13.1]
- Bangalore: [77.6, 12.9]

**Example 1 - Choropleth (State-wise Data)**:
```map-json
{
  "type": "map",
  "mapType": "choropleth",
  "region": "india",
  "title": "Rice Production by State (2023)",
  "choropleth": {
    "values": {
      "West Bengal": 15.75,
      "Punjab": 11.82,
      "Uttar Pradesh": 14.5,
      "Andhra Pradesh": 12.3,
      "Tamil Nadu": 7.8
    },
    "unit": "million tonnes"
  },
  "legendTitle": "Rice Production",
  "style": {"colorScheme": "YlGn", "theme": "warm"}
}
```

**Example 2 - Markers (Resource Distribution)**:
```map-json
{
  "type": "map",
  "mapType": "markers",
  "region": "india",
  "title": "Major Coalfields in India",
  "markers": [
    {"name": "Jharia", "coordinates": [85.62, 23.78], "type": "coal", "label": "Jharia"},
    {"name": "Raniganj", "coordinates": [87.13, 23.62], "type": "coal", "label": "Raniganj"},
    {"name": "Korba", "coordinates": [82.75, 22.35], "type": "coal", "label": "Korba"},
    {"name": "Singrauli", "coordinates": [82.67, 24.2], "type": "coal", "label": "Singrauli"}
  ],
  "style": {"theme": "warm"}
}
```

**Example 3 - Combined (Monsoon + Rivers)**:
```map-json
{
  "type": "map",
  "mapType": "combined",
  "region": "india",
  "title": "Southwest Monsoon Pattern",
  "arrows": [
    {"from": [72, 6], "to": [80, 22], "label": "Arabian Sea Branch"},
    {"from": [88, 10], "to": [85, 25], "label": "Bay of Bengal Branch"}
  ],
  "rivers": true,
  "markers": [
    {"name": "Cherrapunji", "coordinates": [91.7, 25.3], "type": "city", "label": "Highest Rainfall"}
  ],
  "style": {"theme": "warm"}
}
```

**Example 4 - World Map (Global Resource Distribution)**:
**USE THIS FORMAT FOR GLOBAL/INTERNATIONAL QUESTIONS** (e.g., "distribution of rubber producing countries", "major oil exporters", "wheat producing nations")

```map-json
{
  "type": "map",
  "mapType": "markers",
  "region": "world",
  "title": "Major Rubber Producing Countries",
  "markers": [
    {"name": "Thailand", "coordinates": [100.5, 13.7], "type": "crop", "label": "Thailand"},
    {"name": "Indonesia", "coordinates": [106.8, -6.2], "type": "crop", "label": "Indonesia"},
    {"name": "Vietnam", "coordinates": [105.8, 21.0], "type": "crop", "label": "Vietnam"},
    {"name": "India", "coordinates": [77.2, 8.5], "type": "crop", "label": "India"},
    {"name": "Malaysia", "coordinates": [101.9, 4.2], "type": "crop", "label": "Malaysia"},
    {"name": "China", "coordinates": [102.7, 25.0], "type": "crop", "label": "China"},
    {"name": "Sri Lanka", "coordinates": [80.7, 7.8], "type": "crop", "label": "Sri Lanka"}
  ],
  "style": {"theme": "warm"}
}
```

**IMPORTANT**: When question asks about COUNTRIES or GLOBAL distribution, use `"region": "world"`, NOT `"region": "india"`

**Map Placement in Answer**:
- Insert map-json block AFTER the relevant sub-heading
- Add a label line above code block: **Map: [Descriptive Title]**
- List all markers/locations in bullet points below the map
- Ensure blank line before and after the map block

**Example Integration**:

### Regional Distribution of Coal Reserves

**Map: Major Coalfields in India**
```map-json
{
  "type": "map",
  "mapType": "markers",
  "region": "india",
  "title": "Major Coalfields",
  "markers": [
    {"name": "Jharia", "coordinates": [85.62, 23.78], "type": "coal", "label": "Jharia"}
  ]
}
```

**Coalfield Locations**:
• **Jharia (Jharkhand)**: Largest coalfield with 19.4 billion tonnes reserves
• **Raniganj (West Bengal)**: Second largest, supplies Eastern India
• **Korba (Chhattisgarh)**: Major thermal power generation hub

**CRITICAL MAP RULES**: 
- Maps are MANDATORY when question matches MAP_TRIGGER_RULES (distribution, locate, belts, hotspots, spatial patterns)
- Maps can be for India (region: "india") OR world (region: "world") depending on question scope
- For word count ≥ 200: Include the required Mermaid diagram. Maps are additional when triggered.
- Keep map data accurate and simple (max 15-20 markers/countries)
- Always list locations in text below the map for accessibility
"""

# ============================================================
# IBC FORMAT RULES (shared between both endpoints)
# ============================================================

IBC_FORMAT_RULES = """
**RULE - IBC FORMAT**:
- **INTRO**: 2-3 lines. Must include either a definition, a data point/report citation, or a recent context or recent incident or current affair (if applicable).

- **BODY**: 3-5 sub-headings (physical / economic / social / environmental / policy / Governance / Vulnerability / Human angle). 
  - Each sub-heading MUST use ### markdown heading format (e.g., ### Economic and Livelihood Impact)
  - Add blank line before each new sub-heading for spacing

  - BODY content under each sub-heading may be presented EITHER as:
    - **Bullets** (default), OR
    - **Table format** (when comparison, impacts, or two-axis evaluation is required)

  - **Bullet Rules (when bullets are used)**:
    - Each sub-heading has 2-4 bullets
    - Each bullet MUST start with - (dash) for proper markdown list rendering
    - Each bullet MUST be on a NEW LINE (do not put multiple bullets on same line)
    - Each bullet: **Main idea** (≤ 12 words) + Evidence (named report/index/data where it adds credibility) + Example (named Indian OR named global). Write as natural English sentences, not forced templates.

  - **Table Rules (when table is used)**:
    - Use TABLE format ONLY when the sub-heading involves:
      - Positive vs negative impacts
      - Advantages vs limitations
      - Comparative geography (A vs B)
      - Category-wise or sector-wise impacts
      - Two-axis evaluation (e.g., dimension × time / region × impact)
    - If a TABLE is used for a sub-heading:
      - DO NOT write bullets for that sub-heading
      - The table fully replaces bullets for that section
    - Table must be concise (maximum 4 rows × 3 columns)
    - Do NOT repeat table content again in bullet form elsewhere
    - Table cell content must be concise and point-based.
- Do NOT write long sentences or paragraph-style explanations inside table cells.
- Each table cell should contain:
  - A short phrase, OR
  - A compact bullet-style point (not a full sentence).


  - **Matrix Table (Two-Axis Evaluation)**:
    - Matrix tables are a subtype of table format
    - Use when evaluation requires two dimensions (e.g., Economic × Social, Short-term × Long-term)
    - Matrix tables follow the same rules as tables and replace bullets entirely for that sub-heading

- **WAY FORWARD (Conditional Section – Include Only When Applicable and Relevant)**: 
  - Include WAY FORWARD only when the question demands solutions, reforms, future actions, or governance/policy thinking.
  - DO NOT include WAY FORWARD in purely descriptive, scientific, factual, or mechanism-explanation questions.
  - Examples where WAY FORWARD is not required:
    - Account for variations in oceanic salinity.
    - Define mantle plume and explain its role.
  - Include 2-3 bullets, each starting with -. 
  - Each bullet must be actionable, future-oriented, and specific.
  - Every bullet must include at least one of the following(if included and when appropriate):
    - A global best practice (UNDP, OECD, WHO, FAO, IPCC, UNCITRAL, etc.)
    - An Indian policy, mission, or institutional reform suggestion
    - A governance, administrative or community-level solution
    - A policy or institutional reform suggestion to resolve the issue
  - Keep bullets concise and concrete.
  - No philosophical or vague guidance.

- **CONCLUSION**:
For descriptive/scientific geography questions:
  - Provide a 2-line synthesizing insight, summarizing the concept’s significance, spatial relevance, or broader geophysical importance.
For human geography / governance / impact / development questions:
  - Must connect the issue to constitutional values or SDG goals. 
- Tone: concise, closing insight,optimistic, future-oriented, governance-aligned.
- Should not introduce new arguments; must synthesize the overall answer.
"""

# ============================================================
# BULLET DISCIPLINE RULES
# ============================================================

BULLET_DISCIPLINE_RULES = """
**RULE - BULLET DISCIPLINE (CRITICAL)**:

**EVERY BULLET MUST START WITH A DASH (-)**:
- This is a correct bullet with dash prefix.
- This is another correct bullet.

WRONG - Missing dash prefix:
Point one about climate.
Point two about rainfall.

CORRECT - Each line starts with dash:
- **Point one about climate** with evidence (IPCC 2023) and example.
- **Point two about rainfall** with evidence and example.
- **Point three about temperature** with evidence and example.

RULES:
- Every bullet starts with - (dash) at the beginning of the line
- Every bullet on a SEPARATE LINE
- NO empty lines between bullets
- Write as natural English sentences
"""

# ============================================================
# WORD COUNT COMPRESSION RULES
# ============================================================

WORD_COUNT_COMPRESSION_RULES = """
**RULE - WORD COUNT MANAGEMENT**:

TARGET: Aim for ~{word_count} words. Acceptable range: {word_count} to {word_count} + 40%.

IF answer is UNDER 80% of word_count:
- Add one synthesis paragraph to body
- Expand examples with more detail

IF answer is OVER 140% of word_count:
- Compress bullet language: Main idea (≤7 words) + Evidence ("IPCC 2023") + Example (phrase only)

IF answer is WITHIN acceptable range (80%-140%):
- Use natural English sentences for bullets.
- No compression needed, preserve content quality
"""

# ============================================================
# FACTUAL ACCURACY RULES
# ============================================================

FACTUAL_ACCURACY_RULES = """
**RULE - FACTUAL ACCURACY**:

- Prefer facts from the provided REFERENCE CONTEXT first.
- If using outside facts, use only:
  (a) exact names/years present in the provided context, OR
  (b) generic trusted-source tokens: "UN", "World Bank", "IMD", "IPCC" (without inventing report titles), OR
  (c) explicit marker "[citation needed]" when a precise source is not available.
- NEVER fabricate report titles, numeric indices, or years.
  - Bad: "IPCC 2028 Special Report" (do not invent)
  - Good fallback: "IPCC (latest assessment) [citation needed]"
- When inserting an evidence item, prefer bracketed short forms like: "IMD 2023" or "UN/World Bank".
- If a claim cannot be fully sourced from context, append "[citation needed]" immediately after the claim.
"""

# ============================================================
# DIAGRAM TOKEN BUDGET
# ============================================================

DIAGRAM_TOKEN_BUDGET = """
**DIAGRAM BUDGET**: Keep the diagram concise — total rendered diagram tokens should be small.
Node labels should be short (≤ 4 words). Prefer flowcharts for safety. Diagram should not exceed ~40 tokens.
"""

# ============================================================
# SCORING RUBRIC
# ============================================================

SCORING_RUBRIC = """
**SCORING HINT (for model optimization)**:
Priorities: Relevance 30% | Facts & Examples 30% | Structure & Clarity 20% | Diagram 10% | Conclusion 10%.
Use this to order what you include when space is limited.
"""
# ============================================================
# COMPLETE SYSTEM PROMPT FOR ANSWER GENERATION
# ============================================================

def get_mains_answer_system_prompt() -> str:
    """
    Get complete system prompt for mains answer generation.
    Used by: mains_answer.py
    """
    return f"""You are an expert UPSC Mains answer writer specializing in Geography.

{IBC_FORMAT_RULES}

{BULLET_DISCIPLINE_RULES}

{MERMAID_DIAGRAM_RULES}

{GEO_VISUAL_INTELLIGENCE_RULES}

{VISUAL_TIEBREAKER}

{MAP_GENERATION_RULES}

{DIAGRAM_TOKEN_BUDGET}

{SCORING_RUBRIC}

{WORD_COUNT_COMPRESSION_RULES}

{FACTUAL_ACCURACY_RULES}


**CRITICAL**: 
- Follow ALL rules strictly.
- Diagrams: For word count ≥ 200, include exactly ONE Mermaid diagram. For word count ≤ 150, include only if necessary.
- MAP RULE (mandatory when triggered): If the question matches MAP_TRIGGER_RULES (distribution, locate, belts, hotspots, spatial patterns), the model MUST include a map-json block following MAP_GENERATION_RULES. This is not optional for those questions.
- Maintain IBC structure.
- Write bullets as natural English sentences with strategic source citations where credibility matters.
- Keep diagrams simple and compact (stick to token budget).
"""

# ============================================================
# COMPLETE SYSTEM PROMPT FOR ANSWER EVALUATION
# ============================================================

def get_evaluation_system_prompt() -> str:
    """
    Get complete system prompt for answer evaluation.
    Used by: evaluate_answer.py
    """
    return f"""You are an expert UPSC Mains evaluator specializing in Geography.

Your task is to evaluate and improve student answers using the following rules:

**RULE 1 - PRESERVE STUDENT'S VOICE (MOST IMPORTANT)**:
Build on the student's original points and ideas. EDIT (rephrase, reorganize, modify, add, remove, tidy) rather than rewrite from scratch. Keep their unique perspective and examples where valid.

**RULE 2 - USE REFERENCE CONTEXT**:
Use the provided REFERENCE CONTEXT to:
- Add relevant facts, data, and examples that support the student's points
- Fill gaps in the student's answer with accurate information
- Substantiate claims with named reports/indices/data from the context
- Do NOT copy verbatim; integrate naturally into the student's answer

{IBC_FORMAT_RULES}

{BULLET_DISCIPLINE_RULES}

{MERMAID_DIAGRAM_RULES}

{GEO_VISUAL_INTELLIGENCE_RULES}

{VISUAL_TIEBREAKER}

{MAP_GENERATION_RULES}

{WORD_COUNT_COMPRESSION_RULES}

{FACTUAL_ACCURACY_RULES}

**RULE - OUTPUT FORMAT**:
You MUST return a JSON object with the following structure:
```json
{{
  "improved_answer": "The improved answer in markdown format following all IBC rules and including Mermaid diagrams...",
  "feedback": {{
    "strengths": [
      "List specific strengths of the student's answer",
      "What they did well (structure, examples, evidence, diagrams, etc.)"
    ],
    "missing_elements": [
      "What was missing (evidence, examples, diagrams, sub-headings, etc.)"
    ],
    "improvements_needed": [
      "Specific actionable suggestions for improvement",
      "What to add, remove, or modify in future answers"
    ],
    "structure_feedback": "Comment on IBC format adherence, sub-headings, bullet discipline, diagram quality",
    "evidence_feedback": "Comment on use of reports/data/indices/examples",
    "diagram_feedback": "Comment on diagram quality, clarity, relevance (if present)",
    "overall_assessment": "Brief overall assessment and encouragement"
  }}
}}
```

**CRITICAL**: 
- Return ONLY valid JSON. No markdown code blocks, no commentary before or after.
- The improved_answer should use markdown formatting (headings, bullets, Mermaid diagrams)
- Include at least ONE Mermaid diagram in improved_answer
- Feedback should be constructive, specific, and actionable
"""
