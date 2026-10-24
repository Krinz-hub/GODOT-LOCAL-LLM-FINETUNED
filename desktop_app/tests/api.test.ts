import { describe, it, expect, beforeEach, vi } from "vitest";
import { AgentServiceAPI } from "../src/services/api";

describe("AgentServiceAPI Client", () => {
  let api: AgentServiceAPI;

  beforeEach(() => {
    api = new AgentServiceAPI();
    api.setBaseUrl("http://127.0.0.1:8000");
  });

  it("initializes with default base url", () => {
    expect(api.getBaseUrl()).toBe("http://127.0.0.1:8000");
  });

  it("handles base url trimming trailing slashes", () => {
    api.setBaseUrl("http://localhost:8000///");
    expect(api.getBaseUrl()).toBe("http://localhost:8000");
  });

  it("successfully parses health endpoint mock", async () => {
    const mockHealth = {
      status: "online",
      model: {
        state: "ready",
        base_model: "Qwen/Qwen2.5-Coder-7B-Instruct",
        adapter: "godot-agent-lora/final_adapter",
        device: "cuda:0",
        gpu_info: "NVIDIA GB10",
        error_message: null,
        loaded_at: 1700000000,
      },
      project: {
        connected: true,
        project_path: "/home/piet/Documents/dataset/2d_platformer/platformer",
        project_name: "platformer",
        godot_version: "Godot 4.x",
        godot_executable: "/home/piet/.local/bin/godot4",
        connection_method: "editor_plugin",
      },
      auth_token_configured: true,
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockHealth,
    } as any);

    const result = await api.getHealth();
    expect(result.status).toBe("online");
    expect(result.model.state).toBe("ready");
    expect(result.project.connected).toBe(true);
    expect(result.project.project_name).toBe("platformer");
  });

  it("throws error when selecting invalid project", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      statusText: "Bad Request",
      json: async () => ({ detail: "Directory does not exist" }),
    } as any);

    await expect(api.selectProject("/invalid/path")).rejects.toThrow("Directory does not exist");
  });
});
