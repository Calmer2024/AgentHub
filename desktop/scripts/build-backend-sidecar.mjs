import { mkdirSync, rmSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { delimiter, resolve } from "node:path";

const repoRoot = resolve(import.meta.dirname, "..", "..");
const backendDir = resolve(repoRoot, "backend");
const runnerPath = resolve(repoRoot, "desktop", "backend_runner.py");
const resourcesDir = resolve(repoRoot, "desktop", "src-tauri", "resources");
const workPath = resolve(repoRoot, ".tmp", "pyinstaller-work");
const specPath = resolve(repoRoot, ".tmp", "pyinstaller-spec");
const python = process.platform === "win32"
  ? resolve(backendDir, "venv", "Scripts", "python.exe")
  : resolve(backendDir, "venv", "bin", "python");
const addDataSeparator = process.platform === "win32" ? ";" : ":";

mkdirSync(resourcesDir, { recursive: true });
rmSync(resolve(resourcesDir, process.platform === "win32" ? "agenthub-backend.exe" : "agenthub-backend"), {
  force: true,
});

const args = [
  "-m",
  "PyInstaller",
  "--noconfirm",
  "--clean",
  "--onefile",
  "--name",
  "agenthub-backend",
  "--distpath",
  resourcesDir,
  "--workpath",
  workPath,
  "--specpath",
  specPath,
  "--paths",
  backendDir,
  "--add-data",
  `${resolve(backendDir, "migrations")}${addDataSeparator}migrations`,
  "--hidden-import",
  "aiosqlite",
  "--hidden-import",
  "multipart",
  "--hidden-import",
  "uvicorn.lifespan.on",
  "--hidden-import",
  "uvicorn.protocols.http.auto",
  "--hidden-import",
  "uvicorn.protocols.websockets.auto",
  runnerPath,
];

const env = {
  ...process.env,
  PYTHONPATH: [backendDir, process.env.PYTHONPATH].filter(Boolean).join(delimiter),
};

const result = spawnSync(python, args, {
  cwd: repoRoot,
  stdio: "inherit",
  env,
});

process.exit(result.status ?? 1);
