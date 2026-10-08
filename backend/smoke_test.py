"""Send one short prompt to Nemotron Nano, Super and Ultra on Token Factory.

Prints one line per model: response time (ms) and token counts.
Each model is called exactly ONCE, with a small max_tokens, to save credit.
Model IDs come from list_models.py (GET /v1/models).
Usage: python smoke_test.py [nano super ultra]   (default: all three)
"""
import os
import sys
import time

from dotenv import load_dotenv
from openai import OpenAI

# Windows terminals may not print some Unicode characters; replace instead of crashing.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()

MODELS = {
    "nano": "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
    "super": "nvidia/nemotron-3-super-120b-a12b",
    "ultra": "nvidia/Nemotron-3-Ultra-550b-a55b",
}
PROMPT = "In one short sentence: what does a speech-to-text model do?"
MAX_TOKENS = 300

client = OpenAI(
    base_url="https://api.tokenfactory.nebius.com/v1/",
    api_key=os.getenv("NEBIUS_API_KEY"),
)

selected = sys.argv[1:] or list(MODELS)

for name in selected:
    model_id = MODELS[name]
    start = time.perf_counter()
    try:
        response = client.chat.completions.create(
            model=model_id,
            messages=[{"role": "user", "content": PROMPT}],
            max_tokens=MAX_TOKENS,
        )
    except Exception as error:
        print(f"{name:<6} {model_id} | ERROR: {error}")
        continue
    ms = round((time.perf_counter() - start) * 1000)

    usage = response.usage
    details = getattr(usage, "completion_tokens_details", None)
    reasoning = getattr(details, "reasoning_tokens", None) if details else None
    answer = (response.choices[0].message.content or "").strip().replace("\n", " ")

    print(
        f"{name:<6} {model_id} | {ms} ms | "
        f"prompt {usage.prompt_tokens} + completion {usage.completion_tokens} "
        f"= total {usage.total_tokens} tokens"
        + (f" (reasoning {reasoning})" if reasoning else "")
        + f" | finish: {response.choices[0].finish_reason}"
    )
    print(f"       answer: {answer[:120]}")
