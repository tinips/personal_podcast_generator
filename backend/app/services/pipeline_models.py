from pydantic import BaseModel, Field


class BriefingFact(BaseModel):
    fact: str
    source_title: str
    source: str
    url: str


class TopicBriefing(BaseModel):
    topic: str
    summary: str
    why_it_matters: str
    freshness: str
    key_facts: list[BriefingFact]
    tension_or_question: str = ""


class PodcastBriefing(BaseModel):
    episode_theme: str
    listener_interests: list[str]
    topic_briefings: list[TopicBriefing]
    do_not_claim: list[str] = Field(default_factory=list)


class ConversationBeat(BaseModel):
    purpose: str = ""
    john_role: str = ""
    maya_role: str = ""
    source_basis: list[str] = Field(default_factory=list)
    continuity_note: str = ""


class ConversationPlan(BaseModel):
    episode_theme: str
    connection_strategy: str
    connection_confidence: str = ""
    connection_rationale: str = ""
    opening_intent: str
    maya_first_response_intent: str = ""
    beats: list[ConversationBeat | str]
    transition_notes: list[str] = Field(default_factory=list)
    closing_intent: str
    pacing_notes: str = ""
