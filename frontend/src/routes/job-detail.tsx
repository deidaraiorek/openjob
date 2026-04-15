import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { useAppContext } from "../app/layout";
import type { JobDetail } from "../lib/api";

type ApplicationRun = JobDetail["application_runs"][number];

const RUN_STATUS_LABELS: Record<string, string> = {
  submitted: "Submitted",
  blocked_missing_answer: "Waiting on answers",
  queued: "Queued",
  running: "Running",
  failed: "Failed",
  retry_scheduled: "Retrying",
  action_needed: "Action needed",
  platform_changed: "Flow changed",
  cooldown_required: "Cooling down",
};

function runStatusLabel(status: string): string {
  return RUN_STATUS_LABELS[status] ?? status.replaceAll("_", " ");
}

function runStatusTone(status: string): string {
  if (status === "submitted") return "success";
  if (status === "blocked_missing_answer" || status === "retry_scheduled") return "warning";
  if (status === "queued" || status === "running") return "active";
  if (status === "failed" || status === "action_needed" || status === "platform_changed") return "danger";
  return "neutral";
}

function describeRun(run: ApplicationRun): string {
  const events = run.events;

  const blockedEvent = events.find((e) => e.event_type === "blocked_missing_answer");
  if (blockedEvent) {
    const ids = blockedEvent.payload.question_task_ids;
    const count = Array.isArray(ids) ? ids.length : 0;
    return count > 0
      ? `${count} required question${count === 1 ? "" : "s"} still need answering.`
      : "Some required questions still need answering.";
  }

  const failedEvent = events.find((e) => e.event_type === "failed");
  if (failedEvent) {
    const msg = typeof failedEvent.payload.message === "string" ? failedEvent.payload.message : null;
    if (msg && !msg.includes("NoneType") && !msg.includes("Traceback") && msg.length < 200) {
      return msg;
    }
    return "Run ended with an error.";
  }

  if (events.find((e) => e.event_type === "submitted")) {
    return "Application submitted successfully.";
  }

  const retryEvent = events.find((e) => e.event_type === "retry_scheduled");
  if (retryEvent) {
    const msg = typeof retryEvent.payload.message === "string" ? retryEvent.payload.message : null;
    return msg && msg.length < 200 ? msg : "Temporary issue — will retry automatically.";
  }

  if (events.find((e) => e.event_type === "browser_fallback_attempted")) {
    return "Direct API failed — AI browser took over.";
  }

  return "";
}

function formatReadinessStatus(value: string | null | undefined): string | null {
  if (!value) return null;
  const labels: Record<string, string> = {
    ready: "Ready",
    manual_only: "Manual only",
    missing_application_account: "Needs login",
    platform_not_supported: "Not supported",
    login_failed: "Login failed",
    mfa_required: "MFA required",
    platform_changed: "Flow changed",
  };
  return labels[value] ?? value.replaceAll("_", " ");
}

