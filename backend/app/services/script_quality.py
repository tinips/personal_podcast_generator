"""Deterministic parser and TTS safety checks for generated podcast scripts.

This module is the final safety boundary before TTS. It validates parser-facing
script contracts, but it does not use an LLM to creatively rewrite scripts and
does not remove hardcoded style phrases from generated prose. Naturalness belongs
to the planner and writer services.
"""

import re

from .script_service import (
    _dialogue_quality_issues,
    _solo_has_forbidden_labels,
    clean_spoken_text,
    ScriptGenerationError,
)
from .script_turns import (
    ScriptTurn,
    ScriptTurnValidationError,
    validate_script_turns,
)


async def run_quality_checks_and_revise(
    script: str | list[ScriptTurn],
    speaker_mode: str,
) -> str | list[ScriptTurn]:
    """Clean and validate scripts or structured turns without extra LLM calls."""
    if not isinstance(script, str):
        return _check_turns(script, speaker_mode)
    if speaker_mode == "dialogue":
        return _check_dialogue(script)
    return _check_solo(script)


def _check_turns(
    turns: list[ScriptTurn],
    speaker_mode: str,
) -> list[ScriptTurn]:
    try:
        return validate_script_turns(turns, speaker_mode)
    except ScriptTurnValidationError as exc:
        raise ScriptGenerationError(
            "Script turn quality check failed: " + str(exc)
        ) from exc


def _check_dialogue(script: str) -> str:
    raw_issues = _script_surface_safety_issues(script)
    cleaned = clean_spoken_text(script)
    issues = _dedupe_issues([*raw_issues, *_dialogue_quality_issues(cleaned)])
    if issues:
        raise ScriptGenerationError(
            "Script quality check failed: " + "; ".join(issues)
        )
    return cleaned


def _check_solo(script: str) -> str:
    raw_issues = _script_surface_safety_issues(script)
    cleaned = clean_spoken_text(script)
    if _solo_has_forbidden_labels(cleaned):
        raw_issues.append("Solo script must not include speaker labels.")
    if not cleaned:
        raise ScriptGenerationError("Script quality check failed: empty script.")
    issues = _dedupe_issues([*raw_issues, *_solo_quality_issues(cleaned)])
    if issues:
        raise ScriptGenerationError(
            "Script quality check failed: " + "; ".join(issues)
        )
    return cleaned


def _script_surface_safety_issues(script: str) -> list[str]:
    issues: list[str] = []
    if re.search(r"https?://\S+", script):
        issues.append("Remove raw URLs from the script.")
    if re.search(r"```", script):
        issues.append("Remove markdown code fences from the script.")
    return issues


def _dedupe_issues(issues: list[str]) -> list[str]:
    return list(dict.fromkeys(issues))


def _solo_quality_issues(script: str) -> list[str]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", script) if p.strip()]
    if not paragraphs:
        return ["Solo script must include spoken paragraphs."]
    return []
