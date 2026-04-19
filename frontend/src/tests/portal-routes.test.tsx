import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RouterProvider } from "react-router-dom";

import { createMemoryAppRouter } from "../app/router";
import type {
  ActionNeededItem,
  AnswerFileUploadPayload,
  AppApi,
  AnswerEntry,
  ApplicationAccount,
  JobDetail,
  JobListItem,
  QuestionAlias,
  QuestionTask,
  RoleProfile,
  Source,
  SourceSyncResult,
  TriggerApplicationRunResult,
} from "../lib/api";

beforeEach(() => {
  window.localStorage.clear();
});

function createMockApi(overrides?: Partial<AppApi>): AppApi {
  const sources: Source[] = [
    {
      id: 1,
      source_key: "greenhouse",
      source_type: "greenhouse_board",
      name: "Greenhouse",
      base_url: "https://boards.greenhouse.io/acme",
      settings: {},
      active: true,
      auto_sync_enabled: true,
      sync_interval_hours: 6,
      last_synced_at: "2026-04-08T08:00:00Z",
      next_sync_at: "2026-04-08T14:00:00Z",
    },
  ];
  const answers: AnswerEntry[] = [
    {
      id: 1,
      question_template_id: 10,
      label: "Portfolio URL",
      answer_text: "https://example.com",
      answer_payload: {},
    },
  ];
  const applicationAccounts: ApplicationAccount[] = [
    {
      id: 1,
      platform_family: "icims",
      platform_label: "iCIMS",
      tenant_host: "acme.icims.com",
      login_identifier_masked: "o***r@example.com",
      credential_status: "ready",
      last_successful_at: "2026-04-08T09:00:00Z",
      last_failure_at: null,
      last_failure_message: null,
    },
  ];
  const questions: QuestionTask[] = [
    {
      id: 1,
      question_template_id: 10,
      question_fingerprint: "portfolio",
      prompt_text: "Portfolio URL",
      field_type: "input_text",
      option_labels: [],
      status: "new",
      linked_answer_entry_id: null,
    },
  ];
  const questionAliases: QuestionAlias[] = [];
  const jobs: JobListItem[] = [
    {
      id: 1,
      canonical_key: "acme-se-i",
      company_name: "Acme",
      title: "Software Engineer I",
      location: "Remote",
      status: "discovered",
      relevance_decision: "match",
      relevance_source: "ai",
      relevance_score: 0.92,
      relevance_summary: "Strong match.",
      relevance_failure_cause: null,
      relevance_decision_phase: null,
      preferred_apply_target_type: "greenhouse_apply",
      preferred_apply_target_platform_family: "greenhouse",
      preferred_apply_target_platform_label: "Greenhouse",
      preferred_apply_target_driver_family: "direct_api",
      preferred_apply_target_credential_policy: "not_needed",
      preferred_apply_target_readiness_status: "ready",
      preferred_apply_target_readiness_reason: null,
      sighting_count: 2,
      open_question_task_count: 1,
      latest_application_run_status: null,
    },
  ];
  const jobDetail: JobDetail = {
    id: 1,
    canonical_key: "acme-se-i",
    company_name: "Acme",
    title: "Software Engineer I",
    location: "Remote",
    status: "discovered",
    relevance_decision: "match",
    relevance_source: "ai",
    relevance_score: 0.92,
    relevance_summary: "Strong match.",
    relevance_failure_cause: null,
    relevance_decision_phase: null,
    sightings: [],
    preferred_apply_target: {
      id: 1,
      target_type: "greenhouse_apply",
      destination_url: "https://boards.greenhouse.io/acme/jobs/1",
      is_preferred: true,
      platform_family: "greenhouse",
      platform_label: "Greenhouse",
      driver_family: "direct_api",
      credential_policy: "not_needed",
      readiness_status: "ready",
      readiness_reason: null,
      tenant_host: "boards.greenhouse.io",
    },
    question_tasks: [],
    application_runs: [],
    relevance_evaluations: [
      {
        id: 1,
        decision: "match",
        source: "ai",
        score: 0.92,
        summary: "Strong match.",
        matched_signals: ["software engineer i"],
        concerns: [],
        model_name: "groq-test",
        failure_cause: null,
        decision_phase: null,
      },
    ],
  };
  const roleProfile: RoleProfile = {
    id: 1,
    prompt: "new grad backend software engineer",
    generated_titles: ["Software Engineer I"],
    generated_keywords: ["new grad", "backend"],
  };
  const actionNeeded: ActionNeededItem[] = [
    {
      application_run_id: 7,
      job_id: 1,
      company_name: "Acme",
      title: "Software Engineer I",
      target_type: "linkedin_easy_apply",
      run_status: "cooldown_required",
      blocker_type: "cooldown_required",
      last_step: "review",
      message: "LinkedIn asked us to slow down.",
      artifact_paths: ["/tmp/openjob/run-7/page_html.html"],
    },
  ];

  const api: AppApi = {
    getSession: async () => ({ authenticated: true, email: "owner@example.com" }),
    login: async () => ({ authenticated: true, email: "owner@example.com" }),
    logout: async () => undefined,
    listSources: async () => sources,
    createSource: async (payload) => {
      const { sync_interval_hours, ...rest } = payload;
      const next = {
        id: sources.length + 1,
        ...rest,
        sync_interval_hours: sync_interval_hours ?? 6,
        last_synced_at: null,
        next_sync_at: payload.active && payload.auto_sync_enabled ? "2026-04-08T14:00:00Z" : null,
      };
      sources.push(next);
      return next;
    },
    updateSource: async (sourceId, payload) => {
      const source = sources.find((item) => item.id === sourceId)!;
      Object.assign(source, payload);
      return source;
    },
    deleteSource: async (sourceId) => {
      const index = sources.findIndex((item) => item.id === sourceId);
      if (index >= 0) {
        sources.splice(index, 1);
      }
    },
    syncSource: async (sourceId) => {
      const source = sources.find((item) => item.id === sourceId)!;
      source.last_synced_at = "2026-04-08T10:30:00Z";
      source.next_sync_at = source.active && source.auto_sync_enabled ? "2026-04-08T16:30:00Z" : null;
      const summary: SourceSyncResult = {
        source_id: source.id,
        source_key: source.source_key,
        source_type: source.source_type,
        processed: 6,
        created: 2,
        updated: 4,
        pending_title_screening: 1,
        pending_full_relevance: 3,
        last_synced_at: source.last_synced_at,
        next_sync_at: source.next_sync_at,
      };
      return summary;
    },
    getRoleProfile: async () => roleProfile,
    saveRoleProfile: async (payload) => ({ id: 1, ...payload }),
    listApplicationAccounts: async () => applicationAccounts,
    createApplicationAccount: async (payload) => {
      const next: ApplicationAccount = {
        id: applicationAccounts.length + 1,
        platform_family: payload.platform_family,
        platform_label: payload.platform_family === "jobvite" ? "Jobvite" : payload.platform_family,
        tenant_host: payload.tenant_host ?? "",
        login_identifier_masked: "n*****r@example.com",
        credential_status: "ready",
        last_successful_at: null,
        last_failure_at: null,
        last_failure_message: null,
      };
      applicationAccounts.push(next);
      return next;
    },
    updateApplicationAccount: async (applicationAccountId, payload) => {
      const account = applicationAccounts.find((item) => item.id === applicationAccountId)!;
      account.platform_family = payload.platform_family;
      account.platform_label = payload.platform_family === "jobvite" ? "Jobvite" : payload.platform_family;
      account.tenant_host = payload.tenant_host ?? "";
      if (payload.login_identifier) {
        account.login_identifier_masked = "u*****d@example.com";
      }
      account.credential_status = "ready";
      account.last_failure_at = null;
      account.last_failure_message = null;
      return account;
    },
    deleteApplicationAccount: async (applicationAccountId) => {
      const index = applicationAccounts.findIndex((item) => item.id === applicationAccountId);
      if (index >= 0) {
        applicationAccounts.splice(index, 1);
      }
    },
    listAnswers: async () => answers,
    createAnswer: async (payload) => {
      const next = { id: answers.length + 1, ...payload };
      answers.push(next);
      return next;
    },
    uploadAnswerFile: async (payload: AnswerFileUploadPayload) => {
      const next = {
        id: answers.length + 1,
        question_template_id: payload.question_template_id,
        label: payload.label,
        answer_text: null,
        answer_payload: {
          kind: "file",
          filename: payload.file.name,
          mime_type: payload.file.type || "application/octet-stream",
        },
      };
      answers.push(next);
      return next;
    },
    updateAnswer: async (answerId, payload) => {
      const answer = answers.find((item) => item.id === answerId)!;
      Object.assign(answer, payload);
      return answer;
    },
    listQuestionTasks: async () => questions,
    listQuestionAliases: async () => questionAliases,
    updateQuestionAlias: async (aliasId, status) => ({
      id: aliasId,
      source_fingerprint: "source",
      canonical_fingerprint: "canonical",
      source_prompt: "Source prompt",
      canonical_prompt: "Canonical prompt",
      status,
      similarity_score: 0,
    }),
    resolveQuestionTask: async (taskId, payload) => {
      const task = questions.find((item) => item.id === taskId)!;
      task.status = payload.status;
      task.linked_answer_entry_id = payload.linked_answer_entry_id;
      return task;
    },
    listJobs: async () => jobs,
    getJobDetail: async () => jobDetail,
    updateJobRelevance: async (jobId, payload) => {
      const job = jobs.find((item) => item.id === jobId)!;
      job.relevance_decision = payload.decision;
      job.relevance_source = payload.decision === "reject" ? "manual_exclude" : "manual_include";
      job.relevance_score = null;
      job.relevance_summary = payload.summary ?? `Updated to ${payload.decision}`;
      job.relevance_failure_cause = null;
      jobDetail.relevance_decision = job.relevance_decision;
      jobDetail.relevance_source = job.relevance_source;
      jobDetail.relevance_score = job.relevance_score;
      jobDetail.relevance_summary = job.relevance_summary;
      jobDetail.relevance_failure_cause = job.relevance_failure_cause;
      return {
        job_id: jobId,
        relevance_decision: job.relevance_decision,
        relevance_source: job.relevance_source,
        relevance_score: job.relevance_score,
        relevance_summary: job.relevance_summary,
        relevance_failure_cause: job.relevance_failure_cause,
        relevance_decision_phase: null,
      };
    },
    rescoreJob: async (jobId) => ({
      job_id: jobId,
      relevance_decision: "review",
      relevance_source: "ai",
      relevance_score: 0.5,
      relevance_summary: "Needs review.",
      relevance_failure_cause: null,
      relevance_decision_phase: null,
    }),
    triggerJobApplication: async (jobId) => {
      const job = jobs.find((item) => item.id === jobId)!;
      job.latest_application_run_status = "submitted";
      const run: TriggerApplicationRunResult = {
        application_run_id: 99,
        status: "submitted",
        answer_entry_ids: [1],
        created_question_task_ids: [],
      };
      return run;
    },
    listActionNeeded: async () => actionNeeded,
    listSystemEvents: async () => [],
    getApplicationRunLog: async () => ({ application_run_id: 0, job_id: 0, status: "", apply_target_type: null, started_at: "", completed_at: null, events: [], question_answer_map: [] }),
    ...overrides,
  };

  return {
    ...api,
    uploadAnswerFile: overrides?.uploadAnswerFile ?? api.uploadAnswerFile,
  };
}

