import { spawnSync } from "node:child_process";
import { resolve } from "node:path";

const repoRoot = resolve(import.meta.dirname, "..", "..");
const frontendDir = resolve(repoRoot, "frontend");
const command = process.platform === "win32" ? "cmd.exe" : "npm";
const args = process.platform === "win32"
  ? ["/d", "/s", "/c", "npm run build:local"]
  : ["run", "build:local"];

const result = spawnSync(command, args, {
  cwd: frontendDir,
  stdio: "inherit",
  env: {
    ...process.env,
    VITE_AGENTHUB_EDITION: "local",
    VITE_AGENTHUB_SURFACE: "desktop",
    VITE_AGENTHUB_API_BASE: "http://127.0.0.1:8188",
  },
});

if (result.error) {
  console.error(result.error);
}

process.exit(result.status ?? 1);
