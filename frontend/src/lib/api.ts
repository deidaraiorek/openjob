export type SessionResponse = {
  authenticated: boolean;
  email: string | null;
};

export type Source = {
  id: number;
  source_key: string;
  source_type: string;
  name: string;
  base_url: string | null;
  settings: Record<string, unknown>;
  active: boolean;
};

export type SourceSyncResult = {
  source_id: number;
  source_key: string;
  source_type: string;
  processed: number;
  created: number;
  updated: number;
};

export type SourceCreatePayload = {
  source_key: string;
  source_type: string;
  name: string;
  base_url: string | null;
  settings: Record<string, unknown>;
  active: boolean;
};

export type SourceUpdatePayload = SourceCreatePayload;

export type RoleProfile = {
  id: number;
  prompt: string;
  generated_titles: string[];
  generated_keywords: string[];
};

export type RoleProfilePayload = {
  prompt: string;
  generated_titles: string[];
  generated_keywords: string[];
};

export type AnswerEntry = {
  id: number;
  question_template_id: number | null;
  label: string;
  answer_text: string | null;
  answer_payload: Record<string, unknown>;
};

export type AnswerCreatePayload = {
  question_template_id: number | null;
  label: string;
  answer_text: string | null;
  answer_payload: Record<string, unknown>;
};

export type AnswerUpdatePayload = AnswerCreatePayload;

export type QuestionTask = {
  id: number;
  question_template_id: number | null;
  question_fingerprint: string;
  prompt_text: string;
  field_type: string;
  option_labels: string[];
  status: string;
  linked_answer_entry_id: number | null;
};

export type ResolveQuestionTaskPayload = {
  status: string;
  linked_answer_entry_id: number | null;
};

export type JobListItem = {
  id: number;
  canonical_key: string;
  company_name: string;
  title: string;
  location: string | null;
  status: string;
  relevance_decision: string;
  relevance_source: string | null;
  relevance_score: number | null;
  relevance_summary: string | null;
  relevance_failure_cause: string | null;
  preferred_apply_target_type: string | null;
  sighting_count: number;
  open_question_task_count: number;
  latest_application_run_status: string | null;
};

export type JobDetail = {
  id: number;
  canonical_key: string;
  company_name: string;
  title: string;
  location: string | null;
  status: string;
  relevance_decision: string;
  relevance_source: string | null;
  relevance_score: number | null;
  relevance_summary: string | null;
  relevance_failure_cause: string | null;
  sightings: {
    id: number;
    source_id: number | null;
    external_job_id: string | null;
    listing_url: string;
    apply_url: string | null;
  }[];
  preferred_apply_target: {
    id: number;
    target_type: string;
    destination_url: string;
    is_preferred: boolean;
  } | null;
  question_tasks: {
    id: number;
    prompt_text: string;
    status: string;
    linked_answer_entry_id: number | null;
  }[];
  application_runs: {
    id: number;
    status: string;
    apply_target_id: number | null;
    events: { id: number; event_type: string; payload: Record<string, unknown> }[];
  }[];
  relevance_evaluations: {
    id: number;
    decision: string;
    source: string;
    score: number | null;
    summary: string | null;
    matched_signals: string[];
    concerns: string[];
    model_name: string | null;
    failure_cause: string | null;
  }[];
};

export type JobRelevanceUpdatePayload = {
  decision: string;
  summary?: string | null;
};

export type JobRelevanceUpdateResult = {
  job_id: number;
  relevance_decision: string;
  relevance_source: string | null;
  relevance_score: number | null;
  relevance_summary: string | null;
  relevance_failure_cause: string | null;
};

export type ActionNeededItem = {
  application_run_id: number;
  job_id: number;
  company_name: string;
  title: string;
  target_type: string | null;
  run_status: string;
  blocker_type: string;
  last_step: string | null;
  message: string | null;
  artifact_paths: string[];
};

export type TriggerApplicationRunResult = {
  application_run_id: number;
  status: string;
  answer_entry_ids: number[];
  created_question_task_ids: number[];
};

export type LoginPayload = {
  email: string;
  password: string;
};

export interface AuthApi {
  getSession(): Promise<SessionResponse>;
  login(payload: LoginPayload): Promise<SessionResponse>;
  logout(): Promise<void>;
}

