import { existsSync } from "node:fs";
import { resolve } from "node:path";

const required = [
  "src-tauri/tauri.conf.json",
  "src-tauri/Cargo.toml",
  "../frontend/package.json",
];

const missing = required.filter((item) => !existsSync(resolve(import.meta.dirname, "..", item)));
if (missing.length > 0) {
  console.error(`Missing desktop shell files: ${missing.join(", ")}`);
  process.exit(1);
}

console.log("AgentHub local desktop shell smoke OK");
