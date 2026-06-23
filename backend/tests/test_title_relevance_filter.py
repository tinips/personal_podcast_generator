"""Tests for title-based article relevance filtering."""

from __future__ import annotations

from app.services import news_service


def article(title: str, topic: str) -> dict:
    return {"title": title, "topic": topic, "query": topic}


def test_title_matches_short_exact_interest() -> None:
    assert news_service.title_matches_interest(article("AI reshapes education", "AI"), "AI")
    assert news_service.title_matches_interest(article("The future of AI", "AI"), "AI")
    assert news_service.title_matches_interest(article("AI-driven tools arrive", "AI"), "AI")
    assert news_service.title_matches_interest(article("AI: regulation and safety", "AI"), "AI")


def test_title_rejects_weak_or_unrelated_short_interest_matches() -> None:
    assert not news_service.title_matches_interest(article("Rainfall disrupts travel", "AI"), "AI")
    assert not news_service.title_matches_interest(article("OpenAI launches new model", "AI"), "AI")
    assert not news_service.title_matches_interest(
        article("Artificial intelligence rules advance", "AI"),
        "AI",
    )
    assert not news_service.title_matches_interest(article("What officials said today", "AI"), "AI")
    assert not news_service.title_matches_interest(article("Chair maker expands", "AI"), "AI")
    assert not news_service.title_matches_interest(
        article("Tashkent housing market cools", "AI"),
        "AI",
    )


def test_title_matches_multi_word_interest_tokens() -> None:
    assert news_service.title_matches_interest(
        article("Venture capital funding rises", "venture capital"),
        "venture capital",
    )
    assert news_service.title_matches_interest(
        article("Capital flows into venture funds", "venture capital"),
        "venture capital",
    )
    assert news_service.title_matches_interest(
        article("AI regulation bill advances", "AI regulation"),
        "AI regulation",
    )


def test_title_rejects_partial_multi_word_interest_matches() -> None:
    assert news_service.title_matches_interest(
        article("Startups raise funding", "startups"),
        "startups",
    )
    assert not news_service.title_matches_interest(
        article("Startup raises funding", "startups"),
        "startups",
    )
    assert not news_service.title_matches_interest(
        article("AI safety debate grows", "AI regulation"),
        "AI regulation",
    )


def test_filter_title_relevant_articles_keeps_provider_order() -> None:
    ordered = [
        article("Rainfall disrupts travel", "AI"),
        article("AI reshapes education", "AI"),
        article("Startups raise funding", "startups"),
        article("Chair maker expands", "AI"),
    ]

    filtered = news_service.filter_title_relevant_articles(ordered, ["AI", "startups"])

    assert [item["title"] for item in filtered] == [
        "AI reshapes education",
        "Startups raise funding",
    ]
