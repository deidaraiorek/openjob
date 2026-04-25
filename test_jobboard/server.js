import express from "express";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import multer from "multer";
import { JOBS } from "./jobs.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const app = express();
const PORT = process.env.PORT || 4000;

const SUBMISSIONS_FILE = path.join(__dirname, "submissions.json");
const UPLOADS_DIR = path.join(__dirname, "uploads");
fs.mkdirSync(UPLOADS_DIR, { recursive: true });

const upload = multer({ dest: UPLOADS_DIR });

function loadSubmissions() {
  try { return JSON.parse(fs.readFileSync(SUBMISSIONS_FILE, "utf-8")); }
  catch { return []; }
}

function saveSubmissions(submissions) {
  fs.writeFileSync(SUBMISSIONS_FILE, JSON.stringify(submissions, null, 2));
}

function saveSubmission(data) {
  const submissions = loadSubmissions();
  submissions.push({ ...data, id: Date.now(), submitted_at: new Date().toISOString() });
  saveSubmissions(submissions);
}

function deleteSubmission(id) {
  const submissions = loadSubmissions();
  const filtered = submissions.filter((s) => String(s.id) !== String(id));
  saveSubmissions(filtered);
  return submissions.length !== filtered.length;
}

app.use(express.urlencoded({ extended: true }));
app.use(express.json());
app.use(express.static(path.join(__dirname, "public")));

const NAV = `
<nav style="background:#1a1a2e;padding:16px 32px;display:flex;align-items:center;justify-content:space-between;">
  <a href="/" style="color:#fff;font-weight:700;font-size:20px;text-decoration:none;letter-spacing:-0.5px;">
    <span style="color:#7c6af7;">●</span> NovaCorp Jobs
  </a>
  <div style="display:flex;gap:24px;align-items:center;">
    <a href="/" style="color:#aaa;text-decoration:none;font-size:14px;">All Jobs</a>
    <a href="/admin" style="color:#aaa;text-decoration:none;font-size:14px;">Admin</a>
  </div>
</nav>`;

const BASE_STYLE = `
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f8f9fc;color:#1a1a2e;line-height:1.6}
  a{color:#7c6af7}
  .container{max-width:960px;margin:0 auto;padding:0 24px}
  .badge{display:inline-block;padding:3px 10px;border-radius:99px;font-size:12px;font-weight:600}
  .badge-type{background:#ede9fe;color:#6d28d9}
  .badge-dept{background:#e0f2fe;color:#0369a1}
  .badge-location{background:#f0fdf4;color:#166534}
  input[type=text],input[type=email],input[type=tel],input[type=url],input[type=number],textarea,select{width:100%;padding:10px 14px;border:1px solid #d1d5db;border-radius:8px;font-size:14px;font-family:inherit;background:#fff;color:#1a1a2e}
  input[type=text]:focus,input[type=email]:focus,input[type=tel]:focus,input[type=url]:focus,textarea:focus,select:focus{outline:none;border-color:#7c6af7;box-shadow:0 0 0 3px rgba(124,106,247,0.1)}
  input[type=file]{width:100%;padding:8px 0;font-size:14px;color:#374151}
  label.field-label{display:block;font-size:13px;font-weight:600;color:#374151;margin-bottom:6px}
  .radio-group,.checkbox-group{display:flex;flex-direction:column;gap:8px}
  .radio-group label,.checkbox-group label{display:flex;align-items:center;gap:8px;font-size:14px;font-weight:400;color:#1a1a2e;cursor:pointer}
  .radio-group input,.checkbox-group input{width:auto;accent-color:#7c6af7}
  .file-hint{font-size:12px;color:#9ca3af;margin-top:4px}
  .btn{display:inline-block;padding:11px 24px;background:#7c6af7;color:#fff;border:none;border-radius:8px;font-size:15px;font-weight:600;cursor:pointer;text-decoration:none;transition:background 0.15s}
  .btn:hover{background:#6a58e0}
  .btn-secondary{background:#fff;color:#374151;border:1px solid #d1d5db}
  .btn-secondary:hover{background:#f9fafb}
  .btn-danger{background:#fff;color:#dc2626;border:1px solid #fca5a5;font-size:12px;padding:6px 12px;border-radius:6px;cursor:pointer}
  .btn-danger:hover{background:#fef2f2}
  .required-star{color:#dc2626;margin-left:2px}
</style>`;

