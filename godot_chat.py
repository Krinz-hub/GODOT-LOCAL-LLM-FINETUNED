from pathlib import Path
from typing import Any, Dict, List, Optional
import torch
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BatchEncoding,
    BitsAndBytesConfig,
    PreTrainedTokenizerBase,
)
from peft import PeftModel

import os
import re

REPO_ROOT = Path(__file__).resolve().parent
BASE_MODEL = "Qwen/Qwen2.5-Coder-7B-Instruct"
ADAPTER_PATH = str(REPO_ROOT / "godot-agent-lora" / "final_adapter")
DEFAULT_PROJECT = Path("/home/piet/Documents/godot/game")

# Discover existing project files for grounded context
project_files: List[str] = []
if DEFAULT_PROJECT.exists():
    for root, dirs, filenames in os.walk(DEFAULT_PROJECT):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for fn in filenames:
            if fn.endswith((".gd", ".tscn", ".godot", ".tres")):
                project_files.append(str(Path(root, fn).relative_to(DEFAULT_PROJECT)))

files_ctx = ", ".join(sorted(project_files)) if project_files else "Empty project"

SYSTEM_PROMPT = f"""You are an autonomous Godot AI game developer and coding assistant.
You are actively modifying the user's Godot project at: {DEFAULT_PROJECT}
Existing project files: {files_ctx}

Guidelines:
1. Whenever the user asks to add or change features, update or extend the existing project files (such as scripts/player.gd, scripts/coin.gd, scripts/main.gd).
2. For each code file, clearly specify the file path right before the code block (e.g. 'Here is scripts/player.gd:' followed by ```gdscript ... ```).
3. Always output complete, working GDScript without placeholders.
"""
MAX_CONTEXT_TOKENS = 16384


def extract_actions_or_code_blocks(text: str) -> List[Dict[str, Any]]:
    """Extracts either structured JSON actions or markdown code blocks with target filenames."""
    from godot_agent_server import extract_json_from_text
    actions: List[Dict[str, Any]] = []

    # 1. Try pure JSON action
    act = extract_json_from_text(text)
    if act.get("action_type") and act.get("action_type") != "chat_response":
        actions.append(act)
        return actions

    # 2. Extract markdown code blocks with filename hints
    parts = re.split(r"```(?:gdscript|tscn)?", text)
    for i in range(1, len(parts), 2):
        code = parts[i].strip()
        preceding = parts[i - 1].strip()
        m = re.findall(r"([a-zA-Z0-9_\-/\\]+\.(?:gd|tscn))", preceding)
        if not m:
            m = re.findall(r"([a-zA-Z0-9_\-/\\]+\.(?:gd|tscn))", code[:150])
        
        if not m and ("extends " in code or "func " in code):
            # Guess based on context or use standard script path
            if "player" in preceding.lower():
                m = ["scripts/player.gd"]
            elif "coin" in preceding.lower():
                m = ["scripts/coin.gd"]
            elif "obstacle" in preceding.lower():
                m = ["scripts/obstacle.gd"]
            elif "main" in preceding.lower():
                m = ["scripts/main.gd"]
            else:
                m = ["scripts/custom_script.gd"]

        if m and code:
            fn = m[-1]
            if fn.endswith(".gd") and not fn.startswith("scripts/"):
                fn = f"scripts/{fn}"
            elif fn.endswith(".tscn") and not fn.startswith("scenes/"):
                fn = f"scenes/{fn}"
            act_type = "create_scene" if fn.endswith(".tscn") else "create_or_update_script"
            actions.append({
                "thought": f"Extracted code block for {fn}",
                "action_type": act_type,
                "parameters": {
                    "file_path": fn,
                    "content": code,
                },
            })
    return actions


def check_server_online(port: int = 8000) -> bool:
    """Checks if Godot AI server is already running."""
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1.0) as r:
            return r.status == 200
    except Exception:
        return False


