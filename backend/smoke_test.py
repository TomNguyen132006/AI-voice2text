"""Send one short prompt to Nemotron Nano, Super and Ultra on Token Factory, via llm.call_model.

Prints one line per model: response time (ms) and token counts. Every attempt is also
written to the call log (see llm.py). Each model is called ONCE, with a small max_tokens.
Model IDs come from llm_config.py.
Usage: python smoke_test.py [nano super ultra]   (default: all three)
"""
import sys

from dotenv import load_dotenv

# Windows terminals may not print some Unicode characters; replace instead of crashing.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()

import llm
import llm_config

PROMPT = "In one short sentence: what does a speech-to-text model do?"
MAX_TOKENS = 300

selected = sys.argv[1:] or list(llm_config.ROLES)

for role in selected:
    model_id = llm_config.get_role(role).model_id
    try:
        result = llm.call_model(
            role,
            [{"role": "user", "content": PROMPT}],
            job_id="smoke_test",
            stage="smoke_test",
            max_tokens=MAX_TOKENS,
        )
    except llm.LLMError as error:
        print(f"{role:<6} {model_id} | ERROR: {error}")
        continue

    print(
        f"{role:<6} {model_id} | {result.latency_ms} ms | "
        f"prompt {result.prompt_tokens} + completion {result.completion_tokens}"
        + (f" (of which reasoning {result.reasoning_tokens})" if result.reasoning_tokens else "")
        + f" | finish: {result.finish_reason}"
        + (" | TRUNCATED" if result.truncated else "")
        + f" | est ${result.est_cost_usd:.6f}"
    )
    print(f"       answer: {result.text.strip().replace(chr(10), ' ')[:120]}")

print()
print(llm.format_summary(llm.summarize_log()))
