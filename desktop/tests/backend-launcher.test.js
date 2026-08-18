const assert = require("node:assert/strict");
const path = require("node:path");
const test = require("node:test");

const {
  availablePort,
  backendDirectory,
  packagedBackendExecutable,
  pythonCandidates,
} = require("../src/backend-launcher");

test("development backend path points at the shared backend", () => {
  const result = backendDirectory({ isPackaged: false });
  assert.equal(path.basename(result), "backend");
  assert.equal(path.basename(path.dirname(result)), "agent");
});

test("python candidates are platform specific", () => {
  const win = pythonCandidates("C:\\project\\backend", "win32");
  const linux = pythonCandidates("/project/backend", "linux");
  assert.match(win[0], /Scripts[\\/]python\.exe$/);
  assert.match(linux[0], /\.venv-linux[\\/]bin[\\/]python$/);
});

test("packaged backend executable is platform specific", () => {
  assert.equal(
    path.basename(packagedBackendExecutable("C:\\app\\backend", "win32")),
    "my-agent-next-backend.exe",
  );
  assert.equal(
    path.basename(packagedBackendExecutable("/app/backend", "linux")),
    "my-agent-next-backend",
  );
});

test("availablePort returns a bindable ephemeral port", async () => {
  const port = await availablePort();
  assert.ok(Number.isInteger(port));
  assert.ok(port > 0 && port < 65536);
});
