"""Tests for typed intermediate LLM pipeline artifacts."""

from __future__ import annotations

from app.services.pipeline_models import (
    ConversationBeat,
    ConversationPlan,
    PodcastBriefing,
)
from app.services.script_writer_service import (
    _format_briefing_for_writer,
    _format_plan_for_writer,
)


def _briefing_payload() -> dict:
    return {
        "episode_theme": "AI infrastructure is moving from experiments to operations.",
        "listener_interests": ["AI", "data"],
        "topic_briefings": [
            {
                "topic": "AI",
                "summary": "A new model release highlights faster inference.",
                "why_it_matters": "It affects how teams budget production AI systems.",
                "freshness": "Published this week.",
                "key_facts": [
                    {
                        "fact": "The company said latency improved for common workloads.",
                        "source_title": "AI Systems Get Faster",
                        "source": "Tech Daily",
                        "url": "https://example.com/ai-systems",
                    }
                ],
                "tension_or_question": "Can teams trust the gains outside benchmarks?",
            }
        ],
        "do_not_claim": ["Do not claim the model is universally cheaper."],
    }


def _plan_payload() -> dict:
    return {
        "episode_theme": "Operational AI is becoming a cost and reliability story.",
        "connection_strategy": "single_theme",
        "connection_confidence": "medium",
        "connection_rationale": "Both stories concern production deployment tradeoffs.",
        "opening_intent": "Introduce Neural Notes and frame the operations angle.",
        "maya_first_response_intent": "Briefly explain why inference performance matters.",
        "beats": [
            {
                "purpose": "Ground the episode in the concrete model update.",
                "john_role": "Set up the news and ask what changed.",
                "maya_role": "Explain the latency and cost implications.",
                "source_basis": ["Tech Daily - AI Systems Get Faster"],
                "continuity_note": "This beat follows the opening by adding evidence.",
            },
            "Compare the update with wider data platform pressure.",
        ],
        "transition_notes": ["Move from the model update to operational planning."],
        "closing_intent": "Close with a practical takeaway for teams.",
        "pacing_notes": "Keep the benchmark explanation short.",
    }


def test_podcast_briefing_validates_realistic_payload() -> None:
    briefing = PodcastBriefing.model_validate(_briefing_payload())

    assert briefing.listener_interests == ["AI", "data"]
    assert briefing.topic_briefings[0].topic == "AI"
    assert briefing.topic_briefings[0].key_facts[0].source == "Tech Daily"
    assert briefing.do_not_claim == [
        "Do not claim the model is universally cheaper."
    ]


def test_conversation_plan_validates_dialogue_payload() -> None:
    plan = ConversationPlan.model_validate(_plan_payload())

    assert plan.connection_strategy == "single_theme"
    assert isinstance(plan.beats[0], ConversationBeat)
    assert plan.beats[0].source_basis == ["Tech Daily - AI Systems Get Faster"]
    assert plan.beats[1] == "Compare the update with wider data platform pressure."


def test_writer_formatters_accept_typed_pipeline_models() -> None:
    briefing = PodcastBriefing.model_validate(_briefing_payload())
    plan = ConversationPlan.model_validate(_plan_payload())

    briefing_text = _format_briefing_for_writer(briefing)
    plan_text = _format_plan_for_writer(plan, "dialogue")

    assert "Fact: The company said latency improved" in briefing_text
    assert "Avoid unsupported claims" in briefing_text
    assert "Opening intent: Introduce Neural Notes" in plan_text
    assert "Maya first response intent:" in plan_text
    assert "Source basis: ['Tech Daily - AI Systems Get Faster']" in plan_text
    assert "Transitions: ['Move from the model update to operational planning.']" in plan_text
    assert "Transition policy:" not in plan_text
