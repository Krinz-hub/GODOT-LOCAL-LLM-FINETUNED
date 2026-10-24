export type GodotActionType =
  | "create_scene"
  | "edit_scene"
  | "delete_scene"
  | "create_or_update_script"
  | "create_or_update_scene"
  | "read_file"
  | "list_project_files"
  | "run_project"
  | "chat_response";

export interface GodotActionParameters {
  file_path?: string;
  root_node_name?: string;
  root_node_type?: string;
  content?: string;
  script_path?: string;
  overwrite?: boolean;
  add_nodes?: Array<{ name: string; type: string; parent?: string; properties?: Record<string, any> }>;
  remove_nodes?: string[];
  attach_script?: { node: string; script_path: string };
  command?: string;
  message?: string;
}

export interface GodotAction {
  thought: string;
  action_type: GodotActionType;
  parameters: GodotActionParameters;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: number;
  action?: GodotAction;
  execution?: {
    success: boolean;
    action_executed?: string;
    file_written?: string;
    bytes_written?: number;
    error?: string;
    exit_code?: number;
    stdout?: string;
    stderr?: string;
  };
  isStreaming?: boolean;
  error?: string;
  diff?: string;
}

export interface ProjectInfo {
  connected: boolean;
  project_path: string | null;
  project_name: string | null;
  godot_version: string | null;
  godot_executable: string | null;
  connection_method: "editor_plugin" | "manual_folder" | null;
  last_seen?: number;
}

export interface ModelInfo {
  state: "unloaded" | "loading" | "ready" | "error";
  base_model: string;
  adapter: string;
  device: string;
  gpu_info: string;
  error_message: string | null;
  loaded_at: number | null;
}

export interface ProjectFile {
  path: string;
  name: string;
  kind: "script" | "scene" | "resource" | "config" | "asset" | "other";
  size: number;
  mtime: number;
}

export interface FileHistoryRecord {
  id: string;
  file_path: string;
  timestamp: number;
  diff: string;
  backup_file: string | null;
  previous_content: string;
}

export interface GodotValidationResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
  raw_output: string;
  exit_code?: number;
}

export interface GodotRunResult {
  success: boolean;
  exit_code: number;
  stdout: string;
  stderr: string;
  duration_seconds: number;
  command: string;
  error?: string;
}
