"""
subject_config.py — Per-subject blueprint configuration

Derived from:
  • trap_registry (ca_linkage_rate, difficulty_distribution per subject)
  • PYQ pattern JSON files (dominant question types per subject)

Each SubjectConfig is the single source of truth for how many of each type
to include in a blueprint, and what CA ratio to target.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass
class QuestionTypeRange:
    """Min–max range for a question type in a 20-question blueprint."""
    min: int
    max: int


@dataclass
class DifficultyDistribution:
    """Absolute counts for a 20-question blueprint."""
    easy: int
    medium: int
    hard: int


@dataclass
class SubjectConfig:
    """Complete blueprint configuration for one subject."""
    subject: str                            # canonical name matching trap file
    trap_file: str                          # e.g. "traps_geography.json"
    pyq_file: str                           # e.g. "geography_prelims_pyq_patterns.json"
    ca_linkage_rate: float                  # fraction → multiply by N to get CA count
    difficulty: DifficultyDistribution
    # question type slug → (min, max) for 20Q blueprints
    question_type_ranges: Dict[str, QuestionTypeRange] = field(default_factory=dict)


# ── Per-subject configs ────────────────────────────────────────────────────────
# ca_linkage_rate → from _subject_patterns.ca_linkage_rate in trap registry
# difficulty split → from _subject_patterns.difficulty_split (× 20)
# question_type_ranges → derived from dominant_question_types + PYQ patterns

SUBJECT_CONFIGS: Dict[str, SubjectConfig] = {

    "Geography": SubjectConfig(
        subject="Geography",
        trap_file="traps_geography.json",
        pyq_file="geography_prelims_pyq_patterns.json",
        ca_linkage_rate=0.30,
        difficulty=DifficultyDistribution(easy=5, medium=10, hard=5),
        question_type_ranges={
            "multi_statement":  QuestionTypeRange(min=6, max=9),
            "match_pair":       QuestionTypeRange(min=3, max=5),
            "assertion_reason": QuestionTypeRange(min=2, max=4),
            "direct_fact":      QuestionTypeRange(min=2, max=3),
            "spatial":          QuestionTypeRange(min=1, max=2),
        },
    ),

    "History": SubjectConfig(
        subject="History",
        trap_file="traps_history.json",
        pyq_file="history_prelims_pyq_patterns.json",
        ca_linkage_rate=0.15,
        difficulty=DifficultyDistribution(easy=6, medium=9, hard=5),
        question_type_ranges={
            "multi_statement":  QuestionTypeRange(min=5, max=8),
            "match_pair":       QuestionTypeRange(min=3, max=5),
            "assertion_reason": QuestionTypeRange(min=2, max=4),
            "direct_fact":      QuestionTypeRange(min=2, max=4),
            "chronology":       QuestionTypeRange(min=1, max=2),
        },
    ),

    "Polity": SubjectConfig(
        subject="Polity",
        trap_file="traps_polity.json",
        pyq_file="polity_prelims_pyq_patterns.json",
        ca_linkage_rate=0.40,
        difficulty=DifficultyDistribution(easy=4, medium=11, hard=5),
        question_type_ranges={
            "multi_statement":  QuestionTypeRange(min=7, max=10),
            "assertion_reason": QuestionTypeRange(min=3, max=5),
            "match_pair":       QuestionTypeRange(min=2, max=4),
            "direct_fact":      QuestionTypeRange(min=2, max=4),
        },
    ),

    "Economy": SubjectConfig(
        subject="Economy",
        trap_file="traps_economy.json",
        pyq_file="economy_prelims_pyq_patterns.json",
        ca_linkage_rate=0.50,
        difficulty=DifficultyDistribution(easy=4, medium=10, hard=6),
        question_type_ranges={
            "multi_statement":  QuestionTypeRange(min=6, max=9),
            "direct_fact":      QuestionTypeRange(min=3, max=5),
            "assertion_reason": QuestionTypeRange(min=2, max=4),
            "match_pair":       QuestionTypeRange(min=1, max=3),
            "data_based":       QuestionTypeRange(min=1, max=2),
        },
    ),

    "Environment": SubjectConfig(
        subject="Environment",
        trap_file="traps_environment.json",
        pyq_file="environment_ecology_prelims_pyq_patterns.json",
        ca_linkage_rate=0.45,
        difficulty=DifficultyDistribution(easy=5, medium=10, hard=5),
        question_type_ranges={
            "multi_statement":  QuestionTypeRange(min=6, max=9),
            "match_pair":       QuestionTypeRange(min=3, max=5),
            "assertion_reason": QuestionTypeRange(min=2, max=4),
            "direct_fact":      QuestionTypeRange(min=2, max=3),
        },
    ),

    "Science & Technology": SubjectConfig(
        subject="Science & Technology",
        trap_file="traps_science_technology.json",
        pyq_file="science_technology_prelims_pyq_patterns.json",
        ca_linkage_rate=0.60,
        difficulty=DifficultyDistribution(easy=4, medium=9, hard=7),
        question_type_ranges={
            "multi_statement":  QuestionTypeRange(min=6, max=9),
            "direct_fact":      QuestionTypeRange(min=3, max=5),
            "assertion_reason": QuestionTypeRange(min=2, max=4),
            "match_pair":       QuestionTypeRange(min=1, max=3),
            "data_based":       QuestionTypeRange(min=1, max=2),
        },
    ),
}

# Normalisation aliases → canonical key
_ALIASES: Dict[str, str] = {
    "geography":                "Geography",
    "history":                  "History",
    "polity":                   "Polity",
    "polity and governance":    "Polity",
    "economy":                  "Economy",
    "economics":                "Economy",
    "environment":              "Environment",
    "environment & ecology":    "Environment",
    "environment and ecology":  "Environment",
    "science & technology":     "Science & Technology",
    "science & tech":           "Science & Technology",
    "science_technology":       "Science & Technology",
    "science and technology":   "Science & Technology",
    "general":                  "Geography",   # fallback
}


def get_subject_config(subject: str) -> SubjectConfig:
    """Return SubjectConfig for the given subject string (case-insensitive)."""
    key = _ALIASES.get(subject.lower().strip(), subject)
    return SUBJECT_CONFIGS.get(key, SUBJECT_CONFIGS["Geography"])
