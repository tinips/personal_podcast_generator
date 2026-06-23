from pydantic import BaseModel, Field, model_validator
from typing import Optional


DURATION_CONFIG = {
    "short": {"minutes": 1, "max_topics": 1},
    "normal": {"minutes": 2, "max_topics": 2},
    "long": {"minutes": 3, "max_topics": 3},
}

VALID_SPEAKER_MODES = {"solo", "dialogue"}
VALID_DURATIONS = set(DURATION_CONFIG.keys())
VALID_TONES = {"professional", "casual", "energetic"}
VALID_FREQUENCIES = {"manual", "daily", "weekly"}


class ArticleSource(BaseModel):
    title: str
    source: str
    url: str
    published_at: str = ""
    provider: str = ""
    topic: str = ""


class ToolUsageItem(BaseModel):
    tool_name: str
    purpose: str
    calls: int = 0
    usage_unit: str = ""
    usage_amount: float = 0.0
    estimated_cost_usd: float = 0.0


class RecentGenerationMetric(BaseModel):
    created_at: str
    selected_interests: list[str] = Field(default_factory=list)
    speaker_mode: str = "solo"
    generation_type: str = "manual"
    frequency: str = "manual"
    status: str = "completed"
    article_count: int = 0
    duplicate_articles_filtered: int = 0
    seen_articles_filtered: int = 0
    total_fetched: int = 0
    fetched_count: int = 0
    invalid_filtered_count: int = 0
    duplicate_filtered_count: int = 0
    title_filtered_count: int = 0
    seen_filtered_count: int = 0
    used_count: int = 0
    generation_time_seconds: Optional[float] = None
    estimated_cost_usd: float = 0.0
    tool_usage: list[ToolUsageItem] = Field(default_factory=list)
    workflow_timings: dict[str, int] = Field(default_factory=dict)


class GenerateRequest(BaseModel):
    topic: Optional[str] = None
    interests: list[str] = Field(default_factory=list)
    selected_interests: list[str] = Field(default_factory=list)
    tone: str = "professional"
    duration: str = "normal"
    duration_minutes: Optional[int] = None
    frequency: str = "manual"
    voice_id: Optional[str] = None
    voice: Optional[str] = None
    user_id: str = ""
    speaker_mode: str = "solo"
    generation_type: str = "manual"
    schedule_id: Optional[str] = None

    @model_validator(mode="after")
    def validate_request(self) -> "GenerateRequest":
        resolved = self.selected_interests or self.interests
        if self.topic and self.topic.strip() and not resolved:
            resolved = [self.topic.strip()]
        if not resolved:
            raise ValueError("At least one selected interest is required.")
        if self.duration not in VALID_DURATIONS:
            raise ValueError(
                f"Unsupported duration '{self.duration}'. "
                f"Choose: {', '.join(sorted(VALID_DURATIONS))}."
            )
        if self.speaker_mode not in VALID_SPEAKER_MODES:
            raise ValueError(
                f"Unsupported speaker_mode '{self.speaker_mode}'. "
                f"Choose: {', '.join(sorted(VALID_SPEAKER_MODES))}."
            )
        max_topics = DURATION_CONFIG[self.duration]["max_topics"]
        if len(resolved) > max_topics:
            raise ValueError(
                f"A {self.duration} podcast supports up to {max_topics} topic(s). "
                f"Select fewer topics or choose a longer duration."
            )
        return self

    @property
    def selected_topic(self) -> str:
        if self.topic and self.topic.strip():
            return self.topic.strip()
        for interest in self.interests:
            if interest.strip():
                return interest.strip()
        return ""

    @property
    def resolved_interests(self) -> list[str]:
        result = self.selected_interests or self.interests
        if self.topic and self.topic.strip():
            result = [self.topic.strip()]
        return [i.strip() for i in result if i.strip()]

    @property
    def selected_voice_id(self) -> Optional[str]:
        return self.voice_id or self.voice

    @property
    def resolved_duration_minutes(self) -> int:
        if self.duration_minutes is not None:
            return max(1, min(self.duration_minutes, 10))
        return DURATION_CONFIG.get(self.duration, {}).get("minutes", 2)

    @property
    def resolved_duration_label(self) -> str:
        if self.duration in DURATION_CONFIG:
            return self.duration
        return "normal"


