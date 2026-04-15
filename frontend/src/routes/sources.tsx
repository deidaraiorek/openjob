import { useEffect, useRef, useState } from "react";

import { useAppContext } from "../app/layout";
import type { Source, SourceCreatePayload } from "../lib/api";

const initialForm: SourceCreatePayload = {
  source_key: "",
  source_type: "greenhouse_board",
  name: "",
  base_url: "",
  settings: {},
  active: true,
  auto_sync_enabled: true,
  sync_interval_hours: 6,
};

function normalizeGithubCuratedUrl(sourceType: string, baseUrl: string | null): string | null {
  if (sourceType !== "github_curated" || !baseUrl) {
    return baseUrl;
  }

  const trimmed = baseUrl.trim();
  if (!trimmed.includes("github.com") && !trimmed.includes("raw.githubusercontent.com")) {
    return trimmed;
  }

  try {
    const url = new URL(trimmed);

    if (url.hostname === "raw.githubusercontent.com") {
      const normalizedPath = url.pathname.replace(/^\/+/, "").replace(/^refs\/heads\//, "");
      return `https://raw.githubusercontent.com/${normalizedPath}`;
    }

    if (url.hostname !== "github.com") {
      return trimmed;
    }

    const segments = url.pathname.split("/").filter(Boolean);
    if (segments.length < 2) {
      return trimmed;
    }

    const [owner, repo, ...rest] = segments;
    if (rest.length === 0) {
      return `https://raw.githubusercontent.com/${owner}/${repo}/HEAD/README.md`;
    }

    if (rest[0] === "blob" && rest.length >= 3) {
      return `https://raw.githubusercontent.com/${owner}/${repo}/${rest.slice(1).join("/")}`;
    }

    if (rest[0].toLowerCase() === "raw" && rest.length >= 2) {
      return `https://raw.githubusercontent.com/${owner}/${repo}/${rest.slice(1).join("/")}`;
    }

    return trimmed;
  } catch {
    return trimmed;
  }
}

function formatSourceType(sourceType: string): string {
  return sourceType
    .split("_")
    .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
    .join(" ");
}

function displaySourceName(source: Source): string {
  return source.name.trim() || source.source_key;
}

const ISO_OFFSET_PATTERN = /(Z|[+-]\d{2}:\d{2})$/i;

function parseUtcTimestamp(value: string): Date | null {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }

  const normalized = ISO_OFFSET_PATTERN.test(trimmed) ? trimmed : `${trimmed}Z`;
  const timestamp = new Date(normalized);
  if (Number.isNaN(timestamp.getTime())) {
    return null;
  }
  return timestamp;
}

function formatSyncTimestamp(value: string | null, timezone: string): string {
  if (!value) {
    return "Not scheduled yet.";
  }

  const timestamp = parseUtcTimestamp(value);
  if (!timestamp) {
    return value;
  }

  return timestamp.toLocaleString(undefined, { timeZone: timezone });
}

function chooseNewerTimestamp(currentValue: string | null, incomingValue: string | null): string | null {
  if (!currentValue) {
    return incomingValue;
  }
  if (!incomingValue) {
    return currentValue;
  }

  const currentTimestamp = parseUtcTimestamp(currentValue);
  const incomingTimestamp = parseUtcTimestamp(incomingValue);
  if (!currentTimestamp || !incomingTimestamp) {
    return incomingValue;
  }

  return incomingTimestamp.getTime() >= currentTimestamp.getTime() ? incomingValue : currentValue;
}

function mergeSourceWithFreshSyncState(currentSource: Source, incomingSource: Source): Source {
  return {
    ...currentSource,
    ...incomingSource,
    last_synced_at: chooseNewerTimestamp(currentSource.last_synced_at, incomingSource.last_synced_at),
    next_sync_at: chooseNewerTimestamp(currentSource.next_sync_at, incomingSource.next_sync_at),
  };
}

