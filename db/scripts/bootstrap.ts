/**
 * Create the TalentScope database on the target server if it does not exist.
 *
 * Usage:
 *   npm run db:bootstrap                      (local Docker)
 *   npm run db:bootstrap -- --target=remote
 *   npm run db:bootstrap -- --wait            (retry for ~2 min while a fresh container starts)
 */
import { applyTargetArg, loadProjectEnv } from "./lib/env";
import { connect, getMssqlConfig, resolveMssqlTarget, sql } from "./lib/mssql";

loadProjectEnv();
const argv = process.argv.slice(2);
applyTargetArg(argv);

async function connectMaster(target: ReturnType<typeof resolveMssqlTarget>) {
  const attempts = argv.includes("--wait") ? 40 : 1;
  for (let i = 1; ; i += 1) {
    try {
      return await connect(target, "master");
    } catch (err: any) {
      if (i >= attempts) throw err;
      console.log(`  server not ready (${err?.message || err}), retry ${i}/${attempts - 1}...`);
      await new Promise((r) => setTimeout(r, 3000));
    }
  }
}

async function main() {
  const target = resolveMssqlTarget();
  const database = String(getMssqlConfig(target).database);
  if (!/^[A-Za-z0-9_]+$/.test(database)) {
    throw new Error(`Unsafe database name "${database}". Use letters, numbers and underscore only.`);
  }

  const pool = await connectMaster(target);
  try {
    const exists = await pool
      .request()
      .input("name", sql.NVarChar(128), database)
      .query<{ id: number | null }>(`SELECT DB_ID(@name) AS id`);
    if (exists.recordset[0]?.id == null) {
      await pool.request().batch(`CREATE DATABASE [${database}]`);
      console.log(`Created database ${database}`);
    } else {
      console.log(`Database ${database} already exists`);
    }
  } finally {
    await pool.close();
  }
}

main().catch((err) => {
  console.error(err?.message || err);
  process.exit(1);
});
