// Elements
const tabs = document.querySelectorAll(".tab");
const panels = document.querySelectorAll(".panel");

const scrapeProfileBtn = document.getElementById("scrapeProfileBtn");
const profileStatus = document.getElementById("profileStatus");
const profileSaved = document.getElementById("profileSaved");
const profileExpCount = document.getElementById("profileExpCount");

const scrapeJobBtn = document.getElementById("scrapeJobBtn");
const jobStatus = document.getElementById("jobStatus");
const peekTitle = document.getElementById("peekTitle");
const peekCompany = document.getElementById("peekCompany");

const gaugeArc = document.getElementById("gaugeArc");
const gaugeVal = document.getElementById("gaugeVal");
const missingSkills = document.getElementById("missingSkills");
const diffLeft = document.getElementById("diffLeft");
const diffRight = document.getElementById("diffRight");
const regenBullet = document.getElementById("regenBullet");
const acceptBullet = document.getElementById("acceptBullet");

const composeResume = document.getElementById("composeResume");
const composeStatus = document.getElementById("composeStatus");
const latexPreview = document.getElementById("latexPreview");
const copyLatex = document.getElementById("copyLatex");

const downloadTex = document.getElementById("downloadTex");
const downloadPdf = document.getElementById("downloadPdf");
const exportStatus = document.getElementById("exportStatus");

const themeToggle = document.getElementById("themeToggle");
const openInTab = document.getElementById("openInTab");
const toastEl = document.getElementById("toast");

/* Tabs */
tabs.forEach(t => {
  t.addEventListener("click", () => {
    tabs.forEach(x => x.classList.remove("active"));
    t.classList.add("active");
    const id = t.dataset.tab;
    panels.forEach(p => p.classList.remove("active"));
    document.getElementById(`panel-${id}`).classList.add("active");
  });
});

/* Toast */
function toast(msg) {
  toastEl.textContent = msg;
  toastEl.classList.add("show");
  setTimeout(() => toastEl.classList.remove("show"), 1500);
}

/* Theme */
themeToggle.addEventListener("click", () => {
  document.body.classList.toggle("light");
});

/* Open in tab */
openInTab.addEventListener("click", () => {
  chrome.tabs.create({ url: chrome.runtime.getURL("popup.html") });
});

/* Helpers */
function activeTab() { return chrome.tabs.query({ active: true, currentWindow: true }); }

/* Messaging to content script */
async function send(tabId, message) {
  return new Promise(resolve => {
    chrome.tabs.sendMessage(tabId, message, resp => resolve(resp));
  });
}

/* 1) Save profile */
scrapeProfileBtn.addEventListener("click", async () => {
  profileStatus.textContent = "Scraping profile...";
  const [tab] = await activeTab();
  if (!tab?.id) return;

  const resp = await send(tab.id, { type: "SCRAPE_PROFILE" });
  if (!resp?.ok) {
    profileStatus.textContent = "Open your LinkedIn profile and try again.";
    toast("Profile not found");
    return;
  }
  chrome.storage.local.set({ profileData: resp.data });
  profileStatus.textContent = "Profile saved";
  profileSaved.textContent = "Yes";
  profileExpCount.textContent = resp.data?.experiences?.length ?? 0;
  toast("Profile captured");
});

/* 2) Scrape job */
scrapeJobBtn.addEventListener("click", async () => {
  jobStatus.textContent = "Scraping job page...";
  const [tab] = await activeTab();
  if (!tab?.id) return;

  const resp = await send(tab.id, { type: "SCRAPE_JOB" });
  if (!resp?.ok) {
    jobStatus.textContent = "Open a job page and try again.";
    toast("Job not found");
    return;
  }
  chrome.storage.local.set({ jobData: resp.data });
  jobStatus.textContent = "Job captured";
  peekTitle.textContent = resp.data.title || "—";
  peekCompany.textContent = resp.data.company || "—";
  toast("Job captured");

  // Simulated analysis visuals on Analyze tab
  // Your backend will compute real values. We mimic here for demo polish.
  const score = simulateScore(resp.data);
  animateGauge(score);
  renderChips(["GD&T", "ANSYS", "MATLAB"].slice(0, Math.max(0, 3 - Math.floor(score/40))));
  diffLeft.textContent = "Led composite layups and FEA validation for aero package.";
  diffRight.innerHTML = highlightDiff(
    "Led composite layups and FEA validation for aero package.",
    "Led composite layups, GD&T tolerancing, and ANSYS FEA validation for aero package per ASME Y14.5."
  );
});

/* Simulated score for wow factor */
function simulateScore(job) {
  const base = 52 + Math.min(30, (job.title || "").length % 30);
  return Math.min(98, Math.max(24, base));
}

/* Animate semicircle gauge (arc length 157 approx) */
function animateGauge(val) {
  const pct = Math.round(val);
  const arc = 157;
  const dash = arc - (arc * pct) / 100;
  gaugeVal.textContent = pct;
  gaugeArc.style.transition = "stroke-dashoffset .6s ease";
  gaugeArc.style.strokeDashoffset = dash.toString();
}

/* Chips */
function renderChips(arr) {
  missingSkills.innerHTML = "";
  arr.forEach(s => {
    const el = document.createElement("div");
    el.className = "chip";
    el.textContent = s;
    missingSkills.appendChild(el);
  });
}

