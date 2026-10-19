# TalentScope Database

This directory contains the database schema migrations, optional baseline datasets, and deployment scripts for **Microsoft SQL Server** (local, remote, or Azure SQL), plus the **Supabase/PostgreSQL** schema. The Python API can connect to either database using `DB_TARGET`; its current target is independently chosen for SQL Server using `MSSQL_TARGET`. The seed JSON files are excluded from Git and Docker by default because they contain personal data; provide approved, sanitized datasets privately if you need to seed a database.

---

## 📁 Directory Structure

| Path | Description |
|---|---|
| `mssql/migrations/*.sql` | Ordered SQL DDL migrations (applied sequentially, tracked in `__migrations` table) |
| `mssql/data/*.json` | Baseline table seed datasets (employees, job descriptions, test questions, settings) |
| `scripts/migrate.ts` | Migration runner (applies unapplied `.sql` scripts and verifies checksums) |
| `scripts/deploy-data.ts` | Data deployment engine (inserts or upserts baseline datasets into target DB) |
| `scripts/bootstrap.ts` | Creates the database instance if it does not yet exist |
| `scripts/lib/mssql.ts` | Database connection pool configuration and target resolution |
| `supabase/config.toml` | Supabase CLI local-development configuration |
| `supabase/migrations/*.sql` | PostgreSQL schema migrations for Supabase |

---

## ⚙️ Target Environments

The database tooling reads `MSSQL_TARGET` and the matching connection variables from the Python repository's `.env` or `.env.local` file (or `--target=<name>` on the CLI):

| Target | Env Prefix | Description |
|---|---|---|
| `local` | `MSSQL_LOCAL_*` | Local MS SQL Server (e.g. `localhost:1433`, default) |
| `azure` | `MSSQL_AZURE_*` | Microsoft Azure SQL Database (TLS encryption enforced) |
| `remote` | `MSSQL_REMOTE_*` | Company staging / dev SQL Server |

---

## 🚀 Running Migrations & Seeding

### 1. Install Dependencies
```powershell
cd db
npm ci
```

### 2. Check Migration Status
Check which migrations are applied and which are pending:
```powershell
npm run db:status
```

### 3. Apply Schema Migrations
```powershell
npm run db:migrate
```

### 4. Deploy Baseline Datasets
Only run this after supplying the required approved JSON files under `mssql/data/`:
```powershell
# Dry run (test without modifying database)
npm run db:deploy-data -- --dry-run

# Actual deployment
npm run db:deploy-data
```

### 5. Combined One-Step Setup (Local)
Runs both migrations and baseline data deployment against local SQL Server. Requires the private seed files above:
```powershell
npm run db:local
```

### 6. Azure SQL Deployment
`db:azure` includes baseline data deployment and requires the private seed files. To apply schema migrations only, run:
```powershell
npm run db:migrate -- --target=azure
```

## Supabase Data API runtime

The API uses Supabase's HTTPS Data API; no direct PostgreSQL password or local Docker/Supabase stack is needed. Set `DB_TARGET=SUPABASE` in the Python repository's `.env.local`, and configure:

```dotenv
NEXT_PUBLIC_SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<server-side-service-role-key>
SUPABASE_API_TIMEOUT_S=20
```

The backend sends requests to `/rest/v1/` using the service-role key in the `apikey` and bearer authorization headers. The key bypasses row-level security, so it must remain private on the backend and must never be exposed to a browser. The anon key is not used by this backend store. SQL Server retains its separate `MSSQL_TARGET=local|remote|azure` selection when `DB_TARGET=MSSQL`.

Install the Python requirements after updating the checkout:

```powershell
pip install -r requirements.txt
```

Because the service-role key was pasted into chat, treat it as compromised: rotate it in the Supabase dashboard and use only the newly generated key in the ignored `.env.local`. Do not commit that file.

In the Supabase Dashboard, open **SQL Editor**, paste the contents of `supabase/migrations/20261019130000_initial_schema.sql`, and run it against the project. This migration creates the tables and enables row-level security; it does not create client policies.

Only use `DB_TARGET=SUPABASE` once the migration is applied and the URL and rotated key are set. Check `/api/health` and the API logs to verify connectivity.

The optional local Supabase CLI commands still exist for development, but require Docker Desktop:

```powershell
npm run supabase:start
npm run supabase:status
npm run supabase:stop
```

---

## 🛠️ Database Troubleshooting

### 1. `Login failed for user '...'`
- **Cause**: Invalid username or password in `.env` or SQL Server is in Windows Authentication-only mode.
- **Fix**:
  1. Verify `MSSQL_LOCAL_USER` and `MSSQL_LOCAL_PASSWORD` in the Python repository's `.env`.
  2. In SQL Server Management Studio (SSMS), right-click your Server -> **Properties** -> **Security** -> Enable **SQL Server and Windows Authentication mode**.
  3. Under **Security** -> **Logins**, ensure the user exists, is enabled, and has `db_owner` role on the `Talentscope` database.

### 2. `TCP Provider: No connection could be made because the target machine actively refused it`
- **Cause**: SQL Server service is stopped, or TCP/IP protocol is disabled.
- **Fix**:
  1. Open **Windows Services** (`services.msc`) and verify `SQL Server (MSSQLSERVER)` is Running.
  2. Open **SQL Server Configuration Manager** -> **SQL Server Network Configuration** -> **Protocols for MSSQLSERVER**.
  3. Ensure **TCP/IP** is **Enabled**.
  4. Right-click **TCP/IP** -> **Properties** -> **IP Addresses** -> scroll to **IPAll** -> ensure **TCP Port** is `1433`. Restart the SQL Server service.

### 3. `The certificate chain was issued by an authority that is not trusted`
- **Cause**: Self-signed SSL certificate on local SQL Server.
- **Fix**: Set `MSSQL_LOCAL_TRUST_SERVER_CERTIFICATE=true` in the Python repository's `.env`.

### 4. `Migration Checksum Mismatch`
- **Cause**: An existing `.sql` migration file was modified after it was already applied to the database.
- **Fix**: Never edit applied migrations. Create a new migration file (e.g. `006_new_feature.sql`). If developing locally and resetting:
  ```sql
  DROP TABLE __migrations;
  ```
  Then re-run `npm run db:migrate`.

---

## 📜 Adding New Migrations

1. Create a new file in `mssql/migrations/` following the naming convention `00X_description.sql`.
2. Ensure DDL statements are idempotent or safe for migration.
3. If new tables are introduced, add them to [`scripts/lib/tables.ts`](./scripts/lib/tables.ts).
4. Run `npm run db:migrate` and verify with `npm run db:status`.
