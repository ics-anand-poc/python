/**
 * One-way copy: rows saved in TalentScope_DB_Live -> the database the VM app uses (MSSQL_DATABASE).
 * Reads Live only; every write goes to the connected (app) database. Never deletes.
 *
 * A Live row is copied when it is new or its contents changed since it was last copied (SHA-256 of the row,
 * kept in dbo.__live_sync_rows). Rows the app changed itself stay as they are until Live changes them again;
 * a Live row that clashes with app data (unique key, missing parent) is skipped and logged once.
 * The first run of a table only records the current Live rows, so it never overwrites existing app data.
 *
 * Usage: tsx scripts/sync-live-to-dev.ts [--tables=a,b] [--dry-run]
 * Env: MSSQL_* (app database, the target), SYNC_SOURCE_DATABASE (default TalentScope_DB_Live).
 */
import { applyTargetArg, argValue, loadProjectEnv } from "./lib/env";
import { connect, resolveMssqlTarget, sql } from "./lib/mssql";
import { quoteIdent, selectTables, type TableDef } from "./lib/tables";

loadProjectEnv();
const argv = process.argv.slice(2);
applyTargetArg(argv);

const SOURCE = process.env.SYNC_SOURCE_DATABASE || "TalentScope_DB_Live";
const DRY_RUN = argv.includes("--dry-run");
/** Owned by the VM app (Corp Pool roster, admin settings). */
const EXCLUDED = new Set(["portal_settings"]);
const SKIP_TYPES = ["timestamp", "xml", "text", "ntext", "image", "sql_variant", "geography", "geometry", "hierarchyid"];

type Pool = sql.ConnectionPool;
type Changed = { k: string; h: Buffer };
type Result = { changed: number; inserted: number; updated: number; conflicts: number; seeded?: number; notInApp?: number };

type Shape = { cols: string[]; identity: boolean; textual: Set<string> };

async function columnsFor(pool: Pool, table: string): Promise<Shape | null> {
  const result = await pool.request().input("src", sql.NVarChar, `${SOURCE}.dbo.${table}`).input("dst", sql.NVarChar, `dbo.${table}`).query(`
    SELECT s.name, CAST(d.is_identity AS int) AS isIdentity,
           CASE WHEN s.collation_name IS NOT NULL OR d.collation_name IS NOT NULL THEN 1 ELSE 0 END AS textual
    FROM [${SOURCE}].sys.columns s
    JOIN sys.columns d ON d.object_id = OBJECT_ID(@dst) AND d.name = s.name
    WHERE s.object_id = OBJECT_ID(@src) AND s.is_computed = 0 AND d.is_computed = 0
      AND TYPE_NAME(s.system_type_id) NOT IN (${SKIP_TYPES.map((t) => `'${t}'`).join(", ")})
      AND TYPE_NAME(d.system_type_id) NOT IN (${SKIP_TYPES.map((t) => `'${t}'`).join(", ")})
    ORDER BY s.column_id`);
  if (!result.recordset.length) return null;
  return {
    cols: result.recordset.map((r) => String(r.name)),
    identity: result.recordset.some((r) => r.isIdentity),
    textual: new Set(result.recordset.filter((r) => r.textual).map((r) => String(r.name))),
  };
}

