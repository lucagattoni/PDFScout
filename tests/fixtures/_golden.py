import json
from pathlib import Path

_GOLDEN_DIR = Path(__file__).parent / "real_golden"


def load_golden(slot_id: str) -> dict:
    path = _GOLDEN_DIR / f"{slot_id}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text())