test("renders the jobs route inside the portal layout", async () => {
  const router = createMemoryAppRouter(createMockApi(), ["/jobs"]);

  render(<RouterProvider router={router} />);

  expect(await screen.findByRole("heading", { name: /tracked opportunities/i })).toBeInTheDocument();
  expect(await screen.findByRole("link", { name: /acme/i })).toBeInTheDocument();
  expect(await screen.findAllByText(/greenhouse/i)).not.toHaveLength(0);
  expect(await screen.findByRole("button", { name: /run now/i })).toBeInTheDocument();
});

test("creates a new source from the sources screen", async () => {
  const user = userEvent.setup();
  const router = createMemoryAppRouter(createMockApi(), ["/sources"]);

  render(<RouterProvider router={router} />);

  await screen.findByRole("heading", { name: /discovery inputs/i });

  await user.type(screen.getByLabelText(/source key/i), "lever");
  await user.type(screen.getByLabelText(/^name$/i), "Lever");
  await user.selectOptions(screen.getByLabelText(/source type/i), "lever_postings");
  await user.type(screen.getByLabelText(/base url/i), "https://jobs.lever.co/acme");
  await user.click(screen.getByRole("button", { name: /show advanced settings/i }));
  await user.clear(screen.getByLabelText(/settings json/i));
  fireEvent.change(screen.getByLabelText(/settings json/i), {
    target: { value: '{"company_slug":"acme"}' },
  });
  await user.click(screen.getByRole("button", { name: /save source/i }));
  await user.click(screen.getAllByRole("button", { name: /show details/i })[1]);

  await waitFor(() => {
    expect(screen.getByText("https://jobs.lever.co/acme")).toBeInTheDocument();
  });
});

