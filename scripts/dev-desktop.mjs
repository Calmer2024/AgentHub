import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import net from "node:net";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

process.on("uncaughtException", reportFatalError);
process.on("unhandledRejection", reportFatalError);

const repoRoot = resolve(fileURLToPath(new URL(".", import.meta.url)), "..");
const backendDir = resolve(repoRoot, "backend");
const desktopDir = resolve(repoRoot, "desktop");
const runtimeDir = resolve(repoRoot, ".agenthub-runtime", "dev-desktop");

const options = parseArgs(process.argv.slice(2));
const children = new Set();
let stopping = false;

if (options.help) {
  printHelp();
  process.exit(0);
}

options.backendPort = await resolveAvailablePort(options.backendPort, "FastAPI 后端", options.backendPortExplicit);
options.frontendPort = await resolveAvailablePort(options.frontendPort, "Vite 前端", options.frontendPortExplicit);

const backendUrl = `http://127.0.0.1:${options.backendPort}`;
const frontendUrl = `http://127.0.0.1:${options.frontendPort}`;

const python = resolvePython(options.python);
assertFile(resolve(desktopDir, "node_modules", "@tauri-apps", "cli", "tauri.js"), "桌面端依赖缺失，请先运行 cd desktop && npm install");
assertFile(resolve(repoRoot, "frontend", "node_modules", "vite", "bin", "vite.js"), "前端依赖缺失，请先运行 cd frontend && npm install");

if (options.check) {
  console.log(`[dev] 环境检查通过：python=${python}`);
  console.log(`[dev] 可用端口：backend=${options.backendPort}, frontend=${options.frontendPort}`);
  process.exit(0);
}

installShutdownHandlers();

console.log(`[dev] 启动 FastAPI（CLI 兼容热重载）：${backendUrl}`);
const uvicornCommand = [
  quoteShellArg(python),
  "-m",
  "uvicorn",
  "app.main:app",
  "--host",
  "127.0.0.1",
  "--port",
  String(options.backendPort),
].join(" ");
const backend = startChild(
  python,
  [
    "-m",
    "watchfiles",
    "--filter",
    "python",
    "--target-type",
    "command",
    uvicornCommand,
    ".",
  ],
  {
    cwd: backendDir,
    env: {
      ...process.env,
      AGENTHUB_EDITION: "local",
      AGENTHUB_SURFACE: "desktop",
      AGENTHUB_API_BASE_URL: backendUrl,
      AGENTHUB_AUTH_REQUIRED: "false",
      AGENTHUB_DEV_AUTH_ENABLED: "true",
      CORS_ORIGINS: JSON.stringify([
        frontendUrl,
        `http://localhost:${options.frontendPort}`,
        "http://tauri.localhost",
        "https://tauri.localhost",
        "tauri://localhost",
      ]),
    },
  },
  "FastAPI",
);

try {
  const capabilities = await Promise.race([
    waitForJson(`${backendUrl}/api/capabilities`, 60_000),
    childExit(backend, "FastAPI").then((code) => {
      throw new Error(`FastAPI 在健康检查前退出（code=${code}）`);
    }),
  ]);
  if (capabilities.edition !== "local" || capabilities.surface !== "desktop") {
    throw new Error(`后端能力配置不匹配：${capabilities.edition}/${capabilities.surface}`);
  }

  mkdirSync(runtimeDir, { recursive: true });
  const overridePath = resolve(runtimeDir, `tauri.${options.frontendPort}.conf.json`);
  writeFileSync(overridePath, JSON.stringify({
    build: {
      beforeDevCommand: `cd ../frontend && npm run dev:local -- --host 127.0.0.1 --port ${options.frontendPort} --strictPort`,
      devUrl: frontendUrl,
    },
  }, null, 2));

  console.log(`[dev] 后端就绪，启动 Vite + Tauri：${frontendUrl}`);
  console.log("[dev] 修改 React/Python 会自动重载；关闭窗口或按 Ctrl+C 可停止全部进程。\n");

  const tauri = startTauri(overridePath, {
    ...process.env,
    AGENTHUB_DEV_BACKEND_PORT: String(options.backendPort),
    VITE_AGENTHUB_EDITION: "local",
    VITE_AGENTHUB_SURFACE: "desktop",
    VITE_AGENTHUB_API_BASE: backendUrl,
    VITE_AGENTHUB_PROXY_TARGET: backendUrl,
    VITE_AGENTHUB_DEV_AUTH: "false",
  });

  const exitCode = await Promise.race([
    childExit(tauri, "Tauri"),
    childExit(backend, "FastAPI").then((code) => {
      if (!stopping) throw new Error(`FastAPI 意外退出（code=${code}）`);
      return code;
    }),
  ]);
  await shutdown(exitCode ?? 0);
} catch (error) {
  console.error(`[dev] ${error instanceof Error ? error.message : String(error)}`);
  await shutdown(1);
}

function parseArgs(args) {
  const parsed = {
    backendPort: readEnvPort("AGENTHUB_DEV_BACKEND_PORT", 8188),
    frontendPort: readEnvPort("AGENTHUB_DEV_FRONTEND_PORT", 5173),
    backendPortExplicit: Boolean(process.env.AGENTHUB_DEV_BACKEND_PORT),
    frontendPortExplicit: Boolean(process.env.AGENTHUB_DEV_FRONTEND_PORT),
    python: process.env.AGENTHUB_PYTHON || "",
    check: false,
    help: false,
  };

  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    if (arg === "--backend-port") {
      parsed.backendPort = parsePort(args[++index], arg);
      parsed.backendPortExplicit = true;
    } else if (arg === "--frontend-port") {
      parsed.frontendPort = parsePort(args[++index], arg);
      parsed.frontendPortExplicit = true;
    }
    else if (arg === "--python") parsed.python = args[++index] || "";
    else if (arg === "--check") parsed.check = true;
    else if (arg === "--help" || arg === "-h") parsed.help = true;
    else throw new Error(`未知参数：${arg}（使用 --help 查看帮助）`);
  }
  return parsed;
}

