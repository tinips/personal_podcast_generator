# Neural Notes

Neural Notes is a personalized AI podcast generator that turns recent real news into short spoken episodes. A user saves interests, selects topics, chooses tone, duration, frequency, and speaker mode, then generates an MP3 episode with source articles, script text, local scheduling, and product-health metrics.

The project intentionally favors a clean, working end-to-end vertical slice over production infrastructure. Provider failures are surfaced clearly instead of creating fake successful episodes.

## What It Does

- Lets a user save interests and select one or more topics for an episode.
- Supports professional, casual, and energetic tones.
- Supports short, normal, and long durations with topic limits.
- Supports solo host and two-host dialogue modes.
- Fetches recent articles from NewsAPI.ai.
- Uses OpenAI to create a briefing, conversation plan, and final structured script turns.
- Uses ElevenLabs to generate MP3 audio.
- Stores generated episode metadata in SQLite and audio files locally.
- Shows saved episodes, sources, scripts, audio playback, schedules, and a product-health dashboard with KPI drill-downs and recent-run traces.

## Stack

- Backend: FastAPI, Python, SQLite, OpenAI, ElevenLabs, NewsAPI.ai
- Frontend: Next.js 15 App Router, React, TypeScript, Tailwind CSS
- Storage: SQLite metadata in `backend/data/podcast.db`; MP3 files in `backend/audio/`
- Demo audio: root `sample.mp3` is a committed sample generated episode artifact, not a production fallback

## Architecture Notes

The backend keeps FastAPI routes thin and puts the generation work in explicit Python services. `backend/app/services/podcast_service.py` orchestrates the pipeline, while provider-specific and responsibility-specific modules handle news retrieval, briefing, planning, script writing, deterministic quality checks, TTS, storage, and metrics. SQLite CRUD lives under `backend/app/repositories/`.

The AI workflow is implemented as clear backend service steps instead of a workflow framework. Recent articles move through filtering, source-grounded briefing, episode planning, structured speaker turns, audio generation, and SQLite persistence. The OpenAI path is briefing -> planning -> writing: the planner decides whether stories should share a source-backed theme or stay as a mixed briefing, records that editorial reasoning in `connection_rationale`, and uses `transition_notes` plus each beat's `continuity_note` for concrete transitions. The older redundant `transition_policy` field was removed so the planner has one place for reasoning and one place for transition guidance. If the workflow needed durable retries, resumability, human review, or richer state inspection, a production version could move orchestration to workers or LangGraph.

The frontend is a Next.js/React/TypeScript app in `frontend/`. It calls the FastAPI backend directly, stores lightweight local preferences in the browser, and displays the Generate, Episodes, Schedules, and Dashboard workflows.

## Quick Start With Docker

Docker Compose is the recommended setup path. It runs the FastAPI backend and Next.js frontend in separate containers while keeping SQLite and local MP3 storage visible in the repository.

1. Copy the example environment file to the repo root:

```bash
cp .env.example .env
```

PowerShell equivalent:

```powershell
Copy-Item .env.example .env
```

2. Fill in real provider keys and voice IDs in `.env`:

```env
OPENAI_API_KEY=...
ELEVENLABS_API_KEY=...
ELEVENLABS_VOICE_JOHN_CREATIVE=...
ELEVENLABS_VOICE_MAYA_EDUCATIONAL=...
NEWS_API_KEY=...
NEXT_PUBLIC_API_URL=http://localhost:8000
```

3. Start both containers:

```bash
docker compose up --build
```

4. Open:

```text
Frontend: http://localhost:3000
Backend health: http://localhost:8000/health
```

Docker Compose reads provider keys from the root `.env` file and passes them to the backend container. The frontend image is built with `NEXT_PUBLIC_API_URL=http://localhost:8000` because browser requests must use the host-accessible backend URL, not Docker's internal `backend` service name.

SQLite data is bind-mounted from `./backend/data` to `/app/data`. Generated MP3 files are bind-mounted from `./backend/audio` to `/app/audio`. That keeps imported local data, copied database files, and generated audio visible from both the host machine and the backend container. The backend image installs the `ffmpeg` package, which provides both `ffmpeg` and `ffprobe` for dialogue audio assembly.

## Local Development Setup

