"""Write structured Neural Notes speaker turns from a briefing and plan.

The writer converts structured material into natural spoken audio turns. The
backend derives the readable script and TTS jobs from those validated turns.
"""

import os
from .script_service import (
    ScriptGenerationError,
    OPENAI_MODEL,
    openai_usage_from_response,
    parse_json_response,
)
from .script_turns import (
    ScriptTurnValidationError,
    ScriptWriterResult,
    validate_script_turns,
)
from .pipeline_models import ConversationBeat, ConversationPlan, PodcastBriefing
from openai import AsyncOpenAI


WRITER_PROMPT_VERSION = "signalcast-writer-v6"


async def write_signalcast_script(
    briefing: PodcastBriefing,
    plan: ConversationPlan,
    speaker_mode: str,
    tone: str = "neutral",
    duration_label: str = "normal",
    duration_minutes: int = 2,
) -> ScriptWriterResult:
    """Write validated structured speaker turns from briefing and plan."""
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise ScriptGenerationError(
            "OPENAI_API_KEY is required for script writing."
        )

    word_ranges = {
        "short": (140, 180),
        "normal": (300, 380),
        "long": (540, 650),
    }
    default_words = max(1, min(duration_minutes, 10)) * 135
    target_min, target_max = word_ranges.get(
        duration_label, (default_words, default_words + 70)
    )

    format_rules = _build_format_rules(briefing, speaker_mode)
    style_notes = _build_style_notes(tone)

    writer_prompt = (
        f"Write a {duration_minutes}-minute episode of Neural Notes.\n"
        f"Mode: {speaker_mode}. Tone: {tone}.\n"
        f"Target: ~{target_min}-{target_max} spoken words.\n\n"
        f"{format_rules}\n\n"
        f"{style_notes}\n\n"
        "--- BRIEFING (use only these facts) ---\n\n"
        + _format_briefing_for_writer(briefing)
        + "\n\n--- PLAN (follow this structure) ---\n\n"
        + _format_plan_for_writer(plan, speaker_mode)
        + "\n\nOutput only valid JSON. The JSON object must contain only `turns`."
    )

    client = AsyncOpenAI(api_key=api_key, timeout=30.0, max_retries=0)
    try:
        response = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a professional podcast scriptwriter. "
                        "Output only valid JSON with exactly the requested schema. "
                        "Do not include markdown, preamble, or extra fields."
                    ),
                },
                {"role": "user", "content": writer_prompt},
            ],
            max_tokens=2500,
            temperature=0.7,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content or ""
        usage = openai_usage_from_response(
            response,
            stage="openai_script_writer",
            purpose="Script Writer LLM",
            fallback_input_text=writer_prompt,
            fallback_output_text=raw,
        )
        payload = parse_json_response(raw, "Script writer")
        if set(payload.keys()) != {"turns"}:
            raise ScriptGenerationError(
                "Script writer response must contain only the top-level `turns` field."
            )
        try:
            turns = validate_script_turns(payload.get("turns"), speaker_mode)
        except ScriptTurnValidationError as exc:
            raise ScriptGenerationError(
                f"Script writer returned invalid turns: {exc}"
            ) from exc
        return ScriptWriterResult(turns=turns, openai_usage=usage)
    except ScriptGenerationError:
        raise
    except Exception as exc:
        raise ScriptGenerationError(f"Script writing failed: {exc}") from exc


