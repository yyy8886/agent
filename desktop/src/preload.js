const { contextBridge } = require("electron");

contextBridge.exposeInMainWorld("desktopApp", Object.freeze({
  platform: process.platform,
  desktop: true,
}));