function renderField(q) {
  const required = q.required ? 'required' : '';
  const star = q.required ? '<span class="required-star">*</span>' : '';

  if (q.type === "select") {
    const opts = q.options.map((o) => `<option value="${o}">${o}</option>`).join("");
    return `
      <div>
        <label class="field-label" for="${q.id}">${q.label}${star}</label>
        <select id="${q.id}" name="${q.id}" ${required}>
          <option value="">Select…</option>
          ${opts}
        </select>
      </div>`;
  }

  if (q.type === "radio") {
    const opts = q.options.map((o) => `
      <label><input type="radio" name="${q.id}" value="${o}" ${required}> ${o}</label>`).join("");
    return `
      <div>
        <label class="field-label">${q.label}${star}</label>
        <div class="radio-group">${opts}</div>
      </div>`;
  }

  if (q.type === "checkbox") {
    const opts = q.options.map((o) => `
      <label><input type="checkbox" name="${q.id}" value="${o}"> ${o}</label>`).join("");
    return `
      <div>
        <label class="field-label">${q.label}${star}</label>
        <div class="checkbox-group">${opts}</div>
      </div>`;
  }

  if (q.type === "combobox") {
    const opts = q.options.map((o) => `<li role="option" data-value="${o}" style="padding:10px 14px;cursor:pointer;font-size:14px" onmouseover="this.style.background='#ede9fe'" onmouseout="this.style.background=''">${o}</li>`).join("");
    return `
      <div style="position:relative">
        <label class="field-label">${q.label}${star}</label>
        <input type="text" id="${q.id}" name="${q.id}" role="combobox" aria-label="${q.label}"
          placeholder="${q.placeholder || 'Type or select…'}" autocomplete="off" ${required}
          style="width:100%;padding:10px 14px;border:1px solid #d1d5db;border-radius:8px;font-size:14px"
          onfocus="document.getElementById('${q.id}-list').style.display='block'"
          onblur="setTimeout(()=>document.getElementById('${q.id}-list').style.display='none',150)">
        <ul id="${q.id}-list" role="listbox"
          style="display:none;position:absolute;z-index:99;width:100%;background:#fff;border:1px solid #d1d5db;border-radius:8px;margin-top:4px;padding:4px 0;list-style:none;box-shadow:0 4px 16px rgba(0,0,0,0.08)">
          ${opts}
        </ul>
        <script>
          document.querySelectorAll('#${q.id}-list [role=option]').forEach(opt => {
            opt.addEventListener('mousedown', e => {
              e.preventDefault();
              document.getElementById('${q.id}').value = opt.dataset.value;
              document.getElementById('${q.id}-list').style.display = 'none';
            });
          });
        </script>
      </div>`;
  }

  if (q.type === "textarea") {
    return `
      <div>
        <label class="field-label" for="${q.id}">${q.label}${star}</label>
        <textarea id="${q.id}" name="${q.id}" rows="5" placeholder="${q.placeholder || ''}" ${required}></textarea>
      </div>`;
  }

  if (q.type === "file") {
    return `
      <div>
        <label class="field-label" for="${q.id}">${q.label}${star}</label>
        <input type="file" id="${q.id}" name="${q.id}" accept=".pdf,.doc,.docx" ${required}>
        <p class="file-hint">PDF, DOC, or DOCX — max 10 MB</p>
      </div>`;
  }

  return `
    <div>
      <label class="field-label" for="${q.id}">${q.label}${star}</label>
      <input type="${q.type}" id="${q.id}" name="${q.id}" placeholder="${q.placeholder || ''}" ${required}>
    </div>`;
}

