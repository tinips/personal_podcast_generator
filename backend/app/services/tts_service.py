import logging
import os
import re
import shutil
import uuid
import asyncio
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Optional
import httpx

from .script_turns import (
    ScriptTurn,
    ScriptTurnValidationError,
    validate_script_turns,
)

FFMPEG_BINARY_ENV = "FFMPEG_BINARY"
FFPROBE_BINARY_ENV = "FFPROBE_BINARY"


def _prepend_env_binary_dirs_to_path() -> None:
    path_parts = os.environ.get("PATH", "").split(os.pathsep)
    normalized_parts = {part.rstrip("\\/").lower() for part in path_parts if part}
    for env_key in (FFMPEG_BINARY_ENV, FFPROBE_BINARY_ENV):
        configured = os.getenv(env_key, "").strip().strip('"')
        if not configured:
            continue
        binary_path = Path(configured).expanduser()
        try:
            binary_exists = binary_path.is_file()
        except OSError:
            binary_exists = False
        if not binary_exists:
            continue
        binary_dir = str(binary_path.parent)
        if binary_dir.rstrip("\\/").lower() not in normalized_parts:
            os.environ["PATH"] = binary_dir + os.pathsep + os.environ.get("PATH", "")
            normalized_parts.add(binary_dir.rstrip("\\/").lower())


_prepend_env_binary_dirs_to_path()

try:
    from pydub import AudioSegment
    import pydub.utils as pydub_utils
except ImportError:  # pragma: no cover - exercised in environments without pydub
    AudioSegment = None
    pydub_utils = None

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = Path(__file__).resolve().parents[3]
AUDIO_DIR = BACKEND_DIR / "audio"
ROOT_SAMPLE_PATH = REPO_ROOT / "sample.mp3"
logger = logging.getLogger(__name__)
SPEAKER_LABEL_RE = re.compile(
    r"(?:^|\b)(JOHN|MAYA|MAY\b|HOST\s*1|HOST\s*2|HOST|Speaker\s*1|Speaker\s*2)\s*:\s*",
    re.IGNORECASE | re.MULTILINE,
)
DIALOGUE_LABEL_LINE_RE = re.compile(r"^\s*(JOHN|MAYA):\s*$", re.IGNORECASE)
DIALOGUE_INLINE_LABEL_RE = re.compile(r"^\s*(JOHN|MAYA):\s+\S", re.IGNORECASE)
SPEAKER_LIKE_LINE_RE = re.compile(
    r"^\s*([A-Za-z][A-Za-z0-9 ]{0,30})\s*:",
    re.IGNORECASE,
)
SOLO_SENTENCE_PAUSE_RE = re.compile(r"([.!?])\s+(?=[\"']?[A-Z0-9])")
SOLO_PHRASE_PAUSE_RE = re.compile(r"([;:])\s+(?=\S)")
JOHN_VOICE_ENV = "ELEVENLABS_VOICE_JOHN_CREATIVE"
MAYA_VOICE_ENV = "ELEVENLABS_VOICE_MAYA_EDUCATIONAL"
TURN_SILENCE_MS = 200
TURN_FADE_MS = 30
DIALOGUE_TTS_CONCURRENCY = 4
JOHN_VOICE_SETTINGS = {
    "stability": 0.68,
    "similarity_boost": 0.75,
    "style": 0.12,
    "use_speaker_boost": True,
}
MAYA_VOICE_SETTINGS = {
    "stability": 0.78,
    "similarity_boost": 0.75,
    "style": 0.06,
    "use_speaker_boost": False,
}
SHARED_VOICE_SETTINGS = {
    "stability": 0.75,
    "similarity_boost": 0.75,
    "style": 0.10,
    "use_speaker_boost": False,
    "speed": 0.9,
}


@dataclass(frozen=True)
class AudioGenerationResult:
    filename: str
    audio_url: str
    status: str
    error_message: Optional[str] = None
    elevenlabs_calls: int = 0
    elevenlabs_characters: int = 0
    elevenlabs_purpose: str = "text_to_speech"


