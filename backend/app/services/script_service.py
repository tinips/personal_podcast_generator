import logging
import re
from dataclasses import dataclass
from time import perf_counter

from .cost_estimates import estimate_openai_cost
from .script_turns import ScriptTurn, render_script_from_turns

logger = logging.getLogger(__name__)

OPENAI_MODEL = "gpt-4o-mini"
SCRIPT_PROMPT_VERSION = "signalcast-pipeline-v5"
SOLO_FORBIDDEN_LABEL_RE = re.compile(
    r"^(JOHN|MAYA|HOST\s*1|HOST\s*2|HOST|SPEAKER\s*1|SPEAKER\s*2)\s*:",
    re.IGNORECASE | re.MULTILINE,
)
DIALOGUE_LABEL_RE = re.compile(r"^\s*(JOHN|MAYA):\s*$", re.IGNORECASE)
JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)

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


class ScriptGenerationError(RuntimeError):
    pass


@dataclass
class ScriptPipelineResult:
    script: str
    turns: list[ScriptTurn]
    timings_ms: dict[str, int]
    openai_usage: list["OpenAIUsage"]


@dataclass
class OpenAIUsage:
    stage: str
    purpose: str
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float


def estimate_tokens_from_text(text: str) -> int:
    return max(1, round(len(text) / 4))


def openai_usage_from_response(
    response,
    *,
    stage: str,
    purpose: str,
    fallback_input_text: str,
    fallback_output_text: str,
) -> OpenAIUsage:
    usage = getattr(response, "usage", None)
    input_tokens = getattr(usage, "prompt_tokens", None)
    output_tokens = getattr(usage, "completion_tokens", None)

    if input_tokens is None:
        input_tokens = estimate_tokens_from_text(fallback_input_text)
    if output_tokens is None:
        output_tokens = estimate_tokens_from_text(fallback_output_text)

    return OpenAIUsage(
        stage=stage,
        purpose=purpose,
        input_tokens=int(input_tokens),
        output_tokens=int(output_tokens),
        estimated_cost_usd=estimate_openai_cost(int(input_tokens), int(output_tokens)),
    )


def _elapsed_ms(start: float) -> int:
    return int((perf_counter() - start) * 1000)


def parse_json_response(raw: str, label: str = "JSON") -> dict:
    """Parse an LLM JSON response without spoken-text cleanup."""
    text = raw.strip()
    text = JSON_FENCE_RE.sub("", text).strip()
    import json

    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        preview = text[:200].replace("\n", " ")
        raise ScriptGenerationError(
            f"{label} returned invalid JSON. Raw preview: {preview}"
        )
    if not isinstance(result, dict):
        raise ScriptGenerationError(
            f"{label} is not a JSON object. Raw preview: {text[:200]}"
        )
    return result


def normalize_text(text: str) -> str:
    cleaned = text
    for bad, good in TEXT_REPLACEMENTS.items():
        cleaned = cleaned.replace(bad, good)
    return cleaned


