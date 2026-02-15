import json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data" / "conversations"
THREAD_MAP = Path(__file__).parent / "data" / "thread_map.json"


def load(thread_id: str, max_messages: int = 50) -> list[dict]:
    path = DATA_DIR / f"{thread_id}.jsonl"
    if not path.exists():
        return []
    lines = path.read_text().strip().split("\n")
    return [json.loads(line) for line in lines[-max_messages:] if line]


def append(thread_id: str, role: str, content: str):
    path = DATA_DIR / f"{thread_id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps({"role": role, "content": content}) + "\n")


def map_timestamp(timestamp: int, thread_id: str):
    """Map a Signal message timestamp to a thread ID."""
    THREAD_MAP.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    if THREAD_MAP.exists():
        data = json.loads(THREAD_MAP.read_text())
    data[str(timestamp)] = thread_id
    THREAD_MAP.write_text(json.dumps(data))


def get_thread_for_timestamp(timestamp: int) -> str | None:
    """Look up which thread a Signal message timestamp belongs to."""
    if not THREAD_MAP.exists():
        return None
    data = json.loads(THREAD_MAP.read_text())
    return data.get(str(timestamp))
