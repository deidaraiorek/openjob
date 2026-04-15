import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";

import { useAppContext } from "../app/layout";
import type {
  AnswerCreatePayload,
  AnswerEntry,
  ApplicationAccount,
  ApplicationAccountCreatePayload,
  ApplicationAccountUpdatePayload,
} from "../lib/api";

type ProfileTab = "role-profile" | "answers" | "application-accounts";

type ApplicationAccountFormState = {
  platform_family: string;
  tenant_host: string;
  login_identifier: string;
  password: string;
};

const initialForm: AnswerCreatePayload = {
  question_template_id: null,
  label: "",
  answer_text: "",
  answer_payload: {},
};

const initialApplicationAccountForm: ApplicationAccountFormState = {
  platform_family: "icims",
  tenant_host: "",
  login_identifier: "",
  password: "",
};

const APPLICATION_ACCOUNT_PLATFORM_OPTIONS = [
  { value: "icims", label: "iCIMS" },
  { value: "jobvite", label: "Jobvite" },
  { value: "workday", label: "Workday" },
  { value: "linkedin", label: "LinkedIn" },
];

const COMMON_TIMEZONES = [
  "UTC",
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "Europe/London",
  "Europe/Berlin",
  "Asia/Singapore",
  "Asia/Tokyo",
  "Australia/Sydney",
];

const TIMEZONE_QUICK_PICKS = [
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "UTC",
];

function getBrowserTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

function tabFromSearch(search: string): ProfileTab {
  if (search.includes("tab=answers")) {
    return "answers";
  }
  if (search.includes("tab=application-accounts")) {
    return "application-accounts";
  }
  return "role-profile";
}

function isFileAnswer(answer: AnswerEntry) {
  return answer.answer_payload.kind === "file";
}

function describeAnswerValue(answer: AnswerEntry) {
  if (isFileAnswer(answer)) {
    const filename = typeof answer.answer_payload.filename === "string"
      ? answer.answer_payload.filename
      : "Uploaded file";
    return `File upload: ${filename}`;
  }

  if (answer.answer_text) {
    return answer.answer_text;
  }

  return JSON.stringify(answer.answer_payload);
}

function describeCredentialStatus(account: ApplicationAccount): string {
  const labels: Record<string, string> = {
    ready: "Ready",
    login_failed: "Login failed",
    missing_password: "Missing password",
  };
  return labels[account.credential_status] ?? account.credential_status.replaceAll("_", " ");
}

function describeTenantHost(value: string): string {
  return value || "Default / any employer host";
}

