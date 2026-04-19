import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { useAppContext } from "../app/layout";
import type { ActionNeededItem, JobListItem, QuestionTask, Source } from "../lib/api";

export function DashboardRoute() {
  const { api, session } = useAppContext();
  const [actionNeeded, setActionNeeded] = useState<ActionNeededItem[]>([]);
  const [jobs, setJobs] = useState<JobListItem[]>([]);
  const [questions, setQuestions] = useState<QuestionTask[]>([]);
  const [sources, setSources] = useState<Source[]>([]);

  useEffect(() => {
    async function loadData() {
      const [actionItems, jobList, questionTasks, sourceList] = await Promise.all([
        api.listActionNeeded(),
        api.listJobs(),
        api.listQuestionTasks(),
        api.listSources(),
      ]);
      setActionNeeded(actionItems);
      setJobs(jobList);
      setQuestions(questionTasks);
      setSources(sourceList);
    }

    void loadData();
  }, [api]);

  return (
    <main className="page-shell">
      <section className="hero-panel">
        <div>
          <p className="eyebrow">OpenJob Control Room</p>
          <h1>Welcome back to your autopilot</h1>
          <p className="supporting-copy">
            Signed in as <strong>{session.email}</strong>. Track discovery, resolve blockers,
            and keep your application memory clean enough that future runs feel effortless.
          </p>
        </div>
      </section>

      <section className="dashboard-grid">
        <article className="metric-card">
          <span>Visible jobs</span>
          <strong>{jobs.length}</strong>
          <p>Jobs currently in scope for review or application inside the workspace.</p>
        </article>
        <article className="metric-card">
          <span>Open questions</span>
          <strong>{questions.filter((task) => task.status === "new").length}</strong>
          <p>Required answers that still need human input before future auto-apply runs.</p>
        </article>
        <article className="metric-card">
          <span>Action needed</span>
          <strong>{actionNeeded.length}</strong>
          <p>Blocked automation runs that need a browser login, cooldown, or manual follow-up.</p>
        </article>
        <article className="metric-card">
          <span>Active sources</span>
          <strong>{sources.filter((source) => source.active).length}</strong>
          <p>Discovery inputs currently enabled for sync.</p>
        </article>
      </section>

      <section className="content-grid">
        <article className="panel-card">
          <div className="panel-header">
            <h2>Priority queue</h2>
            <Link className="panel-link" to="/questions">
              Review questions
            </Link>
          </div>
          {questions.length === 0 ? (
            <p className="empty-copy">No unresolved questions yet.</p>
          ) : (
            <ul className="stack-list">
              {questions.slice(0, 5).map((task) => (
                <li key={task.id} className="stack-row">
                  <strong>{task.prompt_text}</strong>
                  <span>{task.status}</span>
                </li>
              ))}
            </ul>
          )}
        </article>

        <article className="panel-card">
          <div className="panel-header">
            <h2>Blocked automation</h2>
            <Link className="panel-link" to="/action-needed">
              Open queue
            </Link>
          </div>
          {actionNeeded.length === 0 ? (
            <p className="empty-copy">No LinkedIn or browser blockers right now.</p>
          ) : (
            <ul className="stack-list">
              {actionNeeded.slice(0, 5).map((item) => (
                <li key={item.application_run_id} className="stack-row stack-row-column">
                  <strong>
                    {item.company_name} • {item.title}
                  </strong>
                  <span>
                    {item.blocker_type}
                    {item.last_step ? ` • ${item.last_step}` : ""}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </article>

        <article className="panel-card">
          <div className="panel-header">
            <h2>Recent jobs</h2>
            <Link className="panel-link" to="/jobs">
              Open jobs
            </Link>
          </div>
          {jobs.length === 0 ? (
            <p className="empty-copy">No jobs discovered yet. Add sources to begin syncing.</p>
          ) : (
            <ul className="stack-list">
              {jobs.slice(0, 5).map((job) => (
                <li key={job.id} className="stack-row">
                  <div className="dashboard-job-copy">
                    <strong>{job.company_name}</strong>
                    <span>{job.title}</span>
                  </div>
                  <span>{job.status}</span>
                </li>
              ))}
            </ul>
          )}
        </article>
      </section>
    </main>
  );
}