test("edits an existing source from the sources screen", async () => {
  const user = userEvent.setup();
  const router = createMemoryAppRouter(createMockApi(), ["/sources"]);

  render(<RouterProvider router={router} />);

  await screen.findByRole("heading", { name: /discovery inputs/i });
  await user.click(await screen.findByRole("button", { name: /^edit$/i }));

  const baseUrlField = screen.getByLabelText(/base url/i);
  await user.clear(baseUrlField);
  await user.type(
    baseUrlField,
    "https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/README.md",
  );
  await user.click(screen.getByRole("button", { name: /show advanced settings/i }));
  await user.clear(screen.getByLabelText(/settings json/i));
  fireEvent.change(screen.getByLabelText(/settings json/i), {
    target: { value: '{"board_token":"updated-token"}' },
  });
  await user.click(screen.getByRole("button", { name: /save changes/i }));

  await waitFor(() => {
    expect(
      screen.getByText((value) =>
        value.includes("https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/README.md"),
      ),
    ).toBeInTheDocument();
  });
  expect(screen.getByText(/greenhouse updated\./i)).toBeInTheDocument();
  expect(screen.getAllByText(/"board_token": "updated-token"/i)).not.toHaveLength(0);
  expect(screen.getByRole("heading", { name: /edit source/i })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /save changes/i })).toBeInTheDocument();
});

test("edits the sync interval from the sources screen", async () => {
  const user = userEvent.setup();
  const router = createMemoryAppRouter(createMockApi(), ["/sources"]);

  render(<RouterProvider router={router} />);

  await screen.findByRole("heading", { name: /discovery inputs/i });
  await user.click(await screen.findByRole("button", { name: /^edit$/i }));

  const syncIntervalField = screen.getByRole("textbox", { name: /sync every hours/i });
  await user.clear(syncIntervalField);
  await user.type(syncIntervalField, "12");
  await user.click(screen.getByRole("button", { name: /save changes/i }));

  await waitFor(() => {
    expect(screen.getByText(/auto-sync every 12 hours/i)).toBeInTheDocument();
  });
});

