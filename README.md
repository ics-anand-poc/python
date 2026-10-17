# TalentScope Python API

FastAPI backend with profile-selected database storage.

## Database profiles

The shared database connection settings are in [`conf/application.properties`](conf/application.properties). Select the database with `APP_PROFILE=local`, `APP_PROFILE=vercel`, or `APP_PROFILE=production` in the process environment or ignored root `.env` file. The profile is not selected from `application.properties`. Database connection values can use `${VARIABLE}` placeholders populated from `.env`; process environment variables take precedence. Do not commit `.env` or put secrets in the shared properties file.

| Profile | Selected database | Selection |
|---|---|---|
| `local` | SQL Server `TalentScope_DB_Dev` | Set `APP_PROFILE=local` (recommended in local `.env`) |
| `vercel` | Supabase PostgreSQL | Set `APP_PROFILE=vercel`; Vercel's `VERCEL` variable also selects it |
| `production` | SQL Server `TalentScope_DB_Live` | Set `APP_PROFILE=production`; non-Vercel `NODE_ENV=production` also selects it |

The application uses the same `Store` API for SQL Server and PostgreSQL, so API reads and writes follow the selected profile. Locally, set database credentials in `.env` or process environment variables. For Vercel, set `SUPABASE_DB_PASSWORD` in the Vercel project environment settings. For a non-Vercel production deployment, set `MSSQL_PRODUCTION_PASSWORD` in that host's secret settings.

> The configured SQL Server address `10.0.1.7` is private-network space. A hosted service such as Vercel or Render cannot reach it unless you provide private network connectivity or replace it with a reachable SQL Server endpoint.

## Deploy the API to Vercel

The repository includes `vercel.json` and `api/index.py`. Configure the Vercel project root to this repository directory, set `APP_PROFILE=vercel`, add `SUPABASE_DB_PASSWORD` as a Vercel secret, and deploy. Do not add database credentials to `vercel.json` or `conf/application.properties`.

Vercel's serverless instances do not provide durable local files or reliable long-lived worker threads. The Vercel profile stores uploaded objects in PostgreSQL and disables background threads; queued question generation uses the existing synchronous fallback. Features requiring continuous queue processing or scheduled retention still need a separate worker deployment. The Supabase direct host can also require IPv6, which may not be available on every Vercel plan/runtime.

## PostgreSQL schema

Apply the PostgreSQL migrations before serving application requests with the `vercel` profile. The migration runner applies the numbered scripts in order, tracks checksums, and rejects edits to already-applied migrations:

```powershell
$env:APP_PROFILE = "vercel"
.\venv\Scripts\python.exe scripts\migrate_postgres.py
```

It connects over TLS to the direct Supabase database host in `conf/application.properties`. The Supabase direct endpoint may require IPv6; if the running host cannot resolve or route to it, `/api/health` and the migration command will report that connection failure. For an IPv4-only Vercel runtime, use a Supabase IPv4-capable endpoint or the supported Supavisor connection details and update the profile settings accordingly.

The PostgreSQL migrations create the application tables and convert JSON-backed application columns to `JSONB`. Existing SQL Server rows are not copied automatically; use an approved, reviewed data-transfer process before switching a live deployment to PostgreSQL.

## Local development

Install the requirements and Microsoft's ODBC Driver 18 for SQL Server, then start the API:

```powershell
$env:APP_PROFILE = "local"
$env:MSSQL_LOCAL_PASSWORD = "<development SQL password>"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --port 8000 --reload
```

To test the selected database and the optional Supabase health probe, request:

```powershell
Invoke-RestMethod http://localhost:8000/api/health
```

`database.up` is the connection used for application data. `supabase` is the independent Supabase PostgreSQL probe. In the `vercel` profile, both checks target Supabase.

The standalone diagnostic checks the Supabase Auth endpoint and runs `SELECT 1` using the values in `conf/application.properties`:

```powershell
.\venv\Scripts\python.exe scripts\check_supabase_connection.py
```

## Existing SQL Server tooling and Render deployment

`db/mssql/migrations` and the Node CLI remain available for the local and production SQL Server profiles. The SQL Server migration CLI reads profile settings from `conf/application.properties`; use `npm run db:migrate -- --target=local` or `npm run db:migrate -- --target=azure`.

The Render Blueprint selects `APP_PROFILE=vercel` for Supabase PostgreSQL and `NODE_ENV=production` for production security behavior. Configure `SUPABASE_DB_HOST`, `SUPABASE_DB_USER`, and `SUPABASE_DB_PASSWORD` in the Render dashboard; the Blueprint sets the database name and port defaults. Do not copy the local `.env` into the image or Render. Apply the PostgreSQL migrations with `python scripts/migrate_postgres.py` after the Render environment variables are configured and before serving application traffic.

The Dockerfile builds from this repository root and excludes `.env` from the image. Render must be able to resolve and connect to the configured Supabase database endpoint over TLS. If using the direct Supabase endpoint, verify that its address family is reachable from Render; otherwise use the appropriate Supavisor endpoint and credentials. Profile `vercel` selects PostgreSQL, while the app disables background worker threads only when it is actually running on Vercel; Render runs as a regular web service.

For UI/API integration checks, keep the UI checkout beside this repository or set `TALENTSCOPE_UI_DIR` to its path, then run `python scripts/check_api_links.py`.
