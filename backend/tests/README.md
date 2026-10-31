# Backend tests

From the `backend` directory, install the development dependencies and run the test suite:

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest
```

The suite uses FastAPI `TestClient`, mocks external AI/network calls, and creates a separate SQLite database for each test. It does not require credentials, internet access, or a running Ollama service.