class AudioGenerationError(RuntimeError):
    def __init__(
        self,
        message: str,
        calls: int = 0,
        characters: int = 0,
        purpose: str = "text_to_speech",
    ) -> None:
        super().__init__(message)
        self.calls = calls
        self.characters = characters
        self.purpose = purpose


@dataclass(frozen=True)
class DialogueSegment:
    speaker: str
    text: str


@dataclass(frozen=True)
class DialogueRenderJob:
    index: int
    role_label: str
    text: str
    voice_id: str
    voice_settings: dict[str, object]


@dataclass(frozen=True)
class FfmpegToolStatus:
    name: str
    found: bool
    source: str
    path: Optional[str] = None


@dataclass(frozen=True)
class FfmpegStatus:
    ffmpeg: FfmpegToolStatus
    ffprobe: FfmpegToolStatus

    @property
    def available(self) -> bool:
        return self.ffmpeg.found and self.ffprobe.found


def _resolve_binary(tool_name: str, env_key: str) -> FfmpegToolStatus:
    configured = os.getenv(env_key, "").strip().strip('"')
    if configured:
        binary_path = Path(configured).expanduser()
        try:
            binary_exists = binary_path.is_file()
        except OSError:
            binary_exists = False
        if binary_exists:
            return FfmpegToolStatus(tool_name, True, "env", str(binary_path))
        return FfmpegToolStatus(tool_name, False, "env_missing", configured)

    discovered = shutil.which(tool_name)
    if discovered:
        return FfmpegToolStatus(tool_name, True, "PATH", discovered)
    winget_binary = _find_winget_binary(tool_name)
    if winget_binary:
        return FfmpegToolStatus(tool_name, True, "winget", str(winget_binary))
    return FfmpegToolStatus(tool_name, False, "missing")


def _find_winget_binary(tool_name: str) -> Path | None:
    local_app_data = os.getenv("LOCALAPPDATA", "")
    if not local_app_data:
        return None
    packages_dir = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
    if not packages_dir.is_dir():
        return None
    try:
        return next(packages_dir.glob(f"**/{tool_name}.exe"))
    except StopIteration:
        return None


def _get_ffmpeg_status(configure_pydub: bool = True) -> FfmpegStatus:
    status = FfmpegStatus(
        ffmpeg=_resolve_binary("ffmpeg", FFMPEG_BINARY_ENV),
        ffprobe=_resolve_binary("ffprobe", FFPROBE_BINARY_ENV),
    )

    if configure_pydub and AudioSegment is not None:
        if status.ffmpeg.found and status.ffmpeg.path:
            AudioSegment.converter = status.ffmpeg.path
            AudioSegment.ffmpeg = status.ffmpeg.path
        if (
            status.ffprobe.found
            and status.ffprobe.path
            and pydub_utils is not None
        ):
            prober_path = status.ffprobe.path
            pydub_utils.get_prober_name = lambda: prober_path

    return status


def _tool_basename(status: FfmpegToolStatus) -> str:
    if not status.path:
        return ""
    return Path(status.path).name


def _is_usable_mp3(path: Path) -> bool:
    try:
        data = path.read_bytes()
    except OSError:
        return False

    if len(data) < 1024:
        return False

    has_mp3_header = data.startswith(b"ID3") or (
        len(data) > 1 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0
    )
    if not has_mp3_header:
        return False

    nonzero_ratio = sum(1 for byte in data if byte != 0) / len(data)
    return nonzero_ratio > 0.05


def _strip_speaker_labels(text: str) -> str:
    cleaned = SPEAKER_LABEL_RE.sub("", text)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _normalize_segment_text(text: str) -> str:
    cleaned = _strip_speaker_labels(text)
    cleaned = cleaned.replace("**", "").replace("__", "")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _preprocess_script(script: str) -> str:
    cleaned = script
    cleaned = re.sub(r"\*\*(\w+)\*\*", r"\1", cleaned)
    cleaned = cleaned.replace("**", "")
    cleaned = cleaned.replace("__", "")
    cleaned = re.sub(r"^[#]{1,4}\s*(\w+):\s*$", r"\1:", cleaned, flags=re.MULTILINE)
    return cleaned