test("expanded source details reflect saved status config after edit", async () => {
  const user = userEvent.setup();
  const router = createMemoryAppRouter(createMockApi(), ["/sources"]);

  render(<RouterProvider router={router} />);

  await screen.findByRole("heading", { name: /discovery inputs/i });
  await user.click(await screen.findByRole("button", { name: /^edit$/i }));
  await user.click(screen.getByRole("checkbox", { name: /auto-sync/i }));
  await user.clear(screen.getByRole("textbox", { name: /sync every hours/i }));
  await user.type(screen.getByRole("textbox", { name: /sync every hours/i }), "18");
  await user.click(screen.getByRole("button", { name: /save changes/i }));

  expect(screen.getByText(/^auto-sync off$/i)).toBeInTheDocument();
  expect(screen.getByText(/active with auto-sync off/i)).toBeInTheDocument();
  expect(screen.getByText(/every 18 hours/i)).toBeInTheDocument();
});

test("allows editing the sync interval while auto-sync is off", async () => {
  const user = userEvent.setup();
  const router = createMemoryAppRouter(createMockApi(), ["/sources"]);

  render(<RouterProvider router={router} />);

  await screen.findByRole("heading", { name: /discovery inputs/i });
  await user.click(await screen.findByRole("button", { name: /^edit$/i }));
  await user.click(screen.getByRole("checkbox", { name: /auto-sync/i }));

  const syncIntervalField = screen.getByRole("textbox", { name: /sync every hours/i });
  expect(syncIntervalField).toBeEnabled();
  await user.clear(syncIntervalField);
  await user.type(syncIntervalField, "18");
  expect(syncIntervalField).toHaveValue("18");
});

test("normalizes github blob urls when editing a github curated source", async () => {
  const user = userEvent.setup();
  let savedBaseUrl = "";
  const router = createMemoryAppRouter(
    createMockApi({
      listSources: async () => [
        {
          id: 1,
          source_key: "simplify-new-grad",
          source_type: "github_curated",
          name: "SimplifyJobs New Grad",
          base_url: "https://github.com/SimplifyJobs/New-Grad-Positions/blob/dev/README.md",
          settings: {},
          active: true,
          auto_sync_enabled: true,
          sync_interval_hours: 6,
          last_synced_at: null,
          next_sync_at: "2026-04-08T14:00:00Z",
        },
      ],
      updateSource: async (sourceId, payload) => {
        savedBaseUrl = payload.base_url ?? "";
        const { sync_interval_hours, ...rest } = payload;
        return {
          id: sourceId,
          ...rest,
          sync_interval_hours: sync_interval_hours ?? 6,
          last_synced_at: null,
          next_sync_at: payload.active && payload.auto_sync_enabled ? "2026-04-08T14:00:00Z" : null,
        };
      },
    }),
    ["/sources"],
  );

  render(<RouterProvider router={router} />);

  await screen.findByRole("heading", { name: /discovery inputs/i });
  await user.click(await screen.findByRole("button", { name: /^edit$/i }));
  await user.click(screen.getByRole("button", { name: /save changes/i }));

  await waitFor(() => {
    expect(savedBaseUrl).toBe(
      "https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/README.md",
    );
  });
});

test("shows a specific validation message for invalid settings json", async () => {
  const user = userEvent.setup();
  const router = createMemoryAppRouter(createMockApi(), ["/sources"]);

  render(<RouterProvider router={router} />);

  await screen.findByRole("heading", { name: /discovery inputs/i });
  await user.type(screen.getByLabelText(/source key/i), "bad-json");
  await user.type(screen.getByLabelText(/^name$/i), "Bad JSON");
  await user.click(screen.getByRole("button", { name: /show advanced settings/i }));
  await user.clear(screen.getByLabelText(/settings json/i));
  fireEvent.change(screen.getByLabelText(/settings json/i), {
    target: { value: "not-json" },
  });
  await user.click(screen.getByRole("button", { name: /save source/i }));

  await waitFor(() => {
    expect(screen.getByText(/settings json is invalid/i)).toBeInTheDocument();
  });
});

test("syncs a source from the sources screen", async () => {
  const user = userEvent.setup();
  const router = createMemoryAppRouter(createMockApi(), ["/sources"]);

  render(<RouterProvider router={router} />);

  await screen.findByRole("heading", { name: /discovery inputs/i });
  await user.click(await screen.findByRole("button", { name: /sync now/i }));

  await waitFor(() => {
    expect(screen.getByText(/greenhouse synced: 6 processed, 2 new, 4 updated/i)).toBeInTheDocument();
  });
});

test("manual sync updates the displayed last sync timestamp", async () => {
  const user = userEvent.setup();
  const router = createMemoryAppRouter(createMockApi(), ["/sources"]);

  render(<RouterProvider router={router} />);

  await screen.findByRole("heading", { name: /discovery inputs/i });
  await user.click(await screen.findByRole("button", { name: /show details/i }));

  expect(screen.getByText("4/8/2026, 4:00:00 AM")).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: /sync now/i }));

  await waitFor(() => {
    expect(screen.getByText("4/8/2026, 6:30:00 AM")).toBeInTheDocument();
  });
  expect(screen.getByText("4/8/2026, 12:30:00 PM")).toBeInTheDocument();
});

