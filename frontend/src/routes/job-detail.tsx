import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { useAppContext } from "../app/layout";
import type { JobDetail } from "../lib/api";

type ApplicationRun = JobDetail["application_runs"][number];
type ApplicationEvent = ApplicationRun["events"][number];

const RUN_STATUS_LABELS: Record<string, string> = {
  submitted: "Submitted",
  blocked_missing_answer: "Waiting on answers",
  pending_review: "Review optional fields",
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
  if (status === "blocked_missing_answer" || status === "pending_review" || status === "retry_scheduled" || status === "cooldown_required") return "warning";
  if (status === "queued" || status === "running") return "active";
  if (status === "failed" || status === "action_needed" || status === "platform_changed") return "danger";
  return "neutral";
}

function blockedCounts(run: ApplicationRun): { required: number; optional: number } | null {
  const blockedEvent = run.events.find(
    (e) => e.event_type === "blocked_missing_answer" || e.event_type === "pending_review",
  );
  if (!blockedEvent) return null;
  const qmap = blockedEvent.payload.question_answer_map;
  if (!Array.isArray(qmap)) {
    const ids = blockedEvent.payload.question_task_ids;
    return { required: Array.isArray(ids) ? ids.length : 0, optional: 0 };
  }
  const unanswered = (qmap as Array<{ answer_entry_id: number | null; required: boolean }>).filter(
    (q) => q.answer_entry_id === null,
  );
  return {
    required: unanswered.filter((q) => q.required).length,
    optional: unanswered.filter((q) => !q.required).length,
  };
}

function describeRun(run: ApplicationRun): string {
  const events = run.events;

  const pendingEvent = events.find((event) => event.event_type === "pending_review");
  if (pendingEvent) {
    const count = typeof pendingEvent.payload.unanswered_optional_count === "number"
      ? pendingEvent.payload.unanswered_optional_count
      : 0;
    return `${count} optional field${count === 1 ? "" : "s"} skipped — confirm to submit or answer them first.`;
  }

  const blockedEvent = events.find((event) => event.event_type === "blocked_missing_answer");
  if (blockedEvent) {
    const counts = blockedCounts(run);
    if (!counts) return "Some questions still need answering.";
    const parts: string[] = [];
    if (counts.required > 0) parts.push(`${counts.required} required`);
    if (counts.optional > 0) parts.push(`${counts.optional} optional`);
    const total = counts.required + counts.optional;
    return `${total} question${total === 1 ? "" : "s"} unanswered (${parts.join(", ")}).`;
  }

  const failedEvent = events.find((event) => event.event_type === "failed");
  if (failedEvent) {
    const message = typeof failedEvent.payload.message === "string" ? failedEvent.payload.message : null;
    if (message && !message.includes("NoneType") && !message.includes("Traceback") && message.length < 200) {
      return message;
    }
    return "Run ended with an error.";
  }

  if (events.find((event) => event.event_type === "submitted")) {
    return "Application submitted successfully.";
  }

  const retryEvent = events.find((event) => event.event_type === "retry_scheduled");
  if (retryEvent) {
    const message = typeof retryEvent.payload.message === "string" ? retryEvent.payload.message : null;
    return message && message.length < 200 ? message : "Temporary issue. The system will retry automatically.";
  }

  if (events.find((event) => event.event_type === "browser_fallback_attempted")) {
    return "Direct API submission failed, so the AI browser stepped in.";
  }

  return "Run created. Waiting for more detail.";
}

function eventLabel(type: string): string {
  const labels: Record<string, string> = {
    queued: "Queued",
    questions_fetched: "Fields discovered",
    submitted: "Submitted",
    blocked_missing_answer: "Missing answers",
    pending_review: "Optional fields skipped",
    failed: "Failed",
    retry_scheduled: "Retry planned",
    browser_fallback_attempted: "Switched to AI browser",
    action_needed: "Action needed",
    cooldown_required: "Cooldown required",
    platform_changed: "Flow changed",
    running: "Running",
  };
  return labels[type] ?? type.replaceAll("_", " ");
}