def _resolve_role_voice(env_key: str, role_name: str) -> tuple[str, bool]:
    configured_voice = os.getenv(env_key, "")
    if configured_voice:
        return configured_voice, True

    raise AudioGenerationError(
        f"No ElevenLabs voice configured for {role_name}. Set {env_key}."
    )


def _resolve_john_voice() -> tuple[str, bool]:
    return _resolve_role_voice(JOHN_VOICE_ENV, "John")


def _resolve_maya_voice() -> tuple[str, bool]:
    return _resolve_role_voice(MAYA_VOICE_ENV, "Maya")


def _resolve_dialogue_voices() -> tuple[str, str, bool, bool]:
    john_voice, john_cfg = _resolve_john_voice()
    maya_voice, maya_cfg = _resolve_maya_voice()
    distinct = john_voice != maya_voice

    logger.info(
        "Resolved ElevenLabs voices speaker_mode=dialogue "
        "john_configured=%s maya_configured=%s voices_distinct=%s "
        "john_id=%s maya_id=%s",
        john_cfg,
        maya_cfg,
        distinct,
        _mask_voice_id(john_voice),
        _mask_voice_id(maya_voice),
    )

    if not distinct:
        logger.warning(
            "maya_voice_missing_or_invalid: both voices resolve to the same ID. "
            "Dialogue will not sound distinct. "
            "Configure %s and %s with different IDs.",
            JOHN_VOICE_ENV,
            MAYA_VOICE_ENV,
        )

    return john_voice, maya_voice, john_cfg, maya_cfg


def _resolve_solo_voice() -> str:
    john_voice, john_configured = _resolve_john_voice()
    logger.info(
        "Resolved ElevenLabs voices speaker_mode=solo "
        "john_configured=%s maya_configured=%s voices_distinct=%s",
        john_configured,
        False,
        True,
    )
    return john_voice


def _speaker_to_voice_key(label: str) -> str:
    clean = re.sub(r"\s+", " ", label.strip().upper())
    if clean == "JOHN":
        return "host_1"
    if clean == "MAYA":
        return "host_2"
    raise AudioGenerationError(f"Unsupported dialogue speaker label: {label}.")


def _dialogue_label_errors(script: str) -> list[str]:
    errors: list[str] = []
    for line in _preprocess_script(script).splitlines():
        if DIALOGUE_INLINE_LABEL_RE.match(line):
            errors.append("JOHN/MAYA labels must be on their own line.")
            continue
        match = SPEAKER_LIKE_LINE_RE.match(line)
        if not match:
            continue
        raw_label = re.sub(r"\s+", " ", match.group(1).strip())
        label = raw_label.upper()
        if label not in {"JOHN", "MAYA"}:
            errors.append(f"Unsupported speaker label: {raw_label}.")
        elif raw_label != label:
            errors.append("JOHN/MAYA labels must be uppercase.")
    return errors



def _parse_dialogue_segments(script: str) -> list[DialogueSegment]:
    working = _preprocess_script(script)
    matches: list[tuple[str, int, int]] = []
    cursor = 0
    for raw_line in working.splitlines(keepends=True):
        line_start = cursor
        line_end = cursor + len(raw_line)
        label = DIALOGUE_LABEL_LINE_RE.fullmatch(raw_line.strip())
        if label:
            matches.append((label.group(1), line_start, line_end))
        cursor = line_end
    if not matches:
        logger.warning(
            "Dialogue parser zero matches. Raw script start (300 chars):\n%s",
            script[:300],
        )
        return []

    segments: list[DialogueSegment] = []
    speaker_sequence: list[str] = []
    for index, match in enumerate(matches):
        label, _label_start, label_end = match
        start = label_end
        end = matches[index + 1][1] if index + 1 < len(matches) else len(working)
        text = _normalize_segment_text(working[start:end])
        if not text:
            logger.debug(
                "Dialogue parser skipped empty segment for label '%s'", label
            )
            continue

        speaker = _speaker_to_voice_key(label)
        speaker_sequence.append(speaker)
        if segments and segments[-1].speaker == speaker:
            previous = segments[-1]
            segments[-1] = DialogueSegment(
                speaker=previous.speaker,
                text=f"{previous.text} {text}".strip(),
            )
        else:
            segments.append(DialogueSegment(speaker=speaker, text=text))

    host1_count = sum(1 for s in segments if s.speaker == "host_1")
    host2_count = sum(1 for s in segments if s.speaker == "host_2")
    logger.info(
        "Dialogue parsed %d segment(s) — John=%d Maya=%d sequence: %s",
        len(segments),
        host1_count,
        host2_count,
        " -> ".join(speaker_sequence) if speaker_sequence else "none",
    )
    if host2_count == 0 and matches:
        logger.warning(
            "Dialogue parser found %d label(s) but ZERO Maya segments. "
            "Raw script start (300 chars):\n%s",
            len(matches),
            script[:300],
        )
    return segments


