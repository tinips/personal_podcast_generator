import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional
from ..database import get_connection
from ..models import EpisodeResponse, ArticleSource, ScheduleResponse, ToolUsageItem
from ..services.news_service import _normalize_url_for_tracking
from ..services.script_service import normalize_text


ALLOWED_EPISODE_EVENTS = {
    "audio_played",
    "audio_completed",
    "sources_opened",
    "script_opened",
}


def _row_value(row: sqlite3.Row, key: str, default=None):
    if key not in row.keys():
        return default
    value = row[key]
    return default if value is None else value


def _json_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(value, list):
        return []
    return [normalize_text(str(item)) for item in value]


def _json_articles(raw: str | None) -> list[ArticleSource]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(value, list):
        return []

    articles: list[ArticleSource] = []
    for item in value:
        if isinstance(item, dict):
            articles.append(
                ArticleSource(
                    title=normalize_text(str(item.get("title", ""))),
                    source=normalize_text(str(item.get("source", ""))),
                    url=str(item.get("url", "")),
                    published_at=str(
                        item.get("published_at") or item.get("publishedAt") or ""
                    ),
                    provider=normalize_text(str(item.get("provider", ""))),
                    topic=normalize_text(str(item.get("topic", ""))),
                )
            )
        elif isinstance(item, str):
            title, _, source = item.partition(" - ")
            articles.append(
                ArticleSource(
                    title=normalize_text(title),
                    source=normalize_text(source),
                    url="",
                    published_at="",
                    provider="",
                    topic="",
                )
            )
    return articles


def _json_tool_usage(raw: str | None) -> list[ToolUsageItem]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(value, list):
        return []
    result: list[ToolUsageItem] = []
    for item in value:
        if isinstance(item, dict):
            result.append(ToolUsageItem(
                tool_name=str(item.get("tool_name", "")),
                purpose=str(item.get("purpose", "")),
                calls=int(item.get("calls", 0)),
                usage_unit=str(item.get("usage_unit", "")),
                usage_amount=float(item.get("usage_amount", 0)),
                estimated_cost_usd=float(item.get("estimated_cost_usd", 0)),
            ))
    return result


def _json_workflow_timings(raw: str | None) -> dict[str, int]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    if not isinstance(value, dict):
        return {}
    result: dict[str, int] = {}
    for key, amount in value.items():
        try:
            numeric_amount = int(float(amount))
        except (TypeError, ValueError):
            continue
        result[str(key)] = numeric_amount
    return result


def row_to_episode(row: sqlite3.Row) -> EpisodeResponse:
    success = bool(row["success"])
    status = _row_value(
        row,
        "status",
        "completed" if success else "audio_failed",
    )
    articles = _json_articles(_row_value(row, "articles", "[]"))
    stored_article_count = _row_value(row, "article_count", 0)
    article_count = stored_article_count or len(articles)
    return EpisodeResponse(
        id=row["id"],
        title=normalize_text(row["title"]),
        summary=normalize_text(row["summary"]),
        script=normalize_text(row["script"]),
        audio_url=row["audio_path"],
        interests=_json_list(_row_value(row, "interests", "[]")),
        articles=articles,
        tone=row["tone"],
        duration=row["duration"],
        frequency=row["frequency"],
        voice=row["voice"],
        speaker_mode=_row_value(row, "speaker_mode", "solo"),
        user_id=_row_value(row, "user_id", ""),
        generation_type=_row_value(row, "generation_type", "manual"),
        schedule_id=_row_value(row, "schedule_id"),
        article_count=article_count,
        duplicate_articles_filtered=_row_value(row, "duplicate_articles_filtered", 0),
        seen_articles_filtered=_row_value(row, "seen_articles_filtered", 0),
        total_fetched=_row_value(row, "total_fetched", 0),
        invalid_articles_filtered=_row_value(row, "invalid_articles_filtered", 0),
        title_irrelevant_articles_filtered=_row_value(
            row, "title_irrelevant_articles_filtered", 0
        ),
        estimated_cost_usd=_row_value(row, "estimated_cost_usd", 0.0),
        tool_usage=_json_tool_usage(_row_value(row, "tool_usage", "[]")),
        workflow_timings=_json_workflow_timings(
            _row_value(row, "workflow_timings", "{}")
        ),
        created_at=row["created_at"],
        generation_time_ms=row["generation_time_ms"],
        success=success,
        status=status,
        error_message=(
            normalize_text(_row_value(row, "error_message"))
            if _row_value(row, "error_message")
            else None
        ),
        selected_interest_count=_row_value(row, "selected_interest_count", 1),
    )


