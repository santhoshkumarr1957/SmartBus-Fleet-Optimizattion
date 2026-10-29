# SmartBus — Backend Service

FastAPI-powered transit backend for real-time fleet reallocation, load analysis, and dispatching.

## Features (Stage 1 Foundation)
- FastAPI asynchronous application structure
- CORS middleware configured for frontend development
- Environment-based configuration via `pydantic-settings`
- Health check endpoint (`GET /api/health`)
- SQLAlchemy Declarative Base and session management (resilient if DB is not configured)
- Alembic database migration environment

## Getting Started

### 1. Setup Virtual Environment
```bash
python -m venv .venv

# On Windows PowerShell:
.venv\Scripts\Activate.ps1
# On Linux / macOS:
# source .venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Environment Configuration
Copy the template to `.env`:
```bash
copy .env.example .env
```

### 4. Run the Development Server
```bash
uvicorn app.main:app --reload --port 8000
```

### 5. Verify Health Endpoint
Visit `http://localhost:8000/api/health` or use curl:
```bash
curl http://localhost:8000/api/health
# Response: {"status": "ok"}
```
