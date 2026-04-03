# Quick Start: analyze-pyq-discovery Agent

**TL;DR:** Run this agent to analyze UPSC PYQs and get concept/trap recommendations.

---

## 30-Second Overview

```python
# Launch agent to analyze Climatology PYQs in background
Agent(
  subagent_type="general-purpose",
  description="Analyze Climatology PYQs",
  prompt="""
  Load: backend/app/prelims_v2/agents/analyze-pyq-discovery/config.json
  Skill: backend/skills/analyze-pyq-discovery.md

  Analyze:
  - subject: "Geography"
  - domain: "Climatology"
  - years: "2015-2024"
  - validation_mode: true
  - depth: "standard"
  """,
  run_in_background=true
)

# ~45 mins later, outputs ready in:
# config/research/2026-04-03_1246_Geography_Climatology/
```

---

## What This Agent Does

1. **Reads** extracted UPSC PYQs (20-40 questions)
2. **Analyzes** concepts, traps, patterns using documented methodology
3. **Compares** against existing concept pools (finds gaps, outdated priorities)
4. **Generates** structured recommendations for pool updates
5. **Outputs** 4-5 JSON files + markdown recommendations

---

## Files in This Folder

| File | Read First? | Purpose |
|------|-------------|---------|
| **README.md** | ✓ | This file. Start here. |
| **AGENT.md** | After README | Full agent spec, invocation patterns, debugging |
| **config.json** | For reference | Agent configuration & parameters |
| **prompt_template.md** | For understanding | Detailed workflow (references skill file) |

**Skill File (outside this folder):**
- **backend/skills/analyze-pyq-discovery.md** | ✓ | Read before running agent. Documents analysis methodology. |

---

## Quick Usage

### 1. Analyze a Single Domain

```python
Agent(
  subagent_type="general-purpose",
  description="Analyze Climatology PYQs for Geography",
  prompt="""
  Load and execute: backend/app/prelims_v2/agents/analyze-pyq-discovery/config.json

  Parameters:
  - subject: "Geography"
  - domain: "Climatology"
  - years: "2015-2024"
  - validation_mode: true
  - depth: "standard"

  Follow: backend/skills/analyze-pyq-discovery.md (read first!)
  """,
  run_in_background=true
)
```

### 2. Analyze 3 Domains in Parallel

```python
for domain in ["Climatology", "Geomorphology", "Indian Geography"]:
  Agent(
    subagent_type="general-purpose",
    description=f"Analyze {domain} PYQs",
    prompt=f"""
    Load: backend/app/prelims_v2/agents/analyze-pyq-discovery/config.json

    Parameters:
    - subject: "Geography"
    - domain: "{domain}"
    - depth: "standard"
    """,
    run_in_background=true
  )

# All 3 run in parallel (~45 mins total, not 135 mins)
```

### 3. Quick Analysis (20 min)

```python
Agent(
  subagent_type="general-purpose",
  description="Quick Climatology PYQ analysis",
  prompt="""
  Config: backend/app/prelims_v2/agents/analyze-pyq-discovery/config.json

  Parameters:
  - subject: "Geography"
  - domain: "Climatology"
  - depth: "quick"  # Fast mode
  - validation_mode: false  # Skip pool comparison
  """,
  run_in_background=true
)
```

---

## Parameters

### Required
- **subject** — UPSC subject (e.g., "Geography", "Polity")
- **domain** — Sub-domain (e.g., "Climatology")

### Optional (sensible defaults)
- **years** — Range for analysis (default: "2015-2024")
- **depth** — "quick" | "standard" | "thorough" (default: "standard")
- **validation_mode** — Compare against existing pools? (default: true)
- **focus_areas** — Prioritize specific concepts (default: none, analyze all)

See `config.json` for full parameter list.

---

## Expected Output

**Location:** `config/research/{TIMESTAMP}_{SUBJECT}_{DOMAIN}/`

**Example:** `config/research/2026-04-03_1246_Geography_Climatology/`

