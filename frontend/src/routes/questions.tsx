import { useEffect, useState } from "react";

import { useAppContext } from "../app/layout";
import type { AnswerEntry, QuestionTask } from "../lib/api";

function isMultiSelectField(task: QuestionTask) {
  return task.field_type.includes("multi_select") || task.field_type.includes("checkbox");
}

function isSingleSelectField(task: QuestionTask) {
  return (
    !isMultiSelectField(task)
    && (task.field_type.includes("single_select") || task.field_type.includes("radio"))
  );
}

function describeFieldType(task: QuestionTask) {
  if (isMultiSelectField(task)) {
    return "Select one or more options";
  }
  if (isSingleSelectField(task)) {
    return "Select one option";
  }
  return "Free text answer";
}

export function QuestionsRoute() {
  const { api } = useAppContext();
  const [tasks, setTasks] = useState<QuestionTask[]>([]);
  const [answers, setAnswers] = useState<AnswerEntry[]>([]);
  const [draftLabels, setDraftLabels] = useState<Record<number, string>>({});
  const [draftTexts, setDraftTexts] = useState<Record<number, string>>({});
  const [draftSingleValues, setDraftSingleValues] = useState<Record<number, string>>({});
  const [draftMultiValues, setDraftMultiValues] = useState<Record<number, string[]>>({});
  const [savingTaskId, setSavingTaskId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function reloadData() {
    const [taskList, answerList] = await Promise.all([
      api.listQuestionTasks(),
      api.listAnswers(),
    ]);
    setTasks(taskList);
    setAnswers(answerList);
  }

  useEffect(() => {
    void reloadData();
  }, [api]);

  async function resolveTask(taskId: number, answerEntryId: number) {
    setError(null);
    await api.resolveQuestionTask(taskId, {
      status: "reusable",
      linked_answer_entry_id: answerEntryId,
    });
    await reloadData();
  }

  async function createAndLinkAnswer(task: QuestionTask) {
    const label = (draftLabels[task.id] ?? task.prompt_text).trim();
    let answerText: string | null = null;
    let answerPayload: Record<string, unknown> = {};

    if (isMultiSelectField(task)) {
      const selectedValues = draftMultiValues[task.id] ?? [];
      if (selectedValues.length === 0) {
        setError(`Choose at least one option for "${task.prompt_text}" before saving.`);
        return;
      }
      answerText = selectedValues.join(", ");
      answerPayload = { values: selectedValues };
    } else if (isSingleSelectField(task)) {
      const selectedValue = (draftSingleValues[task.id] ?? "").trim();
      if (!selectedValue) {
        setError(`Choose an option for "${task.prompt_text}" before saving.`);
        return;
      }
      answerText = selectedValue;
      answerPayload = { value: selectedValue };
    } else {
      answerText = (draftTexts[task.id] ?? "").trim();
      if (!answerText) {
        setError(`Add an answer for "${task.prompt_text}" before saving.`);
        return;
      }
    }

    setError(null);
    setSavingTaskId(task.id);

    try {
      const answer = await api.createAnswer({
        question_template_id: task.question_template_id,
        label,
        answer_text: answerText,
        answer_payload: answerPayload,
      });
      await resolveTask(task.id, answer.id);
      setDraftLabels((current) => ({ ...current, [task.id]: "" }));
      setDraftTexts((current) => ({ ...current, [task.id]: "" }));
      setDraftSingleValues((current) => ({ ...current, [task.id]: "" }));
      setDraftMultiValues((current) => ({ ...current, [task.id]: [] }));
    } catch (caughtError) {
      if (caughtError instanceof Error) {
        setError(caughtError.message);
      } else {
        setError(`Unable to save an answer for "${task.prompt_text}" right now.`);
      }
    } finally {
      setSavingTaskId(null);
    }
  }

  return (
    <main className="page-shell">
      <section className="panel-card">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Questions</p>
            <h1>Resolve unknown prompts</h1>
            <p className="supporting-copy">
              Anything missing from your memory lands here so the system can learn it once and stop flagging it as new.
            </p>
          </div>
        </div>
        {error ? <p className="error-copy">{error}</p> : null}

        {tasks.length === 0 ? (
          <p className="empty-copy">No unresolved question tasks right now.</p>
        ) : (
          <ul className="stack-list">
            {tasks.map((task) => (
              <li key={task.id} className="question-task-card">
                <div>
                  <strong>{task.prompt_text}</strong>
                  <p className="muted-copy">
                    {describeFieldType(task)} • {task.field_type} • {task.status}
                  </p>
                  {task.option_labels.length > 0 ? (
                    <ul className="question-option-list" aria-label={`Choices for task ${task.id}`}>
                      {task.option_labels.map((optionLabel) => (
                        <li key={optionLabel} className="question-option-pill">
                          {optionLabel}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </div>
                <div className="question-task-actions question-task-actions-column">
                  <label className="question-select-shell">
                    <span className="sr-only">Answer entry for task {task.id}</span>
                    <select
                      aria-label={`Answer entry for task ${task.id}`}
                      className="question-answer-select"
                      defaultValue=""
                      onChange={(event) => {
                        if (!event.target.value) {
                          return;
                        }
                        void resolveTask(task.id, Number(event.target.value));
                      }}
                    >
                      <option value="">Link an existing answer</option>
                      {answers.map((answer) => (
                        <option key={answer.id} value={answer.id}>
                          {answer.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <div className="question-inline-form">
                    <input
                      aria-label={`Label for task ${task.id}`}
                      className="question-inline-input"
                      placeholder="Answer label"
                      value={draftLabels[task.id] ?? task.prompt_text}
                      onChange={(event) =>
                        setDraftLabels((current) => ({ ...current, [task.id]: event.target.value }))
                      }
                    />
                    {isMultiSelectField(task) && task.option_labels.length > 0 ? (
                      <fieldset className="question-choice-group">
                        <legend className="sr-only">Answer choices for task {task.id}</legend>
                        {task.option_labels.map((optionLabel) => {
                          const selectedValues = draftMultiValues[task.id] ?? [];
                          const checked = selectedValues.includes(optionLabel);
                          return (
                            <label key={optionLabel} className="question-choice-pill">
                              <input
                                type="checkbox"
                                checked={checked}
                                onChange={(event) => {
                                  setDraftMultiValues((current) => {
                                    const currentValues = current[task.id] ?? [];
                                    if (event.target.checked) {
                                      return { ...current, [task.id]: [...currentValues, optionLabel] };
                                    }
                                    return {
                                      ...current,
                                      [task.id]: currentValues.filter((value) => value !== optionLabel),
                                    };
                                  });
                                }}
                              />
                              <span>{optionLabel}</span>
                            </label>
                          );
                        })}
                      </fieldset>
                    ) : isSingleSelectField(task) && task.option_labels.length > 0 ? (
                      <label className="question-select-shell">
                        <span className="sr-only">New answer choice for task {task.id}</span>
                        <select
                          aria-label={`New answer choice for task ${task.id}`}
                          className="question-answer-select"
                          value={draftSingleValues[task.id] ?? ""}
                          onChange={(event) =>
                            setDraftSingleValues((current) => ({
                              ...current,
                              [task.id]: event.target.value,
                            }))
                          }
                        >
                          <option value="">Choose one option</option>
                          {task.option_labels.map((optionLabel) => (
                            <option key={optionLabel} value={optionLabel}>
                              {optionLabel}
                            </option>
                          ))}
                        </select>
                      </label>
                    ) : (
                      <textarea
                        aria-label={`New answer text for task ${task.id}`}
                        className="question-inline-textarea"
                        placeholder="Type the answer you want OpenJob to remember"
                        rows={3}
                        value={draftTexts[task.id] ?? ""}
                        onChange={(event) =>
                          setDraftTexts((current) => ({ ...current, [task.id]: event.target.value }))
                        }
                      />
                    )}
                    <button
                      type="button"
                      className="secondary-button"
                      disabled={savingTaskId === task.id}
                      onClick={() => void createAndLinkAnswer(task)}
                    >
                      {savingTaskId === task.id ? "Saving..." : "Save and link"}
                    </button>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
