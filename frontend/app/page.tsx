"use client";

import { useState, useEffect, useCallback } from "react";
import {
  type Episode,
  type Schedule,
  type ScheduleRequest,
  type DashboardMetrics,
  DURATION_CONFIG,
} from "./types";
import { API_BASE, getUserId, loadPreference, savePreference } from "./utils";
import TabButton from "./components/TabButton";
import GenerateTab from "./tabs/GenerateTab";
import EpisodesTab from "./tabs/EpisodesTab";
import SchedulesTab from "./tabs/SchedulesTab";
import DashboardTab from "./tabs/DashboardTab";

export default function Home() {
  const [userId, setUserId] = useState("");
  const [preferencesLoaded, setPreferencesLoaded] = useState(false);
  const [tab, setTab] = useState<"generate" | "episodes" | "dashboard" | "schedules">(
    "generate"
  );
  const [interestInput, setInterestInput] = useState("");
  const [savedInterests, setSavedInterests] = useState<string[]>([]);
  const [selectedTopics, setSelectedTopics] = useState<string[]>([]);
  const [tone, setTone] = useState("professional");
  const [duration, setDuration] = useState("normal");
  const [frequency, setFrequency] = useState("manual");
  const [speakerMode, setSpeakerMode] = useState("solo");
  const [generating, setGenerating] = useState(false);
  const [genError, setGenError] = useState<string | null>(null);
  const [lastEpisode, setLastEpisode] = useState<Episode | null>(null);
  const [episodes, setEpisodes] = useState<Episode[]>([]);
  const [episodesLoading, setEpisodesLoading] = useState(false);
  const [deletingEpisode, setDeletingEpisode] = useState<string | null>(null);
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);
  const [metricsLoading, setMetricsLoading] = useState(false);

  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [schedulesLoading, setSchedulesLoading] = useState(false);
  const [scheduleNameToSave, setScheduleNameToSave] = useState("");
  const [savingSchedule, setSavingSchedule] = useState(false);
  const [scheduleSaveError, setScheduleSaveError] = useState<string | null>(null);
  const [scheduleSaveSuccess, setScheduleSaveSuccess] = useState<string | null>(null);
  const [runningSchedule, setRunningSchedule] = useState<string | null>(null);
  const [deletingSchedule, setDeletingSchedule] = useState<string | null>(null);

  const topicLimit = DURATION_CONFIG[duration]?.maxTopics ?? 2;
  const topicError =
    selectedTopics.length > topicLimit
      ? `A ${duration} podcast supports up to ${topicLimit} topic(s). Select fewer topics or choose a longer duration.`
      : null;

  const fetchEpisodes = useCallback(async () => {
    setEpisodesLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/episodes`);
      if (res.ok) setEpisodes(await res.json());
    } catch {
      // ignore
    } finally {
      setEpisodesLoading(false);
    }
  }, []);

  const fetchMetrics = useCallback(async () => {
    setMetricsLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/dashboard/metrics`);
      if (res.ok) setMetrics(await res.json());
    } catch {
      // ignore
    } finally {
      setMetricsLoading(false);
    }
  }, []);

  const fetchSchedules = useCallback(async () => {
    if (!userId) return;
    setSchedulesLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/schedules?user_id=${encodeURIComponent(userId)}`);
      if (res.ok) setSchedules(await res.json());
    } catch {
      // ignore
    } finally {
      setSchedulesLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    setUserId(getUserId());
    setSavedInterests(loadPreference<string[]>("interests", []));
    setSelectedTopics(loadPreference<string[]>("topics", []));
    setTone(loadPreference<string>("tone", "professional"));
    setDuration(loadPreference<string>("duration", "normal"));
    setFrequency(loadPreference<string>("frequency", "manual"));
    setSpeakerMode(loadPreference<string>("speakerMode", "solo"));
    setPreferencesLoaded(true);
  }, []);

  useEffect(() => {
    if (tab === "episodes") fetchEpisodes();
    if (tab === "dashboard") fetchMetrics();
    if (tab === "schedules") fetchSchedules();
  }, [tab, fetchEpisodes, fetchMetrics, fetchSchedules]);

  useEffect(() => {
    if (!preferencesLoaded) return;
    savePreference("interests", savedInterests);
  }, [preferencesLoaded, savedInterests]);
  useEffect(() => {
    if (!preferencesLoaded) return;
    savePreference("topics", selectedTopics);
  }, [preferencesLoaded, selectedTopics]);
  useEffect(() => {
    if (!preferencesLoaded) return;
    savePreference("tone", tone);
  }, [preferencesLoaded, tone]);
  useEffect(() => {
    if (!preferencesLoaded) return;
    savePreference("duration", duration);
  }, [preferencesLoaded, duration]);
  useEffect(() => {
    if (!preferencesLoaded) return;
    savePreference("frequency", frequency);
  }, [frequency, preferencesLoaded]);
  useEffect(() => {
    if (!preferencesLoaded) return;
    savePreference("speakerMode", speakerMode);
  }, [preferencesLoaded, speakerMode]);

  const handleAddInterests = () => {
    const topics = interestInput
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    if (topics.length === 0) {
      setGenError("Please enter at least one interest.");
      return;
    }
    setSavedInterests((current) => {
      const seen = new Set(current.map((t) => t.toLowerCase()));
      const next = [...current];
      for (const topic of topics) {
        const key = topic.toLowerCase();
        if (!seen.has(key)) {
          next.push(topic);
          seen.add(key);
        }
      }
      return next;
    });
    setInterestInput("");
    setGenError(null);
  };

  const toggleTopic = (topic: string) => {
    setSelectedTopics((current) =>
      current.includes(topic)
        ? current.filter((t) => t !== topic)
        : [...current, topic]
    );
  };

  const removeSavedInterest = (topic: string) => {
    if (!window.confirm("Remove this interest from your saved interests?")) return;
    setSavedInterests((current) => current.filter((t) => t !== topic));
    setSelectedTopics((current) => current.filter((t) => t !== topic));
    setGenError(null);
    setScheduleSaveError(null);
  };

  const handleGenerate = async () => {
    if (selectedTopics.length === 0) {
      setGenError("Please select at least one topic.");
      return;
    }
    if (topicError) {
      setGenError(topicError);
      return;
    }
    setGenerating(true);
    setGenError(null);
    setLastEpisode(null);
    try {
      const res = await fetch(`${API_BASE}/api/podcast/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          selected_interests: selectedTopics,
          tone,
          duration,
          frequency,
          user_id: userId,
          speaker_mode: speakerMode,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Generation failed" }));
        const detail =
          typeof err.detail === "string"
            ? err.detail
            : err.detail?.message || "Generation failed";
        throw new Error(detail);
      }
      const data = await res.json();
      if (!data.episode?.success) {
        throw new Error(data.episode?.error_message || "Generation failed");
      }
      setLastEpisode(data.episode);
      setTab("episodes");
      fetchEpisodes();
    } catch (e: unknown) {
      setGenError(e instanceof Error ? e.message : "Generation failed");
    } finally {
      setGenerating(false);
    }
  };

  const handleSaveCurrentSchedule = async () => {
    if (frequency === "manual") {
      setScheduleSaveError("Choose Daily or Weekly to save a schedule.");
      return;
    }
    if (selectedTopics.length === 0) {
      setScheduleSaveError("Please select at least one topic.");
      return;
    }
    if (topicError) {
      setScheduleSaveError(topicError);
      return;
    }
    if (!scheduleNameToSave.trim()) {
      setScheduleSaveError("Please enter a schedule name.");
      return;
    }
    setSavingSchedule(true);
    setScheduleSaveError(null);
    setScheduleSaveSuccess(null);
    try {
      const res = await fetch(`${API_BASE}/api/schedules`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: userId,
          name: scheduleNameToSave.trim(),
          selected_interests: selectedTopics,
          frequency,
          duration,
          tone,
          speaker_mode: speakerMode,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Failed to save schedule" }));
        throw new Error(typeof err.detail === "string" ? err.detail : "Failed to save schedule");
      }
      const schedule = (await res.json()) as Schedule;
      setSchedules((current) => [
        schedule,
        ...current.filter((item) => item.id !== schedule.id),
      ]);
      setScheduleNameToSave("");
      setScheduleSaveSuccess("Schedule saved.");
      fetchSchedules();
    } catch (e: unknown) {
      setScheduleSaveError(e instanceof Error ? e.message : "Failed to save schedule");
    } finally {
      setSavingSchedule(false);
    }
  };

  const handleUpdateSchedule = async (
    scheduleId: string,
    payload: ScheduleRequest
  ) => {
    const res = await fetch(`${API_BASE}/api/schedules/${scheduleId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Failed to update schedule" }));
      throw new Error(typeof err.detail === "string" ? err.detail : "Failed to update schedule");
    }
    const updated = (await res.json()) as Schedule;
    setSchedules((current) =>
      current.map((schedule) => (schedule.id === updated.id ? updated : schedule))
    );
    fetchSchedules();
  };

  const handleDeleteSchedule = async (scheduleId: string) => {
    setDeletingSchedule(scheduleId);
    try {
      const res = await fetch(`${API_BASE}/api/schedules/${scheduleId}`, {
        method: "DELETE",
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Failed to delete schedule" }));
        throw new Error(typeof err.detail === "string" ? err.detail : "Failed to delete schedule");
      }
      setSchedules((current) =>
        current.filter((schedule) => schedule.id !== scheduleId)
      );
      fetchSchedules();
    } finally {
      setDeletingSchedule(null);
    }
  };

  const handleDeleteEpisode = async (episodeId: string) => {
    setDeletingEpisode(episodeId);
    try {
      const res = await fetch(`${API_BASE}/api/episodes/${episodeId}`, {
        method: "DELETE",
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Failed to delete episode" }));
        throw new Error(typeof err.detail === "string" ? err.detail : "Failed to delete episode");
      }
      setEpisodes((current) =>
        current.filter((episode) => episode.id !== episodeId)
      );
      setLastEpisode((current) =>
        current?.id === episodeId ? null : current
      );
      fetchMetrics();
    } finally {
      setDeletingEpisode(null);
    }
  };

  const handleRunSchedule = async (scheduleId: string) => {
    setRunningSchedule(scheduleId);
    try {
      await fetch(
        `${API_BASE}/api/scheduler/run?user_id=${encodeURIComponent(userId)}&schedule_id=${scheduleId}`,
        { method: "POST" }
      );
      fetchSchedules();
      fetchEpisodes();
    } catch {
      // ignore
    } finally {
      setRunningSchedule(null);
    }
  };

  const handleRunAllSchedules = async () => {
    setRunningSchedule("__all__");
    try {
      await fetch(
        `${API_BASE}/api/scheduler/run?user_id=${encodeURIComponent(userId)}`,
        { method: "POST" }
      );
      fetchSchedules();
      fetchEpisodes();
    } catch {
      // ignore
    } finally {
      setRunningSchedule(null);
    }
  };

  return (
    <main className="mx-auto max-w-6xl px-4 py-8">
      <header className="mb-8 text-center">
        <h1 className="text-4xl font-bold">Neural Notes</h1>
        <p className="mt-2 text-gray-600">
          Generate personalized AI podcasts from your interests.
        </p>
      </header>

      <nav className="mb-8 flex border-b border-gray-200">
        <TabButton active={tab === "generate"} onClick={() => setTab("generate")}>
          Generate
        </TabButton>
        <TabButton active={tab === "episodes"} onClick={() => setTab("episodes")}>
          Episodes
        </TabButton>
        <TabButton active={tab === "schedules"} onClick={() => setTab("schedules")}>
          Schedules
        </TabButton>
        <TabButton active={tab === "dashboard"} onClick={() => setTab("dashboard")}>
          Monitoring
        </TabButton>
      </nav>

      {tab === "generate" && (
        <GenerateTab
          interestInput={interestInput}
          setInterestInput={setInterestInput}
          savedInterests={savedInterests}
          selectedTopics={selectedTopics}
          toggleTopic={toggleTopic}
          removeSavedInterest={removeSavedInterest}
          tone={tone}
          setTone={setTone}
          duration={duration}
          setDuration={(v) => {
            setDuration(v);
            const limit = DURATION_CONFIG[v]?.maxTopics ?? 2;
            setSelectedTopics((current) => current.slice(0, limit));
          }}
          speakerMode={speakerMode}
          setSpeakerMode={setSpeakerMode}
          frequency={frequency}
          setFrequency={setFrequency}
          generating={generating}
          genError={genError}
          handleAddInterests={handleAddInterests}
          handleGenerate={handleGenerate}
          scheduleNameToSave={scheduleNameToSave}
          setScheduleNameToSave={(value) => {
            setScheduleNameToSave(value);
            setScheduleSaveSuccess(null);
          }}
          savingSchedule={savingSchedule}
          scheduleSaveError={scheduleSaveError}
          scheduleSaveSuccess={scheduleSaveSuccess}
          handleSaveCurrentSchedule={handleSaveCurrentSchedule}
          topicLimit={topicLimit}
          topicError={topicError}
          lastEpisode={lastEpisode}
        />
      )}

      {tab === "episodes" && (
        <EpisodesTab
          episodes={episodes}
          episodesLoading={episodesLoading}
          deletingEpisode={deletingEpisode}
          handleDeleteEpisode={handleDeleteEpisode}
        />
      )}

      {tab === "schedules" && (
        <SchedulesTab
          schedules={schedules}
          schedulesLoading={schedulesLoading}
          runningSchedule={runningSchedule}
          deletingSchedule={deletingSchedule}
          handleRunSchedule={handleRunSchedule}
          handleRunAllSchedules={handleRunAllSchedules}
          handleUpdateSchedule={handleUpdateSchedule}
          handleDeleteSchedule={handleDeleteSchedule}
          savedInterests={savedInterests}
          userId={userId}
        />
      )}

      {tab === "dashboard" && (
        <DashboardTab
          metrics={metrics}
          metricsLoading={metricsLoading}
        />
      )}
    </main>
  );
}
