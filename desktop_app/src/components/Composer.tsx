import React, { useState, useRef, useEffect } from "react";
import { Send, Square, Sparkles, X, Paperclip, Trash2 } from "lucide-react";
import { ProjectFile } from "../types/agent";

interface ComposerProps {
  isStreaming: boolean;
  activeContextFile: ProjectFile | null;
  onSendMessage: (text: string) => void;
  onCancelGeneration: () => void;
  onClearActiveContextFile: () => void;
  onClearChat: () => void;
}

export const Composer: React.FC<ComposerProps> = ({
  isStreaming,
  activeContextFile,
  onSendMessage,
  onCancelGeneration,
  onClearActiveContextFile,
  onClearChat,
}) => {
  const [text, setText] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 160)}px`;
    }
  }, [text]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleSubmit = () => {
    if (!text.trim() || isStreaming) return;
    onSendMessage(text.trim());
    setText("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  return (
    <div className="p-3 bg-dark-900 border-t border-dark-800 flex-shrink-0 select-none">
      <div className="max-w-4xl mx-auto flex flex-col space-y-2">
        {/* Attached File Context Pill */}
        {activeContextFile && (
          <div className="flex items-center space-x-2 bg-dark-850 border border-dark-750 px-2 py-1 rounded w-fit text-xs text-dark-300">
            <Paperclip className="w-3 h-3 text-godot-blue" />
            <span className="font-mono text-[11px] text-dark-200">{activeContextFile.path}</span>
            <button
              onClick={onClearActiveContextFile}
              className="text-dark-500 hover:text-dark-200 p-0.5 rounded"
            >
              <X className="w-3 h-3" />
            </button>
          </div>
        )}

        {/* Input box and buttons */}
        <div className="relative rounded-lg bg-dark-950 border border-dark-800 focus-within:border-dark-700 shadow-inner flex items-end p-2 space-x-2">
          <textarea
            ref={textareaRef}
            rows={1}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask Godot AI agent to edit scripts, generate scenes, or repair errors..."
            className="flex-1 bg-transparent border-0 resize-none text-xs text-dark-100 placeholder-dark-600 focus:outline-none py-1.5 px-2 max-h-40 leading-relaxed font-sans"
          />

          <div className="flex items-center space-x-1.5 flex-shrink-0">
            <button
              onClick={onClearChat}
              className="p-1.5 text-dark-500 hover:text-dark-300 hover:bg-dark-850 rounded transition-colors"
              title="Clear Chat History"
            >
              <Trash2 className="w-4 h-4" />
            </button>

            {isStreaming ? (
              <button
                onClick={onCancelGeneration}
                className="flex items-center space-x-1.5 bg-rose-500/15 hover:bg-rose-500/25 text-rose-400 border border-rose-500/30 text-xs px-3 py-1.5 rounded font-medium transition-colors"
                title="Stop generation"
              >
                <Square className="w-3.5 h-3.5 fill-current" />
                <span>Stop</span>
              </button>
            ) : (
              <button
                onClick={handleSubmit}
                disabled={!text.trim()}
                className={`flex items-center space-x-1.5 text-xs px-3 py-1.5 rounded font-medium transition-colors ${
                  text.trim()
                    ? "bg-godot-blue hover:bg-godot-accent text-white shadow-sm"
                    : "bg-dark-800 text-dark-600 cursor-not-allowed"
                }`}
              >
                <Send className="w-3.5 h-3.5" />
                <span>Send</span>
              </button>
            )}
          </div>
        </div>

        <div className="flex justify-between items-center px-1 text-[10px] text-dark-500">
          <span>Press Enter to send, Shift+Enter for new line</span>
          <span>Inference: Qwen2.5-Coder-7B + Godot-LoRA</span>
        </div>
      </div>
    </div>
  );
};
