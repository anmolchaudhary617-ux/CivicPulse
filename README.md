# CivicPulse

**See it. Report it. Improve your city.**

CivicPulse turns community photographs of visible civic infrastructure issues into structured, human-reviewed reports using Gemma 4.

## AI providers
- Hosted: Gemma 4 through the Google Gemini API (`gemma-4-26b-a4b-it`).
- Local: Gemma 4 E2B through Ollama (`gemma4:e2b`).

The application is designed to support both hosted and local inference. The hosted API key stays on the backend.

## Run locally
See [backend setup](backend/README.md), then:
```powershell
cd frontend
npm install
npm run dev
```
Open http://localhost:5173.

## Important
AI-generated issue categories and severity are preliminary suggestions, not official inspections or verified municipal complaints. Users review findings before saving. Sample dashboard cards are illustrative demo data and are replaced by saved reports when available.

## License
MIT. See LICENSE. Gemma model weights and Google API access are governed by their respective terms; this repository does not redistribute model weights.