def run_server_chat(port: int = 8000, target_project: Optional[str] = None) -> None:
    """Interacts with the running Godot AI server without reloading the model into memory."""
    import urllib.request
    import json
    from godot_agent_server import execute_action, DEFAULT_PROJECT_PATH

    proj = target_project or DEFAULT_PROJECT_PATH or str(DEFAULT_PROJECT)
    print(f"\nConnected to Godot AI Server on http://localhost:{port}")
    print(f"Target Project: {proj}")
    print("Commands: /exit, /clear")
    print("-" * 55)

    session_id = f"term_{os.getpid()}"

    while True:
        try:
            prompt = input("\nYou: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting chat.")
            break

        if not prompt:
            continue

        if prompt.lower() in ("/exit", "/quit"):
            print("Goodbye!")
            break

        if prompt.lower() == "/clear":
            session_id = f"term_{os.getpid()}_{int(torch.cuda.Event().query() if torch.cuda.is_available() else 0)}"
            print("Conversation history reset.")
            continue

        print("\nGodot AI: ", end="", flush=True)

        try:
            # Query the /v1/act endpoint on the server
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/v1/act",
                data=json.dumps({
                    "prompt": prompt,
                    "project_path": proj,
                    "session_id": session_id,
                }).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))

            action = res_data.get("action", {})
            act_type = action.get("action_type", "")
            thought = action.get("thought", "")
            params = action.get("parameters", {})

            if thought:
                print(f"[Thought]: {thought}\n")

            if act_type == "chat_response":
                print(params.get("message", ""))
            else:
                target_fp = params.get("file_path", "")
                content = params.get("content", "")
                print(f"Action: {act_type} -> {target_fp}")
                if content:
                    preview_lines = content.split("\n")[:15]
                    print("```gdscript")
                    print("\n".join(preview_lines))
                    if len(content.split("\n")) > 15:
                        print("... (truncated preview)")
                    print("```")

                execution = res_data.get("execution", {})
                if execution.get("success"):
                    print(f"✓ Automatically applied to Godot: {execution.get('file_written', target_fp)}")
                else:
                    print(f"✗ Server execution result: {execution}")

        except Exception as e:
            print(f"\nCommunication error with server: {e}")


