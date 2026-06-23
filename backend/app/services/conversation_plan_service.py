"""Build a ConversationPlan or SoloPlan from a PodcastBriefing.

The planner decides the structure, continuity, and flow of the episode. It does
not write final script lines.
"""

import os
from dataclasses import dataclass

from openai import AsyncOpenAI
from pydantic import ValidationError

from .script_service import (
    OPENAI_MODEL,
    OpenAIUsage,
    ScriptGenerationError,
    openai_usage_from_response,
    parse_json_response,
)
from .pipeline_models import ConversationPlan, PodcastBriefing


PLAN_PROMPT_VERSION = "signalcast-plan-v6"


@dataclass
class ConversationPlanResult:
    plan: ConversationPlan
    openai_usage: OpenAIUsage


async def build_conversation_plan(
    briefing: PodcastBriefing,
    speaker_mode: str,
    tone: str = "neutral",
    duration_label: str = "normal",
) -> ConversationPlanResult:
    """Build a conversation or solo plan from the briefing."""
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise ScriptGenerationError(
            "OPENAI_API_KEY is required for conversation planning."
        )

    episode_theme = briefing.episode_theme
    topic_briefings = briefing.topic_briefings

    topics_summary = []
    for tb in topic_briefings:
        tension_text = tb.tension_or_question
        topics_summary.append(
            f"Topic: {tb.topic}\n"
            f"Summary: {tb.summary}\n"
            f"Why it matters: {tb.why_it_matters}\n"
            f"Tension: {tension_text}\n"
            f"Freshness: {tb.freshness}\n"
        )

    if speaker_mode == "solo":
        plan_prompt = _solo_plan_prompt(
            episode_theme,
            topics_summary,
            tone,
            duration_label,
        )
    else:
        plan_prompt = _dialogue_plan_prompt(
            episode_theme,
            topics_summary,
            tone,
            duration_label,
        )

    client = AsyncOpenAI(api_key=api_key, timeout=30.0, max_retries=0)
    try:
        response = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a podcast producer planning an episode. "
                        "Output ONLY valid JSON. No markdown fences."
                    ),
                },
                {"role": "user", "content": plan_prompt},
            ],
            max_tokens=1200,
            temperature=0.5,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content or ""
        usage = openai_usage_from_response(
            response,
            stage="openai_planner",
            purpose="Conversation Plan LLM",
            fallback_input_text=plan_prompt,
            fallback_output_text=raw,
        )
        result = parse_json_response(raw, "Conversation plan")
        if "episode_theme" not in result:
            raise ScriptGenerationError(
                "Conversation plan is missing required fields."
            )
        try:
            return ConversationPlanResult(
                plan=ConversationPlan.model_validate(result),
                openai_usage=usage,
            )
        except ValidationError as exc:
            raise ScriptGenerationError(
                f"Conversation plan returned invalid schema: {exc}"
            ) from exc
    except ScriptGenerationError:
        raise
    except Exception as exc:
        raise ScriptGenerationError(f"Conversation planning failed: {exc}") from exc


def _solo_plan_prompt(
    episode_theme: str,
    topics_summary: list[str],
    tone: str,
    duration_label: str,
) -> str:
    theme_context = f"Briefing theme: {episode_theme}\n" if episode_theme else ""

    return (
        "Plan a solo-host Neural Notes episode. John is the narrator.\n\n"
        + theme_context
        + f"Tone: {tone}. Duration: {duration_label}.\n\n"
        "Topic briefings:\n"
        + "\n".join(topics_summary)
        + "\n\n"
        "Return only this JSON shape:\n"
        "{\n"
        '  "episode_theme": "Supported shared theme, or a mixed-briefing frame.",\n'
        '  "connection_strategy": "single_theme or mixed_briefing",\n'
        '  "connection_confidence": "high, medium, or low",\n'
        '  "connection_rationale": "Why the stories are connected, or why they should stay separate.",\n'
        '  "opening_intent": "Hosted Neural Notes intro before article facts.",\n'
        '  "beats": ["Article-backed body beat in order."],\n'
        '  "transition_notes": ["Concrete guidance for moving naturally between beats."],\n'
        '  "closing_intent": "Final takeaway and brief Neural Notes signoff.",\n'
        '  "pacing_notes": "Concise pacing advice."\n'
        "}\n\n"
        "Rules:\n"
        "- Plan structure only; do not write script lines.\n"
        "- Use only briefing facts and do not fabricate deeper connections.\n"
        "- Use single_theme only when there is a specific source-backed shared thread; otherwise use mixed_briefing.\n"
        "- Use connection_rationale for the editorial reasoning behind connecting or separating stories.\n"
        "- Use transition_notes for concrete transition guidance between beats.\n"
        "- Include intro, 3-6 body beats, honest transitions, and outro.\n"
        "- Output only valid JSON."
    )


def _dialogue_plan_prompt(
    episode_theme: str,
    topics_summary: list[str],
    tone: str,
    duration_label: str,
) -> str:
    theme_context = f"Briefing theme: {episode_theme}\n" if episode_theme else ""

    return (
        "Plan a Neural Notes dialogue episode with John as host and Maya as guest analyst.\n\n"
        + theme_context
        + f"Tone: {tone}. Duration: {duration_label}.\n\n"
        "Topic briefings:\n"
        + "\n".join(topics_summary)
        + "\n\n"
        "Return only this JSON shape:\n"
        "{\n"
        '  "episode_theme": "Supported shared theme, or a mixed-briefing frame.",\n'
        '  "connection_strategy": "single_theme or mixed_briefing",\n'
        '  "connection_confidence": "high, medium, or low",\n'
        '  "connection_rationale": "Why the stories are connected, or why they should stay separate.",\n'
        '  "opening_intent": "John opens Neural Notes and introduces Maya naturally.",\n'
        '  "maya_first_response_intent": "Brief response that moves quickly into substance.",\n'
        '  "beats": [\n'
        "    {\n"
        '      "purpose": "What this beat accomplishes.",\n'
        '      "john_role": "How John guides, reacts, or transitions.",\n'
        '      "maya_role": "What Maya analyzes from the briefing.",\n'
        '      "source_basis": ["Briefing fact or source used."],\n'
        '      "continuity_note": "How this beat follows the previous one."\n'
        "    }\n"
        "  ],\n"
        '  "transition_notes": ["Concrete guidance for moving naturally between beats."],\n'
        '  "closing_intent": "Final takeaway and brief John signoff.",\n'
        '  "pacing_notes": "Concise pacing advice."\n'
        "}\n\n"
        "Rules:\n"
        "- Plan structure only; do not write dialogue lines.\n"
        "- Use only briefing facts and do not fabricate deeper connections.\n"
        "- Use single_theme only when there is a specific source-backed shared thread; otherwise use mixed_briefing.\n"
        "- Use connection_rationale for the editorial reasoning behind connecting or separating stories.\n"
        "- Use transition_notes for concrete transition guidance between beats.\n"
        "- Use each beat's continuity_note for how that beat follows from the previous beat.\n"
        "- John guides the episode; Maya provides most analysis.\n"
        "- Include 3-5 progressive beats, honest transitions, and an outro.\n"
        "- Output only valid JSON."
    )
