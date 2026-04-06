import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import type { AuthApi } from "../lib/api";

type LoginRouteProps = {
  api: AuthApi;
};

export function LoginRoute({ api }: LoginRouteProps) {
  const navigate = useNavigate();
  const [email, setEmail] = useState("owner@example.com");
  const [password, setPassword] = useState("changeme");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function checkSession() {
      try {
        const session = await api.getSession();
        if (!cancelled && session.authenticated) {
          navigate("/");
        }
      } catch {
        // Anonymous users should stay on the login page.
      }
    }

    void checkSession();

    return () => {
      cancelled = true;
    };
  }, [api, navigate]);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);

    try {
      const session = await api.login({ email, password });
      if (!session.authenticated) {
        setError("Invalid credentials.");
        return;
      }
      navigate("/");
    } catch {
      setError("Unable to sign in right now.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="auth-shell">
      <section className="auth-card">
        <p className="eyebrow">OpenJob</p>
        <h1>Owner Login</h1>
        <p className="supporting-copy">
          Enter the control room to manage sources, answer memory, and every application state from one dashboard.
        </p>

        <form className="auth-form" onSubmit={handleSubmit}>
          <label>
            <span>Email</span>
            <input
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              type="email"
            />
          </label>

          <label>
            <span>Password</span>
            <input
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              type="password"
            />
          </label>

          {error ? <p className="error-copy">{error}</p> : null}

          <button disabled={submitting} type="submit">
            {submitting ? "Signing in..." : "Sign in"}
          </button>
        </form>
      </section>
    </main>
  );
}