function formatSettingsPreview(settings: Record<string, unknown>): string {
  const entries = Object.entries(settings);
  if (entries.length === 0) {
    return "No extra config.";
  }

  return JSON.stringify(settings, null, 2);
}

function getSyncIntervalHours(source: Source): number {
  return Number.isFinite(source.sync_interval_hours) ? Math.max(1, source.sync_interval_hours) : 6;
}

function formatCompatibilitySummary(summary: Record<string, unknown> | null | undefined): string {
  if (!summary) {
    return "No compatibility data yet.";
  }

  const apiCompatible = Number(summary.api_compatible_targets ?? 0);
  const browserCompatible = Number(summary.browser_compatible_targets ?? 0);
  const manualOnly = Number(summary.manual_only_targets ?? 0);
  const resolutionFailed = Number(summary.resolution_failed_targets ?? 0);
  const parts: string[] = [];
  if (apiCompatible > 0) {
    parts.push(`${apiCompatible} API-compatible`);
  }
  if (browserCompatible > 0) {
    parts.push(`${browserCompatible} browser-compatible`);
  }
  if (manualOnly > 0) {
    parts.push(`${manualOnly} manual-only`);
  }
  if (resolutionFailed > 0) {
    parts.push(`${resolutionFailed} resolution failed`);
  }
  if (parts.length === 0) {
    return "No compatibility data yet.";
  }
  return parts.join(", ");
}

