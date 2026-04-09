import { useEffect, useState } from "react";
import {
  NavLink,
  Outlet,
  useNavigate,
  useOutletContext,
} from "react-router-dom";

import type { AppApi, SessionResponse } from "../lib/api";

type AppLayoutProps = {
  api: AppApi;
};

export type AppContext = {
  api: AppApi;
  session: SessionResponse;
};

export function useAppContext() {
  return useOutletContext<AppContext>();
}

const navigationItems = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/jobs", label: "Jobs" },
  { to: "/sources", label: "Sources" },
  { to: "/questions", label: "Questions" },
  { to: "/action-needed", label: "Action Needed" },
  { to: "/role-profile", label: "Profile" },
];

export function AppLayout({ api }: AppLayoutProps) {
  const navigate = useNavigate();
  const [session, setSession] = useState<SessionResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function loadSession() {
      try {
        const nextSession = await api.getSession();
        if (!nextSession.authenticated) {
          navigate("/login");
          return;
        }
        if (!cancelled) {
          setSession(nextSession);
          setLoading(false);
        }
      } catch {
        if (!cancelled) {
          setLoading(false);
        }
        navigate("/login");
      }
    }

    void loadSession();
    return () => {
      cancelled = true;
    };
  }, [api, navigate]);

  async function handleLogout() {
    await api.logout();
    navigate("/login");
  }

  if (loading || !session) {
    return (
      <main className="dashboard-shell">
        <section className="hero-panel">
          <div>
            <p className="eyebrow">OpenJob Control Room</p>
            <h1>Loading workspace</h1>
            <p className="supporting-copy">
              Checking your owner session and warming up the portal.
            </p>
          </div>
        </section>
      </main>
    );
  }

  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <div>
          <p className="eyebrow">OpenJob</p>
          <h1 className="sidebar-title">Control Room</h1>
          <p className="supporting-copy sidebar-copy">
            Operator portal for sourcing, tracking, and answering application flows.
          </p>
          <p className="supporting-copy sidebar-copy">{session.email}</p>
        </div>

        <nav className="sidebar-nav" aria-label="Primary">
          {navigationItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                isActive ? "sidebar-link active" : "sidebar-link"
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>

        <button className="secondary-button sidebar-logout" onClick={handleLogout} type="button">
          Log out
        </button>
      </aside>

      <section className="app-content">
        <Outlet context={{ api, session }} />
      </section>
    </div>
  );
}
