import { useState } from "react";
import {
  Schedule,
  ScheduleRequest,
  TONES,
  DURATION_CONFIG,
  SPEAKER_MODES,
} from "../types";
import LoadingSpinner from "../components/LoadingSpinner";
import ErrorAlert from "../components/ErrorAlert";

type EditForm = {
  name: string;
  selected_interests: string[];
  frequency: string;
  duration: string;
  tone: string;
  speaker_mode: string;
};

type Props = {
  schedules: Schedule[];
  schedulesLoading: boolean;
  runningSchedule: string | null;
  deletingSchedule: string | null;
  handleRunSchedule: (id: string) => void;
  handleRunAllSchedules: () => void;
  handleUpdateSchedule: (id: string, payload: ScheduleRequest) => Promise<void>;
  handleDeleteSchedule: (id: string) => Promise<void>;
  savedInterests: string[];
  userId: string;
};

const SCHEDULE_FREQUENCIES = ["daily", "weekly"];

function scheduleToEditForm(schedule: Schedule): EditForm {
  return {
    name: schedule.name,
    selected_interests: schedule.selected_interests,
    frequency: schedule.frequency === "weekly" ? "weekly" : "daily",
    duration: schedule.duration,
    tone: schedule.tone,
    speaker_mode: schedule.speaker_mode,
  };
}

function uniqueInterestOptions(savedInterests: string[], selected: string[]) {
  const options: string[] = [];
  const seen = new Set<string>();
  for (const topic of [...savedInterests, ...selected]) {
    const key = topic.toLowerCase();
    if (seen.has(key)) continue;
    options.push(topic);
    seen.add(key);
  }
  return options;
}

