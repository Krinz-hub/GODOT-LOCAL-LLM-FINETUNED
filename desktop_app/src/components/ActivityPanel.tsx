import React, { useState } from "react";
import {
  Terminal,
  CheckCircle2,
  AlertTriangle,
  History,
  RotateCcw,
  FileCode,
  Copy,
  Check,
  X,
} from "lucide-react";
import { FileHistoryRecord, GodotRunResult, GodotValidationResult, ProjectFile } from "../types/agent";

interface ActivityPanelProps {
  runResult: GodotRunResult | null;
  validationResult: GodotValidationResult | null;
  changeHistory: FileHistoryRecord[];
  previewFile: { file: ProjectFile; content: string } | null;
  onRollback: (changeId?: string) => void;
  onClosePreview: () => void;
}

export const ActivityPanel: React.FC<ActivityPanelProps> = ({
  runResult,
  validationResult,
  changeHistory,
  previewFile,
  onRollback,
  onClosePreview,
}) => {
  const [activeTab, setActiveTab] = useState<"output" | "validation" | "history" | "preview">(
    previewFile ? "preview" : "output"
  );
  const [copied, setCopied] = useState(false);

  // If previewFile updates, switch to preview tab
  React.useEffect(() => {
    if (previewFile) {
      setActiveTab("preview");
    }
  }, [previewFile]);

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <aside className="w-80 bg-dark-900 border-l border-dark-800 flex flex-col h-full select-none flex-shrink-0">
      {/* Tabs Header */}
      <div className="flex border-b border-dark-800 bg-dark-950/40 text-[11px]">
        <button
          onClick={() => setActiveTab("output")}
          className={`flex items-center space-x-1.5 px-3 py-2 border-b-2 font-medium transition-colors ${
            activeTab === "output"
              ? "border-godot-blue text-godot-light bg-dark-900"
              : "border-transparent text-dark-400 hover:text-dark-200"
          }`}
        >
          <Terminal className="w-3.5 h-3.5" />
          <span>Output</span>
        </button>

        <button
          onClick={() => setActiveTab("validation")}
          className={`flex items-center space-x-1.5 px-3 py-2 border-b-2 font-medium transition-colors ${
            activeTab === "validation"
              ? "border-emerald-500 text-emerald-400 bg-dark-900"
              : "border-transparent text-dark-400 hover:text-dark-200"
          }`}
        >
          <CheckCircle2 className="w-3.5 h-3.5" />
          <span>Validation</span>
        </button>

        <button
          onClick={() => setActiveTab("history")}
          className={`flex items-center space-x-1.5 px-3 py-2 border-b-2 font-medium transition-colors ${
            activeTab === "history"
              ? "border-amber-500 text-amber-400 bg-dark-900"
              : "border-transparent text-dark-400 hover:text-dark-200"
          }`}
        >
          <History className="w-3.5 h-3.5" />
          <span>Changes ({changeHistory.length})</span>
        </button>

        {previewFile && (
          <button
            onClick={() => setActiveTab("preview")}
            className={`flex items-center space-x-1 px-2.5 py-2 border-b-2 font-medium transition-colors ${
              activeTab === "preview"
                ? "border-purple-500 text-purple-400 bg-dark-900"
                : "border-transparent text-dark-400 hover:text-dark-200"
            }`}
          >
            <FileCode className="w-3.5 h-3.5" />
            <span className="truncate max-w-[50px]">{previewFile.file.name}</span>
          </button>
        )}
      </div>

      {/* Tab Contents */}
      <div className="flex-1 overflow-y-auto p-3 font-mono text-xs">
        {/* Tab 1: Godot Run Output */}
        {activeTab === "output" && (
          <div className="space-y-3">
            <div className="flex items-center justify-between text-dark-400 text-[11px] pb-1 border-b border-dark-800">
              <span>Godot Engine Execution</span>
              {runResult && (
                <span className={runResult.success ? "text-emerald-400" : "text-rose-400"}>
                  Exit Code: {runResult.exit_code} ({runResult.duration_seconds}s)
                </span>
              )}
            </div>

            {runResult ? (
              <div className="space-y-2">
                {runResult.stdout && (
                  <div>
                    <p className="text-[10px] text-dark-500 font-sans uppercase mb-1">STDOUT</p>
                    <pre className="p-2 rounded bg-dark-950 text-dark-200 whitespace-pre-wrap text-[11px] border border-dark-800 leading-relaxed max-h-60 overflow-y-auto">
                      {runResult.stdout}
                    </pre>
                  </div>
                )}
                {runResult.stderr && (
                  <div>
                    <p className="text-[10px] text-rose-400 font-sans uppercase mb-1">STDERR</p>
                    <pre className="p-2 rounded bg-rose-950/20 text-rose-300 whitespace-pre-wrap text-[11px] border border-rose-900/40 leading-relaxed max-h-60 overflow-y-auto">
                      {runResult.stderr}
                    </pre>
                  </div>
                )}
                <div className="text-[10px] text-dark-500 truncate" title={runResult.command}>
                  Command: {runResult.command}
                </div>
              </div>
            ) : (
              <div className="text-center py-12 text-dark-500 text-xs font-sans">
                No engine output yet. Click "Run Project" or "Validate" to execute Godot.
              </div>
            )}
          </div>
        )}

        {/* Tab 2: Validation Results */}
        {activeTab === "validation" && (
          <div className="space-y-3 font-sans">
            <div className="flex items-center justify-between text-dark-400 text-[11px] pb-1 border-b border-dark-800">
              <span>Headless Project Validation</span>
              {validationResult && (
                <span
                  className={`px-1.5 py-0.5 rounded text-[10px] uppercase font-mono ${
                    validationResult.valid
                      ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
                      : "bg-rose-500/10 text-rose-400 border border-rose-500/30"
                  }`}
                >
                  {validationResult.valid ? "Pass" : "Errors Detected"}
                </span>
              )}
            </div>

            {validationResult ? (
              <div className="space-y-3">
                {validationResult.errors.length > 0 && (
                  <div className="space-y-1">
                    <p className="text-xs font-semibold text-rose-400 flex items-center space-x-1">
                      <AlertTriangle className="w-3.5 h-3.5" />
                      <span>Script / Scene Errors ({validationResult.errors.length})</span>
                    </p>
                    {validationResult.errors.map((err, i) => (
                      <div
                        key={i}
                        className="p-2 rounded bg-rose-950/20 border border-rose-900/40 text-rose-300 font-mono text-[11px]"
                      >
                        {err}
                      </div>
                    ))}
                  </div>
                )}

                {validationResult.warnings.length > 0 && (
                  <div className="space-y-1">
                    <p className="text-xs font-semibold text-amber-400 flex items-center space-x-1">
                      <AlertTriangle className="w-3.5 h-3.5" />
                      <span>Warnings ({validationResult.warnings.length})</span>
                    </p>
                    {validationResult.warnings.map((warn, i) => (
                      <div
                        key={i}
                        className="p-2 rounded bg-amber-950/20 border border-amber-900/40 text-amber-300 font-mono text-[11px]"
                      >
                        {warn}
                      </div>
                    ))}
                  </div>
                )}

                {validationResult.valid && (
                  <div className="p-3 rounded bg-emerald-950/20 border border-emerald-900/40 text-emerald-300 text-xs flex items-center space-x-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0" />
                    <span>Project compiled cleanly without syntax or scene parse errors.</span>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-center py-12 text-dark-500 text-xs">
                Click "Validate" on the top bar to run headless project validation.
              </div>
            )}
          </div>
        )}

        {/* Tab 3: Recent Changes & Rollback */}
        {activeTab === "history" && (
          <div className="space-y-3 font-sans">
            <div className="flex items-center justify-between text-dark-400 text-[11px] pb-1 border-b border-dark-800">
              <span>Agent Modification History</span>
              {changeHistory.length > 0 && (
                <button
                  onClick={() => onRollback()}
                  className="flex items-center space-x-1 text-xs text-amber-400 hover:text-amber-300"
                >
                  <RotateCcw className="w-3 h-3" />
                  <span>Revert Last</span>
                </button>
              )}
            </div>

            {changeHistory.length === 0 ? (
              <div className="text-center py-12 text-dark-500 text-xs">
                No file changes made yet.
              </div>
            ) : (
              changeHistory.map((item) => (
                <div
                  key={item.id}
                  className="p-2.5 rounded bg-dark-950 border border-dark-800 space-y-1.5"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-xs text-dark-200 font-medium truncate max-w-[170px]">
                      {item.file_path}
                    </span>
                    <button
                      onClick={() => onRollback(item.id)}
                      className="text-[11px] text-amber-400 hover:text-amber-300 flex items-center space-x-1"
                      title="Revert this change"
                    >
                      <RotateCcw className="w-3 h-3" />
                      <span>Revert</span>
                    </button>
                  </div>

                  {item.diff && (
                    <div className="max-h-36 overflow-y-auto rounded bg-dark-900 p-1.5 font-mono text-[10px]">
                      {item.diff.split("\n").map((line, idx) => {
                        let cls = "text-dark-400";
                        if (line.startsWith("+") && !line.startsWith("+++")) cls = "text-emerald-400 bg-emerald-500/10";
                        if (line.startsWith("-") && !line.startsWith("---")) cls = "text-rose-400 bg-rose-500/10";
                        return (
                          <div key={idx} className={cls}>
                            {line}
                          </div>
                        );
                      })}
                    </div>
                  )}

                  <span className="text-[10px] text-dark-500 block">
                    {new Date(item.timestamp).toLocaleTimeString()}
                  </span>
                </div>
              ))
            )}
          </div>
        )}

        {/* Tab 4: File Preview */}
        {activeTab === "preview" && previewFile && (
          <div className="space-y-2 h-full flex flex-col">
            <div className="flex items-center justify-between text-dark-400 text-[11px] pb-1 border-b border-dark-800 flex-shrink-0">
              <span className="truncate font-mono">{previewFile.file.path}</span>
              <div className="flex items-center space-x-1">
                <button
                  onClick={() => copyToClipboard(previewFile.content)}
                  className="p-1 rounded hover:bg-dark-800 text-dark-400 hover:text-dark-200"
                  title="Copy file text"
                >
                  {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                </button>
                <button
                  onClick={onClosePreview}
                  className="p-1 rounded hover:bg-dark-800 text-dark-400 hover:text-dark-200"
                  title="Close Preview"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>

            <pre className="flex-1 p-2 rounded bg-dark-950 text-dark-200 whitespace-pre font-mono text-[11px] border border-dark-800 overflow-auto leading-relaxed">
              {previewFile.content}
            </pre>
          </div>
        )}
      </div>
    </aside>
  );
};
