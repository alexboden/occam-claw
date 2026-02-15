from datetime import datetime, timezone
from ddgs import DDGS


def get_current_datetime() -> str:
    now = datetime.now(timezone.utc).astimezone()
    return now.strftime("%A, %B %d, %Y %I:%M %p %Z")


def web_search(query: str, max_results: int = 5) -> list[dict]:
    with DDGS() as ddgs:
        results = list(ddgs.text(query, max_results=max_results))
    return [{"title": r["title"], "url": r["href"], "snippet": r["body"]} for r in results]
