"""Tests for pydub/ffmpeg assembly independently of ElevenLabs."""

from __future__ import annotations

import pytest

from app.services.tts_service import _check_ffmpeg_available, _get_ffmpeg_status

pydub = pytest.importorskip("pydub")
AudioSegment = pydub.AudioSegment


def test_pydub_can_export_combined_mp3(tmp_path) -> None:
    _get_ffmpeg_status(configure_pydub=True)
    if not _check_ffmpeg_available():
        pytest.skip("ffmpeg/ffprobe not available to pydub")

    john = AudioSegment.silent(duration=300)
    maya = AudioSegment.silent(duration=500)

    combined = AudioSegment.empty()
    combined += john.fade_in(10).fade_out(10)
    combined += AudioSegment.silent(duration=200)
    combined += maya.fade_in(15).fade_out(15)

    out_path = tmp_path / "audio_smoke_test.mp3"
    combined.export(str(out_path), format="mp3")

    assert out_path.stat().st_size > 0
    assert len(combined) == 1000
