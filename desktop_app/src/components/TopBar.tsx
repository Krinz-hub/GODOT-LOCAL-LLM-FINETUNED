import React from "react";
import {
  Play,
  Square,
  CheckCircle2,
  AlertCircle,
  Cpu,
  FolderGit2,
  Settings2,
  Sparkles,
  RefreshCw,
  FolderOpen,
} from "lucide-react";
import { ModelInfo, ProjectInfo } from "../types/agent";

interface TopBarProps {
  project: ProjectInfo | null;
  model: ModelInfo | null;
  isRunningGodot: boolean;
  isValidating: boolean;
  onOpenFolder: () => void;
  onRunGodot: () => void;
  onStopGodot: () => void;
  onValidateGodot: () => void;
  onOpenModelConfig: () => void;
  onRefreshStatus: () => void;
}

export const TopBar: React.FC<TopBarProps> = ({
  project,
  model,
  isRunningGodot,
  isValidating,
  onOpenFolder,
  onRunGodot,
  onStopGodot,
  onValidateGodot,
  onOpenModelConfig,
  onRefreshStatus,
}) => {
  const isModelReady = model?.state === "ready";
  const isModelLoading = model?.state === "loading";

  return (
    <header className="h-12 bg-dark-900 border-b border-dark-800 flex items-center justify-between px-4 select-none flex-shrink-0 z-10">
      {/* Left: Branding & Connected Project */}
      <div className="flex items-center space-x-3">
        <div className="flex items-center space-x-2 text-godot-blue font-semibold text-sm tracking-wide">
          <div className="w-6 h-6 rounded bg-godot-dark flex items-center justify-center border border-godot-blue/40 shadow-sm">
            <Sparkles className="w-3.5 h-3.5 text-godot-blue" />
          </div>
          <span className="hidden sm:inline">GODOT AI</span>
        </div>

        <div className="h-4 w-px bg-dark-700" />

        {project?.connected ? (
          <div className="flex items-center space-x-2 group relative">
            <FolderGit2 className="w-4 h-4 text-emerald-400" />
            <span className="text-xs font-medium text-dark-100 max-w-[160px] truncate">
              {project.project_name || "Godot Project"}
            </span>
            <span
              className={`text-[10px] px-1.5 py-0.5 rounded font-mono uppercase tracking-wider ${
                project.connection_method === "editor_plugin"
                  ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
                  : "bg-blue-500/10 text-blue-400 border border-blue-500/30"
              }`}
            >
              {project.connection_method === "editor_plugin" ? "Editor Plugin" : "Local"}
            </span>

            {/* Hover Tooltip */}
            <div className="hidden group-hover:block absolute top-8 left-0 bg-dark-850 border border-dark-700 text-dark-200 text-xs px-2.5 py-1.5 rounded shadow-xl whitespace-nowrap z-50">
              <p className="font-semibold text-dark-100">{project.project_name}</p>
              <p className="text-[11px] text-dark-400 font-mono">{project.project_path}</p>
              <p className="text-[10px] text-dark-400 mt-1">
                Engine: {project.godot_version || "Unknown"}
              </p>
            </div>
          </div>
        ) : (
          <button
            onClick={onOpenFolder}
            className="flex items-center space-x-1.5 text-xs text-dark-400 hover:text-dark-200 hover:bg-dark-800 px-2 py-1 rounded transition-colors"
          >
            <FolderOpen className="w-3.5 h-3.5 text-amber-400" />
            <span>Select Godot Project</span>
          </button>
        )}
      </div>

      {/* Center: Godot Engine Actions */}
      <div className="flex items-center space-x-2">
        <button
          onClick={onValidateGodot}
          disabled={!project?.connected || isValidating}
          className={`flex items-center space-x-1.5 text-xs px-2.5 py-1 rounded border transition-all ${
            isValidating
              ? "bg-dark-800 border-dark-700 text-dark-400 cursor-not-allowed"
              : "bg-dark-850 hover:bg-dark-800 border-dark-700 hover:border-dark-600 text-dark-200"
          }`}
          title="Run Godot headless check to validate scenes and syntax"
        >
          {isValidating ? (
            <RefreshCw className="w-3.5 h-3.5 animate-spin text-amber-400" />
          ) : (
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
          )}
          <span>{isValidating ? "Validating..." : "Validate"}</span>
        </button>

        {isRunningGodot ? (
          <button
            onClick={onStopGodot}
            className="flex items-center space-x-1.5 text-xs px-2.5 py-1 rounded bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/30 transition-colors"
          >
            <Square className="w-3.5 h-3.5 fill-current" />
            <span>Stop Engine</span>
          </button>
        ) : (
          <button
            onClick={onRunGodot}
            disabled={!project?.connected}
            className={`flex items-center space-x-1.5 text-xs px-2.5 py-1 rounded border transition-colors ${
              project?.connected
                ? "bg-godot-blue/15 hover:bg-godot-blue/25 text-godot-light border-godot-blue/40"
                : "bg-dark-800 border-dark-700 text-dark-500 cursor-not-allowed"
            }`}
            title="Launch Godot project"
          >
            <Play className="w-3.5 h-3.5 fill-current" />
            <span>Run Project</span>
          </button>
        )}
      </div>

      {/* Right: Model Status & Config Modal Trigger */}
      <div className="flex items-center space-x-3">
        {/* Model Status Pill */}
        <div
          onClick={onOpenModelConfig}
          className="flex items-center space-x-2 bg-dark-850 hover:bg-dark-800 border border-dark-700 px-2.5 py-1 rounded cursor-pointer transition-colors"
          title="Click to view/change model configuration"
        >
          <Cpu className="w-3.5 h-3.5 text-dark-400" />
          <div className="flex items-center space-x-1.5">
            <span
              className={`w-2 h-2 rounded-full ${
                isModelReady
                  ? "bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.6)]"
                  : isModelLoading
                  ? "bg-amber-400 animate-pulse"
                  : "bg-dark-600"
              }`}
            />
            <span className="text-xs font-medium text-dark-200">
              {isModelReady
                ? "Qwen2.5-Coder + LoRA"
                : isModelLoading
                ? "Loading Model..."
                : "Model Unloaded"}
            </span>
          </div>
          {model?.device && (
            <span className="text-[10px] text-dark-400 font-mono hidden md:inline">
              ({model.device})
            </span>
          )}
        </div>

        <button
          onClick={onRefreshStatus}
          className="p-1.5 rounded hover:bg-dark-800 text-dark-400 hover:text-dark-200 transition-colors"
          title="Refresh system status"
        >
          <RefreshCw className="w-3.5 h-3.5" />
        </button>

        <button
          onClick={onOpenModelConfig}
          className="p-1.5 rounded hover:bg-dark-800 text-dark-400 hover:text-dark-200 transition-colors"
          title="Settings & Model Configuration"
        >
          <Settings2 className="w-4 h-4" />
        </button>
      </div>
    </header>
  );
};