def clean_spoken_text(text: str) -> str:
    cleaned = normalize_text(text)
    cleaned = re.sub(r"https?://\S+", "", cleaned)
    cleaned = re.sub(r"```(?:text)?", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.replace("`", "")
    cleaned = cleaned.replace("**", "").replace("__", "")
    cleaned = re.sub(r"^[\s>*#-]+", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _parse_dialogue_turns(script: str) -> list[tuple[str, str]]:
    turns: list[tuple[str, str]] = []
    speaker: str | None = None
    buffer: list[str] = []

    for raw_line in script.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        label = DIALOGUE_LABEL_RE.fullmatch(line)
        if label:
            if speaker is not None:
                turns.append((speaker, " ".join(buffer).strip()))
            speaker = label.group(1).upper()
            buffer = []
        elif speaker is not None:
            buffer.append(line)

    if speaker is not None:
        turns.append((speaker, " ".join(buffer).strip()))

    return turns


def _dialogue_quality_issues(script: str) -> list[str]:
    turns = _parse_dialogue_turns(script)
    issues: list[str] = []
    if not turns:
        return ["Use JOHN: and MAYA: labels, uppercase and on their own lines."]

    speakers = {speaker for speaker, _body in turns}
    if "JOHN" not in speakers or "MAYA" not in speakers:
        issues.append("Dialogue must include both JOHN and MAYA segments.")
    if any(not body.strip() for _speaker, body in turns):
        issues.append("Dialogue labels must not have empty speaker text.")
    if re.search(r"https?://\S+", script):
        issues.append("Remove raw URLs from the script.")
    if re.search(r"(^|\n)\s*(```|#|\* |- )", script):
        issues.append("Remove markdown, headings, bullets, and code fences.")

    return issues


def _group_articles_by_topic(articles: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for article in articles:
        topic = article.get("topic", "General")
        groups.setdefault(topic, []).append(article)
    return groups


def _solo_has_forbidden_labels(script: str) -> bool:
    return bool(SOLO_FORBIDDEN_LABEL_RE.search(script))


async def generate_script(
    articles: list[dict],
    interests: list[str],
    tone: str = "neutral",
    duration_label: str = "normal",
    duration_minutes: int = 2,
    speaker_mode: str = "solo",
) -> str:
    """Generate a podcast script through briefing -> plan -> writer -> quality."""
    result = await generate_script_with_timings(
        articles=articles,
        interests=interests,
        tone=tone,
        duration_label=duration_label,
        duration_minutes=duration_minutes,
        speaker_mode=speaker_mode,
    )
    return result.script


async def generate_script_with_timings(
    articles: list[dict],
    interests: list[str],
    tone: str = "neutral",
    duration_label: str = "normal",
    duration_minutes: int = 2,
    speaker_mode: str = "solo",
) -> ScriptPipelineResult:
    """Generate a script and return stage timings for dashboard monitoring."""
    from . import (
        briefing_service,
        conversation_plan_service,
        script_quality,
        script_writer_service,
    )

    timings: dict[str, int] = {}

    briefing_start = perf_counter()
    briefing_result = await briefing_service.build_podcast_briefing(
        articles,
        interests,
    )
    briefing = briefing_result.briefing
    timings["briefing_llm_ms"] = _elapsed_ms(briefing_start)

    planning_start = perf_counter()
    plan_result = await conversation_plan_service.build_conversation_plan(
        briefing,
        speaker_mode,
        tone,
        duration_label,
    )
    plan = plan_result.plan
    timings["conversation_planning_llm_ms"] = _elapsed_ms(planning_start)

    writing_start = perf_counter()
    writer_result = await script_writer_service.write_signalcast_script(
        briefing,
        plan,
        speaker_mode,
        tone,
        duration_label,
        duration_minutes,
    )
    timings["script_writer_llm_ms"] = _elapsed_ms(writing_start)

    quality_start = perf_counter()
    checked_turns = await script_quality.run_quality_checks_and_revise(
        writer_result.turns,
        speaker_mode,
    )
    timings["quality_check_ms"] = _elapsed_ms(quality_start)
    script = render_script_from_turns(checked_turns, speaker_mode)
    openai_usage = [
        briefing_result.openai_usage,
        plan_result.openai_usage,
    ]
    if writer_result.openai_usage is not None:
        openai_usage.append(writer_result.openai_usage)
    return ScriptPipelineResult(
        script=script,
        turns=checked_turns,
        timings_ms=timings,
        openai_usage=openai_usage,
    )


def _generate_title(articles: list[dict]) -> str:
    topics = [article["title"].split(":")[0].strip() for article in articles[:3]]
    title = " | ".join(topics) if topics else "Personalized Podcast"
    return normalize_text(title)


def _generate_summary(articles: list[dict]) -> str:
    descriptions = [
        article["description"] for article in articles[:3]
        if article.get("description")
    ]
    summary = (
        " ".join(descriptions)[:200]
        if descriptions
        else "Your daily podcast briefing."
    )
    return normalize_text(summary)
