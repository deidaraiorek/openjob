import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { useAppContext } from "../app/layout";
import type { JobListItem } from "../lib/api";

type JobsNotice = {
  tone: "success" | "warning" | "danger";
  eyebrow: string;
  title: string;
  body: string;
  action: { label: string; to: string } | null;
};

function formatFailureCause(value: string | null): string | null {
  if (!value) {
    return null;
  }
  const labels: Record<string, string | null> = {
    title_screening_review: null,
    provider_rate_limited: "AI provider was rate-limited",
    provider_timeout: "AI request timed out",
    provider_unavailable: "AI service is temporarily unavailable",
    provider_response_invalid: "AI response was invalid",
    config_missing: "AI provider is not configured",
    queued_for_async_relevance: null,
  };
  return labels[value] ?? value.replaceAll("_", " ");
}

function formatLabel(value: string | null, fallback = "None"): string {
  if (!value) {
    return fallback;
  }

  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatPendingPhase(value: string | null | undefined): string | null {
  if (!value) {
    return null;
  }
  if (value === "title_screening") {
    return "Waiting on AI title screening";
  }
  if (value === "full_relevance") {
    return "Waiting on full AI relevance";
  }
  return formatLabel(value);
}

type RunTone = "success" | "warning" | "danger" | "neutral" | "active";

function runStatusTone(status: string | null): RunTone {
  if (!status) return "neutral";
  if (status === "submitted") return "success";
  if (status === "blocked_missing_answer") return "warning";
  if (status === "retry_scheduled") return "warning";
  if (status === "queued" || status === "running") return "active";
  if (status === "failed" || status === "action_needed" || status === "platform_changed") return "danger";
  return "neutral";
}

function runStatusLabel(status: string | null): string {
  if (!status) return "Not run";
  const labels: Record<string, string> = {
    submitted: "Submitted",
    blocked_missing_answer: "Needs answers",
    retry_scheduled: "Retrying",
    queued: "Queued",
    running: "Running",
    failed: "Failed",
    action_needed: "Action needed",
    platform_changed: "Flow changed",
    cooldown_required: "Cooling down",
  };
  return labels[status] ?? formatLabel(status);
}

function effectiveReadinessStatus(job: JobListItem): string | null {
  if (job.preferred_apply_target_readiness_status) {
    return job.preferred_apply_target_readiness_status;
  }
  if (job.preferred_apply_target_type === "external_link") {
    return "manual_only";
  }
  if (job.preferred_apply_target_type) {
    return "ready";
  }
  return null;
}

function readinessNote(job: JobListItem): string | null {
  const status = effectiveReadinessStatus(job);
  const reason = job.preferred_apply_target_readiness_reason;
  const compatibilityLabel = job.preferred_apply_target_compatibility_label;
  if (status === "manual_only") {
    if (
      job.preferred_apply_target_type === "external_link" &&
      job.preferred_apply_target_platform_family &&
      job.preferred_apply_target_platform_family !== "external"
    ) {
      return "Needs target upgrade";
    }
    return reason ?? compatibilityLabel ?? "Discovery only";
  }
  if (status === "missing_application_account") {
    return reason ?? "Needs account";
  }
  if (status === "platform_not_supported") {
    return `${preferredTargetLabel(job)} not automated yet`;
  }
  if (status === "login_failed") {
    return reason ?? "Stored login failed";
  }
  if (status === "mfa_required") {
    return reason ?? "MFA required";
  }
  return reason ?? compatibilityLabel ?? null;
}

function canRunJob(job: JobListItem): boolean {
  return Boolean(job.preferred_apply_target_type) && effectiveReadinessStatus(job) === "ready";
}

function preferredTargetLabel(job: JobListItem): string {
  return job.preferred_apply_target_platform_label ?? formatLabel(job.preferred_apply_target_type);
}

function jobNoticeTitle(job: JobListItem): string {
  return `${job.company_name} · ${job.title}`;
}

function buildRunNotice(
  job: JobListItem,
  result: { status: string; created_question_task_ids: number[] },
): JobsNotice {
  const openJobAction = { label: "Open job", to: `/jobs/${job.id}` };

  if (result.status === "submitted") {
    return {
      tone: "success",
      eyebrow: "Application sent",
      title: jobNoticeTitle(job),
      body: `Submitted through ${preferredTargetLabel(job)}.`,
      action: openJobAction,
    };
  }

  if (result.status === "queued") {
    return {
      tone: "success",
      eyebrow: "Queued",
      title: jobNoticeTitle(job),
      body: "This application was added to the run queue. You can keep queuing other jobs while it starts in the background.",
      action: { label: "Open job", to: `/jobs/${job.id}` },
    };
  }

  if (result.status === "blocked_missing_answer") {
    const taskCount = result.created_question_task_ids.length;
    const taskLabel = taskCount === 1 ? "question" : "questions";
    return {
      tone: "warning",
      eyebrow: "Need input",
      title: jobNoticeTitle(job),
      body: `OpenJob found ${taskCount} required ${taskLabel} it still needs before this role can be submitted.`,
      action: { label: "Resolve answers", to: "/questions" },
    };
  }

  if (result.status === "retry_scheduled") {
    return {
      tone: "warning",
      eyebrow: "Retry scheduled",
      title: jobNoticeTitle(job),
      body: "The target hit a temporary issue, so this run was saved and queued for another attempt.",
      action: openJobAction,
    };
  }

  if (result.status === "action_needed") {
    return {
      tone: "warning",
      eyebrow: "Operator follow-up",
      title: jobNoticeTitle(job),
      body: "This flow needs a human step before the next automated run can continue.",
      action: { label: "Open queue", to: "/action-needed" },
    };
  }

  if (result.status === "cooldown_required") {
    return {
      tone: "warning",
      eyebrow: "Pause required",
      title: jobNoticeTitle(job),
      body: "The platform asked us to slow down before trying this application again.",
      action: { label: "Open queue", to: "/action-needed" },
    };
  }

  if (result.status === "platform_changed") {
    return {
      tone: "danger",
      eyebrow: "Flow changed",
      title: jobNoticeTitle(job),
      body: "The live application flow drifted away from the automation path we expected.",
      action: { label: "Open queue", to: "/action-needed" },
    };
  }

  if (result.status === "failed") {
    return {
      tone: "danger",
      eyebrow: "Run failed",
      title: jobNoticeTitle(job),
      body: "The run ended unexpectedly. Open the job to inspect the event history before trying again.",
      action: openJobAction,
    };
  }

  return {
    tone: "warning",
    eyebrow: "Run updated",
    title: jobNoticeTitle(job),
    body: `This run finished with ${formatLabel(result.status).toLowerCase()} status.`,
    action: openJobAction,
  };
}

function buildRunErrorNotice(job: JobListItem, caughtError: unknown): JobsNotice {
  const message =
    caughtError instanceof Error
      ? caughtError.message
      : `Unable to start an application run for ${job.company_name} ${job.title}.`;

  if (message.toLowerCase().includes("already active")) {
    return {
      tone: "warning",
      eyebrow: "Already running",
      title: jobNoticeTitle(job),
      body: "A run is already in progress for this job. Check the job detail for its current status.",
      action: { label: "Open job", to: `/jobs/${job.id}` },
    };
  }

  const action =
    message.toLowerCase().includes("application account")
      ? { label: "Open accounts", to: "/role-profile?tab=application-accounts" }
      : { label: "Open job", to: `/jobs/${job.id}` };

  return {
    tone: "danger",
    eyebrow: "Couldn't start run",
    title: jobNoticeTitle(job),
    body: message,
    action,
  };
}

function buildRelevanceNotice(
  job: JobListItem,
  decision: string,
): JobsNotice {
  return {
    tone: "success",
    eyebrow: "Relevance updated",
    title: jobNoticeTitle(job),
    body: `This role is now marked as ${formatLabel(decision).toLowerCase()} in the queue.`,
    action: { label: "Open job", to: `/jobs/${job.id}` },
  };
}

function getJobActionConfig(job: JobListItem): {
  primaryAction: { label: string; decision: "match" | "reject"; className: string };
  secondaryAction: { label: string; decision: "match" | "reject"; className: string } | null;
} {
  if (job.relevance_decision === "pending") {
    return {
      primaryAction: { label: "Include", decision: "match", className: "secondary-button" },
      secondaryAction: { label: "Exclude", decision: "reject", className: "ghost-button" },
    };
  }

  if (job.relevance_decision === "reject") {
    return {
      primaryAction: { label: "Include", decision: "match", className: "secondary-button" },
      secondaryAction: null,
    };
  }

  if (job.relevance_decision === "match") {
    return {
      primaryAction: { label: "Exclude", decision: "reject", className: "ghost-button" },
      secondaryAction: null,
    };
  }

  return {
    primaryAction: { label: "Include", decision: "match", className: "secondary-button" },
    secondaryAction: { label: "Exclude", decision: "reject", className: "ghost-button" },
  };
}

export function JobsRoute() {
  const { api } = useAppContext();
  const [jobs, setJobs] = useState<JobListItem[]>([]);
  const [relevanceFilter, setRelevanceFilter] = useState("match");
  const [notice, setNotice] = useState<JobsNotice | null>(null);
  const [noticeJobId, setNoticeJobId] = useState<number | null>(null);
  const [runningJobIds, setRunningJobIds] = useState<Set<number>>(new Set());
  const [updatingJobId, setUpdatingJobId] = useState<number | null>(null);

  async function reloadJobs() {
    setJobs(await api.listJobs(relevanceFilter));
  }

  useEffect(() => {
    void reloadJobs();
  }, [api, relevanceFilter]);

  async function handleRun(job: JobListItem) {
    setNoticeJobId(job.id);
    setNotice({
      tone: "success",
      eyebrow: "Queued",
      title: jobNoticeTitle(job),
      body: "Application queued. The AI agent will start in the background — you can keep working.",
      action: { label: "Open job", to: `/jobs/${job.id}` },
    });
    setRunningJobIds((prev) => new Set(prev).add(job.id));

    try {
      const result = await api.triggerJobApplication(job.id);
      await reloadJobs();
      if (result.status !== "queued") {
        setNotice(buildRunNotice(job, result));
      }
    } catch (caughtError) {
      setNotice(buildRunErrorNotice(job, caughtError));
    } finally {
      setRunningJobIds((prev) => { const next = new Set(prev); next.delete(job.id); return next; });
    }
  }

  async function handleRelevanceUpdate(job: JobListItem, decision: "match" | "reject") {
    setNotice(null);
    setNoticeJobId(job.id);
    setUpdatingJobId(job.id);

    try {
      const result = await api.updateJobRelevance(job.id, { decision });
      await reloadJobs();
      setNotice(buildRelevanceNotice(job, result.relevance_decision));
    } catch (caughtError) {
      setNotice({
        tone: "danger",
        eyebrow: "Couldn't update relevance",
        title: jobNoticeTitle(job),
        body:
          caughtError instanceof Error
            ? caughtError.message
            : `Unable to update relevance for ${job.company_name} ${job.title}.`,
        action: { label: "Open job", to: `/jobs/${job.id}` },
      });
    } finally {
      setUpdatingJobId(null);
    }
  }

  return (
    <main className="page-shell">
      <section className="panel-card">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Jobs</p>
            <h1>Tracked opportunities</h1>
            <p className="supporting-copy">
              One canonical view per opportunity, even when the same role appears across multiple sources.
            </p>
          </div>
          <div className="button-row">
            {[
              { key: "pending", label: "Pending" },
              { key: "match", label: "Match" },
              { key: "review", label: "Review" },
              { key: "reject", label: "Reject" },
            ].map((option) => (
              <button
                key={option.key}
                type="button"
                className={relevanceFilter === option.key ? "secondary-button" : "ghost-button"}
                onClick={() => setRelevanceFilter(option.key)}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
        {jobs.length === 0 ? (
          <p className="empty-copy">No jobs are stored yet.</p>
        ) : (
          <div className="job-board">
            {jobs.map((job) => {
              const actionConfig = getJobActionConfig(job);
              const secondaryAction = actionConfig.secondaryAction;
              const inlineReadinessNote = readinessNote(job);
              const inlineReadinessDetail =
                job.preferred_apply_target_readiness_reason ?? job.preferred_apply_target_compatibility_reason ?? null;
              const showInlineNotice = notice !== null && noticeJobId === job.id;

              return (
                <article key={job.id} className={`job-card job-card-${job.relevance_decision}`}>
                  <div className="job-card-main">
                    <div className="job-card-title-group">
                      <p className="job-company-label">{job.company_name}</p>
                      <Link
                        className="job-title-link"
                        to={`/jobs/${job.id}`}
                        aria-label={`${job.company_name} ${job.title}`}
                      >
                        {job.title}
                      </Link>
                    </div>
                    <div className="job-chip-row">
                      <span className="job-chip">{formatLabel(job.status)}</span>
                      <span className="job-chip">{preferredTargetLabel(job)}</span>
                      <span className="job-chip">
                        {job.sighting_count} sighting{job.sighting_count === 1 ? "" : "s"}
                      </span>
                      {job.preferred_apply_target_compatibility_label ? (
                        <span className="job-chip">{job.preferred_apply_target_compatibility_label}</span>
                      ) : null}
                      <span className="job-chip">
                        {job.open_question_task_count} question{job.open_question_task_count === 1 ? "" : "s"}
                      </span>
                    </div>
                  </div>

                  <div className="job-card-relevance">
                    <span className={`decision-badge decision-${job.relevance_decision}`}>
                      {formatLabel(job.relevance_decision)}
                    </span>
                    <p className="job-card-summary">{job.relevance_summary ?? "No rationale yet."}</p>
                    {job.relevance_decision === "pending" && formatPendingPhase(job.pending_relevance_phase) ? (
                      <p className="job-card-subtle">
                        {formatPendingPhase(job.pending_relevance_phase)}
                        {job.pending_relevance_attempt_count ? ` · attempt ${job.pending_relevance_attempt_count + 1}` : ""}
                      </p>
                    ) : null}
                    {job.relevance_decision !== "pending" && formatFailureCause(job.relevance_failure_cause) ? (
                      <p className="job-card-subtle">
                        Temporary issue: {formatFailureCause(job.relevance_failure_cause)}
                      </p>
                    ) : null}
                  </div>

                  <div className="job-card-meta">
                    <div className="job-stat">
                      <span className="job-stat-label">Run status</span>
                      <span className={`run-badge run-badge-${runStatusTone(job.latest_application_run_status)}`}>
                        {runStatusLabel(job.latest_application_run_status)}
                      </span>
                    </div>
                    <div className="job-stat">
                      <span className="job-stat-label">Path</span>
                      <strong>{preferredTargetLabel(job)}</strong>
                    </div>
                  </div>

                  <div className="job-card-actions">
                    <button
                      type="button"
                      className={actionConfig.primaryAction.className}
                      disabled={updatingJobId === job.id}
                      onClick={() => void handleRelevanceUpdate(job, actionConfig.primaryAction.decision)}
                    >
                      {actionConfig.primaryAction.label}
                    </button>
                    {secondaryAction ? (
                      <button
                        type="button"
                        className={secondaryAction.className}
                        disabled={updatingJobId === job.id}
                        onClick={() => void handleRelevanceUpdate(job, secondaryAction.decision)}
                      >
                        {secondaryAction.label}
                      </button>
                    ) : null}
                    {!canRunJob(job) ? (
                      <span className="job-inline-note" title={inlineReadinessDetail ?? undefined}>
                        {inlineReadinessNote ?? "Not ready yet"}
                      </span>
                    ) : (
                      <button
                        type="button"
                        onClick={() => void handleRun(job)}
                        disabled={runningJobIds.has(job.id) || !canRunJob(job)}
                      >
                        {runningJobIds.has(job.id) ? "Applying..." : "Apply"}
                      </button>
                    )}
                  </div>

                  {showInlineNotice ? (
                    <div className={`job-activity-notice job-activity-notice-${notice.tone}`} role="status" aria-live="polite">
                      <div className="job-activity-notice-copy">
                        <p className="job-activity-notice-eyebrow">{notice.eyebrow}</p>
                        <strong>{notice.title}</strong>
                        <p>{notice.body}</p>
                      </div>
                      {notice.action ? (
                        <Link className="job-activity-notice-link" to={notice.action.to}>
                          {notice.action.label}
                        </Link>
                      ) : null}
                    </div>
                  ) : null}
                </article>
              );
            })}
          </div>
        )}
      </section>
    </main>
  );
}
