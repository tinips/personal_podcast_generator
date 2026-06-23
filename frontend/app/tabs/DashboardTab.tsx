"use client";

import { Fragment, useState } from "react";
import { DashboardMetrics, RecentGenerationMetric, ToolCostItem, ToolUsageItem } from "../types";
import LoadingSpinner from "../components/LoadingSpinner";
import SectionHeader from "../components/SectionHeader";
import HorizontalBarChart from "../components/HorizontalBarChart";
import LineChart from "../components/LineChart";
import StatusBreakdownChart from "../components/StatusBreakdownChart";
import FreshnessStackedBarChart, { computeArticlePipelineTotals, computeArticlePipelinePercentages } from "../components/FreshnessStackedBarChart";
import Badge from "../components/Badge";
import ApiStatusPanel from "../components/ApiStatusPanel";
import { formatSeconds, formatCost } from "../utils";

type Props = {
  metrics: DashboardMetrics | null;
  metricsLoading: boolean;
};

type ArticlePipelineRow = DashboardMetrics["freshness_by_episode"][number];
type BadgeTone = "green" | "red" | "amber" | "blue" | "purple" | "gray";
type HealthStatus = "Healthy" | "Needs attention" | "Degraded" | "No data yet";
type KpiTone = "green" | "blue" | "amber" | "purple" | "red";
type IconName = "activity" | "clock" | "dollar" | "play" | "calendar" | "target";

const WORKFLOW_LABELS: Record<string, string> = {
  news_retrieval_ms: "News Retrieval",
  article_filtering_ms: "Article Filtering",
  briefing_llm_ms: "Briefing LLM",
  conversation_planning_llm_ms: "Conversation Plan LLM",
  script_writer_llm_ms: "Script Writer LLM",
  quality_check_ms: "Quality Check",
  tts_audio_generation_ms: "TTS Audio Generation",
  episode_storage_ms: "Episode Storage",
  total_generation_ms: "Total Generation",
};

const WORKFLOW_ORDER = [
  "news_retrieval_ms",
  "article_filtering_ms",
  "briefing_llm_ms",
  "conversation_planning_llm_ms",
  "script_writer_llm_ms",
  "quality_check_ms",
  "tts_audio_generation_ms",
  "episode_storage_ms",
];

const KPI_CLASSES: Record<KpiTone, string> = {
  green: "border-l-emerald-500",
  blue: "border-l-blue-500",
  amber: "border-l-amber-500",
  purple: "border-l-violet-500",
  red: "border-l-red-500",
};

const KPI_ICON_CLASSES: Record<KpiTone, string> = {
  green: "bg-emerald-50 text-emerald-600",
  blue: "bg-blue-50 text-blue-600",
  amber: "bg-amber-50 text-amber-600",
  purple: "bg-violet-50 text-violet-600",
  red: "bg-red-50 text-red-600",
};

const ICON_PATHS: Record<IconName, string> = {
  activity: "M22 12h-4l-3 8L9 4l-3 8H2",
  clock: "M12 6v6l4 2 M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z",
  dollar: "M12 2v20 M17 5H9.5a3.5 3.5 0 0 0 0 7H14a3.5 3.5 0 0 1 0 7H6",
  play: "M8 5v14l11-7-11-7Z",
  calendar: "M8 2v4 M16 2v4 M3 10h18 M5 4h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z",
  target: "M12 2a10 10 0 1 0 10 10 M12 6a6 6 0 1 0 6 6 M12 10a2 2 0 1 0 2 2",
};

const ARTICLE_PIPELINE_DEMO_PATTERN = [
  { fetched_count: 10, invalid_filtered_count: 1, duplicate_filtered_count: 1, title_filtered_count: 5, seen_filtered_count: 0, used_count: 2 },
  { fetched_count: 12, invalid_filtered_count: 1, duplicate_filtered_count: 0, title_filtered_count: 6, seen_filtered_count: 1, used_count: 2 },
  { fetched_count: 15, invalid_filtered_count: 2, duplicate_filtered_count: 1, title_filtered_count: 7, seen_filtered_count: 1, used_count: 3 },
  { fetched_count: 15, invalid_filtered_count: 1, duplicate_filtered_count: 2, title_filtered_count: 7, seen_filtered_count: 1, used_count: 3 },
  { fetched_count: 20, invalid_filtered_count: 3, duplicate_filtered_count: 2, title_filtered_count: 10, seen_filtered_count: 2, used_count: 3 },
  { fetched_count: 12, invalid_filtered_count: 1, duplicate_filtered_count: 1, title_filtered_count: 6, seen_filtered_count: 0, used_count: 2 },
  { fetched_count: 15, invalid_filtered_count: 2, duplicate_filtered_count: 1, title_filtered_count: 8, seen_filtered_count: 1, used_count: 2 },
];

