import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";

import { useAppContext } from "../app/layout";
import type { AnswerCreatePayload, AnswerEntry } from "../lib/api";

type ProfileTab = "role-profile" | "answers";

const initialForm: AnswerCreatePayload = {
  question_template_id: null,
  label: "",
  answer_text: "",
  answer_payload: {},
};

function isFileAnswer(answer: AnswerEntry) {
  return answer.answer_payload.kind === "file";
}

function describeAnswerValue(answer: AnswerEntry) {
  if (isFileAnswer(answer)) {
    const filename = typeof answer.answer_payload.filename === "string"
      ? answer.answer_payload.filename
      : "Uploaded file";
    return `File upload: ${filename}`;
  }

  if (answer.answer_text) {
    return answer.answer_text;
  }

  return JSON.stringify(answer.answer_payload);
}

export function RoleProfileRoute() {
  const { api } = useAppContext();
  const location = useLocation();
  const [currentTab, setCurrentTab] = useState<ProfileTab>(
    location.search.includes("tab=answers") ? "answers" : "role-profile",
  );

  const [prompt, setPrompt] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const [answers, setAnswers] = useState<AnswerEntry[]>([]);
  const [form, setForm] = useState(initialForm);
  const [editingAnswerId, setEditingAnswerId] = useState<number | null>(null);
  const [answerError, setAnswerError] = useState<string | null>(null);

  async function reloadAnswers() {
    setAnswers(await api.listAnswers());
  }

  useEffect(() => {
    async function loadProfile() {
      try {
        const profile = await api.getRoleProfile();
        setPrompt(profile.prompt);
      } catch {
        setPrompt("");
      }
    }

    void Promise.all([loadProfile(), reloadAnswers()]);
  }, [api]);

  async function handleProfileSubmit(event: React.FormEvent<HTMLFormElement>) {
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

  async function handleAnswerSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAnswerError(null);
    try {
      const payload = {
        ...form,
        question_template_id: form.question_template_id || null,
      };
      if (editingAnswerId !== null) {
        await api.updateAnswer(editingAnswerId, payload);
      } else {
        await api.createAnswer(payload);
      }
      setForm(initialForm);
      setEditingAnswerId(null);
      await reloadAnswers();
    } catch (caughtError) {
      setAnswerError(caughtError instanceof Error ? caughtError.message : "Unable to save answer entry.");
    }
  }

  function handleEdit(answer: AnswerEntry) {
    setEditingAnswerId(answer.id);
    setForm({
      question_template_id: answer.question_template_id,
      label: answer.label,
      answer_text: answer.answer_text ?? "",
      answer_payload: answer.answer_payload,
    });
    setAnswerError(null);
    setCurrentTab("answers");
  }

  function handleCancelEdit() {
    setEditingAnswerId(null);
    setForm(initialForm);
    setAnswerError(null);
  }

  useEffect(() => {
    setCurrentTab(location.search.includes("tab=answers") ? "answers" : "role-profile");
  }, [location.search]);

  return (
    <main className="page-shell">
      <section className="panel-card">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Profile</p>
            <h1>Centralized user profile</h1>
            <p className="supporting-copy">
              Keep your role targeting, reusable answers, and upload memory together so future application runs pull from one place.
            </p>
          </div>
        </div>

        <div className="profile-tab-list" role="tablist" aria-label="Profile sections">
          <button
            type="button"
            role="tab"
            aria-selected={currentTab === "role-profile"}
            className={currentTab === "role-profile" ? "profile-tab-button active" : "profile-tab-button"}
            onClick={() => setCurrentTab("role-profile")}
          >
            Role Profile
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={currentTab === "answers"}
            className={currentTab === "answers" ? "profile-tab-button active" : "profile-tab-button"}
            onClick={() => setCurrentTab("answers")}
          >
            Saved Answers
          </button>
        </div>

        {currentTab === "role-profile" ? (
          <section className="profile-section" aria-label="Role profile section">
            <div className="profile-section-copy">
              <p className="supporting-copy">
                Describe the roles you want. We use this prompt directly during AI title screening and deeper relevance review.
              </p>
            </div>

            <form className="form-grid" onSubmit={handleProfileSubmit}>
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
        ) : (
          <section className="profile-section" aria-label="Saved answers section">
            <div className="profile-section-copy">
              <p className="supporting-copy">
                Edit the reusable answers and uploads that power autofill across application flows.
              </p>
            </div>

            <div className="content-grid">
              <article className="panel-card profile-subcard">
                {answers.length === 0 ? (
                  <p className="empty-copy">No saved answers yet.</p>
                ) : (
                  <ul className="stack-list">
                    {answers.map((answer) => (
                      <li key={answer.id} className="stack-row stack-row-column">
                        <strong>{answer.label}</strong>
                        <span>{describeAnswerValue(answer)}</span>
                        <button type="button" className="secondary-button" onClick={() => handleEdit(answer)}>
                          Edit
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </article>

              <article className="panel-card profile-subcard">
                <h2>{editingAnswerId !== null ? "Edit answer" : "Add answer"}</h2>
                <p className="supporting-copy">
                  Template links are attached automatically when you save an answer from the Questions screen.
                </p>
                <form className="form-grid" onSubmit={handleAnswerSubmit}>
                  <label>
                    <span>Label</span>
                    <input
                      value={form.label}
                      onChange={(event) => setForm((current) => ({ ...current, label: event.target.value }))}
                    />
                  </label>
                  <label className="full-width">
                    <span>Answer text</span>
                    <textarea
                      rows={5}
                      value={form.answer_text ?? ""}
                      onChange={(event) => setForm((current) => ({ ...current, answer_text: event.target.value }))}
                    />
                  </label>
                  {answerError ? <p className="error-copy">{answerError}</p> : null}
                  <div className="button-row">
                    <button type="submit">{editingAnswerId !== null ? "Save changes" : "Save answer"}</button>
                    {editingAnswerId !== null ? (
                      <button type="button" className="secondary-button" onClick={handleCancelEdit}>
                        Cancel
                      </button>
                    ) : null}
                  </div>
                </form>
              </article>
            </div>
          </section>
        )}
      </section>
    </main>
  );
}
