from pathlib import Path
from typing import Dict, List
import torch
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BatchEncoding,
    BitsAndBytesConfig,
    PreTrainedTokenizerBase,
)
from peft import PeftModel

REPO_ROOT = Path(__file__).resolve().parents[2]
BASE = "Qwen/Qwen2.5-Coder-7B-Instruct"
ADAPTER = str(REPO_ROOT / "godot-agent-lora" / "final_adapter")

def main():
    quant_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    print("Loading tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(ADAPTER)
    if not isinstance(tokenizer, PreTrainedTokenizerBase):
        raise RuntimeError(f"Failed to load a valid tokenizer from {ADAPTER}")

    print("Loading base model in 4-bit...")
    base_model = AutoModelForCausalLM.from_pretrained(
        BASE,
        quantization_config=quant_config,
        dtype=torch.bfloat16,
        device_map="auto",
    )

    print("Attaching Godot adapter...")
    model = PeftModel.from_pretrained(
        base_model,
        ADAPTER,
    )
    model.eval()

    # Resolve EOS token ID: use tokenizer configured EOS or model generation_config fallback
    eos_token_id = tokenizer.eos_token_id
    if eos_token_id is None:
        gen_config = getattr(model, "generation_config", None)
        if gen_config is not None and getattr(gen_config, "eos_token_id", None) is not None:
            cfg_eos = gen_config.eos_token_id
            eos_token_id = cfg_eos[0] if isinstance(cfg_eos, list) else int(cfg_eos)
        else:
            raise ValueError("Neither tokenizer nor model has a configured eos_token_id.")

    prompt = """Create a complete Godot 4 GDScript player controller for a 2D platformer.

Requirements:
1. Extend CharacterBody2D.
2. Use typed GDScript variables and constants.
3. Implement horizontal movement using Input.get_axis().
4. Implement gravity and jumping, with jumping allowed only while on the floor.
5. Implement health with a maximum of 100.
6. Add a take_damage(amount: int) method that ignores invalid or non-positive damage and emits a health_changed signal.
7. Emit a died signal when health reaches zero, and prevent repeated death handling.
8. Implement a temporary invulnerability period after taking damage using a Timer or a safe timer-based approach.
9. Keep velocity handling compatible with Godot 4 CharacterBody2D.
10. Include all required signal declarations and initialization.
11. Do not use Godot 3 syntax or redeclare built-in CharacterBody2D properties.
12. Return only the complete script, without Markdown fences or explanations.

Make the script internally consistent and ready to attach to a CharacterBody2D node. Clearly identify any assumptions in code comments."""

    messages: List[Dict[str, str]] = [
        {
            "role": "system",
            "content": "You are an expert Godot 4 game development assistant.",
        },
        {"role": "user", "content": prompt},
    ]

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
        raise TypeError(f"Expected input_ids to be a torch.Tensor, but got {type(raw_input_ids).__name__}")

    # Set input_len before generation
    input_len: int = raw_input_ids.shape[-1]

    target_device = getattr(model, "device", torch.device("cuda" if torch.cuda.is_available() else "cpu"))
    if isinstance(raw_inputs, BatchEncoding):
        inputs: BatchEncoding = raw_inputs.to(target_device)
    else:
        inputs = BatchEncoding({k: v.to(target_device) if isinstance(v, torch.Tensor) else v for k, v in raw_inputs.items()})

    print("\nGenerating response...\n")
    with torch.inference_mode():
        output = model.generate(
            **inputs,
            max_new_tokens=700,
            do_sample=False,
            repetition_penalty=1.05,
            pad_token_id=eos_token_id,
        )

    if not isinstance(output, torch.Tensor):
        raise TypeError(f"Expected model.generate to return a torch.Tensor, got {type(output).__name__}")

    new_tokens: torch.Tensor = output[0, input_len:]
    print(tokenizer.decode(new_tokens, skip_special_tokens=True))

    del model, base_model
    torch.cuda.empty_cache()


if __name__ == "__main__":
    main()
