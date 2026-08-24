"""Fine-tuning script for training Policy-Aware Agent Models using Hugging Face TRL & KEOZ OpenEnv."""

import os
import argparse
from typing import Optional
from .trajectories import generate_dpo_dataset, save_dataset_jsonl


def main():
    parser = argparse.ArgumentParser(description="Fine-tune an LLM on KEOZ OpenEnv negotiation bounds using DPO / SFT.")
    parser.add_argument("--model_name", type=str, default="meta-llama/Llama-3.2-1B-Instruct", help="Base model identifier on Hugging Face Hub")
    parser.add_argument("--num_samples", type=int, default=200, help="Number of synthetic negotiation trajectories to generate")
    parser.add_argument("--output_dir", type=str, default="./keoz-finetuned-agent", help="Directory to save fine-tuned model checkpoint")
    parser.add_argument("--generate_only", action="store_true", help="Only generate synthetic OpenEnv DPO dataset without running training")
    args = parser.parse_args()

    print(f"🎮 Generating {args.num_samples} OpenEnv negotiation trajectories from KEOZ environment...")
    dataset = generate_dpo_dataset(num_samples=args.num_samples)
    dataset_file = "keoz_dpo_dataset.jsonl"
    save_dataset_jsonl(dataset, dataset_file)
    print(f"✅ Generated {len(dataset)} DPO trajectory pairs -> Saved to {dataset_file}")

    if args.generate_only:
        print("Dataset generation complete. Exiting (--generate_only).")
        return

    print(f"🚀 Preparing Hugging Face TRL DPOTrainer for base model: {args.model_name}")
    try:
        from datasets import load_dataset
        from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments
        from trl import DPOTrainer

        train_data = load_dataset("json", data_files=dataset_file, split="train")
        print(f"Loaded dataset: {train_data}")
        print("To launch full GPU fine-tuning, run with PyTorch / CUDA environment and Hugging Face token.")
    except ImportError:
        print("💡 Tip: Install `pip install trl datasets transformers accelerate peft` to execute GPU training.")


if __name__ == "__main__":
    main()
