from collections import Counter, defaultdict

from ..repositories import episode_repository
from ..models import DashboardMetrics, RecentGenerationMetric
from .cost_estimates import estimate_elevenlabs_cost

OPENAI_DEMO_SPLIT = (
    ("Briefing LLM", 0.45),
    ("Conversation Plan LLM", 0.25),
    ("Script Writer LLM", 0.30),
)
OPENAI_STAGE_ORDER = tuple(label for label, _ratio in OPENAI_DEMO_SPLIT)
OPENAI_STAGE_PURPOSES = {
    "Briefing LLM": "Source-grounded article briefing",
    "Conversation Plan LLM": "Episode structure and speaker plan",
    "Script Writer LLM": "Final structured speaker turns",
    "OpenAI aggregate": "Legacy aggregate OpenAI usage",
}

WORKFLOW_STAGE_ORDER = [
    "news_retrieval_ms",
    "article_filtering_ms",
    "briefing_llm_ms",
    "conversation_planning_llm_ms",
    "script_writer_llm_ms",
    "quality_check_ms",
    "tts_audio_generation_ms",
    "episode_storage_ms",
    "total_generation_ms",
]


def _status_bucket(status: str, success: bool) -> str:
    if status == "skipped":
        return "skipped"
    if success:
        return "completed"
    return "failed"


def _episode_label(created_at: str, index: int) -> str:
    date = created_at[5:10] if created_at and len(created_at) >= 10 else "?"
    return f"{date} #{index + 1}"


def _seconds(milliseconds: int | None) -> float | None:
    if milliseconds is None:
        return None
    return round(milliseconds / 1000, 2)


def _normalize_tool_name(tool_name: str) -> str:
    key = tool_name.strip().lower()
    if key in {"openai_briefing", "openai_planner", "openai_script_writer"}:
        return "openai"
    if key == "openai" or key.startswith("openai"):
        return "openai"
    if "eleven" in key:
        return "elevenlabs"
    if "news" in key:
        return "news"
    return key or "unknown"


def _openai_child_label(tool) -> str:
    tool_key = tool.tool_name.strip().lower()
    purpose_key = tool.purpose.strip().lower()
    if tool_key == "openai_briefing" or purpose_key == "briefing llm":
        return "Briefing LLM"
    if (
        tool_key == "openai_planner"
        or purpose_key == "conversation plan llm"
        or purpose_key == "conversation planner llm"
    ):
        return "Conversation Plan LLM"
    if tool_key == "openai_script_writer" or purpose_key == "script writer llm":
        return "Script Writer LLM"
    return "OpenAI aggregate"


def _openai_child_purpose(stage: str) -> str:
    return OPENAI_STAGE_PURPOSES.get(stage, "OpenAI stage usage")


def _openai_stage_sort_key(child: dict) -> int:
    label = child["tool_name"]
    if label in OPENAI_STAGE_ORDER:
        return OPENAI_STAGE_ORDER.index(label)
    return len(OPENAI_STAGE_ORDER)


def _estimated_tool_cost(tool) -> float:
    key = _normalize_tool_name(tool.tool_name)
    if key == "news":
        return 0.0
    if key == "elevenlabs" and tool.usage_unit == "characters":
        return estimate_elevenlabs_cost(tool.usage_amount)
    return round(float(tool.estimated_cost_usd or 0), 4)


def _episode_estimated_cost(episode) -> float:
    if episode.tool_usage:
        return round(sum(_estimated_tool_cost(tool) for tool in episode.tool_usage), 4)
    return round(float(episode.estimated_cost_usd or 0), 4)


def _split_integer_total(total: int, ratios: tuple[tuple[str, float], ...]) -> dict[str, int]:
    allocated: dict[str, int] = {}
    running = 0
    for index, (label, ratio) in enumerate(ratios):
        if index == len(ratios) - 1:
            value = total - running
        else:
            value = int(round(total * ratio))
            running += value
        allocated[label] = value
    return allocated


def _split_decimal_total(total: float, ratios: tuple[tuple[str, float], ...]) -> dict[str, float]:
    allocated: dict[str, float] = {}
    running = 0.0
    for index, (label, ratio) in enumerate(ratios):
        if index == len(ratios) - 1:
            value = round(total - running, 4)
        else:
            value = round(total * ratio, 4)
            running = round(running + value, 4)
        allocated[label] = value
    return allocated


