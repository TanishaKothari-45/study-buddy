# processing/classifier.py

EDITORIAL_KEYWORDS = [
    "opinion", "editorial", "analysis", "commentary",
    "viewpoint", "explained"
]

TOPIC_KEYWORDS = []  # dynamically set

def set_topic_keywords(keywords):
    global TOPIC_KEYWORDS
    TOPIC_KEYWORDS = keywords

def detect_type(article):
    title = (article.get("title") or "").lower()
    url = (article.get("url") or "").lower()

    if any(k in title for k in EDITORIAL_KEYWORDS):
        return "editorial"

    if any(k in url for k in EDITORIAL_KEYWORDS):
        return "editorial"

    return "article"


def topic_score(article):
    text = " ".join([
        article.get("title", ""),
        article.get("description", ""),
        article.get("content", "")
    ]).lower()

    score = 0
    for k in TOPIC_KEYWORDS:
        score += text.count(k.lower())

    return score


def mark_corroboration(articles):
    seen_titles = {}
    for a in articles:
        t = (a.get("title") or "").strip().lower()
        if t not in seen_titles:
            seen_titles[t] = []
        seen_titles[t].append(a)

    for group in seen_titles.values():
        if len(group) >= 2:
            for a in group:
                a["corroborated"] = True
        else:
            for a in group:
                a["corroborated"] = False

    return articles