def _build_format_rules(briefing: PodcastBriefing, speaker_mode: str) -> str:
    do_not_claim = briefing.do_not_claim
    caution_text = ""
    if do_not_claim:
        caution_text = "\n".join(f"- Avoid unsupported claim: {c}" for c in do_not_claim)

    if speaker_mode == "solo":
        rules = (
            "Return this JSON shape: "
            '{"turns":[{"speaker":"host_1","text":"Clean spoken text."}]}.\n'
            "Rules:\n"
            "- Every turn uses speaker host_1.\n"
            "- Write natural spoken audio for John as the solo host.\n"
            "- Use the briefing facts and the provided plan.\n"
            "- Avoid speaker labels inside text, markdown, raw links, unsupported claims, and preamble.\n"
            "- Include the planned intro, body beats, transitions, and closing signoff.\n"
        )
    else:
        rules = (
            "Return this JSON shape: "
            '{"turns":[{"speaker":"host_1","text":"Clean spoken text for John."},{"speaker":"host_2","text":"Clean spoken text for Maya."}]}.\n'
            "Rules:\n"
            "- Use host_1 for John and host_2 for Maya.\n"
            "- Include both speakers. John opens, guides transitions, and closes.\n"
            "- Maya provides most analysis from the briefing.\n"
            "- Use the briefing facts and the provided plan.\n"
            "- Avoid speaker labels inside text, markdown, raw links, unsupported claims, and preamble.\n"
            "- Keep turns natural for spoken audio; avoid rigid Q&A or long monologues.\n"
        )
    if caution_text:
        rules += "\n" + caution_text + "\n"
    return rules


def _build_style_notes(tone: str) -> str:
    return (
        "Style: natural spoken audio with clear pacing. "
        "Move quickly into substance, avoid generic filler, and keep synthesis proportional to the evidence. "
        "If stories are loosely related, frame them as a mixed briefing rather than forcing one theme. "
        f"Use a {tone} tone without changing the facts."
    )


def _format_briefing_for_writer(briefing: PodcastBriefing) -> str:
    parts = []
    for tb in briefing.topic_briefings:
        tension_text = tb.tension_or_question
        parts.append(
            f"\nTopic: {tb.topic}\n"
            f"Summary: {tb.summary}\n"
            f"Why it matters: {tb.why_it_matters}\n"
            f"Tension: {tension_text}"
        )
        for fact in tb.key_facts:
            parts.append(
                f"  Fact: {fact.fact} "
                f"[source: {fact.source} - {fact.source_title}]"
            )
    if briefing.do_not_claim:
        parts.append(f"\nAvoid unsupported claims: {briefing.do_not_claim}")
    return "\n".join(parts)


def _format_plan_for_writer(plan: ConversationPlan, speaker_mode: str) -> str:
    parts = [f"Episode theme: {plan.episode_theme}"]
    connection_strategy = _connection_strategy(plan.connection_strategy)
    connection_confidence = plan.connection_confidence or "unspecified"
    connection_rationale = plan.connection_rationale or "Not provided."
    parts.append(f"Connection strategy: {connection_strategy}")
    parts.append(f"Connection confidence: {connection_confidence}")
    parts.append(f"Connection rationale: {connection_rationale}")
    if connection_strategy == "mixed_briefing":
        parts.append(
            "Writer instruction: Frame this as a mixed briefing or segmented update. "
            "Keep separate stories distinct and transition honestly."
        )
    else:
        parts.append(
            "Writer instruction: Build a connected narrative around the supported shared thread."
        )
    parts.append(f"Opening intent: {plan.opening_intent}")
    if speaker_mode == "dialogue":
        parts.append(f"Maya first response intent: {plan.maya_first_response_intent}")
    beats = plan.beats
    if beats:
        parts.append("Beats (in order, each builds on the previous):")
        for i, b in enumerate(beats, 1):
            if isinstance(b, ConversationBeat):
                parts.append(
                    f"  {i}. Purpose: {b.purpose}\n"
                    f"     John: {b.john_role}\n"
                    f"     Maya: {b.maya_role}\n"
                    f"     Source basis: {b.source_basis}\n"
                    f"     Continuity: {b.continuity_note}"
                )
            else:
                parts.append(f"  {i}. {b}")
    if plan.transition_notes:
        parts.append(f"Transitions: {plan.transition_notes}")
    parts.append(f"Closing intent: {plan.closing_intent}")
    if plan.pacing_notes:
        parts.append(f"Pacing: {plan.pacing_notes}")
    return "\n".join(parts)


def _connection_strategy(raw_strategy: object) -> str:
    if isinstance(raw_strategy, str):
        strategy = raw_strategy.strip().lower()
        if strategy == "single_theme":
            return "single_theme"
    return "mixed_briefing"
