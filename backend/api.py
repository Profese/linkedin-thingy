from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional
import os, subprocess, io, shutil
from dotenv import load_dotenv
from supabase import create_client, Client
from brightdata import bdclient
from fastapi.responses import JSONResponse
from tempfile import TemporaryDirectory
from fastapi.responses import StreamingResponse
import ollama


load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
BRIGHTDATA_API = "513f4286533507f9d51c62bf6a9325ffa00e0e457d8ec875252a05163e152075"
JOB_POSTING_API = ""
client = bdclient(api_token=BRIGHTDATA_API)
if not SUPABASE_URL or not SUPABASE_KEY or not BRIGHTDATA_API:
    raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

app = FastAPI(title="Resu.mk API")

# CORS (allow extension + local dev)
allowed_origins = []
for raw in (os.getenv("ALLOWED_ORIGINS") or "").split(","):
    raw = raw.strip()
    if raw:
        # allow chrome-extension://* and your local UI
        if raw.startswith("chrome-extension://"):
            allowed_origins.append(raw)
        else:
            allowed_origins.append(raw)

# Fallback for dev
if not allowed_origins:
    allowed_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Schemas ----------
class UrlPayload(BaseModel):
    url: str

class Experience(BaseModel):
    title: str
    company: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    keywords: List[str] = Field(default_factory=list)  # Generated via Ollama


class Education(BaseModel):
    school: Optional[str] = None
    degree: Optional[str] = None
    field: Optional[str] = None
    start_year: Optional[str] = None
    end_year: Optional[str] = None


class ProfilePayload(BaseModel):
    name: str
    headline: Optional[str] = None
    linkedin_url: Optional[str] = None
    location: Optional[str] = None
    experiences: List[Experience] = Field(default_factory=list)
    education: List[Education] = Field(default_factory=list)
    skills: List[str] = Field(default_factory=list)


class JobPayload(BaseModel):
    title: str
    company: Optional[str] = None
    desc: Optional[str] = None
    keywords: List[str] = Field(default_factory=list)

class ComposeRequest(BaseModel):
    profile: ProfilePayload
    job: JobPayload
    # optional: let the client request 'latex_only' for debugging
    latex_only: Optional[bool] = False


# ---------- Endpoints ----------



def extract_keywords_from_resume(text: str, model: str = "llama3") -> list[str]:
    """
    Uses a local Ollama model to extract key skills or technologies
    mentioned in a job description. Returns a list of short keywords.
    """
    if not text:
        return []
    prompt = (
        "Extract 5 to 10 relevant, concise professional keywords "
        "from this resume. EACH KEYWORD SHOULD ONLY BE SEPARATED BY A COMMA, NO SPACE AFTER.\n\n"
        f"{text}"
    )

    try:
        response = ollama.chat(model=model, messages=[{"role": "user", "content": prompt}])
        raw = response["message"]["content"]
        # clean and split into list
        return [kw.strip() for kw in raw.replace("\n", ",").split(",") if kw.strip()]
    except Exception as e:
        print(f"Ollama keyword extraction failed: {e}")
        return []

def extract_keywords_from_job_desc(text: str, model: str = "llama3") -> list[str]:
    """
    Uses a local Ollama model to extract key skills or technologies
    mentioned in a job description. Returns a list of short keywords.
    """
    if not text:
        return []
    prompt = (
        "Extract 5 to 10 relevant, concise professional keywords "
        "from this resume. EACH KEYWORD SHOULD ONLY BE SEPARATED BY A COMMA, NO SPACE AFTER.\n\n"
        f"{text}"
    )

    try:
        response = ollama.chat(model=model, messages=[{"role": "user", "content": prompt}])
        raw = response["message"]["content"]
        # clean and split into list
        return [kw.strip() for kw in raw.replace("\n", ",").split(",") if kw.strip()]
    except Exception as e:
        print(f"Ollama keyword extraction failed: {e}")
        return []

def _esc(s: str) -> str:
    mp = {'&':'\\&','%':'\\%','$':'\\$','#':'\\#','_':'\\_','{':'\\{','}':'\\}',
          '~':'\\textasciitilde{}','^':'\\textasciicircum{}','\\':'\\textbackslash{}'}
    return "".join(mp.get(c, c) for c in (s or ""))

def _build_latex(profile: ProfilePayload, job: JobPayload) -> str:
    exp = "\n\n".join(
        f"\\entry{{{_esc(e.date or '')}}}{{{_esc(e.title or '')}}}{{{_esc(e.company or '')}}}{{\n  {_esc(e.description or '')}\n}}"
        for e in (profile.experiences or [])[:5]
    ) or "N/A"

    latex = f"""
\\documentclass[10pt,a4paper]{{article}}
\\usepackage[margin=1.6cm]{{geometry}}
\\usepackage{{hyperref}}
\\usepackage{{enumitem}}
\\usepackage{{titlesec}}
\\titleformat*{{\\section}}{{\\large\\bfseries}}
\\setlength{{\\parskip}}{{4pt}}
\\newcommand{{\\entry}}[4]{{\\noindent\\textbf{{##2}} \\hfill {{\\small ##1}}\\\\\\textit{{##3}}\\\\##4\\vspace{{6pt}}}}

\\begin{{document}}
\\begin{{center}}
{{\\Huge {_esc(profile.name or 'Name')}}}\\\\[2pt]
{{\\small {_esc(profile.headline or '')}}}\\\\
\\vspace{{4pt}}\\hrule\\vspace{{8pt}}
\\end{{center}}

\\section*{{Target Role}}
{_esc(job.title or '')} at {_esc(job.company or '')}

\\section*{{Profile}}
{_esc(profile.about or '')}

\\section*{{Experience}}
{exp}

\\section*{{Keywords match}}
{_esc((job.desc or '')[:400])}...

\\end{{document}}
""".strip()
    return latex