class EpisodeResponse(BaseModel):
    id: str
    title: str
    summary: str
    script: str
    audio_url: Optional[str]
    interests: list[str] = Field(default_factory=list)
    articles: list[ArticleSource] = Field(default_factory=list)
    tone: str
    duration: str
    frequency: str
    voice: str = ""
    speaker_mode: str = "solo"
    user_id: str = ""
    generation_type: str = "manual"
    schedule_id: Optional[str] = None
    article_count: int = 0
    duplicate_articles_filtered: int = 0
    seen_articles_filtered: int = 0
    total_fetched: int = 0
    invalid_articles_filtered: int = 0
    title_irrelevant_articles_filtered: int = 0
    estimated_cost_usd: float = 0.0
    tool_usage: list[ToolUsageItem] = Field(default_factory=list)
    workflow_timings: dict[str, int] = Field(default_factory=dict)
    created_at: str
    generation_time_ms: Optional[int]
    success: bool
    status: str = "completed"
    error_message: Optional[str] = None
    selected_interest_count: int = 1


class GenerateResponse(BaseModel):
    episode: EpisodeResponse


class EpisodeEventRequest(BaseModel):
    event_type: str
    value: Optional[float] = None


class ScheduleRequest(BaseModel):
    user_id: str = ""
    name: str
    selected_interests: list[str] = Field(default_factory=list)
    frequency: str = "daily"
    duration: str = "normal"
    tone: str = "professional"
    voice_id: Optional[str] = None
    speaker_mode: str = "solo"

    @model_validator(mode="after")
    def validate_schedule(self) -> "ScheduleRequest":
        self.name = self.name.strip()
        self.selected_interests = [
            interest.strip()
            for interest in self.selected_interests
            if interest.strip()
        ]
        if not self.name:
            raise ValueError("Schedule name is required.")
        if not self.selected_interests:
            raise ValueError("At least one selected interest is required.")
        if self.duration not in VALID_DURATIONS:
            raise ValueError(
                f"Unsupported duration '{self.duration}'. "
                f"Choose: {', '.join(sorted(VALID_DURATIONS))}."
            )
        if self.speaker_mode not in VALID_SPEAKER_MODES:
            raise ValueError(
                f"Unsupported speaker_mode '{self.speaker_mode}'. "
                f"Choose: {', '.join(sorted(VALID_SPEAKER_MODES))}."
            )
        if self.frequency not in VALID_FREQUENCIES:
            raise ValueError(
                f"Unsupported frequency '{self.frequency}'. "
                f"Choose: {', '.join(sorted(VALID_FREQUENCIES))}."
            )
        max_topics = DURATION_CONFIG[self.duration]["max_topics"]
        if len(self.selected_interests) > max_topics:
            raise ValueError(
                f"A {self.duration} podcast supports up to {max_topics} topic(s). "
                f"Select fewer topics or choose a longer duration."
            )
        return self


class ScheduleResponse(BaseModel):
    id: str
    user_id: str
    name: str
    selected_interests: list[str] = Field(default_factory=list)
    frequency: str = "daily"
    duration: str = "normal"
    tone: str = "professional"
    voice: str = ""
    speaker_mode: str = "solo"
    last_run_at: Optional[str] = None
    created_at: str = ""


class DashboardMetrics(BaseModel):
    total_episodes: int
    successful_generations: int
    failed_generations: int
    skipped_generations: int
    success_rate: float
    average_generation_time_seconds: Optional[float]
    fastest_generation_time_seconds: Optional[float]
    slowest_generation_time_seconds: Optional[float]
    estimated_average_cost_usd: float

    top_interests: list[dict]
    average_selected_interests_per_episode: float
    average_articles_per_episode: float
    invalid_articles_filtered_total: int
    duplicate_articles_filtered_total: int
    title_irrelevant_articles_filtered_total: int
    seen_articles_filtered_total: int
    skipped_no_new_articles_count: int

    estimated_total_cost_usd: float
    estimated_average_cost_per_episode: float
    most_expensive_tool: str
    tool_cost_breakdown: list[dict]

    average_workflow_timings_ms: dict[str, float]
    workflow_bottleneck: str

    episodes_played: int
    episodes_played_with_audio: int
    episodes_completed_listens: int
    listen_completion_rate: float
    sources_opened_count: int
    script_opened_count: int
    play_rate: float

    episodes_over_time: list[dict]
    generation_time_over_time: list[dict]
    generation_status_breakdown: list[dict]
    freshness_by_episode: list[dict]
    cost_by_tool: list[dict]
    cost_over_time: list[dict]

    recent_generations: list[RecentGenerationMetric]
