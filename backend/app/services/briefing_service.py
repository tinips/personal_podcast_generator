"""Build a source-grounded PodcastBriefing from filtered articles.

The briefing LLM extracts factual material only. It must not write podcast dialogue,
polished prose, or speaker labels. It prepares the ground for the conversation planner
and final script writer.

Briefer = facts / evidence / risks.
Planner = narrative structure / connections / transitions.
Writer = final spoken turns.
"""

import os
from dataclasses import dataclass
from pydantic import ValidationError
from .script_service import (
    ScriptGenerationError,
    parse_json_response,
    _group_articles_by_topic,
    OPENAI_MODEL,
    OpenAIUsage,
    openai_usage_from_response,
)
from .pipeline_models import PodcastBriefing
from openai import AsyncOpenAI


BRIEFING_PROMPT_VERSION = "signalcast-briefing-v2"


@dataclass
class PodcastBriefingResult:
    briefing: PodcastBriefing
    openai_usage: OpenAIUsage


async def build_podcast_briefing(
    articles: list[dict],
    interests: list[str],
) -> PodcastBriefingResult:
    """Build a structured PodcastBriefing from filtered articles.

    Returns a validated object with keys:
        episode_theme, listener_interests, topic_briefings, do_not_claim
    """
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise ScriptGenerationError(
            "OPENAI_API_KEY is required for podcast briefing."
        )

    grouped = _group_articles_by_topic(articles)
    articles_text_parts: list[str] = []
    for topic, topic_articles in grouped.items():
        articles_text_parts.append(f"\n--- Topic: {topic} ---")
        for a in topic_articles:
            try:
                content = str(a["content"]).strip()
            except KeyError as exc:
                raise ScriptGenerationError(
                    "Selected article is missing required content for briefing."
                ) from exc
            if not content:
                raise ScriptGenerationError(
                    "Selected article has empty content and cannot be briefed."
                )
            articles_text_parts.append(
                f"Title: {a.get('title', '')}\n"
                f"Source: {a.get('source', '')}\n"
                f"Published: {a.get('published_at', '')}\n"
                "Article excerpt:\n"
                f"{content}\n"
            )

    briefing_prompt = (
        "You are a news analyst preparing a structured briefing for a podcast team.\n\n"
        f"The listener is interested in: {', '.join(interests)}.\n\n"
        "Extract and organize facts from the articles below. "
        "Do NOT write the podcast script. Do NOT write dialogue. Do NOT write "
        "speaker labels (JOHN:, MAYA:). Do NOT write polished podcast prose.\n\n"
        "Return a JSON object with exactly these keys:\n\n"
        "{\n"
        '  "episode_theme": "One sentence capturing the main thread across stories.",\n'
        '  "topic_briefings": [\n'
        "    {\n"
        '      "topic": "Topic name.",\n'
        '      "summary": "2-3 sentence factual summary.",\n'
        '      "why_it_matters": "Why this topic matters to the listener.",\n'
        '      "freshness": "How recent or timely this is.",\n'
        '      "key_facts": [\n'
        "        {\n"
        '          "fact": "One specific, source-backed fact.",\n'
        '          "source_title": "Article title.",\n'
        '          "source": "Publisher name.",\n'
        '          "url": "Article URL."\n'
        "        }\n"
        "      ],\n"
        '      "tension_or_question": "An open question or tension this topic raises."\n'
        "    }\n"
        "  ],\n"
        '  "do_not_claim": ["Specific unsupported claim to avoid."]\n'
        "}\n\n"
        "Rules:\n"
        "- Use ONLY facts from the articles. Do not invent.\n"
        "- Output ONLY valid JSON. No markdown fences, no commentary.\n\n"
        "Articles:\n"
        + "\n".join(articles_text_parts)
    )

    client = AsyncOpenAI(api_key=api_key, timeout=30.0, max_retries=0)
    try:
        response = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a professional news analyst. Output ONLY valid JSON "
                        "with the exact structure requested. No markdown fences."
                    ),
                },
                {"role": "user", "content": briefing_prompt},
            ],
            max_tokens=2000,
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content or ""
        usage = openai_usage_from_response(
            response,
            stage="openai_briefing",
            purpose="Briefing LLM",
            fallback_input_text=briefing_prompt,
            fallback_output_text=raw,
        )
        result = parse_json_response(raw, "Podcast briefing")
        if "episode_theme" not in result:
            raise ScriptGenerationError(
                "Podcast briefing is missing required fields."
            )
        result["listener_interests"] = interests
        try:
            return PodcastBriefingResult(
                briefing=PodcastBriefing.model_validate(result),
                openai_usage=usage,
            )
        except ValidationError as exc:
            raise ScriptGenerationError(
                f"Podcast briefing returned invalid schema: {exc}"
            ) from exc
    except ScriptGenerationError:
        raise
    except Exception as exc:
        raise ScriptGenerationError(f"Podcast briefing failed: {exc}") from exc
