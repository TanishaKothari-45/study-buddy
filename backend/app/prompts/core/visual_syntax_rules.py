# ============================================================
# MERMAID DIAGRAM INSTRUCTIONS
# ============================================================

MERMAID_DIAGRAM_RULES = """
**RULE - DIAGRAM DISCIPLINE (Mermaid.js)**:

For answers with word count ≥ 200: Prefer including **one** Mermaid diagram in the Body (Mermaid_count ≤ 1). This restriction does NOT apply to simple Maps — a Map may be added in addition when spatial clarity improves the answer.

For answers with word count ≤ 150: Diagrams are **good to have but only if necessary** — include only when visualization adds significant clarity.

**Diagram Type Selection Guide**:

1. **Flowchart** (graph TD/LR):
   **Purpose**: Represent ordered logic, sequences, and causal progression.
   **Use**:
   - **Natural and physical processes**: Monsoon mechanism, plate tectonics, erosion cycles, disease transmission.
   - **Cause–effect chains**: Environment → economy, policy → outcomes, technology → impact.
   - **Policy and governance workflows**: Policy formulation → implementation → monitoring → outcomes.
   - **Institutional or administrative processes**: Election process, budget cycle, disaster response chain.
   - **Socio-economic or historical progression**: Reform → response → consequence.
   - **Technological or infrastructural pipelines**: Data flow, production chains, mitigation pathways.

   **When to prefer**:
   - Explaining how or why one stage leads to another.
   - Showing dependencies, sequencing, or cumulative effects.
   - When causal clarity improves marks more than prose.

   **Syntax**: `graph TD` (top-down) or `graph LR` (left-right).
   **Decision Rule**:
   - Use a Flowchart when the logic is sequential or stage-based.
   - Use a Cause–Effect diagram when multiple factors simultaneously influence one outcome.
   - If unsure, default to Flowchart.

2. **Mind Map** (mindmap):
   **Purpose**: For dimensions, themes, stakeholders, and multi-factor structuring.
   **Use**:
   - **Multi-Dimensional Analysis**: Climate change impacts, Poverty causes, Internal security.
   - **Stakeholder Mapping**: Governance actors, Development projects, IR.
   - **Factor-Based Questions**: Factors affecting monsoon, Determinants of location.
   - **Impact / Consequence Mapping**: Impact of globalization, Urbanisation impacts.
   - **Policy / Issue Decomposition**: NEP components, Food security pillars.
   - **Thematic Structuring**: Governance pillars, Ethics stakeholders.

   **Syntax**: `mindmap` with root and branches.
   - Central node = core concept
   - First-level branches = major dimensions
   - Second-level branches = sub-points
   - Keep node text short (1–4 words)

3. **Timeline** (timeline):
   **Purpose**: For chronological progression, evolution, and phase-wise change.
   **Use**:
   - **Historical Evolution**: Evolution of Constitution, Freedom movement phases.
   - **Policy / Reform Phases**: Economic reforms, Climate policy evolution.
   - **Disaster / Event Sequencing**: Cyclone lifecycle, Pandemic phases.
   - **Technological / Scientific Development**: Space programme milestones.
   - **Environmental / Geological Time Scales**: Climate change phases.

   **Syntax**: `timeline` with chronological events.

4. **Pie Chart** (pie):
   **Purpose**: For proportional distribution and relative share comparison.
   **Use**:
   - **Sectoral composition**: GDP sector share, employment structure.
   - **Resource distribution**: Land-use pattern, water usage.
   - **Demographic composition**: Population by age, workforce.
   - **Economic structure analysis**: Tax revenue, export basket.
   - **Environmental contribution shares**: Emission sources.

   **Syntax**: `pie` with title and data.
   - Limit to 4–6 segments.
   - Use clear labels.

5. **Cycle Diagram** (graph with circular flow):
   **Purpose**: For cyclical processes, reinforcing, recurring feedback loops.
   **Use**:
   - **Natural and physical cycles**: Water cycle, rock cycle.
   - **Economic and social feedback loops**: Poverty trap, inflation spiral.
   - **Environmental degradation–response loops**: Deforestation feedback.
   - **Governance and policy feedback systems**: Regulation → compliance cycle.
   - **Technological and system feedbacks**: Innovation cycle.

   **Syntax**: `graph TD` or `graph LR` with arrows forming a loop (A->B->C->D->A).

6. **Layered / Block Diagram** (graph TB):
   **Purpose**: For vertical structure, hierarchy, and stratified systems.
   **Use**:
   - **Physical and natural stratification**: Earth’s interior, atmosphere layers.
   - **Institutional and governance hierarchy**: Union → State → Local.
   - **Economic and sectoral structuring**: Primary → Secondary → Tertiary.
   - **Social structure**: Stratification, urban hierarchy.
   - **Technological architecture**: Data stack, security layers.
   - **Policy design architecture**: Vision → policy → implementation.

   **Syntax**: `graph TB` with vertical layout.

**Quality Guidelines**:
- **Text Safety**: ALWAYS enclose node labels in double quotes (e.g., `A["Label"]`). Keep labels SHORT (max 3-4 words). Use `<br/>` for line breaks.
- **Subgraph Labels**: ALWAYS quote subgraph labels containing parentheses or special chars (e.g., `subgraph "Push Factors (North)"`). Better: avoid parentheses entirely in labels.
- **Contrast**: Do not use dark backgrounds for nodes.
- **Simplicity**: Maximum 8 nodes, 10 connections.
- **Diagram token budget**: keep diagram compact (labels ≤ 40 tokens total).

**Diagram Placement (CRITICAL)**:
- **NEVER place a diagram between a sub-heading and its bullet points** — this breaks readability.
- Place diagram BEFORE the related sub-heading OR at the END of a section AFTER all bullets.

**Mermaid Syntax Examples**:

**Example 1 - Flowchart (Cause-Effect)**:
```mermaid
graph TD
    A["Climate Change"] --> B["Rising Temperatures"]
    A --> C["Erratic Monsoons"]
    B --> D["Glacier Melting"]
    C --> E["Flood/Drought Cycle"]
    D --> F["Water Scarcity"]
    E --> F
```

**Example 2 - Mind Map (Multi-factor Analysis)**:
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

**Example 3 - Timeline (Historical)**:
```mermaid
timeline
    title Climate Policy Evolution
    1992 : UNFCCC
    2008 : NAPCC
    2015 : Paris
    2021 : Net Zero
```

**Example 4 - Pie Chart (Distribution)**:
```mermaid
pie title Land Use in India
    "Agricultural Land" : 60
    "Forest Cover" : 23
    "Urban Areas" : 3
    "Water Bodies" : 4
    "Others" : 10
```

**Example 5 - Cycle Diagram (Feedback Loop)**:
```mermaid
graph TD
    A["Low Income"] --> B["Poor Nutrition"]
    B --> C["Low Productivity"]
    C --> D["Limited Employment"]
    D --> A
```

**Example 6 - Layered Diagram (Hierarchy)**:
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
- Do not include other markdown inside the diagram.
- Include diagram title as markdown heading or bold text
- If unsure which diagram to choose, use this minimal, safe flowchart:

```mermaid
graph TD
    A["Causes"] --> B["Impacts"]
    B --> C["Mitigation"]
```

**Subgraph Syntax (CRITICAL)**:
- When using subgraphs, ALWAYS quote labels containing parentheses or special characters.
- ❌ WRONG: `subgraph Push Factors (North)` — parentheses break parser
- ✅ CORRECT: `subgraph "Push Factors (North)"` — quoted label
- ✅ SAFER: `subgraph Push Factors - North` — avoid parentheses entirely

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

- **Differential heating** creates pressure gradients driving monsoon winds. For instance, Delhi experiences a temperature gap of 6–8°C (IMD 2023).
- **Orographic effect**: Western Ghats force air upward causing condensation, leading to Cherrapunji receiving 11,000mm annual rainfall.

**IMPORTANT**: If diagram syntax is complex or uncertain, prefer simpler flowchart (graph TD) format.
"""


