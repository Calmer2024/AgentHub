import { cpSync, existsSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { resolve } from "node:path";

const repoRoot = resolve(import.meta.dirname, "..", "..");
const version = "1.0.0";
const packageName = `AgentHub-${version}-win-x64`;
const bundleRoot = resolve(repoRoot, "deploy", "desktop");
const bundleDir = resolve(bundleRoot, packageName);
const releaseDir = resolve(repoRoot, "desktop", "src-tauri", "target", "release");
const sidecarSource = resolve(repoRoot, "desktop", "src-tauri", "resources", "agenthub-backend.exe");

if (!existsSync(sidecarSource)) {
  console.error(`Missing backend sidecar: ${sidecarSource}`);
  process.exit(1);
}

rmSync(bundleDir, { recursive: true, force: true });
mkdirSync(resolve(bundleDir, "resources"), { recursive: true });

cpSync(resolve(releaseDir, "agenthub-local-desktop.exe"), resolve(bundleDir, "AgentHub.exe"));
cpSync(sidecarSource, resolve(bundleDir, "resources", "agenthub-backend.exe"));
writeFileSync(
  resolve(bundleDir, "README.txt"),
  [
    "AgentHub Desktop 1.0.0",
    "",
    "启动方式：双击 “AgentHub.exe”。",
    "",
    "说明：",
    "- 桌面壳会自动启动内置本地后端 sidecar。",
    "- 本地后端监听 http://127.0.0.1:8188。",
    "- 本地数据目录位于 %APPDATA%\\AgentHub Local Desktop。",
    "- 这是 portable 发布包，不需要先手动启动 frontend/backend。",
    "",
    "如果 8188 端口被其他程序占用，请先关闭占用进程后再启动。",
    "",
  ].join("\n"),
  "utf8",
);

if (process.platform === "win32") {
  const zipPath = resolve(bundleRoot, `${packageName}.zip`);
  rmSync(zipPath, { force: true });
  const command = `Compress-Archive -Path "${bundleDir}\\*" -DestinationPath "${zipPath}" -Force`;
  const zip = spawnSync("powershell.exe", ["-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command], {
    cwd: repoRoot,
    stdio: "inherit",
  });
  if (zip.status !== 0) process.exit(zip.status ?? 1);
}

console.log(`Portable desktop release written to ${bundleDir}`);