function formatMs(value: number): string {
  return value >= 1000 ? `${(value / 1000).toFixed(1)}s` : `${Math.round(value)}ms`;
}

function Icon({ name, className = "h-5 w-5" }: { name: IconName; className?: string }) {
  return (
    <svg
      aria-hidden="true"
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d={ICON_PATHS[name]} />
    </svg>
  );
}

function formatKpiPercent(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "N/A";
  return `${Math.round(value)}%`;
}

function formatKpiSeconds(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "N/A";
  return `${value.toFixed(1)}s`;
}

function formatKpiCost(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "N/A";
  return `$${value.toFixed(2)}`;
}

function formatCreatedDate(value: string): string {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "Unknown";
  return date.toLocaleDateString();
}

function formatRelativeAge(value: string): string {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "Unknown age";

  const diffMs = Date.now() - date.getTime();
  const absMs = Math.abs(diffMs);
  const minutes = Math.floor(absMs / 60000);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);
  const suffix = diffMs >= 0 ? "ago" : "from now";

  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes}m ${suffix}`;
  if (hours < 24) return `${hours}h ${suffix}`;
  if (days < 30) return `${days}d ${suffix}`;
  return date.toLocaleDateString();
}

function formatUsageAmount(value: number): string {
  if (!Number.isFinite(value)) return "0";
  return Number.isInteger(value) ? value.toLocaleString() : value.toLocaleString(undefined, {
    maximumFractionDigits: 1,
  });
}

function toolLabel(toolName: string): string {
  if (toolName === "openai") return "OpenAI";
  if (toolName === "openai_briefing") return "OpenAI Briefing";
  if (toolName === "openai_planner") return "OpenAI Planner";
  if (toolName === "openai_script_writer") return "OpenAI Script Writer";
  if (toolName === "elevenlabs") return "ElevenLabs";
  if (toolName === "news") return "News";
  return toolName || "Unknown";
}

function resourceAmountLabel(tool: ToolUsageItem): string {
  const unit = tool.usage_unit || "units";
  return `${formatUsageAmount(tool.usage_amount)} ${unit}`;
}

function workflowLabel(key: string): string {
  return WORKFLOW_LABELS[key] || key.replace(/_/g, " ");
}

function safeWorkflowBottleneckLabel(key: string | null | undefined): string {
  if (!key || key === "N/A") return "N/A";
  return workflowLabel(key);
}

function workflowStages(timings: Record<string, number>) {
  return WORKFLOW_ORDER
    .filter((key) => timings[key] != null)
    .map((key) => ({
      key,
      stage: workflowLabel(key),
      ms: timings[key],
    }));
}


function buildArticlePipelineDemoRows(rows: ArticlePipelineRow[]): ArticlePipelineRow[] {
  const sourceRows = rows.length > 0
    ? rows
    : ARTICLE_PIPELINE_DEMO_PATTERN.map((_row, index) => ({
        label: `Demo #${index + 1}`,
        date: "",
        fetched_count: 0,
        invalid_filtered_count: 0,
        duplicate_filtered_count: 0,
        title_filtered_count: 0,
        seen_filtered_count: 0,
        used_count: 0,
      }));

  return sourceRows.map((row, index) => ({
    ...row,
    ...ARTICLE_PIPELINE_DEMO_PATTERN[index % ARTICLE_PIPELINE_DEMO_PATTERN.length],
  }));
}

