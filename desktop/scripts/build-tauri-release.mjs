import { spawnSync } from "node:child_process";
import { resolve } from "node:path";

const repoRoot = resolve(import.meta.dirname, "..", "..");
const desktopDir = resolve(repoRoot, "desktop");
const command = process.platform === "win32" ? "cmd.exe" : "npx";
const args = process.platform === "win32"
  ? ["/d", "/s", "/c", "npx tauri build --no-bundle"]
  : ["tauri", "build", "--no-bundle"];

const cargoBin = process.platform === "win32" && process.env.USERPROFILE
  ? resolve(process.env.USERPROFILE, ".cargo", "bin")
  : "";

const result = spawnSync(command, args, {
  cwd: desktopDir,
  stdio: "inherit",
  env: {
    ...process.env,
    PATH: cargoBin ? `${cargoBin};${process.env.PATH ?? ""}` : process.env.PATH,
  },
});

if (result.error) {
  console.error(result.error);
}

process.exit(result.status ?? 1);