# ============================================================
# MAP DIAGRAM INSTRUCTIONS (CORE VISUAL RULES)
# ============================================================

MAP_GENERATION_RULES = """
**RULE — MAP DIAGRAMS (Spatial Visualization)**

Maps are used to demonstrate spatial relationships, distribution, and location-based causation.
They are NOT decorative and must be used only when spatial reasoning improves marks.

Maps are IN ADDITION to Mermaid diagrams (which show process, causality, or flow).

------------------------------------------------
MANDATORY MAP TRIGGERS
------------------------------------------------
A MAP MUST be generated when the question involves ANY of the following:

1. Distribution or concentration of:
   • resources, crops, minerals, industries
   • population, biodiversity, pollution
   • hazards, belts, zones, corridors

2. Spatial patterns across:
   • India OR
   • World / regions / continents

3. Directive keywords explicitly indicating space:
   • locate, identify regions, where, areas
   • belts, hotspots, zones, corridors
   • mark on map

------------------------------------------------
SUBJECT-SPECIFIC MAP USAGE (EXAMINER-ALIGNED)
------------------------------------------------

**Geography (GS1)** — Primary & Mandatory
• Physical geography (rivers, mountains, climate zones, monsoon patterns)
• Resource distribution (minerals, crops, industries, coalfields)
• Environmental phenomena (cyclones, ocean currents, wind belts)

**History (GS1)** — High-Value, Selective
Use maps ONLY for:
• battles, revolts, invasions
• trade routes, ports, migration
• empire expansion or decline
Do NOT use maps for purely administrative or ideological questions.

**Environment & Ecology (GS3)**
• biodiversity hotspots
• protected areas, ecosystems
• climate hazards, pollution hotspots

**Internal Security (GS3)** — Limited
• insurgency belts
• border regions, coastal security
Do NOT use maps for cyber, financing, or institutional issues.

**International Relations (GS2)** — Very Selective
• strategic regions, chokepoints, corridors
• maritime zones (Indo-Pacific, SCS)
Do NOT map treaties or institutional mechanisms.

**Polity / Governance (GS2)** — Rare
• regional governance, federal asymmetry
• delimitation or spatial disparities


------------------------------------------------
MAP OUTPUT FORMAT (STRICT)
------------------------------------------------
Insert a `map-json` code block using the schema below:

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
- For word count ≥ 200, include ONE visual if it materially improves clarity, 
as determined by GEO_VISUAL_INTELLIGENCE_RULES. Maps are additional when triggered.
- Keep map data accurate and simple (max 15-20 markers/countries)
- Always list locations in text below the map for accessibility
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
  - If the question explains a **process, mechanism, interaction, feedback, or causal chain** → include **Mermaid** (if visual clarity improves).
  - If the question requires **comparison, positive vs negative impacts, advantages vs limitations, pros vs cons, trade-offs, or two-axis evaluation** → include a **Table**.
  - If multiple formats appear relevant:
    - Select **only those with distinct explanatory roles**.
    - Do NOT include more than two formats in total.

 ------------------------------------------------
NEGATIVE TRIGGERS (DO NOT USE VISUALS)
------------------------------------------------

Do NOT include any visual if the question is:
- purely **definitional**
- purely **conceptual/theoretical** without structure
- short **justification-based** (e.g., “Why is X important?”)
- GS4 Ethics questions (except rare framework comparison tables)

------------------------------------------------
DIRECTIVE-SENSITIVE PREFERENCE
------------------------------------------------

- Explain / Analyse → Mermaid preferred over Table
- Compare / Evaluate / Examine → Table preferred over Mermaid
- Discuss → Bullets first; visual only if structure/mechanism exists   

- HARD OVERRIDE (Map Priority):
  - If MAP_TRIGGER_RULES are satisfied, a Map MUST be included.
  - The Map cannot be dropped to accommodate a Table or Mermaid.
  - If visual limits are exceeded, In such cases, choose between Table and Mermaid based on which adds greater value.

- STRUCTURAL OVERRIDE (Mermaid Preference):
  - Prefer a Mermaid diagram when understanding depends on relationships, structure, flow, or interaction between factors.
  - This includes causal chains, feedback loops, multi-factor interactions, or layered systems.
  - Do NOT force a table when relationships between elements matter more than listing them.


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
# Tie-breaker when multiple visuals seem useful:
VISUAL_TIEBREAKER = """
If multiple formats appear useful, include only those that add distinct explanatory value and keep the total count ≤ 2.

Never include Table + Mermaid + Map together.
"""

