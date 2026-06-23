"""Run the Neural Notes dev pipeline stage by stage.

Run from the repository root:
    python backend/devtools/run_script_fixture_pipeline.py --interests AI data --news
    python backend/devtools/run_script_fixture_pipeline.py --brief
    python backend/devtools/run_script_fixture_pipeline.py --plan -m d -t p -d n
    python backend/devtools/run_script_fixture_pipeline.py --script -m d -t p -d n
    python backend/devtools/run_script_fixture_pipeline.py --audio -m d
    python backend/devtools/run_script_fixture_pipeline.py --interests AI data --news --brief --plan --script --audio

Default behavior:
    - If no stage flags are passed and --interests is present, runs news -> brief -> plan -> script -> audio.
    - If no stage flags are passed and an articles fixture exists, runs brief -> plan -> script -> audio.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import sys
from pathlib import Path

from dotenv import load_dotenv

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = Path(__file__).resolve().parents[1]
DEVTOOLS_DIR = Path(__file__).resolve().parent
FIXTURE_BASE = DEVTOOLS_DIR / "outputs" / "script_iteration"
ARTICLES_DIR = FIXTURE_BASE / "articles"
BRIEFING_DIR = FIXTURE_BASE / "briefing"
PLANS_DIR = FIXTURE_BASE / "plans"
SCRIPTS_DIR = FIXTURE_BASE / "scripts"
AUDIO_DIR = FIXTURE_BASE / "audio"

for directory in [ARTICLES_DIR, BRIEFING_DIR, PLANS_DIR, SCRIPTS_DIR, AUDIO_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(BACKEND_DIR))
load_dotenv(BACKEND_DIR / ".env")

from app.services.pipeline_models import ConversationPlan, PodcastBriefing

DURATION_CONFIG: dict[str, int] = {"short": 1, "normal": 2, "long": 3}
TARGET_ARTICLES_BY_DURATION: dict[str, int] = {"short": 1, "normal": 2, "long": 3}
SPEAKER_MODE_ALIASES = {
    "d": "dialogue",
    "dialogue": "dialogue",
    "s": "solo",
    "solo": "solo",
}
TONE_ALIASES = {
    "p": "professional",
    "pro": "professional",
    "professional": "professional",
    "c": "casual",
    "casual": "casual",
    "e": "energetic",
    "energetic": "energetic",
}
DURATION_ALIASES = {
    "s": "short",
    "short": "short",
    "n": "normal",
    "normal": "normal",
    "l": "long",
    "long": "long",
}


def _normalize_alias(value: str, aliases: dict[str, str], label: str) -> str:
    normalized = aliases.get(value.strip().lower())
    if normalized:
        return normalized
    valid = ", ".join(sorted(aliases))
    raise ValueError(f"Unsupported {label} '{value}'. Use one of: {valid}.")


def _latest_json(directory: Path) -> Path | None:
    return _latest_file(directory, "*.json")


def _latest_file(directory: Path, pattern: str) -> Path | None:
    if not directory.is_dir():
        return None
    fixtures = sorted(
        directory.glob(pattern),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return fixtures[0] if fixtures else None


def _path_or_project_path(raw_path: str) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _slug_from_stage_path(path: Path) -> str:
    stem = path.stem
    for suffix in (".briefing", ".plan", ".dialogue", ".solo"):
        stem = stem.replace(suffix, "")
    return _slugify(stem)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return slug or "fixture"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_briefing(path: Path) -> PodcastBriefing:
    return PodcastBriefing.model_validate(_load_json(path))


def _load_plan(path: Path) -> ConversationPlan:
    return ConversationPlan.model_validate(_load_json(path))


def _resolve_stage_selection(args: argparse.Namespace) -> list[str]:
    selected = []
    for stage in ("news", "brief", "plan", "script", "audio"):
        if getattr(args, stage):
            selected.append(stage)
    if selected:
        return selected
    if args.interests:
        return ["news", "brief", "plan", "script", "audio"]
    return ["brief", "plan", "script", "audio"]


def _resolve_articles_input(
    fixture_or_path: str | None,
    articles_arg: str | None,
    slug: str | None,
) -> Path:
    if fixture_or_path and articles_arg:
        raise ValueError("Use either the positional fixture or --articles, not both.")

    raw = articles_arg or fixture_or_path
    if slug:
        slug_candidate = ARTICLES_DIR / f"{slug}.json"
        if slug_candidate.is_file():
            return slug_candidate

    if not raw:
        latest = _latest_json(ARTICLES_DIR)
        if latest:
            return latest
        raise ValueError(
            "No articles fixture provided and no JSON fixtures found under "
            f"{ARTICLES_DIR}."
        )

    candidate = Path(raw)
    candidates = (
        [candidate]
        if candidate.is_absolute()
        else [
            PROJECT_ROOT / candidate,
            ARTICLES_DIR / candidate,
            ARTICLES_DIR / f"{raw}.json",
        ]
    )
    for path in candidates:
        if path.is_file():
            return path
    searched = "\n  ".join(str(path) for path in candidates)
    raise ValueError(f"Articles fixture not found. Searched:\n  {searched}")


def _resolve_input_file(path_arg: str | None, default_path: Path, label: str) -> Path:
    candidates = []
    if path_arg:
        raw = Path(path_arg)
        candidates.append(raw if raw.is_absolute() else PROJECT_ROOT / raw)
        candidates.append(default_path.parent / raw.name)
    candidates.append(default_path)
    for path in candidates:
        if path.is_file():
            return path
    searched = "\n  ".join(str(path) for path in dict.fromkeys(candidates))
    raise ValueError(f"{label} not found. Searched:\n  {searched}")


def _resolve_output_path(path_arg: str | None, default_path: Path) -> Path:
    if not path_arg:
        return default_path
    raw = Path(path_arg)
    return raw if raw.is_absolute() else PROJECT_ROOT / raw


def _infer_slug(
    args: argparse.Namespace,
    selected_stages: list[str],
) -> tuple[str, Path | None]:
    if args.slug:
        return _slugify(args.slug), None
    if args.interests:
        joined = "_".join(args.interests)
        return _slugify(joined), None
    if args.script_file:
        return _slug_from_stage_path(_path_or_project_path(args.script_file)), None
    if args.plan_file:
        return _slug_from_stage_path(_path_or_project_path(args.plan_file)), None
    if args.briefing_file:
        return _slug_from_stage_path(_path_or_project_path(args.briefing_file)), None
    if selected_stages:
        first_stage = selected_stages[0]
        if first_stage == "plan":
            latest_briefing = _latest_file(BRIEFING_DIR, "*.briefing.json")
            if latest_briefing:
                return _slug_from_stage_path(latest_briefing), None
            raise ValueError(
                "No briefing file provided and no saved briefings found under "
                f"{BRIEFING_DIR}."
            )
        if first_stage == "script":
            latest_plan = (
                _latest_file(PLANS_DIR, f"*.{args.speaker_mode}.plan.json")
                or _latest_file(PLANS_DIR, "*.plan.json")
            )
            if latest_plan:
                return _slug_from_stage_path(latest_plan), None
            raise ValueError(
                "No plan file provided and no saved plans found under "
                f"{PLANS_DIR}."
            )
        if first_stage == "audio":
            latest_script = (
                _latest_file(SCRIPTS_DIR, f"*.{args.speaker_mode}.txt")
                or _latest_file(SCRIPTS_DIR, "*.txt")
            )
            if latest_script:
                return _slug_from_stage_path(latest_script), None
            raise ValueError(
                "No script file provided and no saved scripts found under "
                f"{SCRIPTS_DIR}."
            )
        if first_stage == "brief":
            articles_path = _resolve_articles_input(args.fixture, args.articles, None)
            fixture = _load_json(articles_path)
            interests = fixture.get("interests", [])
            if interests:
                return _slugify("_".join(str(item) for item in interests)), articles_path
            return _slugify(articles_path.stem), articles_path
    if args.fixture:
        return _slug_from_stage_path(Path(args.fixture)), None
    articles_path = _resolve_articles_input(args.fixture, args.articles, None)
    fixture = _load_json(articles_path)
    interests = fixture.get("interests", [])
    if interests:
        return _slugify("_".join(str(item) for item in interests)), articles_path
    return _slugify(articles_path.stem), articles_path


def _count_words(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9']+", text))


def _target_article_count(duration: str) -> int:
    return TARGET_ARTICLES_BY_DURATION.get(
        duration,
        TARGET_ARTICLES_BY_DURATION["normal"],
    )


def _select_balanced_articles(
    candidates: list[dict],
    interests: list[str],
    target_count: int,
) -> list[dict]:
    from app.services import news_service

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


def _select_articles_for_briefing(
    articles: list[dict],
    interests: list[str],
    duration: str,
) -> tuple[list[dict], list[dict], int]:
    from app.services import news_service

    filtered = news_service.filter_complete_articles(articles)
    deduped, duplicates = news_service.deduplicate_articles_by_url(filtered)
    title_relevant = news_service.filter_title_relevant_articles(deduped, interests)
    target_count = _target_article_count(duration)
    selected = _select_balanced_articles(
        title_relevant,
        interests,
        target_count,
    )
    return selected, title_relevant, duplicates


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run the Neural Notes dev pipeline stage by stage. "
            "Stages: news -> brief -> plan -> script -> audio."
        )
    )
    parser.add_argument(
        "fixture",
        nargs="?",
        help=(
            "Fixture slug or path. Example: ai_data resolves to "
            "backend/devtools/outputs/script_iteration/articles/ai_data.json."
        ),
    )
    parser.add_argument(
        "--slug",
        help="Explicit slug for generated intermediate files.",
    )
    parser.add_argument(
        "--interests",
        nargs="+",
        help="Space-separated interests. Required when running the news stage.",
    )
    parser.add_argument(
        "--articles",
        help="Articles fixture path when reading an existing news output.",
    )
    parser.add_argument(
        "--briefing-file",
        help="Briefing JSON path when reading an existing briefing output.",
    )
    parser.add_argument(
        "--plan-file",
        help="Plan JSON path when reading an existing plan output.",
    )
    parser.add_argument(
        "--script-file",
        help="Script TXT path when reading an existing script output.",
    )
    parser.add_argument(
        "--articles-out",
        help="Output JSON path for the news stage.",
    )
    parser.add_argument(
        "--briefing-out",
        help="Output JSON path for the briefing stage.",
    )
    parser.add_argument(
        "--plan-out",
        help="Output JSON path for the planning stage.",
    )
    parser.add_argument(
        "--script-out",
        help="Output TXT path for the script stage.",
    )
    parser.add_argument(
        "--audio-out",
        help="Output MP3 path for the audio stage.",
    )
    parser.add_argument(
        "-news",
        "--news",
        action="store_true",
        help="Run the news extraction stage only or as part of a selected chain.",
    )
    parser.add_argument(
        "-brief",
        "--brief",
        action="store_true",
        help="Run the podcast briefing stage.",
    )
    parser.add_argument(
        "-plan",
        "--plan",
        action="store_true",
        help="Run the conversation planning stage.",
    )
    parser.add_argument(
        "-script",
        "--script",
        action="store_true",
        help="Run the script writing stage.",
    )
    parser.add_argument(
        "-audio",
        "--audio",
        action="store_true",
        help="Run the audio rendering stage.",
    )
    parser.add_argument(
        "-m",
        "--mode",
        "--speaker-mode",
        dest="speaker_mode",
        default="d",
        help="Speaker mode: d/dialogue or s/solo (default: d)",
    )
    parser.add_argument(
        "-t",
        "--tone",
        default="p",
        help="Tone: p/professional, c/casual, or e/energetic (default: p)",
    )
    parser.add_argument(
        "-d",
        "--duration",
        default="n",
        help="Duration: s/short, n/normal, or l/long (default: n)",
    )
    args = parser.parse_args()

    try:
        args.speaker_mode = _normalize_alias(
            args.speaker_mode, SPEAKER_MODE_ALIASES, "speaker mode"
        )
        args.tone = _normalize_alias(args.tone, TONE_ALIASES, "tone")
        args.duration = _normalize_alias(args.duration, DURATION_ALIASES, "duration")
        stages = _resolve_stage_selection(args)
        slug, inferred_articles_path = _infer_slug(args, stages)
    except ValueError as exc:
        parser.error(str(exc))
        sys.exit(1)

    default_articles_path = ARTICLES_DIR / f"{slug}.json"
    default_briefing_path = BRIEFING_DIR / f"{slug}.briefing.json"
    default_plan_path = PLANS_DIR / f"{slug}.{args.speaker_mode}.plan.json"
    default_script_path = SCRIPTS_DIR / f"{slug}.{args.speaker_mode}.txt"
    default_audio_path = AUDIO_DIR / f"{slug}.{args.speaker_mode}.mp3"

    articles_path = _resolve_output_path(args.articles_out, default_articles_path)
    briefing_path = _resolve_output_path(args.briefing_out, default_briefing_path)
    plan_path = _resolve_output_path(args.plan_out, default_plan_path)
    script_path = _resolve_output_path(args.script_out, default_script_path)
    audio_path = _resolve_output_path(args.audio_out, default_audio_path)
    first_stage = stages[0] if stages else ""

    if first_stage == "plan" and not args.briefing_file:
        latest_briefing = _latest_file(BRIEFING_DIR, "*.briefing.json")
        if latest_briefing:
            briefing_path = latest_briefing
    if first_stage == "script" and not args.plan_file:
        latest_plan = (
            _latest_file(PLANS_DIR, f"*.{args.speaker_mode}.plan.json")
            or _latest_file(PLANS_DIR, "*.plan.json")
        )
        if latest_plan:
            plan_path = latest_plan
    if first_stage == "audio" and not args.script_file:
        latest_script = (
            _latest_file(SCRIPTS_DIR, f"*.{args.speaker_mode}.txt")
            or _latest_file(SCRIPTS_DIR, "*.txt")
        )
        if latest_script:
            script_path = latest_script

    if "news" not in stages and "brief" in stages:
        try:
            articles_path = (
                inferred_articles_path
                if inferred_articles_path is not None
                else _resolve_articles_input(args.fixture, args.articles, slug)
            )
        except ValueError as exc:
            parser.error(str(exc))
            sys.exit(1)

    print(
        "Config: "
        f"slug={slug} "
        f"stages={','.join(stages)} "
        f"mode={args.speaker_mode} tone={args.tone} duration={args.duration}"
    )

    async def _run() -> None:
        current_articles: dict | None = None
        current_briefing: PodcastBriefing | None = None
        current_plan: ConversationPlan | None = None
        current_script: str | None = None
        resolved_articles_path = articles_path
        resolved_briefing_path = briefing_path
        resolved_plan_path = plan_path
        resolved_script_path = script_path
        resolved_audio_path = audio_path

        if "news" in stages:
            if not args.interests:
                raise ValueError("--interests is required when running the news stage.")
            api_key = os.getenv("NEWS_API_KEY", "")
            if not api_key:
                raise ValueError("NEWS_API_KEY is not set in backend/.env")

            from app.services import news_service
            from datetime import datetime, timezone

            print("Stage news: fetching articles...")
            raw_articles = await news_service.fetch_articles_for_interests(
                args.interests,
                articles_count=news_service.candidate_count_for_duration(args.duration),
                window_days=news_service.recency_window_days("manual", "manual"),
            )
            selected_articles, candidate_articles, duplicates = _select_articles_for_briefing(
                raw_articles,
                args.interests,
                args.duration,
            )
            current_articles = {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "interests": args.interests,
                "duration": args.duration,
                "raw_article_count": len(raw_articles),
                "candidate_article_count": len(candidate_articles),
                "article_count": len(selected_articles),
                "duplicate_articles_filtered": duplicates,
                "articles": selected_articles,
                "candidate_articles": candidate_articles,
            }
            resolved_articles_path.parent.mkdir(parents=True, exist_ok=True)
            resolved_articles_path.write_text(
                json.dumps(current_articles, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            print(
                f"  News: {len(raw_articles)} fetched, "
                f"{len(candidate_articles)} candidate(s), "
                f"{len(selected_articles)} selected, "
                f"{duplicates} duplicate(s) filtered -> {resolved_articles_path}"
            )

        if "brief" in stages:
            from app.services.briefing_service import build_podcast_briefing

            if current_articles is None:
                resolved_articles_path = _resolve_input_file(
                    args.articles,
                    default_articles_path if "news" in stages else resolved_articles_path,
                    "Articles fixture",
                )
                current_articles = _load_json(resolved_articles_path)

            articles = current_articles.get("articles", [])
            interests = current_articles.get("interests", [])
            if not articles:
                raise ValueError("Articles fixture contains no articles.")
            selected_articles, _candidate_articles, _duplicates = _select_articles_for_briefing(
                articles,
                interests,
                current_articles.get("duration", args.duration),
            )
            if selected_articles:
                articles = selected_articles

            print("Stage brief: building podcast briefing...")
            briefing_result = await build_podcast_briefing(articles, interests)
            current_briefing = briefing_result.briefing
            resolved_briefing_path.parent.mkdir(parents=True, exist_ok=True)
            resolved_briefing_path.write_text(
                json.dumps(
                    current_briefing.model_dump(),
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            tb_count = len(current_briefing.topic_briefings)
            print(
                f"  Brief: {tb_count} topic(s), "
                f"theme='{current_briefing.episode_theme[:80]}' -> {resolved_briefing_path}"
            )

        if "plan" in stages:
            from app.services.conversation_plan_service import build_conversation_plan

            if current_briefing is None:
                resolved_briefing_path = _resolve_input_file(
                    args.briefing_file,
                    resolved_briefing_path,
                    "Briefing file",
                )
                current_briefing = _load_briefing(resolved_briefing_path)

            print("Stage plan: building conversation plan...")
            plan_result = await build_conversation_plan(
                current_briefing,
                args.speaker_mode,
                args.tone,
                args.duration,
            )
            current_plan = plan_result.plan
            resolved_plan_path.parent.mkdir(parents=True, exist_ok=True)
            resolved_plan_path.write_text(
                json.dumps(
                    current_plan.model_dump(),
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            beats = current_plan.beats
            beat_count = len(beats) if isinstance(beats, list) else 0
            print(f"  Plan: {beat_count} beat(s) -> {resolved_plan_path}")

        if "script" in stages:
            from app.services.script_quality import run_quality_checks_and_revise
            from app.services.script_turns import render_script_from_turns
            from app.services.script_writer_service import write_signalcast_script

            if current_briefing is None:
                resolved_briefing_path = _resolve_input_file(
                    args.briefing_file,
                    resolved_briefing_path,
                    "Briefing file",
                )
                current_briefing = _load_briefing(resolved_briefing_path)
            if current_plan is None:
                resolved_plan_path = _resolve_input_file(
                    args.plan_file,
                    resolved_plan_path,
                    "Plan file",
                )
                current_plan = _load_plan(resolved_plan_path)

            print("Stage script: writing podcast script...")
            duration_minutes = DURATION_CONFIG.get(args.duration, 2)
            writer_result = await write_signalcast_script(
                current_briefing,
                current_plan,
                args.speaker_mode,
                args.tone,
                args.duration,
                duration_minutes,
            )
            turns = await run_quality_checks_and_revise(
                writer_result.turns,
                args.speaker_mode,
            )
            current_script = render_script_from_turns(turns, args.speaker_mode)
            resolved_script_path.parent.mkdir(parents=True, exist_ok=True)
            resolved_script_path.write_text(current_script, encoding="utf-8")
            wc = _count_words(current_script)
            print(f"  Script: {wc} words -> {resolved_script_path}")

        if "audio" in stages:
            from app.services.tts_service import generate_audio

            if current_script is None:
                resolved_script_path = _resolve_input_file(
                    args.script_file,
                    resolved_script_path,
                    "Script file",
                )
                current_script = resolved_script_path.read_text(encoding="utf-8")

            print("Stage audio: generating audio...")
            result = await generate_audio(
                current_script,
                speaker_mode=args.speaker_mode,
            )
            src = BACKEND_DIR / "audio" / result.filename
            resolved_audio_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(resolved_audio_path))
            print(f"  Audio: {resolved_audio_path.stat().st_size} bytes -> {resolved_audio_path}")

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_run())
    except ValueError as exc:
        parser.error(str(exc))
    finally:
        loop.close()

    print(f"\nDone. Outputs under {FIXTURE_BASE}")


if __name__ == "__main__":
    main()