Use the local Python/Node setup when you want to run the backend and frontend directly on your machine instead of through Docker.

Backend:

```bash
cd backend
pip install -r requirements.txt
cp ../.env.example .env
uvicorn app.main:app --reload
```

For this non-Docker path, `backend/.env` is the backend's local config file. It may include the frontend `NEXT_PUBLIC_API_URL` placeholder from `.env.example`, but the backend only consumes the provider and optional ffmpeg variables.

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000. The frontend reads `NEXT_PUBLIC_API_URL` and defaults to `http://127.0.0.1:8000`.

## Environment Variables

For the recommended Docker setup, copy `.env.example` to a root `.env` so Compose can pass both backend provider keys and the frontend API URL to the right containers. For non-Docker local backend runs, backend API keys go in `backend/.env`. Do not commit real keys.

This split gives Docker Compose one root environment file to read while keeping the local Python/Node workflow available for development.

| Variable | Required | Description |
| --- | --- | --- |
| `NEWS_API_KEY` | Yes | NewsAPI.ai key for recent article retrieval |
| `OPENAI_API_KEY` | Yes | OpenAI key for briefing, planning, and script writing |
| `ELEVENLABS_API_KEY` | Yes | ElevenLabs key for text-to-speech |
| `ELEVENLABS_VOICE_JOHN_CREATIVE` | Yes | John voice ID for solo mode and dialogue host turns |
| `ELEVENLABS_VOICE_MAYA_EDUCATIONAL` | Yes | Maya voice ID for dialogue guest analyst turns |
| `FFMPEG_BINARY` | Optional | Explicit path to `ffmpeg` if it is not on PATH |
| `FFPROBE_BINARY` | Optional | Explicit path to `ffprobe` if it is not on PATH |

Dialogue audio uses `pydub` to assemble multiple ElevenLabs MP3 segments, so two-host mode needs external `ffmpeg` and `ffprobe` binaries. Solo mode uses ElevenLabs direct MP3 output.

`NEXT_PUBLIC_API_URL` is a non-secret frontend setting. Docker Compose sets it to `http://localhost:8000`; for non-Docker local development the app defaults to `http://127.0.0.1:8000` if it is unset.

Windows example:

```powershell
winget install Gyan.FFmpeg
ffmpeg -version
ffprobe -version
```

Docker users can leave `FFMPEG_BINARY` and `FFPROBE_BINARY` commented because the backend image includes `ffmpeg`/`ffprobe`. If the binaries are not on PATH for non-Docker local runs, uncomment and set those variables in `backend/.env`.

## How To Generate A Podcast

1. Start the app with `docker compose up --build`.
2. Open the frontend on `http://localhost:3000`.
3. In the Generate tab, add interests such as `AI`, `startups`, or `sports`.
4. Select topics, tone, duration, and speaker mode.
5. Click Generate Podcast.
6. Open the Episodes tab to play the MP3, inspect the script, and open article sources.
7. Open the Dashboard tab to view local product and workflow metrics.

Generated MP3 files are written to `backend/audio/`. Episode metadata, sources, generation status, usage estimates, schedules, seen URLs, and local interaction events are stored in `backend/data/podcast.db`.

## API Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Returns service health and missing required config keys |
| POST | `/api/podcast/generate` | Generates one podcast episode from selected interests and preferences |
| GET | `/api/episodes` | Lists saved episodes |
| DELETE | `/api/episodes/{episode_id}` | Deletes a saved episode and its local audio file when present |
| POST | `/api/episodes/{episode_id}/events` | Records local UI events such as audio played or sources opened |
| GET | `/api/dashboard/metrics` | Returns dashboard metrics derived from SQLite |
| POST | `/api/schedules` | Creates a local daily or weekly schedule |
| GET | `/api/schedules` | Lists schedules, filtered by `user_id` query parameter |
| PUT | `/api/schedules/{schedule_id}` | Updates a saved schedule |
| DELETE | `/api/schedules/{schedule_id}` | Deletes a saved schedule |
| POST | `/api/scheduler/run` | Manually runs due schedules, or one schedule when `schedule_id` is provided |

Example generation request:

```bash
curl -X POST http://localhost:8000/api/podcast/generate \
  -H "Content-Type: application/json" \
  -d '{"selected_interests":["AI","startups"],"tone":"professional","duration":"normal","speaker_mode":"dialogue","frequency":"manual","user_id":"demo-user"}'
```