function freshnessSummary(rows: ArticlePipelineRow[]): string {
  const totals = computeArticlePipelineTotals(rows);
  const percentages = computeArticlePipelinePercentages(totals);
  return `${totals.fetched} demo articles fetched across ${rows.length} displayed episodes. ${totals.invalid} invalid articles filtered (${percentages.invalid}%). ${totals.duplicate} duplicates removed (${percentages.duplicate}%). ${totals.title} title-irrelevant articles filtered (${percentages.title}%). ${totals.seen} previously seen articles skipped (${percentages.seen}%). ${totals.used} articles used (${percentages.used}%).`;
}

function healthStatus(metrics: DashboardMetrics): HealthStatus {
  if (metrics.total_episodes === 0) return "No data yet";
  if (
    metrics.success_rate >= 95 &&
    metrics.failed_generations === 0 &&
    metrics.skipped_generations === 0
  ) {
    return "Healthy";
  }
  if (metrics.success_rate < 80) return "Degraded";
  return "Needs attention";
}

function healthStatusTone(status: HealthStatus): BadgeTone {
  if (status === "Healthy") return "green";
  if (status === "Needs attention") return "amber";
  if (status === "Degraded") return "red";
  return "gray";
}

function deliveryRateTone(metrics: DashboardMetrics): KpiTone {
  if (metrics.success_rate >= 95) return "green";
  if (metrics.success_rate >= 80) return "amber";
  return "red";
}

function heroHeadline(metrics: DashboardMetrics): string {
  const status = healthStatus(metrics);
  if (status === "Healthy") return "Podcast generation status is healthy";
  if (status === "Needs attention") return "Podcast generation includes incomplete runs";
  if (status === "Degraded") return "Podcast generation is below the delivery threshold";
  return "No monitoring data yet";
}

function heroDiagnosis(metrics: DashboardMetrics): string {
  if (metrics.total_episodes === 0) {
    return "Generate a podcast to start measuring reliability, latency, cost, and engagement.";
  }

  if (metrics.workflow_bottleneck && metrics.workflow_bottleneck !== "N/A") {
    return `Average workflow timings identify ${workflowLabel(metrics.workflow_bottleneck)} as the slowest stage.`;
  }
  return "Recorded runs include delivery, timing, cost, and engagement telemetry.";
}

function recordedState(metrics: DashboardMetrics): string {
  if (metrics.total_episodes === 0) {
    return "No generation runs recorded.";
  }
  if (metrics.failed_generations > 0) {
    return "Failed generation attempts are present.";
  }
  if (metrics.skipped_generations > 0) {
    return "No-fresh-news skips are present.";
  }
  if (metrics.workflow_bottleneck && metrics.workflow_bottleneck !== "N/A") {
    return `Slowest average stage: ${workflowLabel(metrics.workflow_bottleneck)}.`;
  }
  return "Completed runs have no recorded failures or skips.";
}

function latestGenerationDate(metrics: DashboardMetrics): Date | null {
  const dates = metrics.recent_generations
    .map((generation) => new Date(generation.created_at))
    .filter((date) => Number.isFinite(date.getTime()));
  if (dates.length === 0) return null;
  return dates.reduce((latest, date) => (date > latest ? date : latest));
}

function formatLastUpdated(metrics: DashboardMetrics): string {
  const date = latestGenerationDate(metrics);
  if (!date) return "No updates yet";
  return `Last updated ${date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  })}`;
}

function statusLabel(status: string): string {
  if (status === "completed") return "Completed";
  if (status === "skipped") return "No Fresh News";
  if (status === "audio_failed") return "Audio Failed";
  if (status === "failed") return "Failed";
  return status.replace(/_/g, " ");
}

function statusTone(status: string): BadgeTone {
  if (status === "completed") return "green";
  if (status === "skipped") return "amber";
  if (status === "failed" || status === "audio_failed") return "red";
  return "gray";
}

function modeLabel(mode: string): string {
  return mode === "dialogue" ? "Dialogue" : "Solo";
}

function typeLabel(type: string): string {
  return type === "scheduled" ? "Scheduled" : "Manual";
}

function freshnessWindowLabel(episode: RecentGenerationMetric): string {
  if (episode.generation_type === "manual") return "2d window";
  if (episode.frequency === "daily") return "1d window";
  if (episode.frequency === "weekly") return "7d window";
  return "2d window";
}