def _compile_with_tectonic(latex_source: str, timeout_seconds: int = 20) -> bytes:
    # Ensure tectonic is available
    if not (sh := shutil.which("tectonic")):
        raise HTTPException(status_code=500, detail="Tectonic not found on server PATH. Please install it.")

    with TemporaryDirectory() as tmp:
        tex_path = os.path.join(tmp, "main.tex")
        pdf_path = os.path.join(tmp, "main.pdf")
        
        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(latex_source)

        # Run tectonic (no shell-escape)
        try:
            result = subprocess.run(
                [sh, "--keep-intermediates", "--outdir", tmp, tex_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=timeout_seconds,
                text=True,
            )
        except subprocess.TimeoutExpired:
            raise HTTPException(status_code=504, detail="LaTeX compilation timed out.")

        if result.returncode != 0 or not os.path.exists(pdf_path):
            log = (result.stdout or "") + "\n" + (result.stderr or "")
            raise HTTPException(status_code=400, detail=f"LaTeX compilation failed.\n{log}")

        with open(pdf_path, "rb") as f:
            return f.read()


@app.get("/health")
def health():
    return {"ok": True}

@app.post("/api/profile")
def upsert_profile(link: UrlPayload):
    """
    Scrapes LinkedIn profile using BrightData API,
    extracts only resume-relevant fields, and stores them in Supabase.
    """
    # 1) Scrape LinkedIn
    #data = client.scrape_linkedin.profiles(link.url)  
    
    #jiya's while loop
    MAX_RETRIES = 10
    attempt = 0
    data = None

    while attempt < MAX_RETRIES:
        try:
            data = client.scrape_linkedin.profiles(link.url)
            if data and isinstance(data, (dict, list)):
                if isinstance(data, dict) and "snapshot_id" in data:
                    print("⚠️ snapshot_id found on attempt", attempt + 1, "retrying...")
                else:
                    print("✅ Got valid JSON on attempt", attempt + 1)
                    break
                print("✅ Successfully got JSON data on attempt", attempt + 1)
                break
            else:
                print("⚠️ Empty or invalid data on attempt", attempt + 1, "retrying...")
            
        except Exception as e:
            print("❌ Error on attempt", attempt + 1, ":", e)
        attempt += 1

    if not data or ("snapshot_id" in data if isinstance(data, dict) else False):
        raise RuntimeError("Failed to retrieve valid JSON without 'snapshot_id' after multiple attempts.")
 
    print(data)

    #if not data:
        #raise HTTPException(status_code=400, detail="Empty response from BrightData scraper")


    # 2) Build ProfilePayload (only essential fields)
    profile = ProfilePayload(
        name=data.get("name", ""),
        headline=data.get("position", ""),
        linkedin_url=data.get("url") or data.get("input_url"),
        location=data.get("city") or data.get("location"),
        experiences=[
            Experience(
                title=exp.get("title", ""),
                company=exp.get("company"),
                location=exp.get("location"),
                keywords=extract_keywords_from_resume(exp.get("description")),
                description=exp.get("description"),
                start_date=exp.get("start_date"),
                end_date=exp.get("end_date"),
            )
            for exp in data.get("experience", [])
        ],
        education=[
            Education(
                school=edu.get("title"),
                degree=edu.get("degree"),
                field=edu.get("field"),
                start_year=edu.get("start_year"),
                end_year=edu.get("end_year"),
            )
            for edu in data.get("education", [])
        ],
        skills=data.get("skills", []),
    )

    # 3) Upsert base profile row
    # Some Supabase/PostgREST setups require a unique constraint for ON CONFLICT
    # upserts. If the DB doesn't have that constraint, using on_conflict will
    # raise a 42P10 error. To be compatible with more schemas, do a
    # simple find-then-update/insert based on linkedin_url. If linkedin_url is
    # not provided, always insert a new profile.

    prof_row = None
    if profile.linkedin_url:
        # try to find an existing profile with this linkedin_url
        find_resp = supabase.table("profiles").select("id").eq("linkedin_url", profile.linkedin_url).execute()
        if getattr(find_resp, "error", None):
            raise HTTPException(status_code=500, detail=f"profiles lookup failed: {find_resp.error.message}")
        if find_resp.data:
            # update existing row
            existing_id = find_resp.data[0]["id"]
            update_resp = supabase.table("profiles").update(
                {
                    "full_name": profile.name,
                    "headline": profile.headline,
                    "location": profile.location,
                }
            ).eq("id", existing_id).execute()
            if getattr(update_resp, "error", None):
                raise HTTPException(status_code=500, detail=f"profiles update failed: {update_resp.error.message}")
            prof_row = (update_resp.data or [None])[0] or {"id": existing_id}
        else:
            # insert new
            insert_resp = supabase.table("profiles").insert(
                {
                    "linkedin_url": profile.linkedin_url,
                    "full_name": profile.name,
                    "headline": profile.headline,
                    "location": profile.location,
                }
            ).execute()
            if getattr(insert_resp, "error", None):
                raise HTTPException(status_code=500, detail=f"profiles insert failed: {insert_resp.error.message}")
            prof_row = (insert_resp.data or [None])[0]
    else:
        # no linkedin_url provided, always insert
        insert_resp = supabase.table("profiles").insert(
            {
                "full_name": profile.name,
                "headline": profile.headline,
                "location": profile.location,
            }
        ).execute()
        if getattr(insert_resp, "error", None):
            raise HTTPException(status_code=500, detail=f"profiles insert failed: {insert_resp.error.message}")
        prof_row = (insert_resp.data or [None])[0]

    if not prof_row:
        raise HTTPException(status_code=500, detail="No profile row returned from Supabase")

    profile_id = prof_row["id"]

    # 4) Replace experiences
    supabase.table("experiences").delete().eq("profile_id", profile_id).execute()
    if profile.experiences:
        exp_rows = [
            {
                "profile_id": profile_id,
                "title": e.title,
                "company": e.company,
                "location": e.location,
                "description": e.description,
                "start_date": e.start_date,
                "end_date": e.end_date,
            }
            for e in profile.experiences
        ]
        exp_resp = supabase.table("experiences").insert(exp_rows).execute()
        if getattr(exp_resp, "error", None):
            raise HTTPException(status_code=500, detail=f"experiences insert failed: {exp_resp.error.message}")

    # 5) Replace education
    supabase.table("education").delete().eq("profile_id", profile_id).execute()
    if profile.education:
        edu_rows = [
            {
                "profile_id": profile_id,
                "school": e.school,
                "degree": e.degree,
                "field": e.field,
                "start_year": e.start_year,
                "end_year": e.end_year,
            }
            for e in profile.education
        ]
        edu_resp = supabase.table("education").insert(edu_rows).execute()
        if getattr(edu_resp, "error", None):
            raise HTTPException(status_code=500, detail=f"education insert failed: {edu_resp.error.message}")

    # 6) Replace skills
    supabase.table("skills").delete().eq("profile_id", profile_id).execute()
    if profile.skills:
        skill_rows = [{"profile_id": profile_id, "name": s} for s in profile.skills]
        skill_resp = supabase.table("skills").insert(skill_rows).execute()
        if getattr(skill_resp, "error", None):
            raise HTTPException(status_code=500, detail=f"skills insert failed: {skill_resp.error.message}")

    # 7) Count for frontend feedback
    exp_count_resp = supabase.table("experiences").select("id", count="exact").eq("profile_id", profile_id).execute()
    exp_count = getattr(exp_count_resp, "count", 0) or 0

    return {
        "success": True,
        "profile_id": profile_id,
        "experienceCount": exp_count,
        "name": profile.name,
        "headline": profile.headline,
        "skills": profile.skills,
    }

@app.post("/api/job")
def save_job(job: JobPayload):
    """
    Stores the scraped job posting for later analysis / compose.
    """
    resp = supabase.table("jobs").insert({
        "title": job.title, "company": job.company, "desc": job.desc
    }).execute()
    if resp.error:
        raise HTTPException(status_code=500, detail=resp.error.message)
    return {"success": True, "job_id": resp.data[0]["id"]}

def upload_pdf_to_supabase(file_path: str, file_name: str) -> str:
    """Upload a PDF file to Supabase Storage and return its public URL."""
    bucket = "resumes"

    # Ensure filename is unique & safe
    base_name = os.path.basename(file_name).replace(" ", "_")
    remote_path = f"{bucket}/{base_name}"

    # Upload file
    with open(file_path, "rb") as f:
        res = supabase.storage.from_(bucket).upload(base_name, f)
        if hasattr(res, "error") and res.error:
            raise HTTPException(status_code=500, detail=f"Upload failed: {res.error.message}")

    # Get public URL
    public_url = supabase.storage.from_(bucket).get_public_url(base_name)
    return public_url

@app.post("/api/compose/pdf")
def compose_pdf(req: ComposeRequest):
    latex = _build_latex(req.profile, req.job)
    if req.latex_only:
        # For debugging: return the LaTeX as text/plain
        return {"latex": latex}
    pdf_bytes = _compile_with_tectonic(latex)
    file_like = io.BytesIO(pdf_bytes)
    headers = {
        "Content-Disposition": 'attachment; filename="resume.pdf"'
    }
    return StreamingResponse(file_like, media_type="application/pdf", headers=headers)