## Generation Flow

```text
selected interests
-> NewsAPI.ai article retrieval
-> required-field filtering
-> URL deduplication
-> deterministic title-token relevance filtering
-> seen-article filtering
-> balanced article selection
-> OpenAI briefing
-> OpenAI conversation plan
-> OpenAI structured script turns
-> deterministic script/TTS safety checks
-> ElevenLabs MP3 generation
-> SQLite metadata and local audio storage
-> frontend episode, sources, audio player, and dashboard
```

Routes are kept relatively thin in `backend/app/main.py`; orchestration lives in `podcast_service.py`, with provider-specific and pipeline-specific work split into service modules.

Article retrieval uses two layers of counts. The backend fetches a candidate pool per selected interest, then selects only the final articles that go into the OpenAI briefing:

- `short`: fetches 10 candidates per topic, selects 1 article total
- `normal`: fetches 15 candidates per topic, selects 2 articles total
- `long`: fetches 25 candidates per topic, selects 3 articles total

Selection first tries to cover each selected interest with one eligible article, then fills any remaining slots from the filtered candidate pool.

### Pipeline Timing And Parallelism

Workflow timings are stored per episode so the Dashboard can explain where generation time is spent. The OpenAI stages currently run sequentially; the briefer is not parallelized today:

- `briefing_llm_ms` is one source-grounded OpenAI call over the selected article content.
- `conversation_planning_llm_ms` is one global planning call that needs the full briefing context.
- `script_writer_llm_ms` is one writer call that turns the plan into validated speaker turns.

News retrieval is parallelized across selected interests, and dialogue TTS uses bounded parallel ElevenLabs requests per speaker turn before assembling the MP3 in order. Because TTS turns can run concurrently, the latency bottleneck may be an OpenAI stage even when ElevenLabs performs more individual calls. Parallel briefing extraction per article or topic is only a future optimization idea, not current behavior; it would need a small synthesis step afterward. The planner should remain global because it needs the full episode context.

## Dashboard

The Dashboard tab is local product observability for the vertical slice, not production SaaS analytics. It reads from SQLite only and does not call NewsAPI.ai, OpenAI, or ElevenLabs.

The current Dashboard is structured as a product-health monitoring view:

- executive "Personal Podcast Monitoring" hero with status, last-updated time, and a human-readable diagnosis
- four KPI cards: delivery rate, average generation time, average cost per completed episode, and play rate
- Reliability Breakdown
- Latency Breakdown
- Cost Breakdown
- Article Pipeline
- Recent Runs debug log with expandable workflow traces

The Article Pipeline section follows the actual backend order: `Fetched -> Invalid -> Dup -> Irrelevant -> Seen -> Used`. For a consistent local demo experience, the visible chart uses deterministic mock/demo counts for every displayed row to demonstrate the funnel consistently; it does not write fake article pipeline data into generated episode metadata.

Cost metrics are estimates from local tool-usage counters, not invoices. OpenAI usage is captured per LLM stage when response usage metadata is available, with a character-count fallback; the dashboard aggregates those into an expandable OpenAI row for Briefing LLM, Conversation Plan LLM, and Script Writer LLM. ElevenLabs cost is estimated from generated characters using the configured multilingual text-to-speech estimate, so it typically dominates demo cost. News retrieval is shown as zero estimated provider cost.

The recent-runs table is intentionally framed as a high-level debug log. It preserves per-run status, selected interests, speaker mode, source count, freshness window, generation time, estimated cost, bottleneck, and expandable stage timings while leaving detailed article filtering to the Article Pipeline section.

## Demo, Devtools, And Tests

The active developer utilities live in `backend/devtools/`:

- `run_script_fixture_pipeline.py` runs the episode-generation pipeline in stages.

`run_script_fixture_pipeline.py` is the main staged development helper. It mirrors the real app pipeline and can run news retrieval, briefing, planning, script writing, and audio rendering independently.

Useful dev pipeline examples:

