# ============================================================
# VISUAL SYNTAX RULES — used in Generator system prompt ONLY
# HOW to write Mermaid diagrams and map-json blocks.
# WHEN to use each type is decided by Blueprint (visual_trigger_rules.py).
# ============================================================

MERMAID_DIAGRAM_RULES = """
**MERMAID DIAGRAM SYNTAX RULES**

The diagram type is already decided in the ANSWER BLUEPRINT.
Your job is to execute the correct syntax for that type.

**Syntax by diagram type**:

flowchart  → `graph TD` (top-down) or `graph LR` (left-right)
mindmap    → `mindmap` with root and branches; central node = core concept; first-level = major dimensions; keep node text 1–4 words
timeline   → `timeline` with chronological events
pie        → `pie title ...` with segments; limit to 4–6 segments; use clear labels
cycle      → `graph TD` or `graph LR` with arrows forming a closed loop (A→B→C→D→A)
layered    → `graph TB` with vertical layout showing hierarchy top to bottom
table      → standard markdown table (not Mermaid); use | headers | and | --- | separator row

**Quality Guidelines**:
- **Text Safety**: ALWAYS enclose node labels in double quotes (e.g., `A["Label"]`). Keep labels SHORT (max 3-4 words). Use `<br/>` for line breaks.
- **Subgraph Labels**: ALWAYS quote subgraph labels containing parentheses or special chars (e.g., `subgraph "Push Factors (North)"`). Better: avoid parentheses entirely in labels.
- **Contrast**: Do not use dark backgrounds for nodes.
- **Simplicity**: Maximum 8 nodes, 10 connections.
- **Diagram token budget**: keep diagram compact (labels ≤ 40 tokens total).

**Diagram Placement (CRITICAL)**:
- **NEVER place a diagram between a sub-heading and its bullet points** — this breaks readability.
- Place diagram BEFORE the related sub-heading OR at the END of a section AFTER all bullets.
- Follow the exact placement specified in the ANSWER BLUEPRINT (e.g., "after Introduction", "end of [subheading]").

**Mermaid Syntax Examples**:

**Flowchart**:
```mermaid
graph TD
    A["Climate Change"] --> B["Rising Temperatures"]
    A --> C["Erratic Monsoons"]
    B --> D["Glacier Melting"]
    C --> E["Flood/Drought Cycle"]
    D --> F["Water Scarcity"]
    E --> F
```

**Mind Map**:
```mermaid
mindmap
  root((Urbanisation))
    Economic
      Jobs
      Growth
    Social
      Housing
      Inequality
    Environmental
      Pollution
      Water Stress
    Governance
      Planning
      Service Delivery
```

**Timeline**:
```mermaid
timeline
    title Climate Policy Evolution
    1992 : UNFCCC
    2008 : NAPCC
    2015 : Paris
    2021 : Net Zero
```

**Pie Chart**:
```mermaid
pie title Land Use in India
    "Agricultural Land" : 60
    "Forest Cover" : 23
    "Urban Areas" : 3
    "Water Bodies" : 4
    "Others" : 10
```

**Cycle Diagram**:
```mermaid
graph TD
    A["Low Income"] --> B["Poor Nutrition"]
    B --> C["Low Productivity"]
    C --> D["Limited Employment"]
    D --> A
```

**Layered Diagram**:
```mermaid
graph TB
    A["Constitutional Vision"] --> B["Policy Framework"]
    B --> C["Institutions"]
    C --> D["Implementation"]
    D --> E["Outcomes"]
```

**CRITICAL FORMATTING**:
- Wrap diagram in markdown code block: ```mermaid
- Close with ```
- Add blank line before and after diagram
- Do not include other markdown inside the diagram
- Include diagram title as markdown heading or bold text above the block
- If diagram syntax is uncertain, default to safe flowchart: `graph TD` with quoted labels

**Subgraph Syntax (CRITICAL)**:
- ❌ WRONG: `subgraph Push Factors (North)` — parentheses break parser
- ✅ CORRECT: `subgraph "Push Factors (North)"` — quoted label
- ✅ SAFER: `subgraph Push Factors - North` — avoid parentheses entirely
"""


# ============================================================
# MAP SYNTAX RULES — used in Generator system prompt ONLY
# HOW to write map-json blocks.
# WHEN to use maps is decided by Blueprint (visual_trigger_rules.py).
# ============================================================