def _build_dialogue_render_jobs_from_turns(
    turns: list[ScriptTurn],
    host_1_id: str,
    host_2_id: str,
) -> list[DialogueRenderJob]:
    validated_turns = validate_script_turns(turns, "dialogue")
    jobs: list[DialogueRenderJob] = []
    for index, turn in enumerate(validated_turns):
        role_label = "john" if turn.speaker == "host_1" else "maya"
        voice_id = host_1_id if turn.speaker == "host_1" else host_2_id
        voice_settings = (
            JOHN_VOICE_SETTINGS
            if turn.speaker == "host_1"
            else MAYA_VOICE_SETTINGS
        )
        jobs.append(
            DialogueRenderJob(
                index=index,
                role_label=role_label,
                text=turn.text,
                voice_id=voice_id,
                voice_settings=voice_settings,
            )
        )
    return jobs


def _build_solo_text_from_turns(turns: list[ScriptTurn]) -> str:
    validated_turns = validate_script_turns(turns, "solo")
    return "\n\n".join(turn.text for turn in validated_turns).strip()


def _add_solo_tts_pauses(text: str) -> str:
    """Add light pacing hints to solo TTS input without changing saved scripts."""
    paragraphs = [
        re.sub(r"\s+", " ", paragraph).strip()
        for paragraph in re.split(r"\n\s*\n", text)
        if paragraph.strip()
    ]
    paced_paragraphs: list[str] = []
    for paragraph in paragraphs:
        paced = SOLO_SENTENCE_PAUSE_RE.sub(r"\1 ... ", paragraph)
        paced = SOLO_PHRASE_PAUSE_RE.sub(r"\1 ... ", paced)
        paced = re.sub(r"(?:\s*\.\.\.\s*){2,}", " ... ", paced)
        paced_paragraphs.append(paced.strip())
    return "\n\n".join(paced_paragraphs).strip()


async def _generate_audio_segment(
    client: httpx.AsyncClient,
    api_key: str,
    text: str,
    voice_id: str,
    voice_settings: dict[str, object] | None = None,
) -> bytes:
    settings = voice_settings or SHARED_VOICE_SETTINGS
    response = await client.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        params={"output_format": "mp3_44100_128"},
        headers={
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": api_key,
        },
        json={
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": settings,
        },
    )
    response.raise_for_status()
    return response.content