```bash
python backend/devtools/run_script_fixture_pipeline.py --interests AI data --news
python backend/devtools/run_script_fixture_pipeline.py --brief
python backend/devtools/run_script_fixture_pipeline.py --plan -m d -t p -d n
python backend/devtools/run_script_fixture_pipeline.py --script -m d -t p -d n
python backend/devtools/run_script_fixture_pipeline.py --audio -m d
python backend/devtools/run_script_fixture_pipeline.py --interests AI data --news --brief --plan --script --audio
```

This stage runner creates and reuses saved artifacts under `backend/devtools/outputs/script_iteration/`:

- `--news` writes article fixtures with selected articles plus the inspectable candidate pool
- `--brief` reads articles and writes briefing JSON
- `--plan` reads briefing and writes plan JSON
- `--script` reads briefing + plan and writes script text
- `--audio` reads script text and writes MP3

Each stage can run independently as long as the previous stage has already saved an artifact. For example, after `--news`, `--brief` can be run without passing a fixture name; after `--brief`, `--plan` can pick up the latest briefing automatically.

The `--news` artifact includes:

- `raw_article_count`: all articles returned by NewsAPI.ai
- `candidate_article_count`: articles that survived required-field, URL dedupe, and title relevance filters
- `article_count`: final selected articles sent to the OpenAI briefing

The repository also contains existing development artifacts under `backend/outputs/script_iteration/` and `outputs/`, including prior article fixtures, briefing/plan/script outputs, rendered MP3s, baselines, smoke-test audio files, and local dev logs. These are inspection artifacts, not production storage; generated runtime episodes still use `backend/data/` and `backend/audio/`.

Backend tests live in `backend/tests/`:

- `test_audio_assembly.py`
- `test_dialogue_audio_pipeline.py`
- `test_dialogue_parser.py`
- `test_pipeline_models.py`
- `test_title_relevance_filter.py`

Run them with:

```bash
pytest backend/tests
```

## Scheduling

Schedules are simple local records. The Generate tab can save a Daily or Weekly configuration, and the Schedules tab can edit, delete, run one schedule immediately, or run all due schedules.

`POST /api/scheduler/run` is a manual trigger for local scheduled generation. In production this would move to cron, a job queue, or managed background workers.

## Error Behavior

- Missing `NEWS_API_KEY` or NewsAPI.ai retrieval failure stops generation with a clear error.
- No usable articles returns a clear message instead of generating from weak data.
- Missing `OPENAI_API_KEY` or OpenAI failure stops generation with a clear error.
- Missing `ELEVENLABS_API_KEY`, missing voice IDs, ffmpeg problems, or ElevenLabs failures are surfaced clearly.
- Audio failures are recorded as unsuccessful `audio_failed` episodes with no audio path and an error message.
- A successful episode requires real selected articles, a real OpenAI-generated script, and a real ElevenLabs MP3.

## Validation

Frontend validation after frontend changes:

```bash
cd frontend
npm run typecheck
npm run build
```

Backend static validation:

```bash
python -m compileall backend/app backend/scripts backend/devtools backend/tests
```

Backend tests:

```bash
pytest backend/tests
```

The audio tests use fake MP3 segments and do not call ElevenLabs. They are
skipped automatically when local `ffmpeg`/`ffprobe` binaries are unavailable.

Documentation-only validation:

```bash
git diff --check
```

## Current Scope

This implementation deliberately uses SQLite, local files, a manual scheduler endpoint, deterministic relevance filters, approximate duration control through word-count targets, and no authentication. Those are intentional constraints to keep the project understandable, inspectable, and end-to-end functional.

Natural production improvements would include Postgres, authentication, background jobs, managed scheduling, retries/backoff, object storage, better source ranking, factuality checks, stronger observability, cost reconciliation, caching, saved user preferences, and deployment hardening.

## Final Checklist

- Docker Compose starts the backend and frontend with `docker compose up --build`.
- Backend health is available at `http://localhost:8000/health`.
- Frontend is available at `http://localhost:3000`.
- Podcast generation works with real provider keys.
- MP3 audio is generated in `backend/audio/`.
- Audio plays in the Episodes UI.
- Dashboard loads from SQLite metrics.
- Schedules can be saved and manually run.
- `sample.mp3` is included as a sample generated episode artifact.
- `.env.example` contains placeholders only.
- `README.md` explains setup and validation clearly.
- `solution.md` explains architectural decisions and trade-offs honestly.