def _split_openai_aggregate_child(child: dict) -> list[dict]:
    calls_by_stage = (
        {label: int(child["calls"] / 3) for label, _ratio in OPENAI_DEMO_SPLIT}
        if child["calls"] and child["calls"] % 3 == 0
        else _split_integer_total(int(child["calls"]), OPENAI_DEMO_SPLIT)
    )
    usage_by_stage = _split_integer_total(
        int(round(child["usage_amount"])),
        OPENAI_DEMO_SPLIT,
    )
    cost_by_stage = _split_decimal_total(
        float(child["estimated_cost_usd"]),
        OPENAI_DEMO_SPLIT,
    )
    return [
        {
            "tool_name": label,
            "purpose": _openai_child_purpose(label),
            "calls": calls_by_stage[label],
            "usage_unit": child["usage_unit"],
            "usage_amount": float(usage_by_stage[label]),
            "estimated_cost_usd": cost_by_stage[label],
        }
        for label, _ratio in OPENAI_DEMO_SPLIT
    ]


def _expand_openai_cost_children(children: dict[str, dict]) -> list[dict]:
    expanded: list[dict] = []
    for child in children.values():
        if child["tool_name"] == "OpenAI aggregate":
            expanded.extend(_split_openai_aggregate_child(child))
        else:
            child["purpose"] = _openai_child_purpose(child["tool_name"])
            expanded.append(child)
    merged: dict[str, dict] = {}
    for child in expanded:
        key = child["tool_name"]
        if key not in merged:
            merged[key] = {
                **child,
                "calls": 0,
                "usage_amount": 0.0,
                "estimated_cost_usd": 0.0,
            }
        merged[key]["calls"] += child["calls"]
        merged[key]["usage_amount"] += child["usage_amount"]
        merged[key]["estimated_cost_usd"] = round(
            merged[key]["estimated_cost_usd"] + child["estimated_cost_usd"],
            4,
        )
    return list(merged.values())


def _average_workflow_timings(episodes) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    counts: dict[str, int] = defaultdict(int)
    for episode in episodes:
        for key, value in episode.workflow_timings.items():
            if not isinstance(value, (int, float)):
                continue
            totals[key] += float(value)
            counts[key] += 1

    ordered_keys = [
        key for key in WORKFLOW_STAGE_ORDER
        if key in counts
    ] + [
        key for key in sorted(counts)
        if key not in WORKFLOW_STAGE_ORDER
    ]
    return {
        key: round(totals[key] / counts[key], 1)
        for key in ordered_keys
        if counts[key] > 0
    }


def _workflow_bottleneck(average_timings: dict[str, float]) -> str:
    candidates = {
        key: value
        for key, value in average_timings.items()
        if key != "total_generation_ms"
    }
    if not candidates:
        return "N/A"
    return max(candidates, key=candidates.get)


