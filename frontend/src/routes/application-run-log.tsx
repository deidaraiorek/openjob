import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";

import { useAppContext } from "../app/layout";
import type { ApplicationRunLog } from "../lib/api";

function formatTime(iso: string, timezone: string): string {
  return new Date(iso).toLocaleString("en-US", {
    timeZone: timezone,
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    submitted: "Submitted",
    blocked_missing_answer: "Blocked — missing answer",
    failed: "Failed",
    queued: "Queued",
    running: "Running",
    retry_scheduled: "Retry scheduled",
  };
  return map[status] ?? status;
}

function statusClass(status: string): string {
  if (status === "submitted") return "run-badge run-badge-success";
  if (status === "blocked_missing_answer") return "run-badge run-badge-warning";
  if (status === "failed") return "run-badge run-badge-danger";
  if (status === "queued" || status === "running") return "run-badge run-badge-active";
  return "run-badge run-badge-neutral";
}

function eventIcon(type: string): string {
  if (type === "queued") return "○";
  if (type === "questions_fetched") return "◎";
  if (type === "submitted") return "●";
  if (type === "blocked_missing_answer") return "◑";
  if (type === "failed") return "✕";
  if (type === "retry_scheduled") return "↻";
  return "·";
}

function eventColor(type: string): string {
  if (type === "submitted") return "#0d6b4d";
  if (type === "blocked_missing_answer") return "#946100";
  if (type === "failed") return "#a24444";
  if (type === "retry_scheduled") return "#946100";
  if (type === "queued") return "#2b5f94";
  return "var(--ink-700)";
}

function eventLabel(type: string): string {
  const map: Record<string, string> = {
    queued: "Queued",
    questions_fetched: "Fields discovered",
    submitted: "Submitted",
    blocked_missing_answer: "Blocked — missing answers",
    failed: "Failed",
    retry_scheduled: "Will retry",
    browser_fallback_attempted: "Switching to AI browser",
    action_needed: "Action needed",
  };
  return map[type] ?? type.replace(/_/g, " ");
}

function eventDescription(type: string, payload: Record<string, unknown>): string | null {
  if (type === "queued") return null;

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
      ? `${count} required field${count === 1 ? "" : "s"} couldn't be answered automatically.`
      : "Some required fields couldn't be answered automatically.";
  }

  if (type === "failed" || type === "retry_scheduled") {
    const msg = typeof payload.message === "string" ? payload.message : null;
    if (!msg) return null;
    if (msg.includes("NoneType") || msg.includes("Traceback") || msg.length > 300) return "An unexpected error occurred.";
    return msg;
  }

  if (type === "browser_fallback_attempted") {
    return "Direct API submission failed — switching to AI browser to complete the application.";
  }

  return null;
}

function matchBadge(source: string) {
  if (source === "unresolved")
    return <span style={{ color: "#a24444", fontWeight: 700, fontSize: "0.75rem" }}>unresolved</span>;
  if (source === "exact_match")
    return <span style={{ color: "#0d6b4d", fontWeight: 700, fontSize: "0.75rem" }}>exact match</span>;
  if (source === "alias_match")
    return <span style={{ color: "#946100", fontWeight: 700, fontSize: "0.75rem" }}>alias match</span>;
  if (source === "ranked_option")
    return <span style={{ color: "#2b5f94", fontWeight: 700, fontSize: "0.75rem" }}>ranked option</span>;
  return <span style={{ fontSize: "0.75rem", color: "var(--ink-700)" }}>{source}</span>;
}

