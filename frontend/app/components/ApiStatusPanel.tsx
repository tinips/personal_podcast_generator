"use client";

import { useEffect, useState } from "react";

type ApiStatusEntry = {
  available: boolean;
  status: string;
};

type ApiStatus = Record<string, ApiStatusEntry>;

const API_NAMES: Record<string, string> = {
  news: "NewsAPI.ai",
  openai: "OpenAI",
  elevenlabs: "ElevenLabs",
};

export default function ApiStatusPanel() {
  const [status, setStatus] = useState<ApiStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function fetchStatus() {
      try {
        const res = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000"}/api/health`
        );
        if (!res.ok) throw new Error("Health check failed");
        const data = await res.json();
        if (!cancelled) {
          setStatus(data);
          setError(false);
        }
      } catch {
        if (!cancelled) setError(true);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    fetchStatus();
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) {
    return (
      <div className="rounded-lg border border-blue-100 bg-white p-5 shadow-sm">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="h-3 w-20 animate-pulse rounded bg-gray-200" />
            <div className="mt-3 h-6 w-44 animate-pulse rounded bg-gray-100" />
          </div>
          <div className="h-10 w-10 animate-pulse rounded-md bg-blue-50" />
        </div>
        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-20 animate-pulse rounded-md bg-gray-50" />
          ))}
        </div>
      </div>
    );
  }

  if (error || !status) {
    return (
      <div className="rounded-lg border border-red-200 bg-white p-5 shadow-sm">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-red-500">
              API Status
            </p>
            <h3 className="mt-1 text-xl font-semibold text-gray-950">
              Provider check unavailable
            </h3>
            <p className="mt-1 text-sm text-gray-500">
              The dashboard could not reach the backend health endpoint.
            </p>
          </div>
          <span className="inline-flex items-center gap-2 rounded-md bg-red-50 px-3 py-2 text-sm font-semibold text-red-700">
            <span className="h-2.5 w-2.5 rounded-full bg-red-500" />
            Check failed
          </span>
        </div>
      </div>
    );
  }

  const upCount = Object.values(status).filter((s) => s.available).length;
  const total = Object.keys(status).length;
  const allAvailable = upCount === total;
  const summaryTone = allAvailable
    ? "border-emerald-200 bg-emerald-50 text-emerald-700"
    : "border-amber-200 bg-amber-50 text-amber-700";

  return (
    <div className="rounded-lg border border-blue-100 bg-white p-5 shadow-sm">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-blue-600">
            API Status
          </p>
          <div className="mt-1 flex flex-wrap items-center gap-3">
            <h3 className="text-xl font-semibold text-gray-950">
              Provider readiness
            </h3>
            <span
              className={`inline-flex items-center gap-2 rounded-md border px-3 py-1.5 text-sm font-semibold ${summaryTone}`}
            >
              <span
                className={`h-2.5 w-2.5 rounded-full ${
                  allAvailable ? "bg-emerald-500" : "bg-amber-500"
                }`}
              />
              {upCount}/{total} available
            </span>
          </div>
          <p className="mt-2 text-sm text-gray-500">
            News, script generation, and audio synthesis dependencies.
          </p>
        </div>
        <div className="grid gap-3 sm:grid-cols-3 lg:min-w-[520px]">
          {Object.entries(status).map(([key, entry]) => (
            <div
              key={key}
              className={`rounded-md border px-4 py-3 ${
                entry.available
                  ? "border-emerald-200 bg-emerald-50"
                  : "border-red-200 bg-red-50"
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <p className="text-sm font-semibold text-gray-900">
                  {API_NAMES[key] || key}
                </p>
                <span
                  className={`h-2.5 w-2.5 rounded-full ${
                    entry.available ? "bg-emerald-500" : "bg-red-500"
                  }`}
                />
              </div>
              <p
                className={`mt-2 text-xs font-medium ${
                  entry.available ? "text-emerald-700" : "text-red-700"
                }`}
              >
                {entry.available ? "Available" : "Unavailable"}
              </p>
              <p className="mt-1 truncate text-xs text-gray-500">
                {entry.status || "No status detail"}
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
