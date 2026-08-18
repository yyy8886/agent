const fs = require("node:fs");
const net = require("node:net");
const path = require("node:path");
const { spawn } = require("node:child_process");

function backendDirectory(app) {
  return app.isPackaged
    ? path.join(process.resourcesPath, "backend")
    : path.resolve(__dirname, "..", "..", "backend");
}

function pythonCandidates(backendDir, platform = process.platform) {
  const configured = process.env.MY_AGENT_PYTHON;
  const candidates = platform === "win32"
    ? [path.join(backendDir, ".venv", "Scripts", "python.exe"), "python"]
    : [
        path.join(backendDir, ".venv-linux", "bin", "python"),
        path.join(backendDir, ".venv", "bin", "python"),
        "python3",
        "python",
      ];
  return configured ? [configured, ...candidates] : candidates;
}

function packagedBackendExecutable(backendDir, platform = process.platform) {
  const name = platform === "win32" ? "my-agent-next-backend.exe" : "my-agent-next-backend";
  return path.join(backendDir, name);
}

function selectPython(backendDir, platform = process.platform) {
  for (const candidate of pythonCandidates(backendDir, platform)) {
    if (!path.isAbsolute(candidate) || fs.existsSync(candidate)) return candidate;
  }
  throw new Error("未找到 Python。请创建项目虚拟环境或设置 MY_AGENT_PYTHON。");
}

function availablePort(host = "127.0.0.1") {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on("error", reject);
    server.listen(0, host, () => {
      const { port } = server.address();
      server.close(() => resolve(port));
    });
  });
}

async function waitForServer(url, child, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) throw new Error(`FastAPI 已退出，退出码 ${child.exitCode}`);
    try {
      const response = await fetch(`${url}/api/health`);
      if (response.ok) return;
    } catch (_) {
      // The backend is still starting.
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error("等待 FastAPI 启动超时。");
}

async function startBackend(app, onLog = () => {}) {
  const cwd = backendDirectory(app);
  const port = await availablePort();
  const url = `http://127.0.0.1:${port}`;
  const packagedExecutable = packagedBackendExecutable(cwd);
  const executable = app.isPackaged ? packagedExecutable : selectPython(cwd);
  if (app.isPackaged && !fs.existsSync(packagedExecutable)) {
    throw new Error(`安装包缺少内置后端：${packagedExecutable}`);
  }
  const args = app.isPackaged
    ? []
    : ["-m", "uvicorn", "my_agent_next.app.web_server:app", "--host", "127.0.0.1", "--port", String(port)];
  const runtimeHome = path.join(app.getPath("userData"), "backend");
  fs.mkdirSync(runtimeHome, { recursive: true });
  const child = spawn(executable, args, {
    cwd,
    env: {
      ...process.env,
      MY_AGENT_DESKTOP: "1",
      MY_AGENT_HOME: runtimeHome,
      MY_AGENT_HOST: "127.0.0.1",
      MY_AGENT_PORT: String(port),
      PYTHONUNBUFFERED: "1",
    },
    detached: process.platform !== "win32",
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"],
  });
  child.stdout.on("data", (data) => onLog(data.toString()));
  child.stderr.on("data", (data) => onLog(data.toString()));
  child.on("error", (error) => onLog(`${error.message}\n`));
  await waitForServer(url, child, app.isPackaged ? 120000 : 30000);
  return { child, url, port, executable, cwd, runtimeHome };
}

function stopBackend(child) {
  if (!child || child.exitCode !== null) return;
  if (process.platform === "win32") {
    spawn("taskkill", ["/pid", String(child.pid), "/T", "/F"], { windowsHide: true, stdio: "ignore" });
  } else {
    try {
      process.kill(-child.pid, "SIGTERM");
    } catch (error) {
      if (error.code !== "ESRCH") throw error;
    }
  }
}

module.exports = {
  availablePort,
  backendDirectory,
  packagedBackendExecutable,
  pythonCandidates,
  selectPython,
  startBackend,
  stopBackend,
  waitForServer,
};