function statements(table: TableDef, shape: Shape) {
  const pk = table.pk[0];
  const src = `[${SOURCE}].dbo.${quoteIdent(table.name)}`;
  const dst = `dbo.${quoteIdent(table.name)}`;
  const q = shape.cols.map(quoteIdent);
  // Live and the app database may use different collations; compare text in the app database's collation.
  const srcCol = (c: string) => `s.${quoteIdent(c)}${shape.textual.has(c) ? " COLLATE DATABASE_DEFAULT" : ""}`;
  const nonKey = shape.cols.filter((c) => c !== pk);
  const key = (alias: string) => `CONVERT(nvarchar(200), ${alias}.${quoteIdent(pk)}) COLLATE DATABASE_DEFAULT`;
  const hash = `HASHBYTES('SHA2_256', (SELECT ${q.map((c) => `s.${c}`).join(", ")} FOR JSON PATH, WITHOUT_ARRAY_WRAPPER, INCLUDE_NULL_VALUES))`;
  const join = `d.${quoteIdent(pk)} = ${srcCol(pk)}`;
  const update = nonKey.length
    ? `UPDATE d SET ${nonKey.map((c) => `d.${quoteIdent(c)} = s.${quoteIdent(c)}`).join(", ")}
       FROM ${dst} d JOIN ${src} s ON ${join} JOIN #chg c ON c.k = ${key("s")}
       WHERE EXISTS (SELECT ${nonKey.map(srcCol).join(", ")} EXCEPT SELECT ${nonKey.map((c) => `d.${quoteIdent(c)}`).join(", ")});`
    : "";
  return {
    hashes: `SELECT ${key("s")} AS k, ${hash} AS h FROM ${src} s`,
    missingInApp: `SELECT COUNT(*) AS n FROM ${src} s WHERE NOT EXISTS (SELECT 1 FROM ${dst} d WHERE ${join})`,
    apply: `
      DECLARE @updated int = 0, @inserted int = 0;
      ${update}
      SET @updated = @@ROWCOUNT;
      INSERT INTO ${dst} (${q.join(", ")})
      SELECT ${q.map((c) => `s.${c}`).join(", ")} FROM ${src} s JOIN #chg c ON c.k = ${key("s")}
      WHERE NOT EXISTS (SELECT 1 FROM ${dst} d WHERE ${join});
      SET @inserted = @@ROWCOUNT;
      SELECT @updated AS updated, @inserted AS inserted;`,
  };
}

async function loadChg(tx: sql.Transaction, rows: Changed[]) {
  await new sql.Request(tx).batch(
    "IF OBJECT_ID('tempdb..#chg') IS NOT NULL DROP TABLE #chg; CREATE TABLE #chg (k nvarchar(200) COLLATE DATABASE_DEFAULT NOT NULL PRIMARY KEY, h varbinary(32) NOT NULL);"
  );
  const t = new sql.Table("#chg");
  t.create = false;
  t.columns.add("k", sql.NVarChar(200), { nullable: false });
  t.columns.add("h", sql.VarBinary(32), { nullable: false });
  for (const r of rows) t.rows.add(r.k, r.h);
  await new sql.Request(tx).bulk(t);
}

async function recordState(tx: sql.Transaction, table: string) {
  await new sql.Request(tx).input("t", sql.NVarChar(64), table).query(`
    MERGE dbo.__live_sync_rows AS r USING #chg AS c ON r.table_name = @t AND r.row_key = c.k
    WHEN MATCHED THEN UPDATE SET row_hash = c.h, synced_at = SYSUTCDATETIME()
    WHEN NOT MATCHED THEN INSERT (table_name, row_key, row_hash) VALUES (@t, c.k, c.h);`);
}

/** Apply `rows` in one transaction; returns counts, or throws (rolled back) if any row is rejected. */
async function applyBatch(pool: Pool, table: TableDef, apply: string, rows: Changed[]) {
  const tx = new sql.Transaction(pool);
  await tx.begin();
  try {
    await loadChg(tx, rows);
    const r = (await new sql.Request(tx).query(apply)).recordset[0] ?? {};
    await recordState(tx, table.name);
    if (DRY_RUN) await tx.rollback();
    else await tx.commit();
    return { updated: Number(r.updated || 0), inserted: Number(r.inserted || 0) };
  } catch (err) {
    await tx.rollback().catch(() => {});
    throw err;
  }
}

async function recordOnly(pool: Pool, table: TableDef, rows: Changed[]) {
  const tx = new sql.Transaction(pool);
  await tx.begin();
  try {
    await loadChg(tx, rows);
    await recordState(tx, table.name);
    if (DRY_RUN) await tx.rollback();
    else await tx.commit();
  } catch (err) {
    await tx.rollback().catch(() => {});
    throw err;
  }
}

