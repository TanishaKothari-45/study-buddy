# processing/summary_builder.py

import re

NUMBER_REGEX = r"(₹\d+(\.\d+)?|\$?\d+(\.\d+)?%?)"

def extract_lead(article):
    text = (
        article.get("content") or
        article.get("description") or
        article.get("title") or ""
    )
    # take first 1–2 sentences max
    parts = re.split(r'[.!?]', text)
    return ". ".join(parts[:2])

def make_one_liner(article):
    lead = extract_lead(article)
    # if numeric fact appears, include verbatim
    match = re.search(NUMBER_REGEX, lead)
    if match:
        num = match.group(0)
        return f"{lead.strip()[:120]} ({num})"

    return lead.strip()[:120]


def extract_editorial_snippet(article):
    text = (
        article.get("content") or
        article.get("description") or ""
    )
    # extract 3–5 sentences max
    parts = re.split(r'[.!?]', text)
    return ". ".join(parts[:5])
