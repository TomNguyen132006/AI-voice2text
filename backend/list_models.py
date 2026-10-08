"""List Token Factory models matching a keyword, with context length and price.

Listing models does not run any model, so it uses no tokens.
Usage: python list_models.py [keyword ...]   (default: nemotron parakeet)
"""
import os
import sys

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    base_url="https://api.tokenfactory.nebius.com/v1/",
    api_key=os.getenv("NEBIUS_API_KEY"),
)

keywords = [k.lower() for k in sys.argv[1:]] or ["nemotron", "parakeet"]

response = client.models.list(extra_query={"verbose": "true"})

for model in response.data:
    info = model.model_dump()
    if not any(k in info["id"].lower() for k in keywords):
        continue
    pricing = info.get("pricing") or {}
    print(
        f"{info['id']}\n"
        f"    context_length: {info.get('context_length')}\n"
        f"    price per token: prompt {pricing.get('prompt')} / completion {pricing.get('completion')}\n"
        f"    status: {info.get('status')}"
    )
