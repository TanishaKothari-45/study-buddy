#!/usr/bin/env python3
"""
detect_pipeline_intent.py

Hook script fired by UserPromptSubmit in settings.json.
Detects pipeline generation intent from user prompt.
Prints status notice and logs the intent.

Exit code: 0 (always succeeds, doesn't block the prompt)
"""

import sys
import json
import re
from datetime import datetime
from pathlib import Path

# Subject mapping
SUBJECT_MAP = {
    "polity": "Polity",
    "geography": "Geography",
    "history": "History",
    "economy": "Economy",
    "environment": "Environment",
    "science": "Science & Technology",
    "tech": "Science & Technology",
}

# Patterns to extract domain from prompt
DOMAIN_PATTERNS = [
    r"for\s+([a-z\s&]+?)(?:\s+domain|\s+subject|\s+concept|\s+pool|\s*$)",
    r"add\s+([a-z\s&]+?)\s+to",
    r"(?:pools?|traps?)\s+(?:for|in)\s+([a-z\s&]+?)(?:\s|$)",
    r"(?:oceanography|geomorphology|climatology|constitutional|international|ancient|medieval|modern|agriculture|industry)",
]

DOMAINS_MAP = {
    "oceanography": "Oceanography",
    "geomorphology": "Geomorphology",
    "climatology": "Climatology",
    "constitutional": "Constitutional Law",
    "international": "International Law",
    "ancient": "Ancient India",
    "medieval": "Medieval India",
    "modern": "Modern India",
    "agriculture": "Agriculture",
    "industry": "Industry",
}


def extract_intent(prompt):
    """Extract subject and domain from user prompt."""
    prompt_lower = prompt.lower()
    subject = "Geography"  # default
    domain = None

    # Detect subject
    for key, value in SUBJECT_MAP.items():
        if key in prompt_lower:
            subject = value
            break

    # Detect domain
    for pattern in DOMAIN_PATTERNS:
        m = re.search(pattern, prompt_lower)
        if m:
            extracted = m.group(1).strip() if m.lastindex else m.group(0)
            # Try to match against DOMAINS_MAP
            for domain_key, domain_value in DOMAINS_MAP.items():
                if domain_key in extracted.lower():
                    domain = domain_value
                    break
            if domain is None and extracted:
                domain = extracted.title()
            break

    return subject, domain


def main():
    # Get prompt from command line
    prompt = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else ""

    if not prompt:
        sys.exit(0)

    subject, domain = extract_intent(prompt)

    # Print notice (visible in Claude Code to user)
    print(f"[PIPELINE AGENT] 🔍 Detected intent: {subject}", end="")
    if domain:
        print(f" > {domain}")
    else:
        print()

    print(f"[PIPELINE AGENT] 🔄 Background agent will run PYQ analysis and update JSON files...")
    print(f"[PIPELINE AGENT] 💬 You can continue working — agent will notify on completion.")

    # Log intent (append to JSONL log)
    try:
        log_path = Path(__file__).parent / "agent_intent_log.jsonl"
        with open(log_path, "a") as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "prompt": prompt[:200],  # Truncate for privacy
                "detected_subject": subject,
                "detected_domain": domain,
                "status": "intent_detected"
            }, f)
            f.write("\n")
    except Exception as e:
        # Silently fail on log write, don't block the prompt
        pass

    sys.exit(0)


if __name__ == "__main__":
    main()
