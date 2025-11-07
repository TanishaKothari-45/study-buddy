"""
UPSC PYQ Pattern Loader
-----------------------
Loads and filters UPSC Prelims Geography PYQ examples for few-shot prompting.

Use this with your 'geography_prelims_pyq_patterns.json' file.
"""

import json
import os
import random
from typing import List, Dict, Optional
from pathlib import Path

# Default path (adjust if needed)
# Path relative to this file: backend/app/utils/upsc_patterns/loader.py
# JSON file is at: study-buddy/geography_prelims_pyq_patterns.json
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent
DEFAULT_PATH = BASE_DIR / "geography_prelims_pyq_patterns.json"

def load_pattern_data(file_path: Optional[str] = None) -> Dict:
    """Load the entire pattern dataset from JSON."""
    path = Path(file_path) if file_path else DEFAULT_PATH
    path = path.resolve()
    
    if not path.exists():
        raise FileNotFoundError(f"PYQ pattern file not found at: {path}")
    
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def get_all_patterns(file_path: Optional[str] = None) -> List[Dict]:
    """Return list of all pattern definitions."""
    data = load_pattern_data(file_path)
    return data.get("patterns", [])

def get_pattern(pattern_id: str, file_path: Optional[str] = None) -> Optional[Dict]:
    """Return a specific pattern dictionary by its ID (Q1–Q6)."""
    patterns = get_all_patterns(file_path)
    for p in patterns:
        if p["id"].lower() == pattern_id.lower():
            return p
    return None

def get_examples(topic: Optional[str] = None, pattern: Optional[str] = None, n: int = 3, file_path: Optional[str] = None) -> List[Dict]:
    """
    Retrieve few-shot examples filtered by pattern and/or topic.
    
    Args:
        topic: Keyword to match topic names (case-insensitive).
        pattern: Pattern ID (e.g., 'Q2' for multi-statement).
        n: Number of examples to return.
        file_path: Optional custom path to dataset.
    
    Returns:
        List of example dictionaries [{question, options, answer, topic, year}, ...]
    """
    data = load_pattern_data(file_path)
    patterns = data.get("patterns", [])
    matches = []
    
    for p in patterns:
        if pattern and p["id"].lower() != pattern.lower():
            continue
        for ex in p["example_questions"]:
            if topic:
                if topic.lower() in ex.get("topic", "").lower():
                    matches.append(ex)
            else:
                matches.append(ex)
    
    if not matches:
        # fallback to random from all
        for p in patterns:
            matches.extend(p["example_questions"])
    
    random.shuffle(matches)
    return matches[:n]

def format_fewshot(examples: List[Dict], pattern_title: Optional[str] = None) -> str:
    """
    Convert example dictionaries into formatted few-shot text for prompting.
    
    Args:
        examples: list of examples from get_examples()
        pattern_title: Optional name of the pattern
    
    Returns:
        Formatted string for LLM prompt
    """
    lines = []
    for i, ex in enumerate(examples):
        q_block = (
            f"Example {i+1}{f' ({pattern_title})' if pattern_title else ''}:\n"
            f"{ex['question']}\n" +
            "\n".join(ex["options"]) +
            f"\n✅ Correct Answer: ({ex['answer']})\n📘 Topic: {ex['topic']} (Year: {ex['year']})"
        )
        lines.append(q_block)
    return "\n\n---\n\n".join(lines)

# ---------- Quick Test ----------
if __name__ == "__main__":
    examples = get_examples(topic="Monsoon", pattern="Q2", n=2)
    print(format_fewshot(examples, "Multi-Statement Evaluation"))

