import { render, screen, waitFor } from "@testing-library/react";
import { RouterProvider } from "react-router-dom";

import { createMemoryAppRouter } from "../app/router";
import type { AnswerFileUploadPayload, AppApi } from "../lib/api";

function buildApi(authenticated: boolean): AppApi {
  return {
    getSession: async () => ({
      authenticated,
      email: authenticated ? "owner@example.com" : null,
    }),
    login: async () => ({ authenticated: true, email: "owner@example.com" }),
    logout: async () => undefined,
    listSources: async () => [],
    createSource: async (payload) => {
      const { sync_interval_hours, ...rest } = payload;
      return { id: 1, ...rest, sync_interval_hours: sync_interval_hours ?? 6, last_synced_at: null, next_sync_at: null };
    },
    updateSource: async (sourceId, payload) => {
      const { sync_interval_hours, ...rest } = payload;
      return { id: sourceId, ...rest, sync_interval_hours: sync_interval_hours ?? 6, last_synced_at: null, next_sync_at: null };
    },
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
      last_synced_at: null,
      next_sync_at: null,
    }),
    getRoleProfile: async () => ({
      id: 1,
      prompt: "",
      generated_titles: [],
      generated_keywords: [],
    }),
    saveRoleProfile: async (payload) => ({ id: 1, ...payload }),
    listApplicationAccounts: async () => [],
    createApplicationAccount: async (payload) => ({
      id: 1,
      platform_family: payload.platform_family,
      platform_label: payload.platform_family,
      tenant_host: payload.tenant_host ?? "",
      login_identifier_masked: "o***r@example.com",
      credential_status: "ready",
      last_successful_at: null,
      last_failure_at: null,
      last_failure_message: null,
    }),
    updateApplicationAccount: async (applicationAccountId, payload) => ({
      id: applicationAccountId,
      platform_family: payload.platform_family,
      platform_label: payload.platform_family,
      tenant_host: payload.tenant_host ?? "",
      login_identifier_masked: "o***r@example.com",
      credential_status: "ready",
      last_successful_at: null,
      last_failure_at: null,
      last_failure_message: null,
    }),
    deleteApplicationAccount: async () => undefined,
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
      question_fingerprint: "test",
      prompt_text: "Test question",
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
    listActionNeeded: async () => [],
    listQuestionAliases: async () => [],
    updateQuestionAlias: async () => ({ id: 0, source_fingerprint: "", canonical_fingerprint: "", source_prompt: "", canonical_prompt: "", status: "rejected", similarity_score: 0 }),
  };
}

test("renders the login screen", async () => {
  const router = createMemoryAppRouter(buildApi(false), ["/login"]);

  render(<RouterProvider router={router} />);

  expect(await screen.findByRole("heading", { name: /owner login/i })).toBeInTheDocument();
});

test("shows dashboard for authenticated users", async () => {
  const router = createMemoryAppRouter(buildApi(true), ["/"]);

  render(<RouterProvider router={router} />);

  await waitFor(() => {
    expect(screen.getByRole("heading", { name: /welcome back/i })).toBeInTheDocument();
  });
  expect(screen.getAllByText(/owner@example.com/i)).toHaveLength(2);
});