export function ApplicationRunLogRoute() {
  const { api, timezone } = useAppContext();
  const { runId } = useParams<{ runId: string }>();
  const [log, setLog] = useState<ApplicationRunLog | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!runId) return;
    api
      .getApplicationRunLog(Number(runId))
      .then(setLog)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Failed to load"));
  }, [api, runId]);

  if (error) {
    return (
      <main className="page-shell">
        <section className="panel-card">
          <p className="muted-copy">{error}</p>
        </section>
      </main>
    );
  }

  if (!log) {
    return (
      <main className="page-shell">
        <section className="panel-card">
          <p className="muted-copy">Loading…</p>
        </section>
      </main>
    );
  }

  const resolved = log.question_answer_map.filter((q) => q.answer_entry_id !== null);
  const requiredUnresolved = log.question_answer_map.filter((q) => q.answer_entry_id === null && q.required);
  const optionalSkipped = log.question_answer_map.filter((q) => q.answer_entry_id === null && !q.required);

  return (
    <main className="page-shell">
      <section className="panel-card" style={{ paddingBottom: "1.5rem" }}>
        <p className="eyebrow">
          <Link className="table-link" to={`/jobs/${log.job_id}`}>← Job #{log.job_id}</Link>
        </p>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "1rem", marginTop: "0.5rem", flexWrap: "wrap" }}>
          <div style={{ minWidth: 0 }}>
            <h1 style={{ margin: 0, fontSize: "clamp(1.2rem, 2.3vw, 1.55rem)" }}>Application run</h1>
            <p style={{ margin: "0.3rem 0 0", color: "var(--ink-700)", fontSize: "0.9rem" }}>
              {log.apply_target_type ?? "unknown target"} · Run #{log.application_run_id}
            </p>
          </div>
          <span className={statusClass(log.status)}>{statusLabel(log.status)}</span>
        </div>
        <p style={{ margin: "0.75rem 0 0", color: "var(--ink-700)", fontSize: "0.9rem" }}>
          Started {formatTime(log.started_at, timezone)}
          {log.completed_at ? ` · Finished ${formatTime(log.completed_at, timezone)}` : ""}
        </p>
        <p style={{ margin: "0.2rem 0 0", color: "rgba(79,103,136,0.72)", fontSize: "0.82rem" }}>
          Job #{log.job_id}
        </p>
      </section>

      <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) minmax(0,1fr)", gap: "1.25rem", alignItems: "start" }}>

        <section className="panel-card">
          <p className="eyebrow">Timeline</p>
          <h2 style={{ marginBottom: "1.25rem" }}>Events</h2>
          {log.events.length === 0 ? (
            <p className="muted-copy">No events recorded.</p>
          ) : (
            <ol style={{ margin: 0, padding: 0, listStyle: "none", display: "flex", flexDirection: "column", gap: 0 }}>
              {log.events.map((event, i) => (
                <li key={event.id} style={{ display: "flex", gap: "0.9rem", position: "relative" }}>
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "center", flexShrink: 0 }}>
                    <span style={{ fontSize: "1.1rem", color: eventColor(event.event_type), lineHeight: 1, marginTop: "0.15rem" }}>
                      {eventIcon(event.event_type)}
                    </span>
                    {i < log.events.length - 1 && (
                      <div style={{ width: "1px", flex: 1, minHeight: "1.4rem", background: "rgba(126,176,227,0.22)", margin: "0.3rem 0" }} />
                    )}
                  </div>
                  <div style={{ paddingBottom: i < log.events.length - 1 ? "0.75rem" : 0, minWidth: 0, flex: 1 }}>
                    <div style={{ display: "flex", alignItems: "baseline", gap: "0.6rem", flexWrap: "wrap" }}>
                      <strong style={{ fontSize: "0.92rem", color: eventColor(event.event_type), letterSpacing: "-0.02em" }}>
                        {eventLabel(event.event_type)}
                      </strong>
                      <span style={{ fontSize: "0.75rem", color: "rgba(79,103,136,0.7)" }}>
                        {formatTime(event.created_at, timezone)}
                      </span>
                    </div>
                    {(() => {
                      const desc = eventDescription(event.event_type, event.payload);
                      return desc ? (
                        <p style={{ margin: "0.25rem 0 0", fontSize: "0.84rem", color: "var(--ink-700)", lineHeight: 1.55 }}>
                          {desc}
                        </p>
                      ) : null;
                    })()}
                  </div>
                </li>
              ))}
            </ol>
          )}
        </section>

        <section className="panel-card">
          <p className="eyebrow">Answer resolution</p>
          <h2 style={{ marginBottom: "0.35rem" }}>Questions</h2>
          <p style={{ margin: "0 0 1.25rem", fontSize: "0.88rem", color: "var(--ink-700)" }}>
            {resolved.length} matched
            {requiredUnresolved.length > 0 && <span style={{ color: "#a24444", fontWeight: 600 }}> · {requiredUnresolved.length} required missing</span>}
            {optionalSkipped.length > 0 && <span style={{ color: "rgba(79,103,136,0.6)" }}> · {optionalSkipped.length} optional skipped</span>}
          </p>

          {log.question_answer_map.length === 0 ? (
            <p className="muted-copy">No question map recorded for this run.</p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.55rem" }}>
              {log.question_answer_map.map((entry) => (
                <div
                  key={entry.question_fingerprint}
                  style={{
                    display: "grid",
                    gridTemplateColumns: "minmax(0,1fr) auto",
                    gap: "0.5rem 0.75rem",
                    alignItems: "start",
                    padding: "0.75rem 0.9rem",
                    borderRadius: "0.85rem",
                    background: entry.answer_entry_id
                      ? "rgba(168,233,208,0.12)"
                      : entry.required
                      ? "rgba(255,198,198,0.18)"
                      : "transparent",
                    border: entry.answer_entry_id
                      ? "1px solid rgba(103,192,160,0.22)"
                      : entry.required
                      ? "1px solid rgba(220,128,152,0.22)"
                      : "1px solid rgba(126,176,227,0.08)",
                    opacity: !entry.answer_entry_id && !entry.required ? 0.55 : 1,
                  }}
                >
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: "0.88rem", fontWeight: 600, color: "var(--ink-900)", lineHeight: 1.35 }}>
                      {entry.prompt_text}
                      {entry.required && (
                        <span style={{ color: "#a24444", marginLeft: "0.25rem" }}>*</span>
                      )}
                    </div>
                    <div style={{ fontSize: "0.75rem", color: "rgba(79,103,136,0.7)", marginTop: "0.2rem" }}>
                      {entry.field_type}
                    </div>
                    {entry.answer_entry_id && entry.answer_value !== null && entry.answer_value !== undefined && (
                      <div style={{ marginTop: "0.35rem", fontSize: "0.82rem", color: "var(--ink-700)" }}>
                        → <strong style={{ color: "var(--ink-900)" }}>{String(entry.answer_value)}</strong>
                      </div>
                    )}
                  </div>
                  <div style={{ paddingTop: "0.1rem" }}>
                    {!entry.answer_entry_id && !entry.required
                      ? <span style={{ fontSize: "0.75rem", color: "rgba(79,103,136,0.5)", fontWeight: 600 }}>skipped</span>
                      : matchBadge(entry.match_source)}
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>

      <style>{`
        @media (max-width: 760px) {
          .run-log-grid { grid-template-columns: 1fr !important; }
        }
      `}</style>
    </main>
  );
}
