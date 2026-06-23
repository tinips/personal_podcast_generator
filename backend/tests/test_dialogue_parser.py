"""Tests for structured turn validation, rendering, and TTS text preparation."""

from __future__ import annotations

import pytest

from app.services.script_turns import (
    ScriptTurnValidationError,
    render_script_from_turns,
    validate_script_turns,
)
from app.services.tts_service import (
    _add_solo_tts_pauses,
    _resolve_dialogue_voices,
)


DIALOGUE_TURNS = [
    {
        "speaker": "host_1",
        "text": "Welcome back to Neural Notes. I'm John, joined by Maya.",
    },
    {
        "speaker": "host_2",
        "text": "Thanks John. The AI landscape has seen remarkable growth recently.",
    },
    {
        "speaker": "host_1",
        "text": "First, let's talk about AI reasoning breakthroughs.",
    },
    {
        "speaker": "host_2",
        "text": "According to Tech Daily, this model matches human performance.",
    },
]


def test_dialogue_turns_render_to_readable_script() -> None:
    validated = validate_script_turns(DIALOGUE_TURNS, "dialogue")
    rendered = render_script_from_turns(validated, "dialogue")

    assert rendered.startswith("JOHN:\n")
    assert "\n\nMAYA:\n" in rendered
    assert "host_1" not in rendered
    assert "host_2" not in rendered


def test_dialogue_validation_requires_both_hosts() -> None:
    with pytest.raises(ScriptTurnValidationError):
        validate_script_turns(
            [{"speaker": "host_1", "text": "Welcome back."}],
            "dialogue",
        )


def test_solo_validation_rejects_host_2() -> None:
    with pytest.raises(ScriptTurnValidationError):
        validate_script_turns(
            [{"speaker": "host_2", "text": "Maya should not appear as solo speaker."}],
            "solo",
        )


def test_solo_script_renders_without_speaker_labels() -> None:
    solo_script = render_script_from_turns(
        [
            {"speaker": "host_1", "text": "Welcome back to Neural Notes."},
            {"speaker": "host_1", "text": "Today we are covering AI infrastructure."},
        ],
        "solo",
    )

    assert "JOHN:" not in solo_script
    assert "MAYA:" not in solo_script
    assert "Welcome back to Neural Notes." in solo_script


def test_solo_tts_pacing_adds_light_pause_hints() -> None:
    solo_tts_text = _add_solo_tts_pauses(
        "Welcome back to Neural Notes. I'm John, your host. "
        "Today we are covering AI infrastructure; here is the signal."
    )

    assert " ... " in solo_tts_text
    assert "JOHN:" not in solo_tts_text
    assert "MAYA:" not in solo_tts_text


def test_dialogue_voice_resolution_uses_distinct_configured_voices(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ELEVENLABS_VOICE_JOHN_CREATIVE", "john_id_123")
    monkeypatch.setenv("ELEVENLABS_VOICE_MAYA_EDUCATIONAL", "maya_id_456")

    john_id, maya_id, _john_config, _maya_config = _resolve_dialogue_voices()

    assert john_id == "john_id_123"
    assert maya_id == "maya_id_456"
    assert john_id != maya_id
