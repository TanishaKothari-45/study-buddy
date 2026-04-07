# ============================================================
# VISUAL TRIGGER RULES — used in Blueprint system prompt ONLY
# Tells the blueprint WHEN to use diagrams/maps, not HOW to write them.
# Syntax rules (Mermaid format, map-json schema) stay in visual_syntax_rules.py
# ============================================================

VISUAL_TRIGGER_RULES = """
**VISUAL SELECTION — TRIGGER CONDITIONS**

Use these rules to decide `diagram_type` and `map_needed` in the blueprint.

─── MAP TRIGGERS (set map_needed: true) ───
Set map_needed = true when the question involves ANY of:
- "distribution", "spread of", "location of", "identify areas", "where are"
- "belt", "zone", "region", "hotspot", "spatial pattern"
- Geographical features: rivers, mountain ranges, coasts, seismic zones, flood plains
- Environmental spatial data: biosphere reserves, tiger reserves, protected areas
- Economic spatial data: industrial corridors, agricultural zones, mineral distribution
- Disaster-prone areas, cyclone tracks, drought-prone districts
- Subject = Geography AND question is about physical or human geography phenomena
- SAARC/ASEAN/regional grouping countries, trade routes, conflict zones (IR)
- Territorial/boundary changes (History)

Subject-specific map usage (examiner-aligned):
  Geography (GS1) — Primary & Mandatory:
    Physical geography (rivers, mountains, climate zones, monsoon patterns)
    Resource distribution (minerals, crops, industries, coalfields)
    Environmental phenomena (cyclones, ocean currents, wind belts)
  History (GS1) — High-Value, Selective:
    Use ONLY for: battles, revolts, invasions; trade routes, ports, migration; empire expansion/decline
    Do NOT use for purely administrative or ideological questions
  Environment & Ecology (GS3): biodiversity hotspots, protected areas, climate hazards, pollution hotspots
  Internal Security (GS3) — Limited:
    Use for: insurgency belts, border regions, coastal security
    Do NOT use for: cyber, financing, or institutional issues
  International Relations (GS2) — Very Selective:
    Use for: strategic regions, chokepoints, corridors, maritime zones (Indo-Pacific, SCS)
    Do NOT map treaties or institutional mechanisms
  Polity / Governance (GS2) — Rare: regional governance, federal asymmetry, delimitation, spatial disparities

─── DIAGRAM TYPE TRIGGERS ───

diagram_type = "flowchart":
  Purpose: Represent ordered logic, sequences, and causal progression.
  Use when question involves:
  - Natural and physical processes: Monsoon mechanism, plate tectonics, erosion cycles, disease transmission
  - Cause–effect chains: Environment → economy, policy → outcomes, technology → impact
  - Policy and governance workflows: Policy formulation → implementation → monitoring → outcomes
  - Institutional or administrative processes: Election process, budget cycle, disaster response chain
  - Socio-economic or historical progression: Reform → response → consequence
  - Technological or infrastructural pipelines: Data flow, production chains, mitigation pathways
  Trigger words: HOW something works, WHY something happens, WHAT LEADS TO what, process, mechanism, causal chain

diagram_type = "timeline":
  Purpose: For chronological progression, evolution, and phase-wise change.
  Use when question involves:
  - Historical Evolution: Evolution of Constitution, Freedom movement phases
  - Policy / Reform Phases: Economic reforms, Climate policy evolution
  - Disaster / Event Sequencing: Cyclone lifecycle, Pandemic phases
  - Technological / Scientific Development: Space programme milestones
  - Environmental / Geological Time Scales: Climate change phases
  Trigger words: CHRONOLOGICAL, evolution, phases, milestones, historical progression

diagram_type = "table":
  Purpose: For structured comparison and two-axis evaluation.
  Use when question involves:
  - Comparing two or more entities/policies: Pros vs cons, advantages vs limitations
  - Two-axis evaluation: scheme A vs scheme B, country A vs country B on metrics
  Trigger words: compare, contrast, distinguish, evaluate pros and cons, advantages and disadvantages

diagram_type = "mindmap":
  Purpose: For dimensions, themes, stakeholders, and multi-factor structuring.
  Use when question involves:
  - Multi-Dimensional Analysis: Climate change impacts, Poverty causes, Internal security
  - Stakeholder Mapping: Governance actors, Development projects, IR
  - Factor-Based Questions: Factors affecting monsoon, Determinants of location
  - Impact / Consequence Mapping: Impact of globalization, Urbanisation impacts
  - Policy / Issue Decomposition: NEP components, Food security pillars
  - Thematic Structuring: Governance pillars, Ethics stakeholders
  Trigger words: MULTI-DIMENSIONAL factors, stakeholders, themes, "discuss the factors", "analyse the dimensions", "impacts of X"
  Use only when truly multi-branch — no single chain or timeline

diagram_type = "pie":
  Purpose: For proportional distribution and relative share comparison.
  Use when question involves:
  - Sectoral composition: GDP sector share, employment structure
  - Resource distribution: Land-use pattern, water usage
  - Demographic composition: Population by age, workforce
  - Economic structure analysis: Tax revenue, export basket
  - Environmental contribution shares: Emission sources
  Trigger: question tests proportional breakdown of a whole into parts

diagram_type = "cycle":
  Purpose: For cyclical processes, reinforcing feedback loops.
  Use when question involves:
  - Natural and physical cycles: Water cycle, rock cycle
  - Economic and social feedback loops: Poverty trap, inflation spiral
  - Environmental degradation–response loops: Deforestation feedback
  - Governance and policy feedback systems: Regulation → compliance cycle
  - Technological and system feedbacks: Innovation cycle
  Trigger: process forms a closed loop, output becomes input again

diagram_type = "layered":
  Purpose: For vertical structure, hierarchy, and stratified systems.
  Use when question involves:
  - Physical and natural stratification: Earth's interior, atmosphere layers
  - Institutional and governance hierarchy: Union → State → Local
  - Economic and sectoral structuring: Primary → Secondary → Tertiary
  - Social structure: Stratification, urban hierarchy
  - Technological architecture: Data stack, security layers
  - Policy design architecture: Vision → policy → implementation
  Trigger: system has distinct vertical layers or levels where position matters

diagram_type = "none":
  - Purely definitional: "What is X?", "Define X", "Describe X briefly"
  - GS4 Ethics/values questions (except framework comparison tables)
  - Short answers (target word count ≤ 150)
  - Abstract philosophical arguments with no structural or spatial component

─── DIRECTIVE-SENSITIVE PREFERENCE ───
- Explain / Analyse → prefer flowchart
- Compare / Evaluate / Examine → prefer table
- Discuss → bullets first; diagram only if process/structure exists
- Locate / Identify / Distribute → map (mandatory, not optional)
- Timeline / Evolution / Phases → timeline diagram
- Impacts / Factors / Dimensions → mindmap
- Feedback / Cycle / Loop → cycle diagram
- Hierarchy / Layers / Levels → layered diagram
- Share / Proportion / Composition → pie chart

─── LIMITS ───
At most TWO visuals per answer (map + one other). Never all three (map + table + diagram).
If map is triggered, map is mandatory — it cannot be dropped to fit diagram.
"""
