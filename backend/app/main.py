"""CivicPulse FastAPI backend: civic-image analysis and report management."""

import asyncio
import base64
import json
import os
import re
import sqlite3
import uuid
import warnings
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Literal

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field

# Load backend/.env regardless of the process working directory.
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DB_PATH = ROOT / "civicpulse.db"
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
MIME_TO_FORMAT = {
    "image/jpeg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
}
ISSUE_TYPES = {
    "Pothole",
    "Garbage",
    "Broken streetlight",
    "Damaged sidewalk",
    "Water leakage",
    "Other",
}
SEVERITIES = {"Low", "Medium", "High", "Unclear"}

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4:e2b")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemma-4-26b-a4b-it")

app = FastAPI(title="CivicPulse API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://civic-pulse-opal.vercel.app",
],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ReportAnalysis(BaseModel):
    issue_type: Literal[
        "Pothole",
        "Garbage",
        "Broken streetlight",
        "Damaged sidewalk",
        "Water leakage",
        "Other",
    ]
    severity: Literal["Low", "Medium", "High", "Unclear"]
    title: str = Field(min_length=1, max_length=140)
    description: str = Field(min_length=1, max_length=1000)
    evidence: list[str] = Field(max_length=8)
    department: str = Field(min_length=1, max_length=100)
    confidence: float = Field(ge=0, le=1, strict=True)
    limitations: list[str] = Field(max_length=8)


class ReportCreate(BaseModel):
    analysis: ReportAnalysis
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
        con.execute(
            """
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
            """
        )


@app.on_event("startup")
def startup():
    init_db()


PROMPT = """You are CivicPulse, an assistant that helps residents document visible civic infrastructure issues.
Analyze the attached image and the user's optional description. Only state what is visually supported.
Do not infer an exact address, cause, ownership, identity, or danger level from an image alone.
If uncertain, say so in limitations. Severity is a preliminary triage estimate, not an official safety assessment.
The user's location is context supplied by the user, not something to infer from the photograph.
Return ONLY one valid JSON object with these keys and types:
{
  "issue_type": "Pothole | Garbage | Broken streetlight | Damaged sidewalk | Water leakage | Other",
  "severity": "Low | Medium | High | Unclear",
  "title": "short factual title",
  "description": "2-3 sentence factual description",
  "evidence": ["specific visible observation"],
  "department": "suggested department, or General Civic Services",
  "confidence": 0.0,
  "limitations": ["what cannot be established from this image"]
}
Confidence is your estimate of image interpretation confidence, from 0 to 1; it is not a calibrated probability.
Do not claim the report was officially verified, filed, or resolved.
User description: {description}
User-provided location (context only): {location}
"""


def make_prompt(description: str, location: str) -> str:
    return (
        PROMPT.replace("{description}", description.strip()[:1000] or "Not provided")
        .replace("{location}", location.strip()[:300] or "Not provided")
    )


def extract_json(text: str) -> dict:
    """Parse a JSON object, tolerating a surrounding Markdown code fence."""
    if not isinstance(text, str) or not text.strip():
        raise HTTPException(status_code=502, detail="AI returned an empty response. Please retry.")

    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError:
        # Fallback for models that add a short preamble around the JSON.
        match = re.search(r"\{[\s\S]*\}", cleaned)
        if not match:
            raise HTTPException(status_code=502, detail="AI did not return valid JSON. Please retry.")
        try:
            result = json.loads(match.group(0))
        except json.JSONDecodeError:
            raise HTTPException(status_code=502, detail="AI returned malformed JSON. Please retry.")

    if not isinstance(result, dict):
        raise HTTPException(status_code=502, detail="AI response must be a JSON object.")
    return result


def _string(value: Any, field: str, max_length: int, *, required: bool = True) -> str:
    if not isinstance(value, str):
        if required:
            raise HTTPException(status_code=502, detail=f"AI response field '{field}' must be text.")
        return ""
    value = value.strip()[:max_length]
    if required and not value:
        raise HTTPException(status_code=502, detail=f"AI response field '{field}' is empty.")
    return value


def _string_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list):
        raise HTTPException(status_code=502, detail=f"AI response field '{field}' must be a list.")
    return [item.strip()[:200] for item in value[:8] if isinstance(item, str) and item.strip()]


