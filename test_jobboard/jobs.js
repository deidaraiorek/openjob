export const JOBS = [
  {
    id: "swe-backend-001",
    title: "Senior Backend Engineer",
    department: "Engineering",
    location: "Remote",
    type: "Full-time",
    salary: "$160,000 – $200,000",
    posted: "2026-04-10",
    description: `
      <p>We're looking for a Senior Backend Engineer to join our platform team.</p>
      <h3>What you'll do</h3>
      <ul>
        <li>Design and implement scalable microservices in Python and Go</li>
        <li>Own reliability and performance of core APIs</li>
        <li>Mentor junior engineers and lead technical design reviews</li>
      </ul>
      <h3>Requirements</h3>
      <ul>
        <li>5+ years of backend engineering experience</li>
        <li>Strong proficiency in Python or Go</li>
        <li>Experience with PostgreSQL, Redis, and distributed systems</li>
      </ul>
    `,
    questions: [
      { id: "first_name",         label: "First Name",               type: "text",     required: true,  placeholder: "Jane" },
      { id: "last_name",          label: "Last Name",                type: "text",     required: true,  placeholder: "Smith" },
      { id: "email",              label: "Email Address",            type: "email",    required: true,  placeholder: "jane@example.com" },
      { id: "phone",              label: "Phone Number",             type: "tel",      required: false, placeholder: "+1 555 000 0000" },
      { id: "linkedin",           label: "LinkedIn Profile URL",     type: "url",      required: false, placeholder: "https://linkedin.com/in/yourname" },
      { id: "resume",             label: "Resume",                   type: "file",     required: true  },
      {
        id: "years_experience", label: "Years of Experience", type: "select", required: true,
        options: ["Less than 1 year", "1–3 years", "3–5 years", "5–8 years", "8+ years"],
      },
      { id: "current_location",   label: "Current Location",         type: "text",     required: true,  placeholder: "San Francisco, CA" },
      {
        id: "preferred_location", label: "Preferred Office Location", type: "radio", required: true,
        options: ["New York, NY", "San Francisco, CA", "Tampa, FL"],
      },
      {
        id: "work_authorization", label: "Work Authorization", type: "select", required: true,
        options: ["US Citizen", "Permanent Resident (Green Card)", "H-1B Visa (requires sponsorship)", "EAD / OPT", "Other / Non-US"],
      },
      {
        id: "sponsorship",        label: "Do you require visa sponsorship?", type: "radio", required: true,
        options: ["Yes", "No"],
      },
      {
        id: "interests",          label: "Areas of Interest",        type: "checkbox", required: false,
        options: ["APIs & Microservices", "Databases & Storage", "Distributed Systems", "Developer Tooling"],
      },
      { id: "salary_expectation", label: "Salary Expectation",       type: "text",     required: false, placeholder: "$160,000" },
      { id: "cover_letter",       label: "Cover Letter",             type: "textarea", required: false, placeholder: "Tell us why you're excited about this role..." },
    ],
  },

  {
    id: "swe-frontend-002",
    title: "Frontend Engineer",
    department: "Engineering",
    location: "Remote",
    type: "Full-time",
    salary: "$130,000 – $160,000",
    posted: "2026-04-12",
    description: `
      <p>Join our product team to build beautiful, fast, and accessible user interfaces.</p>
      <h3>What you'll do</h3>
      <ul>
        <li>Build React components and pages with TypeScript</li>
        <li>Collaborate closely with designers to implement pixel-perfect UI</li>
        <li>Optimize for performance and accessibility</li>
      </ul>
      <h3>Requirements</h3>
      <ul>
        <li>3+ years of frontend experience</li>
        <li>Expert-level React and TypeScript</li>
        <li>Strong understanding of web performance fundamentals</li>
      </ul>
    `,
    questions: [
      { id: "first_name",         label: "First Name",               type: "text",     required: true,  placeholder: "Jane" },
      { id: "family_name",        label: "Family Name",              type: "text",     required: true,  placeholder: "Smith" },
      { id: "email",              label: "Email Address",            type: "email",    required: true,  placeholder: "jane@example.com" },
      { id: "phone",              label: "Phone Number",             type: "tel",      required: false, placeholder: "+1 555 000 0000" },
      { id: "github",             label: "GitHub / Portfolio URL",   type: "url",      required: false, placeholder: "https://github.com/yourname" },
      { id: "resume",             label: "Resume",                   type: "file",     required: true  },
      {
        id: "years_experience", label: "Years of Experience", type: "select", required: true,
        options: ["Less than 1 year", "1–3 years", "3–5 years", "5–8 years", "8+ years"],
      },
      { id: "current_location",   label: "Current Location",         type: "text",     required: true,  placeholder: "New York, NY" },
      {
        id: "preferred_location", label: "Preferred Office Location", type: "radio", required: true,
        options: ["Houston, TX", "Boston, MA", "Philadelphia, PA"],
      },
      {
        id: "work_authorization", label: "Work Authorization", type: "select", required: true,
        options: ["US Citizen", "Permanent Resident (Green Card)", "H-1B Visa (requires sponsorship)", "EAD / OPT", "Other / Non-US"],
      },
      {
        id: "willing_relocate",   label: "Are you willing to relocate?", type: "radio", required: true,
        options: ["Yes", "No", "Open to discussion"],
      },
      {
        id: "tech_stack",         label: "Frameworks you know well", type: "checkbox", required: false,
        options: ["React", "Vue", "Angular", "Svelte", "Next.js"],
      },
      { id: "salary_expectation", label: "Salary Expectation",       type: "text",     required: false, placeholder: "$140,000" },
      { id: "cover_letter",       label: "Cover Letter",             type: "textarea", required: false, placeholder: "Tell us why you're excited about this role..." },
    ],
  },

  {
    id: "ml-engineer-003",
    title: "Machine Learning Engineer",
    department: "AI Research",
    location: "San Francisco, CA or Remote",
    type: "Full-time",
    salary: "$180,000 – $240,000",
    posted: "2026-04-08",
    description: `
      <p>We're building the next generation of AI-powered developer tools.</p>
      <h3>What you'll do</h3>
      <ul>
        <li>Fine-tune and evaluate LLMs for code generation tasks</li>
        <li>Build retrieval-augmented generation (RAG) pipelines</li>
        <li>Deploy and monitor models in production at scale</li>
      </ul>
      <h3>Requirements</h3>
      <ul>
        <li>3+ years of ML engineering experience</li>
        <li>Hands-on experience with PyTorch or JAX</li>
        <li>Strong Python skills and software engineering fundamentals</li>
      </ul>
    `,
    questions: [
      { id: "given_name",         label: "Given Name",               type: "text",     required: true,  placeholder: "Jane" },
      { id: "surname",            label: "Surname",                  type: "text",     required: true,  placeholder: "Smith" },
      { id: "email",              label: "Email Address",            type: "email",    required: true,  placeholder: "jane@example.com" },
      { id: "linkedin",           label: "LinkedIn Profile URL",     type: "url",      required: false, placeholder: "https://linkedin.com/in/yourname" },
      { id: "resume",             label: "Resume",                   type: "file",     required: true  },
      {
        id: "years_experience", label: "Years of Experience", type: "select", required: true,
        options: ["Less than 1 year", "1–3 years", "3–5 years", "5–8 years", "8+ years"],
      },
      { id: "current_location",   label: "Current Location",         type: "text",     required: true,  placeholder: "San Francisco, CA" },
      {
        id: "preferred_location", label: "Preferred Office Location", type: "radio", required: true,
        options: ["New York, NY", "Idaho Falls, ID", "Minneapolis, MN"],
      },
      {
        id: "work_authorization", label: "Work Authorization", type: "select", required: true,
        options: ["US Citizen", "Permanent Resident (Green Card)", "H-1B Visa (requires sponsorship)", "EAD / OPT", "Other / Non-US"],
      },
      {
        id: "sponsorship",        label: "Do you require visa sponsorship?", type: "radio", required: true,
        options: ["Yes", "No"],
      },
      {
        id: "ml_frameworks",      label: "ML frameworks you've used", type: "checkbox", required: true,
        options: ["PyTorch", "TensorFlow", "JAX", "Scikit-learn", "Hugging Face Transformers"],
      },
      {
        id: "remote_preference",  label: "Work style preference",    type: "radio",    required: true,
        options: ["Fully remote", "Hybrid (2–3 days in office)", "On-site preferred"],
      },
      { id: "salary_expectation", label: "Salary Expectation",       type: "text",     required: false, placeholder: "$200,000" },
      { id: "cover_letter",       label: "Cover Letter",             type: "textarea", required: true,  placeholder: "Describe a model you've trained or a system you've shipped..." },
    ],
  },

  {
    id: "devrel-004",
    title: "Developer Advocate",
    department: "Developer Relations",
    location: "Remote",
    type: "Full-time",
    salary: "$120,000 – $150,000",
    posted: "2026-04-14",
    description: `
      <p>Help developers succeed with our platform. You'll create content, speak at conferences, and be the voice of our developer community.</p>
      <h3>What you'll do</h3>
      <ul>
        <li>Create tutorials, blog posts, and demo apps</li>
        <li>Speak at developer conferences and meetups</li>
        <li>Build and grow our open source community</li>
      </ul>
      <h3>Requirements</h3>
      <ul>
        <li>3+ years of software development experience</li>
        <li>Excellent written and verbal communication skills</li>
        <li>Genuine passion for developer communities</li>
      </ul>
    `,
    questions: [
      { id: "first_name",         label: "First Name",               type: "text",     required: true,  placeholder: "Jane" },
      { id: "last_name",          label: "Last Name",                type: "text",     required: true,  placeholder: "Smith" },
      { id: "email",              label: "Email",                    type: "email",    required: true,  placeholder: "jane@example.com" },
      { id: "phone",              label: "Phone Number",             type: "tel",      required: false, placeholder: "+1 555 000 0000" },
      { id: "linkedin",           label: "LinkedIn URL",             type: "url",      required: false, placeholder: "https://linkedin.com/in/yourname" },
      { id: "github",             label: "GitHub / Portfolio URL",   type: "url",      required: false, placeholder: "https://github.com/yourname" },
      { id: "resume",             label: "Resume / CV",              type: "file",     required: true  },
      {
        id: "years_experience", label: "Years of Experience", type: "select", required: true,
        options: ["Less than 1 year", "1–3 years", "3–5 years", "5–8 years", "8+ years"],
      },
      { id: "current_location",   label: "Current Location",         type: "text",     required: true,  placeholder: "Austin, TX" },
      {
        id: "preferred_location", label: "Preferred Office Location", type: "radio", required: true,
        options: ["New York, NY", "San Francisco, CA", "Tampa, FL"],
      },
      {
        id: "work_authorization", label: "Work Authorization", type: "select", required: true,
        options: ["US Citizen", "Permanent Resident (Green Card)", "H-1B Visa (requires sponsorship)", "EAD / OPT", "Other / Non-US"],
      },
      {
        id: "willing_relocate",   label: "Are you willing to relocate?", type: "radio", required: true,
        options: ["Yes", "No", "Open to discussion"],
      },
      {
        id: "content_types",      label: "Content you've created",   type: "checkbox", required: false,
        options: ["Blog posts", "Video tutorials", "Conference talks", "Open source demos", "Podcasts"],
      },
      {
        id: "remote_preference",  label: "Work style preference",    type: "radio",    required: true,
        options: ["Fully remote", "Hybrid (2–3 days in office)", "On-site preferred"],
      },
      { id: "portfolio_url",      label: "Portfolio or Blog URL",    type: "url",      required: false, placeholder: "https://yourblog.dev" },
      { id: "cover_letter",       label: "Cover Letter",             type: "textarea", required: false, placeholder: "Tell us about a piece of content you're proud of..." },
    ],
  },

  {
    id: "combobox-test-006",
    title: "Combobox Test Role",
    department: "QA",
    location: "Remote",
    type: "Full-time",
    salary: "$100,000",
    posted: "2026-04-25",
    description: "<p>Test job for combobox field validation.</p>",
    questions: [
      { id: "first_name", label: "First Name", type: "text", required: true, placeholder: "Jane" },
      { id: "email",      label: "Email Address", type: "email", required: true, placeholder: "jane@example.com" },
      {
        id: "country", label: "Country of Residence", type: "combobox", required: true,
        placeholder: "Select a country…",
        options: ["United States", "Canada", "United Kingdom", "Australia", "Germany", "Other"],
      },
      {
        id: "timezone", label: "Primary Timezone", type: "combobox", required: true,
        placeholder: "Select a timezone…",
        options: ["Pacific Time (PT)", "Mountain Time (MT)", "Central Time (CT)", "Eastern Time (ET)", "UTC", "Other"],
      },
      { id: "cover_letter", label: "Cover Letter", type: "textarea", required: false, placeholder: "Tell us about yourself..." },
    ],
  },

  {
    id: "infra-engineer-005",
    title: "Infrastructure Engineer",
    department: "Platform",
    location: "Remote",
    type: "Full-time",
    salary: "$150,000 – $190,000",
    posted: "2026-04-11",
    description: `
      <p>Own our cloud infrastructure and make it bulletproof. You'll work on Kubernetes, CI/CD, observability, and developer experience tooling.</p>
      <h3>What you'll do</h3>
      <ul>
        <li>Manage and evolve our Kubernetes clusters across multiple cloud regions</li>
        <li>Build and maintain CI/CD pipelines</li>
        <li>Drive reliability improvements and incident response</li>
      </ul>
      <h3>Requirements</h3>
      <ul>
        <li>4+ years of infrastructure or DevOps experience</li>
        <li>Deep Kubernetes and Terraform expertise</li>
        <li>Experience with AWS, GCP, or Azure</li>
      </ul>
    `,
    questions: [
      { id: "first_name",         label: "First Name",               type: "text",     required: true,  placeholder: "Jane" },
      { id: "last_name",          label: "Last Name",                type: "text",     required: true,  placeholder: "Smith" },
      { id: "email_address",      label: "Email Address",            type: "email",    required: true,  placeholder: "jane@example.com" },
      { id: "mobile_number",      label: "Mobile Number",            type: "tel",      required: false, placeholder: "+1 555 000 0000" },
      { id: "resume",             label: "Resume",                   type: "file",     required: true  },
      {
        id: "years_experience", label: "Years of Experience", type: "select", required: true,
        options: ["Less than 1 year", "1–3 years", "3–5 years", "5–8 years", "8+ years"],
      },
      { id: "current_location",   label: "Current Location",         type: "text",     required: true,  placeholder: "Seattle, WA" },
      {
        id: "preferred_location", label: "Preferred Office Location", type: "radio", required: true,
        options: ["Houston, TX", "Boston, MA", "Philadelphia, PA"],
      },
      {
        id: "work_authorization", label: "Work Authorization", type: "select", required: true,
        options: ["US Citizen", "Permanent Resident (Green Card)", "H-1B Visa (requires sponsorship)", "EAD / OPT", "Other / Non-US"],
      },
      {
        id: "requires_sponsorship", label: "Do you need sponsorship?", type: "radio", required: true,
        options: ["Yes", "No"],
      },
      {
        id: "cloud_providers",    label: "Cloud platforms you've worked with", type: "checkbox", required: true,
        options: ["AWS", "Google Cloud (GCP)", "Azure", "DigitalOcean", "Bare metal / on-prem"],
      },
      {
        id: "on_call",            label: "Comfortable with on-call rotations?", type: "radio", required: true,
        options: ["Yes", "Yes, with reasonable compensation", "No"],
      },
      {
        id: "remote_preference",  label: "Work style preference",    type: "radio",    required: true,
        options: ["Fully remote", "Hybrid (2–3 days in office)", "On-site preferred"],
      },
      { id: "salary_expectation", label: "Salary Expectation",       type: "text",     required: false, placeholder: "$170,000" },
      { id: "cover_letter",       label: "Cover Letter",             type: "textarea", required: false, placeholder: "Describe the infrastructure challenge you're most proud of solving..." },
    ],
  },
];
