import { app, BrowserWindow, dialog, ipcMain } from "electron";
import * as path from "path";
import * as fs from "fs";
import { spawn, ChildProcess } from "child_process";
import * as http from "http";

let mainWindow: BrowserWindow | null = null;
let backendProcess: ChildProcess | null = null;

const IS_DEV = process.env.NODE_ENV === "development" || !app.isPackaged;
const BACKEND_PORT = parseInt(process.env.AGENT_PORT || "8000", 10);
const REPO_ROOT = path.resolve(__dirname, "../../");
const VENV_PYTHON = path.join(REPO_ROOT, ".venv/bin/python");
const BACKEND_SCRIPT = path.join(__dirname, "../backend/agent_service.py");

function isPortOpen(port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const req = http.get(`http://127.0.0.1:${port}/health`, { timeout: 1000 }, (res) => {
      resolve(res.statusCode === 200);
    });
    req.on("error", () => resolve(false));
    req.on("timeout", () => {
      req.destroy();
      resolve(false);
    });
  });
}

async function ensureBackendRunning(): Promise<void> {
  const online = await isPortOpen(BACKEND_PORT);
  if (online) {
    console.log(`[Main] Python agent service is already running on port ${BACKEND_PORT}.`);
    return;
  }

  const pythonExec = fs.existsSync(VENV_PYTHON) ? VENV_PYTHON : "python3";
  console.log(`[Main] Launching agent service using: ${pythonExec} ${BACKEND_SCRIPT}...`);

  try {
    backendProcess = spawn(pythonExec, [BACKEND_SCRIPT], {
      env: {
        ...process.env,
        AGENT_PORT: String(BACKEND_PORT),
        PYTHONUNBUFFERED: "1",
      },
      stdio: "pipe",
    });

    backendProcess.stdout?.on("data", (data) => {
      console.log(`[Backend stdout]: ${data.toString().trim()}`);
    });

    backendProcess.stderr?.on("data", (data) => {
      console.error(`[Backend stderr]: ${data.toString().trim()}`);
    });

    backendProcess.on("exit", (code, signal) => {
      console.log(`[Backend] Process exited with code ${code}, signal ${signal}`);
      backendProcess = null;
    });

    // Wait up to 10 seconds for backend to become healthy
    const start = Date.now();
    while (Date.now() - start < 10000) {
      await new Promise((r) => setTimeout(r, 500));
      if (await isPortOpen(BACKEND_PORT)) {
        console.log(`[Main] Agent service successfully started on port ${BACKEND_PORT}.`);
        return;
      }
    }
  } catch (err) {
    console.error("[Main] Failed to spawn agent service:", err);
  }
}

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1380,
    height: 900,
    minWidth: 1024,
    minHeight: 700,
    backgroundColor: "#0b0d13",
    titleBarStyle: "hiddenInset",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  const distHtml = path.join(__dirname, "../dist/index.html");
  if (process.env.VITE_DEV_SERVER_URL) {
    mainWindow.loadURL(process.env.VITE_DEV_SERVER_URL);
  } else if (fs.existsSync(distHtml)) {
    mainWindow.loadFile(distHtml);
  } else {
    mainWindow.loadURL("http://localhost:5173");
  }

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

// IPC Handlers
ipcMain.handle("dialog:open-project", async () => {
  if (!mainWindow) return { canceled: true };
  const res = await dialog.showOpenDialog(mainWindow, {
    title: "Select Godot Project Directory",
    properties: ["openDirectory"],
  });

  if (res.canceled || res.filePaths.length === 0) {
    return { canceled: true };
  }

  const selectedPath = res.filePaths[0];
  const projectGodot = path.join(selectedPath, "project.godot");
  const isValid = fs.existsSync(projectGodot);

  return {
    canceled: false,
    path: selectedPath,
    isValidGodotProject: isValid,
    error: isValid ? null : "Selected directory does not contain a valid 'project.godot' file.",
  };
});

ipcMain.handle("system:get-backend-url", () => {
  return `http://127.0.0.1:${BACKEND_PORT}`;
});

app.whenReady().then(async () => {
  await ensureBackendRunning();
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", () => {
  if (backendProcess) {
    console.log("[Main] Terminating background Python agent process...");
    backendProcess.kill("SIGTERM");
  }
});
