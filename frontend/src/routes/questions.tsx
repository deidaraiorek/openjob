import { useEffect, useState } from "react";

import { useAppContext } from "../app/layout";
import type { AnswerEntry, QuestionTask } from "../lib/api";

function normalizeFieldType(task: QuestionTask) {
  return task.field_type.toLowerCase();
}

function isFileField(task: QuestionTask) {
  const fieldType = normalizeFieldType(task);
  return (
    fieldType.includes("file")
    || fieldType.includes("resume")
    || fieldType.includes("attachment")
    || fieldType.includes("upload")
  );
}

function isFileAnswer(answer: AnswerEntry) {
  return answer.answer_payload.kind === "file";
}

function isMultiSelectField(task: QuestionTask) {
  const fieldType = normalizeFieldType(task);
  return !isFileField(task) && (fieldType.includes("multi_select") || fieldType.includes("checkbox"));
}

function isSingleSelectField(task: QuestionTask) {
  const fieldType = normalizeFieldType(task);
  return (
    !isFileField(task)
    && !isMultiSelectField(task)
    && (fieldType.includes("single_select") || fieldType.includes("radio"))
  );
}

function describeFieldType(task: QuestionTask) {
  if (isFileField(task)) {
    return "Upload a file";
  }
  if (isMultiSelectField(task)) {
    return "Select one or more options";
  }
  if (isSingleSelectField(task)) {
    return "Select one option";
  }
  return "Write a free-text answer";
}

function describeFileFieldHelp(task: QuestionTask) {
  if (!isFileField(task)) {
    return null;
  }
  return "Upload one reusable file now, then link it again for future applications.";
}

function describeAnswerOption(answer: AnswerEntry) {
  if (!isFileAnswer(answer)) {
    return answer.label;
  }

  const filename = typeof answer.answer_payload.filename === "string"
    ? answer.answer_payload.filename
    : null;
  return filename ? `${answer.label} (${filename})` : answer.label;
}

function describeSelectedFile(taskId: number, draftFiles: Record<number, File | null>) {
  return draftFiles[taskId]?.name ?? "No file selected";
}

function compatibleAnswersForTask(task: QuestionTask, answers: AnswerEntry[]) {
  if (isFileField(task)) {
    return answers.filter(isFileAnswer);
  }
  return answers.filter((answer) => !isFileAnswer(answer));
}

