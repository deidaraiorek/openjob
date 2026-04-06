import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { useAppContext } from "../app/layout";
import type { JobListItem } from "../lib/api";

function formatFailureCause(value: string | null): string | null {
  if (!value) {
    return null;
  }
  return value.replaceAll("_", " ");
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
              { key: "all", label: "All" },
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
          <div className="table-shell">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Company</th>
                  <th>Title</th>
                  <th>Status</th>
                  <th>Relevance</th>
                  <th>Apply path</th>
                  <th>Sightings</th>
                  <th>Questions</th>
                  <th>Latest run</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => (
                  <tr key={job.id}>
                    <td>
                      <Link className="table-link" to={`/jobs/${job.id}`}>
                        {job.company_name}
                      </Link>
                    </td>
                    <td>{job.title}</td>
                    <td>{job.status}</td>
                    <td>
                      <div className="table-meta">
                        <strong>{job.relevance_decision}</strong>
                        <span>{job.relevance_summary ?? "No rationale yet"}</span>
                        {job.relevance_failure_cause ? (
                          <span>System issue: {formatFailureCause(job.relevance_failure_cause)}</span>
                        ) : null}
                      </div>
                    </td>
                    <td>{job.preferred_apply_target_type ?? "None"}</td>
                    <td>{job.sighting_count}</td>
                    <td>{job.open_question_task_count}</td>
                    <td>{job.latest_application_run_status ?? "No runs yet"}</td>
                    <td>
                      <div className="button-row compact-row">
                        <button
                          type="button"
                          className="ghost-button"
                          disabled={updatingJobId === job.id}
                          onClick={() => void handleRelevanceUpdate(job, "match")}
                        >
                          Include
                        </button>
                        <button
                          type="button"
                          className="ghost-button"
                          disabled={updatingJobId === job.id}
                          onClick={() => void handleRelevanceUpdate(job, "reject")}
                        >
                          Exclude
                        </button>
                        {job.preferred_apply_target_type === "external_link" ? (
                          <span className="supporting-copy">Discovery only</span>
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
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}