// ── Public routes ────────────────────────────────────────────

app.get("/api/jobs", (req, res) => {
  res.json(JOBS.map(({ id, title, department, location, type, salary, posted }) => ({
    id, title, department, location, type, salary, posted,
  })));
});

app.get("/", (req, res) => {
  const cards = JOBS.map((j) => `
    <a href="/jobs/${j.id}" style="text-decoration:none;color:inherit;display:block;background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:24px;transition:box-shadow 0.15s,border-color 0.15s" onmouseover="this.style.boxShadow='0 4px 20px rgba(0,0,0,0.08)';this.style.borderColor='#7c6af7'" onmouseout="this.style.boxShadow='none';this.style.borderColor='#e5e7eb'">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:16px;flex-wrap:wrap">
        <div>
          <h3 style="font-size:17px;font-weight:700;margin-bottom:8px;letter-spacing:-0.01em">${j.title}</h3>
          <div style="display:flex;gap:8px;flex-wrap:wrap">
            <span class="badge badge-dept">${j.department}</span>
            <span class="badge badge-location">${j.location}</span>
            <span class="badge badge-type">${j.type}</span>
          </div>
        </div>
        <div style="text-align:right;flex-shrink:0">
          <div style="font-size:15px;font-weight:700">${j.salary}</div>
          <div style="font-size:12px;color:#9ca3af;margin-top:4px">Posted ${j.posted}</div>
        </div>
      </div>
    </a>`).join("");

  res.send(`<!DOCTYPE html><html><head>${BASE_STYLE}<title>NovaCorp Jobs</title></head><body>
${NAV}
<div class="container" style="padding-top:48px;padding-bottom:64px">
  <div style="margin-bottom:40px">
    <h1 style="font-size:32px;font-weight:800;margin-bottom:8px">Open Positions</h1>
    <p style="color:#6b7280;font-size:16px">Join NovaCorp — we're building the future of developer tooling.</p>
  </div>
  <div style="display:flex;flex-direction:column;gap:16px">${cards}</div>
</div>
</body></html>`);
});

app.get("/jobs/:id", (req, res) => {
  const job = JOBS.find((j) => j.id === req.params.id);
  if (!job) return res.status(404).send("Job not found");

  res.send(`<!DOCTYPE html><html><head>${BASE_STYLE}<title>${job.title} – NovaCorp</title></head><body>
${NAV}
<div class="container" style="padding-top:40px;padding-bottom:64px">
  <a href="/" style="font-size:14px;color:#6b7280;text-decoration:none;display:inline-flex;align-items:center;gap:6px;margin-bottom:28px">← All Jobs</a>
  <div style="display:grid;grid-template-columns:1fr 320px;gap:32px;align-items:flex-start">
    <div>
      <div style="margin-bottom:24px">
        <h1 style="font-size:28px;font-weight:800;margin-bottom:12px">${job.title}</h1>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <span class="badge badge-dept">${job.department}</span>
          <span class="badge badge-location">${job.location}</span>
          <span class="badge badge-type">${job.type}</span>
        </div>
      </div>
      <div style="background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:28px;font-size:15px;line-height:1.7">${job.description}</div>
    </div>
    <div style="position:sticky;top:24px">
      <div style="background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:24px">
        <div style="font-size:22px;font-weight:800;margin-bottom:4px">${job.salary}</div>
        <div style="color:#6b7280;font-size:13px;margin-bottom:20px">Posted ${job.posted}</div>
        <a href="/jobs/${job.id}/apply" class="btn" style="display:block;text-align:center;margin-bottom:12px">Apply Now</a>
        <a href="/" class="btn btn-secondary" style="display:block;text-align:center">Back to Jobs</a>
      </div>
    </div>
  </div>
</div>
<style>
  @media(max-width:700px){div[style*="grid-template-columns"]{grid-template-columns:1fr!important}}
  h3{font-size:16px;font-weight:700;margin:20px 0 8px} ul{padding-left:20px} li{margin-bottom:4px} p{margin-bottom:12px}
</style>
</body></html>`);
});