export default function SchedulesTab(props: Props) {
  const {
    schedules,
    schedulesLoading,
    runningSchedule,
    deletingSchedule,
    handleRunSchedule,
    handleRunAllSchedules,
    handleUpdateSchedule,
    handleDeleteSchedule,
    savedInterests,
    userId,
  } = props;

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<EditForm | null>(null);
  const [editError, setEditError] = useState<string | null>(null);
  const [savingEdit, setSavingEdit] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const beginEdit = (schedule: Schedule) => {
    setEditingId(schedule.id);
    setEditForm(scheduleToEditForm(schedule));
    setEditError(null);
    setActionError(null);
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditForm(null);
    setEditError(null);
  };

  const setEditDuration = (duration: string) => {
    const limit = DURATION_CONFIG[duration]?.maxTopics ?? 2;
    setEditForm((current) =>
      current
        ? {
            ...current,
            duration,
            selected_interests: current.selected_interests.slice(0, limit),
          }
        : current
    );
  };

  const toggleEditInterest = (topic: string) => {
    setEditForm((current) => {
      if (!current) return current;
      const selected = current.selected_interests.includes(topic);
      return {
        ...current,
        selected_interests: selected
          ? current.selected_interests.filter((item) => item !== topic)
          : [...current.selected_interests, topic],
      };
    });
  };

  const saveEdit = async (schedule: Schedule) => {
    if (!editForm) return;
    const limit = DURATION_CONFIG[editForm.duration]?.maxTopics ?? 2;
    if (!editForm.name.trim()) {
      setEditError("Please enter a schedule name.");
      return;
    }
    if (editForm.selected_interests.length === 0) {
      setEditError("Please select at least one topic.");
      return;
    }
    if (editForm.selected_interests.length > limit) {
      setEditError(
        `A ${editForm.duration} podcast supports up to ${limit} topic(s). Select fewer topics or choose a longer duration.`
      );
      return;
    }

    setSavingEdit(true);
    setEditError(null);
    setActionError(null);
    try {
      await handleUpdateSchedule(schedule.id, {
        user_id: schedule.user_id || userId,
        name: editForm.name.trim(),
        selected_interests: editForm.selected_interests,
        frequency: editForm.frequency,
        duration: editForm.duration,
        tone: editForm.tone,
        speaker_mode: editForm.speaker_mode,
      });
      cancelEdit();
    } catch (error: unknown) {
      setEditError(
        error instanceof Error ? error.message : "Failed to update schedule"
      );
    } finally {
      setSavingEdit(false);
    }
  };

  const deleteSchedule = async (schedule: Schedule) => {
    if (!window.confirm("Delete this schedule?")) return;
    setActionError(null);
    try {
      await handleDeleteSchedule(schedule.id);
      if (editingId === schedule.id) cancelEdit();
    } catch (error: unknown) {
      setActionError(
        error instanceof Error ? error.message : "Failed to delete schedule"
      );
    }
  };

  return (
    <section className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <h2 className="text-xl font-semibold">Podcast Schedules</h2>
        <button
          onClick={handleRunAllSchedules}
          disabled={runningSchedule === "__all__" || schedules.length === 0}
          className="rounded-md bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {runningSchedule === "__all__" ? "Running..." : "Run All Due"}
        </button>
      </div>

      {actionError && <ErrorAlert message={actionError} />}
      {schedulesLoading && <LoadingSpinner />}

      {!schedulesLoading && schedules.length === 0 && (
        <div className="rounded-lg border bg-white p-12 text-center text-gray-500">
          No schedules yet. Create one from the Generate tab by choosing Daily or
          Weekly and saving your configuration.
        </div>
      )}

      {schedules.map((schedule) => {
        const isEditing = editingId === schedule.id && editForm;
        const limit = editForm
          ? DURATION_CONFIG[editForm.duration]?.maxTopics ?? 2
          : 2;
        const editTopicError =
          editForm && editForm.selected_interests.length > limit
            ? `A ${editForm.duration} podcast supports up to ${limit} topic(s). Select fewer topics or choose a longer duration.`
            : null;
        const interestOptions = editForm
          ? uniqueInterestOptions(savedInterests, editForm.selected_interests)
          : [];

        return (
          <div key={schedule.id} className="rounded-lg border bg-white p-4 shadow-sm">
            {!isEditing && (
              <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <h3 className="font-semibold">{schedule.name}</h3>
                  <div className="mt-1 flex flex-wrap gap-2 text-xs text-gray-500">
                    <span>Topics: {schedule.selected_interests.join(", ")}</span>
                    <span>{schedule.frequency}</span>
                    <span>{schedule.duration}</span>
                    <span>{schedule.speaker_mode}</span>
                    <span>Tone: {schedule.tone}</span>
                    {schedule.last_run_at && (
                      <span>
                        Last run: {new Date(schedule.last_run_at).toLocaleString()}
                      </span>
                    )}
                  </div>
                </div>
                <div className="flex shrink-0 flex-wrap gap-2">
                  <button
                    onClick={() => handleRunSchedule(schedule.id)}
                    disabled={runningSchedule === schedule.id}
                    className="rounded-md bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {runningSchedule === schedule.id ? "Running..." : "Run Now"}
                  </button>
                  <button
                    onClick={() => beginEdit(schedule)}
                    className="rounded-md border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
                  >
                    Edit
                  </button>
                  <button
                    onClick={() => deleteSchedule(schedule)}
                    disabled={deletingSchedule === schedule.id}
                    className="rounded-md border border-red-200 px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {deletingSchedule === schedule.id ? "Deleting..." : "Delete"}
                  </button>
                </div>
              </div>
            )}

            {isEditing && editForm && (
              <div className="space-y-4">
                <div>
                  <label className="mb-1 block text-sm font-medium text-gray-700">
                    Name
                  </label>
                  <input
                    type="text"
                    value={editForm.name}
                    onChange={(event) =>
                      setEditForm({ ...editForm, name: event.target.value })
                    }
                    className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
                  />
                </div>

                <div>
                  <label className="mb-2 block text-sm font-medium text-gray-700">
                    Interests
                  </label>
                  {interestOptions.length > 0 ? (
                    <div className="flex flex-wrap gap-2">
                      {interestOptions.map((topic) => {
                        const selected =
                          editForm.selected_interests.includes(topic);
                        return (
                          <button
                            key={topic.toLowerCase()}
                            type="button"
                            onClick={() => toggleEditInterest(topic)}
                            className={`rounded-full border px-3 py-1.5 text-sm font-medium transition-colors ${
                              selected
                                ? "border-blue-600 bg-blue-600 text-white"
                                : "border-gray-300 bg-white text-gray-700 hover:border-blue-300 hover:text-blue-700"
                            }`}
                          >
                            {selected ? `\u2713 ${topic}` : topic}
                          </button>
                        );
                      })}
                    </div>
                  ) : (
                    <p className="text-sm text-gray-500">
                      Add saved interests from the Generate tab before editing topics.
                    </p>
                  )}
                  <p className="mt-2 text-xs text-gray-500">
                    {editForm.selected_interests.length} topic
                    {editForm.selected_interests.length === 1 ? "" : "s"} selected
                    {` (max ${limit} for ${editForm.duration})`}
                  </p>
                </div>

                <div className="grid gap-4 sm:grid-cols-4">
                  <div>
                    <label className="mb-1 block text-sm font-medium text-gray-700">
                      Frequency
                    </label>
                    <select
                      value={editForm.frequency}
                      onChange={(event) =>
                        setEditForm({
                          ...editForm,
                          frequency: event.target.value,
                        })
                      }
                      className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
                    >
                      {SCHEDULE_FREQUENCIES.map((frequency) => (
                        <option key={frequency} value={frequency}>
                          {frequency.charAt(0).toUpperCase() + frequency.slice(1)}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="mb-1 block text-sm font-medium text-gray-700">
                      Duration
                    </label>
                    <select
                      value={editForm.duration}
                      onChange={(event) => setEditDuration(event.target.value)}
                      className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
                    >
                      {Object.entries(DURATION_CONFIG).map(([key, cfg]) => (
                        <option key={key} value={key}>
                          {cfg.label} - max {cfg.maxTopics} topic
                          {cfg.maxTopics > 1 ? "s" : ""}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="mb-1 block text-sm font-medium text-gray-700">
                      Tone
                    </label>
                    <select
                      value={editForm.tone}
                      onChange={(event) =>
                        setEditForm({ ...editForm, tone: event.target.value })
                      }
                      className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
                    >
                      {TONES.map((tone) => (
                        <option key={tone} value={tone}>
                          {tone.charAt(0).toUpperCase() + tone.slice(1)}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="mb-1 block text-sm font-medium text-gray-700">
                      Format
                    </label>
                    <select
                      value={editForm.speaker_mode}
                      onChange={(event) =>
                        setEditForm({
                          ...editForm,
                          speaker_mode: event.target.value,
                        })
                      }
                      className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
                    >
                      {SPEAKER_MODES.map((mode) => (
                        <option key={mode.value} value={mode.value}>
                          {mode.label}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                {editTopicError && <p className="text-xs text-red-600">{editTopicError}</p>}
                {editError && <ErrorAlert message={editError} />}

                <div className="flex justify-end gap-2">
                  <button
                    type="button"
                    onClick={cancelEdit}
                    className="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={() => saveEdit(schedule)}
                    disabled={
                      savingEdit ||
                      !editForm.name.trim() ||
                      editForm.selected_interests.length === 0 ||
                      !!editTopicError
                    }
                    className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {savingEdit ? "Saving..." : "Save"}
                  </button>
                </div>
              </div>
            )}
          </div>
        );
      })}
    </section>
  );
}
