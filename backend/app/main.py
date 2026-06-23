import os
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

from . import database
from .models import (
    GenerateRequest,
    GenerateResponse,
    DashboardMetrics,
    EpisodeResponse,
    EpisodeEventRequest,
    ScheduleRequest,
    ScheduleResponse,
    DURATION_CONFIG,
    VALID_DURATIONS,
    VALID_SPEAKER_MODES,
)
from .repositories import episode_repository
from .services import metrics as metrics_service
from .services.podcast_service import generate_podcast, NoNewArticlesError
from .services.news_service import NewsServiceError
from .services import health_service
from .services.script_service import ScriptGenerationError
from .services.tts_service import AudioGenerationError


def _schedule_voice_for_mode(speaker_mode: str) -> str:
    if speaker_mode == "dialogue":
        return "John creative + Maya educational"
    return "John creative"


@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init_db()
    from .services.tts_service import _check_ffmpeg_available
    if not _check_ffmpeg_available():
        import warnings
        warnings.warn(
            "ffmpeg is not installed or not on PATH. "
            "Dialogue (two-host) audio requires ffmpeg for MP3 assembly. "
            "Solo mode via ElevenLabs direct MP3 output will still work. "
            "Install ffmpeg: https://ffmpeg.org/download.html"
        )
    yield


app = FastAPI(title="Neural Notes API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_origin_regex=(
        r"^http://("
        r"localhost|127\.0\.0\.1|"
        r"192\.168\.\d{1,3}\.\d{1,3}|"
        r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
        r"172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}"
        r"):(3000|5173)$"
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

AUDIO_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "audio")
os.makedirs(AUDIO_DIR, exist_ok=True)
app.mount("/audio", StaticFiles(directory=AUDIO_DIR), name="audio")


@app.get("/health")
async def health():
    required = [
        "NEWS_API_KEY",
        "OPENAI_API_KEY",
        "ELEVENLABS_API_KEY",
        "ELEVENLABS_VOICE_JOHN_CREATIVE",
        "ELEVENLABS_VOICE_MAYA_EDUCATIONAL",
    ]
    missing = [key for key in required if not os.getenv(key)]
    return {"status": "ok", "missing_config": missing}


