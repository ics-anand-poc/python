# TalentScope Python API

FastAPI backend and its SQL Server schema, migration, and seed-data tooling. This folder is a standalone repository root for deployment to Render.

## Deploy on Render

Create a Render Blueprint from this repository and use `render.yaml`, or create a Docker web service with this folder as the build context and `Dockerfile` as the Dockerfile. The API listens on port `8000`; Render checks `/api/health`.

The API requires an existing, network-accessible Microsoft SQL Server or Azure SQL database. Render does not provision SQL Server for this service. Set the `MSSQL_AZURE_*` variables in the Render service (the blueprint prompts for server, database, user, and password). Configure `FRONTEND_ORIGIN` with the Vercel production origin, and set the auth passwords and secrets before opening the app to users. Set `FACE_MATCH_SERVICE_URL` and `FACE_MATCH_API_KEY` to the separately deployed Face Match service values. `LOCAL_LLM_URL` is optional; the API uses its fallback behavior when it is unavailable.

The blueprint attaches a persistent disk at `/app/uploads` for uploaded documents and recordings. Keep that disk attached when redeploying.

## Database migrations and seeds

The `db/` directory contains SQL migrations, seed data, and the Node-based database CLI. Run migrations deliberately from an administrator/developer machine that can reach the target database; deployment does not automatically seed production data.

```powershell
Copy-Item .env.example .env
# Edit .env with the database target and credentials.
cd db
npm ci
npm run db:status
npm run db:migrate
```

Seed JSON files are excluded from Git and Docker because they contain personal data. Supply approved, sanitized seed files privately before running `npm run db:deploy-data` or `npm run db:azure`. Schema-only Azure migrations use `npm run db:migrate -- --target=azure`.

## Local development

Install `requirements.txt`, install Microsoft's ODBC Driver 18 for SQL Server, and run:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --port 8000 --reload
```

For UI/API endpoint integration checks, keep the UI checkout beside this repository or set `TALENTSCOPE_UI_DIR` to its path, then run `python scripts/check_api_links.py`.
