import {
  ChatMessage,
  FileHistoryRecord,
  GodotAction,
  GodotRunResult,
  GodotValidationResult,
  ModelInfo,
  ProjectFile,
  ProjectInfo,
} from "../types/agent";

const DEFAULT_BASE_URL = "http://127.0.0.1:8000";

export class AgentServiceAPI {
  private baseUrl: string = DEFAULT_BASE_URL;

  public setBaseUrl(url: string) {
    this.baseUrl = url.replace(/\/+$/, "");
  }

  public getBaseUrl(): string {
    return this.baseUrl;
  }

  // Health & Model
  public async getHealth(): Promise<{
    status: string;
    model: ModelInfo;
    project: ProjectInfo;
    auth_token_configured: boolean;
  }> {
    const res = await fetch(`${this.baseUrl}/api/health`);
    if (!res.ok) throw new Error(`Health check failed: ${res.statusText}`);
    return res.json();
  }

  public async getModelStatus(): Promise<ModelInfo> {
    const res = await fetch(`${this.baseUrl}/api/model/status`);
    if (!res.ok) throw new Error("Failed to get model status");
    return res.json();
  }

  public async loadModel(params?: {
    base_model?: string;
    adapter?: string;
    load_in_4bit?: boolean;
  }): Promise<{ success: boolean; message?: string; error?: string }> {
    const res = await fetch(`${this.baseUrl}/api/model/load`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params || {}),
    });
    return res.json();
  }

  public async unloadModel(): Promise<{ success: boolean; message?: string }> {
    const res = await fetch(`${this.baseUrl}/api/model/unload`, { method: "POST" });
    return res.json();
  }

  public async cancelGeneration(): Promise<void> {
    await fetch(`${this.baseUrl}/api/chat/cancel`, { method: "POST" });
  }

  // Project Management
  public async getProjectStatus(): Promise<ProjectInfo> {
    const res = await fetch(`${this.baseUrl}/api/project/status`);
    if (!res.ok) throw new Error("Failed to get project status");
    return res.json();
  }

  public async selectProject(projectPath: string): Promise<{ success: boolean; project: ProjectInfo }> {
    const res = await fetch(`${this.baseUrl}/api/project/select`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project_path: projectPath }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Failed to select project");
    }
    return res.json();
  }

  public async listProjectFiles(): Promise<{ total: number; files: ProjectFile[] }> {
    const res = await fetch(`${this.baseUrl}/api/project/files`);
    if (!res.ok) throw new Error("Failed to list project files");
    return res.json();
  }

  public async readProjectFile(filePath: string): Promise<{
    path: string;
    content: string;
    hash: string;
    mtime: number;
    lines: number;
  }> {
    const res = await fetch(`${this.baseUrl}/api/project/file?path=${encodeURIComponent(filePath)}`);
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Failed to read file");
    }
    return res.json();
  }

  public async editProjectFile(params: {
    file_path: string;
    content: string;
    expected_hash?: string;
    force?: boolean;
  }): Promise<{
    success: boolean;
    change_id: string;
    file_path: string;
    diff: string;
    bytes_written: number;
  }> {
    const res = await fetch(`${this.baseUrl}/api/project/edit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Failed to edit file");
    }
    return res.json();
  }

  public async rollbackChange(changeId?: string): Promise<{
    success: boolean;
    reverted_change: string;
    file_path: string;
  }> {
    const res = await fetch(`${this.baseUrl}/api/project/rollback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ change_id: changeId }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Failed to rollback change");
    }
    return res.json();
  }

  public async getHistory(): Promise<{ history: FileHistoryRecord[] }> {
    const res = await fetch(`${this.baseUrl}/api/project/history`);
    if (!res.ok) throw new Error("Failed to get change history");
    return res.json();
  }

  // Godot Execution & Validation
  public async runGodot(params?: {
    headless?: boolean;
    scene?: string;
    timeout?: number;
    custom_args?: string;
  }): Promise<GodotRunResult> {
    const res = await fetch(`${this.baseUrl}/api/godot/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params || {}),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Failed to execute Godot");
    }
    return res.json();
  }

  public async validateProject(): Promise<GodotValidationResult> {
    const res = await fetch(`${this.baseUrl}/api/godot/validate`, {
      method: "POST",
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Failed to validate project");
    }
    return res.json();
  }

  // Execute Agent Action Directly
  public async executeAction(action: GodotAction): Promise<any> {
    const res = await fetch(`${this.baseUrl}/api/agent/execute-action`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Failed to execute action");
    }
    return res.json();
  }

  // Streaming SSE Chat
  public async streamChat(
    prompt: string,
    options: {
      sessionId?: string;
      context?: string;
      onToken: (token: string) => void;
      onAction: (action: GodotAction) => void;
      onError: (err: string) => void;
      onDone: () => void;
    }
  ): Promise<void> {
    const response = await fetch(`${this.baseUrl}/api/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prompt,
        session_id: options.sessionId,
        context: options.context,
      }),
    });

    if (!response.ok) {
      const err = await response.text();
      options.onError(`Server error: ${err}`);
      options.onDone();
      return;
    }

    const reader = response.body?.getReader();
    if (!reader) {
      options.onError("No readable response body");
      options.onDone();
      return;
    }

    const decoder = new TextDecoder();
    let buffer = "";

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          const trimmed = line.trim();
          if (trimmed.startsWith("data: ")) {
            const dataStr = trimmed.slice(6);
            try {
              const payload = JSON.parse(dataStr);
              if (payload.type === "token") {
                options.onToken(payload.content);
              } else if (payload.type === "action") {
                options.onAction(payload.action);
              } else if (payload.type === "error") {
                options.onError(payload.content);
              } else if (payload.type === "cancelled") {
                options.onError("Generation cancelled by user.");
              } else if (payload.type === "done") {
                options.onDone();
                return;
              }
            } catch (e) {
              // Ignore malformed SSE chunk
            }
          }
        }
      }
    } catch (e: any) {
      options.onError(e.message || "Streaming connection failed");
    } finally {
      options.onDone();
    }
  }
}

export const agentAPI = new AgentServiceAPI();