@app.post("/api/podcast/generate", response_model=GenerateResponse)
async def api_generate(req: GenerateRequest):
    try:
        episode = await generate_podcast(req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except NoNewArticlesError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (NewsServiceError, ScriptGenerationError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except AudioGenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if not episode.success:
        raise HTTPException(
            status_code=502,
            detail=episode.error_message or "Podcast generation failed.",
        )
    return GenerateResponse(episode=episode)


@app.get("/api/episodes", response_model=list[EpisodeResponse])
async def api_list_episodes():
    return episode_repository.get_all_episodes()


@app.delete("/api/episodes/{episode_id}")
async def api_delete_episode(episode_id: str):
    episode = episode_repository.delete_episode(episode_id)
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found.")

    if episode.audio_url:
        audio_path = os.path.join(AUDIO_DIR, os.path.basename(episode.audio_url))
        if os.path.isfile(audio_path):
            try:
                os.remove(audio_path)
            except OSError:
                pass

    return {"ok": True}


@app.get("/api/dashboard/metrics", response_model=DashboardMetrics)
async def api_dashboard_metrics():
    return metrics_service.get_dashboard_metrics()


@app.get("/api/health")
async def api_health():
    return await health_service.check_all_apis()


@app.post("/api/episodes/{episode_id}/events")
async def api_record_episode_event(
    episode_id: str,
    req: EpisodeEventRequest,
):
    try:
        episode_repository.insert_episode_event(
            episode_id=episode_id,
            event_type=req.event_type,
            value=req.value,
        )
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "not found" in message.lower() else 400
        raise HTTPException(status_code=status_code, detail=message) from exc
    return {"ok": True}


@app.post("/api/schedules", response_model=ScheduleResponse)
async def api_create_schedule(req: ScheduleRequest):
    try:
        ScheduleRequest.model_validate(req.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    schedule_id = uuid.uuid4().hex[:12]
    schedule = ScheduleResponse(
        id=schedule_id,
        user_id=req.user_id,
        name=req.name,
        selected_interests=req.selected_interests,
        frequency=req.frequency,
        duration=req.duration,
        tone=req.tone,
        voice=_schedule_voice_for_mode(req.speaker_mode),
        speaker_mode=req.speaker_mode,
        last_run_at=None,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    episode_repository.insert_schedule(schedule)
    return schedule


@app.get("/api/schedules", response_model=list[ScheduleResponse])
async def api_list_schedules(user_id: str = ""):
    return episode_repository.get_schedules(user_id)


@app.put("/api/schedules/{schedule_id}", response_model=ScheduleResponse)
async def api_update_schedule(schedule_id: str, req: ScheduleRequest):
    existing = episode_repository.get_schedule_by_id(schedule_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Schedule not found.")

    try:
        ScheduleRequest.model_validate(req.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    updated = ScheduleResponse(
        id=existing.id,
        user_id=existing.user_id,
        name=req.name,
        selected_interests=req.selected_interests,
        frequency=req.frequency,
        duration=req.duration,
        tone=req.tone,
        voice=_schedule_voice_for_mode(req.speaker_mode),
        speaker_mode=req.speaker_mode,
        last_run_at=existing.last_run_at,
        created_at=existing.created_at,
    )
    return episode_repository.update_schedule(updated)


@app.delete("/api/schedules/{schedule_id}")
async def api_delete_schedule(schedule_id: str):
    if not episode_repository.delete_schedule(schedule_id):
        raise HTTPException(status_code=404, detail="Schedule not found.")
    return {"ok": True}


def _record_skipped_generation(schedule: ScheduleResponse, reason: str) -> str:
    episode_id = uuid.uuid4().hex[:12]
    episode = EpisodeResponse(
        id=episode_id,
        title="Skipped: no fresh articles",
        summary=reason,
        script="",
        audio_url=None,
        interests=schedule.selected_interests,
        articles=[],
        tone=schedule.tone,
        duration=schedule.duration,
        frequency=schedule.frequency,
        voice=schedule.voice,
        speaker_mode=schedule.speaker_mode,
        user_id=schedule.user_id,
        generation_type="scheduled",
        schedule_id=schedule.id,
        article_count=0,
        duplicate_articles_filtered=0,
        seen_articles_filtered=0,
        total_fetched=0,
        invalid_articles_filtered=0,
        title_irrelevant_articles_filtered=0,
        estimated_cost_usd=0.0,
        tool_usage=[],
        workflow_timings={},
        created_at=datetime.now(timezone.utc).isoformat(),
        generation_time_ms=None,
        success=False,
        status="skipped",
        error_message=reason,
        selected_interest_count=len(schedule.selected_interests),
    )
    episode_repository.insert_episode(episode)
    return episode_id


def _check_schedule_due(schedule) -> bool:
    from datetime import datetime, timedelta, timezone

    if not schedule.last_run_at:
        return True
    try:
        last_run = datetime.fromisoformat(schedule.last_run_at)
    except (ValueError, TypeError):
        return True

    now = datetime.now(timezone.utc)
    if schedule.frequency == "daily":
        return (now - last_run) > timedelta(hours=24)
    elif schedule.frequency == "weekly":
        return (now - last_run) > timedelta(days=7)
    return False  # manual or unknown — only run explicitly


@app.post("/api/scheduler/run")
async def api_scheduler_run(user_id: str = "", schedule_id: str = ""):
    from datetime import datetime, timedelta, timezone

    if schedule_id:
        schedule = episode_repository.get_schedule_by_id(schedule_id)
        if not schedule:
            raise HTTPException(status_code=404, detail="Schedule not found.")
        schedules_to_run = [schedule]
        force_run = True
    else:
        schedules_to_run = episode_repository.get_schedules(user_id)
        force_run = False

    results: list[dict] = []
    for schedule in schedules_to_run:
        if not force_run:
            due = _check_schedule_due(schedule)
            if not due:
                results.append({
                    "schedule_id": schedule.id,
                    "schedule_name": schedule.name,
                    "status": "not_due",
                    "reason": "Schedule is not due yet.",
                })
                continue
        try:
            req = GenerateRequest(
                selected_interests=schedule.selected_interests,
                tone=schedule.tone,
                duration=schedule.duration,
                frequency=schedule.frequency,
                user_id=schedule.user_id,
                speaker_mode=schedule.speaker_mode,
                generation_type="scheduled",
                schedule_id=schedule.id,
            )
            episode = await generate_podcast(req)
            episode_repository.update_schedule_last_run(schedule.id)
            results.append({
                "schedule_id": schedule.id,
                "schedule_name": schedule.name,
                "status": "generated",
                "episode_id": episode.id,
            })
        except NoNewArticlesError as exc:
            skipped_episode_id = _record_skipped_generation(schedule, str(exc))
            episode_repository.update_schedule_last_run(schedule.id)
            results.append({
                "schedule_id": schedule.id,
                "schedule_name": schedule.name,
                "status": "skipped",
                "episode_id": skipped_episode_id,
                "reason": "No new articles available.",
            })
        except (NewsServiceError, ScriptGenerationError, AudioGenerationError) as exc:
            results.append({
                "schedule_id": schedule.id,
                "schedule_name": schedule.name,
                "status": "failed",
                "reason": str(exc)[:200],
            })

    return {"results": results}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