### Files Generated
1. `concepts_discovered_*.json` — All concepts found, with frequency & priority suggestions
2. `trap_patterns_discovered_*.json` — Trap patterns identified in wrong answers
3. `recommendations_*.md` — **READ THIS** — Actionable updates for your pools
4. `pyq_input_summary.json` — Metadata (how many questions, years analyzed)
5. `validation_report_*.json` (optional) — Pool gaps & mismatches found

---

## After Agent Completes

### Step 1: Review Recommendations
```bash
cat config/research/2026-04-03_1246_Geography_Climatology/recommendations_*.md
```

Looks like:
```markdown
# Recommendations for Geography > Climatology

## Pool Updates

### Add Concepts
- Madden-Julian Oscillation (appears in 2 questions, 2018/2023)

### Adjust Priority
- Monsoon: Increase from "high" → "ultra_high" (appears in 7/35 = 20% of questions)

### Expand Question Types
- Monsoon: Add "pure_ca" (2 pure_ca questions found, currently not listed)
```

### Step 2: Apply Selective Updates

**Edit:** `backend/app/prelims_v2/concept_pools/geography_climatology.json`

```json
{
  "Monsoon": {
    "priority": "ultra_high",  // Changed from "high"
    "tested_as_question_types": ["assertion_reason", "multi_statement", "pure_ca"]  // Added "pure_ca"
  }
}
```

### Step 3: Done!

Blueprint & Generator now use updated pools → better questions.

---

## Success Checklist

✅ Agent succeeded if:
- All output files exist and are valid JSON/Markdown
- Concepts in JSON match manual spot-check (≥90%)
- Recommendations include evidence (e.g., "7/35 questions")
- No JSON parse errors
- Markdown is readable

---

## Troubleshooting

### Agent Times Out
→ Reduce year range (e.g., "2020-2024" instead of "2015-2024")

### Output Files Missing
→ Check that PYQ file exists at: `backend/app/prelims_v2/pyqs_{domain}_{years}.json`

### Recommendations Look Vague
→ Check evidence citations; re-run with `depth="thorough"`

### Want More Details?
→ Read `AGENT.md` (full spec) or `backend/skills/analyze-pyq-discovery.md` (methodology)

---

## Files to Read (In Order)

1. **README.md** ← You are here
2. **backend/skills/analyze-pyq-discovery.md** — Methodology (read before running)
3. **AGENT.md** — Full agent spec (for debugging or details)
4. **config.json** — Parameter reference

---

## Real Example: Climatology Analysis

```python
# Run this:
Agent(
  subagent_type="general-purpose",
  description="Analyze Geography Climatology PYQs 2015-2024",
  prompt="""
  Load: backend/app/prelims_v2/agents/analyze-pyq-discovery/config.json
  Skill: backend/skills/analyze-pyq-discovery.md (read this first!)

  Parameters:
  - subject: "Geography"
  - domain: "Climatology"
  - years: "2015-2024"
  - pyq_file_path: "backend/app/prelims_v2/pyqs_climatology_2015_2024.json"
  - validation_mode: true
  - depth: "standard"

  Execute the 9-phase analysis and generate all outputs.
  """,
  run_in_background=true
)
```

Result (~45 mins later):
```
config/research/2026-04-03_1246_Geography_Climatology/
├── concepts_discovered_Climatology_2026-04-03_1246.json
├── trap_patterns_discovered_Climatology_2026-04-03_1246.json
├── recommendations_Climatology_2026-04-03_1246.md  ← READ THIS
├── validation_report_Climatology_2026-04-03_1246.json
└── pyq_input_summary.json
```

Open recommendations markdown → see what to update → make edits → done!

---

## Next Steps

1. **Read the skill file first:** `backend/skills/analyze-pyq-discovery.md`
2. **Launch an agent** using one of the patterns above
3. **Wait ~45 mins** (runs in background)
4. **Review outputs** in `config/research/`
5. **Apply recommendations** to your concept pools

---

## Questions?

- **How does agent work?** → AGENT.md
- **What is the methodology?** → backend/skills/analyze-pyq-discovery.md
- **What parameters can I use?** → config.json
- **How do I debug?** → AGENT.md (Failure Modes section)

