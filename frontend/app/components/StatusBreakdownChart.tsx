import EmptyChart from "./EmptyChart";

export default function StatusBreakdownChart({
  data,
  xAxisLabel,
  yAxisLabel,
}: {
  data: { status: string; count: number }[];
  xAxisLabel?: string;
  yAxisLabel?: string;
}) {
  const total = data.reduce((sum, item) => sum + item.count, 0);
  const colors: Record<string, string> = {
    completed: "bg-emerald-500",
    failed: "bg-rose-500",
    skipped: "bg-amber-500",
  };
  const labels: Record<string, string> = {
    completed: "Successful",
    failed: "Technical Failure",
    skipped: "No Fresh News",
  };

  if (total === 0) {
    return <EmptyChart />;
  }

  return (
    <div className="space-y-4">
      {(xAxisLabel || yAxisLabel) && (
        <div className="flex items-center justify-between gap-3 text-[10px] font-medium uppercase text-gray-400">
          <span>{yAxisLabel}</span>
          <span>{xAxisLabel}</span>
        </div>
      )}
      <div className="flex h-5 overflow-hidden rounded-full bg-gray-100">
        {data.map((item) => (
          <div
            key={item.status}
            className={colors[item.status] || "bg-gray-400"}
            style={{ width: `${(item.count / total) * 100}%` }}
            title={`${item.status}: ${item.count}`}
          />
        ))}
      </div>
      <div className="grid gap-2 sm:grid-cols-3">
        {data.map((item) => (
          <div key={item.status} className="rounded-md bg-gray-50 p-3">
            <div className="flex items-center gap-2">
              <span className={`h-2.5 w-2.5 rounded-full ${colors[item.status] || "bg-gray-400"}`} />
              <span className="text-xs font-medium text-gray-600">
                {labels[item.status] || item.status}
              </span>
            </div>
            <p className="mt-1 text-xl font-semibold text-gray-950">{item.count}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
