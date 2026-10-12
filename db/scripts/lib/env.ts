import { existsSync, readFileSync } from "fs";
import { join, resolve } from "path";

/** Load the shared .env.local from the project root (parent of DB/) without overriding real env vars. */
export function loadProjectEnv(root = resolve(process.cwd(), "..")): void {
  for (const name of [".env.local", ".env"]) {
    const filePath = join(root, name);
    if (!existsSync(filePath)) continue;

    const raw = readFileSync(filePath, "utf8").replace(/^\uFEFF/, "");
    for (const line of raw.split(/\r?\n/)) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith("#")) continue;

      const eq = trimmed.indexOf("=");
      if (eq <= 0) continue;

      const key = trimmed.slice(0, eq).trim();
      let value = trimmed.slice(eq + 1).trim();
      if (
        (value.startsWith('"') && value.endsWith('"')) ||
        (value.startsWith("'") && value.endsWith("'"))
      ) {
        value = value.slice(1, -1);
      }
      if (!process.env[key]) process.env[key] = value;
    }
  }
}

/** Apply `--target=local|remote|azure` (or `--target local`) to MSSQL_TARGET. */
export function applyTargetArg(argv: string[]): void {
  for (let i = 0; i < argv.length; i += 1) {
    const a = argv[i];
    if (a === "--target" && argv[i + 1]) process.env.MSSQL_TARGET = String(argv[++i]).trim();
    else if (a.startsWith("--target=")) process.env.MSSQL_TARGET = a.slice("--target=".length).trim();
  }
}

/** Read `--name=value` or `--name value`. */
export function argValue(argv: string[], name: string): string | null {
  for (let i = 0; i < argv.length; i += 1) {
    const a = argv[i];
    if (a === `--${name}` && argv[i + 1] && !argv[i + 1].startsWith("--")) return argv[i + 1];
    if (a.startsWith(`--${name}=`)) return a.slice(name.length + 3);
  }
  return null;
}
