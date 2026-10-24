import React, { useEffect, useRef } from "react";
import {
  Sparkles,
  User,
  Bot,
  FileCode,
  Layers,
  CheckCircle,
  XCircle,
  ChevronDown,
  ChevronRight,
  Play,
  RotateCcw,
  Clock,
  AlertTriangle,
} from "lucide-react";
import { ChatMessage, GodotAction } from "../types/agent";

interface ChatAreaProps {
  messages: ChatMessage[];
  isStreaming: boolean;
  onApproveAction: (msgId: string, action: GodotAction) => void;
  onRejectAction: (msgId: string) => void;
  onQuickPrompt: (prompt: string) => void;
}

export const ChatArea: React.FC<ChatAreaProps> = ({
  messages,
  isStreaming,
  onApproveAction,
  onRejectAction,
  onQuickPrompt,
}) => {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isStreaming]);

  const quickPrompts = [
    {
      title: "Create Player Controller",
      prompt: "Create a CharacterBody2D player script with 2D platformer movement, jumping, and gravity.",
    },
    {
      title: "Add Coin Collectible",
      prompt: "Create an Area2D coin collectible script that emits a collected signal and frees itself on player collision.",
    },
    {
      title: "Validate Godot Project",
      prompt: "Inspect and validate our Godot project files, scenes, and scripts for errors or missing references.",
    },
  ];

  return (
    <div className="flex-1 flex flex-col h-full overflow-y-auto p-4 space-y-4">
      {messages.length === 0 ? (
        <div className="flex-1 flex flex-col items-center justify-center text-center p-6 max-w-lg mx-auto">
          <div className="w-12 h-12 rounded-xl bg-godot-dark border border-godot-blue/30 flex items-center justify-center text-godot-blue mb-4 shadow-lg shadow-godot-blue/5">
            <Sparkles className="w-6 h-6" />
          </div>
          <h2 className="text-base font-semibold text-dark-100 mb-1">
            Autonomous Godot 4 AI Agent
          </h2>
          <p className="text-xs text-dark-400 mb-6 leading-relaxed">
            Connected to our fine-tuned Qwen2.5-Coder model with native Godot 4 GDScript & TSCN tool-calling.
            Ask the agent to create scenes, modify scripts, or repair engine errors.
          </p>

          <div className="w-full space-y-2">
            <p className="text-[11px] font-semibold text-dark-500 uppercase tracking-wider text-left pl-1">
              Quick Suggestions
            </p>
            {quickPrompts.map((qp, idx) => (
              <button
                key={idx}
                onClick={() => onQuickPrompt(qp.prompt)}
                className="w-full text-left p-2.5 rounded bg-dark-900 hover:bg-dark-850 border border-dark-800 hover:border-dark-700 transition-colors group"
              >
                <p className="text-xs font-medium text-dark-200 group-hover:text-godot-light">
                  {qp.title}
                </p>
                <p className="text-[11px] text-dark-500 truncate">{qp.prompt}</p>
              </button>
            ))}
          </div>
        </div>
      ) : (
        messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex flex-col space-y-2 max-w-4xl mx-auto w-full ${
              msg.role === "user" ? "items-end" : "items-start"
            }`}
          >
            {/* Header info */}
            <div className="flex items-center space-x-2 text-[11px] text-dark-500 px-1">
              {msg.role === "user" ? (
                <>
                  <span>You</span>
                  <User className="w-3 h-3 text-dark-400" />
                </>
              ) : (
                <>
                  <Bot className="w-3.5 h-3.5 text-godot-blue" />
                  <span className="font-medium text-dark-300">Godot AI Agent</span>
                  <span className="text-[10px] text-dark-600 font-mono">
                    {new Date(msg.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                  </span>
                </>
              )}
            </div>

            {/* Message Bubble */}
            <div
              className={`rounded-lg p-3 text-xs leading-relaxed max-w-full ${
                msg.role === "user"
                  ? "bg-dark-800 text-dark-100 border border-dark-700"
                  : "bg-dark-900 text-dark-200 border border-dark-800 shadow-sm"
              }`}
            >
              {/* Collapsible Thought if present */}
              {msg.action?.thought && (
                <div className="mb-2.5 p-2 rounded bg-dark-950/60 border border-dark-800/80 text-[11px] text-dark-400">
                  <div className="font-semibold text-dark-300 flex items-center space-x-1 mb-1">
                    <Sparkles className="w-3 h-3 text-amber-400" />
                    <span>Agent Plan & Reasoning</span>
                  </div>
                  <p className="whitespace-pre-wrap">{msg.action.thought}</p>
                </div>
              )}

              {/* Text Content */}
              {msg.content && (
                <div className="whitespace-pre-wrap font-sans text-dark-200 mb-2">
                  {msg.content}
                  {msg.isStreaming && (
                    <span className="inline-block w-1.5 h-3.5 bg-godot-blue ml-1 animate-pulse" />
                  )}
                </div>
              )}

              {/* Proposed Action Card if present */}
              {msg.action && msg.action.action_type !== "chat_response" && (
                <div className="mt-2.5 rounded border border-dark-700 bg-dark-950 p-2.5 space-y-2">
                  <div className="flex items-center justify-between border-b border-dark-800 pb-1.5">
                    <div className="flex items-center space-x-1.5">
                      <span className="px-1.5 py-0.5 rounded text-[10px] font-mono uppercase bg-godot-blue/15 text-godot-light border border-godot-blue/30">
                        {msg.action.action_type}
                      </span>
                      {msg.action.parameters.file_path && (
                        <span className="text-[11px] font-mono text-dark-200 font-medium">
                          {msg.action.parameters.file_path}
                        </span>
                      )}
                    </div>

                    {msg.execution ? (
                      <span className="flex items-center space-x-1 text-[11px] text-emerald-400 font-medium">
                        <CheckCircle className="w-3.5 h-3.5" />
                        <span>Applied</span>
                      </span>
                    ) : (
                      <span className="flex items-center space-x-1 text-[11px] text-amber-400">
                        <Clock className="w-3.5 h-3.5" />
                        <span>Pending Approval</span>
                      </span>
                    )}
                  </div>

                  {/* Code preview if code is included */}
                  {msg.action.parameters.content && (
                    <div className="max-h-56 overflow-y-auto rounded bg-dark-900 p-2 font-mono text-[11px] text-dark-200 border border-dark-800/80">
                      <pre className="whitespace-pre">{msg.action.parameters.content}</pre>
                    </div>
                  )}

                  {/* Approval Actions */}
                  {!msg.execution && !msg.isStreaming && (
                    <div className="flex items-center space-x-2 pt-1">
                      <button
                        onClick={() => onApproveAction(msg.id, msg.action!)}
                        className="flex items-center space-x-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-xs px-3 py-1 rounded font-medium transition-colors shadow-sm"
                      >
                        <CheckCircle className="w-3.5 h-3.5" />
                        <span>Approve & Apply to Godot</span>
                      </button>
                      <button
                        onClick={() => onRejectAction(msg.id)}
                        className="flex items-center space-x-1.5 bg-dark-800 hover:bg-dark-750 text-dark-400 hover:text-dark-200 text-xs px-2.5 py-1 rounded border border-dark-700 transition-colors"
                      >
                        <XCircle className="w-3.5 h-3.5" />
                        <span>Dismiss</span>
                      </button>
                    </div>
                  )}

                  {/* Execution Result Log */}
                  {msg.execution && (
                    <div className="text-[11px] p-2 rounded bg-dark-900 border border-dark-800">
                      {msg.execution.success ? (
                        <p className="text-emerald-400">
                          ✓ Successfully updated file: {msg.execution.file_written} ({msg.execution.bytes_written} bytes)
                        </p>
                      ) : (
                        <p className="text-rose-400">
                          ✗ Error applying changes: {msg.execution.error}
                        </p>
                      )}
                    </div>
                  )}
                </div>
              )}

              {/* Error Display */}
              {msg.error && (
                <div className="mt-2 p-2 rounded bg-rose-500/10 border border-rose-500/30 text-rose-300 text-[11px] flex items-start space-x-2">
                  <AlertTriangle className="w-4 h-4 text-rose-400 flex-shrink-0 mt-0.5" />
                  <span>{msg.error}</span>
                </div>
              )}
            </div>
          </div>
        ))
      )}
      <div ref={bottomRef} />
    </div>
  );
};
