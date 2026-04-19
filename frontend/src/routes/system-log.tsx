import { useEffect, useState } from "react";

import { useAppContext } from "../app/layout";
import type { SystemEvent } from "../lib/api";

function formatDate(iso: string, timezone: string): string {
  return new Date(iso).toLocaleString("en-US", {
    timeZone: timezone,
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function SystemLogRoute() {
  const { api, timezone } = useAppContext();
  const [events, setEvents] = useState<SystemEvent[]>([]);
  const [sourceFilter, setSourceFilter] = useState("");
  const [eventTypeFilter, setEventTypeFilter] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function load() {
    setLoading(true);
    setError(null);
    api
      .listSystemEvents({
        source: sourceFilter || undefined,
        eventType: eventTypeFilter || undefined,
        limit: 100,
      })
      .then(setEvents)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Failed to load"))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load();
  }, [api]);

  return (
    <main className="page-shell">
      <section className="panel-card">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Admin only</p>
            <h1>System log</h1>
            <p className="supporting-copy">
              Backend events from discovery, relevance, and application runs.
            </p>
          </div>
        </div>

        <div className="filter-row">
          <input
            className="text-input"
            type="text"
            placeholder="Filter by source"
            value={sourceFilter}
            onChange={(e) => setSourceFilter(e.target.value)}
          />
          <input
            className="text-input"
            type="text"
            placeholder="Filter by event type"
            value={eventTypeFilter}
            onChange={(e) => setEventTypeFilter(e.target.value)}
          />
          <button className="secondary-button" onClick={load} type="button">
            Apply
          </button>
        </div>

        {error && <p className="muted-copy">{error}</p>}

        {loading ? (
          <p className="muted-copy">Loading…</p>
        ) : events.length === 0 ? (
          <p className="empty-copy">No system events found.</p>
        ) : (
          <ul className="stack-list">
            {events.map((event) => (
              <li key={event.id} className="question-task-card">
                <div className="stack-row stack-row-column">
                  <strong>{event.event_type}</strong>
                  <span className="muted-copy">
                    {event.source} • {formatDate(event.created_at, timezone)}
                    {event.account_id ? ` • account ${event.account_id}` : ""}
                  </span>
                  <pre className="log-payload">{JSON.stringify(event.payload, null, 2)}</pre>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
