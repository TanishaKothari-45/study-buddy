# Agent: analyze-pyq-discovery

**Agent ID:** `analyze-pyq-discovery`

**Skill Reference:** `backend/skills/analyze-pyq-discovery.md` (read first for detailed methodology)

**Type:** Background research & analysis agent

**Model:** Sonnet 4.6 (reasoning-heavy)

---

## Purpose

Autonomously analyze last 10 year UPSC Preliminary year questions (PYQs) for a given subject/domain to:
### Core Analysis Tasks
- **Extract Concepts**: Identify every concept, sub-concept, and linked concept tested across all PYQs. Classify by frequency (rare/occasional/common/very_high) based on appearance count.
- **Classify Question Types**: For each concept, note which question types tested it (assertion_reason, multi_statement, match_pair, pure_ca, direct_fact, scenario, etc.).
- **Identify Trap Patterns**: Analyze wrong answer options to extract common misconceptions. For each pattern, identify the mechanism, affected concepts, and evidence (cite specific question numbers).
- **Map Cross-Domain Links**: Detect which other domains appear with your domain (e.g., climatology linked with oceanography). Record linking patterns.
- **Flag Current Affairs Triggers**: Identify which concepts are CA-connectable based on PYQ evidence (e.g., monsoon + news of monsoon failure).
- **Validate Against Existing Pools** (if provided): Compare discovered concepts against existing concept pool. Flag concepts in pool not in PYQs, concepts in PYQs not in pool, priority mismatches, and question-type discrepancies.

---

## When to Use

### ✅ Perfect Use Cases

1. **New subject/domain analysis** — First time analyzing a subject for question generation
2. **Periodic validation** — Every 1-2 years, re-analyze PYQs to catch trends
3. **Parallel batch analysis** — Launch agents for 3+ domains simultaneously
4. **Gap analysis** — Identify concepts tested in PYQs but missing from pools
5. **Priority calibration** — Verify concept priorities match actual question frequency

### ❌ Not Ideal For

- Single question analysis (use Read/Grep instead)
- Real-time question generation (agent is for offline analysis)
- Simple fact-checking (overkill for quick lookups)
- When you just need to read a file (use Read tool directly)

---

## Architecture

### Folder Structure
```
backend/.claude/agents/analyze-pyq-discovery/
├── AGENT.md                    # This file (agent specification)
├── config.json                 # Agent configuration & parameters
├── prompt_template.md          # Detailed prompt with analysis workflow
└── README.md                   # Quick start guide
```

### Relationship to Skill
- **Skill file** (`backend/skills/analyze-pyq-discovery.md`): Documents the analysis methodology (9 phases, prompts, output specs)
- **Agent folder** (this folder): Orchestrates execution, couples skill to agent workflow

**Key point:** Agent loads the skill file at runtime and follows its methodology step-by-step. If skill evolves, agent automatically uses updated methodology.

---

## Input Parameters

### Required
- **subject** — UPSC subject (Geography, Polity, History, Economy, Science, Environment)
- **domain** — Sub-domain or topic (Climatology, Geomorphology, Constitutional Law, etc.)

### Optional
- **years** — Year range for analysis (default: 2015-2024). Format: "2015-2024"
- **pyq_file_path** — Path to extracted PYQ JSON. If omitted, agent searches standard location
- **validation_mode** — If true, compare findings against existing concept pool (default: true)
- **depth** — Analysis depth: "quick" (20 min), "standard" (45 min), "thorough" (120 min) (default: standard)
- **focus_areas** — Specific concepts to prioritize (e.g., ["Monsoon", "ENSO"])

---

## Output

**Location:** `config/research/{timestamp}_{subject}_{domain}/`

**Example:** `config/research/2026-04-03_1246_Geography_Climatology/`

### Generated Files

1. **concepts_discovered_{domain}_{timestamp}.json**
   - All concepts extracted from PYQs
   - Frequency, sub-concepts, linked concepts, question types
   - CA-connectable flags
   - Priority suggestions
   - Evidence citations

2. **trap_patterns_discovered_{domain}_{timestamp}.json**
   - Trap patterns identified in wrong answers
   - Frequency distribution
   - Mechanism explanation
   - Mapping to existing trap IDs (GEO_C_T01, etc.)
   - Evidence: which questions demonstrate each trap

