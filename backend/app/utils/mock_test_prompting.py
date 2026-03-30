"""
UPSC Mock Test Prompt System - Refactored
Clean, hierarchical prompt structure for question generation
"""
import json
from pathlib import Path
from typing import Optional, Dict, Any, List

# Path to the patterns configuration
# study-buddy/backend/app/utils/mock_test_prompting.py -> study-buddy/
# Base directory for config files
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent

def load_pyq_patterns(subject: str = "Geography") -> Dict[str, Any]:
    """Load the enhanced UPSC Prelims patterns from JSON for a given subject."""
    filename = "geography_prelims_pyq_patterns.json"
    if subject == "History":
        filename = "history_prelims_pyq_patterns.json"
    elif subject == "Economy":
        filename = "economy_prelims_pyq_patterns.json"
    elif "Science" in subject:
        filename = "science_technology_prelims_pyq_patterns.json"
    elif "Environment" in subject:
        filename = "environment_ecology_prelims_pyq_patterns.json"
    elif "Polity" in subject:
        filename = "polity_prelims_pyq_patterns.json"
        
    patterns_path = BASE_DIR / "config" / filename
    try:
        if patterns_path.exists():
            with open(patterns_path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading patterns for {subject}: {e}")
    return {"patterns": []}

def format_patterns_for_prompt(subject: str = "Geography") -> str:
    """Format the patterns JSON into a readable string for the prompt."""
    data = load_pyq_patterns(subject)
    patterns = data.get("patterns", [])
    if not patterns:
        return ""
    
    formatted = "### Additional UPSC Question Patterns:\n"
    for p in patterns:
        formatted += f"- **{p.get('title', 'Pattern')}**: {p.get('explanation', '')}\n"
    return formatted

# ----------------------------------------------------------------------
# SYSTEM PROMPTS (Dynamic)
# ----------------------------------------------------------------------

def get_system_prompt(subject: str) -> str:
    """Generate subject-specific system prompt."""
    return f"""You are an expert UPSC Prelims {subject} question designer with deep examiner-level understanding of the UPSC CSE exam pattern, especially for {subject} sections.

Your role is to generate multiple-choice questions that reflect how UPSC examiners think, reason, and trap candidates — privileging application, conceptual linkage, chronology/logic (for History) or spatial/map logic (for Geography), and disciplined elimination reasoning.

Your questions must be rooted in static {subject.lower()} concepts, with current contextual elements used only to test concept application, not to ask superficial news facts.

### Source Legitimacy Rule:
If provided context is minimal or missing, you MUST use your search tool to find verified academic, governmental, or reputable reference sources. You MUST prioritize these search results over your internal weights to ensure questions are grounded in legit, non-hallucinated content.

You must produce questions in authentic UPSC formats including multi-statement reasoning, assertion–reasoning, match-pairs, and applied conceptual themes.

Craft distractors that are plausible, conceptually related, and require reasoning to eliminate. Avoid trivial or purely definitional options unless tightly linked with deeper understanding.

You should always assume UPSC-like language, precision, and structure in all questions and explanations.
"""

# ----------------------------------------------------------------------
# COGNITIVE FRAMEWORKS (Subject-Specific)
# ----------------------------------------------------------------------

FRAMEWORK_GEOGRAPHY = """COGNITIVE FRAMEWORK

PATTERN DEFINITIONS & QUESTION DESIGN RULES (GEOGRAPHY UP-SC CSE PRELIMS)

You must generate UPSC-level geography MCQs that reflect how questions are designed in actual UPSC Prelims papers — not simple recall items, but applied, analytical, spatial, and logically linked items.

The patterns below define *what each type tests*, *how linkages must work*, and *how distractors must be constructed*. Follow these strictly.

---

1) CONCEPT DEFINITION / CORE GEOGRAPHIC CONCEPT MCQ

Purpose:
- Tests precise understanding of key geography concepts (physical processes, spatial principles, interactions).
- Not a trivial definition recall; distractors must be conceptually plausible and target common misunderstandings.

Expected Features:
- Stem asks for the *best description/definition* of a concept.
- Distractors reflect close concepts that candidates often confuse.
- Avoid completely irrelevant or obviously wrong options.

Example Traps to Use:
- Confusion between forces (e.g., Coriolis vs pressure gradient)
- Related but distinct terms (continental drift vs plate tectonics)

Static vs Current:
- Static concept at core. Current context may *illustrate* concept but not be tested as isolated knowledge.

Distractor Logic:
- Subtle differences (e.g., directionality, mechanism) that require reasoning.

---

2) MULTI-STATEMENT EVALUATION MCQs

Purpose:
- Tests cumulative understanding of a concept via several linked statements.
- Most common pattern in geography prelims, often with 3–4 statements.

Expected Features:
- Use “Consider the following statements…” followed by numbered items.
- Statements must be independent but conceptually related.
- Statements should test the application of static concepts.
- Options query which are correct, requiring the solver to reason through each.

Linkage Rules:
- All statements should stem from a **common conceptual theme** (e.g., monsoon mechanism, ocean current behavior).
- Some statements should be *plausible but subtly wrong* to enforce elimination reasoning.

Distractor Logic:
- Small factual/qualifier errors: direction, extent, conditions.
- Avoid trivial falsehoods; make every statement *appear plausible on first glance*.

Static vs Current:
- Static concepts govern correctness. Current context can be used to *frame or modify a statement*, but correctness must still derive from core geography logic.

---

3) MATCH-THE-PAIR / LIST MCQs

Purpose:
- Tests precise mapping of related items (rivers → basins, mountains → continents, climate types → characteristics).

Expected Features:
- Two columns with items requiring accurate one-to-one association.
- A mix of correct and incorrect pairings, where incorrect ones are *plausible but wrong*.

Linkage Rules:
- Each item pair must be verifiable through geography knowledge; traps should be near matches.

Distractor Logic:
- Similar names or regions (e.g., similar basin names, nearby mountain ranges) are good distractor sources.

Static vs Current:
- Largely static, factual spatial mapping.

---

4) ASSERTION–REASON TYPE

Purpose:
- Tests ability to evaluate *cause–effect or explanatory link* between two statements.

Expected Features:
- Two statements (Assertion and Reason).
- Options:
  (a) Both true, R explains A  
  (b) Both true, R does not explain A  
  (c) A true, R false  
  (d) A false, R true

Linkage Rules:
- Reason must link conceptually to assertion to be a correct explanation.
- Distractors test partial truth vs causal linkage.

Distractor Logic:
- R may be true but not explanatory.
- One or both statements may be subtly off.

Static vs Current:
- Primarily static logic; current context only to *validate or contextualize* a cause–effect.

---

5) FACT-BASED / DIRECT MCQs

Purpose:
- Tests accurate recall of geographic facts where high-level reasoning may not be required, but distractors must remain plausible.

Expected Features:
- One-question stems on geographic fact (rivers, latitudes, physiography).
- Distractors should be *close in parameters* (e.g., similar latitude or river location).

Distractor Logic:
- Near misses (latitude slightly off), similar but incorrect geographic features.

Static vs Current:
- Static.

---

6) MAP / LOCATION / SPATIAL REASONING

Purpose:
- Tests spatial understanding — relative positions, closest/furthest from a latitude/longitude, ordering.

Expected Features:
- Stem makes reference to spatial relationships, not just names.
- Distractors should be *geo-spatially adjacent or similar*.

Linkage Rules:
- Spatial reasoning must tie back to coordinate or proximity logic.

Distractor Logic:
- Nearby but incorrect positional alternatives.

Static vs Current:
- Static spatial relationships.

---

7) CONCEPT + CURRENT CONTEXT (APPLIED GEOGRAPHY)

Purpose:
- Tests *static geography principles* in the light of *recent contextual observations or trends*.
- Current context should serve as a testing *lens* for geography concepts, not trivia.
- Current context should be applied part of the static concept.

Expected Features:
- One or more statements include a current context premise.
- Correctness still hinges on *core geography concept application*.

Linkage Rules:
- Use current context to *modify or illustrate* static concepts (e.g., anomalous rainfall patterns, sea surface temperature trends).
- Current info must *alter or test* conceptual interpretation.

Distractor Logic:
- Current context can introduce confusion if misinterpreted; use that as trap logic, but still tie back to static truth.

---

GENERAL RULES FOR LINKAGE & DISTRACTOR DESIGN

1. Reasoning and Elimination:
- Questions should be structured so candidates apply elimination reasoning, not pure recall.  
- In multi-statement and assertion–reasoning items, logical evaluation of each option is required.

2. Static + Current Integration:
- *Static geography knowledge forms the core truth*.  
- *Current affairs can be used to test or extend this truth but should not stand alone.*  
- Avoid superficial news questions that do not *deepen the conceptual test*.

3. Plausible Distractors — Hallmarks of UPSC:
- Distractors should exploit:
  • Common misconceptions
  • Qualifier traps (“only”, “always”, “never”)
  • Spatial or causal confusion
  • Near-true factual variants

4. Language and Tone:
- Use formal, precise, concise language, similar to UPSC question papers.  
- Avoid unnecessary verbosity.

5. Pattern Diversity in a Single Mock:
- A balanced mock should include:
  • At least two multi-statement questions
  • One assertion–reason
  • One match-the-pair (if possible)
  • One applied concept link with current context
  • A mix of fact- and spatial-based items

6. Explanation Requirement:
- Provide concise justification for each correct answer and brief reasons why other options are incorrect.
- Explanations must reflect *UPSC-like reasoning*, not generic clarification.

---
"""

# Handle framework selection and pattern integration dynamically in get_cognitive_framework or assemble_upsc_prompt
FRAMEWORK_HISTORY = """COGNITIVE FRAMEWORK

1. Examination Intent
   • History in UPSC Prelims tests **factual knowledge, chronological understanding, logical reasoning, and conceptual discrimination** based on the Indian historical narrative — from ancient to modern and art & culture.  
   • Questions are derived from *core sources* (NCERTs, standard reference texts, PYQ trends) and often combine understanding with analysis or cause–effect logic.  
   • History questions may vary in difficulty from straightforward recall to analytical multi-statement and comparative reasoning. :contentReference[oaicite:0]{index=0}

2. Topic Coverage & Domain Balance
   • Cover all major History domains — Ancient, Medieval, Modern, and Art & Culture — with a balanced distribution reflecting PYQ trends. Modern History generally has higher annual representation, followed by Ancient and Art & Culture. :contentReference[oaicite:1]{index=1}  
   • Each question should be anchored in *relevant historical context*, not isolated trivia.

3. Core Question Types & Generation Rules

   A) **Direct Concept / Definition**
      - Test precise understanding of historical concepts, terminologies, systems, or institutions.
      - Craft distractors that reflect *related but distinct concepts* to challenge elimination skills.

   B) **Multi-Statement Evaluation**
      - Use 2-or-3 statement sets requiring examinees to evaluate each statement’s correctness.
      - Include combinations that test *cause–effect relationships, policy context, or comparative facts*.

   C) **Match-the-Pair**
      - Pair personalities with contributions, movements with leaders, kingdoms with capitals, inscriptions with rulers, etc.
      - Distractors should include *incorrect but plausible associations* drawn from adjacent historical contexts.

   D) **Assertion–Reason**
      - Frame an assertion reflecting a historical fact, with a reason statement that may or may not logically explain it.
      - Ensure all four options (A–D) cover the logical space of explanation correctness.

   E) **Chronology / Sequence**
      - Tests ordering of events, reforms, movements, or reigns.
      - Distractors should represent *historically plausible but incorrect sequences*, forcing chronological discrimination.

   F) **Current-Linked Static Application**
      - If current or heritage context is used (e.g., archaeological discoveries, centenaries), embed it into the stem so that it serves as *a trigger for testing static knowledge*, not as trivia.

4. Distractor Engineering
   • Distractors must be:
     – **Plausible**: derived from closely related content or common misconceptions.  
     – **Non-redundant**: each must represent a distinct wrong choice, not trivial or obviously incorrect.  
     – **Elimination-testable**: knowledgeable candidates can eliminate based on historical relationships, not impossible facts.

   • Example distractor sources:
     – Alternate administrative systems (e.g., confusing Ryotwari vs Zamindari).  
     – Misplaced chronological facts (events from adjacent periods).  
     – Incorrect causal links (e.g., associating a law with the wrong movement).

5. Difficulty Calibration
   • **Easy:** Pure recall (dates, definitions, names, capitals, contributions).  
   • **Medium:** Multi-statement or matching where at least one statement/distractor requires reasoning.  
   • **Hard:** Assertion–Reason or sequence questions that *interlink two domains or themes* (e.g., reform policy impact on subsequent movements).

6. Static vs Current Use
   • Static knowledge is foundational; current context (heritage news, archaeological news, centenaries) should *supplement static understanding* and test analytical application.  
   • Avoid relying on isolated news facts — always link current context back to the syllabus. :contentReference[oaicite:2]{index=2}

7. Domain Nuances
   • **Ancient History:** Civilizational features, political structures, philosophical streams, art & architecture, societal frameworks.  
   • **Medieval History:** Sultanate and Mughal structures, regional powers, religious and cultural synthesis. :contentReference[oaicite:3]{index=3}  
   • **Modern History:** British policies, revolts & movements, constitutional developments, nationalist leadership — frequently tested and a major component of PYQs. :contentReference[oaicite:4]{index=4}  
   • **Art & Culture:** Architectural styles, rock-cut traditions, inscription analysis, literature and performance traditions — tested contextually.

8. Explanation Standards
   • Provide **concise but comprehensive** explanations that justify the correct answer and eliminate distractors.  
   • Explanations must highlight *historical logic*, not just factual affirmation.

9. Output Structure & Consistency
   • Each generated question should follow the JSON format with fields: “question”, “options”, “correct_answer”, “explanation”, and a “source” map indicating the historical topic and sub-domain.  
   • Avoid repetition of facts across questions; emphasize variety even within a topic cluster.

10. Examples of Prompt Framing (Internal Guidance for Model)
   • “Use the historical narrative and logical relationships to construct distractors that require elimination reasoning.”  
   • “For multi-statement and assertion–reason questions, ensure each statement tests a distinct factual or conceptual element.”  
   • “When using recent context or archaeology/heritage triggers, anchor the question in static content — do not ask about current news directly.” 

"""

FRAMEWORK_ECONOMY = """COGNITIVE FRAMEWORK

1. Examination Intent
   • UPSC Prelims Economy tests **core economic concepts, policy interpretation, macro & microeconomic reasoning, and application of national data with policy context**. It also evaluates how aspirants connect basic theory with real-world economic indicators and policy outcomes.  
   • Questions often blend static fundamentals (GDP, inflation, deficits, banking) with **current economic developments, budgets, and official data releases**. • Questions are framed to require **reasoned elimination** and not just rote recall of facts. :contentReference[oaicite:0]{index=0}  

2. Topic Coverage & Domain Balance
   • Include balanced coverage of key UPSC Prelims economy areas: Basic Concepts, Macroeconomics, Microeconomics, Fiscal & Monetary Policy, Banking & Finance, Public Finance, External Sector and Sectoral components.  
   • Each question should *anchor* a concept in economic logic — e.g., how a policy change affects inflation, employment, trade, or public finance. :contentReference[oaicite:1]{index=0}  

3. Core Question Types & Generation Rules

   A) **Direct Concept / Definition**
      - Test precise understanding of economics terms (e.g., GDP vs GVA, fiscal deficit, etc.).
      - Distractors should reflect *related economic concepts* that are close but incorrect.

   B) **Multi-Statement Evaluation**
      - Use multiple statements linking theory (e.g., inflation types) with policy outcomes or indicator effects.
      - Include statements that test both economics definitions and real economic behaviour.

   C) **Match-the-Pair**
      - Pair institutions with functions (RBI → monetary policy; SEBI → markets), indicators with explanations, or policy measures with effects.
      - Distractors should be plausible but incorrect linkages drawn from adjacent economic roles.

   D) **Assertion–Reason**
      - Test cause–effect logic in economic relationships (e.g., repo rate changes → demand effects).
      - Ensure options cover all logical combinations of A and R correctness.

   E) **Data/Indicator Interpretation**
      - Frame simple interpretation of economic trends, macro data changes, or policy announcements.
      - Distractors should include *mis-applied logical inferences* (e.g., assuming causation where only correlation exists).

   F) **Current-Linked Economy Application**
      - Use recent economic developments (budget proposals, RBI policy changes, official reports) as triggers but test *static economic logic*.
      - Avoid questions on only news headlines without grounding in economic principles.

4. Distractor Engineering
   • Distractors must be:
     – **Plausible within economic logic** (e.g., misinterpret GDP vs GNP understanding).  
     – **Non-redundant**: each wrong option must reflect a *distinct incorrect economic reasoning*.  
     – **Elimination-testable**: use static economic principles to eliminate incorrect choices.

   • Typical distractor sources:
     – Confusion between macro indicators (GDP vs GVA).  
     – Policy impact mis-attributions (e.g., assuming increased spending always reduces inflation).  
     – Mistaken institutional roles (e.g., SEBI managing RBI functions).

5. Difficulty Calibration
   • **Easy:** Core definitions and straightforward policy–term connections.  
   • **Medium:** Multi-statement with some reasoning, data interpretation with modest elimination logic.  
   • **Hard:** Assertion–Reason or application questions requiring *integration of static concept + current event/indicator trends*.

6. Static vs Current Use
   • Economy has a *dynamic current component* (budgets, surveys, RBI policy) but always link it to *static economic concepts* to test reasoning.  
   • Do not frame questions that simply repeat news facts — they must *require understanding* of how these news items affect economic logic.

7. Explanation Standards
   • Provide concise yet comprehensive explanations outlining:
     – Why the correct option is correct based on economic theory and data logic.  
     – Why other options are incorrect due to flawed economic reasoning or misapplication.

8. Output Structure & Consistency
   • Each question must include: “question”, “options”, “correct_answer”, “explanation”, and a “source” with topic/sub-domain.  
   • Avoid repetition of facts; emphasize *diversity of economic logic within a test*.

9. Prompt Framing Guidance
   • “Craft questions that blend static economic definitions with real policy outcomes and data interpretation.”  
   • “Ensure distractors reflect common misconceptions in economic reasoning.”  
   • “Use official data context and policy developments to *trigger* questions, but not as standalone news trivia.”  
"""
FRAMEWORK_POLITY = """COGNITIVE FRAMEWORK

1. Examination Intent
   • UPSC Polity tests **constitutional provisions, institutional structures, law-making processes, governance mechanisms, and their application** to real governance scenarios.  
   • Questions often ask for precise application of constitutional text and logic rather than mere definitions. :contentReference[oaicite:1]{index=1}

2. Topic Coverage & Domain Balance
   • Include coverage of Constitution basics, union/state structures, judiciary, electoral mechanisms, federalism, governance reforms, and recent developments in polity.  
   • Tie static constitutional principles with scenarios requiring application of provisions.

3. Core Question Types & Generation Rules

   A) **Direct Polity MCQ**
      - Test definitions, constitutional articles, institutional roles.
      - Distractors should reflect *similar but incorrect constitutional interpretations*.

   B) **Multi-Statement Polity Logic**
      - Combine several statements involving constitutional provisions and governance mechanisms.
      - Each statement should require *nuanced understanding*.

   C) **Match-the-Pair**
      - Link parts/articles of Constitution with provisions, institutions with functions.
      - Distractors should be plausible yet incorrect associations.

   D) **Assertion–Reason**
      - Test cause–effect or explanation logic in governance (e.g., why a provision exists).
      - Ensure all combinations of correctness are presented in options.

   E) **Fact-Based Governance MCQ**
      - Directly test governance roles, appointment powers, etc., using static constitutional text.

   F) **Current-Linked Polity MCQ**
      - Use recent amendments, ordinance enactments, or commission reports as context but test *underlying constitutional logic*.

4. Distractor Engineering
   • Distractors must:
     – Be *constitutionally plausible but incorrect*.  
     – Reflect common misconceptions about powers, functions, and provisions.  
     – Permit *elimination based on constitutional logic*.

   • Example distractor types:
     – Mis-assignment of powers (President vs PM).  
     – Incorrect constitutional article references.  
     – Misinterpretation of federal structures.

5. Difficulty Calibration
   • **Easy:** Direct constitutional facts.  
   • **Medium:** Multi-statement or match requiring careful elimination.  
   • **Hard:** Assertion–Reason with deep constitutional implications and current context integration.

6. Static vs Current Use
   • Static constitutional provisions are the core; current developments (ordinances, reforms) add *contextual application requirements*.  
   • Avoid trivia based solely on news headlines; always tie back to constitutional text or logic.

7. Explanation Standards
   • Provide clear reasoning using constitutional provisions and judicial interpretation to justify the correct answer and eliminate other options.

8. Output Structure & Consistency
   • Each question must include “source” mapping to the relevant Constitution/ governance sub-domain.  
   • Ensure varied sub-domain coverage in each test set.

9. Prompt Framing Rules
   • “Link governance scenarios with constitutional logic in questions.”  
   • “Use distractors that only fail through precise constitutional interpretation not vague misunderstandings.”  
"""
FRAMEWORK_ENVIRONMENT = """COGNITIVE FRAMEWORK

1. Examination Intent
   • UPSC Prelims Environment & Ecology tests **ecological principles, biodiversity, environmental laws and policies, pollution science, and global environmental frameworks**.  
   • Questions often integrate *static ecological concepts* with emerging environmental policy and global treaty contexts. :contentReference[oaicite:5]{index=5}

2. Topic Coverage & Domain Balance
   • Include ecology basics, ecosystem structure, biogeochemical cycles, biodiversity & conservation, pollution & mitigation, climate change frameworks, and environmental legislation.  
   • Questions should require candidates to *apply static ecological knowledge* with understanding of environment issues and policies.

3. Core Question Types & Generation Rules

   A) **Direct Environment MCQ**
      - Test static ecology definitions and environmental science principles.
      - Distractors should reflect *related ecological concepts but incorrect in outcome or definition*.

   B) **Multi-Statement Environment Logic**
      - Combine statements involving ecological processes, pollution types and effects.
      - Each statement should require *reasoned evaluation*.

   C) **Match-the-Pair**
      - Pair environmental terms with features, laws with their provisions, or treaties with goals.
      - Distractors should be plausible but incorrect associations.

   D) **Assertion–Reason in Ecology**
      - Test biological / environmental cause–effect relationships (e.g., greenhouse gas effect vs climate trends).
      - Ensure all possible answer combinations are available.

   E) **Fact-Based Environment MCQ**
      - Directly test static facts about environment, biodiversity hotspots, law provisions.

   F) **Current-Linked Environment MCQ**
      - Use recent environmental news (policy announcements, summit outcomes, treaties) as trigger to test *static ecological understanding*.

4. Distractor Engineering
   • Distractors must:
     – Be rooted in *plausible ecological concepts or legal interpretations*.  
     – Reflect common misconceptions (e.g., ozone vs greenhouse gases).  
     – Permit elimination through clear environmental logic.

   • Example distractor themes:
     – Confusion between ecosystem levels (e.g., food web vs food chain).  
     – Mis-association of laws and their mandates.  
     – Incorrect treaty provisions.

5. Difficulty Calibration
   • **Easy:** Static ecological definitions.  
   • **Medium:** Multi-statement with moderate reasoning.  
   • **Hard:** Assertion–Reason or current context requiring comprehensive elimination.

6. Static vs Current Use
   • Static ecology basics are core; current environmental developments (policy, summits, agreements) should be used as *application triggers* not trivia.

7. Explanation Standards
   • Explanations must connect ecological process or legal context with reasoning for correct and incorrect options.

8. Output Structure & Consistency
   • Each question includes “source” mapping to environment sub-domain.  
   • Each test should represent diverse ecological and policy sub-domains.

9. Prompt Framing Rules
   • “Frame questions that require application of core ecological theory to real environmental issues.”  
   • “Use current environmental developments as a contextual layer over static identity of processes or laws.”  
"""
FRAMEWORK_SCIENCE_TECH = """COGNITIVE FRAMEWORK

1. Examination Intent
   • Science & Technology in UPSC Prelims tests **fundamental scientific principles + ability to apply them contextually** to modern technological developments (space, biotech, IT, etc.).  
   • Questions should assess conceptual clarity and application logic (e.g., why a scientific principle leads to an outcome). Technology questions are often *application-oriented* rather than highly technical. :contentReference[oaicite:28]{index=0}

2. Topic Coverage & Domain Balance
   • Include basics from physics, chemistry, biology where relevant, and *modern technology domains* such as space missions, information technology, biotechnology, nanotechnology, and cybersecurity.  
   • Contextual triggers from *recent scientific advances and innovation achievements* should connect to static principles.

3. Core Question Types & Generation Rules

   A) **Direct Concept / Definition**
      - Test static science fundamentals (e.g., semiconductor conduction, ecological terms).
      - Distractors reflect subtle conceptual misunderstandings.

   B) **Multi-Statement Evaluation**
      - Use combinations of statements involving scientific ordering, spectrum, properties, etc.
      - Each statement should test *distinct scientific logic*.

   C) **Match-the-Pair**
      - Pair technologies with applications or discoveries with principles.
      - Distractors should be *incorrect but plausible* matches.

   D) **Assertion–Reason**
      - Test scientific cause–effect (e.g., technology advancement → impact due to physics/engineering principles).
      - Ensure all logical option combinations are represented.

   E) **Application / Data Interpretation**
      - Use simple, real-world scenarios requiring conceptual interpretation.
      - Distractors should challenge elimination reasoning.

   F) **Current-Linked Tech MCQ**
      - Use recent tech contexts (AI governance, space achievements, biotech innovations) as triggers; test *underlying principles or implications*.

4. Distractor Engineering
   • Distractors must:
     – Be scientifically plausible and reflect *common misconceptions*.  
     – Avoid technical jargon that requires specialist expertise.  
     – Facilitate elimination by conceptual reasoning.

   • Typical distractor sources:
     – Mis-application of laws (e.g., mixing properties of electromagnetic spectrum).  
     – Confusion between similar tech definitions (AI vs ML).  
     – Incorrect cause–effect reasoning.

5. Difficulty Calibration
   • **Easy:** Static concept definitions.  
   • **Medium:** Multi-statement or match with some reasoning.  
   • **Hard:** Assertion–Reason and technology application using current contexts.

6. Static vs Current Use
   • Base questions on static science principles; use current technological developments to *test applied understanding*.  
   • Do not ask standalone current news facts — tie them back to *static scientific explanation*.

7. Explanation Standards
   • Explanations must connect the scientific principle to the correct choice and dissect why each distractor is flawed conceptually.

8. Output Structure & Consistency
   • Maintain consistent JSON format with “source” mapping to topic/sub-domain.  
   • Ensure question sets cover diverse science sub-areas in a single mock test.

9. Prompt Guidance
   • “Frame questions that visibly test foundational science principles applied to modern technological contexts.”  
   • “Use recent scientific developments to anchor application questions tied to core concepts.”  
"""


def get_cognitive_framework(subject: str) -> str:
    """Return the cognitive framework for the given subject."""
    if subject == "History":
        return FRAMEWORK_HISTORY
    elif subject == "Economy":
        return FRAMEWORK_ECONOMY
    elif "Science" in subject:
        return FRAMEWORK_SCIENCE_TECH
    elif "Polity" in subject:
        return FRAMEWORK_POLITY
    elif "Environment" in subject:
        return FRAMEWORK_ENVIRONMENT
    # Default to Geography
    return FRAMEWORK_GEOGRAPHY

def get_question_type_quota(num_questions: int, ca_available: bool) -> str:
    """Return a strict per-type quota for the batch."""
    if not ca_available:
        return f"""QUESTION TYPE DISTRIBUTION (strict):
- {num_questions // 3} Multi-statement evaluation questions
- {num_questions // 5} Assertion-Reason questions  
- {num_questions // 5} Match-the-pair questions
- Remaining: Fact-based and spatial reasoning mixed"""
    
    # With current affairs available, assign CA linkage to specific types
    return f"""QUESTION TYPE QUOTA (you MUST hit these counts exactly):
- {num_questions * 3 // 10} Multi-statement: one statement in each MUST cite a 2024-2025 event from your search results
- {num_questions * 2 // 10} Assertion-Reason: Assertion = a 2024-2025 current development, Reason = the static geographic/scientific explanation
- {num_questions * 2 // 10} Match-the-pair: STATIC spatial/factual only — no current affairs
- {num_questions * 2 // 10} Fact-based: static concept, one distractor uses a current data point to trap candidates
- {num_questions * 1 // 10} Map/spatial reasoning: STATIC only

CRITICAL: CA integration must be in the QUESTION STEM, not just the explanation."""   


# Integrate patterns is now dynamic in the assembler

# ----------------------------------------------------------------------
# PROMPT ASSEMBLER
# ----------------------------------------------------------------------

def assemble_upsc_prompt(
    topic: str,
    subject: str,
    num_questions: int,
    retrieved_static_text: str,
    retrieved_current_affairs: str = "",
    pyq_chunks: List[Dict] = None,
    search_queries: List[Dict] = None
) -> str:
    """
    Build the hierarchical prompt for UPSC question generation.
    
    Args:
        topic: Topic for the questions
        subject: Subject (Geography, History)
        num_questions: Number of questions
        retrieved_static_text: Static material context
        retrieved_current_affairs: Current affairs context
        pyq_chunks: PYQ chunks for style learning
        search_queries: Google Search queries
        
    Returns:
        Complete prompt string ready for LLM
    """
    # 1. Get Subject-Specific System Prompt
    system_prompt = get_system_prompt(subject)
    
    # 2. Get Subject-Specific Cognitive Framework and append Patterns
    cognitive_framework = get_cognitive_framework(subject)
    patterns_text = format_patterns_for_prompt(subject)
    
    if patterns_text:
        cognitive_framework += "\n\n" + patterns_text

    # Pass full contexts without trimming (enforced by bucket selection logic)
    content_text = retrieved_static_text if retrieved_static_text else "No content material available."
    
    # Format search queries if provided
    research_instruction = ""
    if search_queries:
        research_instruction = """### STEP 0: EXTRACT ATOMIC FACTUAL UNITS (CRITICAL REASONING STEP)

Before generating any questions, you MUST extract and return a JSON array of `factual_units`. 
A **Factual Unit** is a standalone, individually verifiable historical, geographical, or economic fact derived from your search results or the provided context.

Follow these rules for Factual Units:
- Extract 7-10 dense factual units.
- They serve as context anchors for the question stems.
- They are the "Ground Truth" used to evaluate the correctness of your options.
- Use them to create distractors that are grounded in actual content (e.g., swapping a dynasty name or a current data point).

### STEP 1: CONDUCT LIVE RESEARCH (CRITICAL FOR GROUNDING)

You MUST use your Google Search tool to research the following queries. These queries target BOTH latest developments (2024-2025) and static core concepts from authoritative sources (NCERT, Gov reports).

**SEARCH QUERIES TO EXECUTE:**
"""
        for i, sq in enumerate(search_queries):
            research_instruction += f"{i+1}. {sq['q']}\n"
        
        research_instruction += """
**AFTER SEARCHING**, synthesize your findings into "Verified Factual Units" as described in STEP 0.

### STEP 2: INTEGRATE CURRENT AFFAIRS WITH STATIC CONTENT

**IMPORTANT**: You MUST create questions that integrate BOTH:
1. **Static Knowledge** - Subject concepts, processes, theories (Verified via search or context)
2. **Current Affairs** - Recent events, policies, data (Verified via search)

"""
        ca_available = bool(retrieved_current_affairs)
        research_instruction += get_question_type_quota(num_questions, ca_available) + "\n"
    
    # Format PYQ chunks for style learning
    pyq_examples_text = ""
    if pyq_chunks:
        for i, chunk in enumerate(pyq_chunks):
            content = chunk.get("content", "").strip()
            meta = chunk.get("metadata", {})
            major = meta.get("major_domain", "General")
            sub = meta.get("sub_domain", "General")
            
            if content:
                pyq_examples_text += f"Example {i+1} [Topic: {major} > {sub}]:\n{content}\n---\n"
    
    if not pyq_examples_text:
        pyq_examples_text = "No style learning examples available."
    
    prompt = f"""SYSTEM:

{system_prompt}

---

FRAMEWORK:

{cognitive_framework}


{research_instruction}

CONTEXT SOURCES (Factual Knowledge - 70%):

{content_text}

---

PYQ STYLE EXAMPLES (Style Learning):

{pyq_examples_text}

---

TASK:

Generate {num_questions} UPSC-style MCQs on the topic: {topic}.

You MUST return a JSON object with two main keys:
1. "factual_units": An array of at least 8 independently verifiable atomic facts extracted from your search and context.
2. "questions": An array of questions derived from those units.

Each question must follow this structure:

{{
  "factual_units": ["Fact 1...", "Fact 2...", "..."],
  "questions": [
    {{
      "question": "...",
      "options": ["(a)...", "(b)...", "(c)...", "(d)..."],
      "correct_answer": "A" | "B" | "C" | "D",
      "explanation": "...",
      "source": {{"topic": "...", "sub_domain": "..."}}
    }},
    ...
  ]
}}

Ensure:

• Follow the QUESTION TYPE QUOTA exactly (see STEP 2 above if search queries were provided).
• Avoid keyword or fact repetition.
• Tone and conciseness must match authentic UPSC.
• Each explanation justifies correct and incorrect options.

CRITICAL FORMATTING RULES:

1. For Multi-Statement questions ("Consider the following statements"):
   - The "question" field MUST include ALL statements WITHIN it.
   - Format: "Consider the following statements regarding [topic]:\\n1. [First statement]\\n2. [Second statement]\\n3. [Third statement]\\n\\nWhich of the following is correct?"
   - DO NOT put statements in a separate field - they must be part of the question text.

2. For Assertion-Reason questions:
   - Format: "Assertion (A): [Assertion text]\\nReason (R): [Reason text]\\n\\nWhich of the following is correct?"
   - Both Assertion and Reason MUST be in the question field.

3. For Match-the-Pair questions:
   - Format: "Match the following:\\nList I\\n1. [Item 1]\\n2. [Item 2]\\n3. [Item 3]\\n\\nList II\\n(a) [Match 1]\\n(b) [Match 2]\\n(c) [Match 3]\\n\\nSelect the correct answer:"
   - All pairs and lists MUST be in the question field.

IMPORTANT: The "options" field must be a JSON array of strings, not a dictionary.
Example: "options": ["(a) Option 1", "(b) Option 2", "(c) Option 3", "(d) Option 4"]
NOT: "options": {{"A": "Option 1", "B": "Option 2"}}

**CRITICAL JSON OUTPUT REQUIREMENT:**
You MUST return ONLY valid JSON with NO markdown formatting, NO code blocks, NO explanatory text.
Start your response with {{ and end with }}.
Do NOT wrap the JSON in ```json or any other markers."""
    
    return prompt.strip()
    
    return prompt.strip()