test("manual sync keeps the returned timestamp even if the next source refresh is stale", async () => {
  const user = userEvent.setup();
  const staleSources: Source[] = [
    {
      id: 1,
      source_key: "greenhouse",
      source_type: "greenhouse_board",
      name: "Greenhouse",
      base_url: "https://boards.greenhouse.io/acme",
      settings: {},
      active: true,
      auto_sync_enabled: true,
      sync_interval_hours: 6,
      last_synced_at: "2026-04-08T08:00:00Z",
      next_sync_at: "2026-04-08T14:00:00Z",
    },
  ];
  let listCallCount = 0;
  const router = createMemoryAppRouter(
    createMockApi({
      listSources: async () => {
        listCallCount += 1;
        return staleSources;
      },
      syncSource: async () => ({
        source_id: 1,
        source_key: "greenhouse",
        source_type: "greenhouse_board",
        processed: 6,
        created: 2,
        updated: 4,
        pending_title_screening: 1,
        pending_full_relevance: 3,
        last_synced_at: "2026-04-08T10:30:00Z",
        next_sync_at: "2026-04-08T16:30:00Z",
      }),
    }),
    ["/sources"],
  );

  render(<RouterProvider router={router} />);

  await screen.findByRole("heading", { name: /discovery inputs/i });
  await user.click(await screen.findByRole("button", { name: /show details/i }));
  await user.click(screen.getByRole("button", { name: /sync now/i }));

  await waitFor(() => {
    expect(screen.getByText("4/8/2026, 6:30:00 AM")).toBeInTheDocument();
  });
  expect(listCallCount).toBeGreaterThan(1);
});

test("shows auto-sync controls and sync schedule details on the sources screen", async () => {
  const user = userEvent.setup();
  const router = createMemoryAppRouter(createMockApi(), ["/sources"]);

  render(<RouterProvider router={router} />);

  await screen.findByRole("heading", { name: /discovery inputs/i });
  await screen.findByRole("button", { name: /show details/i });
  expect(screen.getByLabelText(/auto-sync/i)).toBeInTheDocument();
  expect(screen.getByLabelText(/sync every/i)).toBeInTheDocument();
  expect(screen.queryByText(/last sync/i)).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: /show details/i }));
  expect(screen.getByText(/last sync/i)).toBeInTheDocument();
  expect(screen.getByText(/next sync/i)).toBeInTheDocument();
});

test("uses the selected timezone when rendering source sync timestamps", async () => {
  const user = userEvent.setup();
  window.localStorage.setItem("openjob.portal.timezone", "America/Los_Angeles");
  const router = createMemoryAppRouter(createMockApi(), ["/sources"]);

  render(<RouterProvider router={router} />);

  await screen.findByRole("heading", { name: /discovery inputs/i });
  await user.click(await screen.findByRole("button", { name: /show details/i }));

  expect(screen.getByText("America/Los_Angeles")).toBeInTheDocument();
  expect(screen.getByText("4/8/2026, 1:00:00 AM")).toBeInTheDocument();
  expect(screen.getByText("4/8/2026, 7:00:00 AM")).toBeInTheDocument();
});

test("treats naive source timestamps from the API as UTC before applying the chosen timezone", async () => {
  const user = userEvent.setup();
  window.localStorage.setItem("openjob.portal.timezone", "America/Los_Angeles");
  const router = createMemoryAppRouter(
    createMockApi({
      listSources: async () => [
        {
          id: 1,
          source_key: "greenhouse",
          source_type: "greenhouse_board",
          name: "Greenhouse",
          base_url: "https://boards.greenhouse.io/acme",
          settings: {},
          active: true,
          auto_sync_enabled: true,
          sync_interval_hours: 6,
          last_synced_at: "2026-04-08T08:00:00",
          next_sync_at: "2026-04-08T14:00:00",
        },
      ],
    }),
    ["/sources"],
  );

  render(<RouterProvider router={router} />);

  await screen.findByRole("heading", { name: /discovery inputs/i });
  await user.click(await screen.findByRole("button", { name: /show details/i }));

  expect(screen.getByText("4/8/2026, 1:00:00 AM")).toBeInTheDocument();
  expect(screen.getByText("4/8/2026, 7:00:00 AM")).toBeInTheDocument();
});

test("disables manual sync affordance for inactive sources", async () => {
  const user = userEvent.setup();
  const router = createMemoryAppRouter(
    createMockApi({
      listSources: async () => [
        {
          id: 1,
          source_key: "paused-source",
          source_type: "greenhouse_board",
          name: "Paused Source",
          base_url: "https://boards.greenhouse.io/paused",
          settings: {},
          active: false,
          auto_sync_enabled: true,
          sync_interval_hours: 6,
          last_synced_at: null,
          next_sync_at: null,
        },
      ],
    }),
    ["/sources"],
  );

  render(<RouterProvider router={router} />);

  expect(await screen.findByRole("button", { name: /reactivate to sync/i })).toBeDisabled();
  await user.click(screen.getByRole("button", { name: /show details/i }));
  expect(screen.getByText(/scheduled and manual sync are paused/i)).toBeInTheDocument();
});

