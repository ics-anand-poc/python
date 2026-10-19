import sql from "mssql";

export type MssqlTarget = "local" | "remote" | "azure";

export function resolveMssqlTarget(): MssqlTarget {
  const raw = String(process.env.MSSQL_TARGET || "local").trim().toLowerCase();
  return raw === "remote" || raw === "azure" ? raw : "local";
}

function envPick(keys: string[], fallback = ""): string {
  for (const key of keys) {
    const v = process.env[key];
    if (v != null && String(v).trim() !== "") return String(v).trim();
  }
  return fallback;
}

function envBool(keys: string[], fallback: boolean): boolean {
  const v = envPick(keys, String(fallback)).toLowerCase();
  return v !== "false" && v !== "0" && v !== "no";
}

/**
 * Each target reads its own MSSQL_<TARGET>_* block (local | remote | azure), then plain MSSQL_*.
 */
export function getMssqlConfig(target = resolveMssqlTarget(), databaseOverride?: string): sql.config {
  const p = `MSSQL_${target.toUpperCase()}_`;
  const isLocal = target === "local";

  const server = envPick([`${p}SERVER`, "MSSQL_SERVER"], isLocal ? "127.0.0.1" : "");
  const database = databaseOverride ?? envPick([`${p}DATABASE`, "MSSQL_DATABASE"], "TalentScope");
  const user = envPick([`${p}USER`, "MSSQL_USER"], isLocal ? "sa" : "");
  const password = envPick(
    isLocal ? [`${p}PASSWORD`, "MSSQL_PASSWORD", "MSSQL_SA_PASSWORD"] : [`${p}PASSWORD`, "MSSQL_PASSWORD"]
  );
  const port = Number(envPick([`${p}PORT`, "MSSQL_PORT"], "1433")) || 1433;

  if (!server || !user || !password) {
    throw new Error(
      `Missing MSSQL ${target} connection env. Set ${p}SERVER / ${p}USER / ${p}PASSWORD (or MSSQL_SERVER / MSSQL_USER / MSSQL_PASSWORD).`
    );
  }

  return {
    server,
    port,
    database,
    user,
    password,
    options: {
      encrypt: envBool([`${p}ENCRYPT`, "MSSQL_ENCRYPT"], true),
      trustServerCertificate: envBool(
        [`${p}TRUST_SERVER_CERTIFICATE`, "MSSQL_TRUST_SERVER_CERTIFICATE"],
        target !== "azure"
      ),
      enableArithAbort: true,
    },
    pool: { max: 4, min: 0 },
    connectionTimeout: Math.max(5_000, Number(process.env.MSSQL_CONNECTION_TIMEOUT_MS) || 30_000),
    requestTimeout: Math.max(10_000, Number(process.env.MSSQL_REQUEST_TIMEOUT_MS) || 600_000),
  };
}

export async function connect(target = resolveMssqlTarget(), databaseOverride?: string) {
  const config = getMssqlConfig(target, databaseOverride);
  console.log(`[mssql] ${target} -> ${config.server}:${config.port}/${config.database}`);
  return new sql.ConnectionPool(config).connect();
}

export { sql };
