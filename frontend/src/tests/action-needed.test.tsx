import { render, screen, waitFor } from "@testing-library/react";
import { RouterProvider } from "react-router-dom";

import { createMemoryAppRouter } from "../app/router";
import type { AnswerFileUploadPayload, AppApi } from "../lib/api";

function buildApi(): AppApi {
  return {
    getSession: async () => ({ authenticated: true, email: "owner@example.com" }),
    login: async () => ({ authenticated: true, email: "owner@example.com" }),
    logout: async () => undefined,
    listSources: async () => [],
    createSource: async (payload) => ({ id: 1, last_synced_at: null, next_sync_at: null, sync_interval_hours: payload.sync_interval_hours ?? 6, ...payload }),
    updateSource: async (sourceId, payload) => ({ id: sourceId, last_synced_at: null, next_sync_at: null, sync_interval_hours: payload.sync_interval_hours ?? 6, ...payload }),
    deleteSource: async () => undefined,
    syncSource: async () => ({
      source_id: 1,
      source_key: "test",
      source_type: "greenhouse_board",
      processed: 0,
      created: 0,
      updated: 0,
      pending_title_screening: 0,
      pending_full_relevance: 0,
    }),
    getRoleProfile: async () => ({
      id: 1,
      prompt: "",
      generated_titles: [],
      generated_keywords: [],
    }),
    saveRoleProfile: async (payload) => ({ id: 1, ...payload }),
    listAnswers: async () => [],
    createAnswer: async (payload) => ({ id: 1, ...payload }),
    uploadAnswerFile: async (payload: AnswerFileUploadPayload) => ({
      id: 1,
      question_template_id: payload.question_template_id,
      label: payload.label,
      answer_text: null,
      answer_payload: { kind: "file", filename: payload.file.name },
    }),
    updateAnswer: async (answerId, payload) => ({ id: answerId, ...payload }),
    listQuestionTasks: async () => [],
    resolveQuestionTask: async (taskId, payload) => ({
      id: taskId,
      question_template_id: 1,
      question_fingerprint: "question",
      prompt_text: "Question",
      field_type: "input_text",
      option_labels: [],
      status: payload.status,
      linked_answer_entry_id: payload.linked_answer_entry_id,
    }),
    listJobs: async () => [],
    getJobDetail: async () => ({
      id: 1,
      canonical_key: "test",
      company_name: "Acme",
      title: "Software Engineer I",
      location: "Remote",
      status: "discovered",
      relevance_decision: "review",
      relevance_source: "ai",
      relevance_score: 0.5,
      relevance_summary: "Needs review.",
      relevance_failure_cause: null,
      sightings: [],
      preferred_apply_target: null,
      question_tasks: [],
      application_runs: [],
      relevance_evaluations: [],
    }),
    updateJobRelevance: async (jobId, payload) => ({
      job_id: jobId,
      relevance_decision: payload.decision,
      relevance_source: "manual_include",
      relevance_score: null,
      relevance_summary: payload.summary ?? null,
      relevance_failure_cause: null,
    }),
    rescoreJob: async (jobId) => ({
      job_id: jobId,
      relevance_decision: "review",
      relevance_source: "ai",
      relevance_score: 0.5,
      relevance_summary: "Needs review.",
      relevance_failure_cause: null,
    }),
    triggerJobApplication: async (jobId) => ({
      application_run_id: jobId,
      status: "queued",
      answer_entry_ids: [],
      created_question_task_ids: [],
    }),
    listActionNeeded: async () => [
      {
        application_run_id: 3,
        job_id: 1,
        company_name: "Acme",
        title: "Software Engineer I",
        target_type: "linkedin_easy_apply",
        run_status: "platform_changed",
        blocker_type: "platform_changed",
        last_step: "form-submit",
        message: "Expected submit selector missing.",
        artifact_paths: ["/tmp/openjob/run-3/page_html.html"],
      },
    ],
  };
}

test("renders action-needed queue details", async () => {
  const router = createMemoryAppRouter(buildApi(), ["/action-needed"]);

  render(<RouterProvider router={router} />);

  expect(await screen.findByRole("heading", { name: /action needed/i })).toBeInTheDocument();
  await waitFor(() => {
    expect(screen.getByText(/expected submit selector missing/i)).toBeInTheDocument();
  });
  expect(screen.getByText(/platform_changed/i)).toBeInTheDocument();
});
