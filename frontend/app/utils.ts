export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export function getUserId(): string {
  if (typeof window === "undefined") return "";
  let id = localStorage.getItem("podcast_user_id");
  if (!id) {
    id = "user_" + Math.random().toString(36).slice(2, 14);
    localStorage.setItem("podcast_user_id", id);
  }
  return id;
}

export function loadPreference<T>(key: string, fallback: T): T {
  if (typeof window === "undefined") return fallback;
  try {
    const raw = localStorage.getItem(`podcast_pref_${key}`);
    if (raw === null) return fallback;
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

export function savePreference(key: string, value: unknown): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(`podcast_pref_${key}`, JSON.stringify(value));
  } catch {
    // localStorage full or unavailable — ignore
  }
}

export function statusLabel(status: string, success: boolean): string {
  if (status === "audio_failed" || !success) return "Failed";
  return "Success";
}

export function formatSeconds(value: number | null): string {
  return value == null ? "N/A" : `${value.toFixed(1)}s`;
}

export function formatCost(value: number): string {
  return `$${value.toFixed(value >= 1 ? 2 : 4)}`;
}

export async function trackEpisodeEvent(
  episodeId: string,
  eventType: string,
  value?: number
): Promise<void> {
  try {
    await fetch(`${API_BASE}/api/episodes/${episodeId}/events`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ event_type: eventType, value: value ?? null }),
    });
  } catch {
    // Monitoring should never break playback UX.
  }
}
