import EmptyChart from "./EmptyChart";

export default function HorizontalBarChart({
  data,
  labelKey,
  valueKey,
  valueFormatter = (value: number) => String(value),
  barClassName = "bg-blue-600",
  xAxisLabel,
  yAxisLabel,
}: {
  data: Record<string, string | number>[];
  labelKey: string;
  valueKey: string;
  valueFormatter?: (value: number) => string;
  barClassName?: string;
  xAxisLabel?: string;
  yAxisLabel?: string;
}) {
  const max = Math.max(
    1,
    ...data.map((item) => Number(item[valueKey]) || 0)
  );

  if (data.length === 0) {
    return <EmptyChart />;
  }

  return (
    <div className="space-y-3">
      {(xAxisLabel || yAxisLabel) && (
        <div className="flex items-center justify-between gap-3 text-[10px] font-medium uppercase text-gray-400">
          <span>{yAxisLabel}</span>
          <span>{xAxisLabel}</span>
        </div>
      )}
      {data.map((item) => {
        const value = Number(item[valueKey]) || 0;
        const width = value > 0 ? Math.max(4, (value / max) * 100) : 0;
        return (
          <div key={String(item[labelKey])} className="space-y-1">
            <div className="flex items-center justify-between gap-3 text-xs">
              <span className="truncate font-medium text-gray-700">
                {String(item[labelKey])}
              </span>
              <span className="shrink-0 tabular-nums text-gray-500">
                {valueFormatter(value)}
              </span>
            </div>
            <div className="h-2.5 overflow-hidden rounded-full bg-gray-100">
              <div
                className={`h-full rounded-full ${barClassName}`}
                style={{ width: `${width}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