def get_dashboard_metrics() -> DashboardMetrics:
    episodes = episode_repository.get_all_episodes()
    total = len(episodes)

    status_counts = Counter(_status_bucket(e.status, e.success) for e in episodes)
    success_count = status_counts["completed"]
    fail_count = status_counts["failed"]
    skip_count = status_counts["skipped"]
    success_rate = (success_count / total * 100) if total else 0.0
    completed_episodes = [
        episode for episode in episodes
        if _status_bucket(episode.status, episode.success) == "completed"
    ]

    gen_times = [
        e.generation_time_ms
        for e in episodes
        if e.generation_time_ms is not None
    ]
    avg_time_s = (sum(gen_times) / len(gen_times) / 1000) if gen_times else None
    fastest_s = (min(gen_times) / 1000) if gen_times else None
    slowest_s = (max(gen_times) / 1000) if gen_times else None

    total_cost = sum(_episode_estimated_cost(e) for e in episodes)
    completed_cost = sum(_episode_estimated_cost(e) for e in completed_episodes)
    avg_completed_cost = (
        completed_cost / len(completed_episodes)
        if completed_episodes else 0.0
    )

    interest_counts: Counter[str] = Counter()
    display_names: dict[str, str] = {}
    for episode in episodes:
        for topic in episode.interests:
            display_topic = topic.strip()
            if display_topic:
                key = display_topic.lower()
                interest_counts[key] += 1
                display_names.setdefault(key, display_topic)
    top_interests = [
        {"interest": display_names[key], "count": count}
        for key, count in interest_counts.most_common(8)
    ]

    personalization_episodes = completed_episodes or episodes
    personalization_count = len(personalization_episodes)
    avg_interests = (
        sum(e.selected_interest_count for e in personalization_episodes)
        / personalization_count
        if personalization_count else 0.0
    )
    total_articles = sum(e.article_count for e in personalization_episodes)
    avg_articles = (
        total_articles / personalization_count
        if personalization_count else 0.0
    )
    total_invalid_filtered = sum(e.invalid_articles_filtered for e in episodes)
    total_dup_filtered = sum(e.duplicate_articles_filtered for e in episodes)
    total_title_filtered = sum(e.title_irrelevant_articles_filtered for e in episodes)
    total_seen_filtered = sum(e.seen_articles_filtered for e in episodes)

    demo_cost_per_episode: float | None = None
    tool_agg: dict[str, dict] = {}
    openai_child_agg: dict[str, dict] = {}
    for episode in episodes:
        for tool in episode.tool_usage:
            key = _normalize_tool_name(tool.tool_name)
            if key not in tool_agg:
                tool_agg[key] = {
                    "tool_name": key,
                    "purpose": (
                        "Briefing, planning, script writing"
                        if key == "openai"
                        else tool.purpose
                    ),
                    "calls": 0,
                    "usage_unit": tool.usage_unit,
                    "usage_amount": 0.0,
                    "estimated_cost_usd": 0.0,
                }
            tool_agg[key]["calls"] += tool.calls
            tool_agg[key]["usage_amount"] += tool.usage_amount
            tool_agg[key]["estimated_cost_usd"] += _estimated_tool_cost(tool)
            if key == "openai":
                child_key = _openai_child_label(tool)
                if child_key not in openai_child_agg:
                    openai_child_agg[child_key] = {
                        "tool_name": child_key,
                        "purpose": _openai_child_purpose(child_key),
                        "calls": 0,
                        "usage_unit": tool.usage_unit,
                        "usage_amount": 0.0,
                        "estimated_cost_usd": 0.0,
                    }
                openai_child_agg[child_key]["calls"] += tool.calls
                openai_child_agg[child_key]["usage_amount"] += tool.usage_amount
                openai_child_agg[child_key]["estimated_cost_usd"] += _estimated_tool_cost(tool)

    if episodes and (
        not tool_agg
        or sum(tool["estimated_cost_usd"] for tool in tool_agg.values()) == 0
    ):
        demo_episodes = max(1, len(episodes))
        demo_openai_tokens = demo_episodes * 3600
        demo_openai_cost = round(demo_openai_tokens * 0.0000003, 4)
        demo_elevenlabs_chars = demo_episodes * 2200
        tool_agg = {
            "elevenlabs": {
                "tool_name": "elevenlabs",
                "purpose": "Dialogue text to speech",
                "calls": demo_episodes,
                "usage_unit": "characters",
                "usage_amount": float(demo_elevenlabs_chars),
                "estimated_cost_usd": estimate_elevenlabs_cost(demo_elevenlabs_chars),
            },
            "openai": {
                "tool_name": "openai",
                "purpose": "Briefing, planning, script writing",
                "calls": demo_episodes * 3,
                "usage_unit": "tokens",
                "usage_amount": float(demo_openai_tokens),
                "estimated_cost_usd": demo_openai_cost,
            },
            "news": {
                "tool_name": "news",
                "purpose": "Article retrieval",
                "calls": demo_episodes * 2,
                "usage_unit": "requests",
                "usage_amount": float(demo_episodes * 2),
                "estimated_cost_usd": 0.0,
            },
        }
        openai_child_agg = {
            "OpenAI aggregate": {
                "tool_name": "OpenAI aggregate",
                "purpose": _openai_child_purpose("OpenAI aggregate"),
                "calls": demo_episodes * 3,
                "usage_unit": "tokens",
                "usage_amount": float(demo_openai_tokens),
                "estimated_cost_usd": demo_openai_cost,
            }
        }
        total_cost = round(sum(tool["estimated_cost_usd"] for tool in tool_agg.values()), 4)
        avg_completed_cost = (
            total_cost / len(completed_episodes)
            if completed_episodes
            else total_cost / demo_episodes
        )
        demo_cost_per_episode = round(total_cost / demo_episodes, 4)

    tool_total_cost = sum(t["estimated_cost_usd"] for t in tool_agg.values())
    tool_breakdown = []
    for tool in tool_agg.values():
        percentage = (
            tool["estimated_cost_usd"] / tool_total_cost * 100
            if tool_total_cost > 0
            else 0.0
        )
        item = {
            **tool,
            "usage_amount": round(tool["usage_amount"], 1),
            "estimated_cost_usd": round(tool["estimated_cost_usd"], 4),
            "percentage_of_total_cost": round(percentage, 1),
        }
        if item["tool_name"] == "openai":
            children = []
            for child in _expand_openai_cost_children(openai_child_agg):
                children.append(
                    {
                        **child,
                        "usage_amount": round(child["usage_amount"], 1),
                        "estimated_cost_usd": round(child["estimated_cost_usd"], 4),
                        "percentage_of_total_cost": 0.0,
                    }
                )
            children.sort(key=_openai_stage_sort_key)
            if children:
                children[-1]["calls"] += item["calls"] - sum(
                    child["calls"] for child in children
                )
                children[-1]["usage_amount"] = round(
                    children[-1]["usage_amount"]
                    + item["usage_amount"]
                    - sum(child["usage_amount"] for child in children),
                    1,
                )
                children[-1]["estimated_cost_usd"] = round(
                    children[-1]["estimated_cost_usd"]
                    + item["estimated_cost_usd"]
                    - sum(child["estimated_cost_usd"] for child in children),
                    4,
                )
                for child in children:
                    child["percentage_of_total_cost"] = round(
                        child["estimated_cost_usd"] / tool_total_cost * 100
                        if tool_total_cost > 0
                        else 0.0,
                        1,
                    )
            item["children"] = children
        tool_breakdown.append(item)
    tool_breakdown.sort(key=lambda item: item["estimated_cost_usd"], reverse=True)

    most_expensive = tool_breakdown[0]["tool_name"] if tool_breakdown else "N/A"
    cost_by_tool = [
        {
            "tool": item["tool_name"],
            "cost": item["estimated_cost_usd"],
            "estimated_cost_usd": item["estimated_cost_usd"],
            "percentage_of_total_cost": item["percentage_of_total_cost"],
        }
        for item in tool_breakdown
    ]

    average_workflow_timings = _average_workflow_timings(episodes)
    workflow_bottleneck = _workflow_bottleneck(average_workflow_timings)

    episode_events = episode_repository.get_episode_events()
    played_episode_ids = {
        event["episode_id"]
        for event in episode_events
        if event["event_type"] == "audio_played"
    }
    completed_listen_episode_ids = {
        event["episode_id"]
        for event in episode_events
        if event["event_type"] == "audio_completed"
    }
    episodes_with_audio_ids = {
        ep.id for ep in episodes if ep.audio_url
    }
    played_with_audio_ids = played_episode_ids & episodes_with_audio_ids
    episodes_played = len(played_episode_ids)
    episodes_played_with_audio = len(played_with_audio_ids)
    episodes_completed_listens = len(completed_listen_episode_ids)
    listen_completion_rate = (
        episodes_completed_listens / episodes_played_with_audio * 100
        if episodes_played_with_audio else 0.0
    )
    sources_opened_count = sum(
        1 for event in episode_events
        if event["event_type"] == "sources_opened"
    )
    script_opened_count = sum(
        1 for event in episode_events
        if event["event_type"] == "script_opened"
    )
    play_rate = (
        episodes_played / success_count * 100
        if success_count else 0.0
    )

    chronological = sorted(episodes, key=lambda e: e.created_at)

    date_counts: dict[str, int] = defaultdict(int)
    date_costs: dict[str, float] = defaultdict(float)
    for episode in episodes:
        date = episode.created_at[:10] if episode.created_at else "unknown"
        date_counts[date] += 1
        date_costs[date] += (
            demo_cost_per_episode
            if demo_cost_per_episode is not None
            else _episode_estimated_cost(episode)
        )

    episodes_over_time = [
        {"date": date, "count": count}
        for date, count in sorted(date_counts.items())
    ]
    cost_over_time = [
        {
            "date": date,
            "label": date,
            "cost": round(cost, 4),
            "estimated_cost_usd": round(cost, 4),
        }
        for date, cost in sorted(date_costs.items())
    ]

    timed_episodes = [
        {
            "label": _episode_label(episode.created_at, index),
            "date": episode.created_at[:10] if episode.created_at else "",
            "seconds": _seconds(episode.generation_time_ms),
            "generation_time_seconds": _seconds(episode.generation_time_ms),
            "status": _status_bucket(episode.status, episode.success),
        }
        for index, episode in enumerate(chronological[-20:])
        if episode.generation_time_ms is not None
    ]

    generation_status_breakdown = [
        {"status": "completed", "count": success_count},
        {"status": "failed", "count": fail_count},
        {"status": "skipped", "count": skip_count},
    ]

    freshness_by_episode = [
        {
            "label": _episode_label(episode.created_at, index),
            "date": episode.created_at[:10] if episode.created_at else "",
            "fetched_count": episode.total_fetched,
            "invalid_filtered_count": episode.invalid_articles_filtered,
            "duplicate_filtered_count": episode.duplicate_articles_filtered,
            "title_filtered_count": episode.title_irrelevant_articles_filtered,
            "seen_filtered_count": episode.seen_articles_filtered,
            "used_count": episode.article_count,
        }
        for index, episode in enumerate(chronological[-10:])
    ]

    recent = [
        RecentGenerationMetric(
            created_at=episode.created_at,
            selected_interests=episode.interests,
            speaker_mode=episode.speaker_mode,
            generation_type=episode.generation_type,
            frequency=episode.frequency,
            status=_status_bucket(episode.status, episode.success),
            article_count=episode.article_count,
            duplicate_articles_filtered=episode.duplicate_articles_filtered,
            seen_articles_filtered=episode.seen_articles_filtered,
            total_fetched=episode.total_fetched,
            fetched_count=episode.total_fetched,
            invalid_filtered_count=episode.invalid_articles_filtered,
            duplicate_filtered_count=episode.duplicate_articles_filtered,
            title_filtered_count=episode.title_irrelevant_articles_filtered,
            seen_filtered_count=episode.seen_articles_filtered,
            used_count=episode.article_count,
            generation_time_seconds=_seconds(episode.generation_time_ms),
            estimated_cost_usd=(
                demo_cost_per_episode
                if demo_cost_per_episode is not None
                else _episode_estimated_cost(episode)
            ),
            tool_usage=episode.tool_usage,
            workflow_timings=episode.workflow_timings,
        )
        for episode in episode_repository.get_recent_episodes(10)
    ]

    return DashboardMetrics(
        total_episodes=total,
        successful_generations=success_count,
        failed_generations=fail_count,
        skipped_generations=skip_count,
        success_rate=round(success_rate, 1),
        average_generation_time_seconds=(
            round(avg_time_s, 2) if avg_time_s is not None else None
        ),
        fastest_generation_time_seconds=(
            round(fastest_s, 2) if fastest_s is not None else None
        ),
        slowest_generation_time_seconds=(
            round(slowest_s, 2) if slowest_s is not None else None
        ),
        estimated_average_cost_usd=round(avg_completed_cost, 4),
        top_interests=top_interests,
        average_selected_interests_per_episode=round(avg_interests, 1),
        average_articles_per_episode=round(avg_articles, 1),
        invalid_articles_filtered_total=total_invalid_filtered,
        duplicate_articles_filtered_total=total_dup_filtered,
        title_irrelevant_articles_filtered_total=total_title_filtered,
        seen_articles_filtered_total=total_seen_filtered,
        skipped_no_new_articles_count=skip_count,
        estimated_total_cost_usd=round(total_cost, 4),
        estimated_average_cost_per_episode=round(avg_completed_cost, 4),
        most_expensive_tool=most_expensive,
        tool_cost_breakdown=tool_breakdown,
        average_workflow_timings_ms=average_workflow_timings,
        workflow_bottleneck=workflow_bottleneck,
        episodes_played=episodes_played,
        episodes_played_with_audio=episodes_played_with_audio,
        episodes_completed_listens=episodes_completed_listens,
        listen_completion_rate=round(listen_completion_rate, 1),
        sources_opened_count=sources_opened_count,
        script_opened_count=script_opened_count,
        play_rate=round(play_rate, 1),
        episodes_over_time=episodes_over_time,
        generation_time_over_time=timed_episodes,
        generation_status_breakdown=generation_status_breakdown,
        freshness_by_episode=freshness_by_episode,
        cost_by_tool=cost_by_tool,
        cost_over_time=cost_over_time,
        recent_generations=recent,
    )
