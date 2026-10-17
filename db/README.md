# TalentScope Database (MS SQL Server)

This directory contains the database schema migrations, baseline datasets, and deployment scripts for **Microsoft SQL Server**. PostgreSQL application migrations for the Supabase profile are in `postgres/migrations/`.

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

---

## ⚙️ Target Environments

The database tooling reads the connection settings from `../conf/application.properties`. The active `app.profile` selects the default target; `--target=<name>` overrides it for a command:

| Target | Properties | Description |
|---|---|---|
| `local` | `database.local.*` | SQL Server development database |
| `azure` | `database.production.*` | SQL Server live database |
| `vercel` | — | Supabase PostgreSQL; use `scripts/migrate_postgres.py` instead |

---

## 🚀 Running Migrations & Seeding

### 1. Install Dependencies
```powershell
cd DB
npm install
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
Populate standard test questions, curriculum topics, settings, and baseline employees:
```powershell
# Dry run (test without modifying database)
npm run db:deploy-data -- --dry-run

# Actual deployment
npm run db:deploy-data
```

### 5. Combined One-Step Setup (Local)
Runs both migrations and baseline data deployment against local SQL Server:
```powershell
npm run db:local
```

### 6. Azure SQL Deployment
```powershell
npm run db:azure
```

---

## 🛠️ Database Troubleshooting

### 1. `Login failed for user '...'`
- **Cause**: Invalid username or password in `conf/application.properties` or SQL Server is in Windows Authentication-only mode.
- **Fix**:
  1. Verify `database.local.user` in `conf/application.properties` and set `MSSQL_LOCAL_PASSWORD` as a runtime secret.
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
- **Fix**: Set `database.local.trust_certificate=true` in `conf/application.properties`.

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
3. If new tables are introduced, add them to `TABLES` in [`scripts/lib/tables.ts`](file:///scripts/lib/tables.ts).
4. Run `npm run db:migrate` and verify with `npm run db:status`.