export function QuestionsRoute() {
  const { api } = useAppContext();
  const [tasks, setTasks] = useState<QuestionTask[]>([]);
  const [answers, setAnswers] = useState<AnswerEntry[]>([]);
  const [selectedExistingAnswerIds, setSelectedExistingAnswerIds] = useState<Record<number, number | null>>({});
  const [draftLabels, setDraftLabels] = useState<Record<number, string>>({});
  const [draftTexts, setDraftTexts] = useState<Record<number, string>>({});
  const [draftSingleValues, setDraftSingleValues] = useState<Record<number, string>>({});
  const [draftMultiValues, setDraftMultiValues] = useState<Record<number, string[]>>({});
  const [draftFiles, setDraftFiles] = useState<Record<number, File | null>>({});
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

  function clearSelectedExistingAnswer(taskId: number) {
    setSelectedExistingAnswerIds((current) => ({ ...current, [taskId]: null }));
  }

  function stageExistingAnswer(task: QuestionTask, answer: AnswerEntry) {
    setError(null);
    setSelectedExistingAnswerIds((current) => ({ ...current, [task.id]: answer.id }));

    if (isFileField(task)) {
      setDraftFiles((current) => ({ ...current, [task.id]: null }));
      return;
    }

    if (isMultiSelectField(task)) {
      const values = Array.isArray(answer.answer_payload.values)
        ? answer.answer_payload.values.filter((value): value is string => typeof value === "string")
        : [];
      setDraftMultiValues((current) => ({ ...current, [task.id]: values }));
      setDraftSingleValues((current) => ({ ...current, [task.id]: "" }));
      setDraftTexts((current) => ({ ...current, [task.id]: "" }));
      return;
    }

    if (isSingleSelectField(task)) {
      const value = typeof answer.answer_payload.value === "string"
        ? answer.answer_payload.value
        : (answer.answer_text ?? "");
      setDraftSingleValues((current) => ({ ...current, [task.id]: value }));
      setDraftMultiValues((current) => ({ ...current, [task.id]: [] }));
      setDraftTexts((current) => ({ ...current, [task.id]: "" }));
      return;
    }

    setDraftTexts((current) => ({ ...current, [task.id]: answer.answer_text ?? "" }));
    setDraftSingleValues((current) => ({ ...current, [task.id]: "" }));
    setDraftMultiValues((current) => ({ ...current, [task.id]: [] }));
  }

  async function createAndLinkAnswer(task: QuestionTask) {
    const label = (draftLabels[task.id] ?? task.prompt_text).trim();
    const selectedExistingAnswerId = selectedExistingAnswerIds[task.id];

    if (selectedExistingAnswerId) {
      setError(null);
      setSavingTaskId(task.id);
      try {
        await resolveTask(task.id, selectedExistingAnswerId);
        setSelectedExistingAnswerIds((current) => ({ ...current, [task.id]: null }));
        setDraftLabels((current) => ({ ...current, [task.id]: "" }));
        setDraftTexts((current) => ({ ...current, [task.id]: "" }));
        setDraftSingleValues((current) => ({ ...current, [task.id]: "" }));
        setDraftMultiValues((current) => ({ ...current, [task.id]: [] }));
        setDraftFiles((current) => ({ ...current, [task.id]: null }));
      } finally {
        setSavingTaskId(null);
      }
      return;
    }

    if (isFileField(task)) {
      const file = draftFiles[task.id];
      if (!file) {
        setError(`Choose a file for "${task.prompt_text}" before saving.`);
        return;
      }

      setError(null);
      setSavingTaskId(task.id);

      try {
        const answer = await api.uploadAnswerFile({
          question_template_id: task.question_template_id,
          label,
          file,
        });
        await resolveTask(task.id, answer.id);
        setSelectedExistingAnswerIds((current) => ({ ...current, [task.id]: null }));
        setDraftLabels((current) => ({ ...current, [task.id]: "" }));
        setDraftFiles((current) => ({ ...current, [task.id]: null }));
      } catch (caughtError) {
        if (caughtError instanceof Error) {
          setError(caughtError.message);
        } else {
          setError(`Unable to upload a file for "${task.prompt_text}" right now.`);
        }
      } finally {
        setSavingTaskId(null);
      }
      return;
    }

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
      setSelectedExistingAnswerIds((current) => ({ ...current, [task.id]: null }));
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
            {tasks.map((task) => {
              const compatibleAnswers = compatibleAnswersForTask(task, answers);
              const selectedExistingAnswerId = selectedExistingAnswerIds[task.id] ?? null;

              return (
                <li key={task.id} className="question-task-card">
                <div>
                  <strong>{task.prompt_text}</strong>
                  <p className="muted-copy">{describeFieldType(task)}</p>
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
                  {isFileField(task) ? (
                    <>
                      {compatibleAnswers.length > 0 ? (
                        <div className="question-existing-answers">
                          <p className="muted-copy question-existing-answers-label">Use a saved upload</p>
                          <div className="question-existing-answer-list">
                            {compatibleAnswers.map((answer) => (
                              <button
                                key={answer.id}
                                type="button"
                                className="question-existing-answer-button"
                                onClick={() => stageExistingAnswer(task, answer)}
                              >
                                {describeAnswerOption(answer)}
                              </button>
                            ))}
                          </div>
                        </div>
                      ) : null}
                      <div className="question-inline-form">
                        <div className="question-inline-note">
                          <p className="muted-copy">{describeFileFieldHelp(task)}</p>
                        </div>
                        <input
                          aria-label={`Label for task ${task.id}`}
                          className="question-inline-input"
                          placeholder="Answer label"
                          value={draftLabels[task.id] ?? task.prompt_text}
                          onChange={(event) =>
                            {
                              clearSelectedExistingAnswer(task.id);
                              setDraftLabels((current) => ({ ...current, [task.id]: event.target.value }));
                            }
                          }
                        />
                        <label className="question-file-input-shell">
                          <span className="question-file-input-label">Upload file</span>
                          <input
                            aria-label={`File upload for task ${task.id}`}
                            className="question-file-input"
                            type="file"
                            onChange={(event) =>
                              {
                                clearSelectedExistingAnswer(task.id);
                                setDraftFiles((current) => ({
                                  ...current,
                                  [task.id]: event.target.files?.[0] ?? null,
                                }));
                              }
                            }
                          />
                          <span className="question-file-input-row">
                            <span className="question-file-input-trigger">Select file</span>
                            <span className="question-file-input-name">
                              {describeSelectedFile(task.id, draftFiles)}
                            </span>
                          </span>
                        </label>
                        {selectedExistingAnswerId ? (
                          <p className="muted-copy">Selected saved upload: {describeAnswerOption(compatibleAnswers.find((answer) => answer.id === selectedExistingAnswerId)!)}</p>
                        ) : null}
                        <button
                          type="button"
                          className="secondary-button"
                          disabled={savingTaskId === task.id}
                          onClick={() => void createAndLinkAnswer(task)}
                        >
                          {savingTaskId === task.id ? "Uploading..." : "Upload and link"}
                        </button>
                      </div>
                    </>
                  ) : (
                    <>
                      {compatibleAnswers.length > 0 ? (
                        <div className="question-existing-answers">
                          <p className="muted-copy question-existing-answers-label">Use a saved answer</p>
                          <div className="question-existing-answer-list">
                            {compatibleAnswers.map((answer) => (
                              <button
                                key={answer.id}
                                type="button"
                                className="question-existing-answer-button"
                                onClick={() => stageExistingAnswer(task, answer)}
                              >
                                {describeAnswerOption(answer)}
                              </button>
                            ))}
                          </div>
                        </div>
                      ) : null}
                      <div className="question-inline-form">
                        <input
                          aria-label={`Label for task ${task.id}`}
                          className="question-inline-input"
                          placeholder="Answer label"
                          value={draftLabels[task.id] ?? task.prompt_text}
                          onChange={(event) =>
                            {
                              clearSelectedExistingAnswer(task.id);
                              setDraftLabels((current) => ({ ...current, [task.id]: event.target.value }));
                            }
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
                                      clearSelectedExistingAnswer(task.id);
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
                                {
                                  clearSelectedExistingAnswer(task.id);
                                  setDraftSingleValues((current) => ({
                                    ...current,
                                    [task.id]: event.target.value,
                                  }));
                                }
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
                              {
                                clearSelectedExistingAnswer(task.id);
                                setDraftTexts((current) => ({ ...current, [task.id]: event.target.value }));
                              }
                            }
                          />
                        )}
                        {selectedExistingAnswerId ? (
                          <p className="muted-copy">Selected saved answer: {describeAnswerOption(compatibleAnswers.find((answer) => answer.id === selectedExistingAnswerId)!)}</p>
                        ) : null}
                        <button
                          type="button"
                          className="secondary-button"
                          disabled={savingTaskId === task.id}
                          onClick={() => void createAndLinkAnswer(task)}
                        >
                          {savingTaskId === task.id ? "Saving..." : "Save and link"}
                        </button>
                      </div>
                    </>
                  )}
                </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </main>
  );
}
