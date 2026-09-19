# Trader

Swing trading helper app — a read-only portfolio dashboard synced from Trading212.

## Running locally

**Backend** (from `backend/`):

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
copy .env.example .env   # then fill in your Trading212 API key/secret and a random DASHBOARD_API_KEY
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

**Frontend** (from `frontend/`, in a second terminal):

```powershell
npm install
copy .env.local.example .env.local   # BACKEND_URL + the same DASHBOARD_API_KEY as the backend
npm run dev
```

Then open http://localhost:3000.
