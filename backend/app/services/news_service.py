import asyncio
import os
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx

NEWSAPI_AI_URL = "https://eventregistry.org/api/v1/article/getArticles"
NEWSAPI_ARTICLE_BODY_LEN = 1700
REQUIRED_ARTICLE_FIELDS = (
    "title",
    "description",
    "content",
    "source",
    "url",
    "published_at",
)
CANDIDATES_PER_TOPIC_BY_DURATION = {
    "short": 10,
    "normal": 15,
    "long": 25,
}
CANDIDATES_PER_TOPIC = CANDIDATES_PER_TOPIC_BY_DURATION["normal"]
MAX_SELECTED_ARTICLES = 3
TITLE_RELEVANCE_STOPWORDS = {
    "a",
    "an",
    "and",
    "as",
    "for",
    "in",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}


class NewsServiceError(RuntimeError):
    pass


TRACKING_PARAMS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
}


def recency_window_days(frequency: str, generation_type: str = "manual") -> int:
    if generation_type == "manual":
        return 2
    if frequency == "daily":
        return 1
    if frequency == "weekly":
        return 7
    return 2


def candidate_count_for_duration(duration_label: str) -> int:
    return CANDIDATES_PER_TOPIC_BY_DURATION.get(
        duration_label,
        CANDIDATES_PER_TOPIC_BY_DURATION["normal"],
    )


def resolve_date_window(
    window_days: int,
    now: datetime | None = None,
) -> tuple[str, str]:
    current_time = now or datetime.now(timezone.utc)
    date_start = (current_time - timedelta(days=window_days)).date().isoformat()
    date_end = current_time.date().isoformat()
    return date_start, date_end


def _is_tracking_param(name: str) -> bool:
    clean = name.lower()
    return clean.startswith("utm_") or clean in TRACKING_PARAMS


def _normalize_url_for_tracking(url: str) -> str:
    try:
        parsed = urlparse(url)
    except ValueError:
        return url.strip().lower()
    if not parsed.scheme or not parsed.netloc:
        return url.strip().lower()
    query = urlencode(
        [
            (k, v)
            for k, v in parse_qsl(parsed.query, keep_blank_values=True)
            if not _is_tracking_param(k)
        ]
    )
    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path.rstrip("/"),
            "",
            query,
            "",
        )
    )


async def fetch_articles_for_interests(
    interests: list[str],
    articles_count: int = CANDIDATES_PER_TOPIC,
    window_days: int | None = None,
) -> list[dict]:
    selected_interests = [interest.strip() for interest in interests if interest.strip()]
    if not selected_interests:
        raise NewsServiceError("At least one interest is required to fetch news.")

    api_key = os.getenv("NEWS_API_KEY", "")
    if not api_key:
        raise NewsServiceError("NEWS_API_KEY is required for real podcast generation.")

    resolved_window_days = window_days if window_days is not None else 2
    date_start, date_end = resolve_date_window(resolved_window_days)

    async with httpx.AsyncClient(timeout=20) as client:
        results = await asyncio.gather(
            *[
                _fetch_newsapi_ai_query(
                    client,
                    api_key,
                    interest,
                    articles_count=articles_count,
                    date_start=date_start,
                    date_end=date_end,
                )
                for interest in selected_interests
            ],
            return_exceptions=True,
        )

    all_articles: list[dict] = []
    errors: list[str] = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            errors.append(f"interest '{selected_interests[i]}': {result}")
        else:
            all_articles.extend(result)

    if errors:
        raise NewsServiceError(
            "NewsAPI.ai retrieval failed: " + " | ".join(errors[:3])
        )

    return all_articles


async def fetch_articles(topic: str) -> list[dict]:
    selected_topic = topic.strip()
    if not selected_topic:
        raise NewsServiceError("A selected topic is required to fetch news.")

    raw_articles = await fetch_articles_for_interests(
        [selected_topic],
        articles_count=candidate_count_for_duration("long"),
        window_days=recency_window_days("manual", "manual"),
    )
    prepared = _prepare_articles(raw_articles, selected_topic)
    if not prepared:
        raise NewsServiceError(f"No usable articles found for topic: {selected_topic}")
    return prepared[:MAX_SELECTED_ARTICLES]


