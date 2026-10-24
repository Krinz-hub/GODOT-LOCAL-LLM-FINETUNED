import { contextBridge, ipcRenderer } from "electron";

export interface IElectronAPI {
  openProjectDialog: () => Promise<{
    canceled: boolean;
    path?: string;
    isValidGodotProject?: boolean;
    error?: string | null;
  }>;
  getBackendUrl: () => Promise<string>;
}

const api: IElectronAPI = {
  openProjectDialog: () => ipcRenderer.invoke("dialog:open-project"),
  getBackendUrl: () => ipcRenderer.invoke("system:get-backend-url"),
};

contextBridge.exposeInMainWorld("electronAPI", api);

declare global {
  interface Window {
    electronAPI?: IElectronAPI;
  }
}
