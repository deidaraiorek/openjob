import { useEffect, useState } from "react";

import { useAppContext } from "../app/layout";
import type { Source, SourceCreatePayload } from "../lib/api";

const initialForm: SourceCreatePayload = {
  source_key: "",
  source_type: "greenhouse_board",
  name: "",
  base_url: "",
  settings: {},
  active: true,
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

export function SourcesRoute() {
  const { api } = useAppContext();
  const [sources, setSources] = useState<Source[]>([]);
  const [form, setForm] = useState(initialForm);
  const [editingSourceId, setEditingSourceId] = useState<number | null>(null);
  const [settingsText, setSettingsText] = useState("{}");
  const [showAdvancedSettings, setShowAdvancedSettings] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const [syncingSourceId, setSyncingSourceId] = useState<number | null>(null);

  async function reloadSources() {
    setSources(await api.listSources());
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
      const payload = { ...form, base_url: normalizedBaseUrl, settings };
      if (editingSourceId !== null) {
        await api.updateSource(editingSourceId, payload);
      } else {
        await api.createSource(payload);
      }
      setEditingSourceId(null);
      setForm(initialForm);
      setSettingsText("{}");
      setShowAdvancedSettings(false);
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
    setEditingSourceId(source.id);
    setForm({
      source_key: source.source_key,
      source_type: source.source_type,
      name: source.name,
      base_url: source.base_url,
      settings: source.settings,
      active: source.active,
    });
    setSettingsText(JSON.stringify(source.settings, null, 2));
    setShowAdvancedSettings(Object.keys(source.settings ?? {}).length > 0);
    setError(null);
    setSyncMessage(null);
  }

  function handleCancelEdit() {
    setEditingSourceId(null);
    setForm(initialForm);
    setSettingsText("{}");
    setShowAdvancedSettings(false);
    setError(null);
  }

  async function handleSync(source: Source) {
    setSyncMessage(null);
    setSyncingSourceId(source.id);

    try {
      const summary = await api.syncSource(source.id);
      await reloadSources();
      setSyncMessage(
        `${source.name} synced: ${summary.processed} processed, ${summary.created} new, ${summary.updated} updated.`,
      );
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
              {sources.map((source) => (
                <li key={source.id} className="stack-row stack-row-column">
                  <div>
                    <strong>{source.name}</strong>
                    <span>{source.source_type}</span>
                    <span>{source.base_url ?? "No base URL"}</span>
                  </div>
                  <div className="button-row">
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => handleEdit(source)}
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      onClick={() => void handleSync(source)}
                      disabled={syncingSourceId === source.id}
                    >
                      {syncingSourceId === source.id ? "Syncing..." : "Sync now"}
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
          {syncMessage ? <p className="supporting-copy">{syncMessage}</p> : null}
        </article>

        <article className="panel-card">
          <h2>{editingSourceId !== null ? "Edit source" : "Add source"}</h2>
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
    </main>
  );
}
