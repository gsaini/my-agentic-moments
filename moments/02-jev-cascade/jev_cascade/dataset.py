"""The labeled requests: what each one needs, and which of Jev's documented weak spots it leans on."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data" / "requests.jsonl"

# Each trap targets one weak spot from https://docs.typesafe.ai/model-jaggedness/jev-1.13.
TRAPS: dict[str, str] = {
    "plain": "no trap: the control group",
    "negation": "negations and double negatives",
    "indirection": "a request relayed for someone else",
    "distractor": "irrelevant detail that names other routes",
    "injection": "text that tells the router what to answer",
    "boundary": "decided by a boundary the definitions spell out (literal reading)",
}


@dataclass(frozen=True)
class Request:
    id: str
    text: str
    route: str = ""  # the label — only in the eval set
    trap: str = ""
    note: str = ""  # why the label is what it is, where a reader might dispute it


def load_requests(ids: list[str] | None = None, path: Path = DATA) -> list[Request]:
    requests = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            raw = json.loads(line)
            if ids and raw["id"] not in ids:
                continue
            requests.append(Request(raw["id"], raw["text"], raw["route"], raw["trap"], raw.get("note", "")))
    return requests
