import logging
import uuid
from time import perf_counter
from datetime import datetime, timezone
from . import news_service, script_service, tts_service
from .cost_estimates import estimate_elevenlabs_cost
from ..repositories import episode_repository
from ..models import (
    GenerateRequest,
    EpisodeResponse,
    ArticleSource,
    ToolUsageItem,
)


logger = logging.getLogger(__name__)

TARGET_ARTICLES_BY_DURATION = {
    "short": 1,
    "normal": 2,
    "long": 3,
}

class NoNewArticlesError(RuntimeError):
    pass


def elapsed_ms(start: float) -> int:
    return int((perf_counter() - start) * 1000)


def _build_tool_usage(
    newsapi_calls: int,
    openai_usage: list[script_service.OpenAIUsage],
    elevenlabs_calls: int,
    elevenlabs_chars: int,
    elevenlabs_purpose: str,
) -> list[ToolUsageItem]:
    elevenlabs_cost = estimate_elevenlabs_cost(elevenlabs_chars)
    tools = [
        ToolUsageItem(
            tool_name="news",
            purpose="Article retrieval",
            calls=newsapi_calls,
            usage_unit="requests",
            usage_amount=float(newsapi_calls),
            estimated_cost_usd=0.0,
        ),
    ]
    tools.extend(
        ToolUsageItem(
            tool_name="openai",
            purpose=usage.purpose,
            calls=1,
            usage_unit="tokens",
            usage_amount=float(usage.input_tokens + usage.output_tokens),
            estimated_cost_usd=usage.estimated_cost_usd,
        )
        for usage in openai_usage
    )
    tools.append(
        ToolUsageItem(
            tool_name="elevenlabs",
            purpose=f"{elevenlabs_purpose} (eleven_multilingual_v2 estimate)",
            calls=elevenlabs_calls,
            usage_unit="characters",
            usage_amount=float(elevenlabs_chars),
            estimated_cost_usd=elevenlabs_cost,
        )
    )
    return tools


def _target_article_count(duration_label: str) -> int:
    return TARGET_ARTICLES_BY_DURATION.get(
        duration_label,
        TARGET_ARTICLES_BY_DURATION["normal"],
    )


def _select_balanced_articles(
    candidates: list[dict],
    interests: list[str],
    target_count: int,
) -> list[dict]:
    if not candidates or target_count <= 0:
        return []

    selected: list[dict] = []
    selected_urls: set[str] = set()

    for topic in interests:
        topic_key = topic.lower()
        topic_candidates = [
            article for article in candidates
            if str(article.get("topic", "")).lower() == topic_key
        ]
        if not topic_candidates:
            continue
        article = topic_candidates[0]
        url = news_service._normalize_url_for_tracking(article.get("url", ""))
        if url and url not in selected_urls:
            selected.append(article)
            selected_urls.add(url)
        if len(selected) >= target_count:
            return selected

    for article in candidates:
        url = news_service._normalize_url_for_tracking(article.get("url", ""))
        if not url or url in selected_urls:
            continue
        selected.append(article)
        selected_urls.add(url)
        if len(selected) >= target_count:
            break

    return selected