export function JobDetailRoute() {
  const { api } = useAppContext();
  const { jobId } = useParams();
  const [job, setJob] = useState<JobDetail | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [working, setWorking] = useState(false);

  async function loadJob() {
    if (!jobId) return;
    setJob(await api.getJobDetail(Number(jobId)));
  }

  useEffect(() => {
    if (!jobId) return;
    void loadJob();
  }, [api, jobId]);

  async function runNow() {
    if (!jobId) return;
    setWorking(true);
    setMessage(null);
    try {
      await api.triggerJobApplication(Number(jobId));
      setMessage("Queued. Running in the background.");
      await loadJob();
    } catch (caughtError) {
      setMessage(caughtError instanceof Error ? caughtError.message : "Unable to start run.");
    } finally {
      setWorking(false);
    }
  }

  async function updateRelevance(decision: "match" | "reject" | "review") {
    if (!jobId || !job) return;
    setWorking(true);
    setMessage(null);
    try {
      await api.updateJobRelevance(Number(jobId), { decision });
      await loadJob();
    } catch (caughtError) {
      setMessage(caughtError instanceof Error ? caughtError.message : "Unable to update relevance.");
    } finally {
      setWorking(false);
    }
  }

  if (!job) {
    return (
      <main className="page-shell">
        <section className="panel-card">
          <h1>Loading…</h1>
        </section>
      </main>
    );
  }

  const applyTarget = job.preferred_apply_target;
  const latestSighting = job.sightings[job.sightings.length - 1] ?? null;
  const latestRun = job.application_runs.length > 0
    ? job.application_runs[job.application_runs.length - 1]
    : null;
  const openQuestions = job.question_tasks.filter((t) => t.status === "new" || t.status === "pending");
  const isBlocked = latestRun?.status === "blocked_missing_answer";
  const canRun = Boolean(applyTarget && applyTarget.readiness_status === "ready");

  return (
    <main className="page-shell">
      <section className="panel-card">

        {/* Header */}
        <div className="jd-header">
          <div className="jd-title-block">
            <p className="eyebrow">{job.company_name}</p>
            <h1 className="jd-title">{job.title}</h1>
            {job.location ? <p className="jd-location">{job.location}</p> : null}
          </div>
          <div className="jd-header-actions">
            <Link className="ghost-button" to="/jobs">← Jobs</Link>
          </div>
        </div>

        {message ? <p className="jd-message">{message}</p> : null}

        <div className="jd-grid">

          {/* Apply card */}
          <article className="jd-card">
            <h2 className="jd-card-title">Apply</h2>
            {!applyTarget ? (
              <p className="empty-copy">No application path available yet.</p>
            ) : (
              <div className="jd-card-body">
                <div className="jd-stat-row">
                  <span className="jd-label">Platform</span>
                  <strong>{applyTarget.platform_label}</strong>
                </div>
                <div className="jd-stat-row">
                  <span className="jd-label">Status</span>
                  <span>{formatReadinessStatus(applyTarget.readiness_status) ?? "Unknown"}</span>
                </div>
                {applyTarget.readiness_reason ? (
                  <p className="jd-note">{applyTarget.readiness_reason}</p>
                ) : null}
                <a className="table-link" href={applyTarget.destination_url} target="_blank" rel="noreferrer">
                  Open application →
                </a>
                {latestSighting?.source_name ? (
                  <p className="jd-note">Found via {latestSighting.source_name}</p>
                ) : null}
                <div className="jd-run-actions">
                  {canRun ? (
                    <button type="button" className="secondary-button" disabled={working} onClick={() => void runNow()}>
                      {working ? "Starting…" : "Run now"}
                    </button>
                  ) : (
                    <span className="jd-note">{formatReadinessStatus(applyTarget.readiness_status) ?? "Not ready"}</span>
                  )}
                </div>
              </div>
            )}
          </article>

          {/* Application status card */}
          <article className="jd-card">
            <h2 className="jd-card-title">Application status</h2>
            {!latestRun ? (
              <p className="empty-copy">No runs yet.</p>
            ) : (
              <div className="jd-card-body">
                <span className={`run-badge run-badge-${runStatusTone(latestRun.status)}`}>
                  {runStatusLabel(latestRun.status)}
                </span>
                {describeRun(latestRun) ? (
                  <p className="jd-note">{describeRun(latestRun)}</p>
                ) : null}
                {isBlocked && openQuestions.length > 0 ? (
                  <Link className="secondary-button" to={`/questions?job_id=${jobId}`}>
                    Answer {openQuestions.length} question{openQuestions.length === 1 ? "" : "s"} →
                  </Link>
                ) : null}
                {job.application_runs.length > 1 ? (
                  <details className="jd-history">
                    <summary className="jd-history-toggle">
                      {job.application_runs.length - 1} earlier run{job.application_runs.length === 2 ? "" : "s"}
                    </summary>
                    <ul className="jd-history-list">
                      {[...job.application_runs].reverse().slice(1).map((run) => (
                        <li key={run.id} className={`run-history-item run-history-${runStatusTone(run.status)}`}>
                          <span className={`run-badge run-badge-${runStatusTone(run.status)}`}>{runStatusLabel(run.status)}</span>
                          {describeRun(run) ? <p className="run-history-desc">{describeRun(run)}</p> : null}
                        </li>
                      ))}
                    </ul>
                  </details>
                ) : null}
              </div>
            )}
          </article>

          {/* Relevance card */}
          <article className="jd-card">
            <h2 className="jd-card-title">Relevance</h2>
            <div className="jd-card-body">
              <span className={`decision-badge decision-${job.relevance_decision}`}>
                {job.relevance_decision}
              </span>
              {job.relevance_summary ? (
                <p className="jd-summary">{job.relevance_summary}</p>
              ) : null}
              <div className="jd-relevance-actions">
                <button type="button" className="ghost-button" disabled={working} onClick={() => void updateRelevance("match")}>
                  Include
                </button>
                <button type="button" className="ghost-button" disabled={working} onClick={() => void updateRelevance("review")}>
                  Review
                </button>
                <button type="button" className="ghost-button" disabled={working} onClick={() => void updateRelevance("reject")}>
                  Exclude
                </button>
              </div>
            </div>
          </article>

          {/* Questions card — only if there are open ones */}
          {openQuestions.length > 0 ? (
            <article className="jd-card">
              <h2 className="jd-card-title">Questions needed</h2>
              <div className="jd-card-body">
                <ul className="jd-question-list">
                  {openQuestions.map((task) => (
                    <li key={task.id} className="jd-question-item">{task.prompt_text}</li>
                  ))}
                </ul>
                <Link className="secondary-button" to={`/questions?job_id=${jobId}`}>
                  Answer questions →
                </Link>
              </div>
            </article>
          ) : null}

        </div>
      </section>
    </main>
  );
}