async def _fetch_newsapi_ai_query(
    client: httpx.AsyncClient,
    api_key: str,
    query: str,
    articles_count: int = CANDIDATES_PER_TOPIC,
    window_days: int | None = None,
    date_start: str | None = None,
    date_end: str | None = None,
) -> list[dict]:
    if date_start is None or date_end is None:
        date_start, date_end = resolve_date_window(window_days or 2)

    payload = {
        "apiKey": api_key,
        "action": "getArticles",
        "keyword": query,
        "lang": "eng",
        "articlesPage": 1,
        "articlesCount": articles_count,
        "articlesSortBy": "socialScore",
        "articlesSortByAsc": False,
        "articlesArticleBodyLen": NEWSAPI_ARTICLE_BODY_LEN,
        "resultType": "articles",
        "dataType": ["news", "blog"],
        "dateStart": date_start,
        "dateEnd": date_end,
    }

    for attempt in range(2):
        try:
            response = await client.post(
                NEWSAPI_AI_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
        except httpx.TimeoutException as exc:
            raise NewsServiceError(
                f"NewsAPI.ai query '{query}' timed out after {client.timeout!s}."
            ) from exc
        except httpx.HTTPError as exc:
            detail = str(exc) or exc.__class__.__name__
            raise NewsServiceError(
                f"NewsAPI.ai query '{query}' request failed: {detail}"
            ) from exc
        if response.status_code == 429 and attempt == 0:
            await asyncio.sleep(1.5)
            continue
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = response.text.strip().replace("\n", " ")[:300]
            raise NewsServiceError(
                f"NewsAPI.ai query '{query}' failed with HTTP "
                f"{response.status_code}: {detail}"
            ) from exc
        break

    try:
        data = response.json()
    except ValueError as exc:
        raise NewsServiceError(
            f"NewsAPI.ai query '{query}' returned invalid JSON."
        ) from exc

    if "error" in data:
        raise NewsServiceError(
            f"NewsAPI.ai query '{query}' failed: {str(data['error'])[:300]}"
        )

    articles = data.get("articles", {}).get("results", [])
    return [
        _normalize_newsapi_ai_article(article, query)
        for article in articles
        if isinstance(article, dict)
    ]


def _normalize_newsapi_ai_article(article: dict, topic: str) -> dict:
    source = article.get("source", {})
    if isinstance(source, dict):
        source_name = source.get("title") or source.get("uri") or ""
    else:
        source_name = str(source or "")

    content = _clean_text(
        article.get("body")
        or article.get("content")
        or article.get("articleBody")
        or ""
    )[:NEWSAPI_ARTICLE_BODY_LEN].strip()
    raw_description = _clean_text(
        article.get("description")
        or article.get("summary")
        or ""
    )
    description = raw_description or _short_description(content)

    return {
        "title": _clean_text(article.get("title") or ""),
        "description": description,
        "content": content,
        "source": _clean_text(source_name),
        "url": str(article.get("url") or "").strip(),
        "published_at": (
            article.get("dateTimePub")
            or article.get("dateTime")
            or article.get("date")
            or ""
        ),
        "provider": "NewsAPI.ai",
        "query": topic,
        "topic": topic,
    }


def has_required_article_fields(article: dict) -> bool:
    title = str(article.get("title", "")).strip()
    description = str(article.get("description", "")).strip()
    content = str(article.get("content", "")).strip()
    source = str(article.get("source", "")).strip()
    url = str(article.get("url", "")).strip()
    published_at = str(article.get("published_at", "")).strip()

    return (
        len(title) >= 12
        and len(description) >= 40
        and len(content) >= 300
        and bool(source)
        and bool(url)
        and bool(published_at)
        and _valid_url(url)
        and _timestamp(published_at) > 0
    )


def filter_complete_articles(articles: list[dict]) -> list[dict]:
    complete: list[dict] = []
    for article in articles:
        if not has_required_article_fields(article):
            continue
        complete.append(
            {
                **article,
                "title": str(article.get("title", "")).strip(),
                "description": str(article.get("description", "")).strip(),
                "content": str(article.get("content", "")).strip(),
                "source": str(article.get("source", "")).strip(),
                "url": str(article.get("url", "")).strip(),
                "published_at": str(article.get("published_at", "")).strip(),
                "provider": str(article.get("provider", "")).strip(),
                "query": str(article.get("query", "")).strip(),
                "topic": str(article.get("topic", "")).strip(),
            }
        )
    return complete


def title_matches_interest(article: dict, interest: str) -> bool:
    title_token_set = set(_title_tokens(str(article.get("title", ""))))
    meaningful_tokens = [
        token for token in _title_tokens(interest)
        if token not in TITLE_RELEVANCE_STOPWORDS
    ]
    if not meaningful_tokens:
        return False
    return all(token in title_token_set for token in meaningful_tokens)


def filter_title_relevant_articles(
    articles: list[dict],
    interests: list[str],
) -> list[dict]:
    interest_by_key = {
        _interest_key(interest): interest
        for interest in interests
        if _interest_key(interest)
    }
    filtered: list[dict] = []
    for article in articles:
        matching_interest = _article_interest(article, interest_by_key)
        if matching_interest and title_matches_interest(article, matching_interest):
            filtered.append(article)
    return filtered


def deduplicate_articles_by_url(articles: list[dict]) -> tuple[list[dict], int]:
    seen_urls: set[str] = set()
    deduped: list[dict] = []
    duplicates = 0
    for article in articles:
        normalized_url = _canonical_url(article.get("url", ""))
        if not normalized_url:
            continue
        if normalized_url in seen_urls:
            duplicates += 1
            continue
        seen_urls.add(normalized_url)
        deduped.append(article)
    return deduped, duplicates


def _prepare_articles(articles: list[dict], topic: str | None = None) -> list[dict]:
    _ = topic
    deduped, _duplicates = deduplicate_articles_by_url(
        filter_complete_articles(articles)
    )
    return deduped


def _filter_articles(
    articles: list[dict],
    topic: str | None = None,
    require_relevance: bool = False,
) -> list[dict]:
    _ = topic
    _ = require_relevance
    return filter_complete_articles(articles)


def _dedupe_articles(articles: list[dict]) -> list[dict]:
    deduped, _duplicates = deduplicate_articles_by_url(articles)
    return deduped


def _select_diverse_articles(articles: list[dict], limit: int) -> list[dict]:
    return articles[:limit]


def _article_interest(article: dict, interest_by_key: dict[str, str]) -> str:
    for field in ("topic", "query"):
        key = _interest_key(str(article.get(field, "")))
        if key in interest_by_key:
            return interest_by_key[key]
    return ""


def _interest_key(value: str) -> str:
    return " ".join(_title_tokens(value))


def _title_tokens(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", value.lower())


def _canonical_url(url: str) -> str:
    normalized = _normalize_url_for_tracking(url)
    return normalized if _valid_url(normalized) else ""


def _valid_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _timestamp(raw_date: str) -> float:
    if not raw_date:
        return 0
    try:
        value = raw_date.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except ValueError:
        return 0


def _strip_html(value: str) -> str:
    return re.sub(r"<[^>]+>", " ", str(value)).replace("&nbsp;", " ").strip()


def _clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", _strip_html(str(value or ""))).strip()


def _short_description(value: str) -> str:
    clean = _clean_text(value)
    if len(clean) <= 450:
        return clean
    sentence_end = clean.find(". ", 180, 450)
    if sentence_end != -1:
        return clean[: sentence_end + 1]
    return clean[:447].rstrip() + "..."


async def check_news_api_key() -> bool:
    api_key = os.getenv("NEWS_API_KEY", "")
    if not api_key:
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            articles = await _fetch_newsapi_ai_query(
                client,
                api_key,
                "technology",
                articles_count=1,
                window_days=2,
            )
            return len(articles) > 0
    except Exception:
        return False
