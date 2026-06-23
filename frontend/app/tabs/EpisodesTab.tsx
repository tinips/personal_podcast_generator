"use client";

import { useState } from "react";
import { Episode, ArticleSource } from "../types";
import { statusLabel, trackEpisodeEvent } from "../utils";
import LoadingSpinner from "../components/LoadingSpinner";
import AudioPlayer from "../components/AudioPlayer";
import ErrorAlert from "../components/ErrorAlert";

type Props = {
  episodes: Episode[];
  episodesLoading: boolean;
  deletingEpisode: string | null;
  handleDeleteEpisode: (id: string) => Promise<void>;
};

export default function EpisodesTab({
  episodes,
  episodesLoading,
  deletingEpisode,
  handleDeleteEpisode,
}: Props) {
  const [trackedSources, setTrackedSources] = useState<Set<string>>(
    () => new Set()
  );
  const [trackedScripts, setTrackedScripts] = useState<Set<string>>(
    () => new Set()
  );
  const [actionError, setActionError] = useState<string | null>(null);

  const trackOnce = (
    episodeId: string,
    eventType: "sources_opened" | "script_opened",
  ) => {
    const tracked = eventType === "sources_opened" ? trackedSources : trackedScripts;
    if (tracked.has(episodeId)) return;
    if (eventType === "sources_opened") {
      setTrackedSources((current) => new Set(current).add(episodeId));
    } else {
      setTrackedScripts((current) => new Set(current).add(episodeId));
    }
    void trackEpisodeEvent(episodeId, eventType);
  };

  const deleteEpisode = async (episode: Episode) => {
    if (!window.confirm("Delete this episode?")) return;
    setActionError(null);
    try {
      await handleDeleteEpisode(episode.id);
    } catch (error: unknown) {
      setActionError(
        error instanceof Error ? error.message : "Failed to delete episode"
      );
    }
  };

  return (
    <section className="space-y-4">
      {actionError && <ErrorAlert message={actionError} />}
      {episodesLoading && <LoadingSpinner />}
      {!episodesLoading && episodes.length === 0 && (
        <div className="rounded-lg border bg-white p-12 text-center text-gray-400">
          No episodes yet. Go to Generate to create one.
        </div>
      )}
      {episodes.map((ep) => (
        <div key={ep.id} className="rounded-lg border bg-white p-6 shadow-sm">
          <div className="mb-2 flex items-start justify-between gap-4">
            <div>
              <h3 className="text-lg font-semibold">{ep.title}</h3>
              <p className="mt-1 text-sm text-gray-500">{ep.summary}</p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <span
                className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                  ep.success
                    ? "bg-green-100 text-green-700"
                    : "bg-red-100 text-red-700"
                }`}
              >
                {statusLabel(ep.status, ep.success)}
              </span>
              <button
                type="button"
                onClick={() => deleteEpisode(ep)}
                disabled={deletingEpisode === ep.id}
                className="rounded-md border border-red-200 px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {deletingEpisode === ep.id ? "Deleting..." : "Delete"}
              </button>
            </div>
          </div>
          <div className="mb-3 flex flex-wrap gap-2 text-xs text-gray-500">
            {ep.interests.length > 0 && (
              <span>Topics: {ep.interests.join(", ")}</span>
            )}
            <span>Tone: {ep.tone}</span>
            <span>Duration: {ep.duration}</span>
            <span>Format: {ep.speaker_mode}</span>
            <span>{new Date(ep.created_at).toLocaleDateString()}</span>
            {ep.generation_time_ms && (
              <span>{(ep.generation_time_ms / 1000).toFixed(1)}s</span>
            )}
          </div>
          {ep.articles.length > 0 && (
            <div className="mb-3">
              <p className="mb-2 text-xs font-medium text-gray-500">
                Articles used ({ep.articles.length})
              </p>
              <ul className="space-y-2">
                {ep.articles.map((article: ArticleSource, i) => (
                  <li
                    key={i}
                    className="rounded-md border border-gray-100 bg-gray-50 px-3 py-2 text-xs text-gray-600"
                  >
                    {article.url ? (
                      <a
                        href={article.url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-blue-600 hover:underline"
                        onClick={() => trackOnce(ep.id, "sources_opened")}
                      >
                        {article.title}
                      </a>
                    ) : (
                      article.title
                    )}
                    {article.source && ` - ${article.source}`}
                    {article.provider && ` via ${article.provider}`}
                    {article.topic && ` [${article.topic}]`}
                    {article.published_at &&
                      ` (${new Date(article.published_at).toLocaleDateString()})`}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {ep.error_message && (
            <p className="mb-3 rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-700">
              {ep.error_message}
            </p>
          )}
          {ep.script && (
            <details
              className="mb-3 rounded-md border border-gray-100 bg-gray-50 px-3 py-2"
              onToggle={(event) => {
                if (event.currentTarget.open) {
                  trackOnce(ep.id, "script_opened");
                }
              }}
            >
              <summary className="cursor-pointer text-xs font-medium text-gray-600">
                Script
              </summary>
              <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap text-xs leading-5 text-gray-700">
                {ep.script}
              </pre>
            </details>
          )}
          <AudioPlayer audioUrl={ep.audio_url} episodeId={ep.id} />
        </div>
      ))}
    </section>
  );
}
