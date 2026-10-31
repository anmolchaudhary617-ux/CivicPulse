# CivicPulse API

## Setup (PowerShell)
```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
# Add GEMINI_API_KEY to .env for hosted Gemma 4
uvicorn app.main:app --reload --port 8000
```

Local inference requires Ollama running and `gemma4:e2b` installed.
Hosted inference uses `gemma-4-26b-a4b-it` through the Google Gen AI SDK.
Never commit `.env`.
