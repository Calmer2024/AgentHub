import { existsSync } from "node:fs";
import { resolve } from "node:path";

const required = [
  "capacitor.config.ts",
  "../frontend/src/shells/mobile/MobileShell.tsx",
];

const missing = required.filter((item) => !existsSync(resolve(import.meta.dirname, "..", item)));
if (missing.length > 0) {
  console.error(`Missing mobile shell files: ${missing.join(", ")}`);
  process.exit(1);
}

console.log("AgentHub mobile shell smoke OK");