3. **recommendations_{domain}_{timestamp}.md**
   - Actionable recommendations organized by section:
     - Pool Updates (add concepts, adjust priority, expand question types)
     - Trap Registry Updates (new patterns, frequency adjustments)
     - Question Generation Changes (Blueprint/Generator implications)
     - Architecture Implications (difficulty recipes, CA weighting)
     - Synthesis & key takeaways

4. **pyq_input_summary.json**
   - Metadata: subject, domain, years analyzed
   - Question count and distribution by year
   - Unique concepts/traps discovered
   - Analysis parameters and timestamp

5. **validation_report_{domain}_{timestamp}.json** (if validation_mode=true)
   - Concepts in pool but not in PYQ (possibly outdated)
   - Concepts in PYQ but not in pool (gaps to fill)
   - Priority mismatches (pool vs frequency-based evidence)
   - Question type mismatches (pool incomplete vs actual usage)

---

## How Agent Uses Skill File

### At Runtime

1. **Agent starts** → reads `config.json` → sees `"skill_reference": "../../skills/analyze-pyq-discovery.md"`
2. **Loads skill file** → extracts methodology (9-phase workflow)
3. **Reads prompt_template.md** → this includes the skill's analysis steps
4. **Executes 9 phases** (from skill file):
   - Phase 1: Data Loading & Validation
   - Phase 2: Concept Extraction
   - Phase 3: Trap Pattern Discovery
   - Phase 4: Linking Analysis
   - Phase 5: Question Type Classification
   - Phase 6: Current Affairs Mapping
   - Phase 7: Validation Against Existing Pool
   - Phase 8: Recommendation Generation
   - Phase 9: Output Generation
5. **Generates outputs** → writes all JSON/markdown files to dated directory

### Advantage of This Design

- **Single source of truth:** Skill file is the definitive methodology
- **No code duplication:** Agent doesn't hardcode analysis logic
- **Easy updates:** If skill methodology improves, agent automatically uses new version
- **Auditability:** Skill file + agent outputs = reproducible, traceable analysis

---

## Invocation Patterns

