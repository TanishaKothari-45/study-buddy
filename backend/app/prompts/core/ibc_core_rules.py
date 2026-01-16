# ============================================================
# IBC FORMAT RULES (shared between both endpoints)
# ============================================================

IBC_FORMAT_RULES = """
**RULE - IBC FORMAT**:
- **INTRO**: 
- 2–3 lines only.
- Must clearly:
  - introduce the theme of the question, AND
  - define, contextualise, or frame the issue.
- May include (when relevant):
  - a brief definition,
  - a data point / report reference,
  - a contemporary reference or factual anchor.
- Avoid generic openings (“In today’s world…”).

- **BODY**: 
- Organise the body into **3–5 clear sub-headings**.
- Each sub-heading must:
  - address a distinct dimension or component of the question,
  - align with the directive (analyse, examine, evaluate, etc.).

### Sub-heading rules
- Use `###` markdown for every sub-heading.
- Leave one blank line before each new sub-heading.
- Do NOT merge multiple dimensions under one sub-heading.
------------------------------------------------
CONTENT PRESENTATION
------------------------------------------------

Each sub-heading may use **ONE** of the following formats:

### A. BULLETS (default)
- Use bullets unless another format clearly improves clarity.
- Each sub-heading: **2–4 bullets** only.
- Bullet discipline:
  - One main idea per bullet.
  - Clear, concise sentences.
  - Support with:
    - an example, OR
    - a data point / report / case, where it adds credibility.
- Avoid repetition across bullets.
 - Each bullet MUST start with - (dash) for proper markdown list rendering
 - Each bullet: **Main idea** (≤ 12 words) + Evidence (named report/index/data where it adds credibility) + Example (named Indian OR named global). Write as natural English sentences, not forced templates.


  ### B. TABLE (secondary, not default)
- Use ONLY when comparison, classification, impact, multi-dimensional evaluation, or two-axis evaluation is required.
- Table replaces bullets entirely for that sub-heading.
-A table improves clarity or reduces repetition compared to bullets

  - **When tables are appropriate**:

  - CONSIDER TABLE format when the sub-heading involves:
    - Positive vs negative impacts
    - Advantages vs limitations
    - Comparative analysis (A vs B)
    - Category-wise or sector-wise impacts
    - Two-axis evaluation (e.g., dimension × time / region × impact)
    
  - **Table Usage**:
  - Tables are an optional structuring aid, not a thinking or explanation tool.
  - Prefer bullets for explanation, assessment, and evaluative answers.

  - AVOID TABLE format when:
    - Spatial clarity is required (use Map)
    - The answer requires causal explanation, reasoning, or assessment(use Mermaid)
    - Evidence and examples need narrative development
    - A process/mechanism diagram (Mermaid) provides better clarity
    - If bullets can convey the idea clearly without repetition, do NOT introduce a table.


    - If a TABLE is used for a sub-heading:
      - DO NOT write bullets for that sub-heading
      - The table fully replaces bullets for that section
    - Table must be concise (preferably ≤ 4 rows × 3 columns)
- Do NOT repeat table content again in bullet form elsewhere
- Table cell content must be concise, point-based, and exam-readable.

- Table cell rules depend on table type:

  - **Comparison Tables (A vs B)**:
    - Each table cell should contain ONE compact descriptive point (preferably one liner).
    - Use short phrases; avoid explanations or multiple ideas.
    - Examples may be included only as a single keyword (e.g., Anai Mudi, NE monsoon).

  - **Impact / Analytical Tables**:
    - Each table cell may include 2–3 compact points.
    - Points must be listed as phrases, not sentences.
    - Examples are allowed as keywords, not explanations.

EXAMPLE OF INVALID TABLE CELLS:
- Do NOT generate:
  - "High vulnerability to shocks (e.g., COVID-19).<br>- Inflation and cost rise."
  - "Overuse of fertilisers causes soil problems, reducing fertility, and harming microbes."
  - Any cell containing HTML tags (<br>, <div>, etc.)

EXAMPLE OF VALID TABLE CELLS:
- High shock vulnerability (COVID-19)
- Rising cost of living
- Soil nutrient loss; chemical overuse
- Pollutant trapping; respiratory risk


- HARD CONSTRAINT (MANDATORY):
  - Narrative or paragraph-style sentences are NOT allowed inside table cells.
  - Table cells must be written as compact descriptive phrases or listed points, not explanatory prose.
  - Avoid commas and full stops inside table cells
  - HTML line breaks (e.g., <br>, <br/>) are STRICTLY forbidden.
  - HTML tags of any form (<...>) are STRICTLY forbidden.
  HTML tags (anything matching /<.*?>/) are forbidden in cells.
- If multiple points are needed inside a table cell:
  - Use semicolons (;) or dashes (–) within the same cell, OR
  - Split into additional table rows instead of line breaks.
- Never use bullet symbols (-, •) inside table cells.

- Preferred separators inside table cells:
  - Semicolon (;), slash (/), or dash (–)
  - Use separators only to split compact phrases, not full sentences.

- **Matrix Table (Two-Axis Evaluation)**:
    - Matrix tables are a subtype of table format
    - Use when evaluation requires two dimensions (e.g., Economic × Social, Short-term × Long-term)
    - Matrix tables follow the same rules as tables and replace bullets entirely for that sub-heading

- **WAY FORWARD/FORWARD LINKAGE(Conditional Section)**: 

Include a forward-looking element (either as a distinct section or embedded in the conclusion) when the issue:
    - Has current or future relevance, AND
    - Involves human systems, governance, sustainability, security, development, or resilience, AND
    - Is amenable to intervention, reform, adaptation, or management.

This forward-looking element may include:
    - Policy direction
    - Institutional or governance response
    - Technological or adaptive solutions
    - Behavioural or structural changes

Do NOT include forward linkage when the question is purely descriptive, definitional, or explanatory of natural mechanisms without intervention scope.
  - DO NOT include WAY FORWARD in purely descriptive, scientific, factual, or mechanism-explanation questions.
  - Include **2–3 bullets**, each starting with -. 
  - Each bullet must be actionable, future-oriented, and concrete.
  - Keep bullets concise and concrete.
  - No philosophical or vague guidance.

- **CONCLUSION**:
- 2–3 lines only.
- Must:
  - synthesise the core argument,
  - provide closure (not repetition),
  - reflect the directive’s demand.
- Do NOT introduce new arguments.
- Tone: concise, balanced, forward-looking where appropriate.

"""
