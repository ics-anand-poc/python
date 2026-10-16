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

### Supabase PostgreSQL health check

The API's application data store remains SQL Server. `/api/health` can additionally verify a Supabase PostgreSQL connection using the direct database credentials in the ignored repository-root `.env` file:

```dotenv
SUPABASE_DB_HOST=<Supabase database host>
SUPABASE_DB_PORT=5432
SUPABASE_DB_NAME=postgres
SUPABASE_DB_USER=postgres
SUPABASE_DB_PASSWORD=<Supabase database password>
```

The Supabase URL, anon key, and service-role key are not needed for this direct PostgreSQL probe. After setting these values and restarting the API, check for `"supabase": { "configured": true, "up": true }` in `/api/health`. When the database settings are missing, the response reports `"configured": false` and `"up": null`; a failed connection reports `"up": false` with an actionable `error` code and writes a sanitized diagnostic to the API log. Install dependencies from `requirements.txt` to provide the `psycopg` driver.

To check the Supabase Auth health endpoint and direct PostgreSQL connection independently of the API, set `NEXT_PUBLIC_SUPABASE_URL`, either `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` or `NEXT_PUBLIC_SUPABASE_ANON_KEY`, and the `SUPABASE_DB_*` variables in `.env`, then run:

```powershell
.\venv\Scripts\python.exe scripts\check_supabase_connection.py
```

The script validates the REST response and executes `SELECT 1` against the direct database connection. It never prints the API key or database password.

For an IPv4-compatible Supavisor session-pooler check, copy the exact host, port, and username from Supabase **Dashboard → Connect → Session pooler** into `.env` as `SUPABASE_POOLER_HOST`, `SUPABASE_POOLER_PORT`, and `SUPABASE_POOLER_USER`. Keep `SUPABASE_DB_NAME` and `SUPABASE_DB_PASSWORD` set to the database name and password, then run:

```powershell
.\venv\Scripts\python.exe scripts\check_supabase_pooler.py
```

The pooler username differs from the direct database username; use the full username shown by Supabase rather than assuming it is `postgres`. The script connects with SSL and runs `SELECT 1`.

#### Troubleshooting direct Supabase connections

- If the endpoint reports `psycopg_not_installed`, activate the same virtual environment used to run Uvicorn and install `requirements.txt`. On a managed Windows network where pip reports a certificate verification error, use the organization's approved CA configuration or package index; do not disable TLS verification. If pip then receives HTTP 403 for `files.pythonhosted.org`, ask the network administrator to allow that package host or configure the approved mirror. Restart Uvicorn after installation.
- Use the direct host `db.<project-ref>.supabase.co` and port `5432` from Supabase's Direct connection details. If health reports `dns_resolution_failed`, check that the project reference and host are exact, then check DNS resolution and outbound IPv6 routing on the machine running the API; Supabase's direct endpoint may resolve only to IPv6. If that network has no IPv6 route, ask the network administrator to enable IPv6 or ask Supabase support about direct IPv4 connectivity for the project. The Session Pooler is a different connection mode and is not used by this app's direct-connection probe.
- Confirm the route independently with the Supabase-provided `psql` connection details and `SELECT 1`. Once `/api/health` reports `configured: true` and `up: true`, the probe is verified.

For UI/API endpoint integration checks, keep the UI checkout beside this repository or set `TALENTSCOPE_UI_DIR` to its path, then run `python scripts/check_api_links.py`.
