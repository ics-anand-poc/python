import { existsSync, readFileSync } from "fs";
import { join, resolve } from "path";

function readProperties(root: string): Map<string, string> {
  const propertiesPath = join(root, "conf", "application.properties");
  if (!existsSync(propertiesPath)) throw new Error(`application.properties was not found at ${propertiesPath}`);

  const properties = new Map<string, string>();
  const raw = readFileSync(propertiesPath, "utf8").replace(/^\uFEFF/, "");
  for (const line of raw.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#") || trimmed.startsWith("!")) continue;
    const eq = trimmed.indexOf("=");
    if (eq <= 0) throw new Error(`Invalid property line in ${propertiesPath}`);
    properties.set(trimmed.slice(0, eq).trim(), trimmed.slice(eq + 1).trim());
  }
  return properties;
}

function readDotenv(root: string): Map<string, string> {
  const dotenvPath = join(root, ".env");
  const values = new Map<string, string>();
  if (!existsSync(dotenvPath)) return values;

  for (const [index, sourceLine] of readFileSync(dotenvPath, "utf8").replace(/^\uFEFF/, "").split(/\r?\n/).entries()) {
    let line = sourceLine.trim();
    if (!line || line.startsWith("#")) continue;
    if (line.startsWith("export ")) line = line.slice(7).trimStart();
    const eq = line.indexOf("=");
    if (eq <= 0) throw new Error(`Invalid environment variable at ${dotenvPath}:${index + 1}`);
    const key = line.slice(0, eq).trim();
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(key)) {
      throw new Error(`Invalid environment variable at ${dotenvPath}:${index + 1}`);
    }
    let value = line.slice(eq + 1).trim();
    if (value.length >= 2 && (value.startsWith('"') && value.endsWith('"') || value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }
    values.set(key, value);
  }
  return values;
}

function propertyValue(properties: Map<string, string>, dotenv: Map<string, string>, key: string): string {
  const value = properties.get(key) || "";
  const reference = /^\$\{([A-Za-z_][A-Za-z0-9_]*)(?::([^}]*))?\}$/.exec(value);
  return reference ? process.env[reference[1]] || dotenv.get(reference[1]) || reference[2] || "" : value;
}

/** Load non-secret profile connection values from application.properties. */
export function loadApplicationProperties(root = resolve(process.cwd(), "..")): void {
  const properties = readProperties(root);
  const dotenv = readDotenv(root);
  const activeProfile = process.env.APP_PROFILE
    || (process.env.VERCEL ? "vercel" : process.env.NODE_ENV === "production" ? "production" : properties.get("app.profile") || "local");

  for (const [profile, target] of [["local", "LOCAL"], ["production", "AZURE"]] as const) {
    const prefix = `database.${profile}.`;
    const fields: Record<string, string> = {
      SERVER: "host",
      PORT: "port",
      DATABASE: "database",
      USER: "user",
      PASSWORD: "password",
      ENCRYPT: "encrypt",
      TRUST_SERVER_CERTIFICATE: "trust_certificate",
    };
    for (const [suffix, property] of Object.entries(fields)) {
      const value = propertyValue(properties, dotenv, prefix + property);
      if (value && !process.env[`MSSQL_${target}_${suffix}`]) {
        process.env[`MSSQL_${target}_${suffix}`] = value;
      }
    }
  }

  if (!process.env.MSSQL_TARGET) {
    process.env.MSSQL_TARGET = activeProfile === "production" ? "azure" : activeProfile === "local" ? "local" : "vercel";
  }
}

/** Apply `--target=local|remote|azure` (or `--target local`) to MSSQL_TARGET. */
export function applyTargetArg(argv: string[]): void {
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--target" && argv[i + 1]) process.env.MSSQL_TARGET = String(argv[++i]).trim();
    else if (arg.startsWith("--target=")) process.env.MSSQL_TARGET = arg.slice("--target=".length).trim();
  }
}

/** Read `--name=value` or `--name value`. */
export function argValue(argv: string[], name: string): string | null {
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === `--${name}` && argv[i + 1] && !argv[i + 1].startsWith("--")) return argv[i + 1];
    if (arg.startsWith(`--${name}=`)) return arg.slice(name.length + 3);
  }
  return null;
}