function episodeBottleneck(workflowTimings: Record<string, number>): string {
  const entries = Object.entries(workflowTimings).filter(
    ([key]) => key !== "total_generation_ms"
  );
  if (entries.length === 0) return "";
  return entries.reduce((max, current) => (current[1] > max[1] ? current : max))[0];
}

function OverviewKpiGrid({ metrics }: { metrics: DashboardMetrics }) {
  const bottleneck = safeWorkflowBottleneckLabel(metrics.workflow_bottleneck);

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <KpiCard
        label="Delivery Rate"
        icon="activity"
        value={formatKpiPercent(metrics.success_rate)}
        detail={`${metrics.successful_generations} completed - ${metrics.failed_generations} failed - ${metrics.skipped_generations} skipped`}
        explanation="Attempts that became playable podcast episodes."
        tone={deliveryRateTone(metrics)}
      />
      <KpiCard
        label="Avg Generation Time"
        icon="clock"
        value={formatKpiSeconds(metrics.average_generation_time_seconds)}
        detail={`Bottleneck: ${bottleneck}`}
        explanation="Average end-to-end time across recorded generation runs."
        tone="blue"
      />
      <KpiCard
        label="Avg Cost / Completed"
        icon="dollar"
        value={formatKpiCost(metrics.estimated_average_cost_per_episode)}
        detail={`Most expensive: ${toolLabel(metrics.most_expensive_tool)}`}
        explanation="Estimated provider cost for each completed episode."
        tone="amber"
      />
      <KpiCard
        label="Play Rate"
        icon="play"
        value={formatKpiPercent(metrics.play_rate)}
        detail={`${metrics.episodes_played_with_audio} with audio played - ${metrics.episodes_completed_listens} completed`}
        explanation="Completed episodes that were played in the local UI."
        tone="purple"
      />
    </div>
  );
}


function KpiCard({
  label,
  icon,
  value,
  detail,
  explanation,
  tone,
}: {
  label: string;
  icon: IconName;
  value: React.ReactNode;
  detail: string;
  explanation: string;
  tone: KpiTone;
}) {
  return (
    <div className={`rounded-lg border border-l-4 bg-white p-4 shadow-sm ${KPI_CLASSES[tone]}`}>
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm font-medium text-gray-500">{label}</p>
        <span className={`rounded-md p-2 ${KPI_ICON_CLASSES[tone]}`}>
          <Icon name={icon} className="h-4 w-4" />
        </span>
      </div>
      <div className="mt-2 text-3xl font-semibold text-gray-950">{value}</div>
      <p className="mt-2 text-xs font-medium text-gray-600">{detail}</p>
      <p className="mt-2 text-xs leading-5 text-gray-400">{explanation}</p>
    </div>
  );
}

function BreakdownHeader({
  icon,
  title,
  subtitle,
}: {
  icon: IconName;
  title: string;
  subtitle: string;
}) {
  return (
    <div className="mb-3 flex items-start gap-3">
      <span className="rounded-md bg-gray-100 p-2 text-gray-600">
        <Icon name={icon} className="h-4 w-4" />
      </span>
      <div>
        <h2 className="text-lg font-semibold text-gray-950">{title}</h2>
        <p className="mt-1 text-sm text-gray-500">{subtitle}</p>
      </div>
    </div>
  );
}