### Pattern 1: Single Domain (Background)
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

  Follow methodology in: backend/skills/analyze-pyq-discovery.md
  Generate all outputs to config/research/[timestamp]_Geography_Climatology/
  """,
  run_in_background=true
)
```

### Pattern 2: Parallel Multi-Domain (3 Agents, No Blocking)
```python
domains = ["Climatology", "Geomorphology", "Indian Geography"]

for domain in domains:
  Agent(
    subagent_type="general-purpose",
    description=f"Analyze {domain} PYQs",
    prompt=f"""
    Execute: backend/app/prelims_v2/agents/analyze-pyq-discovery/config.json

    Parameters:
    - subject: "Geography"
    - domain: "{domain}"
    - years: "2015-2024"
    - validation_mode: true
    - depth: "standard"
    """,
    run_in_background=true
  )

# All 3 run in parallel
# Result: Complete in ~45 mins (not 45×3=135 mins)
```

### Pattern 3: With Focus Areas
```python
Agent(
  subagent_type="general-purpose",
  description="Analyze Climatology PYQs (focus: Monsoon & ENSO)",
  prompt="""
  Execute: backend/app/prelims_v2/agents/analyze-pyq-discovery/config.json

  Parameters:
  - subject: "Geography"
  - domain: "Climatology"
  - years: "2015-2024"
  - focus_areas: ["Monsoon", "ENSO", "Jet Streams"]
  - validation_mode: true
  - depth: "thorough"
  """,
  run_in_background=true
)
```

---

## Expected Duration

| Depth | Time | Includes |
|-------|------|----------|
| quick | 20 min | Core concept/trap extraction only |
| standard | 45 min | Full analysis + validation + recommendations |
| thorough | 2 hrs | Everything + trend analysis + semantic clustering + outlier detection |

---

## Success Criteria

✅ Agent succeeded if:

- **Output Files** — All 4-5 required files generated, well-formed JSON/Markdown
- **Concept Extraction** — ≥90% match vs manual spot-check (5 random questions)
- **Trap Patterns** — Mapped to existing trap IDs OR proposed as new with evidence
- **Recommendations** — Specific & actionable (not vague suggestions)
- **Evidence** — All claims cited (e.g., "7/35 questions", "Q12 2023", "GEO_C_T02")
- **Validation** — If enabled, identifies real pool/PYQ mismatches

---

## Failure Modes & Recovery

| Symptom | Likely Cause | Recovery |
|---------|--------------|----------|
| PYQ file not found | Wrong path or missing file | Provide explicit `pyq_file_path` parameter |
| JSON parse error | Malformed PYQ input | Validate PYQ JSON structure; report which field is problematic |
| < 20 questions processed | Insufficient data | Expand year range or combine related domains |
| Validation report shows >20% mismatches | Pool is stale or out of sync | Flag for human review; do not auto-apply |
| Trap pattern with <2 question evidence | Low confidence pattern | Include but mark as "low confidence" in recommendations |

---

## Integration Workflow

### After Agent Completes

**Step 1:** Review recommendations
```bash
cat config/research/2026-04-03_1246_Geography_Climatology/recommendations_*.md
```

**Step 2:** Review validation report (if enabled)
```bash
cat config/research/2026-04-03_1246_Geography_Climatology/validation_report_*.json
```

**Step 3:** Apply selective updates to concept pool
```json
// Edit: backend/app/prelims_v2/concept_pools/geography_climatology.json
"Monsoon": {
  "priority": "ultra_high",  // Changed from "high"
  "tested_as_question_types": ["assertion_reason", "multi_statement", "pure_ca"]  // Added types
}
```

**Step 4:** Apply selective updates to trap registry
```json
// Edit: backend/app/prelims_v2/traps_climatology.json
"GEO_C_T02": {
  "frequency": 0.18  // Increased from 0.15
}
```

**Step 5:** Blueprint/Generator now use updated pools → better questions

---

## Files in This Folder

| File | Purpose |
|------|---------|
| **AGENT.md** | This file. Agent specification & quick reference. |
| **config.json** | Agent configuration, parameters, success criteria. |
| **prompt_template.md** | Detailed prompt with full 9-phase workflow. Agent executes this. |
| **README.md** | Quick start guide for users. |

---

## Configuration Reference

See `config.json` for:
- All input parameters with descriptions
- Output file specifications
- Success criteria checklist
- Use cases
- Estimated durations

---

## Skill File Reference

See `backend/skills/analyze-pyq-discovery.md` for:
- Complete 9-phase analysis workflow
- Prompt templates for each phase
- Output format specifications
- Example analyses
- Error handling

---

## Next Steps

1. **Launch agent** using one of the invocation patterns above
2. **Wait for completion** (background execution, no blocking)
3. **Review outputs** in `config/research/[timestamp]_*/`
4. **Apply recommendations** selectively to concept pools/trap registries
5. **Monitor quality** — verify question generation improves with updated pools

---

## Support & Debugging

### If Agent Fails
1. Check error message in agent output
2. Verify input file exists and is valid JSON
3. Check year range has ≥20 questions
4. Re-run with `depth="quick"` to narrow down issue

### If Results Look Wrong
1. Manually spot-check extracted concepts (5 random questions)
2. Compare against skill file's example analyses
3. Review evidence citations in recommendations
4. Flag for human validation if gap >10%

### For Feature Requests
- Update skill file (`backend/skills/analyze-pyq-discovery.md`)
- Agent automatically uses new methodology on next run
- No need to edit agent files

---

## Links

- **Skill File:** `backend/skills/analyze-pyq-discovery.md`
- **Config File:** `config.json` (in this folder)
- **Prompt Template:** `prompt_template.md` (in this folder)
- **Concept Pool Schema:** `backend/app/prelims_v2/skill.md`
- **Trap Registry Example:** `backend/app/prelims_v2/traps_climatology.json`
- **Difficulty Types:** `backend/app/prelims_v2/difficulty_types_geography_base.json`

---

## Version History

| Date | Version | Notes |
|------|---------|-------|
| 2026-04-03 | 1.0 | Initial release. Option B structured folder approach. |