async function syncTable(pool: Pool, table: TableDef): Promise<Result | string> {
  if (table.pk.length !== 1) return "composite key, skipped";
  const shape = await columnsFor(pool, table.name);
  if (!shape) return "not in both databases, skipped";
  if (!shape.cols.includes(table.pk[0])) return `key ${table.pk[0]} missing, skipped`;
  if (shape.identity) return "identity column, skipped";
  const st = statements(table, shape);

  const seeded = (
    await pool.request().input("t", sql.NVarChar(64), table.name).query("SELECT TOP 1 1 AS x FROM dbo.__live_sync_rows WHERE table_name = @t")
  ).recordset.length > 0;

  const changed = (
    await pool.request().input("t", sql.NVarChar(64), table.name).query(`
      SELECT x.k, x.h FROM (${st.hashes}) x
      WHERE NOT EXISTS (SELECT 1 FROM dbo.__live_sync_rows r WHERE r.table_name = @t AND r.row_key = x.k AND r.row_hash = x.h)`)
  ).recordset as Changed[];

  if (!seeded) {
    if (changed.length) await recordOnly(pool, table, changed);
    const notInApp = Number((await pool.request().query(st.missingInApp)).recordset[0]?.n || 0);
    return { changed: 0, inserted: 0, updated: 0, conflicts: 0, seeded: changed.length, notInApp };
  }
  if (!changed.length) return { changed: 0, inserted: 0, updated: 0, conflicts: 0 };

  try {
    return { changed: changed.length, conflicts: 0, ...(await applyBatch(pool, table, st.apply, changed)) };
  } catch (err: any) {
    console.warn(`  ${table.name.padEnd(26)} batch rejected (${err?.message || err}); applying row by row`);
  }
  const res: Result = { changed: changed.length, inserted: 0, updated: 0, conflicts: 0 };
  for (const row of changed) {
    try {
      const r = await applyBatch(pool, table, st.apply, [row]);
      res.inserted += r.inserted;
      res.updated += r.updated;
    } catch (err: any) {
      res.conflicts++;
      console.warn(`  ${table.name.padEnd(26)} kept the app's version of ${row.k}: ${err?.message || err}`);
      await recordOnly(pool, table, [row]);
    }
  }
  return res;
}

async function main() {
  if (!/^[A-Za-z0-9_]+$/.test(SOURCE)) throw new Error(`Invalid SYNC_SOURCE_DATABASE "${SOURCE}"`);
  const started = Date.now();
  const pool = await connect(resolveMssqlTarget());
  try {
    const target = String((await pool.request().query("SELECT DB_NAME() AS db")).recordset[0].db);
    if (target.toLowerCase() === SOURCE.toLowerCase()) {
      throw new Error(`Target ${target} is the source database; this job only writes the app database.`);
    }
    const state = await pool.request().query("SELECT OBJECT_ID(N'dbo.__live_sync_rows', N'U') AS id");
    if (!state.recordset[0]?.id) throw new Error("dbo.__live_sync_rows is missing; apply migration 007 first.");
    console.log(`[live-to-dev] ${new Date(started).toISOString()} ${SOURCE} -> ${target}${DRY_RUN ? " (dry run)" : ""}`);

    const totals = { changed: 0, inserted: 0, updated: 0, conflicts: 0 };
    let failed = 0;
    for (const table of selectTables(argValue(argv, "tables")).filter((t) => !EXCLUDED.has(t.name))) {
      try {
        const r = await syncTable(pool, table);
        if (typeof r === "string") {
          console.log(`  ${table.name.padEnd(26)} ${r}`);
          continue;
        }
        if (r.seeded !== undefined) {
          console.log(
            `  ${table.name.padEnd(26)} first run: recorded ${r.seeded} Live row(s)${r.notInApp ? `; ${r.notInApp} Live row(s) not in the app database were left out` : ""}`
          );
          continue;
        }
        for (const k of Object.keys(totals) as Array<keyof typeof totals>) totals[k] += r[k];
        if (r.changed) {
          console.log(
            `  ${table.name.padEnd(26)} ${String(r.changed).padStart(5)} changed in Live | +${r.inserted} inserted, ~${r.updated} updated${r.conflicts ? `, ${r.conflicts} kept as in app` : ""}`
          );
        }
      } catch (err: any) {
        failed++;
        console.error(`  ${table.name.padEnd(26)} FAILED: ${err?.message || err}`);
      }
    }
    const secs = ((Date.now() - started) / 1000).toFixed(1);
    console.log(
      `[live-to-dev] ${DRY_RUN ? "dry run, rolled back" : "done"}: ${totals.changed} Live row(s) new/changed, +${totals.inserted} inserted, ~${totals.updated} updated, ${totals.conflicts} kept as in app${failed ? `, ${failed} table(s) failed` : ""}, ${secs}s`
    );
    if (failed) process.exitCode = 1;
  } finally {
    await pool.close();
  }
}

main().catch((err) => {
  console.error(`[live-to-dev] FAILED: ${err?.message || err}`);
  process.exit(1);
});
