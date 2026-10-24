import React, { useState } from "react";
import {
  X,
  Cpu,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  Power,
  HardDrive,
  Sliders,
  Sparkles,
} from "lucide-react";
import { ModelInfo } from "../types/agent";

interface ModelConfigModalProps {
  isOpen: boolean;
  model: ModelInfo | null;
  backendUrl: string;
  onClose: () => void;
  onLoadModel: (params: { base_model: string; adapter: string; load_in_4bit: boolean }) => void;
  onUnloadModel: () => void;
  onRefreshHealth: () => void;
}

export const ModelConfigModal: React.FC<ModelConfigModalProps> = ({
  isOpen,
  model,
  backendUrl,
  onClose,
  onLoadModel,
  onUnloadModel,
  onRefreshHealth,
}) => {
  if (!isOpen) return null;

  const [baseModel, setBaseModel] = useState(
    model?.base_model || "Qwen/Qwen2.5-Coder-7B-Instruct"
  );
  const [adapterPath, setAdapterPath] = useState(
    model?.adapter || "/home/piet/Documents/dataset/godot-agent-lora/final_adapter"
  );
  const [load4Bit, setLoad4Bit] = useState(true);

  const isReady = model?.state === "ready";
  const isLoading = model?.state === "loading";

  return (
    <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-dark-900 border border-dark-700 w-full max-w-xl rounded-xl shadow-2xl overflow-hidden flex flex-col animate-in fade-in zoom-in-95 duration-150">
        {/* Header */}
        <div className="p-4 border-b border-dark-800 flex items-center justify-between bg-dark-950/60">
          <div className="flex items-center space-x-2.5">
            <div className="p-1.5 rounded-lg bg-godot-dark border border-godot-blue/40 text-godot-blue">
              <Cpu className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-dark-100">Model Configuration</h3>
              <p className="text-[11px] text-dark-400">Fine-tuned Qwen2.5-Coder Godot Agent Model</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-md text-dark-400 hover:text-dark-200 hover:bg-dark-800 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="p-5 space-y-4 text-xs">
          {/* Status Banner */}
          <div className="p-3 rounded-lg bg-dark-950 border border-dark-800 flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div
                className={`w-3 h-3 rounded-full ${
                  isReady
                    ? "bg-emerald-400 shadow-[0_0_10px_rgba(52,211,153,0.8)]"
                    : isLoading
                    ? "bg-amber-400 animate-pulse"
                    : "bg-dark-600"
                }`}
              />
              <div>
                <p className="font-semibold text-dark-100 uppercase tracking-wide text-[11px]">
                  State: {model?.state || "unloaded"}
                </p>
                <p className="text-[11px] text-dark-400">
                  {model?.gpu_info || "No GPU loaded"} ({model?.device || "cpu"})
                </p>
              </div>
            </div>

            <div className="flex items-center space-x-2">
              <button
                onClick={onRefreshHealth}
                className="p-1.5 rounded hover:bg-dark-800 text-dark-400 hover:text-dark-200"
                title="Refresh Health"
              >
                <RefreshCw className="w-3.5 h-3.5" />
              </button>
              {isReady ? (
                <button
                  onClick={onUnloadModel}
                  className="flex items-center space-x-1.5 px-3 py-1.5 rounded bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/30 font-medium transition-colors"
                >
                  <Power className="w-3.5 h-3.5" />
                  <span>Unload</span>
                </button>
              ) : (
                <button
                  onClick={() =>
                    onLoadModel({
                      base_model: baseModel,
                      adapter: adapterPath,
                      load_in_4bit: load4Bit,
                    })
                  }
                  disabled={isLoading}
                  className="flex items-center space-x-1.5 px-3 py-1.5 rounded bg-godot-blue hover:bg-godot-accent text-white font-medium shadow-sm transition-colors disabled:opacity-50"
                >
                  <Power className="w-3.5 h-3.5" />
                  <span>{isLoading ? "Loading..." : "Load Model"}</span>
                </button>
              )}
            </div>
          </div>

          {model?.error_message && (
            <div className="p-3 rounded bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs">
              <span className="font-semibold">Error:</span> {model.error_message}
            </div>
          )}

          {/* Form Fields */}
          <div className="space-y-3">
            <div>
              <label className="block text-[11px] font-medium text-dark-300 mb-1">
                Base Model Name or Path
              </label>
              <input
                type="text"
                value={baseModel}
                onChange={(e) => setBaseModel(e.target.value)}
                disabled={isReady || isLoading}
                className="w-full bg-dark-950 border border-dark-800 focus:border-dark-700 text-xs rounded px-3 py-2 text-dark-100 font-mono focus:outline-none disabled:opacity-50"
              />
            </div>

            <div>
              <label className="block text-[11px] font-medium text-dark-300 mb-1">
                Fine-Tuned Godot LoRA Adapter Path
              </label>
              <input
                type="text"
                value={adapterPath}
                onChange={(e) => setAdapterPath(e.target.value)}
                disabled={isReady || isLoading}
                className="w-full bg-dark-950 border border-dark-800 focus:border-dark-700 text-xs rounded px-3 py-2 text-dark-100 font-mono focus:outline-none disabled:opacity-50"
              />
            </div>

            <div>
              <label className="block text-[11px] font-medium text-dark-300 mb-1">
                Inference Backend Address
              </label>
              <input
                type="text"
                value={backendUrl}
                disabled
                className="w-full bg-dark-950/60 border border-dark-800 text-xs rounded px-3 py-2 text-dark-400 font-mono cursor-not-allowed"
              />
            </div>

            <div className="flex items-center space-x-2 pt-1">
              <input
                type="checkbox"
                id="quant4bit"
                checked={load4Bit}
                onChange={(e) => setLoad4Bit(e.target.checked)}
                disabled={isReady || isLoading}
                className="rounded border-dark-700 bg-dark-950 text-godot-blue focus:ring-0"
              />
              <label htmlFor="quant4bit" className="text-dark-300 select-none cursor-pointer">
                Load in 4-bit NormalFloat (NF4 with double quantization) for optimal VRAM efficiency
              </label>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-dark-800 bg-dark-950/40 flex justify-between items-center text-[11px] text-dark-500">
          <span>PEFT LoRA v0.21.2 • BitsAndBytes 4-bit</span>
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded bg-dark-800 hover:bg-dark-750 text-dark-200 border border-dark-700 transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
