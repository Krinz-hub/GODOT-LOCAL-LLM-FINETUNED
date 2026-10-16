# pyrefly: ignore-errors
import os

# Ensure Python headers are discoverable by Triton JIT compiler
py_inc = os.path.expanduser("~/.local/usr/include/python3.12")
arch_inc = os.path.expanduser("~/.local/usr/include")
includes = f"{py_inc}:{arch_inc}"
for var in ("CPATH", "C_INCLUDE_PATH"):
    current = os.environ.get(var, "")
    os.environ[var] = f"{includes}:{current}" if current else includes

import inspect
import torch
from datasets import load_dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    TrainingArguments,
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from trl import SFTTrainer

# Gracefully support setup_chat_format across TRL versions
try:
    from trl import setup_chat_format
except ImportError:
    def setup_chat_format(model, tokenizer):
        # Qwen2.5-Coder-7B-Instruct natively provides a Jinja chat template in its tokenizer
        return model, tokenizer

# 1. Configuration
MODEL_ID = "Qwen/Qwen2.5-Coder-7B-Instruct"
DATA_PATH = (
    "./final_godot_sharegpt.jsonl"
    if os.path.exists("./final_godot_sharegpt.jsonl")
    else "./godot_training_workspace/data/train.jsonl"
)
OUTPUT_DIR = "./godot-agent-lora"

# 2. Tokenizer Setup
print(f"Initializing tokenizer for {MODEL_ID}...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
tokenizer.pad_token = tokenizer.eos_token

# 3. Load Model in 4-bit (QLoRA)
print("Loading Qwen2.5-Coder-7B onto Grace-Blackwell GPUs...")
bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_compute_dtype=torch.bfloat16,
)

model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID,
    device_map="auto",
    quantization_config=bnb_config,
    torch_dtype=torch.bfloat16,
)

model, tokenizer = setup_chat_format(model, tokenizer)
model = prepare_model_for_kbit_training(model)

# 4. LoRA Adapters Targeting Coding Layers
lora_config = LoraConfig(
    r=16,
    lora_alpha=32,
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM",
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
)
model = get_peft_model(model, lora_config)

# 5. Load the Cleaned Dataset
print(f"Loading the grounded Godot dataset from {DATA_PATH}...")
dataset = load_dataset("json", data_files={"train": DATA_PATH})

# 6. GB10 Optimized Training Arguments
training_args = TrainingArguments(
    output_dir=OUTPUT_DIR,
    per_device_train_batch_size=4,
    gradient_accumulation_steps=4,
    warmup_steps=100,
    num_train_epochs=3, # Target 3 passes over the 7,990 records
    learning_rate=2e-4,
    fp16=False,
    bf16=True, # Utilizing native GB10 bfloat16
    logging_steps=10,
    optim="adamw_8bit",
    save_strategy="steps",
    save_steps=100,
    save_total_limit=3,
    report_to="none"
)

# 7. Start Training
sft_params = inspect.signature(SFTTrainer.__init__).parameters
trainer_kwargs = {
    "model": model,
    "train_dataset": dataset["train"],
    "args": training_args,
}

if "processing_class" in sft_params:
    trainer_kwargs["processing_class"] = tokenizer
elif "tokenizer" in sft_params:
    trainer_kwargs["tokenizer"] = tokenizer

if "dataset_kwargs" in sft_params:
    trainer_kwargs["dataset_kwargs"] = {"skip_prepare_dataset": True}

trainer = SFTTrainer(**trainer_kwargs)

from transformers.trainer_utils import get_last_checkpoint
last_checkpoint = get_last_checkpoint(OUTPUT_DIR) if os.path.exists(OUTPUT_DIR) else None
if last_checkpoint:
    print(f"Resuming training from checkpoint: {last_checkpoint}")

print("Igniting DGX Training Run...")
trainer.train(resume_from_checkpoint=last_checkpoint)

# 8. Export Adapters
print(f"Saving adapters to {OUTPUT_DIR}/final_adapter...")
trainer.model.save_pretrained(f"{OUTPUT_DIR}/final_adapter")
tokenizer.save_pretrained(f"{OUTPUT_DIR}/final_adapter")
print(f"Training complete! Adapters saved to {OUTPUT_DIR}/final_adapter")
