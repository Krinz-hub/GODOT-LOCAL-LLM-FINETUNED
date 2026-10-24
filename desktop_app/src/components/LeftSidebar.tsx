import React, { useState } from "react";
import {
  FolderOpen,
  FolderTree,
  FileCode,
  Layers,
  FileBox,
  FileText,
  Search,
  RefreshCw,
  Plus,
  Radio,
  File,
} from "lucide-react";
import { ProjectFile, ProjectInfo } from "../types/agent";

interface LeftSidebarProps {
  project: ProjectInfo | null;
  files: ProjectFile[];
  selectedFile: string | null;
  isLoadingFiles: boolean;
  onSelectFile: (file: ProjectFile) => void;
  onOpenFolder: () => void;
  onRefreshFiles: () => void;
}

export const LeftSidebar: React.FC<LeftSidebarProps> = ({
  project,
  files,
  selectedFile,
  isLoadingFiles,
  onSelectFile,
  onOpenFolder,
  onRefreshFiles,
}) => {
  const [filterType, setFilterType] = useState<"all" | "scripts" | "scenes" | "resources">("all");
  const [searchQuery, setSearchQuery] = useState("");

  const filteredFiles = files.filter((f) => {
    // Filter by type
    if (filterType === "scripts" && f.kind !== "script") return false;
    if (filterType === "scenes" && f.kind !== "scene") return false;
    if (filterType === "resources" && f.kind !== "resource") return false;

    // Filter by search query
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      return f.path.toLowerCase().includes(q);
    }
    return true;
  });

  const getFileIcon = (kind: ProjectFile["kind"]) => {
    switch (kind) {
      case "script":
        return <FileCode className="w-3.5 h-3.5 text-blue-400 flex-shrink-0" />;
      case "scene":
        return <Layers className="w-3.5 h-3.5 text-purple-400 flex-shrink-0" />;
      case "resource":
        return <FileBox className="w-3.5 h-3.5 text-amber-400 flex-shrink-0" />;
      case "config":
        return <FileText className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />;
      default:
        return <File className="w-3.5 h-3.5 text-dark-400 flex-shrink-0" />;
    }
  };

  return (
    <aside className="w-64 bg-dark-900 border-r border-dark-800 flex flex-col h-full select-none flex-shrink-0">
      {/* Header / Project Connection */}
      <div className="p-3 border-b border-dark-800 flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <FolderTree className="w-4 h-4 text-dark-400" />
          <span className="text-xs font-semibold uppercase tracking-wider text-dark-300">
            Project Explorer
          </span>
        </div>
        <div className="flex items-center space-x-1">
          <button
            onClick={onRefreshFiles}
            disabled={!project?.connected || isLoadingFiles}
            className="p-1 rounded hover:bg-dark-800 text-dark-400 hover:text-dark-200 transition-colors disabled:opacity-40"
            title="Refresh file tree"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoadingFiles ? "animate-spin" : ""}`} />
          </button>
          <button
            onClick={onOpenFolder}
            className="p-1 rounded hover:bg-dark-800 text-dark-400 hover:text-dark-200 transition-colors"
            title="Open or Switch Project Folder"
          >
            <FolderOpen className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Disconnected State Banner */}
      {!project?.connected ? (
        <div className="p-4 flex-1 flex flex-col items-center justify-center text-center text-dark-400">
          <Radio className="w-8 h-8 text-dark-600 mb-2 animate-pulse" />
          <p className="text-xs font-medium text-dark-300 mb-1">No Project Connected</p>
          <p className="text-[11px] text-dark-500 mb-4 px-2">
            Open Godot editor with the connector plugin, or select a project directory manually.
          </p>
          <button
            onClick={onOpenFolder}
            className="w-full flex items-center justify-center space-x-2 bg-godot-blue/15 hover:bg-godot-blue/25 text-godot-light border border-godot-blue/40 text-xs py-1.5 px-3 rounded transition-colors"
          >
            <FolderOpen className="w-3.5 h-3.5" />
            <span>Select Folder</span>
          </button>
        </div>
      ) : (
        <>
          {/* Search Input */}
          <div className="p-2 border-b border-dark-800">
            <div className="relative">
              <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-dark-500" />
              <input
                type="text"
                placeholder="Search files..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full bg-dark-950 border border-dark-800 focus:border-dark-700 text-xs rounded pl-8 pr-2.5 py-1 text-dark-200 placeholder-dark-600 focus:outline-none"
              />
            </div>
          </div>

          {/* Quick Filter Tabs */}
          <div className="flex border-b border-dark-800 px-2 py-1.5 space-x-1 text-[11px]">
            <button
              onClick={() => setFilterType("all")}
              className={`px-2 py-0.5 rounded transition-colors ${
                filterType === "all"
                  ? "bg-dark-800 text-dark-100 font-medium"
                  : "text-dark-400 hover:text-dark-200"
              }`}
            >
              All ({files.length})
            </button>
            <button
              onClick={() => setFilterType("scripts")}
              className={`px-2 py-0.5 rounded transition-colors ${
                filterType === "scripts"
                  ? "bg-blue-500/15 text-blue-400 font-medium"
                  : "text-dark-400 hover:text-dark-200"
              }`}
            >
              Scripts
            </button>
            <button
              onClick={() => setFilterType("scenes")}
              className={`px-2 py-0.5 rounded transition-colors ${
                filterType === "scenes"
                  ? "bg-purple-500/15 text-purple-400 font-medium"
                  : "text-dark-400 hover:text-dark-200"
              }`}
            >
              Scenes
            </button>
          </div>

          {/* File List */}
          <div className="flex-1 overflow-y-auto p-1.5 space-y-0.5">
            {isLoadingFiles ? (
              <div className="p-4 text-center text-xs text-dark-500">
                <RefreshCw className="w-4 h-4 animate-spin mx-auto mb-1 text-dark-600" />
                Scanning project...
              </div>
            ) : filteredFiles.length === 0 ? (
              <div className="p-4 text-center text-xs text-dark-500">No matching files found.</div>
            ) : (
              filteredFiles.map((file) => {
                const isSelected = selectedFile === file.path;
                return (
                  <div
                    key={file.path}
                    onClick={() => onSelectFile(file)}
                    className={`flex items-center space-x-2 px-2 py-1 rounded cursor-pointer text-xs transition-colors ${
                      isSelected
                        ? "bg-dark-800 text-dark-100 font-medium border border-dark-700"
                        : "text-dark-300 hover:bg-dark-850 hover:text-dark-200"
                    }`}
                    title={file.path}
                  >
                    {getFileIcon(file.kind)}
                    <span className="truncate flex-1 font-mono text-[11px]">{file.path}</span>
                  </div>
                );
              })
            )}
          </div>

          {/* Footer Info */}
          <div className="p-2.5 border-t border-dark-800 text-[10px] text-dark-500 flex justify-between items-center bg-dark-950/40">
            <span>{files.length} project items</span>
            <span className="font-mono truncate max-w-[120px]">{project.godot_version}</span>
          </div>
        </>
      )}
    </aside>
  );
};