/* Tiny inline diff highlighter */
function highlightDiff(orig, mod) {
  // Super simple for demo: mark additions
  const add = mod.replace(orig, "");
  return mod.replace(add, `<ins>${escapeHtml(add)}</ins>`);
}
function escapeHtml(s) { return s.replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m])); }

/* 3) Compose LaTeX */
composeResume.addEventListener("click", async () => {
  composeStatus.textContent = "Composing LaTeX...";
  const { profileData, jobData } = await chrome.storage.local.get(["profileData", "jobData"]);
  if (!profileData || !jobData) {
    composeStatus.textContent = "Profile or job missing";
    toast("Capture profile and job first");
    return;
  }
  const tpl = document.querySelector('input[name="tpl"]:checked')?.value || "classic";
  const tex = toLatex(profileData, jobData, tpl);
  latexPreview.value = tex;
  composeStatus.textContent = "Done";
  toast("LaTeX ready");
});

/* 4) Copy and downloads */
copyLatex.addEventListener("click", async () => {
  if (!latexPreview.value.trim()) return;
  await navigator.clipboard.writeText(latexPreview.value);
  toast("LaTeX copied");
});
downloadTex.addEventListener("click", () => {
  if (!latexPreview.value.trim()) { toast("Compose LaTeX first"); return; }
  downloadFile("resu.mk_resume.tex", latexPreview.value, "application/x-tex");
  exportStatus.textContent = "Saved .tex";
  toast(".tex downloaded");
});
downloadPdf.addEventListener("click", () => {
  // Frontend cannot compile to PDF alone. Call your backend if available.
  exportStatus.textContent = "PDF generation requires backend compile. Use .tex or wire server.";
  toast("Use backend to compile PDF");
});

/* File utils */
function downloadFile(name, content, mime) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a"); a.href = url; a.download = name; a.click();
  URL.revokeObjectURL(url);
}

/* Minimal LaTeX builder */
function toLatex(profile, job, tpl) {
  const esc = sanitizeLatex;
  const exp = (profile.experiences || []).slice(0, 5).map(e =>
`\\entry{${esc(e.date||"")}}{${esc(e.title||"")}}{${esc(e.company||"")}}{
  ${esc(e.description||"")}
}`).join("\n\n");

  const modernPreamble = `
\\documentclass[10pt,a4paper]{article}
\\usepackage[margin=1.4cm]{geometry}
\\usepackage{hyperref}
\\usepackage{enumitem}
\\usepackage{titlesec}
\\usepackage{fontspec}
\\setmainfont{Helvetica Neue}
\\titleformat*{\\section}{\\large\\bfseries}
\\newcommand{\\entry}[4]{\\noindent\\textbf{##2} \\hfill {\\small ##1}\\\\\\textit{##3}\\\\##4\\vspace{6pt}}
`;

  const classic = `
\\documentclass[10pt,a4paper]{article}
\\usepackage[margin=1.6cm]{geometry}
\\usepackage{hyperref}
\\usepackage{enumitem}
\\usepackage{titlesec}
\\titleformat*{\\section}{\\large\\bfseries}
\\newcommand{\\entry}[4]{\\noindent\\textbf{##2} \\hfill {\\small ##1}\\\\\\textit{##3}\\\\##4\\vspace{6pt}}
`;

  const compact = `
\\documentclass[9pt,a4paper]{article}
\\usepackage[margin=1.2cm]{geometry}
\\usepackage{hyperref}
\\usepackage{enumitem}
\\usepackage{titlesec}
\\titleformat*{\\section}{\\normalsize\\bfseries}
\\newcommand{\\entry}[4]{\\noindent\\textbf{##2} \\hfill {\\small ##1}\\\\\\textit{##3}\\\\##4\\vspace{4pt}}
`;

  const pre = tpl === "modern" ? modernPreamble : tpl === "compact" ? compact : classic;

  return `
${pre}
\\begin{document}
\\begin{center}
{\\Huge ${esc(profile.name || "Name")}}\\\\[2pt]
{\\small ${esc(profile.headline || "")}}\\\\
\\vspace{4pt}\\hrule\\vspace{8pt}
\\end{center}

\\section*{Target Role}
${esc(job.title || "")} at ${esc(job.company || "")}

\\section*{Profile}
${esc(profile.about || "")}

\\section*{Experience}
${exp || "N/A"}

\\section*{Keywords match}
${esc((job.desc||"").slice(0, 400))}...

\\end{document}
`.trim();
}

function sanitizeLatex(str) {
  const map = { '&':'\\&','%':'\\%','$':'\\$','#':'\\#','_':'\\_','{':'\\{','}':'\\}','~':'\\textasciitilde{}','^':'\\textasciicircum{}','\\':'\\textbackslash{}' };
  return String(str || "").replace(/[&%$#_{}~^\\]/g, m => map[m]);
}

/* Keyboard shortcuts */
document.addEventListener("keydown", e => {
  if (e.metaKey && e.key.toLowerCase() === "b") document.getElementById("composeResume").click();      // Cmd+B compose
  if (e.metaKey && e.key.toLowerCase() === "s") { e.preventDefault(); downloadTex.click(); }           // Cmd+S save .tex
});
