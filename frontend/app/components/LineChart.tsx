import EmptyChart from "./EmptyChart";

export default function LineChart({
  data,
  valueKey,
  valueFormatter = (value: number) => String(value),
  stroke = "#2563eb",
  xAxisLabel,
  yAxisLabel,
}: {
  data: Record<string, string | number | null>[];
  valueKey: string;
  valueFormatter?: (value: number) => string;
  stroke?: string;
  xAxisLabel?: string;
  yAxisLabel?: string;
}) {
  const points = data
    .map((item) => ({
      label: String(item.label || item.date || ""),
      dateLabel: compactDateLabel(String(item.date || item.label || "")),
      value: Number(item[valueKey]),
    }))
    .filter((item) => Number.isFinite(item.value));

  if (points.length === 0) {
    return <EmptyChart />;
  }

  const width = 420;
  const height = 200;
  const padX = 28;
  const padTop = 18;
  const padBottom = 36;
  const maxValue = Math.max(1, ...points.map((point) => point.value));
  const chartWidth = width - padX * 2;
  const chartHeight = height - padTop - padBottom;
  const coords = points.map((point, index) => {
    const x =
      points.length === 1
        ? width / 2
        : padX + (index / (points.length - 1)) * chartWidth;
    const y = height - padBottom - (point.value / maxValue) * chartHeight;
    return { ...point, x, y };
  });
  const tickStep = Math.max(1, Math.ceil(coords.length / 6));
  const path = coords
    .map((point, index) => `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`)
    .join(" ");

  return (
    <div>
      {yAxisLabel && (
        <div className="mb-2 flex items-center justify-between gap-3 text-[10px] font-medium text-gray-400">
          <span>{yAxisLabel}</span>
        </div>
      )}
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="h-44 w-full overflow-visible"
        role="img"
      >
        <line x1={padX} x2={width - padX} y1={height - padBottom} y2={height - padBottom} stroke="#e5e7eb" />
        <line x1={padX} x2={padX} y1={padTop} y2={height - padBottom} stroke="#e5e7eb" />
        <path d={path} fill="none" stroke={stroke} strokeWidth="3" strokeLinecap="round" />
        {coords.map((point, index) => (
          <g key={`${point.label}-${point.x}`}>
            <circle cx={point.x} cy={point.y} r="4" fill="white" stroke={stroke} strokeWidth="2" />
            <text x={point.x} y={point.y - 9} textAnchor="middle" className="fill-gray-500 text-[10px]">
              {valueFormatter(point.value)}
            </text>
            {(index % tickStep === 0 || index === coords.length - 1) && (
              <>
                <line x1={point.x} x2={point.x} y1={height - padBottom} y2={height - padBottom + 4} stroke="#d1d5db" />
                <text x={point.x} y={height - 14} textAnchor="middle" className="fill-gray-400 text-[10px]">
                  {point.dateLabel}
                </text>
              </>
            )}
          </g>
        ))}
      </svg>
      <div className="mt-1 flex justify-center text-[10px] font-medium text-gray-400">
        {xAxisLabel || "Date"}
      </div>
    </div>
  );
}

function compactDateLabel(value: string): string {
  const isoMatch = value.match(/\d{4}-(\d{2})-(\d{2})/);
  if (isoMatch) return `${isoMatch[1]}-${isoMatch[2]}`;

  const compactMatch = value.match(/(\d{2})-(\d{2})/);
  if (compactMatch) return `${compactMatch[1]}-${compactMatch[2]}`;

  const date = new Date(value);
  if (Number.isFinite(date.getTime())) {
    return `${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
  }

  return value || "-";
}
