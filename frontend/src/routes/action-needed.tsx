import { useEffect, useState } from "react";

import { useAppContext } from "../app/layout";
import type { ActionNeededItem } from "../lib/api";

export function ActionNeededRoute() {
  const { api } = useAppContext();
  const [items, setItems] = useState<ActionNeededItem[]>([]);

  useEffect(() => {
    void api.listActionNeeded().then(setItems);
  }, [api]);

  return (
    <main className="page-shell">
      <section className="panel-card">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Operator queue</p>
            <h1>Action needed</h1>
            <p className="supporting-copy">
              Browser blockers, platform drift, and cooldowns that need human follow-up.
            </p>
          </div>
        </div>

        {items.length === 0 ? (
          <p className="empty-copy">No action-needed runs right now.</p>
        ) : (
          <ul className="stack-list">
            {items.map((item) => (
              <li key={item.application_run_id} className="question-task-card">
                <div className="stack-row stack-row-column">
                  <strong>
                    {item.company_name} • {item.title}
                  </strong>
                  <span className="muted-copy">
                    {item.blocker_type} • {item.run_status}
                    {item.last_step ? ` • ${item.last_step}` : ""}
                  </span>
                  <p className="supporting-copy action-message">
                    {item.message ?? "No extra detail captured for this blocker."}
                  </p>
                </div>
                <div className="artifact-list">
                  {item.artifact_paths.length === 0 ? (
                    <span className="muted-copy">No artifacts captured</span>
                  ) : (
                    item.artifact_paths.map((path) => (
                      <a
                        key={path}
                        className="table-link"
                        href={path}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Open artifact
                      </a>
                    ))
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
