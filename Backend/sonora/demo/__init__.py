"""Demo content (the four sample sessions the frontend used to mock)."""

import json
from functools import cache
from importlib import resources
from typing import Any


@cache
def demo_sessions() -> list[dict[str, Any]]:
    data = resources.files(__package__).joinpath("sessions.json").read_text(encoding="utf-8")
    sessions: list[dict[str, Any]] = json.loads(data)["sessions"]
    return sessions
