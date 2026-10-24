import React, { useState, useEffect, useCallback } from "react";
import { TopBar } from "./components/TopBar";
import { LeftSidebar } from "./components/LeftSidebar";
import { ChatArea } from "./components/ChatArea";
import { Composer } from "./components/Composer";
import { ActivityPanel } from "./components/ActivityPanel";
import { ModelConfigModal } from "./components/ModelConfigModal";
import { agentAPI } from "./services/api";
import {
  ChatMessage,
  FileHistoryRecord,
  GodotAction,
  GodotRunResult,
  GodotValidationResult,
  ModelInfo,
  ProjectFile,
  ProjectInfo,
} from "./types/agent";

export const App: React.FC = () => {
  const [project, setProject] = useState<ProjectInfo | null>(null);
  const [files, setFiles] = useState<ProjectFile[]>([]);
  const [model, setModel] = useState<ModelInfo | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [isRunningGodot, setIsRunningGodot] = useState(false);
  const [isValidating, setIsValidating] = useState(false);
  const [isLoadingFiles, setIsLoadingFiles] = useState(false);
  const [activeContextFile, setActiveContextFile] = useState<ProjectFile | null>(null);
  const [previewFile, setPreviewFile] = useState<{ file: ProjectFile; content: string } | null>(null);
  const [runResult, setRunResult] = useState<GodotRunResult | null>(null);
  const [validationResult, setValidationResult] = useState<GodotValidationResult | null>(null);
  const [changeHistory, setChangeHistory] = useState<FileHistoryRecord[]>([]);
  const [isModelConfigOpen, setIsModelConfigOpen] = useState(false);

  // Poll system health and project status
  const refreshStatus = useCallback(async () => {
    try {
      const health = await agentAPI.getHealth();
      setModel(health.model);

      // Detect if project changed or was registered by Godot plugin
      if (
        health.project.connected &&
        (!project?.connected || health.project.project_path !== project.project_path)
      ) {
        setProject(health.project);
        loadProjectFiles();
      } else if (!health.project.connected && project?.connected) {
        setProject(null);
        setFiles([]);
      }
    } catch (err) {
      // Backend offline or starting up
    }
  }, [project]);

  const loadProjectFiles = async () => {
    setIsLoadingFiles(true);
    try {
      const res = await agentAPI.listProjectFiles();
      setFiles(res.files);
      const hist = await agentAPI.getHistory();
      setChangeHistory(hist.history);
    } catch (err) {
      console.error("Failed to load files:", err);
    } finally {
      setIsLoadingFiles(false);
    }
  };

  useEffect(() => {
    refreshStatus();
    const interval = setInterval(refreshStatus, 3500);
    return () => clearInterval(interval);
  }, [refreshStatus]);

  // Open / Switch Project Directory
  const handleOpenFolder = async () => {
    if (window.electronAPI) {
      const res = await window.electronAPI.openProjectDialog();
      if (!res.canceled && res.path) {
        if (!res.isValidGodotProject) {
          alert("Selected directory does not contain 'project.godot'!");
          return;
        }
        try {
          const selectRes = await agentAPI.selectProject(res.path);
          setProject(selectRes.project);
          await loadProjectFiles();
        } catch (e: any) {
          alert(`Error opening project: ${e.message}`);
        }
      }
    } else {
      // Fallback for browser preview / headless test
      const customPath = prompt(
        "Enter absolute path to Godot project directory:",
        "/home/piet/Documents/dataset/2d_platformer/platformer"
      );
      if (customPath) {
        try {
          const selectRes = await agentAPI.selectProject(customPath);
          setProject(selectRes.project);
          await loadProjectFiles();
        } catch (e: any) {
          alert(`Error opening project: ${e.message}`);
        }
      }
    }
  };

  // Select File in Sidebar
  const handleSelectFile = async (file: ProjectFile) => {
    try {
      const res = await agentAPI.readProjectFile(file.path);
      setPreviewFile({ file, content: res.content });
      setActiveContextFile(file);
    } catch (e: any) {
      alert(`Could not read file: ${e.message}`);
    }
  };

  // Send Chat / Task to Agent
  const handleSendMessage = async (text: string) => {
    const userMsgId = `user_${Date.now()}`;
    const assistantMsgId = `asst_${Date.now()}`;

    setMessages((prev) => [
      ...prev,
      { id: userMsgId, role: "user", content: text, timestamp: Date.now() },
      {
        id: assistantMsgId,
        role: "assistant",
        content: "",
        timestamp: Date.now(),
        isStreaming: true,
      },
    ]);

    setIsStreaming(true);

    let contextText = "";
    if (activeContextFile && previewFile) {
      contextText = `Active File (${activeContextFile.path}):\n\`\`\`gdscript\n${previewFile.content}\n\`\`\``;
    }

    await agentAPI.streamChat(text, {
      context: contextText,
      onToken: (token) => {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsgId ? { ...m, content: m.content + token } : m
          )
        );
      },
      onAction: (action) => {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsgId ? { ...m, action, isStreaming: false } : m
          )
        );
      },
      onError: (err) => {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsgId ? { ...m, error: err, isStreaming: false } : m
          )
        );
        setIsStreaming(false);
      },
      onDone: () => {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsgId ? { ...m, isStreaming: false } : m
          )
        );
        setIsStreaming(false);
      },
    });
  };

  const handleCancelGeneration = async () => {
    await agentAPI.cancelGeneration();
    setIsStreaming(false);
  };

  // Approve & Apply Agent Action to Godot Project
  const handleApproveAction = async (msgId: string, action: GodotAction) => {
    try {
      const execResult = await agentAPI.executeAction(action);
      setMessages((prev) =>
        prev.map((m) => (m.id === msgId ? { ...m, execution: execResult } : m))
      );
      // Refresh files and history
      await loadProjectFiles();
    } catch (e: any) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === msgId ? { ...m, execution: { success: false, error: e.message } } : m
        )
      );
    }
  };

  const handleRejectAction = (msgId: string) => {
    setMessages((prev) =>
      prev.map((m) =>
        m.id === msgId ? { ...m, action: undefined, error: "Action dismissed by user." } : m
      )
    );
  };

  // Godot Execution Controls
  const handleRunGodot = async () => {
    if (!project?.connected) return;
    setIsRunningGodot(true);
    try {
      const res = await agentAPI.runGodot({ headless: true, timeout: 25 });
      setRunResult(res);
    } catch (e: any) {
      alert(`Godot execution failed: ${e.message}`);
    } finally {
      setIsRunningGodot(false);
    }
  };

  const handleStopGodot = () => {
    setIsRunningGodot(false);
  };

  const handleValidateGodot = async () => {
    if (!project?.connected) return;
    setIsValidating(true);
    try {
      const res = await agentAPI.validateProject();
      setValidationResult(res);
    } catch (e: any) {
      alert(`Validation check failed: ${e.message}`);
    } finally {
      setIsValidating(false);
    }
  };

  // Rollback Change
  const handleRollback = async (changeId?: string) => {
    if (!confirm("Revert this agent file edit?")) return;
    try {
      await agentAPI.rollbackChange(changeId);
      await loadProjectFiles();
      alert("Change reverted successfully.");
    } catch (e: any) {
      alert(`Rollback failed: ${e.message}`);
    }
  };

  // Model Load / Unload
  const handleLoadModel = async (params: {
    base_model: string;
    adapter: string;
    load_in_4bit: boolean;
  }) => {
    try {
      await agentAPI.loadModel(params);
      await refreshStatus();
    } catch (e: any) {
      alert(`Failed to load model: ${e.message}`);
    }
  };

  const handleUnloadModel = async () => {
    try {
      await agentAPI.unloadModel();
      await refreshStatus();
    } catch (e: any) {
      alert(`Failed to unload model: ${e.message}`);
    }
  };

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-dark-950 text-dark-100">
      {/* Top Application Bar */}
      <TopBar
        project={project}
        model={model}
        isRunningGodot={isRunningGodot}
        isValidating={isValidating}
        onOpenFolder={handleOpenFolder}
        onRunGodot={handleRunGodot}
        onStopGodot={handleStopGodot}
        onValidateGodot={handleValidateGodot}
        onOpenModelConfig={() => setIsModelConfigOpen(true)}
        onRefreshStatus={refreshStatus}
      />

      {/* Main 3-Column IDE Layout */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left: Project Explorer */}
        <LeftSidebar
          project={project}
          files={files}
          selectedFile={previewFile?.file.path || null}
          isLoadingFiles={isLoadingFiles}
          onSelectFile={handleSelectFile}
          onOpenFolder={handleOpenFolder}
          onRefreshFiles={loadProjectFiles}
        />

        {/* Center: Agent Chat Area + Composer */}
        <main className="flex-1 flex flex-col h-full overflow-hidden bg-dark-950">
          <ChatArea
            messages={messages}
            isStreaming={isStreaming}
            onApproveAction={handleApproveAction}
            onRejectAction={handleRejectAction}
            onQuickPrompt={handleSendMessage}
          />
          <Composer
            isStreaming={isStreaming}
            activeContextFile={activeContextFile}
            onSendMessage={handleSendMessage}
            onCancelGeneration={handleCancelGeneration}
            onClearActiveContextFile={() => setActiveContextFile(null)}
            onClearChat={() => setMessages([])}
          />
        </main>

        {/* Right: Activity Panel (Godot Output, Validation, History, Preview) */}
        <ActivityPanel
          runResult={runResult}
          validationResult={validationResult}
          changeHistory={changeHistory}
          previewFile={previewFile}
          onRollback={handleRollback}
          onClosePreview={() => setPreviewFile(null)}
        />
      </div>

      {/* Model Config Modal */}
      <ModelConfigModal
        isOpen={isModelConfigOpen}
        model={model}
        backendUrl={agentAPI.getBaseUrl()}
        onClose={() => setIsModelConfigOpen(false)}
        onLoadModel={handleLoadModel}
        onUnloadModel={handleUnloadModel}
        onRefreshHealth={refreshStatus}
      />
    </div>
  );
};