def normalize(data: dict, provider: str) -> dict:
    """Validate and normalize model output to the frontend's stable contract."""
    required = {
        "issue_type", "severity", "title", "description", "evidence",
        "department", "confidence", "limitations",
    }
    missing = required.difference(data)
    if missing:
        raise HTTPException(
            status_code=502,
            detail="AI response is missing required fields: " + ", ".join(sorted(missing)),
        )

    issue_type = _string(data["issue_type"], "issue_type", 80)
    canonical_issue = next((x for x in ISSUE_TYPES if x.casefold() == issue_type.casefold()), None)
    limitations = _string_list(data["limitations"], "limitations")
    if canonical_issue is None:
        canonical_issue = "Other"
        limitations.append("The issue category was not one of the supported categories and was generalized to Other.")

    severity = _string(data["severity"], "severity", 20)
    if severity.casefold() not in {x.casefold() for x in SEVERITIES}:
        severity = "Unclear"
        limitations.append("The model returned an unsupported severity label; severity was set to Unclear.")
    else:
        severity = next(x for x in SEVERITIES if x.casefold() == severity.casefold())

    confidence_value = data["confidence"]
    if isinstance(confidence_value, bool) or not isinstance(confidence_value, (int, float)):
        raise HTTPException(status_code=502, detail="AI response confidence must be a number between 0 and 1.")
    confidence = float(confidence_value)
    if not 0.0 <= confidence <= 1.0:
        raise HTTPException(status_code=502, detail="AI response confidence is outside the 0–1 range.")

    return {
        "issue_type": canonical_issue,
        "severity": severity,
        "title": _string(data["title"], "title", 140),
        "description": _string(data["description"], "description", 1000),
        "evidence": _string_list(data["evidence"], "evidence"),
        "department": _string(data["department"], "department", 100),
        "confidence": confidence,
        "limitations": limitations[:8],
        "provider": provider,
    }


def validate_image(data: bytes, content_type: str) -> None:
    """Verify that the bytes are a real supported image and not a MIME spoof."""
    if content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=415, detail="Upload a JPG, PNG or WEBP image.")
    if not data:
        raise HTTPException(status_code=400, detail="The uploaded image is empty.")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as img:
                if img.format != MIME_TO_FORMAT[content_type]:
                    raise HTTPException(status_code=415, detail="The image contents do not match the uploaded file type.")
                width, height = img.size
                if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
                    raise HTTPException(status_code=413, detail="Image dimensions are too large. Please upload a smaller image.")
                img.verify()
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(status_code=400, detail="The uploaded file is not a valid or supported image.")


async def analyze_gemini(image: bytes, mime: str, description: str, location: str) -> dict:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise HTTPException(status_code=503, detail="Gemini is not configured. Add GEMINI_API_KEY to backend/.env.")

    # The synchronous SDK call runs in a worker thread so it does not block FastAPI's event loop.
    def _request():
        from google import genai
        from google.genai import types

        client = genai.Client(
            api_key=key,
            http_options=types.HttpOptions(timeout=180_000),
        )
        image_part = types.Part.from_bytes(data=image, mime_type=mime)
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[image_part, make_prompt(description, location)],
            config=types.GenerateContentConfig(temperature=0.2),
        )
        return response.text or ""

    try:
        response_text = await asyncio.to_thread(_request)
        return normalize(extract_json(response_text), "gemini")
    except HTTPException:
        raise
    except Exception as exc:
        message = str(exc).lower()
        if any(term in message for term in ("not found", "404", "unknown model", "unsupported model")):
            detail = f"Gemma model '{GEMINI_MODEL}' was not found or is unavailable to this API key. Verify model access and the exact model ID."
        elif any(term in message for term in ("api key", "unauthorized", "permission", "403", "401")):
            detail = "Gemini authentication failed. Check GEMINI_API_KEY and whether the key has access to the Gemini API."
        elif "quota" in message or "resource_exhausted" in message or "429" in message:
            detail = "Gemini API quota or rate limit reached. Please retry later."
        else:
            detail = f"Gemini image analysis failed ({type(exc).__name__}). Check the backend logs for details."
        # Provider exception text can contain sensitive request details.
        print(f"[Gemini error] {type(exc).__name__}")
        raise HTTPException(status_code=502, detail=detail)


