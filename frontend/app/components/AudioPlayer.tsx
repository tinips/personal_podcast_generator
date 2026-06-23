"use client";

import { useRef } from "react";
import { API_BASE, trackEpisodeEvent } from "../utils";

export default function AudioPlayer({
  audioUrl,
  episodeId,
}: {
  audioUrl: string | null;
  episodeId?: string;
}) {
  const playedTracked = useRef(false);

  if (!audioUrl) {
    return (
      <p className="text-sm text-gray-400 italic">
        No audio available for this episode.
      </p>
    );
  }
  const src = `${API_BASE}/audio/${audioUrl}`;
  return (
    <audio
      key={src}
      controls
      className="w-full"
      preload="metadata"
      onPlay={() => {
        if (!episodeId || playedTracked.current) return;
        playedTracked.current = true;
        void trackEpisodeEvent(episodeId, "audio_played");
      }}
      onEnded={() => {
        if (!episodeId) return;
        void trackEpisodeEvent(episodeId, "audio_completed");
      }}
    >
      <source src={src} type="audio/mpeg" />
    </audio>
  );
}
