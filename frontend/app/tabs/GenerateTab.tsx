import {
  DURATION_CONFIG,
  TONES,
  FREQUENCIES,
  SPEAKER_MODES,
  Episode,
} from "../types";
import LoadingSpinner from "../components/LoadingSpinner";
import ErrorAlert from "../components/ErrorAlert";

type Props = {
  interestInput: string;
  setInterestInput: (v: string) => void;
  savedInterests: string[];
  selectedTopics: string[];
  toggleTopic: (t: string) => void;
  removeSavedInterest: (t: string) => void;
  tone: string;
  setTone: (v: string) => void;
  duration: string;
  setDuration: (v: string) => void;
  speakerMode: string;
  setSpeakerMode: (v: string) => void;
  frequency: string;
  setFrequency: (v: string) => void;
  generating: boolean;
  genError: string | null;
  handleAddInterests: () => void;
  handleGenerate: () => void;
  scheduleNameToSave: string;
  setScheduleNameToSave: (v: string) => void;
  savingSchedule: boolean;
  scheduleSaveError: string | null;
  scheduleSaveSuccess: string | null;
  handleSaveCurrentSchedule: () => void;
  topicLimit: number;
  topicError: string | null;
  lastEpisode: Episode | null;
};

export default function GenerateTab(props: Props) {
  const {
    interestInput,
    setInterestInput,
    savedInterests,
    selectedTopics,
    toggleTopic,
    removeSavedInterest,
    tone,
    setTone,
    duration,
    setDuration,
    speakerMode,
    setSpeakerMode,
    frequency,
    setFrequency,
    generating,
    genError,
    handleAddInterests,
    handleGenerate,
    scheduleNameToSave,
    setScheduleNameToSave,
    savingSchedule,
    scheduleSaveError,
    scheduleSaveSuccess,
    handleSaveCurrentSchedule,
    topicLimit,
    topicError,
    lastEpisode,
  } = props;

  const saveScheduleDisabled =
    savingSchedule ||
    frequency === "manual" ||
    selectedTopics.length === 0 ||
    !!topicError ||
    scheduleNameToSave.trim().length === 0;

  return (
    <section className="space-y-6">
      <div className="rounded-lg border bg-white p-6 shadow-sm">
        <label className="mb-2 block text-sm font-medium text-gray-700">
          Saved Interests
        </label>
        <div className="flex gap-2">
          <input
            type="text"
            value={interestInput}
            onChange={(e) => setInterestInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleAddInterests();
            }}
            placeholder="e.g. AI, startups, sports"
            className="min-w-0 flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          />
          <button
            type="button"
            onClick={handleAddInterests}
            className="shrink-0 rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800"
          >
            Add interests
          </button>
        </div>
        {savedInterests.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-2">
            {savedInterests.map((topic) => {
              const selected = selectedTopics.includes(topic);
              return (
                <span
                  key={topic.toLowerCase()}
                  className={`inline-flex items-center overflow-hidden rounded-full border text-sm font-medium transition-colors ${
                    selected
                      ? "border-blue-600 bg-blue-600 text-white"
                      : "border-gray-300 bg-white text-gray-700 hover:border-blue-300 hover:text-blue-700"
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => toggleTopic(topic)}
                    className="px-3 py-1.5"
                  >
                    {selected ? `\u2713 ${topic}` : topic}
                  </button>
                  <button
                    type="button"
                    aria-label={`Remove ${topic}`}
                    onClick={(e) => {
                      e.stopPropagation();
                      removeSavedInterest(topic);
                    }}
                    className={`border-l px-2 py-1.5 ${
                      selected
                        ? "border-blue-400 text-blue-50 hover:bg-blue-700"
                        : "border-gray-200 text-gray-500 hover:bg-gray-100 hover:text-gray-800"
                    }`}
                  >
                    {"\u00d7"}
                  </button>
                </span>
              );
            })}
          </div>
        )}
        {selectedTopics.length > 0 && (
          <p className="mt-2 text-xs text-gray-500">
            {selectedTopics.length} topic{selectedTopics.length > 1 ? "s" : ""} selected
            {topicLimit > 0 && ` (max ${topicLimit} for ${duration})`}
          </p>
        )}
        {topicError && (
          <p className="mt-2 text-xs text-red-600">{topicError}</p>
        )}
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <div className="rounded-lg border bg-white p-4 shadow-sm">
          <label className="mb-2 block text-sm font-medium text-gray-700">Tone</label>
          <select
            value={tone}
            onChange={(e) => setTone(e.target.value)}
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          >
            {TONES.map((t) => (
              <option key={t} value={t}>
                {t.charAt(0).toUpperCase() + t.slice(1)}
              </option>
            ))}
          </select>
        </div>
        <div className="rounded-lg border bg-white p-4 shadow-sm">
          <label className="mb-2 block text-sm font-medium text-gray-700">Duration</label>
          <select
            value={duration}
            onChange={(e) => setDuration(e.target.value)}
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          >
            {Object.entries(DURATION_CONFIG).map(([key, cfg]) => (
              <option key={key} value={key}>
                {cfg.label} - max {cfg.maxTopics} topic{cfg.maxTopics > 1 ? "s" : ""}
              </option>
            ))}
          </select>
        </div>
        <div className="rounded-lg border bg-white p-4 shadow-sm">
          <label className="mb-2 block text-sm font-medium text-gray-700">Format</label>
          <select
            value={speakerMode}
            onChange={(e) => setSpeakerMode(e.target.value)}
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          >
            {SPEAKER_MODES.map((m) => (
              <option key={m.value} value={m.value}>
                {m.label}
              </option>
            ))}
          </select>
          <p className="mt-2 text-xs text-gray-500">
            {speakerMode === "dialogue"
              ? "Dialogue mode uses John as the main host and Maya as the guest analyst."
              : "Solo mode uses John as the host."}
          </p>
        </div>
      </div>

      <div className="rounded-lg border bg-white p-4 shadow-sm">
        <label className="mb-2 block text-sm font-medium text-gray-700">Frequency</label>
        <select
          value={frequency}
          onChange={(e) => setFrequency(e.target.value)}
          className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
        >
          {FREQUENCIES.map((f) => (
            <option key={f} value={f}>
              {f.charAt(0).toUpperCase() + f.slice(1)}
            </option>
          ))}
        </select>
      </div>

      {frequency !== "manual" && (
        <div className="rounded-lg border bg-white p-4 shadow-sm">
          <label className="mb-2 block text-sm font-medium text-gray-700">
            Schedule name
          </label>
          <div className="flex flex-col gap-2 sm:flex-row">
            <input
              type="text"
              value={scheduleNameToSave}
              onChange={(e) => setScheduleNameToSave(e.target.value)}
              placeholder="e.g. Morning AI Briefing"
              className="min-w-0 flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
            />
            <button
              type="button"
              onClick={handleSaveCurrentSchedule}
              disabled={saveScheduleDisabled}
              className="shrink-0 rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {savingSchedule ? "Saving..." : "Save as Schedule"}
            </button>
          </div>
          {scheduleSaveError && (
            <div className="mt-3">
              <ErrorAlert message={scheduleSaveError} />
            </div>
          )}
          {scheduleSaveSuccess && (
            <p className="mt-3 rounded-md border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">
              {scheduleSaveSuccess}
            </p>
          )}
        </div>
      )}

      <button
        onClick={handleGenerate}
        disabled={generating || selectedTopics.length === 0 || !!topicError}
        className="w-full rounded-lg bg-blue-600 px-6 py-3 text-white font-medium hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {generating ? "Generating..." : "Generate Podcast"}
      </button>

      {generating && <LoadingSpinner />}
      {genError && <ErrorAlert message={genError} />}

      {lastEpisode && (
        <div className="rounded-lg border border-green-200 bg-green-50 p-4">
          <h3 className="font-semibold text-green-800">Episode Generated</h3>
          <p className="mt-1 text-sm text-green-700">{lastEpisode.title}</p>
        </div>
      )}
    </section>
  );
}
