import { useEffect, useState } from "react";

import { useAppContext } from "../app/layout";

export function RoleProfileRoute() {
  const { api } = useAppContext();
  const [prompt, setPrompt] = useState("");
  const [titles, setTitles] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    async function loadProfile() {
      try {
        const profile = await api.getRoleProfile();
        setPrompt(profile.prompt);
        setTitles(profile.generated_titles.join(", "));
      } catch {
        setPrompt("");
      }
    }

    void loadProfile();
  }, [api]);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    try {
      const saved = await api.saveRoleProfile({
        prompt,
        generated_titles: titles
          .split(",")
          .map((value) => value.trim())
          .filter(Boolean),
        generated_keywords: [],
      });
      setTitles(saved.generated_titles.join(", "));
      setStatus("Saved");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleGenerateSuggestions() {
    setSubmitting(true);
    try {
      const generated = await api.saveRoleProfile({
        prompt,
        generated_titles: [],
        generated_keywords: [],
      });
      setTitles(generated.generated_titles.join(", "));
      setStatus("Generated suggestions");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="page-shell">
      <section className="panel-card">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Role profile</p>
            <h1>Targeting memory</h1>
            <p className="supporting-copy">
              Describe the roles you want and keep the AI-generated title catalog editable and reusable.
            </p>
          </div>
        </div>

        <form className="form-grid" onSubmit={handleSubmit}>
          <label className="full-width">
            <span>Prompt</span>
            <textarea rows={4} value={prompt} onChange={(event) => setPrompt(event.target.value)} />
          </label>
          <label className="full-width">
            <span>Generated titles</span>
            <textarea rows={4} value={titles} onChange={(event) => setTitles(event.target.value)} />
          </label>
          {status ? <p className="success-copy">{status}</p> : null}
          <div className="button-row">
            <button disabled={submitting || !prompt.trim()} type="button" onClick={handleGenerateSuggestions}>
              {submitting ? "Working..." : "Generate with AI"}
            </button>
            <button disabled={submitting || !prompt.trim()} type="submit">
              {submitting ? "Working..." : "Save role profile"}
            </button>
          </div>
        </form>
      </section>
    </main>
  );
}