test("deletes a source from the sources screen", async () => {
  const user = userEvent.setup();
  const router = createMemoryAppRouter(createMockApi(), ["/sources"]);

  render(<RouterProvider router={router} />);

  await screen.findByRole("heading", { name: /discovery inputs/i });
  await user.click(await screen.findByRole("button", { name: /delete/i }));
  expect(screen.getByText(/delete source\?/i)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: /delete source/i }));

  await waitFor(() => {
    expect(screen.getByText(/no sources configured yet\./i)).toBeInTheDocument();
  });
  expect(screen.getByText(/greenhouse deleted\./i)).toBeInTheDocument();
});

test("saves the role profile from the role-profile screen", async () => {
  const user = userEvent.setup();
  let savedPrompt = "";
  let savedTitles: string[] = ["unexpected"];
  const router = createMemoryAppRouter(
    createMockApi({
      saveRoleProfile: async (payload) => {
        savedPrompt = payload.prompt;
        savedTitles = payload.generated_titles;
        return { id: 1, ...payload };
      },
    }),
    ["/role-profile"],
  );

  render(<RouterProvider router={router} />);

  expect(await screen.findByRole("heading", { name: /centralized user profile/i })).toBeInTheDocument();
  const promptField = await screen.findByLabelText(/prompt/i);
  fireEvent.change(promptField, {
    target: { value: "early career platform engineer" },
  });
  await user.click(screen.getByRole("button", { name: /save role profile/i }));

  await waitFor(() => {
    expect(screen.getByText(/^saved$/i)).toBeInTheDocument();
  });
  expect(savedPrompt).toBe("early career platform engineer");
  expect(savedTitles).toEqual([]);
});

test("role profile screen no longer shows generated title controls", async () => {
  const router = createMemoryAppRouter(createMockApi(), ["/role-profile"]);

  render(<RouterProvider router={router} />);

  await screen.findByRole("heading", { name: /centralized user profile/i });
  expect(screen.getByRole("tab", { name: /role profile/i })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByRole("tab", { name: /saved answers/i })).toHaveAttribute("aria-selected", "false");

  expect(screen.queryByRole("button", { name: /generate with ai/i })).not.toBeInTheDocument();
  expect(screen.queryByLabelText(/generated titles/i)).not.toBeInTheDocument();
  expect(screen.getByText(/screened in ai batches against this prompt first/i)).toBeInTheDocument();
});

test("answers live under the profile screen", async () => {
  const user = userEvent.setup();
  const router = createMemoryAppRouter(createMockApi(), ["/role-profile?tab=answers"]);

  render(<RouterProvider router={router} />);

  expect(await screen.findByRole("heading", { name: /centralized user profile/i })).toBeInTheDocument();
  expect(screen.getByRole("tab", { name: /saved answers/i })).toHaveAttribute("aria-selected", "true");
  expect(await screen.findByText(/portfolio url/i)).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: /add answer/i })).toBeInTheDocument();

  await user.click(screen.getByRole("tab", { name: /role profile/i }));
  expect(screen.getByRole("tab", { name: /role profile/i })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByLabelText(/prompt/i)).toBeInTheDocument();
});

test("manages application accounts from the profile screen", async () => {
  const user = userEvent.setup();
  const router = createMemoryAppRouter(createMockApi(), ["/role-profile?tab=application-accounts"]);

  render(<RouterProvider router={router} />);

  expect(await screen.findByRole("heading", { name: /centralized user profile/i })).toBeInTheDocument();
  expect(screen.getByRole("tab", { name: /application accounts/i })).toHaveAttribute("aria-selected", "true");
  expect(await screen.findByText(/acme.icims.com/i)).toBeInTheDocument();

  await user.selectOptions(screen.getByLabelText(/^platform$/i), "jobvite");
  await user.type(screen.getByLabelText(/employer host/i), "jobs.jobvite.com");
  await user.type(screen.getByLabelText(/login email or username/i), "newuser@example.com");
  await user.type(screen.getByLabelText(/^password$/i), "hunter2");
  await user.click(screen.getByRole("button", { name: /save application account/i }));

  await waitFor(() => {
    expect(screen.getByText(/application account saved\./i)).toBeInTheDocument();
  });
  expect(screen.getByText(/jobs.jobvite.com/i)).toBeInTheDocument();

  await user.click(screen.getAllByRole("button", { name: /^edit$/i })[0]);
  expect(screen.getByLabelText(/login email or username/i)).toHaveAttribute(
    "placeholder",
    "Leave blank to keep the current login",
  );
  await user.clear(screen.getByLabelText(/employer host/i));
  await user.type(screen.getByLabelText(/employer host/i), "globex.icims.com");
  await user.type(screen.getByLabelText(/new password/i), "updated-password");
  await user.click(screen.getByRole("button", { name: /save account changes/i }));

  await waitFor(() => {
    expect(screen.getByText(/application account updated\./i)).toBeInTheDocument();
  });
  expect(screen.getByText(/globex.icims.com/i)).toBeInTheDocument();

  await user.click(screen.getAllByRole("button", { name: /^delete$/i })[0]);

  await waitFor(() => {
    expect(screen.queryByText(/^globex.icims.com$/i)).not.toBeInTheDocument();
  });
  expect(screen.getByText(/application account deleted\./i)).toBeInTheDocument();
});

