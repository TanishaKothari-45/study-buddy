# processing/selector.py

from ..config import FINAL_ARTICLE_COUNT, FINAL_EDITORIAL_COUNT

def select_articles_and_editorials(articles):
    articles_only = [a for a in articles if a["type"] == "article"]
    editorials_only = [a for a in articles if a["type"] == "editorial"]

    # sort articles by (corroboration, topic_score, recency)
    articles_only.sort(
        key=lambda a: (a.get("corroborated", False), a.get("topic_score", 0)),
        reverse=True
    )

    # editorials sorted primarily by topic score
    editorials_only.sort(
        key=lambda a: (a.get("topic_score", 0)),
        reverse=True
    )

    return (
        articles_only[:FINAL_ARTICLE_COUNT],
        editorials_only[:FINAL_EDITORIAL_COUNT]
    )
