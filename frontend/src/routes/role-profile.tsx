import { useEffect, useState } from "react";

import { useAppContext } from "../app/layout";

export function RoleProfileRoute() {
  const { api } = useAppContext();
  const [prompt, setPrompt] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    async function loadProfile() {
      try {
        const profile = await api.getRoleProfile();
        setPrompt(profile.prompt);
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
      await api.saveRoleProfile({
        prompt,
        generated_titles: [],
        generated_keywords: [],
      });
      setStatus("Saved");
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
              Describe the roles you want. We use this prompt directly during AI title screening and deeper relevance review.
            </p>
          </div>
        </div>

        <form className="form-grid" onSubmit={handleSubmit}>
          <label className="full-width">
            <span>Prompt</span>
            <textarea rows={4} value={prompt} onChange={(event) => setPrompt(event.target.value)} />
          </label>
          <p className="supporting-copy full-width">
            During sync, discovered job titles are screened in AI batches against this prompt first. Only plausible titles move on to deeper relevance checks.
          </p>
          {status ? <p className="success-copy">{status}</p> : null}
          <div className="button-row">
            <button disabled={submitting || !prompt.trim()} type="submit">
              {submitting ? "Working..." : "Save role profile"}
            </button>
          </div>
        </form>
      </section>
    </main>
  );
}