function StageBreakdown({
  stages,
  sorted = false,
}: {
  stages: { key: string; stage: string; ms: number }[];
  sorted?: boolean;
}) {
  const displayStages = sorted
    ? [...stages].sort((a, b) => b.ms - a.ms)
    : stages;
  const max = Math.max(1, ...displayStages.map((stage) => stage.ms));

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-[118px_1fr_54px] items-center gap-3 text-[10px] font-medium uppercase text-gray-400 sm:grid-cols-[150px_1fr_58px]">
        <span>Stage</span>
        <span>Relative duration</span>
        <span className="text-right">Time</span>
      </div>
      {displayStages.map((stage) => {
        const width = Math.max(3, (stage.ms / max) * 100);
        return (
          <div
            key={stage.key}
            className="grid grid-cols-[118px_1fr_54px] items-center gap-3 sm:grid-cols-[150px_1fr_58px]"
          >
            <span className="truncate text-xs font-medium text-gray-600">
              {stage.stage}
            </span>
            <div className="h-3 overflow-hidden rounded-full bg-gray-100">
              <div
                className="h-full rounded-full bg-indigo-600"
                style={{ width: `${width}%` }}
              />
            </div>
            <span className="text-right text-xs tabular-nums text-gray-500">
              {formatMs(stage.ms)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function ResourceBreakdown({ episode }: { episode: RecentGenerationMetric }) {
  return (
    <div className="mb-4">
      <div className="rounded-md border border-gray-200 bg-white px-3 py-2">
        <p className="text-[11px] font-medium uppercase text-gray-400">
          Resource usage
        </p>
        {episode.tool_usage.length === 0 ? (
          <p className="mt-1 text-sm text-gray-500">
            Resource usage was not recorded for this run.
          </p>
        ) : (
          <div className="mt-2 grid gap-2 sm:grid-cols-3">
            {episode.tool_usage.map((tool) => (
              <div key={tool.tool_name} className="rounded bg-gray-50 px-2 py-2">
                <p className="text-xs font-semibold text-gray-700">
                  {toolLabel(tool.tool_name)}
                </p>
                <p className="mt-1 text-xs text-gray-500">
                  {tool.calls} call{tool.calls === 1 ? "" : "s"} -{" "}
                  {resourceAmountLabel(tool)}
                </p>
                <p className="mt-1 text-xs font-mono text-gray-500">
                  {formatCost(tool.estimated_cost_usd)}
                </p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function CostBreakdownRow({
  tool,
  isChild = false,
  expanded = false,
  onToggle,
}: {
  tool: ToolCostItem;
  isChild?: boolean;
  expanded?: boolean;
  onToggle?: () => void;
}) {
  const expandable = Boolean(onToggle);
  return (
    <tr
      className={`border-b last:border-0 ${expandable ? "cursor-pointer hover:bg-gray-50" : ""} ${
        isChild ? "bg-gray-50" : ""
      }`}
      onClick={onToggle}
    >
      <td className={`px-4 py-2 font-medium text-gray-800 ${isChild ? "pl-8" : ""}`}>
        {expandable ? (
          <span className="inline-flex items-center gap-1">
            <span className="text-xs text-gray-400">{expanded ? "v" : ">"}</span>
            {toolLabel(tool.tool_name)}
          </span>
        ) : (
          toolLabel(tool.tool_name)
        )}
      </td>
      <td className="px-4 py-2 text-gray-500">{tool.purpose}</td>
      <td className="px-4 py-2 text-right">{tool.calls}</td>
      <td className="px-4 py-2 text-right">
        {tool.usage_amount.toLocaleString()} {tool.usage_unit}
      </td>
      <td className="px-4 py-2 text-right font-mono">
        {formatCost(tool.estimated_cost_usd)}
      </td>
      <td className="px-4 py-2 text-right">
        <div className="flex items-center justify-end gap-2">
          <div
            className="h-2 rounded bg-emerald-500"
            style={{
              width:
                tool.percentage_of_total_cost > 0
                  ? `${Math.max(6, tool.percentage_of_total_cost)}px`
                  : "0px",
            }}
          />
          <span>{tool.percentage_of_total_cost}%</span>
        </div>
      </td>
    </tr>
  );
}

function TraceDetail({ episode }: { episode: RecentGenerationMetric }) {
  const stages = workflowStages(episode.workflow_timings);
  if (stages.length === 0) {
    return (
      <div className="rounded-md bg-gray-50 px-4 py-3">
        <ResourceBreakdown episode={episode} />
        <p className="text-xs text-gray-500">
          Workflow timing was not recorded for this generation.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-md bg-gray-50 px-4 py-3">
      <ResourceBreakdown episode={episode} />
      <div className="mb-3 flex flex-wrap gap-2 text-[11px] font-medium text-gray-500">
        {stages.map((stage, index) => (
          <Fragment key={stage.key}>
            <span>{stage.stage}</span>
            {index < stages.length - 1 && <span className="text-gray-300">-&gt;</span>}
          </Fragment>
        ))}
      </div>
      <StageBreakdown stages={stages} />
    </div>
  );
}

export default function DashboardTab({ metrics, metricsLoading }: Props) {
  const [expandedTrace, setExpandedTrace] = useState<string | null>(null);
  const [openAiCostExpanded, setOpenAiCostExpanded] = useState(false);

  const averageStages = metrics
    ? workflowStages(metrics.average_workflow_timings_ms)
    : [];
  const articlePipelineRows = metrics
    ? buildArticlePipelineDemoRows(metrics.freshness_by_episode)
    : [];
  const status = metrics ? healthStatus(metrics) : null;

  return (
    <section className="space-y-6">
      {metricsLoading && (
        <div className="rounded-lg border bg-white p-8 text-center shadow-sm">
          <p className="mb-4 text-sm font-medium text-gray-600">
            Loading monitoring metrics...
          </p>
          <LoadingSpinner />
        </div>
      )}

      {!metricsLoading && metrics && status && (
        <>
          <ApiStatusPanel />

          <div className="rounded-lg border border-gray-200 bg-gray-950 p-6 text-white shadow-sm">
            <div className="flex flex-col gap-6 lg:flex-row lg:items-stretch lg:justify-between">
              <div className="max-w-3xl">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-sm font-medium text-gray-300">
                    Personal Podcast Monitoring
                  </p>
                  <Badge tone={healthStatusTone(status)}>{status}</Badge>
                  <span className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/10 px-2 py-1 text-xs font-medium text-gray-300">
                    <Icon name="calendar" className="h-3.5 w-3.5" />
                    {formatLastUpdated(metrics)}
                  </span>
                </div>
                <h2 className="mt-3 text-3xl font-semibold tracking-normal">
                  {heroHeadline(metrics)}
                </h2>
                <p className="mt-3 text-sm leading-6 text-gray-300">
                  {heroDiagnosis(metrics)}
                </p>
              </div>
              <div className="rounded-md border border-white/10 bg-white/10 px-4 py-4 lg:min-w-[320px] lg:max-w-sm">
                <div className="flex items-center gap-2 text-xs font-medium uppercase text-gray-300">
                  <Icon name="target" className="h-4 w-4" />
                  <span>Recorded state</span>
                </div>
                <p className="mt-2 text-sm font-semibold leading-6">
                  {recordedState(metrics)}
                </p>
              </div>
            </div>
          </div>

          <OverviewKpiGrid metrics={metrics} />

          {metrics.total_episodes === 0 ? (
            <div className="rounded-lg border bg-white p-12 text-center text-gray-500">
              <p className="font-medium text-gray-700">
                No generations yet. Generate a podcast to populate monitoring metrics.
              </p>
              <p className="mt-2 text-sm">
                Run backend/scripts/generate_demo_dashboard_data.py to create local demo data.
              </p>
            </div>
          ) : (
            <>

          <div>
            <BreakdownHeader
              icon="activity"
              title="Reliability Breakdown"
              subtitle="Explains whether generation attempts become playable episodes, fail technically, or skip because there is no fresh news."
            />
            <div className="rounded-lg border bg-white p-4 shadow-sm">
              <h3 className="mb-3 text-sm font-semibold text-gray-800">
                Generation Status Breakdown
              </h3>
              <StatusBreakdownChart
                data={metrics.generation_status_breakdown}
                xAxisLabel="Runs"
                yAxisLabel="Generation status"
              />
            </div>
          </div>

          <div>
            <BreakdownHeader
              icon="clock"
              title="Latency Breakdown"
              subtitle="Each generation is treated like a lightweight trace. This shows which pipeline stage is slowest."
            />
            <div className="grid gap-4 lg:grid-cols-2">
              <div className="rounded-lg border bg-white p-4 shadow-sm">
                <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                  <h3 className="text-sm font-semibold text-gray-800">
                    Generation Time Over Time
                  </h3>
                  <span className="text-xs font-medium text-gray-500">
                    Fastest / slowest:{" "}
                    {metrics.fastest_generation_time_seconds != null
                      ? `${formatSeconds(metrics.fastest_generation_time_seconds)} / ${formatSeconds(metrics.slowest_generation_time_seconds)}`
                      : "N/A"}
                  </span>
                </div>
                <LineChart
                  data={metrics.generation_time_over_time}
                  valueKey="seconds"
                  valueFormatter={(value) => `${value.toFixed(1)}s`}
                  stroke="#2563eb"
                  xAxisLabel="Date"
                  yAxisLabel="Generation time (s)"
                />
              </div>
              <div className="rounded-lg border bg-white p-4 shadow-sm">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <h3 className="text-sm font-semibold text-gray-800">
                    Average Pipeline Stage Duration
                  </h3>
                  <span className="rounded bg-indigo-100 px-2 py-1 text-xs font-medium text-indigo-700">
                    trace view
                  </span>
                </div>
                {averageStages.length === 0 ? (
                  <div className="rounded-md bg-gray-50 p-6 text-center text-sm text-gray-400">
                    Workflow timing appears after the next generated episode.
                  </div>
                ) : (
                  <StageBreakdown stages={averageStages} sorted />
                )}
              </div>
            </div>
          </div>

          <div>
            <BreakdownHeader
              icon="dollar"
              title="Cost Breakdown"
              subtitle="Estimated provider usage and cost by tool. Totals include recorded attempts; the KPI average uses completed episodes only."
            />
            <div className="rounded-lg border bg-white p-4 shadow-sm">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <h3 className="text-sm font-semibold text-gray-800">Cost Over Time</h3>
                <span className="text-xs font-medium text-gray-500">
                  Total estimate, all recorded attempts:{" "}
                  {formatCost(metrics.estimated_total_cost_usd)}
                </span>
              </div>
              <LineChart
                data={metrics.cost_over_time}
                valueKey="cost"
                valueFormatter={formatCost}
                stroke="#059669"
                xAxisLabel="Date"
                yAxisLabel="Estimated cost (USD)"
              />
            </div>
            {metrics.tool_cost_breakdown.length > 0 && (
              <div className="mt-4 overflow-x-auto rounded-lg border bg-white shadow-sm">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b bg-gray-50 text-left text-xs font-medium uppercase text-gray-500">
                      <th className="px-4 py-2">Tool</th>
                      <th className="px-4 py-2">Purpose</th>
                      <th className="px-4 py-2 text-right">Calls</th>
                      <th className="px-4 py-2 text-right">Usage</th>
                      <th className="px-4 py-2 text-right">Estimated Cost</th>
                      <th className="px-4 py-2 text-right">% of Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {metrics.tool_cost_breakdown.map((tool) => (
                      <Fragment key={tool.tool_name}>
                        <CostBreakdownRow
                          tool={tool}
                          expanded={openAiCostExpanded}
                          onToggle={
                            tool.tool_name === "openai" && tool.children?.length
                              ? () => setOpenAiCostExpanded((value) => !value)
                              : undefined
                          }
                        />
                        {tool.tool_name === "openai" &&
                          openAiCostExpanded &&
                          tool.children?.map((child) => (
                            <CostBreakdownRow
                              key={`${tool.tool_name}-${child.tool_name}`}
                              tool={child}
                              isChild
                            />
                          ))}
                      </Fragment>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div>
            <SectionHeader
              title="Article Pipeline"
              subtitle="Fetched articles are counted in backend filter order: invalid, duplicate, title-irrelevant, previously seen, and used."
            />
            <div className="grid gap-4 lg:grid-cols-[1fr_1.15fr]">
              <div className="rounded-lg border bg-white p-4 shadow-sm">
                <h3 className="mb-3 text-sm font-semibold text-gray-800">
                  Most Used Interests
                </h3>
                <HorizontalBarChart
                  data={metrics.top_interests}
                  labelKey="interest"
                  valueKey="count"
                  valueFormatter={(value) => `${value} episode${value === 1 ? "" : "s"}`}
                  barClassName="bg-blue-600"
                  xAxisLabel="Episode count"
                  yAxisLabel="Interests"
                />
              </div>
              <div className="rounded-lg border bg-white p-4 shadow-sm">
                <h3 className="mb-3 text-sm font-semibold text-gray-800">
                  Article Pipeline by Episode
                </h3>
                <FreshnessStackedBarChart data={articlePipelineRows} />
                <p className="mt-3 rounded-md bg-violet-50 px-3 py-2 text-sm text-violet-700">
                  {freshnessSummary(articlePipelineRows)}
                </p>
              </div>
            </div>
          </div>

          <div>
            <SectionHeader
              title="Recent Runs"
              subtitle="Latest generation attempts as a debug log with status, freshness, latency, cost, and bottleneck."
            />
            {metrics.recent_generations.length === 0 ? (
              <div className="rounded-lg border bg-white p-8 text-center text-gray-400">
                No generations yet.
              </div>
            ) : (
              <div className="overflow-x-auto rounded-lg border bg-white shadow-sm">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b bg-gray-50 text-left text-xs font-medium uppercase text-gray-500">
                      <th className="px-3 py-2">Created</th>
                      <th className="px-3 py-2">Topics</th>
                      <th className="px-3 py-2">Format</th>
                      <th className="px-3 py-2">Type</th>
                      <th className="px-3 py-2">Status</th>
                      <th className="px-3 py-2 text-right">Sources</th>
                      <th className="px-3 py-2">Freshness</th>
                      <th className="px-3 py-2 text-right">Time</th>
                      <th className="px-3 py-2 text-right">Cost</th>
                      <th className="px-3 py-2">Bottleneck</th>
                    </tr>
                  </thead>
                  <tbody>
                    {metrics.recent_generations.map((episode, index) => {
                      const rowId = `${episode.created_at}-${index}`;
                      const bottleneckKey = episodeBottleneck(episode.workflow_timings);
                      const expanded = expandedTrace === rowId;
                      return (
                        <Fragment key={rowId}>
                          <tr
                            className="cursor-pointer border-b hover:bg-gray-50"
                            onClick={() => setExpandedTrace(expanded ? null : rowId)}
                          >
                            <td className="whitespace-nowrap px-3 py-2 text-xs">
                              <div className="font-medium text-gray-700">
                                {formatCreatedDate(episode.created_at)}
                              </div>
                              <div className="mt-0.5 text-[11px] text-gray-400">
                                {formatRelativeAge(episode.created_at)}
                              </div>
                            </td>
                            <td className="px-3 py-2 text-xs">
                              {episode.selected_interests.join(", ") || "-"}
                            </td>
                            <td className="px-3 py-2 text-xs">
                              <Badge
                                tone={episode.speaker_mode === "solo" ? "blue" : "purple"}
                              >
                                {modeLabel(episode.speaker_mode)}
                              </Badge>
                            </td>
                            <td className="px-3 py-2 text-xs">
                              <Badge
                                tone={
                                  episode.generation_type === "scheduled"
                                    ? "purple"
                                    : "gray"
                                }
                              >
                                {typeLabel(episode.generation_type)}
                              </Badge>
                            </td>
                            <td className="px-3 py-2 text-xs">
                              <Badge tone={statusTone(episode.status)}>
                                {statusLabel(episode.status)}
                              </Badge>
                            </td>
                            <td className="px-3 py-2 text-right text-xs tabular-nums">
                              {episode.used_count}
                            </td>
                            <td className="px-3 py-2 text-xs text-gray-500">
                              {freshnessWindowLabel(episode)}
                            </td>
                            <td className="whitespace-nowrap px-3 py-2 text-right text-xs">
                              {episode.generation_time_seconds != null
                                ? `${episode.generation_time_seconds.toFixed(1)}s`
                                : "-"}
                            </td>
                            <td className="px-3 py-2 text-right text-xs font-mono">
                              {formatCost(episode.estimated_cost_usd)}
                            </td>
                            <td className="px-3 py-2 text-xs">
                              {bottleneckKey ? (
                                <Badge tone="gray">{workflowLabel(bottleneckKey)}</Badge>
                              ) : (
                                "-"
                              )}
                            </td>
                          </tr>
                          {expanded && (
                            <tr className="border-b">
                              <td colSpan={10} className="px-3 py-3">
                                <TraceDetail episode={episode} />
                              </td>
                            </tr>
                          )}
                        </Fragment>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
            </>
          )}
        </>
      )}

      {!metricsLoading && !metrics && (
        <div className="rounded-lg border bg-white p-12 text-center text-gray-400">
          Could not load monitoring metrics. Ensure the backend is running, then
          reopen the Monitoring tab to retry.
        </div>
      )}
    </section>
  );
}
