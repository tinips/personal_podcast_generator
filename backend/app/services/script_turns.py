"""Structured podcast script turns and deterministic rendering."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal


SpeakerId = Literal["host_1", "host_2"]
VALID_SPEAKERS = {"host_1", "host_2"}
SPEAKER_LABELS = {"host_1": "JOHN", "host_2": "MAYA"}

TEXT_REPLACEMENTS = {
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u2013": "-",
    "\u2014": "-",
    "\ufffd": "",
    "\u00e2\u20ac\u02dc": "'",
    "\u00e2\u20ac\u2122": "'",
    "\u00e2\u20ac\u0153": '"',
    "\u00e2\u20ac\u009d": '"',
    "\u00e2\u20ac\u201c": "-",
    "\u00e2\u20ac\u201d": "-",
    "\u00ef\u00bf\u00bd": "",
    "\u00c3\u00a2\u00e2\u201a\u00ac\u00e2\u201e\u00a2": "'",
}

SPEAKER_LABEL_RE = re.compile(
    r"(?:^|[\n\r]|\b)"
    r"(JOHN|MAYA|HOST\s*1|HOST\s*2|HOST|SPEAKER\s*1|SPEAKER\s*2)"
    r"\s*:",
    re.IGNORECASE,
)
RAW_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
MARKDOWN_RE = re.compile(
    r"```|`|\*\*|__|(?:^|\n)\s*(#{1,6}\s+|[-*]\s+)",
    re.IGNORECASE,
)


class ScriptTurnValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ScriptTurn:
    speaker: SpeakerId
    text: str


@dataclass(frozen=True)
class ScriptWriterResult:
    turns: list[ScriptTurn]
    openai_usage: object | None = None


def clean_turn_text(text: str) -> str:
    cleaned = text
    for bad, good in TEXT_REPLACEMENTS.items():
        cleaned = cleaned.replace(bad, good)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\s*\n\s*", " ", cleaned)
    return cleaned.strip()


def validate_script_turns(
    raw_turns: object,
    speaker_mode: str,
) -> list[ScriptTurn]:
    """Validate and normalize structured script turns.

    Consecutive dialogue turns from the same speaker are merged deterministically
    so backend cleanup does not rely on LLM formatting discipline.
    """
    if speaker_mode not in {"solo", "dialogue"}:
        raise ScriptTurnValidationError(f"Unsupported speaker_mode: {speaker_mode}.")
    if not isinstance(raw_turns, list) or not raw_turns:
        raise ScriptTurnValidationError("turns must be a non-empty list.")

    errors: list[str] = []
    normalized: list[ScriptTurn] = []

    for index, raw_turn in enumerate(raw_turns):
        speaker: object
        text: object
        if isinstance(raw_turn, ScriptTurn):
            speaker = raw_turn.speaker
            text = raw_turn.text
        elif isinstance(raw_turn, dict):
            if set(raw_turn.keys()) != {"speaker", "text"}:
                errors.append(f"turn {index} must contain only speaker and text.")
                continue
            speaker = raw_turn.get("speaker")
            text = raw_turn.get("text")
        else:
            errors.append(f"turn {index} must be an object.")
            continue

        if speaker not in VALID_SPEAKERS:
            errors.append(f"turn {index} speaker must be host_1 or host_2.")
            continue
        if speaker_mode == "solo" and speaker != "host_1":
            errors.append("solo mode only allows host_1 turns.")
            continue
        if not isinstance(text, str):
            errors.append(f"turn {index} text must be a string.")
            continue

        cleaned = clean_turn_text(text)
        if not cleaned:
            errors.append(f"turn {index} text must be non-empty.")
            continue

        issues = _turn_text_safety_issues(cleaned)
        if issues:
            errors.append(f"turn {index}: " + "; ".join(issues))
            continue

        normalized.append(ScriptTurn(speaker=speaker, text=cleaned))

    if errors:
        raise ScriptTurnValidationError(" ".join(errors))
    if not normalized:
        raise ScriptTurnValidationError("turns must contain spoken text.")

    merged = (
        _merge_consecutive_turns(normalized)
        if speaker_mode == "dialogue"
        else normalized
    )

    if speaker_mode == "dialogue":
        speakers = {turn.speaker for turn in merged}
        if "host_1" not in speakers or "host_2" not in speakers:
            raise ScriptTurnValidationError(
                "dialogue mode requires at least one host_1 turn and one host_2 turn."
            )

    return merged


def render_script_from_turns(
    turns: list[ScriptTurn],
    speaker_mode: str,
) -> str:
    """Render the public readable script from validated turns."""
    validated = validate_script_turns(turns, speaker_mode)
    if speaker_mode == "solo":
        return "\n\n".join(turn.text for turn in validated).strip()

    parts = [
        f"{SPEAKER_LABELS[turn.speaker]}:\n{turn.text}"
        for turn in validated
    ]
    return "\n\n".join(parts).strip()


def _merge_consecutive_turns(turns: list[ScriptTurn]) -> list[ScriptTurn]:
    merged: list[ScriptTurn] = []
    for turn in turns:
        if merged and merged[-1].speaker == turn.speaker:
            previous = merged[-1]
            merged[-1] = ScriptTurn(
                speaker=previous.speaker,
                text=f"{previous.text} {turn.text}".strip(),
            )
        else:
            merged.append(turn)
    return merged


def _turn_text_safety_issues(text: str) -> list[str]:
    issues: list[str] = []
    if SPEAKER_LABEL_RE.search(text):
        issues.append("speaker labels are not allowed inside turn text")
    if RAW_URL_RE.search(text):
        issues.append("raw URLs are not allowed inside turn text")
    if MARKDOWN_RE.search(text):
        issues.append("markdown or code fences are not allowed inside turn text")
    return issues
