const path = require("node:path");
const { app, BrowserWindow, dialog } = require("electron");
const { startBackend, stopBackend } = require("./backend-launcher");

let backend = null;
let mainWindow = null;

function createWindow(url) {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 920,
    minWidth: 1000,
    minHeight: 680,
    backgroundColor: "#0b0d12",
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  mainWindow.removeMenu();
  mainWindow.once("ready-to-show", () => {
    mainWindow.show();
    mainWindow.focus();
    mainWindow.webContents.focus();
  });
  mainWindow.webContents.setWindowOpenHandler(({ url: target }) => {
    require("electron").shell.openExternal(target);
    return { action: "deny" };
  });
  return mainWindow.loadURL(url);
}

app.whenReady().then(async () => {
  try {
    backend = await startBackend(app, (line) => process.stdout.write(`[backend] ${line}`));
    await createWindow(backend.url);
  } catch (error) {
    dialog.showErrorBox("My Agent Next 启动失败", error.message);
    app.quit();
  }
});

app.on("window-all-closed", () => app.quit());
app.on("before-quit", () => stopBackend(backend?.child));