def insert_episode(episode: EpisodeResponse) -> None:
    conn = get_connection()
    conn.execute(
        """INSERT INTO episodes
           (id, title, summary, script, audio_path, interests, articles, tone,
            duration, frequency, voice, speaker_mode, user_id,
            generation_type, schedule_id,
            article_count, duplicate_articles_filtered, seen_articles_filtered,
            total_fetched, invalid_articles_filtered,
            title_irrelevant_articles_filtered,
            estimated_cost_usd, tool_usage, workflow_timings,
            selected_interest_count, created_at, generation_time_ms, success,
            status, error_message)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            episode.id,
            normalize_text(episode.title),
            normalize_text(episode.summary),
            normalize_text(episode.script),
            episode.audio_url,
            json.dumps([normalize_text(item) for item in episode.interests]),
            json.dumps(
                [
                    {
                        "title": normalize_text(article.title),
                        "source": normalize_text(article.source),
                        "url": article.url,
                        "published_at": article.published_at,
                        "provider": article.provider,
                        "topic": article.topic,
                    }
                    for article in episode.articles
                ]
            ),
            episode.tone,
            episode.duration,
            episode.frequency,
            episode.voice,
            episode.speaker_mode,
            episode.user_id,
            episode.generation_type,
            episode.schedule_id,
            episode.article_count,
            episode.duplicate_articles_filtered,
            episode.seen_articles_filtered,
            episode.total_fetched,
            episode.invalid_articles_filtered,
            episode.title_irrelevant_articles_filtered,
            episode.estimated_cost_usd,
            json.dumps(
                [
                    {
                        "tool_name": t.tool_name,
                        "purpose": t.purpose,
                        "calls": t.calls,
                        "usage_unit": t.usage_unit,
                        "usage_amount": t.usage_amount,
                        "estimated_cost_usd": t.estimated_cost_usd,
                    }
                    for t in episode.tool_usage
                ]
            ),
            json.dumps(episode.workflow_timings),
            episode.selected_interest_count,
            episode.created_at,
            episode.generation_time_ms,
            int(episode.success),
            episode.status,
            normalize_text(episode.error_message) if episode.error_message else None,
        ),
    )
    conn.commit()
    conn.close()


def update_episode_workflow_timings(
    episode_id: str,
    workflow_timings: dict[str, int],
    generation_time_ms: int | None = None,
) -> None:
    conn = get_connection()
    if generation_time_ms is None:
        conn.execute(
            "UPDATE episodes SET workflow_timings = ? WHERE id = ?",
            (json.dumps(workflow_timings), episode_id),
        )
    else:
        conn.execute(
            """UPDATE episodes
               SET workflow_timings = ?, generation_time_ms = ?
               WHERE id = ?""",
            (json.dumps(workflow_timings), generation_time_ms, episode_id),
        )
    conn.commit()
    conn.close()


def get_all_episodes() -> list[EpisodeResponse]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM episodes ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [row_to_episode(r) for r in rows]


def get_episode_by_id(episode_id: str) -> Optional[EpisodeResponse]:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM episodes WHERE id = ?", (episode_id,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return row_to_episode(row)


def delete_episode(episode_id: str) -> Optional[EpisodeResponse]:
    episode = get_episode_by_id(episode_id)
    if episode is None:
        return None

    conn = get_connection()
    conn.execute("DELETE FROM episode_events WHERE episode_id = ?", (episode_id,))
    conn.execute("DELETE FROM episodes WHERE id = ?", (episode_id,))
    conn.commit()
    conn.close()
    return episode


def get_recent_episodes(limit: int = 10) -> list[EpisodeResponse]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM episodes ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [row_to_episode(r) for r in rows]


def get_seen_urls(user_id: str) -> set[str]:
    if not user_id:
        return set()
    conn = get_connection()
    rows = conn.execute(
        "SELECT url FROM seen_articles WHERE user_id = ?", (user_id,)
    ).fetchall()
    conn.close()
    return {row["url"] for row in rows}


def mark_urls_seen(user_id: str, urls: list[str]) -> None:
    if not user_id or not urls:
        return
    normalized_urls = [
        _normalize_url_for_tracking(url)
        for url in urls
        if _normalize_url_for_tracking(url)
    ]
    if not normalized_urls:
        return
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    conn.executemany(
        "INSERT OR IGNORE INTO seen_articles (user_id, url, seen_at) VALUES (?, ?, ?)",
        [(user_id, url, now) for url in dict.fromkeys(normalized_urls)],
    )
    conn.commit()
    conn.close()


def insert_schedule(schedule: "ScheduleResponse") -> None:
    conn = get_connection()
    conn.execute(
        """INSERT OR REPLACE INTO schedules
           (id, user_id, name, selected_interests, frequency, duration,
            tone, voice, speaker_mode, last_run_at, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            schedule.id,
            schedule.user_id,
            schedule.name,
            json.dumps(schedule.selected_interests),
            schedule.frequency,
            schedule.duration,
            schedule.tone,
            schedule.voice,
            schedule.speaker_mode,
            schedule.last_run_at,
            schedule.created_at,
        ),
    )
    conn.commit()
    conn.close()


