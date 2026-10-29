# SmartBus — Dynamic Public Bus Fleet Reallocation System

SmartBus is a real-time public bus fleet management system designed to detect overcrowded and underutilized routes using real-time/simulated passenger and GPS data, then recommend optimal bus reallocations without machine learning.

## Stage 1: Project Foundation

This repository currently implements **Stage 1 ONLY: Project Foundation**, establishing the monorepo architecture, FastAPI backend with health endpoints, SQLAlchemy/Alembic database foundation, and a minimal React + TypeScript + Vite + Tailwind CSS frontend.

### Architecture Overview

```
Simulated / Real-time Transit Data (Future)
              │
              ▼
       FastAPI Backend
              │
              ├── Load Analysis Engine (Future)
              └── Optimization Engine (Google OR-Tools - Future)
              │
              ▼
   React Dispatcher Dashboard
```

---

## Repository Structure

```
smartbus/
│
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI entry point & CORS
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   └── config.py        # Settings via Pydantic
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   └── routes/
│   │   │       ├── __init__.py
│   │   │       └── health.py    # GET /api/health
│   │   ├── models/              # Reserved for Stage 2 DB models
│   │   ├── schemas/             # Pydantic schemas
│   │   ├── services/            # Business & transit domain services
│   │   └── db/
│   │       ├── __init__.py
│   │       ├── session.py       # SQLAlchemy engine & session factory
│   │       └── base.py          # Declarative Base
│   ├── alembic/                 # Alembic migration environment
│   ├── requirements.txt         # Backend Python dependencies
│   ├── .env.example             # Backend environment template
│   └── README.md                # Backend documentation
│
├── frontend/
│   ├── src/
│   │   ├── components/          # Reusable UI components
│   │   ├── pages/               # Views / pages
│   │   ├── services/            # API client services
│   │   ├── types/               # TypeScript interface definitions
│   │   ├── hooks/               # Custom React hooks
│   │   ├── App.tsx              # Root component & health indicator
│   │   ├── main.tsx             # Application bootstrap
│   │   └── index.css            # Tailwind CSS styling
│   ├── public/                  # Static assets
│   ├── package.json             # Frontend dependencies & scripts
│   ├── vite.config.ts           # Vite configuration
│   └── .env.example             # Frontend environment template
│
├── .gitignore
└── README.md
```

---

## Quick Start

### 1. Prerequisites
- Python 3.11+ (Python 3.13 supported)
- Node.js 18+ (Node 24 supported)
- PostgreSQL (optional for Stage 1; backend starts without a running DB)

### 2. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# Linux / macOS:
# source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create environment configuration
copy .env.example .env

# Run FastAPI development server
uvicorn app.main:app --reload --port 8000
```

FastAPI will start at `http://localhost:8000`.  
Check the health endpoint at: `http://localhost:8000/api/health`

### 3. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Create environment configuration
copy .env.example .env

# Start Vite development server
npm run dev
```

The frontend will run at `http://localhost:5173`.  
It will automatically connect to `http://localhost:8000/api/health` and display **"Backend Status: Connected"**.