async def _generate_dialogue_audio_parts_parallel(
    client: httpx.AsyncClient,
    api_key: str,
    jobs: list[DialogueRenderJob],
) -> list[bytes]:
    semaphore = asyncio.Semaphore(DIALOGUE_TTS_CONCURRENCY)

    async def render(job: DialogueRenderJob) -> bytes:
        async with semaphore:
            logger.info(
                "segment_plan index=%d speaker=%s text_chars=%d "
                "voice_role=%s voice_id=%s",
                job.index,
                job.role_label,
                len(job.text),
                job.role_label,
                _mask_voice_id(job.voice_id),
            )
            try:
                audio = await _generate_audio_segment(
                    client,
                    api_key,
                    job.text,
                    job.voice_id,
                    job.voice_settings,
                )
            except Exception as exc:
                logger.error(
                    "tts_segment_failed index=%d speaker=%s error=%s",
                    job.index,
                    job.role_label,
                    str(exc)[:200],
                )
                raise
            if not audio:
                raise AudioGenerationError(
                    "ElevenLabs returned no usable audio for a dialogue segment."
                )
            logger.info(
                "tts_segment_success index=%d speaker=%s bytes=%d",
                job.index,
                job.role_label,
                len(audio),
            )
            return audio

    results = await asyncio.gather(
        *(render(job) for job in jobs),
        return_exceptions=True,
    )

    audio_parts: list[bytes] = []
    for result in results:
        if isinstance(result, Exception):
            raise result
        audio_parts.append(result)
    return audio_parts


def _combine_mp3_segments(audio_parts: list[bytes]) -> bytes:
    if AudioSegment is None:
        raise AudioGenerationError(
            "pydub is required for valid dialogue MP3 concatenation."
        )
    if not audio_parts:
        raise AudioGenerationError("No audio segments were generated.")

    ffmpeg_ok = _check_ffmpeg_available()
    logger.info(
        "pydub combine start: segments=%d ffmpeg_available=%s",
        len(audio_parts),
        ffmpeg_ok,
    )
    if not ffmpeg_ok:
        logger.warning("ffmpeg_missing_or_unavailable")
        raise AudioGenerationError(
            "ffmpeg and ffprobe are required for dialogue MP3 assembly."
        )

    combined = AudioSegment.empty()
    turn_silence = AudioSegment.silent(duration=TURN_SILENCE_MS)

    for index, audio_bytes in enumerate(audio_parts):
        try:
            segment = AudioSegment.from_file(BytesIO(audio_bytes), format="mp3")
            seg_ms = len(segment)
            if seg_ms > TURN_FADE_MS * 2:
                segment = segment.fade_in(TURN_FADE_MS).fade_out(TURN_FADE_MS)
            if index > 0:
                combined += turn_silence
            combined += segment
            logger.info(
                "pydub_decode_success index=%d duration_ms=%d bytes_in=%d",
                index,
                seg_ms,
                len(audio_bytes),
            )
        except Exception as exc:
            logger.error(
                "pydub_decode_failed index=%d error=%s bytes_in=%d",
                index,
                str(exc)[:100],
                len(audio_bytes),
            )
            raise AudioGenerationError(
                f"pydub decode failed at segment {index}: {exc}"
            ) from exc

    output = BytesIO()
    combined.export(output, format="mp3")
    final_bytes = output.getvalue()
    total_ms = len(combined)
    logger.info(
        "pydub_export_success total_duration_ms=%d final_bytes=%d",
        total_ms,
        len(final_bytes),
    )
    return final_bytes


def _check_ffmpeg_available() -> bool:
    if AudioSegment is None:
        logger.warning("ffmpeg_check pydub_installed=false")
        return False

    status = _get_ffmpeg_status(configure_pydub=True)
    logger.info(
        "ffmpeg_check ffmpeg_found=%s ffmpeg_source=%s ffmpeg_name=%s "
        "ffprobe_found=%s ffprobe_source=%s ffprobe_name=%s",
        status.ffmpeg.found,
        status.ffmpeg.source,
        _tool_basename(status.ffmpeg),
        status.ffprobe.found,
        status.ffprobe.source,
        _tool_basename(status.ffprobe),
    )
    if not status.available:
        return False

    try:
        seg = AudioSegment.silent(duration=10)
        buf = BytesIO()
        seg.export(buf, format="mp3")
        return len(buf.getvalue()) > 0
    except Exception as exc:
        logger.warning("ffmpeg_check export_failed error=%s", str(exc)[:200])
        return False


def _mask_voice_id(voice_id: str) -> str:
    if len(voice_id) <= 4:
        return voice_id
    return f"...{voice_id[-4:]}"


