import { useEffect, useState } from "react";

import { useAppContext } from "../app/layout";
import type { AnswerEntry, AnswerCreatePayload } from "../lib/api";

const initialForm: AnswerCreatePayload = {
  question_template_id: null,
  label: "",
  answer_text: "",
  answer_payload: {},
};

export function AnswersRoute() {
  const { api } = useAppContext();
  const [answers, setAnswers] = useState<AnswerEntry[]>([]);
  const [form, setForm] = useState(initialForm);
  const [editingAnswerId, setEditingAnswerId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function reloadAnswers() {
    setAnswers(await api.listAnswers());
  }

  useEffect(() => {
    void reloadAnswers();
  }, [api]);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
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
      setError(caughtError instanceof Error ? caughtError.message : "Unable to save answer entry.");
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
    setError(null);
  }

  function handleCancelEdit() {
    setEditingAnswerId(null);
    setForm(initialForm);
    setError(null);
  }

  return (
    <main className="page-shell">
      <section className="content-grid">
        <article className="panel-card">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Answers</p>
              <h1>Answer memory</h1>
              <p className="supporting-copy">
                Save reusable answers once so future application runs can fill them without rework.
              </p>
            </div>
          </div>

          {answers.length === 0 ? (
            <p className="empty-copy">No saved answers yet.</p>
          ) : (
            <ul className="stack-list">
              {answers.map((answer) => (
                <li key={answer.id} className="stack-row stack-row-column">
                  <strong>{answer.label}</strong>
                  <span>{answer.answer_text ?? JSON.stringify(answer.answer_payload)}</span>
                  <button type="button" className="secondary-button" onClick={() => handleEdit(answer)}>
                    Edit
                  </button>
                </li>
              ))}
            </ul>
          )}
        </article>

        <article className="panel-card">
          <h2>{editingAnswerId !== null ? "Edit answer" : "Add answer"}</h2>
          <form className="form-grid" onSubmit={handleSubmit}>
            <label>
              <span>Label</span>
              <input
                value={form.label}
                onChange={(event) => setForm((current) => ({ ...current, label: event.target.value }))}
              />
            </label>
            <label>
              <span>Question template ID</span>
              <input
                value={form.question_template_id ?? ""}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    question_template_id: event.target.value ? Number(event.target.value) : null,
                  }))
                }
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
            {error ? <p className="error-copy">{error}</p> : null}
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
      </section>
    </main>
  );
}