function eventDescription(event: ApplicationEvent): string | null {
  const { event_type: type, payload } = event;

  if (type === "queued" || type === "running") {
    return null;
  }

  if (type === "questions_fetched") {
    const count = typeof payload.question_count === "number" ? payload.question_count : null;
    return count !== null ? `Found ${count} field${count === 1 ? "" : "s"} on the form.` : null;
  }

  if (type === "submitted") {
    const ids = Array.isArray(payload.answer_entry_ids) ? payload.answer_entry_ids : [];
    return `Filled ${ids.length} field${ids.length === 1 ? "" : "s"} and submitted successfully.`;
  }

  if (type === "blocked_missing_answer") {
    const ids = Array.isArray(payload.question_task_ids) ? payload.question_task_ids : [];
    const count = ids.length;
    return count > 0
      ? `${count} required field${count === 1 ? "" : "s"} could not be answered automatically.`
      : "Some required fields could not be answered automatically.";
  }

  if (type === "pending_review") {
    const count = typeof payload.unanswered_optional_count === "number" ? payload.unanswered_optional_count : 0;
    return `${count} optional field${count === 1 ? "" : "s"} have no saved answer. Confirm to submit or add answers first.`;
  }

  if (type === "failed" || type === "retry_scheduled" || type === "action_needed" || type === "cooldown_required") {
    const message = typeof payload.message === "string" ? payload.message : null;
    if (!message) return null;
    if (message.includes("NoneType") || message.includes("Traceback") || message.length > 300) {
      return "An unexpected error occurred.";
    }
    return message;
  }

  if (type === "browser_fallback_attempted") {
    return "Direct submission failed, so OpenJob switched to the AI browser flow.";
  }

  if (type === "platform_changed") {
    return "The live application flow drifted away from the automation we expected.";
  }

  return null;
}

