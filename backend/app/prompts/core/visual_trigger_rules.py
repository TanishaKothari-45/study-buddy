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

─── DIAGRAM TYPE TRIGGERS ───
diagram_type = "flowchart":
  - Question asks HOW something works, WHY something happens, WHAT LEADS TO what
  - Process, mechanism, causal chain, policy → outcome, reform → consequence
  - Examples: monsoon mechanism, erosion cycle, poverty trap, disaster response chain

diagram_type = "timeline":
  - Question involves CHRONOLOGICAL progression, evolution, phases, milestones
  - Historical evolution, reform phases, event sequences, policy development arc

diagram_type = "table":
  - Question asks to COMPARE, contrast, or evaluate two or more entities/policies
  - Pros vs cons, advantages vs limitations, two-axis evaluation
  - Directive words: "compare", "contrast", "distinguish", "evaluate pros and cons"

diagram_type = "mindmap":
  - Question involves MULTI-DIMENSIONAL factors, stakeholders, or themes
  - "Discuss the factors", "analyse the dimensions", "impacts of X"
  - No single chain or timeline — truly multi-branch

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

─── LIMITS ───
At most TWO visuals per answer (map + one other). Never all three (map + table + diagram).
If map is triggered, map is mandatory — it cannot be dropped to fit diagram.
"""
