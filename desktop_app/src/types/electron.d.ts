export interface IElectronAPI {
  openProjectDialog: () => Promise<{
    canceled: boolean;
    path?: string;
    isValidGodotProject?: boolean;
    error?: string | null;
  }>;
  getBackendUrl: () => Promise<string>;
}

declare global {
  interface Window {
    electronAPI?: IElectronAPI;
  }
}
