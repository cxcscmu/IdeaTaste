"""Append-only jsonl files: the checkpoint format of every long-running step."""

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


class JsonlLog:
    """Append-only jsonl file, safe to write from several threads."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()

    def read(self):
        if not self.path.exists():
            return []
        with self.path.open(encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def append(self, row):
        with self.lock, self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def cached_map(items, key, function, path, concurrency=8):
    """{key(item): function(item)} for every item, resuming from the jsonl at `path`.

    A call that raises is logged with its error and attempted again on the next run; its key is missing from the returned dict.
    """
    log = JsonlLog(path)
    done = {row["key"]: row["value"] for row in log.read() if "error" not in row}
    todo = [item for item in items if key(item) not in done]

    def work(item):
        try:
            value = function(item)
        except Exception as error:  # noqa: BLE001 - logged, retried on the next run
            log.append({"key": key(item), "error": f"{type(error).__name__}: {error}"})
            return
        log.append({"key": key(item), "value": value})
        done[key(item)] = value

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        list(pool.map(work, todo))
    n_failed = sum(1 for item in items if key(item) not in done)
    if n_failed:
        print(f"[{Path(path).name}] {n_failed} of {len(items)} calls failed; rerun to retry them", flush=True)
    return {key(item): done[key(item)] for item in items if key(item) in done}
