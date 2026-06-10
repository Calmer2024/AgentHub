import { spawnSync } from "node:child_process";
import { resolve } from "node:path";

const repoRoot = resolve(import.meta.dirname, "..", "..");
const tauriDir = resolve(repoRoot, "desktop", "src-tauri");
const command = process.platform === "win32" ? "cmd.exe" : "cargo";
const args = process.platform === "win32"
  ? ["/d", "/s", "/c", "cargo build --release"]
  : ["build", "--release"];

const cargoBin = process.platform === "win32" && process.env.USERPROFILE
  ? resolve(process.env.USERPROFILE, ".cargo", "bin")
  : "";

const result = spawnSync(command, args, {
  cwd: tauriDir,
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