export function SourcesRoute() {
  const { api, timezone } = useAppContext();
  const [sources, setSources] = useState<Source[]>([]);
  const [expandedSourceIds, setExpandedSourceIds] = useState<number[]>([]);
  const [form, setForm] = useState(initialForm);
  const [syncIntervalInput, setSyncIntervalInput] = useState(String(initialForm.sync_interval_hours ?? ""));
  const [editingSourceId, setEditingSourceId] = useState<number | null>(null);
  const [settingsText, setSettingsText] = useState("{}");
  const [showAdvancedSettings, setShowAdvancedSettings] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const [syncingSourceId, setSyncingSourceId] = useState<number | null>(null);
  const [pendingDeleteSource, setPendingDeleteSource] = useState<Source | null>(null);
  const [deletingSourceId, setDeletingSourceId] = useState<number | null>(null);
  const formPanelRef = useRef<HTMLElement | null>(null);

  function loadSourceIntoForm(source: Source, options?: { preserveSyncMessage?: boolean }) {
    const syncIntervalHours = getSyncIntervalHours(source);
    setEditingSourceId(source.id);
    setExpandedSourceIds((current) => (current.includes(source.id) ? current : [...current, source.id]));
    setForm({
      source_key: source.source_key,
      source_type: source.source_type,
      name: source.name,
      base_url: source.base_url,
      settings: source.settings,
      active: source.active,
      auto_sync_enabled: source.auto_sync_enabled,
      sync_interval_hours: syncIntervalHours,
    });
    setSyncIntervalInput(String(syncIntervalHours));
    setSettingsText(JSON.stringify(source.settings, null, 2));
    setShowAdvancedSettings(Object.keys(source.settings ?? {}).length > 0);
    setError(null);
    if (!options?.preserveSyncMessage) {
      setSyncMessage(null);
    }
  }

  function mergeSource(savedSource: Source) {
    setSources((current) => {
      const next = current.some((source) => source.id === savedSource.id)
        ? current.map((source) =>
            source.id === savedSource.id ? mergeSourceWithFreshSyncState(source, savedSource) : source,
          )
        : [...current, savedSource];

      return [...next].sort((left, right) => left.name.localeCompare(right.name));
    });
  }

  async function reloadSources() {
    const freshSources = await api.listSources();
    setSources((current) => {
      const currentById = new Map(current.map((source) => [source.id, source]));
      const mergedSources = freshSources.map((source) => {
        const existingSource = currentById.get(source.id);
        return existingSource ? mergeSourceWithFreshSyncState(existingSource, source) : source;
      });

      return [...mergedSources].sort((left, right) => left.name.localeCompare(right.name));
    });
  }

  useEffect(() => {
    void reloadSources();
  }, [api]);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    try {
      const settings = JSON.parse(settingsText) as Record<string, unknown>;
      const normalizedBaseUrl = normalizeGithubCuratedUrl(form.source_type, form.base_url);
      const parsedSyncIntervalHours = syncIntervalInput.trim() ? Number(syncIntervalInput.trim()) : null;
      const payload = {
        ...form,
        base_url: normalizedBaseUrl,
        settings,
        sync_interval_hours: parsedSyncIntervalHours,
      };
      let savedSource: Source;
      if (editingSourceId !== null) {
        savedSource = await api.updateSource(editingSourceId, payload);
        mergeSource(savedSource);
        setExpandedSourceIds((current) => (current.includes(savedSource.id) ? current : [...current, savedSource.id]));
        setSyncMessage(`${displaySourceName(savedSource)} updated.`);
        loadSourceIntoForm(savedSource, { preserveSyncMessage: true });
      } else {
        savedSource = await api.createSource(payload);
        mergeSource(savedSource);
        setExpandedSourceIds((current) => [...current, savedSource.id]);
        setSyncMessage(`${displaySourceName(savedSource)} added.`);
        setEditingSourceId(null);
        setForm(initialForm);
        setSyncIntervalInput(String(initialForm.sync_interval_hours ?? ""));
        setSettingsText("{}");
        setShowAdvancedSettings(false);
      }
      await reloadSources();
    } catch (caughtError) {
      if (caughtError instanceof SyntaxError) {
        setError("Settings JSON is invalid. Use a JSON object like {}.");
        return;
      }

      if (caughtError instanceof Error) {
        setError(caughtError.message);
        return;
      }

      setError("Unable to save source right now.");
    }
  }

  function handleEdit(source: Source) {
    loadSourceIntoForm(source);
    if (typeof formPanelRef.current?.scrollIntoView === "function") {
      formPanelRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  function handleCancelEdit() {
    setEditingSourceId(null);
    setForm(initialForm);
    setSyncIntervalInput(String(initialForm.sync_interval_hours ?? ""));
    setSettingsText("{}");
    setShowAdvancedSettings(false);
    setError(null);
  }

  function toggleSourceDetails(sourceId: number) {
    setExpandedSourceIds((current) =>
      current.includes(sourceId) ? current.filter((id) => id !== sourceId) : [...current, sourceId],
    );
  }

  async function handleSync(source: Source) {
    setSyncMessage(null);
    setSyncingSourceId(source.id);

    try {
      const summary = await api.syncSource(source.id);
      const applySyncSummary = () =>
        setSources((current) =>
          current.map((item) =>
            item.id === source.id
              ? {
                  ...item,
                  last_synced_at: summary.last_synced_at ?? item.last_synced_at,
                  next_sync_at: summary.next_sync_at ?? item.next_sync_at,
                }
              : item,
          ),
        );

      applySyncSummary();
      const pendingBits: string[] = [];
      if (summary.pending_title_screening) {
        pendingBits.push(`${summary.pending_title_screening} pending title screen`);
      }
      if (summary.pending_full_relevance) {
        pendingBits.push(`${summary.pending_full_relevance} pending relevance`);
      }
      const pendingSuffix = pendingBits.length > 0 ? ` ${pendingBits.join(", ")}.` : "";
      const compatibilityBits = [
        summary.api_compatible_targets ? `${summary.api_compatible_targets} API-compatible` : null,
        summary.browser_compatible_targets ? `${summary.browser_compatible_targets} browser-compatible` : null,
        summary.manual_only_targets ? `${summary.manual_only_targets} manual-only` : null,
        summary.resolution_failed_targets ? `${summary.resolution_failed_targets} resolution failed` : null,
      ].filter((value): value is string => Boolean(value));
      const compatibilitySuffix =
        compatibilityBits.length > 0 ? ` Compatibility: ${compatibilityBits.join(", ")}.` : "";
      setSyncMessage(
        `${source.name} synced: ${summary.processed} processed, ${summary.created} new, ${summary.updated} updated.${pendingSuffix}${compatibilitySuffix}`,
      );
      await reloadSources();
      applySyncSummary();
    } catch (caughtError) {
      if (caughtError instanceof Error) {
        setSyncMessage(caughtError.message);
      } else {
        setSyncMessage(`Unable to sync ${source.name} right now.`);
      }
    } finally {
      setSyncingSourceId(null);
    }
  }

  async function handleDelete(source: Source) {
    setPendingDeleteSource(source);
    setError(null);
    setSyncMessage(null);
  }

  async function confirmDelete() {
    if (!pendingDeleteSource) {
      return;
    }

    setError(null);
    setSyncMessage(null);
    setDeletingSourceId(pendingDeleteSource.id);

    try {
      await api.deleteSource(pendingDeleteSource.id);
      if (editingSourceId === pendingDeleteSource.id) {
        handleCancelEdit();
      }
      await reloadSources();
      setSyncMessage(`${pendingDeleteSource.name} deleted.`);
      setPendingDeleteSource(null);
    } catch (caughtError) {
      if (caughtError instanceof Error) {
        setError(caughtError.message);
      } else {
        setError(`Unable to delete ${pendingDeleteSource.name} right now.`);
      }
    } finally {
      setDeletingSourceId(null);
    }
  }

  return (
    <main className="page-shell">
      <section className="content-grid">
        <article className="panel-card">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Sources</p>
              <h1>Discovery inputs</h1>
              <p className="supporting-copy">
                Configure the boards, feeds, and partner sources your platform should monitor for relevant roles.
              </p>
            </div>
          </div>

          {sources.length === 0 ? (
            <p className="empty-copy">No sources configured yet.</p>
          ) : (
            <ul className="stack-list">
              {sources.map((source) => {
                const isExpanded = expandedSourceIds.includes(source.id);
                const syncIntervalHours = getSyncIntervalHours(source);

                return (
                  <li
                    key={source.id}
                    className={`stack-row stack-row-column source-card${
                      syncingSourceId === source.id ? " source-card-syncing" : ""
                    }`}
                  >
                    <div className="source-card-summary">
                      <div className="source-card-head">
                        <div className="source-card-topline">
                          <strong>{displaySourceName(source)}</strong>
                        </div>
                        {source.name.trim() && source.name.trim() !== source.source_key ? (
                          <p className="source-key-line">{source.source_key}</p>
                        ) : null}
                        <p className="source-summary-line">
                          {source.active
                            ? source.auto_sync_enabled
                              ? `Auto-sync every ${syncIntervalHours} hour${syncIntervalHours === 1 ? "" : "s"}`
                              : "Auto-sync off"
                            : "Inactive"}
                        </p>
                      </div>
                      <div className="source-summary-actions">
                        <span className="source-type-pill">{formatSourceType(source.source_type)}</span>
                        <button
                          type="button"
                          className="ghost-button source-disclosure-button"
                          onClick={() => toggleSourceDetails(source.id)}
                          aria-expanded={isExpanded}
                          aria-controls={`source-details-${source.id}`}
                        >
                          <span
                            className={`source-disclosure-icon${isExpanded ? " source-disclosure-icon-open" : ""}`}
                            aria-hidden="true"
                          />
                          {isExpanded ? "Hide details" : "Show details"}
                        </button>
                      </div>
                    </div>

                    {isExpanded ? (
                      <div id={`source-details-${source.id}`} className="source-details">
                        <div className="source-link-block">
                          <span className="source-link-label">Monitored URL</span>
                          <p className="source-link-value">{source.base_url ?? "No base URL yet."}</p>
                        </div>
                        <div className="source-link-block">
                          <span className="source-link-label">Status</span>
                          <p className="source-link-value">
                            {source.active ? (source.auto_sync_enabled ? "Active with auto-sync" : "Active with auto-sync off") : "Inactive"}
                          </p>
                        </div>
                        <div className="source-link-block">
                          <span className="source-link-label">Sync interval</span>
                          <p className="source-link-value">
                            Every {syncIntervalHours} hour{syncIntervalHours === 1 ? "" : "s"}
                          </p>
                        </div>
                        <div className="source-link-block">
                          <span className="source-link-label">Last sync</span>
                          <p className="source-link-value">{formatSyncTimestamp(source.last_synced_at, timezone)}</p>
                        </div>
                        <div className="source-link-block">
                          <span className="source-link-label">Next sync</span>
                          <p className="source-link-value">
                            {source.active ? formatSyncTimestamp(source.next_sync_at, timezone) : "Paused while source is inactive"}
                          </p>
                        </div>
                        <div className="source-link-block">
                          <span className="source-link-label">Timezone</span>
                          <p className="source-link-value">{timezone}</p>
                        </div>
                        <div className="source-link-block">
                          <span className="source-link-label">Config</span>
                          <pre className="source-config-preview">{formatSettingsPreview(source.settings)}</pre>
                        </div>
                        <div className="source-link-block">
                          <span className="source-link-label">Last compatibility scan</span>
                          <p className="source-link-value">{formatCompatibilitySummary(source.last_sync_summary)}</p>
                        </div>
                      </div>
                    ) : null}

                    {syncingSourceId === source.id ? (
                      <div className="source-sync-status" role="status" aria-live="polite">
                        <span className="source-sync-pulse" aria-hidden="true" />
                        Checking this source for new jobs and updating relevance.
                      </div>
                    ) : !source.active ? (
                      <div className="source-sync-status" role="status" aria-live="polite">
                        Source is inactive, so scheduled and manual sync are paused.
                      </div>
                    ) : null}

                    <div className="button-row source-card-actions">
                      <button
                        type="button"
                        className="secondary-button"
                        onClick={() => handleEdit(source)}
                        disabled={syncingSourceId === source.id}
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        className="ghost-button"
                        onClick={() => void handleDelete(source)}
                        disabled={syncingSourceId === source.id}
                      >
                        Delete
                      </button>
                      <button
                        type="button"
                        className={`source-primary-button${syncingSourceId === source.id ? " source-sync-button" : ""}`}
                        onClick={() => void handleSync(source)}
                        disabled={syncingSourceId === source.id || !source.active}
                      >
                        {syncingSourceId === source.id ? (
                          <>
                            <span className="button-spinner" aria-hidden="true" />
                            Syncing source
                          </>
                        ) : !source.active ? (
                          "Reactivate to sync"
                        ) : (
                          "Sync now"
                        )}
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </article>

        <article className="panel-card" ref={formPanelRef}>
          <h2>{editingSourceId !== null ? "Edit source" : "Add source"}</h2>
          {editingSourceId !== null ? (
            <p className="supporting-copy">
              Editing <strong>{form.name.trim() || form.source_key || "selected source"}</strong>. Save changes will
              update this source instead of creating a new one.
            </p>
          ) : null}
          <form className="form-grid" onSubmit={handleSubmit}>
            <label>
              <span>Source key</span>
              <input
                value={form.source_key}
                onChange={(event) => setForm((current) => ({ ...current, source_key: event.target.value }))}
              />
            </label>
            <label>
              <span>Name</span>
              <input
                value={form.name}
                onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
              />
            </label>
            <label>
              <span>Source type</span>
              <select
                value={form.source_type}
                onChange={(event) => setForm((current) => ({ ...current, source_type: event.target.value }))}
              >
                <option value="greenhouse_board">Greenhouse</option>
                <option value="lever_postings">Lever</option>
                <option value="github_curated">GitHub curated</option>
                <option value="linkedin_search">LinkedIn search</option>
              </select>
            </label>
            <label>
              <span>Base URL</span>
              <input
                value={form.base_url ?? ""}
                onChange={(event) => setForm((current) => ({ ...current, base_url: event.target.value }))}
              />
            </label>

            <div className="full-width source-form-controls">
              <label className="source-toggle-row">
                <span>Active</span>
                <input
                  type="checkbox"
                  checked={form.active}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      active: event.target.checked,
                      auto_sync_enabled: event.target.checked ? current.auto_sync_enabled : false,
                    }))
                  }
                />
              </label>

              <label className={`source-toggle-row${!form.active ? " source-toggle-row-disabled" : ""}`}>
                <span>Auto-sync</span>
                <input
                  type="checkbox"
                  checked={form.auto_sync_enabled}
                  onChange={(event) => {
                    if (event.target.checked && !syncIntervalInput.trim()) {
                      setSyncIntervalInput("6");
                    }
                    setForm((current) => ({
                      ...current,
                      auto_sync_enabled: event.target.checked,
                    }));
                  }}
                  disabled={!form.active}
                />
              </label>

              <label className={`source-inline-field${!form.active ? " source-inline-field-disabled" : ""}`}>
                <span>Sync every</span>
                <div className="source-hours-shell">
                  <input
                    type="text"
                    inputMode="numeric"
                    pattern="[0-9]*"
                    value={syncIntervalInput}
                    onChange={(event) => {
                      const nextValue = event.target.value.replace(/[^\d]/g, "");
                      setSyncIntervalInput(nextValue);
                    }}
                    disabled={!form.active}
                    aria-label="Sync every hours"
                  />
                  <span className="source-hours-suffix">hours</span>
                </div>
              </label>
            </div>

            {form.source_type === "github_curated" ? (
              <p className="supporting-copy full-width">
                Paste the repo README raw URL or a normal GitHub README link. The form will convert
                GitHub <code>blob</code> links into raw markdown automatically.
              </p>
            ) : null}
            <div className="full-width advanced-settings-card">
              <button
                type="button"
                className="ghost-button advanced-settings-toggle"
                onClick={() => setShowAdvancedSettings((current) => !current)}
                aria-expanded={showAdvancedSettings}
              >
                {showAdvancedSettings ? "Hide advanced settings" : "Show advanced settings"}
              </button>
              <p className="muted-copy">
                Only use this when a source needs extra per-source configuration beyond the basic fields.
              </p>
              {showAdvancedSettings ? (
                <label className="full-width">
                  <span>Settings JSON</span>
                  <textarea
                    value={settingsText}
                    onChange={(event) => setSettingsText(event.target.value)}
                    rows={6}
                  />
                </label>
              ) : null}
            </div>
            {error ? <p className="error-copy">{error}</p> : null}
            <div className="button-row">
              <button type="submit">{editingSourceId !== null ? "Save changes" : "Save source"}</button>
              {editingSourceId !== null ? (
                <button type="button" className="secondary-button" onClick={handleCancelEdit}>
                  Cancel
                </button>
              ) : null}
            </div>
          </form>
        </article>
      </section>
      {pendingDeleteSource ? (
        <div className="confirm-toast" role="status" aria-live="polite">
          <div className="confirm-toast-copy">
            <strong>Delete source?</strong>
            <p>
              Remove <span>{pendingDeleteSource.name}</span> from discovery inputs. You can add it back later, but
              this source will stop syncing immediately.
            </p>
          </div>
          <div className="button-row">
            <button
              type="button"
              className="ghost-button"
              onClick={() => setPendingDeleteSource(null)}
              disabled={deletingSourceId === pendingDeleteSource.id}
            >
              Cancel
            </button>
            <button
              type="button"
              className="danger-button"
              onClick={() => void confirmDelete()}
              disabled={deletingSourceId === pendingDeleteSource.id}
            >
              {deletingSourceId === pendingDeleteSource.id ? "Deleting..." : "Delete source"}
            </button>
          </div>
        </div>
      ) : null}
      {syncMessage ? (
        <div className="action-toast" role="status" aria-live="polite">
          <p>{syncMessage}</p>
          <button type="button" className="ghost-button action-toast-close" onClick={() => setSyncMessage(null)}>
            Dismiss
          </button>
        </div>
      ) : null}
    </main>
  );
}
