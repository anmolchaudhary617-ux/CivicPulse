import base64
import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

load_dotenv()
ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "civicpulse.db"
MAX_IMAGE_BYTES = 8 * 1024 * 1024
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}

app = FastAPI(title="CivicPulse API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ReportCreate(BaseModel):
    analysis: dict
    location: str = ""
    description: str = ""
    image_name: str = ""

class StatusUpdate(BaseModel):
    status: str = Field(pattern="^(Submitted|Under Review|Resolved)$")

def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with db() as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS reports (
          id TEXT PRIMARY KEY,
          created_at TEXT NOT NULL,
          issue_type TEXT NOT NULL,
          severity TEXT NOT NULL,
          title TEXT NOT NULL,
          description TEXT NOT NULL,
          evidence TEXT NOT NULL,
          department TEXT NOT NULL,
          confidence REAL NOT NULL,
          limitations TEXT NOT NULL,
          location TEXT NOT NULL,
          image_name TEXT NOT NULL,
          status TEXT NOT NULL
        )
        """)

@app.on_event("startup")
def startup():
    init_db()

PROMPT = """You are CivicPulse, an assistant that helps residents document visible civic infrastructure issues.
Analyze the attached image and the user's optional description. Only state what is visually supported.
Do not infer an exact address, cause, ownership, or danger level from an image alone.
If uncertain, say so in limitations. Severity is a preliminary triage estimate, not an official assessment.
Return ONLY valid JSON with exactly these keys:
{
 "issue_type": "Pothole | Garbage | Broken streetlight | Damaged sidewalk | Water leakage | Other",
 "severity": "Low | Medium | High | Unclear",
 "title": "short factual title",
 "description": "2-3 sentence factual description",
 "evidence": ["visible observation"],
 "department": "suggested responsible department, or General Civic Services",
 "confidence": 0.0,
 "limitations": ["what cannot be established from this image"]
}
Confidence must be a number from 0 to 1. Do not claim the report was officially filed.
User description: {description}
User-provided location: {location}
"""

def extract_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            raise HTTPException(502, "AI returned no valid JSON. Please retry.")
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            raise HTTPException(502, "AI returned malformed JSON. Please retry.")

def normalize(data: dict, provider: str) -> dict:
    required = ["issue_type", "severity", "title", "description", "evidence", "department", "confidence", "limitations"]
    if not all(k in data for k in required):
        raise HTTPException(502, "AI response is missing required fields.")
    if data["severity"] not in {"Low", "Medium", "High", "Unclear"}:
        data["severity"] = "Unclear"
    try:
        confidence = max(0.0, min(1.0, float(data["confidence"])))
    except (TypeError, ValueError):
        confidence = 0.0
    return {
        "issue_type": str(data["issue_type"])[:80],
        "severity": data["severity"],
        "title": str(data["title"])[:140],
        "description": str(data["description"])[:1000],
        "evidence": [str(x)[:200] for x in data["evidence"][:8]] if isinstance(data["evidence"], list) else [],
        "department": str(data["department"])[:100],
        "confidence": confidence,
        "limitations": [str(x)[:200] for x in data["limitations"][:8]] if isinstance(data["limitations"], list) else [],
        "provider": provider,
    }

async def analyze_gemini(image: bytes, mime: str, description: str, location: str) -> dict:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise HTTPException(400, "GEMINI_API_KEY is not configured in backend/.env")
    try:
        from google import genai
        from google.genai import types
        import tempfile
        client = genai.Client(api_key=key)
        suffix = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}[mime]
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp:
                temp.write(image)
                temp_path = temp.name
            uploaded = client.files.upload(file=temp_path)
            response = client.models.generate_content(
                model=os.getenv("GEMINI_MODEL", "gemma-4-26b-a4b-it"),
                contents=[uploaded, PROMPT.replace("{description}", description or "Not provided").replace("{location}", location or "Not provided")],
                config=types.GenerateContentConfig(temperature=0.2),
            )
            if not response.text:
                raise ValueError("Empty model response")
            return normalize(extract_json(response.text), "gemini")
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, f"Gemini analysis failed: {str(exc)[:240]}")

async def analyze_local(image: bytes, description: str, location: str) -> dict:
    payload = {
        "model": os.getenv("OLLAMA_MODEL", "gemma4:e2b"),
        "stream": False,
        "format": "json",
        "messages": [{
            "role": "user",
            "content": PROMPT.replace("{description}", description or "Not provided").replace("{location}", location or "Not provided"),
            "images": [base64.b64encode(image).decode("ascii")]
        }]
    }
    try:
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(os.getenv("OLLAMA_URL", "http://localhost:11434") + "/api/chat", json=payload)
            response.raise_for_status()
        content = response.json().get("message", {}).get("content", "")
        return normalize(extract_json(content), "local")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, f"Local Ollama analysis failed: {str(exc)[:240]}")

@app.get("/api/health")
async def health():
    local_ok = False
    try:
        async with httpx.AsyncClient(timeout=2) as client:
            r = await client.get(os.getenv("OLLAMA_URL", "http://localhost:11434") + "/api/tags")
            local_ok = r.status_code == 200
    except Exception:
        pass
    return {
        "status": "ok",
        "gemini_key_configured": bool(os.getenv("GEMINI_API_KEY", "").strip()),
        "ollama_reachable": local_ok,
        "local_model": os.getenv("OLLAMA_MODEL", "gemma4:e2b"),
    }

@app.post("/api/analyze")
async def analyze(
    image: UploadFile = File(...),
    description: str = Form(""),
    location: str = Form(""),
    provider: str = Form("gemini"),
):
    if image.content_type not in ALLOWED_TYPES:
        raise HTTPException(415, "Upload a JPG, PNG or WEBP image.")
    data = await image.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "Image must be 8 MB or smaller.")
    if not data:
        raise HTTPException(400, "The uploaded image is empty.")
    if provider == "gemini":
        result = await analyze_gemini(data, image.content_type, description, location)
    elif provider == "local":
        result = await analyze_local(data, description, location)
    else:
        raise HTTPException(400, "provider must be 'gemini' or 'local'.")
    result["image_name"] = image.filename or "uploaded-image"
    return result

@app.post("/api/reports")
async def create_report(payload: ReportCreate):
    a = payload.analysis
    report_id = str(uuid.uuid4())[:8].upper()
    created = datetime.now(timezone.utc).isoformat()
    with db() as con:
        con.execute("""INSERT INTO reports VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
            report_id, created, a.get("issue_type","Other"), a.get("severity","Unclear"),
            a.get("title","Civic issue report"), a.get("description",""),
            json.dumps(a.get("evidence",[])), a.get("department","General Civic Services"),
            float(a.get("confidence",0)), json.dumps(a.get("limitations",[])),
            payload.location, payload.image_name, "Submitted"
        ))
    return {"id": report_id, "status": "Submitted", "created_at": created}

@app.get("/api/reports")
async def list_reports():
    with db() as con:
        rows = con.execute("SELECT * FROM reports ORDER BY created_at DESC").fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["evidence"] = json.loads(item["evidence"])
        item["limitations"] = json.loads(item["limitations"])
        result.append(item)
    return result

@app.patch("/api/reports/{report_id}")
async def update_report(report_id: str, payload: StatusUpdate):
    with db() as con:
        cur = con.execute("UPDATE reports SET status=? WHERE id=?", (payload.status, report_id))
        if cur.rowcount == 0:
            raise HTTPException(404, "Report not found.")
    return {"id": report_id, "status": payload.status}
