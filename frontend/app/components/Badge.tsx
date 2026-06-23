export default function Badge({
  children,
  tone,
}: {
  children: React.ReactNode;
  tone: "green" | "red" | "amber" | "blue" | "purple" | "gray";
}) {
  const classes = {
    green: "bg-emerald-100 text-emerald-700",
    red: "bg-rose-100 text-rose-700",
    amber: "bg-amber-100 text-amber-700",
    blue: "bg-blue-100 text-blue-700",
    purple: "bg-violet-100 text-violet-700",
    gray: "bg-gray-100 text-gray-600",
  };

  return (
    <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${classes[tone]}`}>
      {children}
    </span>
  );
}
