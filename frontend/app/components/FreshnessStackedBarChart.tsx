export type ArticlePipelineRow = {
  label: string;
  fetched_count: number;
  invalid_filtered_count: number;
  duplicate_filtered_count: number;
  title_filtered_count: number;
  seen_filtered_count: number;
  used_count: number;
};

export type ArticlePipelineTotals = {
  fetched: number;
  invalid: number;
  duplicate: number;
  title: number;
  seen: number;
  used: number;
};

export function computeArticlePipelineTotals(rows: ArticlePipelineRow[]): ArticlePipelineTotals {
  return rows.reduce(
    (sum, row) => ({
      fetched: sum.fetched + row.fetched_count,
      invalid: sum.invalid + row.invalid_filtered_count,
      duplicate: sum.duplicate + row.duplicate_filtered_count,
      title: sum.title + row.title_filtered_count,
      seen: sum.seen + row.seen_filtered_count,
      used: sum.used + row.used_count,
    }),
    { fetched: 0, invalid: 0, duplicate: 0, title: 0, seen: 0, used: 0 }
  );
}

export function computeArticlePipelinePercentages(totals: ArticlePipelineTotals) {
  const pct = (n: number) =>
    totals.fetched === 0 ? 0 : Math.round((n / totals.fetched) * 100);
  return {
    invalid: pct(totals.invalid),
    duplicate: pct(totals.duplicate),
    title: pct(totals.title),
    seen: pct(totals.seen),
    used: pct(totals.used),
  };
}

export default function FreshnessStackedBarChart({
  data,
}: {
  data: ArticlePipelineRow[];
}) {
  const rows = data;

  const maxValue = Math.max(
    1,
    ...rows.flatMap((row) => [
      row.fetched_count,
      row.invalid_filtered_count,
      row.duplicate_filtered_count,
      row.title_filtered_count,
      row.seen_filtered_count,
      row.used_count,
    ])
  );

  const totals = computeArticlePipelineTotals(rows);
  const percentages = computeArticlePipelinePercentages(totals);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2 text-[10px] font-medium uppercase text-gray-400">
        <span>Rows: episodes</span>
        <span>Values: article counts by pipeline stage</span>
      </div>
      <p className="rounded-md bg-gray-50 px-3 py-2 text-xs text-gray-500">
        Demo funnel view using deterministic counts to show backend filter order.
      </p>
      <div className="grid grid-cols-[72px_repeat(6,minmax(58px,1fr))] gap-1.5 text-[10px] font-medium uppercase text-gray-400">
        <span>EP</span>
        <span>FETCHED</span>
        <span>INVALID</span>
        <span>DUP</span>
        <span>IRRELEVANT</span>
        <span>SEEN</span>
        <span>USED</span>
      </div>
      {rows.map((item) => (
        <div
          key={item.label}
          className="grid grid-cols-[72px_repeat(6,minmax(58px,1fr))] items-center gap-1.5 rounded-md bg-gray-50 px-2 py-2"
        >
          <span className="truncate text-xs font-medium text-gray-600">
            {item.label}
          </span>
          <MetricBar value={item.fetched_count} max={maxValue} className="bg-gray-400" />
          <MetricBar value={item.invalid_filtered_count} max={maxValue} className="bg-red-400" />
          <MetricBar value={item.duplicate_filtered_count} max={maxValue} className="bg-amber-500" />
          <MetricBar value={item.title_filtered_count} max={maxValue} className="bg-blue-400" />
          <MetricBar value={item.seen_filtered_count} max={maxValue} className="bg-violet-500" />
          <MetricBar value={item.used_count} max={maxValue} className="bg-emerald-500" />
        </div>
      ))}
      <div className="grid grid-cols-[72px_repeat(6,minmax(58px,1fr))] gap-1.5 border-t pt-2 text-[10px] font-medium text-gray-500">
        <span>Total</span>
        <span>{totals.fetched}</span>
        <span>{totals.invalid}</span>
        <span>{totals.duplicate}</span>
        <span>{totals.title}</span>
        <span>{totals.seen}</span>
        <span>{totals.used}</span>
      </div>
      <div className="grid grid-cols-[72px_repeat(6,minmax(58px,1fr))] gap-1.5 text-[10px] text-gray-400">
        <span className="font-normal">%</span>
        <span className="font-normal">{"\u2014"}</span>
        <span className="font-normal">{percentages.invalid}%</span>
        <span className="font-normal">{percentages.duplicate}%</span>
        <span className="font-normal">{percentages.title}%</span>
        <span className="font-normal">{percentages.seen}%</span>
        <span className="font-normal">{percentages.used}%</span>
      </div>
    </div>
  );
}

function MetricBar({
  value,
  max,
  className,
}: {
  value: number;
  max: number;
  className: string;
}) {
  const pct = max === 0 ? 0 : (value / max) * 100;
  const width = pct === 0 ? 0 : Math.max(8, pct);
  return (
    <div className="flex items-center gap-1">
      <div className="h-2 flex-1 rounded-full bg-white">
        <div
          className={`h-full rounded-full ${className}`}
          style={{ width: `${width}%` }}
        />
      </div>
      <span className="w-5 text-right text-xs tabular-nums text-gray-500">
        {value}
      </span>
    </div>
  );
}