test("shows action-needed runs in the operator queue", async () => {
  const router = createMemoryAppRouter(createMockApi(), ["/action-needed"]);

  render(<RouterProvider router={router} />);

  expect(await screen.findByRole("heading", { name: /action needed/i })).toBeInTheDocument();
  await waitFor(() => {
    expect(screen.getByText(/linkedin asked us to slow down/i)).toBeInTheDocument();
  });
  expect(screen.getByRole("link", { name: /open artifact/i })).toBeInTheDocument();
});

test("runs an application from the jobs screen and shows the latest status", async () => {
  const user = userEvent.setup();
  const router = createMemoryAppRouter(createMockApi(), ["/jobs"]);

  render(<RouterProvider router={router} />);

  await screen.findByRole("heading", { name: /tracked opportunities/i });
  await user.click(await screen.findByRole("button", { name: /run now/i }));

  await waitFor(() => {
    expect(screen.getByText(/application sent/i)).toBeInTheDocument();
  });
  expect(screen.getByText(/submitted through greenhouse\./i)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /open job/i })).toHaveAttribute("href", "/jobs/1");
  expect(screen.getByText(/^submitted$/i)).toBeInTheDocument();
});

test("shows discovery-only jobs as non-runnable", async () => {
  const router = createMemoryAppRouter(
    createMockApi({
      listJobs: async () => [
        {
          id: 1,
          canonical_key: "acme-se-i",
          company_name: "Acme",
          title: "Software Engineer I",
          location: "Remote",
          status: "discovered",
          relevance_decision: "match",
          relevance_source: "ai",
          relevance_score: 0.92,
          relevance_summary: "Strong match.",
          relevance_failure_cause: null,
          relevance_decision_phase: null,
          preferred_apply_target_type: "external_link",
          preferred_apply_target_platform_family: "lever",
          preferred_apply_target_platform_label: "Lever",
          preferred_apply_target_readiness_status: "manual_only",
          preferred_apply_target_readiness_reason:
            "Lever link is recognized, but this generic external target still needs a target upgrade before it can run automatically.",
          sighting_count: 2,
          open_question_task_count: 0,
          latest_application_run_status: null,
        },
      ],
    }),
    ["/jobs"],
  );

  render(<RouterProvider router={router} />);

  expect(await screen.findByText(/needs target upgrade/i)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /run now/i })).not.toBeInTheDocument();
});

test("shows a compact unsupported-platform note on jobs cards", async () => {
  const router = createMemoryAppRouter(
    createMockApi({
      listJobs: async () => [
        {
          id: 1,
          canonical_key: "acme-se-i",
          company_name: "Acme",
          title: "Software Engineer I",
          location: "Remote",
          status: "discovered",
          relevance_decision: "match",
          relevance_source: "ai",
          relevance_score: 0.92,
          relevance_summary: "Strong match.",
          relevance_failure_cause: null,
          relevance_decision_phase: null,
          preferred_apply_target_type: "external_link",
          preferred_apply_target_platform_family: "workday",
          preferred_apply_target_platform_label: "Workday",
          preferred_apply_target_compatibility_label: "Browser-compatible",
          preferred_apply_target_readiness_status: "platform_not_supported",
          preferred_apply_target_readiness_reason: "Workday is recognized but not supported yet.",
          sighting_count: 2,
          open_question_task_count: 0,
          latest_application_run_status: null,
        },
      ],
    }),
    ["/jobs"],
  );

  render(<RouterProvider router={router} />);

  expect(await screen.findByText(/workday not automated yet/i)).toBeInTheDocument();
  expect(screen.queryByText(/recognized but not supported yet/i)).not.toBeInTheDocument();
});

test("updates job relevance from the jobs screen", async () => {
  const user = userEvent.setup();
  const router = createMemoryAppRouter(createMockApi(), ["/jobs"]);

  render(<RouterProvider router={router} />);

  await screen.findByRole("button", { name: /exclude/i });
  await user.click(screen.getByRole("button", { name: /exclude/i }));

  await waitFor(() => {
    expect(screen.getByText(/marked as reject in the queue\./i)).toBeInTheDocument();
  });
});

test("shows a single recovery action for rejected jobs", async () => {
  const router = createMemoryAppRouter(
    createMockApi({
      listJobs: async () => [
        {
          id: 1,
          canonical_key: "ops-associate",
          company_name: "Acme",
          title: "Operations Associate",
          location: "Remote",
          status: "discovered",
          relevance_decision: "reject",
          relevance_source: "ai",
          relevance_score: 0.18,
          relevance_summary: "This role sits outside the software engineering profile.",
          relevance_failure_cause: null,
          relevance_decision_phase: null,
          preferred_apply_target_type: "greenhouse_apply",
          sighting_count: 1,
          open_question_task_count: 0,
          latest_application_run_status: null,
        },
      ],
    }),
    ["/jobs"],
  );

  render(<RouterProvider router={router} />);

  expect(await screen.findByRole("button", { name: /^include$/i })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /^exclude$/i })).not.toBeInTheDocument();
});

