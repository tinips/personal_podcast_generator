"""Tests for structured dialogue TTS jobs and fake audio assembly."""

from __future__ import annotations

from io import BytesIO

import pytest

from app.services.script_turns import validate_script_turns
from app.services.tts_service import (
    _build_dialogue_render_jobs_from_turns,
    _check_ffmpeg_available,
    _combine_mp3_segments,
    _get_ffmpeg_status,
)

pydub = pytest.importorskip("pydub")
AudioSegment = pydub.AudioSegment


DIALOGUE_TURNS = [
    {
        "speaker": "host_1",
        "text": "Welcome to Neural Notes. I'm John, joined by Maya.",
    },
    {
        "speaker": "host_2",
        "text": "Thanks John. The company will host an event next week about AI breakthroughs.",
    },
    {
        "speaker": "host_1",
        "text": "That is why this matters - these advances are changing how we work.",
    },
    {
        "speaker": "host_2",
        "text": "Absolutely. It's an important development for the industry.",
    },
]


def test_dialogue_render_jobs_use_clean_turn_text_and_expected_voices() -> None:
    turns = validate_script_turns(DIALOGUE_TURNS, "dialogue")

    jobs = _build_dialogue_render_jobs_from_turns(
        turns,
        host_1_id="john_voice_id",
        host_2_id="maya_voice_id",
    )

    assert len(jobs) == len(turns)
    assert [job.voice_id for job in jobs] == [
        "john_voice_id",
        "maya_voice_id",
        "john_voice_id",
        "maya_voice_id",
    ]
    assert [job.role_label for job in jobs] == ["john", "maya", "john", "maya"]


def test_dialogue_fake_mp3_segments_can_be_combined() -> None:
    _get_ffmpeg_status(configure_pydub=True)
    if not _check_ffmpeg_available():
        pytest.skip("ffmpeg/ffprobe not available to pydub")

    turns = validate_script_turns(DIALOGUE_TURNS, "dialogue")
    jobs = _build_dialogue_render_jobs_from_turns(
        turns,
        host_1_id="john_voice_id",
        host_2_id="maya_voice_id",
    )

    fake_parts: list[bytes] = []
    for job in jobs:
        duration_ms = 300 if job.role_label == "john" else 500
        segment = AudioSegment.silent(duration=duration_ms)
        buffer = BytesIO()
        segment.export(buffer, format="mp3")
        fake_parts.append(buffer.getvalue())

    combined = _combine_mp3_segments(fake_parts)

    assert len(combined) > 0