def main() -> None:
    print("=" * 55)
    print("  GODOT AI — Interactive Terminal")
    print("=" * 55)

    # Check if background agent server is already running on port 8000
    if check_server_online(8000):
        print("⚡ Active Godot AI server detected on http://localhost:8000!")
        try:
            ans = input("Connect via server for instant responses (no model reload)? [Y/n]: ").strip().lower()
            if ans in ("", "y", "yes"):
                run_server_chat(8000, target_project=str(DEFAULT_PROJECT) if DEFAULT_PROJECT else None)
                return
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            return

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable. Check your GPU setup.")

    print("GPU:", torch.cuda.get_device_name(0))
    print("\nLoading tokenizer...")

    tokenizer = AutoTokenizer.from_pretrained(ADAPTER_PATH)
    if not isinstance(tokenizer, PreTrainedTokenizerBase):
        raise RuntimeError(f"Failed to load a valid tokenizer from {ADAPTER_PATH}")

    print("Loading base model in 4-bit...")

    quant_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    base_model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        quantization_config=quant_config,
        dtype=torch.bfloat16,
        device_map="auto",
    )

    print("Attaching fine-tuned adapter...")

    model = PeftModel.from_pretrained(
        base_model,
        ADAPTER_PATH,
    )
    model.eval()

    # Safely resolve EOS and pad token IDs (support both <|im_end|> and <|endoftext|>)
    im_end_id = tokenizer.convert_tokens_to_ids("<|im_end|>")
    endoftext_id = tokenizer.convert_tokens_to_ids("<|endoftext|>")
    eos_token_ids: List[int] = []
    if isinstance(im_end_id, int) and im_end_id >= 0:
        eos_token_ids.append(im_end_id)
    if isinstance(endoftext_id, int) and endoftext_id >= 0 and endoftext_id != im_end_id:
        eos_token_ids.append(endoftext_id)
    if not eos_token_ids and tokenizer.eos_token_id is not None:
        eos_token_ids = [tokenizer.eos_token_id]
    if not eos_token_ids:
        eos_token_ids = [151645]

    pad_token_id = tokenizer.pad_token_id if tokenizer.pad_token_id is not None else eos_token_ids[0]

    print("\nModel loaded and ready.")
    print("Commands: /exit, /clear")
    print("-" * 55)

    messages: List[Dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]

    while True:
        try:
            prompt = input("\nYou: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting chat.")
            break

        if not prompt:
            continue

        if prompt.lower() in ("/exit", "/quit"):
            print("Goodbye!")
            break

        if prompt.lower() == "/clear":
            messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            print("Conversation history cleared.")
            continue

        messages.append({"role": "user", "content": prompt})

        # Trim conversation history if it exceeds token limit, preserving system prompt
        while len(messages) > 3:
            encoded_len = len(tokenizer.apply_chat_template(messages, tokenize=True))
            if encoded_len <= MAX_CONTEXT_TOKENS:
                break
            # Remove oldest turn (user + assistant pair after system)
            messages.pop(1)
            if len(messages) > 1 and messages[1].get("role") == "assistant":
                messages.pop(1)

        try:
            raw_inputs = tokenizer.apply_chat_template(
                messages,
                tokenize=True,
                add_generation_prompt=True,
                return_tensors="pt",
                return_dict=True,
            )

            if not isinstance(raw_inputs, (BatchEncoding, dict)) or "input_ids" not in raw_inputs:
                raise TypeError("apply_chat_template did not return a BatchEncoding/dict with 'input_ids'.")

            raw_input_ids = raw_inputs["input_ids"]
            if not isinstance(raw_input_ids, torch.Tensor):
                raise TypeError(f"Expected input_ids to be a torch.Tensor, got {type(raw_input_ids).__name__}")

            input_length: int = raw_input_ids.shape[-1]

            # Send inputs to the model's input embedding device.
            input_device = model.get_input_embeddings().weight.device
            if isinstance(raw_inputs, BatchEncoding):
                inputs: BatchEncoding = raw_inputs.to(input_device)
            else:
                inputs = BatchEncoding({k: v.to(input_device) if isinstance(v, torch.Tensor) else v for k, v in raw_inputs.items()})

            print("\nGodot AI: ", end="", flush=True)

            with torch.inference_mode():
                outputs = model.generate(
                    **inputs,
                    max_new_tokens=1200,
                    do_sample=True,
                    temperature=0.6,
                    top_p=0.9,
                    repetition_penalty=1.02,
                    pad_token_id=pad_token_id,
                    eos_token_id=eos_token_ids,
                )

            if not isinstance(outputs, torch.Tensor):
                raise TypeError(f"Expected model.generate output to be a torch.Tensor, got {type(outputs).__name__}")

            new_tokens: torch.Tensor = outputs[0, input_length:]
            raw_answer = tokenizer.decode(
                new_tokens,
                skip_special_tokens=True,
            )
            answer: str = raw_answer[0].strip() if isinstance(raw_answer, list) else raw_answer.strip()

            print(answer)

            # Auto-detect if model generated actions or code blocks and prompt to apply them
            from godot_agent_server import execute_action, DEFAULT_PROJECT_PATH
            detected_actions = extract_actions_or_code_blocks(answer)
            proj = DEFAULT_PROJECT_PATH or str(DEFAULT_PROJECT)

            for act in detected_actions:
                act_type = act.get("action_type", "")
                params = act.get("parameters", {})
                target_fp = params.get("file_path", "")
                print(f"\n⚡ [AI File Update Detected]: {target_fp} ({act_type})")
                try:
                    confirm = input(f"Apply {target_fp} to Godot project ({proj})? [Y/n]: ").strip().lower()
                    if confirm in ("", "y", "yes"):
                        res = execute_action(proj, act)
                        if res.get("success"):
                            print(f"✓ Successfully written to Godot: {res.get('file_written', target_fp)}")
                        else:
                            print(f"✗ Failed to apply: {res.get('error')}")
                    else:
                        print(f"Skipped applying {target_fp}.")
                except (KeyboardInterrupt, EOFError):
                    pass

            messages.append({
                "role": "assistant",
                "content": answer,
            })

        except Exception as error:
            # Remove the unanswered user message so it can be retried.
            messages.pop()
            print(f"\nGeneration error: {type(error).__name__}: {error}")
            print("You can try another prompt or type /exit.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Godot AI Interactive CLI")
    parser.add_argument("--project-path", default=None, help="Target Godot project path")
    cli_args = parser.parse_args()
    if cli_args.project_path:
        DEFAULT_PROJECT = Path(cli_args.project_path).resolve()
    main()