function readEnvPort(name, fallback) {
  return process.env[name] ? parsePort(process.env[name], name) : fallback;
}

function parsePort(value, label) {
  const port = Number(value);
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error(`${label} 必须是 1-65535 之间的端口号`);
  }
  return port;
}

function resolvePython(explicit) {
  const candidates = explicit
    ? [resolve(repoRoot, explicit), explicit]
    : [
        resolve(backendDir, ".venv", "Scripts", "python.exe"),
        resolve(backendDir, "venv", "Scripts", "python.exe"),
        resolve(repoRoot, ".venv", "Scripts", "python.exe"),
        "python",
        "python3",
      ];

  for (const candidate of candidates) {
    if (candidate.includes("\\") || candidate.includes("/")) {
      if (existsSync(candidate)) return candidate;
      continue;
    }
    const probe = spawnSync(candidate, ["--version"], { stdio: "ignore" });
    if (probe.status === 0) return candidate;
  }
  throw new Error("找不到 Python。请创建 backend/.venv，或通过 --python / AGENTHUB_PYTHON 指定解释器。");
}

function assertFile(path, message) {
  if (!existsSync(path)) throw new Error(message);
}

async function resolveAvailablePort(preferredPort, label, explicit) {
  const lastPort = explicit ? preferredPort : Math.min(preferredPort + 50, 65535);
  for (let port = preferredPort; port <= lastPort; port += 1) {
    if (await isPortAvailable(port)) {
      if (port !== preferredPort) console.log(`[dev] ${label}端口 ${preferredPort} 已占用，自动改用 ${port}`);
      return port;
    }
  }
  if (explicit) {
    throw new Error(`${label}端口 ${preferredPort} 已被占用，请选择其他端口。`);
  }
  throw new Error(`${label}在 ${preferredPort}-${lastPort} 范围内没有可用端口。`);
}

function isPortAvailable(port) {
  return new Promise((resolvePromise) => {
    const server = net.createServer();
    server.once("error", () => resolvePromise(false));
    server.once("listening", () => server.close(() => resolvePromise(true)));
    server.listen(port, "127.0.0.1");
  });
}

function startChild(command, args, config, label) {
  const child = spawn(command, args, {
    ...config,
    stdio: "inherit",
    windowsHide: false,
  });
  children.add(child);
  child.once("error", (error) => {
    console.error(`[dev] ${label} 启动失败：${error.message}`);
  });
  child.once("exit", () => children.delete(child));
  return child;
}

function quoteShellArg(value) {
  if (/^[A-Za-z0-9_./:\\-]+$/.test(value)) return value;
  return process.platform === "win32"
    ? `"${value.replaceAll('"', '""')}"`
    : `'${value.replaceAll("'", "'\\''")}'`;
}

function startTauri(overridePath, env) {
  const tauriCli = resolve(desktopDir, "node_modules", "@tauri-apps", "cli", "tauri.js");
  return startChild(process.execPath, [tauriCli, "dev", "--config", overridePath], {
    cwd: desktopDir,
    env,
  }, "Tauri");
}

async function waitForJson(url, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  let lastError = "服务尚未响应";
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(2_000) });
      if (response.ok) return await response.json();
      lastError = `HTTP ${response.status}`;
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error);
    }
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 400));
  }
  throw new Error(`等待后端超时：${url}（${lastError}）`);
}

function childExit(child, label) {
  return new Promise((resolvePromise, reject) => {
    child.once("error", reject);
    child.once("exit", (code, signal) => {
      if (!stopping) console.log(`[dev] ${label} 已退出（code=${code}, signal=${signal ?? "none"}）`);
      resolvePromise(code);
    });
  });
}

function installShutdownHandlers() {
  process.once("SIGINT", () => void shutdown(0));
  process.once("SIGTERM", () => void shutdown(0));
}

async function shutdown(code) {
  if (stopping) return;
  stopping = true;
  console.log("\n[dev] 正在停止开发环境...");
  for (const child of [...children]) terminateTree(child);
  await new Promise((resolvePromise) => setTimeout(resolvePromise, 250));
  process.exit(code);
}

function terminateTree(child) {
  if (!child.pid || child.exitCode !== null) return;
  if (process.platform === "win32") {
    spawnSync("taskkill", ["/PID", String(child.pid), "/T", "/F"], { stdio: "ignore", windowsHide: true });
  } else {
    child.kill("SIGTERM");
  }
}

function printHelp() {
  console.log(`AgentHub 桌面端统一开发启动器

用法：
  npm run dev
  npm run dev -- --backend-port 8190 --frontend-port 5176

选项：
  --backend-port <port>   FastAPI 端口，默认 8188
  --frontend-port <port>  Vite 端口，默认 5173
  --python <path>         指定 Python 解释器
  --check                 只检查依赖与端口，不启动服务
  --help                  显示帮助

对应环境变量：AGENTHUB_DEV_BACKEND_PORT、AGENTHUB_DEV_FRONTEND_PORT、AGENTHUB_PYTHON`);
}

function reportFatalError(error) {
  console.error(`[dev] ${error instanceof Error ? error.message : String(error)}`);
  process.exit(1);
}