app.get("/jobs/:id/apply", (req, res) => {
  const job = JOBS.find((j) => j.id === req.params.id);
  if (!job) return res.status(404).send("Job not found");

  const fields = job.questions.map(renderField).join("\n");
  const hasFile = job.questions.some((q) => q.type === "file");
  const enctype = hasFile ? 'enctype="multipart/form-data"' : '';

  res.send(`<!DOCTYPE html><html><head>${BASE_STYLE}<title>Apply – ${job.title}</title></head><body>
${NAV}
<div class="container" style="padding-top:40px;padding-bottom:64px">
  <a href="/jobs/${job.id}" style="font-size:14px;color:#6b7280;text-decoration:none;display:inline-flex;align-items:center;gap:6px;margin-bottom:28px">← Back to Job</a>
  <div style="max-width:640px">
    <h1 style="font-size:24px;font-weight:800;margin-bottom:4px">Apply for ${job.title}</h1>
    <p style="color:#6b7280;font-size:14px;margin-bottom:32px">${job.department} · ${job.location}</p>
    <form method="POST" action="/jobs/${job.id}/apply" ${enctype} style="display:flex;flex-direction:column;gap:20px">
      ${fields}
      <div style="display:flex;gap:12px;padding-top:8px">
        <button type="submit" class="btn">Submit Application</button>
        <a href="/jobs/${job.id}" class="btn btn-secondary">Cancel</a>
      </div>
    </form>
  </div>
</div>
</body></html>`);
});

app.post("/jobs/:id/apply", upload.single("resume"), (req, res) => {
  const job = JOBS.find((j) => j.id === req.params.id);
  if (!job) return res.status(404).send("Job not found");

  const fields = {};
  for (const q of job.questions) {
    if (q.type === "file") {
      fields[q.id] = req.file ? req.file.originalname : null;
    } else if (q.type === "checkbox") {
      const val = req.body[q.id];
      fields[q.id] = Array.isArray(val) ? val : val ? [val] : [];
    } else {
      fields[q.id] = req.body[q.id] ?? null;
    }
  }

  saveSubmission({ job_id: job.id, job_title: job.title, department: job.department, ...fields });

  res.send(`<!DOCTYPE html><html><head>${BASE_STYLE}<title>Application Submitted</title></head><body>
${NAV}
<div class="container" style="padding-top:80px;padding-bottom:64px;text-align:center;max-width:520px">
  <div style="font-size:56px;margin-bottom:20px">🎉</div>
  <h1 style="font-size:26px;font-weight:800;margin-bottom:12px">Application Submitted!</h1>
  <p style="color:#6b7280;font-size:15px;margin-bottom:32px">
    Thanks for applying for <strong>${job.title}</strong>. We'll review your application and get back to you within 5–7 business days.
  </p>
  <a href="/" class="btn">View More Jobs</a>
</div>
</body></html>`);
});

// ── Admin routes ─────────────────────────────────────────────

