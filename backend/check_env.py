"""Check that NEBIUS_API_KEY is loaded from .env. Never prints the key itself."""
import os
import sys

from dotenv import load_dotenv

# Searches for .env starting from this file's folder, then parent folders (repo root).
load_dotenv()

key = os.getenv("NEBIUS_API_KEY")

if not key:
    print("NEBIUS_API_KEY not found. Copy .env.example to .env and add your key.")
    sys.exit(1)

print(f"key loaded ({len(key)} characters)")