export function RoleProfileRoute() {
  const { api, timezone, setTimezone } = useAppContext();
  const location = useLocation();
  const [currentTab, setCurrentTab] = useState<ProfileTab>(tabFromSearch(location.search));

  const [prompt, setPrompt] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [timezoneStatus, setTimezoneStatus] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const [answers, setAnswers] = useState<AnswerEntry[]>([]);
  const [form, setForm] = useState(initialForm);
  const [editingAnswerId, setEditingAnswerId] = useState<number | null>(null);
  const [answerError, setAnswerError] = useState<string | null>(null);

  const [applicationAccounts, setApplicationAccounts] = useState<ApplicationAccount[]>([]);
  const [applicationAccountForm, setApplicationAccountForm] = useState(initialApplicationAccountForm);
  const [editingApplicationAccountId, setEditingApplicationAccountId] = useState<number | null>(null);
  const [applicationAccountError, setApplicationAccountError] = useState<string | null>(null);
  const [applicationAccountStatus, setApplicationAccountStatus] = useState<string | null>(null);
  const [applicationAccountSubmitting, setApplicationAccountSubmitting] = useState(false);
  const [deletingApplicationAccountId, setDeletingApplicationAccountId] = useState<number | null>(null);

  async function reloadAnswers() {
    setAnswers(await api.listAnswers());
  }

  async function reloadApplicationAccounts() {
    setApplicationAccounts(await api.listApplicationAccounts());
  }

  useEffect(() => {
    async function loadProfile() {
      try {
        const profile = await api.getRoleProfile();
        setPrompt(profile.prompt);
      } catch {
        setPrompt("");
      }
    }

    void Promise.all([loadProfile(), reloadAnswers(), reloadApplicationAccounts()]);
  }, [api]);

  async function handleProfileSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    try {
      await api.saveRoleProfile({
        prompt,
        generated_titles: [],
        generated_keywords: [],
      });
      setStatus("Saved");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleAnswerSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAnswerError(null);
    try {
      const payload = {
        ...form,
        question_template_id: form.question_template_id || null,
      };
      if (editingAnswerId !== null) {
        await api.updateAnswer(editingAnswerId, payload);
      } else {
        await api.createAnswer(payload);
      }
      setForm(initialForm);
      setEditingAnswerId(null);
      await reloadAnswers();
    } catch (caughtError) {
      setAnswerError(caughtError instanceof Error ? caughtError.message : "Unable to save answer entry.");
    }
  }

  async function handleApplicationAccountSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setApplicationAccountError(null);
    setApplicationAccountStatus(null);

    const tenantHost = applicationAccountForm.tenant_host.trim();
    const loginIdentifier = applicationAccountForm.login_identifier.trim();
    const password = applicationAccountForm.password.trim();

    if (editingApplicationAccountId === null && !loginIdentifier) {
      setApplicationAccountError("Login email or username is required.");
      return;
    }

    if (editingApplicationAccountId === null && !password) {
      setApplicationAccountError("Password is required for a new application account.");
      return;
    }

    setApplicationAccountSubmitting(true);
    try {
      if (editingApplicationAccountId !== null) {
        const payload: ApplicationAccountUpdatePayload = {
          platform_family: applicationAccountForm.platform_family,
          tenant_host: tenantHost || null,
          ...(loginIdentifier ? { login_identifier: loginIdentifier } : {}),
          ...(password ? { password } : {}),
        };
        await api.updateApplicationAccount(editingApplicationAccountId, payload);
        setApplicationAccountStatus("Application account updated.");
      } else {
        const payload: ApplicationAccountCreatePayload = {
          platform_family: applicationAccountForm.platform_family,
          tenant_host: tenantHost || null,
          login_identifier: loginIdentifier,
          password,
        };
        await api.createApplicationAccount(payload);
        setApplicationAccountStatus("Application account saved.");
      }
      setApplicationAccountForm(initialApplicationAccountForm);
      setEditingApplicationAccountId(null);
      await reloadApplicationAccounts();
    } catch (caughtError) {
      setApplicationAccountError(
        caughtError instanceof Error ? caughtError.message : "Unable to save application account.",
      );
    } finally {
      setApplicationAccountSubmitting(false);
    }
  }

  async function handleDeleteApplicationAccount(accountId: number) {
    setDeletingApplicationAccountId(accountId);
    setApplicationAccountError(null);
    setApplicationAccountStatus(null);
    try {
      await api.deleteApplicationAccount(accountId);
      if (editingApplicationAccountId === accountId) {
        setEditingApplicationAccountId(null);
        setApplicationAccountForm(initialApplicationAccountForm);
      }
      setApplicationAccountStatus("Application account deleted.");
      await reloadApplicationAccounts();
    } catch (caughtError) {
      setApplicationAccountError(
        caughtError instanceof Error ? caughtError.message : "Unable to delete application account.",
      );
    } finally {
      setDeletingApplicationAccountId(null);
    }
  }

  function handleEdit(answer: AnswerEntry) {
    setEditingAnswerId(answer.id);
    setForm({
      question_template_id: answer.question_template_id,
      label: answer.label,
      answer_text: answer.answer_text ?? "",
      answer_payload: answer.answer_payload,
    });
    setAnswerError(null);
    setCurrentTab("answers");
  }

  function handleCancelEdit() {
    setEditingAnswerId(null);
    setForm(initialForm);
    setAnswerError(null);
  }

  function handleEditApplicationAccount(account: ApplicationAccount) {
    setEditingApplicationAccountId(account.id);
    setApplicationAccountForm({
      platform_family: account.platform_family,
      tenant_host: account.tenant_host,
      login_identifier: "",
      password: "",
    });
    setApplicationAccountError(null);
    setApplicationAccountStatus(null);
    setCurrentTab("application-accounts");
  }

  function handleCancelApplicationAccountEdit() {
    setEditingApplicationAccountId(null);
    setApplicationAccountForm(initialApplicationAccountForm);
    setApplicationAccountError(null);
    setApplicationAccountStatus(null);
  }

  useEffect(() => {
    setCurrentTab(tabFromSearch(location.search));
  }, [location.search]);

  return (
    <main className="page-shell">
      <section className="panel-card">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Profile</p>
            <h1>Centralized user profile</h1>
            <p className="supporting-copy">
              Keep your role targeting, reusable answers, and login-ready application accounts together so future runs pull from one place.
            </p>
          </div>
        </div>

        <div className="profile-tab-list" role="tablist" aria-label="Profile sections">
          <button
            type="button"
            role="tab"
            aria-selected={currentTab === "role-profile"}
            className={currentTab === "role-profile" ? "profile-tab-button active" : "profile-tab-button"}
            onClick={() => setCurrentTab("role-profile")}
          >
            Role Profile
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={currentTab === "answers"}
            className={currentTab === "answers" ? "profile-tab-button active" : "profile-tab-button"}
            onClick={() => setCurrentTab("answers")}
          >
            Saved Answers
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={currentTab === "application-accounts"}
            className={currentTab === "application-accounts" ? "profile-tab-button active" : "profile-tab-button"}
            onClick={() => setCurrentTab("application-accounts")}
          >
            Application Accounts
          </button>
        </div>

        {currentTab === "role-profile" ? (
          <section className="profile-section" aria-label="Role profile section">
            <div className="profile-section-copy">
              <p className="supporting-copy">
                Describe the roles you want. We use this prompt directly during AI title screening and deeper relevance review.
              </p>
            </div>

            <form className="form-grid" onSubmit={handleProfileSubmit}>
              <label className="full-width">
                <span>Prompt</span>
                <textarea rows={4} value={prompt} onChange={(event) => setPrompt(event.target.value)} />
              </label>
              <p className="supporting-copy full-width">
                During sync, discovered job titles are screened in AI batches against this prompt first. Only plausible titles move on to deeper relevance checks.
              </p>
              {status ? <p className="success-copy">{status}</p> : null}
              <div className="button-row">
                <button disabled={submitting || !prompt.trim()} type="submit">
                  {submitting ? "Working..." : "Save role profile"}
                </button>
              </div>
            </form>

            <div className="profile-preference-card">
              <div className="profile-preference-header">
                <div>
                  <h2>Timezone</h2>
                  <p className="supporting-copy">
                    Source sync times are stored in UTC and displayed here in the timezone you choose.
                  </p>
                </div>
                <div className="profile-timezone-current">
                  <span className="profile-timezone-current-label">Current</span>
                  <strong>{timezone}</strong>
                </div>
              </div>

              <div className="profile-timezone-meta">
                <span className="profile-timezone-note">Browser detected: {getBrowserTimezone()}</span>
                <span className="profile-timezone-note">Applies to source sync timestamps in this portal.</span>
              </div>

              <div className="profile-timezone-quick-picks" role="group" aria-label="Common timezone choices">
                {TIMEZONE_QUICK_PICKS.map((option) => (
                  <button
                    key={option}
                    type="button"
                    className={timezone === option ? "profile-timezone-chip active" : "profile-timezone-chip"}
                    onClick={() => {
                      setTimezone(option);
                      setTimezoneStatus(`Timezone set to ${option}.`);
                    }}
                  >
                    {option}
                  </button>
                ))}
              </div>

              <label className="full-width profile-timezone-field">
                <span>Choose another timezone</span>
                <select
                  value={timezone}
                  onChange={(event) => {
                    setTimezone(event.target.value);
                    setTimezoneStatus(`Timezone set to ${event.target.value}.`);
                  }}
                >
                  {COMMON_TIMEZONES.includes(timezone) ? null : <option value={timezone}>{timezone}</option>}
                  {COMMON_TIMEZONES.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </label>
              {timezoneStatus ? <p className="success-copy">{timezoneStatus}</p> : null}
            </div>
          </section>
        ) : null}

        {currentTab === "answers" ? (
          <section className="profile-section" aria-label="Saved answers section">
            <div className="profile-section-copy">
              <p className="supporting-copy">
                Edit the reusable answers and uploads that power autofill across application flows.
              </p>
            </div>

            <div className="content-grid">
              <article className="panel-card profile-subcard">
                {answers.length === 0 ? (
                  <p className="empty-copy">No saved answers yet.</p>
                ) : (
                  <ul className="stack-list">
                    {answers.map((answer) => (
                      <li key={answer.id} className="stack-row stack-row-column">
                        <strong>{answer.label}</strong>
                        <span>{describeAnswerValue(answer)}</span>
                        <button type="button" className="secondary-button" onClick={() => handleEdit(answer)}>
                          Edit
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </article>

              <article className="panel-card profile-subcard">
                <h2>{editingAnswerId !== null ? "Edit answer" : "Add answer"}</h2>
                <p className="supporting-copy">
                  Template links are attached automatically when you save an answer from the Questions screen.
                </p>
                <form className="form-grid" onSubmit={handleAnswerSubmit}>
                  <label>
                    <span>Label</span>
                    <input
                      value={form.label}
                      onChange={(event) => setForm((current) => ({ ...current, label: event.target.value }))}
                    />
                  </label>
                  <label className="full-width">
                    <span>Answer text</span>
                    <textarea
                      rows={5}
                      value={form.answer_text ?? ""}
                      onChange={(event) => setForm((current) => ({ ...current, answer_text: event.target.value }))}
                    />
                  </label>
                  {answerError ? <p className="error-copy">{answerError}</p> : null}
                  <div className="button-row">
                    <button type="submit">{editingAnswerId !== null ? "Save changes" : "Save answer"}</button>
                    {editingAnswerId !== null ? (
                      <button type="button" className="secondary-button" onClick={handleCancelEdit}>
                        Cancel
                      </button>
                    ) : null}
                  </div>
                </form>
              </article>
            </div>
          </section>
        ) : null}

        {currentTab === "application-accounts" ? (
          <section className="profile-section" aria-label="Application accounts section">
            <div className="profile-section-copy">
              <p className="supporting-copy">
                Store login credentials for platforms that use returning-candidate accounts or employer-specific portals. Passwords stay write-only.
              </p>
            </div>

            <div className="content-grid">
              <article className="panel-card profile-subcard">
                {applicationAccounts.length === 0 ? (
                  <p className="empty-copy">No application accounts saved yet.</p>
                ) : (
                  <ul className="stack-list">
                    {applicationAccounts.map((account) => (
                      <li key={account.id} className="stack-row stack-row-column">
                        <strong>{account.platform_label}</strong>
                        <span>{describeTenantHost(account.tenant_host)}</span>
                        <span>{account.login_identifier_masked}</span>
                        <span>{describeCredentialStatus(account)}</span>
                        {account.last_failure_message ? <span>{account.last_failure_message}</span> : null}
                        <div className="button-row">
                          <button type="button" className="secondary-button" onClick={() => handleEditApplicationAccount(account)}>
                            Edit
                          </button>
                          <button
                            type="button"
                            className="ghost-button"
                            disabled={deletingApplicationAccountId === account.id}
                            onClick={() => void handleDeleteApplicationAccount(account.id)}
                          >
                            {deletingApplicationAccountId === account.id ? "Deleting..." : "Delete"}
                          </button>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </article>

              <article className="panel-card profile-subcard">
                <h2>{editingApplicationAccountId !== null ? "Edit application account" : "Add application account"}</h2>
                <p className="supporting-copy">
                  Use employer host when a platform keeps separate candidate logins per company. Leave it blank when one login works everywhere.
                </p>
                <form className="form-grid" onSubmit={handleApplicationAccountSubmit}>
                  <label>
                    <span>Platform</span>
                    <select
                      value={applicationAccountForm.platform_family}
                      onChange={(event) =>
                        setApplicationAccountForm((current) => ({ ...current, platform_family: event.target.value }))
                      }
                    >
                      {APPLICATION_ACCOUNT_PLATFORM_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    <span>Employer host</span>
                    <input
                      placeholder="acme.icims.com"
                      value={applicationAccountForm.tenant_host}
                      onChange={(event) =>
                        setApplicationAccountForm((current) => ({ ...current, tenant_host: event.target.value }))
                      }
                    />
                  </label>
                  <label>
                    <span>Login email or username</span>
                    <input
                      placeholder={
                        editingApplicationAccountId !== null
                          ? "Leave blank to keep the current login"
                          : "candidate@example.com"
                      }
                      value={applicationAccountForm.login_identifier}
                      onChange={(event) =>
                        setApplicationAccountForm((current) => ({ ...current, login_identifier: event.target.value }))
                      }
                    />
                  </label>
                  <label>
                    <span>{editingApplicationAccountId !== null ? "New password (optional)" : "Password"}</span>
                    <input
                      type="password"
                      value={applicationAccountForm.password}
                      onChange={(event) =>
                        setApplicationAccountForm((current) => ({ ...current, password: event.target.value }))
                      }
                    />
                  </label>
                  {applicationAccountError ? <p className="error-copy">{applicationAccountError}</p> : null}
                  {applicationAccountStatus ? <p className="success-copy">{applicationAccountStatus}</p> : null}
                  <div className="button-row">
                    <button
                      type="submit"
                      disabled={
                        applicationAccountSubmitting
                        || (editingApplicationAccountId === null && !applicationAccountForm.login_identifier.trim())
                        || (editingApplicationAccountId === null && !applicationAccountForm.password.trim())
                      }
                    >
                      {applicationAccountSubmitting
                        ? "Working..."
                        : editingApplicationAccountId !== null
                          ? "Save account changes"
                          : "Save application account"}
                    </button>
                    {editingApplicationAccountId !== null ? (
                      <button type="button" className="secondary-button" onClick={handleCancelApplicationAccountEdit}>
                        Cancel
                      </button>
                    ) : null}
                  </div>
                </form>
              </article>
            </div>
          </section>
        ) : null}
      </section>
    </main>
  );
}