app.get("/admin", (req, res) => {
  const submissions = loadSubmissions();

  const rows = submissions.length === 0
    ? `<tr><td colspan="7" style="padding:40px;text-align:center;color:#9ca3af">No applications yet.</td></tr>`
    : submissions.slice().reverse().map((s) => {
        const name = [s.first_name || s.given_name || "", s.last_name || s.family_name || s.surname || ""].join(" ").trim() || "—";
        const email = s.email || s.email_address || "—";
        return `
        <tr style="border-bottom:1px solid #f3f4f6">
          <td style="padding:12px 16px;font-weight:600;font-size:13px">${name}</td>
          <td style="padding:12px 16px;font-size:13px;color:#6b7280">${email}</td>
          <td style="padding:12px 16px;font-size:13px">${s.job_title || "—"}</td>
          <td style="padding:12px 16px;font-size:13px;color:#6b7280">${s.department || "—"}</td>
          <td style="padding:12px 16px;font-size:13px;color:#6b7280">${s.years_experience || "—"}</td>
          <td style="padding:12px 16px;font-size:12px;color:#9ca3af">${new Date(s.submitted_at).toLocaleString()}</td>
          <td style="padding:12px 16px">
            <form method="POST" action="/admin/delete/${s.id}" onsubmit="return confirm('Delete this application?')">
              <button type="submit" class="btn-danger">Delete</button>
            </form>
          </td>
        </tr>`;
      }).join("");

  res.send(`<!DOCTYPE html><html><head>${BASE_STYLE}<title>Admin – NovaCorp</title></head><body>
${NAV}
<div class="container" style="padding-top:40px;padding-bottom:64px">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:28px;flex-wrap:wrap;gap:12px">
    <div>
      <h1 style="font-size:24px;font-weight:800;margin-bottom:4px">Applications</h1>
      <p style="color:#6b7280;font-size:14px">${submissions.length} total submission${submissions.length !== 1 ? "s" : ""}</p>
    </div>
    <div style="display:flex;gap:10px;align-items:center">
      <form method="POST" action="/admin/delete-all" onsubmit="return confirm('Delete ALL applications?')">
        <button type="submit" class="btn-danger" style="padding:8px 14px">Clear all</button>
      </form>
      <a href="/admin/export" class="btn btn-secondary" style="font-size:13px;padding:8px 16px">Export JSON</a>
    </div>
  </div>
  <div style="background:#fff;border:1px solid #e5e7eb;border-radius:12px;overflow:auto">
    <table style="width:100%;border-collapse:collapse">
      <thead>
        <tr style="border-bottom:2px solid #e5e7eb;background:#f9fafb">
          <th style="padding:12px 16px;text-align:left;font-size:11px;font-weight:700;color:#374151;text-transform:uppercase;letter-spacing:0.05em">Name</th>
          <th style="padding:12px 16px;text-align:left;font-size:11px;font-weight:700;color:#374151;text-transform:uppercase;letter-spacing:0.05em">Email</th>
          <th style="padding:12px 16px;text-align:left;font-size:11px;font-weight:700;color:#374151;text-transform:uppercase;letter-spacing:0.05em">Position</th>
          <th style="padding:12px 16px;text-align:left;font-size:11px;font-weight:700;color:#374151;text-transform:uppercase;letter-spacing:0.05em">Dept</th>
          <th style="padding:12px 16px;text-align:left;font-size:11px;font-weight:700;color:#374151;text-transform:uppercase;letter-spacing:0.05em">Experience</th>
          <th style="padding:12px 16px;text-align:left;font-size:11px;font-weight:700;color:#374151;text-transform:uppercase;letter-spacing:0.05em">Submitted</th>
          <th style="padding:12px 16px;text-align:left;font-size:11px;font-weight:700;color:#374151;text-transform:uppercase;letter-spacing:0.05em"></th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  </div>
</div>
</body></html>`);
});

app.post("/admin/delete/:id", (req, res) => {
  deleteSubmission(req.params.id);
  res.redirect("/admin");
});

app.post("/admin/delete-all", (req, res) => {
  saveSubmissions([]);
  res.redirect("/admin");
});

app.get("/admin/export", (req, res) => {
  const submissions = loadSubmissions();
  res.setHeader("Content-Type", "application/json");
  res.setHeader("Content-Disposition", "attachment; filename=applications.json");
  res.send(JSON.stringify(submissions, null, 2));
});

app.listen(PORT, () => {
  console.log(`Test job board running at http://localhost:${PORT}`);
  console.log(`Admin panel: http://localhost:${PORT}/admin`);
});
