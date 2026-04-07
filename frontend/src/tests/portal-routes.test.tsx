import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RouterProvider } from "react-router-dom";

import { createMemoryAppRouter } from "../app/router";
import type {
  ActionNeededItem,
  AppApi,
  AnswerEntry,
  JobDetail,
  JobListItem,
  QuestionTask,
  RoleProfile,
  Source,
  SourceSyncResult,
  TriggerApplicationRunResult,
} from "../lib/api";

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
      preferred_apply_target_type: "greenhouse_apply",
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
    sightings: [],
    preferred_apply_target: {
      id: 1,
      target_type: "greenhouse_apply",
      destination_url: "https://boards.greenhouse.io/acme/jobs/1",
      is_preferred: true,
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
      const next = { id: sources.length + 1, ...payload };
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
      const summary: SourceSyncResult = {
        source_id: source.id,
        source_key: source.source_key,
        source_type: source.source_type,
        processed: 6,
        created: 2,
        updated: 4,
      };
      return summary;
    },
    getRoleProfile: async () => roleProfile,
    saveRoleProfile: async (payload) => ({ id: 1, ...payload }),
    listAnswers: async () => answers,
    createAnswer: async (payload) => {
      const next = { id: answers.length + 1, ...payload };
      answers.push(next);
      return next;
    },
    updateAnswer: async (answerId, payload) => {
      const answer = answers.find((item) => item.id === answerId)!;
      Object.assign(answer, payload);
      return answer;
    },
    listQuestionTasks: async () => questions,
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
      };
    },
    rescoreJob: async (jobId) => ({
      job_id: jobId,
      relevance_decision: "review",
      relevance_source: "ai",
      relevance_score: 0.5,
      relevance_summary: "Needs review.",
      relevance_failure_cause: null,
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
    ...overrides,
  };

  return api;
}

test("renders the jobs route inside the portal layout", async () => {
  const router = createMemoryAppRouter(createMockApi(), ["/jobs"]);

  render(<RouterProvider router={router} />);

  expect(await screen.findByRole("heading", { name: /tracked opportunities/i })).toBeInTheDocument();
  expect(await screen.findByRole("link", { name: /acme/i })).toBeInTheDocument();
  expect(await screen.findAllByText(/greenhouse apply/i)).not.toHaveLength(0);
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
  await user.click(screen.getByRole("button", { name: /save changes/i }));

  await waitFor(() => {
    expect(
      screen.getByText((value) =>
        value.includes("https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/README.md"),
      ),
    ).toBeInTheDocument();
  });
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
        },
      ],
      updateSource: async (sourceId, payload) => {
        savedBaseUrl = payload.base_url ?? "";
        return { id: sourceId, ...payload };
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

  const promptField = await screen.findByLabelText(/prompt/i);
  fireEvent.change(promptField, {
    target: { value: "early career platform engineer" },
  });
  await user.click(screen.getByRole("button", { name: /save role profile/i }));

  await waitFor(() => {
    expect(screen.getByText(/saved/i)).toBeInTheDocument();
  });
  expect(savedPrompt).toBe("early career platform engineer");
  expect(savedTitles).toEqual([]);
});

test("role profile screen no longer shows generated title controls", async () => {
  const router = createMemoryAppRouter(createMockApi(), ["/role-profile"]);

  render(<RouterProvider router={router} />);

  await screen.findByRole("heading", { name: /targeting memory/i });

  expect(screen.queryByRole("button", { name: /generate with ai/i })).not.toBeInTheDocument();
  expect(screen.queryByLabelText(/generated titles/i)).not.toBeInTheDocument();
  expect(screen.getByText(/screened in ai batches against this prompt first/i)).toBeInTheDocument();
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
    expect(screen.getByText(/run finished with status submitted/i)).toBeInTheDocument();
  });
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
          preferred_apply_target_type: "external_link",
          sighting_count: 2,
          open_question_task_count: 0,
          latest_application_run_status: null,
        },
      ],
    }),
    ["/jobs"],
  );

  render(<RouterProvider router={router} />);

  expect(await screen.findByText(/discovery only/i)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /run now/i })).not.toBeInTheDocument();
});

test("updates job relevance from the jobs screen", async () => {
  const user = userEvent.setup();
  const router = createMemoryAppRouter(createMockApi(), ["/jobs"]);

  render(<RouterProvider router={router} />);

  await screen.findByRole("button", { name: /exclude/i });
  await user.click(screen.getByRole("button", { name: /exclude/i }));

  await waitFor(() => {
    expect(screen.getByText(/relevance updated to reject/i)).toBeInTheDocument();
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