export interface AppApi extends AuthApi {
  listSources(): Promise<Source[]>;
  createSource(payload: SourceCreatePayload): Promise<Source>;
  updateSource(sourceId: number, payload: SourceUpdatePayload): Promise<Source>;
  syncSource(sourceId: number): Promise<SourceSyncResult>;
  getRoleProfile(): Promise<RoleProfile>;
  saveRoleProfile(payload: RoleProfilePayload): Promise<RoleProfile>;
  listAnswers(): Promise<AnswerEntry[]>;
  createAnswer(payload: AnswerCreatePayload): Promise<AnswerEntry>;
  updateAnswer(answerId: number, payload: AnswerUpdatePayload): Promise<AnswerEntry>;
  listQuestionTasks(): Promise<QuestionTask[]>;
  resolveQuestionTask(taskId: number, payload: ResolveQuestionTaskPayload): Promise<QuestionTask>;
  listJobs(relevance?: string): Promise<JobListItem[]>;
  getJobDetail(jobId: number): Promise<JobDetail>;
  updateJobRelevance(jobId: number, payload: JobRelevanceUpdatePayload): Promise<JobRelevanceUpdateResult>;
  rescoreJob(jobId: number): Promise<JobRelevanceUpdateResult>;
  triggerJobApplication(jobId: number): Promise<TriggerApplicationRunResult>;
  listActionNeeded(): Promise<ActionNeededItem[]>;
}

const baseUrl = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function buildError(response: Response): Promise<Error> {
  let message = `Request failed with status ${response.status}`;

  try {
    const payload = (await response.json()) as { detail?: string | { msg?: string }[] };
    if (typeof payload.detail === "string") {
      message = payload.detail;
    } else if (Array.isArray(payload.detail) && payload.detail.length > 0) {
      const firstDetail = payload.detail[0];
      if (firstDetail && typeof firstDetail.msg === "string") {
        message = firstDetail.msg;
      }
    }
  } catch {
    // Leave the fallback message in place when the body is empty or non-JSON.
  }

  return new Error(message);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });

  if (!response.ok) {
    throw await buildError(response);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export const apiClient: AppApi = {
  getSession() {
    return request<SessionResponse>("/api/auth/session");
  },
  login(payload) {
    return request<SessionResponse>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  logout() {
    return request<void>("/api/auth/logout", { method: "POST" });
  },
  listSources() {
    return request<Source[]>("/api/sources");
  },
  createSource(payload) {
    return request<Source>("/api/sources", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  updateSource(sourceId, payload) {
    return request<Source>(`/api/sources/${sourceId}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
  },
  syncSource(sourceId) {
    return request<SourceSyncResult>(`/api/sources/${sourceId}/sync`, {
      method: "POST",
    });
  },
  getRoleProfile() {
    return request<RoleProfile>("/api/role-profile");
  },
  saveRoleProfile(payload) {
    return request<RoleProfile>("/api/role-profile", {
      method: "PUT",
      body: JSON.stringify(payload),
    });
  },
  listAnswers() {
    return request<AnswerEntry[]>("/api/answers");
  },
  createAnswer(payload) {
    return request<AnswerEntry>("/api/answers", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  updateAnswer(answerId, payload) {
    return request<AnswerEntry>(`/api/answers/${answerId}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
  },
  listQuestionTasks() {
    return request<QuestionTask[]>("/api/questions/tasks");
  },
  resolveQuestionTask(taskId, payload) {
    return request<QuestionTask>(`/api/questions/tasks/${taskId}/resolve`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },
  listJobs(relevance = "active") {
    return request<JobListItem[]>(`/api/jobs?relevance=${encodeURIComponent(relevance)}`);
  },
  getJobDetail(jobId) {
    return request<JobDetail>(`/api/jobs/${jobId}`);
  },
  updateJobRelevance(jobId, payload) {
    return request<JobRelevanceUpdateResult>(`/api/jobs/${jobId}/relevance`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },
  rescoreJob(jobId) {
    return request<JobRelevanceUpdateResult>(`/api/jobs/${jobId}/relevance/rescore`, {
      method: "POST",
    });
  },
  triggerJobApplication(jobId) {
    return request<TriggerApplicationRunResult>(`/api/applications/jobs/${jobId}/run`, {
      method: "POST",
    });
  },
  listActionNeeded() {
    return request<ActionNeededItem[]>("/api/applications/action-needed");
  },
};
