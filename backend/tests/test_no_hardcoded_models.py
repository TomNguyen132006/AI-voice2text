"""Model IDs live only in llm_config.py (S2-1). Case-insensitive: the 3 IDs use different capitalization."""
import re
from pathlib import Path

import llm_config

BACKEND = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".venv", "__pycache__", ".data", "tests"}
CONFIG_FILE = BACKEND / "llm_config.py"
# Nemotron on Token Factory, e.g. "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B". Parakeet (Hugging Face) is not a Token Factory model.
NEMOTRON_ID = re.compile(r"nvidia/[\w.\-]*nemotron", re.IGNORECASE)


def _python_files():
    for path in BACKEND.rglob("*.py"):
        if SKIP_DIRS & set(path.relative_to(BACKEND).parts) or path == CONFIG_FILE:
            continue
        yield path


def test_no_nemotron_id_outside_config():
    offenders = []
    for path in _python_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for n, line in enumerate(text.splitlines(), start=1):
            if NEMOTRON_ID.search(line):
                offenders.append(f"{path.relative_to(BACKEND)}:{n}")
    assert not offenders, f"move model IDs to llm_config.py: {offenders}"


def test_no_configured_model_id_outside_config():
    ids = [r.model_id.lower() for r in llm_config.ROLES.values()]
    offenders = []
    for path in _python_files():
        text = path.read_text(encoding="utf-8", errors="replace").lower()
        offenders += [f"{path.relative_to(BACKEND)} has {i}" for i in ids if i in text]
    assert not offenders, offenders


def test_the_scan_itself_catches_a_planted_id():
    assert NEMOTRON_ID.search('MODEL = "NVIDIA/NVIDIA-NEMOTRON-3-Nano-30B-A3B"')
    assert NEMOTRON_ID.search("'nvidia/nemotron-3-super-120b-a12b'")
    assert not NEMOTRON_ID.search('"nvidia/parakeet-tdt-0.6b-v3"')