async def generate_audio(
    script: str | None = None,
    speaker_mode: str = "solo",
    tone: str | None = None,
    turns: list[ScriptTurn] | None = None,
) -> AudioGenerationResult:
    _ = tone  # Tone affects script writing only; voice identity is role-based.
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    api_key = os.getenv("ELEVENLABS_API_KEY", "")
    if not api_key:
        raise AudioGenerationError(
            "ELEVENLABS_API_KEY is required for real audio generation."
        )

    validated_turns: list[ScriptTurn] | None = None
    if turns is not None:
        try:
            validated_turns = validate_script_turns(turns, speaker_mode)
        except ScriptTurnValidationError as exc:
            raise AudioGenerationError(f"Invalid TTS turns: {exc}") from exc
        clean_script = (
            _build_solo_text_from_turns(validated_turns)
            if speaker_mode == "solo"
            else "\n\n".join(turn.text for turn in validated_turns).strip()
        )
    else:
        if script is None:
            raise AudioGenerationError("Script or turns are required for TTS.")
        clean_script = _strip_speaker_labels(script)

    if not clean_script.strip():
        raise AudioGenerationError("TTS input is empty after cleanup.")

    filename = f"podcast_{uuid.uuid4().hex[:12]}.mp3"
    filepath = AUDIO_DIR / filename
    elevenlabs_calls = 0
    elevenlabs_chars = 0
    elevenlabs_purpose = (
        "dialogue_text_to_speech"
        if speaker_mode == "dialogue"
        else "text_to_speech"
    )

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            if speaker_mode == "dialogue":
                host_1_id, host_2_id, john_cfg, maya_cfg = _resolve_dialogue_voices()
                if validated_turns is not None:
                    try:
                        jobs = _build_dialogue_render_jobs_from_turns(
                            validated_turns,
                            host_1_id,
                            host_2_id,
                        )
                    except ScriptTurnValidationError as exc:
                        raise AudioGenerationError(
                            f"Invalid dialogue TTS turns: {exc}",
                            calls=elevenlabs_calls,
                            characters=elevenlabs_chars,
                            purpose=elevenlabs_purpose,
                        ) from exc
                    parsed_count = len(jobs)
                else:
                    label_errors = _dialogue_label_errors(script or "")
                    if label_errors:
                        raise AudioGenerationError(
                            "Invalid dialogue speaker labels: "
                            + " ".join(dict.fromkeys(label_errors)),
                            calls=elevenlabs_calls,
                            characters=elevenlabs_chars,
                            purpose=elevenlabs_purpose,
                        )

                    segments = _parse_dialogue_segments(script or "")
                    if not segments:
                        raise AudioGenerationError(
                            "Legacy dialogue script TTS requires parsed JOHN/MAYA speaker segments.",
                            calls=elevenlabs_calls,
                            characters=elevenlabs_chars,
                            purpose=elevenlabs_purpose,
                        )

                    jobs = []
                    for seg_idx, segment in enumerate(segments):
                        seg_text = _normalize_segment_text(segment.text)
                        if not seg_text:
                            continue
                        role_label = "john" if segment.speaker == "host_1" else "maya"
                        voice_id = (
                            host_1_id if segment.speaker == "host_1" else host_2_id
                        )
                        settings = (
                            JOHN_VOICE_SETTINGS
                            if segment.speaker == "host_1"
                            else MAYA_VOICE_SETTINGS
                        )
                        jobs.append(
                            DialogueRenderJob(
                                index=seg_idx,
                                role_label=role_label,
                                text=seg_text,
                                voice_id=voice_id,
                                voice_settings=settings,
                            )
                        )
                    parsed_count = len(segments)

                logger.info(
                    "dialogue_audio_start speaker_mode=%s "
                    "john_voice_configured=%s maya_voice_configured=%s "
                    "john_maya_same_voice=%s turn_jobs=%d",
                    speaker_mode,
                    john_cfg,
                    maya_cfg,
                    host_1_id == host_2_id,
                    parsed_count,
                )

                if not jobs:
                    raise AudioGenerationError(
                        "Dialogue TTS has no non-empty turn text.",
                        calls=elevenlabs_calls,
                        characters=elevenlabs_chars,
                        purpose=elevenlabs_purpose,
                    )

                elevenlabs_calls = len(jobs)
                elevenlabs_chars = sum(len(job.text) for job in jobs)

                try:
                    audio_parts = await _generate_dialogue_audio_parts_parallel(
                        client,
                        api_key,
                        jobs,
                    )
                except AudioGenerationError as exc:
                    raise AudioGenerationError(
                        str(exc),
                        calls=elevenlabs_calls,
                        characters=elevenlabs_chars,
                        purpose=elevenlabs_purpose,
                    ) from exc

                try:
                    audio = _combine_mp3_segments(audio_parts)
                except AudioGenerationError as exc:
                    raise AudioGenerationError(
                        str(exc),
                        calls=elevenlabs_calls,
                        characters=elevenlabs_chars,
                        purpose=elevenlabs_purpose,
                    ) from exc
                except Exception as exc:
                    raise AudioGenerationError(
                        f"Dialogue MP3 assembly failed: {exc}",
                        calls=elevenlabs_calls,
                        characters=elevenlabs_chars,
                        purpose=elevenlabs_purpose,
                    ) from exc
            else:
                voice_id = _resolve_solo_voice()
                solo_tts_text = _add_solo_tts_pauses(clean_script)
                elevenlabs_calls = 1
                elevenlabs_chars = len(solo_tts_text)
                audio = await _generate_audio_segment(
                    client,
                    api_key,
                    solo_tts_text,
                    voice_id,
                    SHARED_VOICE_SETTINGS,
                )

            filepath.write_bytes(audio)

        if not _is_usable_mp3(filepath):
            raise AudioGenerationError(
                "ElevenLabs returned an empty or invalid MP3.",
                calls=elevenlabs_calls,
                characters=elevenlabs_chars,
                purpose=elevenlabs_purpose,
            )

        return AudioGenerationResult(
            filename=filename,
            audio_url=filename,
            status="completed",
            elevenlabs_calls=elevenlabs_calls,
            elevenlabs_characters=elevenlabs_chars,
            elevenlabs_purpose=elevenlabs_purpose,
        )
    except httpx.HTTPStatusError as e:
        detail = e.response.text.strip().replace("\n", " ")[:300]
        raise AudioGenerationError(
            "ElevenLabs audio generation failed "
            f"(HTTP {e.response.status_code}: {detail}).",
            calls=elevenlabs_calls,
            characters=elevenlabs_chars,
            purpose=elevenlabs_purpose,
        ) from e
    except httpx.HTTPError as e:
        raise AudioGenerationError(
            f"ElevenLabs audio generation failed: {e}",
            calls=elevenlabs_calls,
            characters=elevenlabs_chars,
            purpose=elevenlabs_purpose,
        ) from e
    except AudioGenerationError:
        raise
    except Exception as e:
        raise AudioGenerationError(
            f"ElevenLabs audio generation failed: {e}",
            calls=elevenlabs_calls,
            characters=elevenlabs_chars,
            purpose=elevenlabs_purpose,
        ) from e


if __name__ == "__main__":
    test_script = """JOHN:
Welcome to Neural Notes.

MAYA:
The important context is that this trend is accelerating.

JOHN:
That is why it matters."""

    segments = _parse_dialogue_segments(test_script)
    print(f"Parsed {len(segments)} segment(s):")
    for i, seg in enumerate(segments):
        print(f"  [{i}] speaker={seg.speaker} text={seg.text[:60]}...")

    expected_speakers = ["host_1", "host_2", "host_1"]
    actual_speakers = [s.speaker for s in segments]
    assert len(segments) == 3, f"Expected 3, got {len(segments)}"
    assert actual_speakers == expected_speakers, f"Expected {expected_speakers}, got {actual_speakers}"
    for seg in segments:
        assert "JOHN" not in seg.text.upper(), f"JOHN leaked into text: {seg.text}"
        assert "MAYA" not in seg.text.upper(), f"MAYA leaked into text: {seg.text}"
    print("All parser smoke tests passed.")
