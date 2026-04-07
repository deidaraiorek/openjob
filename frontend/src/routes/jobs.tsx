import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { useAppContext } from "../app/layout";
import type { JobListItem } from "../lib/api";

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

function formatLatestRun(job: JobListItem): string {
  if (!job.latest_application_run_status) {
    return "No runs yet";
  }

  return formatLabel(job.latest_application_run_status);
}

function getJobActionConfig(job: JobListItem): {
  primaryAction: { label: string; decision: "match" | "reject"; className: string };
  secondaryAction: { label: string; decision: "match" | "reject"; className: string } | null;
} {
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
  const [relevanceFilter, setRelevanceFilter] = useState("active");
  const [runMessage, setRunMessage] = useState<string | null>(null);
  const [runningJobId, setRunningJobId] = useState<number | null>(null);
  const [updatingJobId, setUpdatingJobId] = useState<number | null>(null);

  async function reloadJobs() {
    setJobs(await api.listJobs(relevanceFilter));
  }

  useEffect(() => {
    void reloadJobs();
  }, [api, relevanceFilter]);

  async function handleRun(job: JobListItem) {
    setRunMessage(null);
    setRunningJobId(job.id);

    try {
      const result = await api.triggerJobApplication(job.id);
      await reloadJobs();
      setRunMessage(`${job.company_name} ${job.title}: run finished with status ${result.status}.`);
    } catch (caughtError) {
      if (caughtError instanceof Error) {
        setRunMessage(`${job.company_name} ${job.title}: ${caughtError.message}.`);
      } else {
        setRunMessage(`Unable to start an application run for ${job.company_name} ${job.title}.`);
      }
    } finally {
      setRunningJobId(null);
    }
  }

  async function handleRelevanceUpdate(job: JobListItem, decision: "match" | "reject") {
    setRunMessage(null);
    setUpdatingJobId(job.id);

    try {
      const result = await api.updateJobRelevance(job.id, { decision });
      await reloadJobs();
      setRunMessage(`${job.company_name} ${job.title}: relevance updated to ${result.relevance_decision}.`);
    } catch (caughtError) {
      if (caughtError instanceof Error) {
        setRunMessage(`${job.company_name} ${job.title}: ${caughtError.message}.`);
      } else {
        setRunMessage(`Unable to update relevance for ${job.company_name} ${job.title}.`);
      }
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
              { key: "active", label: "Match + Review" },
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
        {runMessage ? <p className="supporting-copy">{runMessage}</p> : null}

        {jobs.length === 0 ? (
          <p className="empty-copy">No jobs are stored yet.</p>
        ) : (
          <div className="job-board">
            {jobs.map((job) => {
              const actionConfig = getJobActionConfig(job);
              const secondaryAction = actionConfig.secondaryAction;

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
                      <span className="job-chip">{formatLabel(job.preferred_apply_target_type)}</span>
                      <span className="job-chip">
                        {job.sighting_count} sighting{job.sighting_count === 1 ? "" : "s"}
                      </span>
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
                    {formatFailureCause(job.relevance_failure_cause) ? (
                      <p className="job-card-subtle">
                        Temporary issue: {formatFailureCause(job.relevance_failure_cause)}
                      </p>
                    ) : null}
                  </div>

                  <div className="job-card-meta">
                    <div className="job-stat">
                      <span className="job-stat-label">Latest run</span>
                      <strong>{formatLatestRun(job)}</strong>
                    </div>
                    <div className="job-stat">
                      <span className="job-stat-label">Path</span>
                      <strong>{formatLabel(job.preferred_apply_target_type)}</strong>
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
                    {job.preferred_apply_target_type === "external_link" ? (
                      <span className="job-inline-note">Discovery only</span>
                    ) : (
                      <button
                        type="button"
                        onClick={() => void handleRun(job)}
                        disabled={runningJobId === job.id || !job.preferred_apply_target_type}
                      >
                        {runningJobId === job.id ? "Running..." : "Run now"}
                      </button>
                    )}
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </section>
    </main>
  );
}