MAP_GENERATION_RULES = """
**MAP OUTPUT SYNTAX (map-json)**

Maps are decided by the ANSWER BLUEPRINT (map_needed: true/false).
Your job is to write a valid map-json block when blueprint requires it.

**Output format — insert a `map-json` code block**:

```map-json
{
  "type": "map",
  "mapType": "choropleth | markers | rivers | combined",
  "region": "india | world",
  "title": "Brief descriptive title",
  "choropleth": {
    "values": {"Region": value},
    "unit": "unit description"
  },
  "markers": [
    {"name": "Location", "coordinates": [lon, lat], "type": "city|port|resource", "label": "Short label"}
  ],
  "arrows": [
    {"from": [lon, lat], "to": [lon, lat], "label": "Flow / direction"}
  ],
  "paths": [
    {
      "label": "Physical feature",
      "coordinates": [[lon, lat], [lon, lat]],
      "stroke": "#8B4513",
      "strokeWidth": 3
    }
  ],
  "rivers": true,
  "legendTitle": "Legend description",
  "style": {"colorScheme": "YlGn | YlOrRd | Blues | Greens", "theme": "warm"}
}
```

**Map types**:
- `choropleth`: colour-coded regions by data value (state-wise crop production, rainfall)
- `markers`: point locations (mineral deposits, cities, ports, industrial centres)
- `rivers`: river network overlay
- `combined`: multiple layers — rivers + markers + choropleth + paths (use for physical features)

**Physical features rule**:
- Do NOT use markers (dots) for elongated features like mountain ranges, coastlines
- Use `paths` to draw a line along the feature
- Example Western Ghats: `[[73, 20], [74, 15], [77, 9]]`; `"stroke": "#8B4513"` (brown)

**Region rule**:
- India questions → `"region": "india"`
- Global / international / country comparison questions → `"region": "world"`

**Color schemes**:
- `YlGn`: crops, vegetation, forest cover
- `YlOrRd`: temperature, intensity, population density
- `Blues`: water resources, rainfall, humidity
- `Greens`: environmental indicators, green cover

**Coordinate reference** (lon, lat):
- Delhi: [77.2, 28.6] | Mumbai: [72.8, 19.1] | Kolkata: [88.4, 22.6]
- Chennai: [80.3, 13.1] | Bangalore: [77.6, 12.9]

**Example — Markers**:
```map-json
{
  "type": "map",
  "mapType": "markers",
  "region": "india",
  "title": "Major Coalfields in India",
  "markers": [
    {"name": "Jharia", "coordinates": [85.62, 23.78], "type": "coal", "label": "Jharia"},
    {"name": "Raniganj", "coordinates": [87.13, 23.62], "type": "coal", "label": "Raniganj"},
    {"name": "Korba", "coordinates": [82.75, 22.35], "type": "coal", "label": "Korba"}
  ],
  "style": {"theme": "warm"}
}
```

**Example — Combined (flow + rivers)**:
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

**Map placement**:
- Insert map-json block AFTER the relevant sub-heading (or after Introduction if blueprint says so)
- Add label above: **Map: [Descriptive Title]**
- List all markers/locations in bullet points below the map
- Blank line before and after the block

**Guidelines**:
- Max 15-20 states/markers; short labels (≤ 3 words)
- Always list locations in text below map for accessibility
- Coordinates format: [longitude, latitude]
"""


# ============================================================
# GEO-VISUAL INTELLIGENCE — legacy pipeline only
# Not used in new blueprint pipeline (blueprint handles decisions)
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
  - If the question explains a **process, mechanism, interaction, feedback, or causal chain** → include **Mermaid** (if visual clarity improves).
  - If the question requires **comparison, positive vs negative impacts, advantages vs limitations, pros vs cons, trade-offs, or two-axis evaluation** → include a **Table**.
  - If multiple formats appear relevant:
    - Select **only those with distinct explanatory roles**.
    - Do NOT include more than two formats in total.

NEGATIVE TRIGGERS (DO NOT USE VISUALS):
Do NOT include any visual if the question is:
- purely definitional
- purely conceptual/theoretical without structure
- short justification-based (e.g., "Why is X important?")
- GS4 Ethics questions (except rare framework comparison tables)

DIRECTIVE-SENSITIVE PREFERENCE:
- Explain / Analyse → Mermaid preferred over Table
- Compare / Evaluate / Examine → Table preferred over Mermaid
- Discuss → Bullets first; visual only if structure/mechanism exists

- HARD OVERRIDE (Map Priority): If map triggers satisfied, Map MUST be included.
- Priority order: 1. Map  2. Table  3. Mermaid
- Never include Table + Mermaid + Map together.
"""

VISUAL_TIEBREAKER = """
If multiple formats appear useful, include only those that add distinct explanatory value and keep the total count ≤ 2.
Never include Table + Mermaid + Map together.
"""