test("renders multi-select question choices and saves structured answers", async () => {
  const user = userEvent.setup();
  let savedPayload: { answer_text: string | null; answer_payload: Record<string, unknown> } | null = null;
  const router = createMemoryAppRouter(
    createMockApi({
      listQuestionTasks: async () => [
        {
          id: 2,
          question_template_id: 20,
          question_fingerprint: "hear_about_us",
          prompt_text: "How did you hear about us?",
          field_type: "multi_value_multi_select",
          option_labels: ["LinkedIn", "Referral", "School"],
          status: "new",
          linked_answer_entry_id: null,
        },
      ],
      createAnswer: async (payload) => {
        savedPayload = {
          answer_text: payload.answer_text,
          answer_payload: payload.answer_payload,
        };
        return { id: 2, ...payload };
      },
    }),
    ["/questions"],
  );

  render(<RouterProvider router={router} />);

  expect(await screen.findByText(/select one or more options/i)).toBeInTheDocument();
  expect(screen.getByLabelText(/choices for task 2/i)).toBeInTheDocument();
  await user.click(screen.getByLabelText("LinkedIn"));
  await user.click(screen.getByLabelText("School"));
  await user.click(screen.getByRole("button", { name: /save and link/i }));

  await waitFor(() => {
    expect(savedPayload).toEqual({
      answer_text: "LinkedIn, School",
      answer_payload: { values: ["LinkedIn", "School"] },
    });
  });
});

test("stages a saved answer and waits for save before linking", async () => {
  const user = userEvent.setup();
  let resolvedAnswerId: number | null = null;
  const router = createMemoryAppRouter(
    createMockApi({
      listAnswers: async () => [
        {
          id: 7,
          question_template_id: 70,
          label: "Phone",
          answer_text: "555-0100",
          answer_payload: {},
        },
      ],
      listQuestionTasks: async () => [
        {
          id: 4,
          question_template_id: 70,
          question_fingerprint: "phone",
          prompt_text: "Phone",
          field_type: "input_text",
          option_labels: [],
          status: "new",
          linked_answer_entry_id: null,
        },
      ],
      resolveQuestionTask: async (taskId, payload) => {
        resolvedAnswerId = payload.linked_answer_entry_id;
        return {
          id: taskId,
          question_template_id: 70,
          question_fingerprint: "phone",
          prompt_text: "Phone",
          field_type: "input_text",
          option_labels: [],
          status: payload.status,
          linked_answer_entry_id: payload.linked_answer_entry_id,
        };
      },
    }),
    ["/questions"],
  );

  render(<RouterProvider router={router} />);

  expect(await screen.findByText(/use a saved answer/i)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: /^phone$/i }));

  expect(screen.getByDisplayValue("555-0100")).toBeInTheDocument();
  expect(screen.getByLabelText(/label for task 4/i)).toHaveValue("Phone");
  expect(resolvedAnswerId).toBeNull();

  await user.click(screen.getByRole("button", { name: /save and link/i }));

  await waitFor(() => {
    expect(resolvedAnswerId).toBe(7);
  });
});

test("uploads and links file answers for resume questions", async () => {
  const user = userEvent.setup();
  let uploadedFileName: string | null = null;
  let resolvedAnswerId: number | null = null;
  const router = createMemoryAppRouter(
    createMockApi({
      listQuestionTasks: async () => [
        {
          id: 3,
          question_template_id: 30,
          question_fingerprint: "resume",
          prompt_text: "Resume/CV",
          field_type: "input_file",
          option_labels: [],
          status: "new",
          linked_answer_entry_id: null,
        },
      ],
      uploadAnswerFile: async (payload: AnswerFileUploadPayload) => {
        uploadedFileName = payload.file.name;
        return {
          id: 3,
          question_template_id: payload.question_template_id,
          label: payload.label,
          answer_text: null,
          answer_payload: {
            kind: "file",
            filename: payload.file.name,
            mime_type: payload.file.type || "application/octet-stream",
          },
        };
      },
      resolveQuestionTask: async (taskId, payload) => {
        resolvedAnswerId = payload.linked_answer_entry_id;
        return {
          id: taskId,
          question_template_id: 30,
          question_fingerprint: "resume",
          prompt_text: "Resume/CV",
          field_type: "input_file",
          option_labels: [],
          status: payload.status,
          linked_answer_entry_id: payload.linked_answer_entry_id,
        };
      },
    }),
    ["/questions"],
  );

  render(<RouterProvider router={router} />);

  expect(await screen.findByText(/upload a file/i)).toBeInTheDocument();
  const file = new File(["resume"], "resume.pdf", { type: "application/pdf" });
  await user.upload(screen.getByLabelText(/file upload for task 3/i), file);
  await user.click(screen.getByRole("button", { name: /upload and link/i }));

  await waitFor(() => {
    expect(uploadedFileName).toBe("resume.pdf");
  });
  expect(resolvedAnswerId).toBe(3);
});