async def analyze_local(image: bytes, mime: str, description: str, location: str) -> dict:
    payload = {
        "model": OLLAMA_MODEL,
        "stream": False,
        "format": "json",
        "messages": [{
            "role": "user",
            "content": make_prompt(description, location),
            "images": [base64.b64encode(image).decode("ascii")],
        }],
        "options": {"temperature": 0.2},
    }
    timeout = httpx.Timeout(180.0, connect=5.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(f"{OLLAMA_URL}/api/chat", json=payload)
        if response.status_code == 404:
            raise HTTPException(status_code=503, detail=f"Ollama model '{OLLAMA_MODEL}' is not installed. Run: ollama pull {OLLAMA_MODEL}")
        if response.status_code >= 400:
            print(f"[Ollama error] HTTP {response.status_code}: {response.text[:500]}")
            raise HTTPException(status_code=502, detail="Ollama rejected the analysis request. Check the local model and Ollama logs.")
        body = response.json()
        content = body.get("message", {}).get("content", "") if isinstance(body, dict) else ""
        return normalize(extract_json(content), "local")
    except HTTPException:
        raise
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Cannot reach Ollama. Start Ollama and confirm it is listening at OLLAMA_URL.")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Local Gemma analysis timed out. Try a smaller image or check available system memory.")
    except (ValueError, json.JSONDecodeError):
        raise HTTPException(status_code=502, detail="Ollama returned an unreadable response. Please retry.")
    except Exception as exc:
        print(f"[Ollama error] {type(exc).__name__}: {exc}")
        raise HTTPException(status_code=502, detail=f"Local Ollama analysis failed ({type(exc).__name__}). Check backend logs.")


@app.get("/api/health")
async def health():
    ollama_reachable = False
    local_model_available = False
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"{OLLAMA_URL}/api/tags")
        if response.status_code == 200:
            ollama_reachable = True
            models = response.json().get("models", [])
            local_model_available = any(
                isinstance(model, dict)
                and OLLAMA_MODEL in {model.get("name"), model.get("model")}
                for model in models
            )
    except (httpx.HTTPError, ValueError):
        pass

    return {
        "status": "ok",
        "gemini_key_configured": bool(os.getenv("GEMINI_API_KEY", "").strip()),
        "gemini_model": GEMINI_MODEL,
        "ollama_reachable": ollama_reachable,
        "local_model": OLLAMA_MODEL,
        "local_model_available": local_model_available,
    }


@app.post("/api/analyze")
async def analyze(
    image: UploadFile = File(...),
    description: str = Form(""),
    location: str = Form(""),
    provider: str = Form("gemini"),
):
    if provider not in {"gemini", "local"}:
        raise HTTPException(status_code=400, detail="provider must be 'gemini' or 'local'.")

    data = await image.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image must be 8 MB or smaller.")
    validate_image(data, image.content_type or "")

    if provider == "gemini":
        result = await analyze_gemini(data, image.content_type, description, location)
    else:
        result = await analyze_local(data, image.content_type, description, location)

    result["image_name"] = Path(image.filename or "uploaded-image").name[:255]
    return result


# Report-management endpoints are intentionally preserved for the product lead's integration.
@app.post("/api/reports")
async def create_report(payload: ReportCreate):
    a = payload.analysis.model_dump()
    report_id = str(uuid.uuid4())[:8].upper()
    created = datetime.now(timezone.utc).isoformat()
    with db() as con:
        con.execute("INSERT INTO reports VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            report_id, created, a.get("issue_type", "Other"), a.get("severity", "Unclear"),
            a.get("title", "Civic issue report"), a.get("description", ""),
            json.dumps(a.get("evidence", [])), a.get("department", "General Civic Services"),
            float(a.get("confidence", 0)), json.dumps(a.get("limitations", [])),
            payload.location, payload.image_name, "Submitted",
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
            raise HTTPException(status_code=404, detail="Report not found.")
    return {"id": report_id, "status": payload.status}
