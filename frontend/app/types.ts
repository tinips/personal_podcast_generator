export type ArticleSource = {
  title: string;
  source: string;
  url: string;
  published_at: string;
  provider: string;
  topic: string;
};

export type ToolUsageItem = {
  tool_name: string;
  purpose: string;
  calls: number;
  usage_unit: string;
  usage_amount: number;
  estimated_cost_usd: number;
};

export type Episode = {
  id: string;
  title: string;
  summary: string;
  script: string;
  audio_url: string | null;
  interests: string[];
  articles: ArticleSource[];
  tone: string;
  duration: string;
  frequency: string;
  voice: string;
  speaker_mode: string;
  user_id: string;
  generation_type: string;
  schedule_id: string | null;
  article_count: number;
  duplicate_articles_filtered: number;
  seen_articles_filtered: number;
  estimated_cost_usd: number;
  tool_usage: ToolUsageItem[];
  workflow_timings: Record<string, number>;
  created_at: string;
  generation_time_ms: number | null;
  success: boolean;
  status: string;
  error_message: string | null;
  selected_interest_count: number;
};

export type ToolCostItem = {
  tool_name: string;
  purpose: string;
  calls: number;
  usage_unit: string;
  usage_amount: number;
  estimated_cost_usd: number;
  percentage_of_total_cost: number;
  children?: ToolCostItem[];
};

export type RecentGenerationMetric = {
  created_at: string;
  selected_interests: string[];
  speaker_mode: string;
  generation_type: string;
  frequency: string;
  status: "completed" | "failed" | "skipped" | string;
  article_count: number;
  duplicate_articles_filtered: number;
  seen_articles_filtered: number;
  total_fetched: number;
  fetched_count: number;
  invalid_filtered_count: number;
  duplicate_filtered_count: number;
  title_filtered_count: number;
  seen_filtered_count: number;
  used_count: number;
  generation_time_seconds: number | null;
  estimated_cost_usd: number;
  tool_usage: ToolUsageItem[];
  workflow_timings: Record<string, number>;
};

export type DashboardMetrics = {
  total_episodes: number;
  successful_generations: number;
  failed_generations: number;
  skipped_generations: number;
  success_rate: number;
  average_generation_time_seconds: number | null;
  fastest_generation_time_seconds: number | null;
  slowest_generation_time_seconds: number | null;
  estimated_average_cost_usd: number;
  top_interests: { interest: string; count: number }[];
  average_selected_interests_per_episode: number;
  average_articles_per_episode: number;
  invalid_articles_filtered_total: number;
  duplicate_articles_filtered_total: number;
  title_irrelevant_articles_filtered_total: number;
  seen_articles_filtered_total: number;
  skipped_no_new_articles_count: number;
  estimated_total_cost_usd: number;
  estimated_average_cost_per_episode: number;
  most_expensive_tool: string;
  tool_cost_breakdown: ToolCostItem[];
  average_workflow_timings_ms: Record<string, number>;
  workflow_bottleneck: string;
  episodes_played: number;
  episodes_played_with_audio: number;
  episodes_completed_listens: number;
  listen_completion_rate: number;
  sources_opened_count: number;
  script_opened_count: number;
  play_rate: number;
  episodes_over_time: { date: string; count: number }[];
  generation_time_over_time: {
    label: string;
    date: string;
    seconds: number | null;
    generation_time_seconds: number | null;
    status: string;
  }[];
  generation_status_breakdown: { status: string; count: number }[];
  freshness_by_episode: {
    label: string;
    date: string;
    fetched_count: number;
    invalid_filtered_count: number;
    duplicate_filtered_count: number;
    title_filtered_count: number;
    seen_filtered_count: number;
    used_count: number;
  }[];
  cost_by_tool: {
    tool: string;
    cost: number;
    estimated_cost_usd: number;
    percentage_of_total_cost: number;
  }[];
  cost_over_time: {
    date: string;
    label: string;
    cost: number;
    estimated_cost_usd: number;
  }[];
  recent_generations: RecentGenerationMetric[];
};

export type Schedule = {
  id: string;
  user_id: string;
  name: string;
  selected_interests: string[];
  frequency: string;
  duration: string;
  tone: string;
  voice: string;
  speaker_mode: string;
  last_run_at: string | null;
  created_at: string;
};

export type ScheduleRequest = {
  user_id: string;
  name: string;
  selected_interests: string[];
  frequency: string;
  duration: string;
  tone: string;
  speaker_mode: string;
};

export const DURATION_CONFIG: Record<string, { minutes: number; maxTopics: number; label: string }> = {
  short: { minutes: 1, maxTopics: 1, label: "Short" },
  normal: { minutes: 2, maxTopics: 2, label: "Normal" },
  long: { minutes: 3, maxTopics: 3, label: "Long" },
};

export const TONES = ["professional", "casual", "energetic"];
export const FREQUENCIES = ["manual", "daily", "weekly"];
export const SPEAKER_MODES = [
  { value: "solo", label: "Solo host" },
  { value: "dialogue", label: "Two-host conversation" },
];
