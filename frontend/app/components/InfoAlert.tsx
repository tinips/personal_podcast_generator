export default function InfoAlert({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-amber-700">
      {message}
    </div>
  );
}
