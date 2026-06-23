export default function EmptyChart({ label = "No data yet" }: { label?: string }) {
  return (
    <div className="flex h-44 items-center justify-center rounded-md border border-dashed border-gray-200 bg-gray-50 text-sm text-gray-400">
      {label}
    </div>
  );
}