async def generate_podcast(req: GenerateRequest) -> EpisodeResponse:
    start_time = perf_counter()
    workflow_timings: dict[str, int] = {}
    interests = req.resolved_interests
    duration_label = req.resolved_duration_label
    duration_minutes = req.resolved_duration_minutes
    target_article_count = _target_article_count(duration_label)

    selected_window_days = news_service.recency_window_days(
        req.frequency,
        req.generation_type,
    )
    candidates_per_topic = news_service.candidate_count_for_duration(duration_label)
    news_start = perf_counter()
    raw_articles = await news_service.fetch_articles_for_interests(
        interests,
        articles_count=candidates_per_topic,
        window_days=selected_window_days,
    )
    workflow_timings["news_retrieval_ms"] = elapsed_ms(news_start)
    newsapi_calls = len(interests)
    fetched_count = len(raw_articles)

    filtering_start = perf_counter()
    seen_urls = episode_repository.get_seen_urls(req.user_id)
    complete_articles = news_service.filter_complete_articles(raw_articles)
    complete_count = len(complete_articles)
    invalid_filtered_count = fetched_count - complete_count
    deduped, _duplicates = news_service.deduplicate_articles_by_url(
        complete_articles
    )
    deduped_count = len(deduped)
    duplicate_filtered_count = complete_count - deduped_count
    title_relevant = news_service.filter_title_relevant_articles(
        deduped,
        interests,
    )
    title_relevant_count = len(title_relevant)
    title_filtered_count = deduped_count - title_relevant_count

    unseen: list[dict] = []
    for article in title_relevant:
        url = news_service._normalize_url_for_tracking(article.get("url", ""))
        if url and url in seen_urls:
            continue
        unseen.append(article)
    unseen_count = len(unseen)
    seen_filtered_count = title_relevant_count - unseen_count

    selected = _select_balanced_articles(
        unseen,
        interests,
        target_article_count,
    )
    used_count = len(selected)
    workflow_timings["article_filtering_ms"] = elapsed_ms(filtering_start)

    logger.info(
        "[podcast] article_selection user_id=%s interests=%s window_days=%s "
        "candidates_per_topic=%s fetched_count=%s complete_count=%s "
        "deduped_count=%s title_relevant_count=%s seen_filtered_count=%s usable_count=%s "
        "selected_count=%s",
        req.user_id,
        interests,
        selected_window_days,
        candidates_per_topic,
        fetched_count,
        complete_count,
        deduped_count,
        title_relevant_count,
        seen_filtered_count,
        unseen_count,
        used_count,
    )

    if not selected:
        raise NoNewArticlesError(
            "No usable articles found for the selected interests. "
            "Try again later or choose a broader topic."
        )

    script_result = await script_service.generate_script_with_timings(
        selected,
        interests=interests,
        tone=req.tone,
        duration_label=duration_label,
        duration_minutes=duration_minutes,
        speaker_mode=req.speaker_mode,
    )
    script = script_result.script
    workflow_timings.update(script_result.timings_ms)

    title = script_service._generate_title(selected)
    summary = script_service._generate_summary(selected)

    tts_start = perf_counter()
    try:
        audio_result = await tts_service.generate_audio(
            script,
            speaker_mode=req.speaker_mode,
            turns=script_result.turns,
        )
        audio_url = audio_result.audio_url
        status = audio_result.status
        error_message = audio_result.error_message
        elevenlabs_calls = audio_result.elevenlabs_calls
        elevenlabs_chars = audio_result.elevenlabs_characters
        elevenlabs_purpose = audio_result.elevenlabs_purpose
        success = True
    except tts_service.AudioGenerationError as e:
        audio_url = None
        success = False
        status = "audio_failed"
        error_message = str(e)
        elevenlabs_calls = e.calls
        elevenlabs_chars = e.characters
        elevenlabs_purpose = e.purpose
    workflow_timings["tts_audio_generation_ms"] = elapsed_ms(tts_start)

    generation_time_ms = elapsed_ms(start_time)
    workflow_timings["episode_storage_ms"] = 0
    workflow_timings["total_generation_ms"] = generation_time_ms

    tool_usage = _build_tool_usage(
        newsapi_calls,
        script_result.openai_usage,
        elevenlabs_calls,
        elevenlabs_chars,
        elevenlabs_purpose,
    )
    estimated_cost = round(sum(t.estimated_cost_usd for t in tool_usage), 4)

    article_sources = [
        ArticleSource(
            title=script_service.normalize_text(a.get("title", "")),
            source=script_service.normalize_text(a.get("source", "")),
            url=a.get("url", ""),
            published_at=a.get("published_at") or a.get("publishedAt", ""),
            provider=a.get("provider", ""),
            topic=a.get("topic", ""),
        )
        for a in selected
    ]

    episode = EpisodeResponse(
        id=uuid.uuid4().hex[:12],
        title=title,
        summary=summary,
        script=script,
        audio_url=audio_url,
        interests=interests,
        articles=article_sources,
        tone=req.tone,
        duration=duration_label,
        frequency=req.frequency,
        voice="John creative" if req.speaker_mode == "solo" else "John creative + Maya educational",
        speaker_mode=req.speaker_mode,
        user_id=req.user_id,
        generation_type=req.generation_type,
        schedule_id=req.schedule_id,
        article_count=used_count,
        duplicate_articles_filtered=duplicate_filtered_count,
        seen_articles_filtered=seen_filtered_count,
        total_fetched=fetched_count,
        invalid_articles_filtered=invalid_filtered_count,
        title_irrelevant_articles_filtered=title_filtered_count,
        estimated_cost_usd=estimated_cost,
        tool_usage=tool_usage,
        workflow_timings=workflow_timings,
        created_at=datetime.now(timezone.utc).isoformat(),
        generation_time_ms=generation_time_ms,
        success=success,
        status=status,
        error_message=error_message,
        selected_interest_count=len(interests),
    )

    storage_start = perf_counter()
    episode_repository.insert_episode(episode)

    if success:
        urls = [
            news_service._normalize_url_for_tracking(a.get("url", ""))
            for a in selected
        ]
        selected_urls = [u for u in urls if u]
        episode_repository.mark_urls_seen(req.user_id, selected_urls)
        logger.info(
            "[podcast] article_selection_complete user_id=%s interests=%s "
            "window_days=%s fetched_count=%s deduped_count=%s "
            "title_relevant_count=%s seen_filtered_count=%s usable_count=%s selected_count=%s "
            "used_urls_marked_seen=%s",
            req.user_id,
            interests,
            selected_window_days,
            fetched_count,
            deduped_count,
            title_relevant_count,
            seen_filtered_count,
            unseen_count,
            used_count,
            len(selected_urls),
        )

    workflow_timings["episode_storage_ms"] = elapsed_ms(storage_start)
    workflow_timings["total_generation_ms"] = elapsed_ms(start_time)
    episode.workflow_timings = workflow_timings
    episode.generation_time_ms = workflow_timings["total_generation_ms"]
    episode_repository.update_episode_workflow_timings(
        episode.id,
        workflow_timings,
        episode.generation_time_ms,
    )

    return episode