def get_schedules(user_id: str) -> list["ScheduleResponse"]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM schedules WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,),
    ).fetchall()
    conn.close()
    result: list[ScheduleResponse] = []
    for row in rows:
        result.append(
            ScheduleResponse(
                id=row["id"],
                user_id=row["user_id"],
                name=row["name"],
                selected_interests=_json_list(row["selected_interests"]),
                frequency=row["frequency"],
                duration=row["duration"],
                tone=row["tone"],
                voice=row["voice"],
                speaker_mode=row["speaker_mode"],
                last_run_at=row["last_run_at"],
                created_at=row["created_at"],
            )
        )
    return result


def get_schedule_by_id(schedule_id: str) -> Optional["ScheduleResponse"]:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM schedules WHERE id = ?", (schedule_id,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return ScheduleResponse(
        id=row["id"],
        user_id=row["user_id"],
        name=row["name"],
        selected_interests=_json_list(row["selected_interests"]),
        frequency=row["frequency"],
        duration=row["duration"],
        tone=row["tone"],
        voice=row["voice"],
        speaker_mode=row["speaker_mode"],
        last_run_at=row["last_run_at"],
        created_at=row["created_at"],
    )


def update_schedule(schedule: "ScheduleResponse") -> "ScheduleResponse":
    conn = get_connection()
    conn.execute(
        """UPDATE schedules
           SET name = ?, selected_interests = ?, frequency = ?, duration = ?,
               tone = ?, voice = ?, speaker_mode = ?
           WHERE id = ?""",
        (
            schedule.name,
            json.dumps(schedule.selected_interests),
            schedule.frequency,
            schedule.duration,
            schedule.tone,
            schedule.voice,
            schedule.speaker_mode,
            schedule.id,
        ),
    )
    conn.commit()
    conn.close()
    return schedule


def delete_schedule(schedule_id: str) -> bool:
    conn = get_connection()
    cursor = conn.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def get_seen_url_count() -> int:
    conn = get_connection()
    row = conn.execute("SELECT COUNT(*) as cnt FROM seen_articles").fetchone()
    conn.close()
    return row["cnt"] if row else 0


def update_schedule_last_run(schedule_id: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    conn.execute(
        "UPDATE schedules SET last_run_at = ? WHERE id = ?",
        (now, schedule_id),
    )
    conn.commit()
    conn.close()


def insert_episode_event(
    episode_id: str,
    event_type: str,
    value: float | None = None,
) -> None:
    if event_type not in ALLOWED_EPISODE_EVENTS:
        allowed = ", ".join(sorted(ALLOWED_EPISODE_EVENTS))
        raise ValueError(f"Invalid episode event type '{event_type}'. Choose: {allowed}.")

    conn = get_connection()
    exists = conn.execute(
        "SELECT 1 FROM episodes WHERE id = ?",
        (episode_id,),
    ).fetchone()
    if exists is None:
        conn.close()
        raise ValueError(f"Episode '{episode_id}' not found.")

    conn.execute(
        """INSERT INTO episode_events
           (id, episode_id, event_type, value, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (
            uuid.uuid4().hex,
            episode_id,
            event_type,
            value,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def get_episode_events() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """SELECT id, episode_id, event_type, value, created_at
           FROM episode_events
           ORDER BY created_at DESC"""
    ).fetchall()
    conn.close()
    return [
        {
            "id": row["id"],
            "episode_id": row["episode_id"],
            "event_type": row["event_type"],
            "value": row["value"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]
