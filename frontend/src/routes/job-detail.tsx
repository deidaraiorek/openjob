import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { useAppContext } from "../app/layout";
import type { JobDetail } from "../lib/api";

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

export function JobDetailRoute() {
  const { api } = useAppContext();
  const { jobId } = useParams();
  const [job, setJob] = useState<JobDetail | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [working, setWorking] = useState(false);

  async function loadJob() {
    if (!jobId) {
      return;
    }
    setJob(await api.getJobDetail(Number(jobId)));
  }

  useEffect(() => {
    if (!jobId) {
      return;
    }
    void loadJob();
  }, [api, jobId]);

  async function updateRelevance(decision: "match" | "reject" | "review") {
    if (!jobId || !job) {
      return;
    }
    setWorking(true);
    setMessage(null);
    try {
      const result = await api.updateJobRelevance(Number(jobId), { decision });
      await loadJob();
      setMessage(`Relevance updated to ${result.relevance_decision}.`);
    } catch (caughtError) {
      if (caughtError instanceof Error) {
        setMessage(caughtError.message);
      } else {
        setMessage("Unable to update relevance right now.");
      }
    } finally {
      setWorking(false);
    }
  }

  async function rescoreJob() {
    if (!jobId) {
      return;
    }
    setWorking(true);
    setMessage(null);
    try {
      const result = await api.rescoreJob(Number(jobId));
      await loadJob();
      setMessage(`Relevance rescored as ${result.relevance_decision}.`);
    } catch (caughtError) {
      if (caughtError instanceof Error) {
        setMessage(caughtError.message);
      } else {
        setMessage("Unable to rescore this job right now.");
      }
    } finally {
      setWorking(false);
    }
  }

  if (!job) {
    return (
      <main className="page-shell">
        <section className="panel-card">
          <h1>Loading job detail</h1>
        </section>
      </main>
    );
  }

  return (
    <main className="page-shell">
      <section className="panel-card">
        <div className="panel-header">
          <div>
            <p className="eyebrow">{job.company_name}</p>
            <h1>{job.title}</h1>
            <p className="supporting-copy">{job.location ?? "Location not provided"}</p>
            <p className="muted-copy">Status: {job.status}</p>
            <p className="muted-copy">
              Relevance: {job.relevance_decision}
              {job.relevance_score !== null ? ` (${Math.round(job.relevance_score * 100)}%)` : ""}
            </p>
            {formatFailureCause(job.relevance_failure_cause) ? (
              <p className="muted-copy">Temporary issue: {formatFailureCause(job.relevance_failure_cause)}</p>
            ) : null}
            <p className="supporting-copy">{job.relevance_summary ?? "No relevance rationale stored yet."}</p>
          </div>
          <div className="button-row">
            <button type="button" className="ghost-button" disabled={working} onClick={() => void updateRelevance("match")}>
              Include
            </button>
            <button type="button" className="ghost-button" disabled={working} onClick={() => void updateRelevance("review")}>
              Review
            </button>
            <button type="button" className="ghost-button" disabled={working} onClick={() => void updateRelevance("reject")}>
              Exclude
            </button>
            <button type="button" className="secondary-button" disabled={working} onClick={() => void rescoreJob()}>
              Rescore
            </button>
            <Link className="panel-link" to="/jobs">
              Back to jobs
            </Link>
          </div>
        </div>
        {message ? <p className="supporting-copy">{message}</p> : null}

        <div className="detail-grid">
          <article className="detail-card">
            <h2>Apply target</h2>
            <p>{job.preferred_apply_target?.target_type ?? "No preferred target"}</p>
            <p className="muted-copy">
              {job.preferred_apply_target?.destination_url ?? "No destination URL"}
            </p>
          </article>

          <article className="detail-card">
            <h2>Question tasks</h2>
            {job.question_tasks.length === 0 ? (
              <p className="empty-copy">No question blockers for this job.</p>
            ) : (
              <ul className="stack-list">
                {job.question_tasks.map((task) => (
                  <li key={task.id} className="stack-row">
                    <strong>{task.prompt_text}</strong>
                    <span>{task.status}</span>
                  </li>
                ))}
              </ul>
            )}
          </article>

          <article className="detail-card">
            <h2>Source sightings</h2>
            <ul className="stack-list">
              {job.sightings.map((sighting) => (
                <li key={sighting.id} className="stack-row">
                  <span>{sighting.external_job_id ?? "No external ID"}</span>
                  <a className="table-link" href={sighting.listing_url} target="_blank" rel="noreferrer">
                    Listing
                  </a>
                </li>
              ))}
            </ul>
          </article>

          <article className="detail-card">
            <h2>Application history</h2>
            {job.application_runs.length === 0 ? (
              <p className="empty-copy">No application runs logged yet.</p>
            ) : (
              <ul className="stack-list">
                {job.application_runs.map((run) => (
                  <li key={run.id} className="stack-row stack-row-column">
                    <strong>{run.status}</strong>
                    <span>Events: {run.events.map((event) => event.event_type).join(", ")}</span>
                  </li>
                ))}
              </ul>
            )}
          </article>

          <article className="detail-card">
            <h2>Relevance history</h2>
            {job.relevance_evaluations.length === 0 ? (
              <p className="empty-copy">No relevance evaluations recorded yet.</p>
            ) : (
              <ul className="stack-list">
                {job.relevance_evaluations.map((evaluation) => (
                  <li key={evaluation.id} className="stack-row stack-row-column">
                    <strong>
                      {evaluation.decision}
                      {evaluation.score !== null ? ` • ${Math.round(evaluation.score * 100)}%` : ""}
                    </strong>
                    <span>{evaluation.summary ?? "No summary provided."}</span>
                    <span>
                      {evaluation.source}
                      {evaluation.model_name ? ` • ${evaluation.model_name}` : ""}
                    </span>
                    {formatFailureCause(evaluation.failure_cause) ? (
                      <span>Temporary issue: {formatFailureCause(evaluation.failure_cause)}</span>
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
          </article>
        </div>
      </section>
    </main>
  );
}