function eventTone(type: string): "success" | "warning" | "danger" | "active" | "neutral" {
  if (type === "submitted") return "success";
  if (type === "blocked_missing_answer" || type === "pending_review" || type === "retry_scheduled" || type === "cooldown_required") return "warning";
  if (type === "failed" || type === "action_needed" || type === "platform_changed") return "danger";
  if (type === "queued" || type === "running" || type === "questions_fetched" || type === "browser_fallback_attempted") return "active";
  return "neutral";
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

function formatPlatform(value: string | null | undefined): string {
  return value ? value.replaceAll("_", " ") : "Unknown target";
}

const POLLING_STATUSES = new Set(["queued", "running"]);

export function JobDetailRoute() {
  const { api } = useAppContext();
  const { jobId } = useParams();
  const [job, setJob] = useState<JobDetail | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [working, setWorking] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  function stopPolling() {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }

  async function loadJob() {
    if (!jobId) return;
    const detail = await api.getJobDetail(Number(jobId));
    setJob(detail);
    return detail;
  }

  function startPolling() {
    if (pollRef.current) return;
    pollRef.current = setInterval(async () => {
      if (!jobId) return;
      const detail = await api.getJobDetail(Number(jobId));
      setJob(detail);
      const latestRun = detail.application_runs.at(-1);
      if (latestRun && !POLLING_STATUSES.has(latestRun.status)) {
        stopPolling();
      }
    }, 1500);
  }

  useEffect(() => {
    if (!jobId) return;
    void loadJob().then((detail) => {
      const latestRun = detail?.application_runs.at(-1);
      if (!latestRun || POLLING_STATUSES.has(latestRun.status)) {
        startPolling();
      }
    });
    return stopPolling;
  }, [api, jobId]);

  async function runNow() {
    if (!jobId) return;
    setWorking(true);
    setMessage(null);
    // Optimistic update — show queued immediately without waiting for API
    setJob((prev) => {
      if (!prev) return prev;
      const optimisticRun = {
        id: -1,
        status: "queued",
        apply_target_id: prev.preferred_apply_target?.id ?? null,
        events: [],
      };
      return { ...prev, application_runs: [...prev.application_runs, optimisticRun] };
    });
    try {
      await api.triggerJobApplication(Number(jobId));
      const prevRunCount = job?.application_runs.length ?? 0;
      const deadline = Date.now() + 10_000;
      let detail = await loadJob();
      while (detail && detail.application_runs.length <= prevRunCount && Date.now() < deadline) {
        await new Promise((resolve) => setTimeout(resolve, 600));
        detail = await loadJob();
      }
      startPolling();
    } catch (caughtError) {
      setMessage(caughtError instanceof Error ? caughtError.message : "Unable to start run.");
      await loadJob();
    } finally {
      setWorking(false);
    }
  }

  async function confirmRun(runId: number, action: "submit" | "answer_optional") {
    setWorking(true);
    setMessage(null);
    try {
      await api.confirmRun(runId, action);
      await loadJob();
      if (action === "submit") startPolling();
    } catch (caughtError) {
      setMessage(caughtError instanceof Error ? caughtError.message : "Unable to confirm run.");
      await loadJob();
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
          <p className="muted-copy">Loading…</p>
        </section>
      </main>
    );
  }

  const applyTarget = job.preferred_apply_target;
  const latestSighting = job.sightings[job.sightings.length - 1] ?? null;
  const orderedRuns = [...job.application_runs].reverse();
  const latestRun = orderedRuns[0] ?? null;
  const openQuestions = job.question_tasks.filter((task) => task.status === "new" || task.status === "pending");
  const isBlocked = latestRun?.status === "blocked_missing_answer";
  const latestBlockedCounts = latestRun && isBlocked ? blockedCounts(latestRun) : null;
  const totalUnanswered = latestBlockedCounts
    ? latestBlockedCounts.required + latestBlockedCounts.optional
    : openQuestions.length;
  const canRun = Boolean(applyTarget && applyTarget.readiness_status === "ready");
  const latestTone = latestRun ? runStatusTone(latestRun.status) : null;

  return (
    <main className="page-shell">
      <div className="jd-page">
        <div className="jd-nav">
          <Link className="jd-back-link" to="/jobs">← Jobs</Link>
        </div>

        <section className="jd-hero">
          <div className="jd-hero-copy">
            <p className="eyebrow">{job.company_name}</p>
            <h1 className="jd-hero-title">{job.title}</h1>
            {job.location ? <p className="jd-hero-location">{job.location}</p> : null}
            <p className="jd-hero-summary">
              {job.relevance_summary ?? "Track application readiness, operator blockers, and every automation run from one place."}
            </p>
          </div>

          <div className="jd-hero-rail">
            <div className="jd-hero-badges">
              <span className={`decision-badge decision-${job.relevance_decision}`}>
                {job.relevance_decision}
              </span>
              {latestRun ? (
                <span className={`run-badge run-badge-${latestTone}`}>
                  {runStatusLabel(latestRun.status)}
                </span>
              ) : null}
            </div>

            <div className="jd-hero-stats">
              <div className="jd-stat-pill">
                <span>Runs</span>
                <strong>{job.application_runs.length}</strong>
              </div>
              <div className="jd-stat-pill">
                <span>Questions</span>
                <strong>{totalUnanswered}</strong>
              </div>
              <div className="jd-stat-pill">
                <span>Path</span>
                <strong>{applyTarget?.platform_label ?? "None yet"}</strong>
              </div>
            </div>
          </div>
        </section>

        {message ? <p className="jd-message">{message}</p> : null}

        <div className="jd-main-grid">
          <div className="jd-col-left">
            <section className="jd-section jd-section-application">
              <div className="jd-section-head">
                <div>
                  <p className="jd-section-label">Application</p>
                  <h2 className="jd-section-title">Ready path</h2>
                </div>
              </div>

              {!applyTarget ? (
                <p className="muted-copy" style={{ margin: 0 }}>No application path available yet.</p>
              ) : (
                <div className="jd-apply-block">
                  <div className="jd-detail-grid">
                    <div className="jd-detail-cell">
                      <span className="jd-detail-label">Platform</span>
                      <strong>{applyTarget.platform_label}</strong>
                    </div>
                    <div className="jd-detail-cell">
                      <span className="jd-detail-label">Readiness</span>
                      <span className={`jd-readiness-pill jd-readiness-${applyTarget.readiness_status}`}>
                        {formatReadinessStatus(applyTarget.readiness_status) ?? "Unknown"}
                      </span>
                    </div>
                    <div className="jd-detail-cell">
                      <span className="jd-detail-label">Compatibility</span>
                      <strong>{applyTarget.compatibility_label ?? "Unknown"}</strong>
                    </div>
                    <div className="jd-detail-cell">
                      <span className="jd-detail-label">Source</span>
                      <strong>{latestSighting?.source_name ?? "Unknown"}</strong>
                    </div>
                  </div>

                  {applyTarget.readiness_reason ? (
                    <p className="jd-apply-note">{applyTarget.readiness_reason}</p>
                  ) : null}

                  <div className="jd-apply-actions">
                    <a className="jd-open-link" href={applyTarget.destination_url} target="_blank" rel="noreferrer">
                      Open application →
                    </a>
                    {canRun ? (
                      <button type="button" className="jd-run-button" disabled={working} onClick={() => void runNow()}>
                        {working ? "Starting…" : "Run now"}
                      </button>
                    ) : null}
                  </div>
                </div>
              )}
            </section>

            <section className="jd-section jd-section-runs">
              <div className="jd-section-head">
                <div>
                  <p className="jd-section-label">Automation activity</p>
                  <h2 className="jd-section-title">Run history</h2>
                </div>
              </div>

              {!latestRun ? (
                <p className="muted-copy" style={{ margin: 0 }}>No runs yet.</p>
              ) : (
                <div className="jd-run-stack">
                  {orderedRuns.map((run, index) => {
                    const tone = runStatusTone(run.status);
                    const isLatest = index === 0;
                    return (
                      <article key={run.id} className={`jd-run-card jd-run-card-${tone}`}>
                        <div className="jd-run-card-head">
                          <div className="jd-run-card-title">
                            <div className="jd-run-card-topline">
                              <strong>{run.id === -1 ? "Run" : `Run #${run.id}`}</strong>
                              {isLatest ? <span className="jd-current-pill">Latest</span> : null}
                            </div>
                            <p>{describeRun(run)}</p>
                          </div>
                          <div className="jd-run-card-meta">
                            <span className={`run-badge run-badge-${tone}`}>{runStatusLabel(run.status)}</span>
                            <span className="jd-run-platform">{formatPlatform(applyTarget?.target_type)}</span>
                          </div>
                        </div>

                        <ol className="jd-event-list">
                          {run.events.length === 0 ? (
                            <li className="jd-event-item jd-event-item-empty">
                              <p>No events recorded yet.</p>
                            </li>
                          ) : (
                            run.events.map((event, eventIndex) => {
                              const eventState = eventTone(event.event_type);
                              const description = eventDescription(event);
                              return (
                                <li key={event.id} className="jd-event-item">
                                  <div className="jd-event-rail" aria-hidden="true">
                                    <span className={`jd-event-dot jd-event-dot-${eventState}`} />
                                    {eventIndex < run.events.length - 1 ? <span className="jd-event-line" /> : null}
                                  </div>
                                  <div className="jd-event-copy">
                                    <div className="jd-event-head">
                                      <strong>{eventLabel(event.event_type)}</strong>
                                      <span>Step {eventIndex + 1}</span>
                                    </div>
                                    {description ? <p>{description}</p> : null}
                                  </div>
                                </li>
                              );
                            })
                          )}
                        </ol>

                        {run.status === "blocked_missing_answer" && totalUnanswered > 0 ? (
                          <div className="jd-run-card-footer">
                            <Link className="secondary-button" to={`/questions?job_id=${jobId}`}>
                              Answer {totalUnanswered} question{totalUnanswered === 1 ? "" : "s"} →
                            </Link>
                          </div>
                        ) : run.status === "pending_review" ? (
                          <div className="jd-run-card-footer" style={{ gap: "0.65rem" }}>
                            <button
                              type="button"
                              className="jd-run-button"
                              disabled={working}
                              onClick={() => void confirmRun(run.id, "submit")}
                            >
                              Submit without optional fields
                            </button>
                            <Link className="secondary-button" to={`/questions?job_id=${jobId}`}>
                              Answer optional fields first →
                            </Link>
                          </div>
                        ) : null}
                      </article>
                    );
                  })}
                </div>
              )}
            </section>
          </div>

          <div className="jd-col-right">
            <section className="jd-section">
              <div className="jd-section-head">
                <div>
                  <p className="jd-section-label">Relevance</p>
                  <h2 className="jd-section-title">Decision</h2>
                </div>
              </div>

              <div className="jd-relevance-block">
                <span className={`decision-badge decision-${job.relevance_decision}`}>
                  {job.relevance_decision}
                </span>
                {job.relevance_summary ? (
                  <p className="jd-relevance-summary">{job.relevance_summary}</p>
                ) : (
                  <p className="jd-relevance-summary">No rationale has been stored yet.</p>
                )}
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
            </section>

            {openQuestions.length > 0 ? (
              <section className="jd-section jd-section-warning">
                <div className="jd-section-head">
                  <div>
                    <p className="jd-section-label">Operator queue</p>
                    <h2 className="jd-section-title">Questions needed</h2>
                  </div>
                </div>
                <ul className="jd-question-list">
                  {openQuestions.map((task) => (
                    <li key={task.id} className="jd-question-item">{task.prompt_text}</li>
                  ))}
                </ul>
                <Link className="secondary-button" style={{ alignSelf: "flex-start" }} to={`/questions?job_id=${jobId}`}>
                  Answer questions →
                </Link>
              </section>
            ) : null}

            <section className="jd-section">
              <div className="jd-section-head">
                <div>
                  <p className="jd-section-label">Discovery</p>
                  <h2 className="jd-section-title">Latest sighting</h2>
                </div>
              </div>

              {latestSighting ? (
                <div className="jd-sighting-card">
                  <div className="jd-detail-cell">
                    <span className="jd-detail-label">Source</span>
                    <strong>{latestSighting.source_name ?? "Unknown"}</strong>
                  </div>
                  <div className="jd-detail-cell">
                    <span className="jd-detail-label">Listing</span>
                    <a className="table-link" href={latestSighting.listing_url} target="_blank" rel="noreferrer">
                      Open listing →
                    </a>
                  </div>
                  {latestSighting.apply_url ? (
                    <div className="jd-detail-cell">
                      <span className="jd-detail-label">Apply URL</span>
                      <a className="table-link" href={latestSighting.apply_url} target="_blank" rel="noreferrer">
                        Open apply page →
                      </a>
                    </div>
                  ) : null}
                </div>
              ) : (
                <p className="muted-copy" style={{ margin: 0 }}>No sightings recorded.</p>
              )}
            </section>

            {isBlocked && openQuestions.length > 0 ? (
              <section className="jd-section jd-section-warning">
                <div className="jd-section-head">
                  <div>
                    <p className="jd-section-label">Next action</p>
                    <h2 className="jd-section-title">Unblock latest run</h2>
                  </div>
                </div>
                <p className="jd-relevance-summary">
                  The newest run stopped because required answers are still missing. Resolve them here, then re-run.
                </p>
                <Link className="secondary-button" style={{ alignSelf: "flex-start" }} to={`/questions?job_id=${jobId}`}>
                  Resolve blockers →
                </Link>
              </section>
            ) : null}
          </div>
        </div>
      </div>
    </main>
  );
}
